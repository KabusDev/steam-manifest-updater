"""JSON configuration and validation for automatic and explicit update modes."""
from __future__ import annotations

import json
from pathlib import Path


class ConfigError(ValueError):
    pass


def _appid(value, label: str):
    if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
        raise ConfigError(f'{label} must be a positive Steam AppID string')


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f'{path} does not exist. Run: python -m steam_manifest_updater init')
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f'Cannot read config: {exc}') from exc
    if not isinstance(config, dict):
        raise ConfigError('The config file must contain a JSON object')
    for key in ('steam_roots', 'jobs'):
        if not isinstance(config.get(key, []), list):
            raise ConfigError(f'{key} must be a list')
    if not all(isinstance(x, str) for x in config.get('steam_roots', [])):
        raise ConfigError('steam_roots must contain strings')

    auto = config.get('auto_update', {})
    if not isinstance(auto, dict):
        raise ConfigError('auto_update must be an object')
    for key in ('enabled', 'validate', 'skip_if_steam_running'):
        if not isinstance(auto.get(key, True if key != 'validate' else False), bool):
            raise ConfigError(f'auto_update.{key} must be true or false')
    excluded = auto.get('exclude_appids', [])
    if not isinstance(excluded, list):
        raise ConfigError('auto_update.exclude_appids must be a list')
    for i, appid in enumerate(excluded):
        _appid(appid, f'auto_update.exclude_appids[{i}]')

    seen_jobs = set()
    for i, job in enumerate(config.get('jobs', [])):
        if not isinstance(job, dict):
            raise ConfigError(f'jobs[{i}] must be an object')
        for key in ('enabled', 'validate', 'require_manifest'):
            if not isinstance(job.get(key, key == 'require_manifest'), bool):
                raise ConfigError(f'jobs[{i}].{key} must be true or false')
        _appid(job.get('detect_appid'), f'jobs[{i}].detect_appid')
        if job['detect_appid'] in seen_jobs:
            raise ConfigError(f'Multiple manual jobs for AppID {job["detect_appid"]}; use one per AppID')
        seen_jobs.add(job['detect_appid'])
        if not job.get('enabled', False):
            continue
        for key in ('steamcmd_appid', 'install_dir'):
            if not isinstance(job.get(key), str) or not job[key].strip():
                raise ConfigError(f'jobs[{i}].{key} must be a non-empty string')
        _appid(job['steamcmd_appid'], f'jobs[{i}].steamcmd_appid')
        if job.get('login', 'anonymous') != 'anonymous':
            raise ConfigError('Only anonymous SteamCMD login is supported (no passwords in config)')

    timeout = config.get('timeout_minutes', 180)
    if not isinstance(timeout, int) or not (1 <= timeout <= 1440):
        raise ConfigError('timeout_minutes must be an integer from 1 to 1440')
    licence_timeout = config.get('licence_timeout_seconds', 90)
    if not isinstance(licence_timeout, int) or not (10 <= licence_timeout <= 600):
        raise ConfigError('licence_timeout_seconds must be between 10 and 600')
    cache = config.get('licence_cache', {})
    if not isinstance(cache, dict):
        raise ConfigError('licence_cache must be an object')
    for key, minimum, maximum, default in [
        ('denied_days', 0, 30, 7),
        ('granted_hours', 0, 168, 0),
        ('cooldown_minutes', 1, 1440, 60),
    ]:
        value = cache.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ConfigError(f'licence_cache.{key} must be an integer from {minimum} to {maximum}')
    return config


def project_path(repo: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else repo / path).resolve()
