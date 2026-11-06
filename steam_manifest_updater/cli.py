"""User-facing command line, inventory reports and licence-aware update logs."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .config import ConfigError, load_config, project_path
from .discovery import detect_steam_roots, discover
from .runner import execute, plan_jobs, run_lock, write_summary

REPO = Path(__file__).resolve().parent.parent


def setup_logging(logdir: Path, stamp: str):
    logdir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('steam-manifest-updater')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(logdir / f'{stamp}.log', encoding='utf-8')):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def main(argv=None):
    p = argparse.ArgumentParser(prog='steam-manifest-updater',
                                description='Scan Steam manifests, check anonymous licences, then run eligible SteamCMD updates')
    p.add_argument('--config', type=Path, default=REPO / 'config.json', help='Path to config.json')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Create editable config.json without overwriting it')
    sub.add_parser('discover', help='List detected Steam manifests (does not update)')
    sub.add_parser('doctor', help='Check detection, SteamCMD and planned jobs')
    cmd = sub.add_parser('run', help='Check anonymous licences then update eligible apps')
    cmd.add_argument('--dry-run', action='store_true', help='Do read-only licence checks, no app downloads')
    args = p.parse_args(argv)

    try:
        if args.command == 'init':
            template = REPO / 'config.example.json'
            if args.config.exists():
                print(f'Already exists: {args.config} (not overwritten)')
            else:
                args.config.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(template, args.config)
                print(f'Created: {args.config}. Automatic mode enabled; configure exclusions or overrides as needed.')
            return 0

        config = load_config(args.config)
        roots = detect_steam_roots()
        for raw in config.get('steam_roots', []):
            root = project_path(REPO, raw)
            if root not in roots:
                roots.append(root)
        warnings = []
        apps, libraries = discover(roots, warn=warnings.append)
        if args.command == 'discover':
            print(f'Detected {len(apps)} app manifest(s) across {len(libraries)} Steam libraries:')
            for app in sorted(apps, key=lambda a: (a.name.casefold(), a.appid)):
                suffix = '' if app.files_present else ' [INSTALL FOLDER MISSING]'
                print(f'  {app.name} [{app.appid}] -> {app.install_dir}{suffix}')
            for warning in warnings:
                print(f'WARNING: {warning}', file=sys.stderr)
            if not libraries:
                print('No libraries detected. Add Steam library roots to config.json if necessary.')
            return 0

        jobs, steamcmd, inventory = plan_jobs(config, apps, libraries, REPO)
        if args.command == 'doctor':
            mode = 'enabled' if config.get('auto_update', {}).get('enabled', False) else 'disabled'
            print(f'Steam libraries: {len(libraries)} | Manifests: {len(apps)} | Jobs planned: {len(jobs)}')
            print(f'Automatic mode: {mode} | SteamCMD: {steamcmd} ({"found" if steamcmd.is_file() else "missing"})')
            print('Anonymous licence checks run at update time, NOT during doctor.')
            if not libraries:
                print('ACTION: Set steam_roots in config.json or install Steam.')
            if jobs and not steamcmd.is_file():
                print('ACTION: Run scripts/install-steamcmd.ps1 to enable licence preflights and updates.')
            for warning in warnings:
                print(f'WARNING: {warning}')
            return 0 if (libraries or any(not job.get('require_manifest', True) for job in config.get('jobs', []))) and (not jobs or steamcmd.is_file()) else 1

        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        logdir = project_path(REPO, config.get('log_dir', 'logs'))
        logger = setup_logging(logdir, stamp)
        with run_lock(logdir / '.update.lock'):
            logger.info('Found %d manifest(s) in %d libraries; %d candidate job(s)', len(apps), len(libraries), len(jobs))
            for warning in warnings:
                logger.warning(warning)
            for entry in inventory:
                logger.info('INVENTORY AppID %s: %s (%s)', entry['appid'], entry['status'], entry['reason'])
            results, licence_checks = execute(jobs, steamcmd, config.get('timeout_minutes', 180), logger,
                                               licence_timeout_seconds=config.get('licence_timeout_seconds', 90),
                                               dry_run=args.dry_run)
            summary = {
                'timestamp': datetime.now().astimezone().isoformat(),
                'dry_run': args.dry_run,
                'manifests': len(apps),
                'libraries': [str(x) for x in libraries],
                'inventory': inventory,
                'planned': jobs,
                'licence_checks': licence_checks,
                'results': results,
                'warnings': warnings,
            }
            report = write_summary(logdir, summary, stamp)
            logger.info('Report: %s', report)
            logger.info('Summary: %d updated, %d skipped, %d failed',
                        sum(x['status'] == 'updated' for x in results),
                        sum(x['status'] == 'skipped' for x in results),
                        sum(x['status'] == 'failed' for x in results))
        return 1 if any(result['status'] == 'failed' for result in results) else 0
    except (ConfigError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
