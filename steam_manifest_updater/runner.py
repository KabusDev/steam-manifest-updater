"""Build manifest-driven and explicit SteamCMD jobs, then gate them by anonymous licence.

A local ACF file is an inventory record, NOT an anonymous SteamCMD licence.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, project_path
from .licence_cache import LicenceCache
from .licence_snapshot import check_anonymous_licences_bulk

SUCCESS_PATTERN = re.compile(r"(?im)^\s*Success!\s+App\b")
ERROR_PATTERN = re.compile(r"(?im)^\s*(?:ERROR!|Error!)\s+(?:Failed|App\b)")
LICENSE_HEADER = re.compile(r"(?im)^\s*License packageID\s+(\d+)\s*:")
ACTIVE_STATE = re.compile(r"(?im)^\s*-?\s*State\s*:\s*Active\b")
APPS_LINE = re.compile(r"(?im)^\s*-?\s*Apps\s*:\s*([^\r\n]+)")


@contextmanager
def run_lock(path: Path):
    """Cross-platform process lock, released automatically on exit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as file:
        try:
            if os.name == 'nt':
                import msvcrt
                file.seek(0)
                if not file.read(1):
                    file.seek(0)
                    file.write(b'\0')
                    file.flush()
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ConfigError('Another updater run is already active (file lock).') from exc
        try:
            file.seek(0)
            file.truncate()
            file.write(f'{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n'.encode())
            file.flush()
            yield
        finally:
            file.seek(0)
            if os.name == 'nt':
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _inside(target: Path, root: Path) -> bool:
    return target == root or root in target.parents


def validate_target(install_dir: Path, libraries: list[Path], steamcmd: Path):
    """Explicit SteamCMD jobs must not alter Steam client libraries."""
    if not install_dir.is_absolute() or install_dir == Path(install_dir.anchor):
        raise ConfigError('Manual install_dir must be an absolute, non-root directory')
    if _inside(install_dir, steamcmd.parent) or _inside(steamcmd.parent, install_dir):
        raise ConfigError('SteamCMD target overlaps the SteamCMD installation')
    for library in libraries:
        if _inside(install_dir, library) or _inside(library, install_dir):
            raise ConfigError(f'Manual target {install_dir} overlaps Steam library {library}')


def plan_jobs(config: dict, apps, libraries: list[Path], repo: Path):
    """Plan auto jobs from installed manifests and optional explicit overrides.

    A manual job, including a disabled one, overrides auto handling of its detect_appid.
    The returned inventory gives users a reason for every skipped local manifest.
    """
    steamcmd = project_path(repo, config.get('steamcmd_path', 'tools/steamcmd/steamcmd.exe'))
    auto = config.get('auto_update', {})
    auto_enabled = auto.get('enabled', False)  # legacy configs stay opt-in; new template enables it
    excluded = set(auto.get('exclude_appids', []))
    explicit = config.get('jobs', [])
    overridden = {job['detect_appid'] for job in explicit}
    installed = {app.appid for app in apps if app.files_present}
    jobs, inventory = [], []

    for app in sorted(apps, key=lambda item: (item.appid, str(item.install_dir))):
        entry = {'appid': app.appid, 'name': app.name, 'manifest': str(app.manifest),
                 'install_dir': str(app.install_dir), 'files_present': app.files_present}
        if not app.files_present:
            entry['status'], entry['reason'] = 'skipped', 'installation folder missing'
        elif app.appid in overridden:
            entry['status'], entry['reason'] = 'explicit', 'handled by matching config job'
        elif not auto_enabled:
            entry['status'], entry['reason'] = 'skipped', 'automatic updates disabled'
        elif app.appid in excluded:
            entry['status'], entry['reason'] = 'skipped', 'AppID excluded by config'
        else:
            jobs.append({'mode': 'auto', 'detect_appid': app.appid, 'steamcmd_appid': app.appid,
                         'name': app.name, 'install_dir': str(app.install_dir),
                         'validate': auto.get('validate', False),
                         'skip_if_steam_running': auto.get('skip_if_steam_running', True)})
            entry['status'], entry['reason'] = 'planned', 'automatic manifest match'
        inventory.append(entry)

    for job in explicit:
        if not job.get('enabled', False):
            continue
        if job.get('require_manifest', True) and job['detect_appid'] not in installed:
            inventory.append({'appid': job['detect_appid'], 'status': 'skipped', 'mode': 'manual',
                              'reason': 'manual job requires installed manifest'})
            continue
        target = Path(job['install_dir']).expanduser()
        if not target.is_absolute():
            raise ConfigError(f'Manual install_dir for AppID {job["detect_appid"]} must be absolute')
        target = target.resolve()
        validate_target(target, libraries, steamcmd)
        jobs.append({'mode': 'manual', 'detect_appid': job['detect_appid'],
                     'steamcmd_appid': job['steamcmd_appid'], 'name': job.get('name', 'Manual job'),
                     'install_dir': str(target), 'validate': job.get('validate', False),
                     'skip_if_steam_running': False})
        inventory.append({'appid': job['steamcmd_appid'], 'status': 'planned',
                          'mode': 'manual', 'reason': 'enabled config job', 'install_dir': str(target)})
    return jobs, steamcmd, inventory


