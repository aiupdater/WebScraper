import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings
from system.paths import config_path


class ConfigurationPathsTests(unittest.TestCase):
    def test_old_categories_are_moved_and_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            old = base / 'categories.local.json'
            old.write_text(json.dumps(['Tiefbau', 'Abbruch']))
            api = DesktopAPI(base, settings=MySQLSettings(password='test-only'))
            self.assertEqual(api.bootstrap()['categories'], ['Tiefbau', 'Abbruch'])
            self.assertFalse(old.exists())
            self.assertEqual(json.loads((base/'config/categories.local.json').read_text()), ['Tiefbau', 'Abbruch'])

    def test_old_mysql_settings_are_preserved_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            content = b'{"host":"test.invalid", "password":"test-only"}\n'
            old = base / 'mysql.local.json'
            old.write_bytes(content)
            target = config_path('mysql.local.json', base)
            self.assertEqual(target.read_bytes(), content)
            self.assertFalse(old.exists())

    def test_existing_config_is_never_overwritten_by_legacy(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            target = config_path('mysql.local.json', base)
            target.write_text('new settings')
            old = base/'mysql.local.json'
            old.write_text('old settings')
            self.assertEqual(config_path('mysql.local.json', base).read_text(), 'new settings')
            self.assertEqual(old.read_text(), 'old settings')

    def test_example_env_is_not_loaded_but_active_env_is(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            base = Path(folder)
            target = config_path('mysql.local.json', base)
            target.write_text(json.dumps({'password': 'local-test-only'}))
            (target.parent/'.env.example').write_text('MYSQLPASSWORD=example-test-only')
            self.assertEqual(MySQLSettings.load(target).password, 'local-test-only')
            (base/'.env').write_text('MYSQLPASSWORD=active-test-only')
            config_path('.env', base)
            self.assertEqual(MySQLSettings.load(target).password, 'active-test-only')

    def test_configuration_name_cannot_escape_config_folder(self):
        with self.assertRaises(ValueError):
            config_path('../other.txt')
