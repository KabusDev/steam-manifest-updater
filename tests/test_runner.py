import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from steam_manifest_updater.config import ConfigError, load_config
from steam_manifest_updater.discovery import InstalledApp
from steam_manifest_updater.runner import execute, plan_jobs, validate_target


class RunnerTests(unittest.TestCase):
    def test_disabled_and_undetected_jobs_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = {'jobs': [
                {'enabled': False, 'detect_appid': '730'},
                {'enabled': True, 'detect_appid': '999', 'steamcmd_appid': '999',
                 'install_dir': str(root / 'servers/unknown')},
            ]}
            jobs, _ = plan_jobs(config, [], [], root)
            self.assertEqual(jobs, [])

    def test_approved_game_uses_isolated_directory_and_anonymous_login(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = root / 'steam'
            game = library / 'steamapps/common/Example'
            game.mkdir(parents=True)
            app = InstalledApp('730', 'Example', library, game, library / 'steamapps/appmanifest_730.acf', True)
            config = {'jobs': [{'enabled': True, 'detect_appid': '730', 'steamcmd_appid': '740',
                                'install_dir': str(root / 'servers/csgo'), 'validate': False}]}
            jobs, steamcmd = plan_jobs(config, [app], [library], root)
            steamcmd.parent.mkdir(parents=True)
            steamcmd.touch()
            with patch('steam_manifest_updater.runner.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout="Success! App '740' fully installed.\n", stderr='')) as process:
                results = execute(jobs, steamcmd, 10, SimpleNamespace(info=lambda *args: None))
            self.assertTrue(results[0]['success'])
            command = process.call_args.args[0]
            self.assertEqual(command[1:5], ['+force_install_dir', str(root / 'servers/csgo'), '+login', 'anonymous'])
            self.assertEqual(command[5:7], ['+app_update', '740'])
            self.assertNotIn('validate', command)

    def test_refuse_steam_client_library_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ConfigError):
                validate_target(root / 'steam/steamapps/common/Example', [root / 'steam'], root / 'steamcmd/steamcmd.exe')

    def test_missing_success_confirmation_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'steamcmd.exe'
            exe.touch()
            job = {'detect_appid': '1', 'steamcmd_appid': '2', 'install_dir': str(Path(folder) / 'server'), 'validate': True}
            with patch('steam_manifest_updater.runner.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout='Steam>', stderr='')):
                results = execute([job], exe, 5, SimpleNamespace(info=lambda *args: None))
            self.assertFalse(results[0]['success'])

    def test_config_rejects_password_login(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text('{"jobs":[{"enabled":true,"detect_appid":"1","steamcmd_appid":"2",'
                            '"install_dir":"/servers/example","login":"my-username"}]}')
            with self.assertRaises(ConfigError):
                load_config(path)
