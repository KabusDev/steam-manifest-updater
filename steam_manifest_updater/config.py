"""JSON configuration and validation."""
from __future__ import annotations

import json
from pathlib import Path


class ConfigError(ValueError):
    pass


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
    for i, job in enumerate(config.get('jobs', [])):
        if not isinstance(job, dict):
            raise ConfigError(f'jobs[{i}] must be an object')
        if not isinstance(job.get('enabled', False), bool):
            raise ConfigError(f'jobs[{i}].enabled must be true or false')
        if not job.get('enabled', False):
            continue
        for key in ('detect_appid', 'steamcmd_appid', 'install_dir'):
            if not isinstance(job.get(key), str) or not job[key].strip():
                raise ConfigError(f'jobs[{i}].{key} must be a non-empty string')
        for key in ('detect_appid', 'steamcmd_appid'):
            if not job[key].isdigit() or int(job[key]) <= 0:
                raise ConfigError(f'jobs[{i}].{key} must be a positive Steam AppID')
        if job.get('login', 'anonymous') != 'anonymous':
            raise ConfigError('v0.1 permits only anonymous SteamCMD login (no passwords in config)')
        if not isinstance(job.get('validate', False), bool):
            raise ConfigError(f'jobs[{i}].validate must be true or false')
    timeout = config.get('timeout_minutes', 180)
    if not isinstance(timeout, int) or not (1 <= timeout <= 1440):
        raise ConfigError('timeout_minutes must be an integer from 1 to 1440')
    return config


def project_path(repo: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else repo / path).resolve()
