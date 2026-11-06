import tempfile
import unittest
from pathlib import Path

from steam_manifest_updater.discovery import discover


class DiscoveryTests(unittest.TestCase):
    def test_multiple_libraries_and_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root, other = base / 'steam', base / 'Other Library'
            for library in (root, other):
                (library / 'steamapps').mkdir(parents=True)
            (root / 'steamapps/libraryfolders.vdf').write_text(
                '"libraryfolders" { "1" { "path" "' + str(other) + '" } }', encoding='utf-8')
            (root / 'steamapps/appmanifest_730.acf').write_text(
                '"AppState" { "appid" "730" "name" "Counter-Strike 2" "installdir" "Counter-Strike Global Offensive" }', encoding='utf-8')
            (other / 'steamapps/appmanifest_440.acf').write_text(
                '"AppState" { "appid" "440" "name" "Team Fortress 2" "installdir" "Team Fortress 2" }', encoding='utf-8')
            (other / 'steamapps/common/Team Fortress 2').mkdir(parents=True)
            apps, libraries = discover([root])
            self.assertEqual(len(libraries), 2)
            self.assertEqual({a.appid for a in apps}, {'730', '440'})
            self.assertFalse(next(a for a in apps if a.appid == '730').files_present)
            self.assertTrue(next(a for a in apps if a.appid == '440').files_present)

    def test_manifest_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'steamapps').mkdir()
            (root / 'steamapps/appmanifest_730.acf').write_text(
                '"AppState" { "appid" "730" "name" "Bad" "installdir" "../../bad" }', encoding='utf-8')
            warnings = []
            apps, _ = discover([root], warn=warnings.append)
            self.assertEqual(apps, [])
            self.assertTrue(any('outside' in warning for warning in warnings))
