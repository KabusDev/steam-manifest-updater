import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from steam_manifest_updater.cli import main


class CLITests(unittest.TestCase):
    def test_discovery_and_dry_run_from_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            steam = root / 'steam'
            apps = steam / 'steamapps'
            apps.mkdir(parents=True)
            (apps / 'common' / 'Demo').mkdir(parents=True)
            (apps / 'appmanifest_123.acf').write_text(
                '"AppState" { "appid" "123" "name" "Demo" "installdir" "Demo" }')
            config = root / 'config.json'
            config.write_text(json.dumps({'steam_roots': [str(steam)], 'log_dir': str(root / 'logs'),
                                          'jobs': [{'enabled': True, 'detect_appid': '123',
                                                    'steamcmd_appid': '456', 'install_dir': str(root / 'server')}] }))
            with patch('steam_manifest_updater.cli.detect_steam_roots', return_value=[]):
                with redirect_stdout(io.StringIO()) as out:
                    code = main(['--config', str(config), 'discover'])
                self.assertEqual(code, 0)
                self.assertIn('Demo [123]', out.getvalue())
                code = main(['--config', str(config), 'run', '--dry-run'])
            self.assertEqual(code, 0)
            reports = list((root / 'logs').glob('*.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(report['planned'][0]['steamcmd_appid'], '456')
            self.assertEqual(report['results'], [])
