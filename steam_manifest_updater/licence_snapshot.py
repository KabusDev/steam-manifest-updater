"""One SteamCMD session to inspect anonymous licences for all candidate AppIDs.

Valve's console output is not a stable machine API. Unrecognised or incomplete
output fails closed: no updates and no long-lived negative cache.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

HEADER = re.compile(r"(?im)^\s*License packageID\s+(\d+)\s*:")
ACTIVE = re.compile(r"(?im)^\s*-?\s*State\s*:\s*Active\b")
APPS = re.compile(r"(?im)^\s*-?\s*Apps\s*:\s*([^\r\n]+)")
RATE_LIMIT = re.compile(r"(?i)(?:rate[ -]?limit|too many (?:requests|logins)|429\b|try again later)")
LOGIN_FAILURE = re.compile(r"(?i)(?:login failure|failed to log in|invalid password|offline mode|not logged on)")
SUCCESSFUL_LOGIN = re.compile(r"(?i)(?:Connecting anonymously to Steam Public\.\.\.OK|Waiting for client config\.\.\.OK|Logged in OK)")


def parse_snapshot(output: str, appids: list[str]) -> dict[str, dict]:
    """A complete recognised licence listing is required before inferring denial.

    Partial, ambiguous, or changed console output is UNKNOWN, not DENIED.
    """
    ids = set(appids)
    if RATE_LIMIT.search(output):
        return {aid: {'status': 'rate_limited', 'reason': 'SteamCMD reported a service rate limit'} for aid in ids}
    if LOGIN_FAILURE.search(output):
        return {aid: {'status': 'unknown', 'reason': 'anonymous login failed'} for aid in ids}

    headers = list(HEADER.finditer(output))
    # The prompt indicates SteamCMD completed the command. An empty licence
    # listing is not sufficient evidence to cache 200+ denials for a week.
    if not headers or not SUCCESSFUL_LOGIN.search(output):
        return {aid: {'status': 'unknown', 'reason': 'unrecognised or empty anonymous licence listing'} for aid in ids}

    granted = {}
    incomplete = []
    for i, match in enumerate(headers):
        block = output[match.end():headers[i+1].start() if i+1 < len(headers) else len(output)]
        if not ACTIVE.search(block):
            continue
        apps = APPS.search(block)
        package_id = match.group(1)
        if not apps:
            incomplete.append(f'package {package_id}: no AppID list')
            continue
        line = apps.group(1)
        listing = line.split('(')[0]
        listed_ids = set(re.findall(r"\b\d+\b", listing))
        count = re.search(r"\((\d+)\s+in\s+total\)", line, re.IGNORECASE)
        if not listed_ids or (count and len(listed_ids) != int(count.group(1))):
            reported = count.group(1) if count else 'not supplied'
            incomplete.append(f'package {package_id}: parsed {len(listed_ids)} AppIDs, reported {reported}')
        # Explicit package membership is useful evidence even if its list is
        # truncated. Never infer DENIED from a partially parsed snapshot.
        for aid in listed_ids & ids:
            granted[aid] = {'status': 'granted',
                            'reason': 'active anonymous licence explicitly lists this AppID',
                            'package_id': package_id}
    if incomplete:
        reason = ('incomplete anonymous licence snapshot: ' +
                  '; '.join(incomplete[:5]) +
                  (f'; and {len(incomplete) - 5} more packages' if len(incomplete) > 5 else ''))
        return {aid: granted.get(aid, {'status': 'unknown', 'reason': reason}) for aid in ids}
    return {aid: granted.get(aid, {'status': 'denied',
                                   'reason': 'no active package in anonymous licence snapshot lists AppID'})
            for aid in ids}


def check_anonymous_licences_bulk(steamcmd: Path, appids: list[str], timeout_seconds: int = 90) -> dict[str, dict]:
    ids = sorted(set(appids), key=int)
    if not ids:
        return {}
    def unknown(reason):
        return {aid: {'status': 'unknown', 'reason': reason} for aid in ids}
    if not steamcmd.is_file():
        return unknown(f'SteamCMD executable missing: {steamcmd}')
    command = [str(steamcmd), '+login', 'anonymous', '+licenses_print', '+quit']
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return unknown('anonymous licence snapshot timed out')
    except OSError as exc:
        return unknown(f'could not launch SteamCMD: {exc}')
    output = '\n'.join((result.stdout or '', result.stderr or ''))
    if RATE_LIMIT.search(output):
        return {aid: {'status': 'rate_limited', 'reason': 'SteamCMD reported a service rate limit'} for aid in ids}
    if result.returncode != 0:
        return unknown(f'anonymous licence snapshot returned exit code {result.returncode}')
    return parse_snapshot(output, ids)
