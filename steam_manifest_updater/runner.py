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
from .licence_snapshot import check_anonymous_licences_bulk, RATE_LIMIT, LOGIN_FAILURE

SUCCESS_PATTERN = re.compile(r"(?im)^\s*Success!\s+App\b")
UP_TO_DATE_PATTERN = re.compile(r"(?im)^\s*Success!\s+App\b[^\r\n]*\balready up to date\.")
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
    # Different AppIDs can share one Steam installation (Half-Life,
    # Spore DLC, etc.). Never blindly apply automatic updates there.
    shared_folders = {}
    for app in apps:
        if app.files_present:
            key = os.path.normcase(str(app.install_dir.resolve())).casefold()
            shared_folders.setdefault(key, set()).add(app.appid)
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
        elif len(shared_folders[os.path.normcase(str(app.install_dir.resolve())).casefold()]) > 1:
            shared_ids = shared_folders[os.path.normcase(str(app.install_dir.resolve())).casefold()]
            entry['status'], entry['reason'] = (
                'skipped', 'installation folder shared by AppIDs ' +
                ', '.join(sorted(shared_ids, key=int)) + '; use an isolated manual job')
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
    """Interpret a single-app query without manufacturing denials.

    SteamCMD can truncate an active package's Apps list (e.g. 32 of 737).
    Explicit membership is a grant, but absence from an incomplete package
    is UNKNOWN, never a cached DENIED.
    """
    if RATE_LIMIT.search(output):
        return {'status': 'rate_limited', 'reason': 'SteamCMD reported a rate limit'}
    if LOGIN_FAILURE.search(output):
        return {'status': 'unknown', 'reason': 'anonymous login failed'}
    headers = list(LICENSE_HEADER.finditer(output))
    incomplete = []
    for index, match in enumerate(headers):
        block = output[match.end():headers[index + 1].start() if index + 1 < len(headers) else len(output)]
        if int(match.group(1)) == 0 or not ACTIVE_STATE.search(block):
            continue
        apps_match = APPS_LINE.search(block)
        if not apps_match:
            incomplete.append('active package ' + match.group(1) + ' lacks an AppID list')
            continue
        line = apps_match.group(1)
        listed_ids = set(re.findall(r'\b\d+\b', line.split('(')[0]))
        if appid in listed_ids:
            return {'status': 'granted',
                    'reason': 'anonymous SteamCMD explicitly listed the requested AppID in an active package',
                    'package_id': match.group(1)}
        count = re.search(r'\((\d+)\s+in\s+total\)', line, re.IGNORECASE)
        if not count or len(listed_ids) != int(count.group(1)):
            reported = count.group(1) if count else 'unknown'
            incomplete.append(f'package {match.group(1)} lists {len(listed_ids)} of {reported} AppIDs')
    if incomplete:
        return {'status': 'unknown',
                'reason': 'single-app licence response incomplete: ' + '; '.join(incomplete[:3])}
    if headers or re.search(r'(?i)\b(?:no (?:active )?licen[cs]es?|no subscription)\b', output):
        return {'status': 'denied', 'reason': 'no matching active anonymous licence in complete response'}
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
    if RATE_LIMIT.search(output):
        return {'status': 'rate_limited', 'reason': 'SteamCMD reported a rate limit'}
    if result.returncode != 0:
        return {'status': 'unknown', 'reason': f'licence probe exited with code {result.returncode}'}
    if LOGIN_FAILURE.search(output):
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
            licences_only: bool = False,
            fallback_enabled: bool = True, fallback_max_per_run: int = 8,
            fallback_retry_hours: int = 48) -> tuple[list[dict], list[dict]]:
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
    # Only fall back when a valid anonymous login produced a truncated
    # package list. Login failures, missing SteamCMD and rate limits stay
    # fail-closed without starting more SteamCMD processes.
    if licence_cache is not None and fallback_enabled and not licence_cache.cooldown():
        unresolved = [
            appid for appid, check in checks.items()
            if check['status'] == 'unknown' and
               check['reason'].startswith('incomplete anonymous licence snapshot')
        ]
        due = sorted(
            (appid for appid in unresolved
             if refresh_licences or licence_cache.probe_due(appid, fallback_retry_hours)),
            key=lambda appid: (licence_cache.last_probe_at(appid) or
                               datetime.min.replace(tzinfo=timezone.utc), int(appid))
        )
        attempted = 0
        for appid in due[:fallback_max_per_run]:
            licence_cache.record_probe(appid)
            outcome = check_anonymous_licence(steamcmd, appid, licence_timeout_seconds)
            checks[appid] = outcome
            attempted += 1
            if outcome['status'] in ('denied', 'granted'):
                licence_cache.put(appid, outcome)
            if outcome['status'] == 'rate_limited':
                until = licence_cache.rate_limited()
                logger.warning('SteamCMD licence fallback rate limited; stopping until %s', until)
                break
        if unresolved:
            logger.info('LICENCE fallback: individually checked %d/%d incomplete-snapshot AppIDs '
                        '(limit %d per run; retry unknown after %d hours)',
                        attempted, len(unresolved), fallback_max_per_run, fallback_retry_hours)
    results = []
    steam_state = None
    logged_licences = set()
    cached_denials = 0
    grouped_unknowns = {}
    for job in jobs:
        appid = job['steamcmd_appid']
        if appid not in checks:
            checks[appid] = check_anonymous_licence(steamcmd, appid, licence_timeout_seconds)
        check = checks[appid]
        if appid not in logged_licences:
            logged_licences.add(appid)
            if check.get('cached') and check['status'] == 'denied':
                cached_denials += 1
            elif check['status'] in ('unknown', 'rate_limited'):
                key = (check['status'], check['reason'])
                grouped_unknowns[key] = grouped_unknowns.get(key, 0) + 1
            else:
                logger.info('LICENCE AppID %s: %s%s (%s)', appid, check['status'].upper(),
                            ' [CACHE]' if check.get('cached') else '', check['reason'])
        base = {**job, 'licence_status': check['status']}
        if check['status'] != 'granted':
            reason = f'Skipped: anonymous licence {check["status"]}: {check["reason"]}'
            results.append({**base, 'status': 'skipped', 'success': None, 'message': reason})
            continue
        active_cooldown = licence_cache.cooldown() if licence_cache is not None else None
        if active_cooldown and not (dry_run or licences_only):
            results.append({**base, 'status': 'skipped', 'success': None,
                            'message': f'SteamCMD rate-limit cooldown until {active_cooldown}'})
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
        already_current = False
        try:
            result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                    timeout=timeout_minutes * 60, check=False)
            output = '\n'.join(filter(None, (result.stdout, result.stderr)))
            if output:
                logger.info('SteamCMD output:\n%s', output)
            ok = result.returncode == 0 and bool(SUCCESS_PATTERN.search(output)) and not ERROR_PATTERN.search(output)
            already_current = ok and bool(UP_TO_DATE_PATTERN.search(output))
            message = ('SteamCMD already up to date' if already_current else
                       'SteamCMD confirmed installation/update' if ok else
                       'SteamCMD did not confirm success (see log; depot access is not guaranteed)')
            if RATE_LIMIT.search(output) and licence_cache is not None:
                until = licence_cache.rate_limited()
                message = f'SteamCMD rate limited; cooldown until {until}'
                ok = False
        except subprocess.TimeoutExpired:
            ok, message = False, f'Timed out after {timeout_minutes} minutes'
        except OSError as exc:
            ok, message = False, f'Could not launch SteamCMD: {exc}'
        status = 'already_up_to_date' if already_current and ok else 'updated' if ok else 'failed'
        results.append({**base, 'status': status, 'success': ok, 'message': message})
        logger.info('%s: AppID %s: %s', 'OK' if ok else 'FAILED', appid, message)
    for (status, reason), count in sorted(grouped_unknowns.items()):
        logger.warning('LICENCE %s: %d AppID(s) skipped: %s (details in JSON report)',
                       status.upper(), count, reason)
    if cached_denials:
        logger.info('Skipped %d cached anonymous-licence denials (details in JSON report)', cached_denials)
    return results, [{'appid': appid, **status} for appid, status in sorted(checks.items(), key=lambda x:int(x[0]))]


def write_summary(logdir: Path, summary: dict, stamp: str) -> Path:
    logdir.mkdir(parents=True, exist_ok=True)
    target = logdir / f'{stamp}.json'
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return target
