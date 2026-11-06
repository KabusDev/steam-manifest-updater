"""User-facing command line and report output."""
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
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(logdir / f'{stamp}.log', encoding='utf-8')):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def main(argv=None):
    p = argparse.ArgumentParser(prog='steam-manifest-updater', description='Discover Steam installs and safely manage opt-in SteamCMD updates')
    p.add_argument('--config', type=Path, default=REPO / 'config.json', help='Path to config.json')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Create editable config.json, without overwriting it')
    sub.add_parser('discover', help='List detected Steam library games (no updates)')
    sub.add_parser('doctor', help='Check discovery and enabled update jobs')
    cmd = sub.add_parser('run', help='Run only enabled and detected SteamCMD jobs')
    cmd.add_argument('--dry-run', action='store_true', help='Show the plan without launching SteamCMD')
    args = p.parse_args(argv)

    try:
        if args.command == 'init':
            template = REPO / 'config.example.json'
            if args.config.exists():
                print(f'Already exists: {args.config} (not overwritten)')
            else:
                args.config.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(template, args.config)
                print(f'Created: {args.config}. Edit this file to enable your own jobs.')
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
                print('No libraries detected. Set steam_roots in config.json to your Steam installation directory.')
            return 0

        jobs, steamcmd = plan_jobs(config, apps, libraries, REPO)
        if args.command == 'doctor':
            print(f'Steam libraries: {len(libraries)} | Manifest entries: {len(apps)} | Enabled and detected jobs: {len(jobs)}')
            print(f'SteamCMD: {steamcmd} ({"found" if steamcmd.is_file() else "not installed"})')
            if not libraries:
                print('ACTION: Add your Steam folder to steam_roots in config.json.')
            if not config.get('jobs'):
                print('ACTION: No jobs configured. Add an explicit allowlist job to config.json.')
            if jobs and not steamcmd.is_file():
                print('ACTION: Run scripts/install-steamcmd.ps1.')
            for warning in warnings:
                print(f'WARNING: {warning}')
            return 0 if libraries and (not jobs or steamcmd.is_file()) else 1

        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        logdir = project_path(REPO, config.get('log_dir', 'logs'))
        logger = setup_logging(logdir, stamp)
        with run_lock(logdir / '.update.lock'):
            logger.info('Scanned %d manifest(s) in %d libraries; %d eligible SteamCMD job(s)', len(apps), len(libraries), len(jobs))
            for warning in warnings:
                logger.warning(warning)
            for job in jobs:
                logger.info('Planned AppID %s -> SteamCMD AppID %s -> %s', job['detect_appid'], job['steamcmd_appid'], job['install_dir'])
            if args.dry_run:
                logger.info('DRY RUN: No SteamCMD processes launched.')
                results = []
            else:
                results = execute(jobs, steamcmd, config.get('timeout_minutes', 180), logger)
            summary = {'timestamp': datetime.now().astimezone().isoformat(), 'dry_run': args.dry_run,
                       'manifests': len(apps), 'libraries': [str(x) for x in libraries],
                       'planned': jobs, 'results': results, 'warnings': warnings}
            report = write_summary(logdir, summary, stamp)
            logger.info('Report: %s', report)
        return 1 if any(not result['success'] for result in results) else 0
    except (ConfigError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
