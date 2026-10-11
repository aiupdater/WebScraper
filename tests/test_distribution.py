import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from filelock import FileLock, Timeout
from system.paths import APP_ROOT, data_root, configure_bundled_browser
from system.instance import Instance
from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings
from system.updates import Updates, LATEST, ASSET_NAME, version_tuple, safe_download_url
from system.legacy_import import inspect_import, execute_import
from system.update_helper import install_request


class DistributionPathsTests(unittest.TestCase):
    def test_frozen_root_explicit_base_and_browser(self):
        with patch('sys.frozen', True, create=True), patch.dict(os.environ, {'LOCALAPPDATA': 'C:/Users/Test/AppData/Local'}):
            self.assertEqual(data_root().name, 'WebScraper')
            with tempfile.TemporaryDirectory() as folder:
                self.assertEqual(data_root(folder), Path(folder).resolve())
            configure_bundled_browser()
            self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(APP_ROOT / 'browsers'))

    def test_source_layout_and_empty_default_password(self):
        self.assertEqual(data_root(), APP_ROOT)
        self.assertEqual(MySQLSettings().password, '')

    def test_single_instance_and_updater_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            with Instance(folder):
                with self.assertRaises(Timeout):
                    with Instance(folder):
                        pass
            with FileLock(str(Path(folder) / '.update.lock')):
                with self.assertRaises(Timeout):
                    with Instance(folder):
                        pass

    def test_update_install_defers_all_busy_states(self):
        with tempfile.TemporaryDirectory() as folder:
            api = DesktopAPI(folder)
            for flag in ('_running', '_db_busy', '_closing', '_maintenance'):
                setattr(api, flag, True)
                self.assertFalse(api.install_update()['ok'])
                setattr(api, flag, False)
            self.assertFalse(api.install_update()['ok'])  # source launch cannot update itself


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.payload = b'unit-test-installer-not-executable'
        self.setup_url = 'https://github.com/aiupdater/WebScraper/releases/download/v1.1.0/' + ASSET_NAME
        self.manifest_url = 'https://github.com/aiupdater/WebScraper/releases/download/v1.1.0/update.json'
        self.manifest = {'version':'1.1.0', 'asset':ASSET_NAME, 'size':len(self.payload),
                         'sha256':hashlib.sha256(self.payload).hexdigest()}
        self.release = {'tag_name':'v1.1.0','draft':False,'prerelease':False,'body':'Nová verze',
            'assets':[{'name':ASSET_NAME,'size':len(self.payload),'browser_download_url':self.setup_url},
                      {'name':'update.json','browser_download_url':self.manifest_url}]}
        self.requests = []
        self.events = []
        def respond(request):
            url = str(request.url)
            self.requests.append(url)
            if url == LATEST:
                return httpx.Response(200, json=self.release)
            if url == self.manifest_url:
                return httpx.Response(200, json=self.manifest)
            if url == self.setup_url:
                return httpx.Response(200, content=self.payload)
            return httpx.Response(404)
        self.transport = httpx.MockTransport(respond)
        self.updates = Updates(self.base, self.events.append, client_factory=lambda: httpx.Client(transport=self.transport))

    def wait(self):
        self.updates.worker.join(5)
        self.assertFalse(self.updates.worker.is_alive())

    def check(self):
        self.assertTrue(self.updates.check()['ok'])
        self.wait()

    def test_check_download_and_reverify(self):
        self.check()
        self.assertEqual(self.updates.snapshot()['state'], 'available')
        self.assertTrue(self.updates.download()['ok'])
        self.wait()
        self.assertEqual(self.updates.snapshot()['state'], 'ready')
        installer = self.updates.verified_installer()
        self.assertEqual(installer.read_bytes(), self.payload)
        installer.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.updates.verified_installer()

    def test_automatic_daily_manual_unlimited(self):
        self.check()
        self.assertTrue(self.updates.check(True)['skipped'])
        count = len(self.requests)
        self.check()
        self.assertGreater(len(self.requests), count)

    def test_draft_and_prerelease_are_ignored(self):
        for field in ('draft','prerelease'):
            self.release[field] = True
            self.check()
            self.assertEqual(self.updates.snapshot()['state'], 'current')
            self.release[field] = False

    def test_invalid_asset_and_manifest_rejected(self):
        for field, value in [('version','9.0.0'), ('size',-1), ('sha256','bad'), ('asset','anything.exe')]:
            original = self.manifest[field]
            self.manifest[field] = value
            self.check()
            self.assertEqual(self.updates.snapshot()['state'], 'error')
            self.manifest[field] = original
        self.release['assets'][0]['browser_download_url'] = 'https://example.com/setup.exe'
        self.check()
        self.assertEqual(self.updates.snapshot()['state'], 'error')

    def test_corrupt_download_not_marked_ready(self):
        self.manifest['sha256'] = '0' * 64
        self.check()
        self.updates.download()
        self.wait()
        self.assertEqual(self.updates.snapshot()['state'], 'error')
        self.assertFalse((self.base / 'updates/1.1.0/verified.json').exists())
        self.assertFalse(list(self.base.rglob('*.part')))

    def test_network_limit_and_external_redirect_fail_closed(self):
        for status in (403,429,500):
            self.updates.client_factory = lambda status=status: httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(status)))
            self.check()
            self.assertEqual(self.updates.snapshot()['state'], 'error')
        self.updates.client_factory = lambda: httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={'location':'http://example.com/setup.exe'})))
        self.check()
        self.assertEqual(self.updates.snapshot()['state'], 'error')

    def test_missing_release_is_normal(self):
        self.updates.client_factory = lambda: httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
        self.check()
        self.assertEqual(self.updates.snapshot()['state'], 'current')

    def test_low_disk_and_overlapping_download(self):
        self.check()
        with patch('system.updates.shutil.disk_usage', return_value=Mock(free=0)):
            self.updates.download()
            self.wait()
        self.assertEqual(self.updates.snapshot()['state'], 'error')
        self.updates.worker = Mock(is_alive=lambda: True)
        self.assertFalse(self.updates.download()['ok'])

    def test_strict_stable_version_order(self):
        self.assertGreater(version_tuple('1.10.0'), version_tuple('1.9.9'))
        for version in ('v1.0.0','1.0.0-beta','01.0.0','1.0',None):
            with self.assertRaises(ValueError):
                version_tuple(version)
        for url in ('http://github.com/x','https://evil.example/x','https://user:secret@github.com/x'):
            with self.assertRaises(ValueError):
                safe_download_url(url)

    def test_helper_passes_only_fixed_installer_arguments_and_restarts(self):
        self.check()
        self.updates.download()
        self.wait()
        installer = self.updates.verified_installer()
        executable = self.base / 'program/WebScraper.exe'
        executable.parent.mkdir()
        executable.write_bytes(b'fake-test-exe')
        request = installer.parent / 'request.json'
        request.write_text(json.dumps({'version':'1.1.0','token':'test-only','executable':str(executable),'parent_pid':123,'parent_created':1}))
        run, launch = Mock(return_value=Mock(returncode=0)), Mock()
        install_request(request, root=self.base, runner=run, launcher=launch, waiter=Mock())
        self.assertEqual(run.call_args.args[0][0], str(installer))
        self.assertIn('/NORESTART', run.call_args.args[0])
        launch.assert_called_once_with([str(executable)], cwd=str(executable.parent))
        self.assertTrue(json.loads((installer.parent / 'result.json').read_text())['ok'])

    def test_helper_failure_never_restarts(self):
        self.check()
        self.updates.download()
        self.wait()
        installer = self.updates.verified_installer()
        executable = self.base / 'WebScraper.exe'
        executable.write_bytes(b'test')
        request = installer.parent / 'request.json'
        request.write_text(json.dumps({'version':'1.1.0','token':'test-only','executable':str(executable),'parent_pid':123,'parent_created':1}))
        launch = Mock()
        with self.assertRaises(RuntimeError):
            install_request(request, root=self.base, runner=Mock(return_value=Mock(returncode=1)), launcher=launch, waiter=Mock())
        launch.assert_not_called()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'old'
        self.target = Path(self.temporary.name) / 'new'
        for name in ('system','ui','config','vysledky/run/prohlizec_chromium'):
            (self.source / name).mkdir(parents=True, exist_ok=True)
        (self.source / 'config/categories.local.json').write_text('["Tiefbau"]')
        (self.source / 'vysledky/run/stav.sqlite3').write_bytes(b'test-state')
        (self.source / 'vysledky/run/prohlizec_chromium/test').write_bytes(b'test-profile')
        self.closed = patch('system.legacy_import.ensure_closed')
        self.closed.start()
        self.addCleanup(self.closed.stop)

    def test_copy_keeps_source_byte_for_byte(self):
        preview = inspect_import(self.source, self.target)
        execute_import(self.source, self.target, preview['fingerprint'])
        for relative in ('config/categories.local.json','vysledky/run/stav.sqlite3','vysledky/run/prohlizec_chromium/test'):
            self.assertEqual((self.source / relative).read_bytes(), (self.target / relative).read_bytes())
        self.assertEqual(json.loads((self.target/'logs/import.json').read_text())['state'], 'complete')

    def test_conflict_prevents_all_copying(self):
        destination = self.target / 'config/categories.local.json'
        destination.parent.mkdir(parents=True)
        destination.write_text('["Existing"]')
        preview = inspect_import(self.source,self.target)
        self.assertEqual(preview['conflicts'], ['config/categories.local.json'])
        with self.assertRaises(ValueError):
            execute_import(self.source,self.target,preview['fingerprint'])
        self.assertEqual(destination.read_text(),'["Existing"]')
        self.assertFalse((self.target/'vysledky').exists())

    def test_source_change_and_running_profile_are_rejected(self):
        preview = inspect_import(self.source,self.target)
        (self.source/'vysledky/run/stav.sqlite3').write_bytes(b'changed-state')
        with self.assertRaises(ValueError):
            execute_import(self.source,self.target,preview['fingerprint'])
        with patch('system.legacy_import.ensure_closed', side_effect=ValueError('running')):
            with self.assertRaises(ValueError):
                inspect_import(self.source,self.target)

    def test_no_nested_import_and_no_unknown_folder(self):
        with self.assertRaises(ValueError):
            inspect_import(self.source,self.source/'new')
        with self.assertRaises(ValueError):
            inspect_import(self.target,self.source)

    def test_failed_copy_never_reports_completion(self):
        preview = inspect_import(self.source,self.target)
        with patch('system.legacy_import.shutil.copy2', side_effect=OSError('locked')):
            with self.assertRaises(OSError):
                execute_import(self.source,self.target,preview['fingerprint'])
        self.assertFalse((self.target/'vysledky/run').exists())
        self.assertTrue((self.source/'vysledky/run/stav.sqlite3').exists())

    def test_duplicate_config_rejected(self):
        (self.source/'categories.local.json').write_text('["Other"]')
        with self.assertRaises(ValueError):
            inspect_import(self.source,self.target)


if __name__ == '__main__':
    unittest.main()