def parse_licence_result(output: str, appid: str) -> dict:
    """Fail closed: only an explicitly ACTIVE licence package grants an update attempt.

    Command output and app metadata are not a guarantee of depot access. Unknown is
    deliberately distinct from denied, and both prevent download attempts.
    """
    headers = list(LICENSE_HEADER.finditer(output))
    for index, match in enumerate(headers):
        block = output[match.end():headers[index + 1].start() if index + 1 < len(headers) else len(output)]
        if int(match.group(1)) == 0 or not ACTIVE_STATE.search(block):
            continue
        apps_match = APPS_LINE.search(block)
        if not apps_match:
            return {'status': 'unknown', 'reason': 'licence package lacks an explicit AppID list'}
        ids = re.findall(r'\b\d+\b', apps_match.group(1).split('(')[0])
        if appid not in ids:
            continue
        return {'status': 'granted', 'reason': 'anonymous SteamCMD reported an active licence package',
                'package_id': match.group(1)}
    if headers or re.search(r'(?i)\b(?:no (?:active )?licen[cs]es?|no subscription)\b', output):
        return {'status': 'denied', 'reason': 'no active matching licence reported by anonymous SteamCMD'}
    return {'status': 'unknown', 'reason': 'SteamCMD did not return a recognisable licence response'}


def check_anonymous_licence(steamcmd: Path, appid: str, timeout_seconds: int = 90) -> dict:
    """Read-only anonymous preflight; this intentionally never calls app_update."""
    if not steamcmd.is_file():
        return {'status': 'unknown', 'reason': f'SteamCMD executable missing: {steamcmd}'}
    command = [str(steamcmd), '+login', 'anonymous', '+licenses_for_app', appid, '+quit']
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'unknown', 'reason': 'anonymous licence probe timed out'}
    except OSError as exc:
        return {'status': 'unknown', 'reason': f'could not run SteamCMD licence probe: {exc}'}
    output = '\n'.join((result.stdout or '', result.stderr or ''))
    if result.returncode != 0:
        return {'status': 'unknown', 'reason': f'licence probe exited with code {result.returncode}'}
    if re.search(r'(?i)(?:login failure|failed to log in|invalid password|offline mode|not logged on)', output):
        return {'status': 'unknown', 'reason': 'SteamCMD anonymous login was not successful'}
    return parse_licence_result(output, appid)


