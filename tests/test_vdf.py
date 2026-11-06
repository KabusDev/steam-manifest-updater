import unittest
from steam_manifest_updater.vdf import VDFError, get_ci, parse


class VDFTests(unittest.TestCase):
    def test_nested_values_comments_and_windows_escapes(self):
        value = parse(r'''
            // Steam library index
            "libraryfolders" {
                "0" { "path" "C:\\Program Files (x86)\\Steam" "apps" { "730" "123" } }
                "1" { "path" "D:\\Steam Games" }
            }
        ''')
        self.assertEqual(value['libraryfolders']['1']['path'], r'D:\Steam Games')
        self.assertEqual(value['libraryfolders']['0']['apps']['730'], '123')

    def test_key_casing(self):
        self.assertEqual(get_ci({'AppID': '730'}, 'appid'), '730')

    def test_invalid(self):
        with self.assertRaises(VDFError):
            parse('"AppState" { "appid" "730"')
        with self.assertRaises(VDFError):
            parse('"AppState" "unterminated')
