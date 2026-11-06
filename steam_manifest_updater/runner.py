"""Execute explicit SteamCMD allowlist jobs, never directly patch Steam library folders."""
from __future__ import annotations

import json
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, project_path

SUCCESS_PATTERN = re.compile(r'(?im)^\s*Success!\s+App\b')
ERROR_PATTERN = re.compile(r'(?im)^\s*(?:ERROR!|Error!)\s+(?:Failed|App\b)')


@contextmanager
def run_lock(path: Path):
    """Cross-platform OS file lock; safely released on process exit or crash."""
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
    if not install_dir.is_absolute():
        raise ConfigError('install_dir must be an absolute path')
    if install_dir == Path(install_dir.anchor):
        raise ConfigError('Refusing to use a drive root as a SteamCMD install directory')
    if _inside(install_dir, steamcmd.parent):
        raise ConfigError('SteamCMD target must not be inside the SteamCMD installation')
    for library in libraries:
        if _inside(install_dir, library) or _inside(library, install_dir):
            raise ConfigError(f'Target {install_dir} overlaps Steam library {library}; choose a separate server folder')


def plan_jobs(config: dict, apps, libraries, repo: Path):
    """Only plan enabled jobs whose detection AppID is actually installed."""
    detected = {app.appid for app in apps if app.files_present}
    steamcmd = project_path(repo, config.get('steamcmd_path', 'tools/steamcmd/steamcmd.exe'))
    jobs = []
    for job in config.get('jobs', []):
        if not job.get('enabled', False):
            continue
        if job['detect_appid'] not in detected:
            continue
        raw = Path(job['install_dir']).expanduser()
        if not raw.is_absolute():
            raise ConfigError(f'install_dir for app {job["detect_appid"]} must be an absolute path')
        target = raw.resolve()
        validate_target(target, libraries, steamcmd)
        jobs.append({
            'detect_appid': job['detect_appid'],
            'steamcmd_appid': job['steamcmd_appid'],
            'install_dir': str(target),
            'validate': job.get('validate', False),
        })
    return jobs, steamcmd


def execute(jobs: list[dict], steamcmd: Path, timeout_minutes: int, logger) -> list[dict]:
    results = []
    if jobs and not steamcmd.is_file():
        raise ConfigError(f'SteamCMD missing: {steamcmd}. Run scripts/install-steamcmd.ps1 first.')
    for job in jobs:
        command = [str(steamcmd), '+force_install_dir', job['install_dir'], '+login', 'anonymous',
                   '+app_update', job['steamcmd_appid']]
        if job['validate']:
            command.append('validate')
        command.append('+quit')
        logger.info('Updating detected AppID %s using SteamCMD AppID %s in %s',
                    job['detect_appid'], job['steamcmd_appid'], job['install_dir'])
        try:
            result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                    timeout=timeout_minutes * 60, check=False)
            output = '\n'.join(filter(None, (result.stdout, result.stderr)))
            if output:
                logger.info('SteamCMD output:\n%s', output)
            ok = result.returncode == 0 and bool(SUCCESS_PATTERN.search(output)) and not ERROR_PATTERN.search(output)
            message = 'Verified SteamCMD success message' if ok else 'SteamCMD failed or did not confirm success (inspect log)'
        except subprocess.TimeoutExpired:
            ok, message = False, f'Timed out after {timeout_minutes} minutes'
        except OSError as exc:
            ok, message = False, f'Could not launch SteamCMD: {exc}'
        results.append({**job, 'success': ok, 'message': message})
        logger.info('%s: AppID %s: %s', 'OK' if ok else 'FAILED', job['steamcmd_appid'], message)
    return results


def write_summary(logdir: Path, summary: dict, stamp: str) -> Path:
    logdir.mkdir(parents=True, exist_ok=True)
    target = logdir / f'{stamp}.json'
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return target
