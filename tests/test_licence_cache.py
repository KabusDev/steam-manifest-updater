"""Unit tests for one-session anonymous preflight and persistent skip cache."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from steam_manifest_updater.licence_cache import LicenceCache
from steam_manifest_updater.licence_snapshot import parse_snapshot, check_anonymous_licences_bulk
from steam_manifest_updater.runner import execute


OUTPUT = (
    'Connecting anonymously to Steam Public...OK\n'
    'License packageID 17906:\n'
    '- State : Active ( flags 0x10000 )\n'
    '- Apps : 4000, 440, 730 (3 in total)\n'
    '- Depots : 1, 2\n'
)
IDS = ['4000', '440', '730', '1517290', '1623730']


class Logger:
    def info(self, *args):
        pass
    def warning(self, *args):
        pass


class CacheTests(unittest.TestCase):
    def test_snapshot_explicit_membership(self):
        data = parse_snapshot(OUTPUT, IDS)
        self.assertEqual(data['4000']['status'], 'granted')
        self.assertEqual(data['1517290']['status'], 'denied')

    def test_snapshot_no_membership_fails_closed(self):
        modified = OUTPUT.replace('- Apps : 4000, 440, 730 (3 in total)\n', '')
        self.assertEqual(parse_snapshot(modified, IDS)['4000']['status'], 'unknown')

    def test_snapshot_truncated_listing_fails_closed(self):
        modified = OUTPUT.replace('4000, 440, 730 (3 in total)', '4000 (3 in total)')
        results = parse_snapshot(modified, IDS)
        self.assertEqual(results['4000']['status'], 'granted')
        self.assertEqual(results['1517290']['status'], 'unknown')
        self.assertIn('parsed 1 AppIDs, reported 3', results['1517290']['reason'])

    def test_malformed_package_does_not_hide_valid_grants(self):
        output = (
            'Connecting anonymously to Steam Public...OK\n'
            'License packageID 100:\n- State : Active\n- Apps : 4000 (3 in total)\n'
            'License packageID 200:\n- State : Active\n- Apps : 440, 730 (2 in total)\n'
        )
        results = parse_snapshot(output, IDS)
        self.assertEqual(results['4000']['status'], 'granted')
        self.assertEqual(results['440']['status'], 'granted')
        self.assertEqual(results['1517290']['status'], 'unknown')

    def test_snapshot_unrecognised_fails_closed(self):
        self.assertEqual(parse_snapshot('No licences returned', IDS)['4000']['status'], 'unknown')

    def test_snapshot_rate_limit(self):
        self.assertEqual(parse_snapshot('Rate Limit Exceeded', IDS)['4000']['status'], 'rate_limited')

    def test_one_session_for_multiple_games(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            with patch('steam_manifest_updater.licence_snapshot.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout=OUTPUT, stderr='')) as proc:
                got = check_anonymous_licences_bulk(exe, IDS)
            proc.assert_called_once()
            cmd = proc.call_args.args[0]
            self.assertEqual(cmd[1:], ['+login', 'anonymous', '+licenses_print', '+quit'])
            self.assertEqual(got['440']['status'], 'granted')
            self.assertEqual(got['1623730']['status'], 'denied')

    def test_cache_expires_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'licence-cache.json'
            now = datetime(2026, 11, 6, tzinfo=timezone.utc)
            c = LicenceCache(path, denied_days=7)
            c.put('1517290', {'status': 'denied', 'reason': 'test'}, now=now)
            c2 = LicenceCache(path, denied_days=7)
            self.assertEqual(c2.get('1517290', now=now + timedelta(days=6))['status'], 'denied')
            self.assertIsNone(c2.get('1517290', now=now + timedelta(days=8)))

    def test_granted_is_not_cached_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = LicenceCache(Path(folder) / 'cache.json')
            cache.put('4000', {'status': 'granted', 'reason': 'test'})
            self.assertIsNone(cache.get('4000'))

    def test_bulk_skips_cached_denial_without_relogin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache.json'
            cache = LicenceCache(path)
            cache.put('1517290', {'status': 'denied', 'reason': 'test'})
            job = {'mode': 'manual', 'detect_appid': '1517290', 'steamcmd_appid': '1517290',
                   'install_dir': str(Path(folder) / 'game')}
            with patch('steam_manifest_updater.runner.check_anonymous_licences_bulk') as bulk:
                results, checks = execute([job], Path(folder) / 'steamcmd.exe', 15,
                                          Logger(), licence_cache=cache)
            bulk.assert_not_called()
            self.assertEqual(results[0]['status'], 'skipped')
            self.assertTrue(checks[0]['cached'])

    def test_bulk_populates_cache_and_never_downloads_when_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache.json'
            cache = LicenceCache(path)
            job = {'mode': 'manual', 'detect_appid': '1517290', 'steamcmd_appid': '1517290',
                   'install_dir': str(Path(folder) / 'game')}
            with patch('steam_manifest_updater.runner.check_anonymous_licences_bulk',
                       return_value={'1517290': {'status': 'denied', 'reason': 'not owned'}}) as bulk, \
                 patch('steam_manifest_updater.runner.subprocess.run') as subprocess_mock:
                results, checks = execute([job], Path(folder) / 'steamcmd.exe', 15,
                                          Logger(), licence_cache=cache)
            bulk.assert_called_once()
            subprocess_mock.assert_not_called()
            self.assertEqual(results[0]['status'], 'skipped')
            self.assertIsNotNone(cache.get('1517290'))

    def test_rate_limit_sets_cooldown(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = LicenceCache(Path(folder) / 'cache.json')
            job = {'mode': 'manual', 'detect_appid': '123', 'steamcmd_appid': '123',
                   'install_dir': str(Path(folder) / 'game')}
            with patch('steam_manifest_updater.runner.check_anonymous_licences_bulk',
                       return_value={'123': {'status': 'rate_limited', 'reason': '429'}}):
                results, _ = execute([job], Path(folder) / 'steamcmd.exe', 15,
                                     Logger(), licence_cache=cache)
            self.assertIsNotNone(cache.cooldown())
            self.assertEqual(results[0]['status'], 'skipped')


if __name__ == '__main__':
    unittest.main()
