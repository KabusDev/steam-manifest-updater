import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from steam_manifest_updater.config import ConfigError, load_config
from steam_manifest_updater.discovery import InstalledApp
from steam_manifest_updater.runner import (
    check_anonymous_licence, execute, parse_licence_result, plan_jobs, validate_target,
)


class DummyLogger:
    def info(self, *args):
        pass

    def warning(self, *args):
        pass


def app(root, appid='730'):
    library = root / 'steam'
    directory = library / 'steamapps/common/Example'
    directory.mkdir(parents=True, exist_ok=True)
    return InstalledApp(appid, 'Example', library, directory, library / f'steamapps/appmanifest_{appid}.acf', True)


class RunnerTests(unittest.TestCase):
    def test_new_config_auto_jobs_detected_by_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = app(root)
            jobs, _, inventory = plan_jobs({'auto_update': {'enabled': True}, 'jobs': []},
                                           [installed], [installed.library], root)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['steamcmd_appid'], '730')
            self.assertEqual(jobs[0]['install_dir'], str(installed.install_dir))
            self.assertEqual(jobs[0]['mode'], 'auto')
            self.assertEqual(inventory[0]['status'], 'planned')

    def test_legacy_config_does_not_implicitly_enable_auto(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = app(root)
            jobs, _, inventory = plan_jobs({'jobs': []}, [installed], [installed.library], root)
            self.assertEqual(jobs, [])
            self.assertEqual(inventory[0]['status'], 'skipped')

    def test_config_exclusion_and_disabled_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = app(root)
            config = {'auto_update': {'enabled': True}, 'jobs': [{'detect_appid': '730', 'enabled': False}]}
            jobs, _, inventory = plan_jobs(config, [installed], [installed.library], root)
            self.assertEqual(jobs, [])
            self.assertEqual(inventory[0]['status'], 'explicit')
            config['jobs'] = []
            config['auto_update']['exclude_appids'] = ['730']
            jobs, _, inventory = plan_jobs(config, [installed], [installed.library], root)
            self.assertEqual(jobs, [])
            self.assertEqual(inventory[0]['reason'], 'AppID excluded by config')

    def test_explicit_override_keeps_separate_server_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = app(root)
            config = {'auto_update': {'enabled': True}, 'jobs': [
                {'enabled': True, 'detect_appid': '730', 'steamcmd_appid': '740',
                 'install_dir': str(root / 'servers/csgo')}]}
            jobs, _, inventory = plan_jobs(config, [installed], [installed.library], root)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['mode'], 'manual')
            self.assertEqual(jobs[0]['steamcmd_appid'], '740')
            self.assertEqual(Path(jobs[0]['install_dir']).resolve(), (root / 'servers/csgo').resolve())
            self.assertEqual(inventory[0]['status'], 'explicit')

    def test_manual_only_without_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = {'jobs': [{'enabled': True, 'detect_appid': '740', 'steamcmd_appid': '740',
                                'require_manifest': False, 'install_dir': str(root / 'server')}]}
            jobs, _, _ = plan_jobs(config, [], [], root)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['mode'], 'manual')

    def test_missing_install_folder_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = app(root)
            missing = InstalledApp(installed.appid, installed.name, installed.library,
                                   installed.install_dir, installed.manifest, False)
            jobs, _, inventory = plan_jobs({'auto_update': {'enabled': True}}, [missing],
                                           [installed.library], root)
            self.assertEqual(jobs, [])
            self.assertEqual(inventory[0]['reason'], 'installation folder missing')

    def test_parse_granted_active_matching_app(self):
        output = ('License packageID 321:\n- State : Active (flags 0x10000)\n'
                  '- Apps : 730, 740, (2 in total)\n- Depots : 100, 200\n')
        self.assertEqual(parse_licence_result(output, '730')['status'], 'granted')
        self.assertEqual(parse_licence_result(output, '900')['status'], 'denied')
        self.assertEqual(parse_licence_result(output.replace('Active', 'Inactive'), '730')['status'], 'denied')
        self.assertEqual(parse_licence_result('No active licenses for app 730', '730')['status'], 'denied')
        self.assertEqual(parse_licence_result('Steam> app_info_print 730', '730')['status'], 'unknown')

    def test_licence_query_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            with patch('steam_manifest_updater.runner.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout='License packageID 1:\n- State : Active\n- Apps : 740\n', stderr='')) as process:
                result = check_anonymous_licence(exe, '740')
            self.assertEqual(result['status'], 'granted')
            cmd = process.call_args.args[0]
            self.assertEqual(cmd[1:], ['+login', 'anonymous', '+licenses_for_app', '740', '+quit'])
            self.assertNotIn('+app_update', cmd)

    def test_failed_or_unrecognised_license_does_not_download(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            job = {'mode': 'manual', 'detect_appid': '1', 'steamcmd_appid': '2',
                   'install_dir': str(Path(folder) / 'server'), 'validate': False}
            with patch('steam_manifest_updater.runner.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout='Steam> No licenses for AppID 2', stderr='')) as process:
                results, checks = execute([job], exe, 5, DummyLogger())
            self.assertEqual(results[0]['status'], 'skipped')
            self.assertEqual(checks[0]['status'], 'denied')
            self.assertEqual(process.call_count, 1)
            self.assertNotIn('+app_update', process.call_args.args[0])

    def test_granted_license_updates_manual_job(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            job = {'mode': 'manual', 'detect_appid': '730', 'steamcmd_appid': '740',
                   'install_dir': str(Path(folder) / 'server'), 'validate': False}
            def fake_run(cmd, **kwargs):
                if '+licenses_for_app' in cmd:
                    return SimpleNamespace(returncode=0, stdout='License packageID 42:\n- State : Active\n- Apps : 740\n', stderr='')
                return SimpleNamespace(returncode=0, stdout="Success! App '740' fully installed.\n", stderr='')
            with patch('steam_manifest_updater.runner.subprocess.run', side_effect=fake_run) as process:
                results, checks = execute([job], exe, 10, DummyLogger())
            self.assertTrue(results[0]['success'])
            self.assertEqual(results[0]['status'], 'updated')
            self.assertEqual(checks[0]['status'], 'granted')
            self.assertEqual(process.call_count, 2)
            command = process.call_args.args[0]
            self.assertEqual(command[1:5], ['+force_install_dir', str(Path(folder) / 'server'), '+login', 'anonymous'])
            self.assertEqual(command[5:7], ['+app_update', '740'])

    def test_auto_skips_steam_open(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            job = {'mode': 'auto', 'detect_appid': '730', 'steamcmd_appid': '730',
                   'install_dir': str(Path(folder) / 'steamapps/common/Demo'),
                   'skip_if_steam_running': True}
            with patch('steam_manifest_updater.runner.check_anonymous_licence',
                       return_value={'status': 'granted', 'reason': 'test'}), \
                 patch('steam_manifest_updater.runner.steam_client_running', return_value=True), \
                 patch('steam_manifest_updater.runner.subprocess.run') as process:
                results, _ = execute([job], exe, 10, DummyLogger())
            self.assertEqual(results[0]['status'], 'skipped')
            process.assert_not_called()

    def test_dry_run_does_not_download_even_if_granted(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            job = {'mode': 'manual', 'detect_appid': '740', 'steamcmd_appid': '740',
                   'install_dir': str(Path(folder) / 'server')}
            with patch('steam_manifest_updater.runner.check_anonymous_licence',
                       return_value={'status': 'granted', 'reason': 'test'}), \
                 patch('steam_manifest_updater.runner.subprocess.run') as process:
                results, _ = execute([job], exe, 10, DummyLogger(), dry_run=True)
            self.assertEqual(results[0]['status'], 'dry-run')
            process.assert_not_called()

    def test_refuse_manual_steam_library_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ConfigError):
                validate_target(root / 'steam/steamapps/common/Example', [root / 'steam'], root / 'steamcmd/steamcmd.exe')

    def test_config_rejects_password_login(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text('{"jobs":[{"enabled":true,"detect_appid":"1","steamcmd_appid":"2",'
                            '"install_dir":"/servers/example","login":"my-username"}]}')
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_config_rejects_invalid_exclusions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text('{"auto_update":{"enabled":true,"exclude_appids":[123]}}')
            with self.assertRaises(ConfigError):
                load_config(path)