def steam_client_running() -> bool | None:
    """For in-place updates, skip if Steam is open; unknown is also a skip."""
    if os.name == 'nt':
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq steam.exe', '/FO', 'CSV', '/NH'],
                                    capture_output=True, text=True, errors='replace', timeout=15)
            if result.returncode != 0:
                return None
            rows = list(csv.reader(io.StringIO(result.stdout)))
            return any(row and row[0].strip().lower() == 'steam.exe' for row in rows)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if os.name == 'posix':
        try:
            result = subprocess.run(['pgrep', '-x', 'steam'], capture_output=True, timeout=15)
            if result.returncode == 0:
                return True
            if result.returncode == 1:
                return False
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def execute(jobs: list[dict], steamcmd: Path, timeout_minutes: int, logger, *,
            licence_timeout_seconds: int = 90, dry_run: bool = False,
            licence_cache: LicenceCache | None = None,
            refresh_licences: bool = False,
            licences_only: bool = False) -> tuple[list[dict], list[dict]]:
    """Skip denied apps, check all uncached AppIDs with one anonymous login.

    The legacy single-app probe remains available for direct callers without
    a cache, but the CLI always supplies a cache and uses the fast snapshot.
    """
    checks = {}
    if licence_cache is not None:
        ids = sorted({job['steamcmd_appid'] for job in jobs}, key=int)
        cooldown = licence_cache.cooldown()
        uncached = []
        for appid in ids:
            hit = None if refresh_licences else licence_cache.get(appid)
            if hit:
                checks[appid] = hit
            elif cooldown:
                checks[appid] = {'status': 'rate_limited', 'reason': f'cooldown in effect until {cooldown}'}
            else:
                uncached.append(appid)
        if uncached:
            batch = check_anonymous_licences_bulk(steamcmd, uncached, licence_timeout_seconds)
            for appid, outcome in batch.items():
                checks[appid] = outcome
                if outcome['status'] in ('denied', 'granted'):
                    licence_cache.put(appid, outcome)
                elif outcome['status'] == 'rate_limited':
                    cooldown = licence_cache.rate_limited()
                    logger.warning('SteamCMD rate limited; licence checks stopped until %s', cooldown)
            logger.info('Anonymous licence snapshot: %d AppIDs checked using one SteamCMD session', len(uncached))
    results = []
    steam_state = None
    for job in jobs:
        appid = job['steamcmd_appid']
        if appid not in checks:
            checks[appid] = check_anonymous_licence(steamcmd, appid, licence_timeout_seconds)
        check = checks[appid]
        logger.info('LICENCE AppID %s: %s%s (%s)', appid, check['status'].upper(),
                    ' [CACHE]' if check.get('cached') else '', check['reason'])
        base = {**job, 'licence_status': check['status']}
        if check['status'] != 'granted':
            reason = f'Skipped: anonymous licence {check["status"]}: {check["reason"]}'
            results.append({**base, 'status': 'skipped', 'success': None, 'message': reason})
            logger.info('%s AppID %s', reason, appid)
            continue
        if job.get('skip_if_steam_running', False) and not licences_only:
            if steam_state is None:
                steam_state = steam_client_running()
            if steam_state is not False:
                reason = 'Steam client is running' if steam_state is True else 'could not verify Steam client is closed'
                results.append({**base, 'status': 'skipped', 'success': None,
                                'message': f'Skipped in-place update: {reason}'})
                logger.warning('Skipping AppID %s: %s', appid, reason)
                continue
        if dry_run or licences_only:
            results.append({**base, 'status': 'dry-run', 'success': None,
                            'message': 'Licence preflight passed; no download started'})
            logger.info('PREVIEW: eligible AppID %s in %s; no download started', appid, job['install_dir'])
            continue
        command = [str(steamcmd), '+force_install_dir', job['install_dir'], '+login', 'anonymous',
                   '+app_update', appid]
        if job.get('validate', False):
            command.append('validate')
        command.append('+quit')
        logger.info('Updating %s AppID %s in %s', job.get('mode', 'manual'), appid, job['install_dir'])
        try:
            result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                    timeout=timeout_minutes * 60, check=False)
            output = '\n'.join(filter(None, (result.stdout, result.stderr)))
            if output:
                logger.info('SteamCMD output:\n%s', output)
            ok = result.returncode == 0 and bool(SUCCESS_PATTERN.search(output)) and not ERROR_PATTERN.search(output)
            message = 'SteamCMD confirmed success' if ok else 'SteamCMD did not confirm success (see log; depot access is not guaranteed)'
        except subprocess.TimeoutExpired:
            ok, message = False, f'Timed out after {timeout_minutes} minutes'
        except OSError as exc:
            ok, message = False, f'Could not launch SteamCMD: {exc}'
        results.append({**base, 'status': 'updated' if ok else 'failed', 'success': ok, 'message': message})
        logger.info('%s: AppID %s: %s', 'OK' if ok else 'FAILED', appid, message)
    return results, [{'appid': appid, **status} for appid, status in sorted(checks.items(), key=lambda x:int(x[0]))]


def write_summary(logdir: Path, summary: dict, stamp: str) -> Path:
    logdir.mkdir(parents=True, exist_ok=True)
    target = logdir / f'{stamp}.json'
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return target
