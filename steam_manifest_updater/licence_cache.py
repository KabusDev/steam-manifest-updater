"""Persistent, conservative SteamCMD anonymous licence decisions.

No credentials stored. Denials expire; grants are rechecked by default.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw)
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


class LicenceCache:
    def __init__(self, path: Path, denied_days: int = 7, granted_hours: int = 0,
                 cooldown_minutes: int = 60):
        self.path = Path(path)
        self.denied_days = denied_days
        self.granted_hours = granted_hours
        self.cooldown_minutes = cooldown_minutes
        self.warning = None
        self.data = {'version': 1, 'apps': {}, 'cooldown_until': None}
        if self.path.exists():
            try:
                parsed = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(parsed, dict) or parsed.get('version') != 1 or not isinstance(parsed.get('apps'), dict):
                    raise ValueError('unexpected cache structure')
                self.data = parsed
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                self.warning = f'Ignoring invalid licence cache: {exc}'

    def cooldown(self, now: datetime | None = None) -> str | None:
        expiry = parse_utc(self.data.get('cooldown_until'))
        return expiry.isoformat() if expiry and expiry > (now or utcnow()) else None

    def get(self, appid: str, now: datetime | None = None) -> dict | None:
        entry = self.data['apps'].get(str(appid))
        if not isinstance(entry, dict):
            return None
        status = entry.get('status')
        hours = self.denied_days * 24 if status == 'denied' else (
            self.granted_hours if status == 'granted' else 0
        )
        if hours <= 0:
            return None
        checked = parse_utc(entry.get('checked_at'))
        expiry = checked + timedelta(hours=hours) if checked else None
        if not expiry or expiry <= (now or utcnow()):
            return None
        result = {'status': status, 'reason': entry.get('reason', 'cached decision'),
                  'cached': True, 'checked_at': checked.isoformat(),
                  'next_check': expiry.isoformat()}
        if entry.get('package_id'):
            result['package_id'] = entry['package_id']
        return result

    def put(self, appid: str, result: dict, now: datetime | None = None) -> None:
        if result.get('status') not in ('denied', 'granted'):
            return
        entry = {'status': result['status'], 'reason': str(result.get('reason', '')),
                 'checked_at': (now or utcnow()).isoformat()}
        if result.get('package_id'):
            entry['package_id'] = str(result['package_id'])
        self.data['apps'][str(appid)] = entry
        self.save()

    def rate_limited(self, now: datetime | None = None) -> str:
        expiry = (now or utcnow()) + timedelta(minutes=self.cooldown_minutes)
        self.data['cooldown_until'] = expiry.isoformat()
        self.save()
        return expiry.isoformat()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        target = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.licence-cache-', suffix='.tmp',
                                             delete=False) as handle:
                target = Path(handle.name)
                json.dump(self.data, handle, indent=2, sort_keys=True)
                handle.write('\n')
            os.replace(target, self.path)
        finally:
            if target and target.exists():
                target.unlink()
