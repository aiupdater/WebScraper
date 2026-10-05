import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from system.run_cleanup import remove_run_folder
from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'vysledky'
        self.run = self.root / 'run'
        self.profile = self.run / 'prohlizec_chromium' / 'Crashpad' / 'attachments'
        self.profile.mkdir(parents=True)
        self.database = self.run / 'stav.sqlite3'
        self.database.write_bytes(b'fixture')

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only attributes')
    def test_real_readonly_crashpad_directory_and_file(self):
        file = self.profile / 'attachment'
        file.write_text('fixture')
        os.chmod(file, stat.S_IREAD)
        os.chmod(self.profile, stat.S_IREAD)
        remove_run_folder(self.run, self.root)
        self.assertFalse(self.run.exists())

    def test_locked_profile_leaves_saved_results_and_reports_failure(self):
        with patch('system.run_cleanup.shutil.rmtree', side_effect=PermissionError('locked')), patch('system.run_cleanup.time.sleep'):
            with self.assertRaises(PermissionError):
                remove_run_folder(self.run, self.root)
        self.assertEqual(self.database.read_bytes(), b'fixture')

    def test_transient_lock_retries_profile_before_results(self):
        import shutil
        original = shutil.rmtree
        calls = []
        def remove(path, **kwargs):
            calls.append(Path(path).name)
            if len(calls) == 1:
                raise PermissionError('transient')
            original(path, **kwargs)
        with patch('system.run_cleanup.shutil.rmtree', side_effect=remove), patch('system.run_cleanup.time.sleep'):
            remove_run_folder(self.run, self.root)
        self.assertEqual(calls, ['prohlizec_chromium', 'prohlizec_chromium', 'run'])
        self.assertFalse(self.run.exists())

    def test_outside_results_and_results_root_are_rejected(self):
        for target in (Path(self.tmp.name), self.root):
            with self.assertRaises(ValueError): remove_run_folder(target, self.root)
        self.assertTrue(self.database.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only attributes')
    def test_saved_run_bridge_removes_readonly_crashpad(self):
        api = DesktopAPI(self.tmp.name, settings=MySQLSettings())
        os.chmod(self.profile, stat.S_IREAD)
        result = api.discard_saved_run(str(self.run))
        self.assertTrue(result['ok'], result)
        self.assertFalse(self.run.exists())
        self.assertEqual(api.poll_events(), [dict(type='discarded', folder=str(self.run))])
