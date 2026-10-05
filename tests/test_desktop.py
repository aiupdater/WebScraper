"""Bridge regression tests; no live MySQL, browser or credential use."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock
from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings


class DesktopTests(unittest.TestCase):
    def test_selected_portal_is_validated_and_passed_to_pipeline(self):
        self.assertFalse(self.api.start_run({**self.payload, 'portal': 'unknown'})['ok'])
        self.assertTrue(self.api.start_run({**self.payload, 'portal': '11880'})['ok'])
        self.finish()
        self.assertEqual(self.captured[0][0].portal, '11880')

    def test_saved_folder_reports_its_portal(self):
        folder = self.base / 'saved'
        folder.mkdir()
        (folder / 'stav.sqlite3').touch()
        (folder / 'souhrn.json').write_text(json.dumps({'status': 'STOPPED', 'portal': '11880'}))
        result = self.api.folder_info(str(folder))
        self.assertTrue(result['resume'])
        self.assertEqual(result['portal'], '11880')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.settings = MySQLSettings(password='unit-test-password')
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.captured = []
        parent = self
        class Pipeline:
            def __init__(self, config, folder, callback, stop, **kwargs):
                self.callback, self.stop = callback, stop
                parent.captured.append((config,folder,kwargs))
            def run(self):
                self.callback({'type':'stage','stage':1,'done':0,'total':1,'status':'Běží'})
                parent.release.wait(2)
        self.api = DesktopAPI(self.base, settings=self.settings, pipeline_factory=Pipeline)
        self.payload = {'query':'Tiefbau','max_pages':'20','start_page':'1','workers':'6','delay':'2,0',
                        'output_mode':'files','skip_existing':False,'group_id':'',
                        'wlw_mode':'browser','browser_channel':'msedge','folder':str(self.base/'run')}

    def finish(self):
        self.release.set()
        if self.api._worker:
            self.api._worker.join(3)

    def test_bootstrap_never_exposes_password(self):
        data = self.api.bootstrap()
        self.assertTrue(data['settings']['has_password'])
        self.assertNotIn(self.settings.password,json.dumps(data))
        self.assertNotIn('password',data['settings'])

    def test_categories_persist_including_empty_list(self):
        self.assertEqual(self.api.bootstrap()['categories'], ['Tiefbau'])
        self.assertEqual(json.loads((self.base/'config'/'categories.local.json').read_text()), ['Tiefbau'])
        self.assertTrue(self.api.save_categories(['Tiefbau', ' Vlastní kategorie '])['ok'])
        reopened = DesktopAPI(self.base, settings=self.settings)
        self.assertEqual(reopened.bootstrap()['categories'], ['Tiefbau', 'Vlastní kategorie'])
        self.assertFalse(self.api.save_categories(['Tiefbau', 'tiefbau'])['ok'])
        self.assertFalse(self.api.save_categories([' '])['ok'])
        self.assertTrue(self.api.save_categories([])['ok'])
        self.assertEqual(DesktopAPI(self.base, settings=self.settings).bootstrap()['categories'], [])
        self.assertFalse(self.api.start_run({**self.payload, 'categories': []})['ok'])
        self.assertFalse(self.api.start_run(self.payload)['ok'])

    def test_multiple_categories_passed_to_pipeline(self):
        self.api.save_categories(['Tiefbau', 'Abbruch'])
        payload = {**self.payload, 'categories': ['Tiefbau', 'Abbruch']}
        self.assertTrue(self.api.start_run(payload)['ok'])
        self.assertFalse(self.api.save_categories([])['ok'])
        self.finish()
        self.assertEqual(self.captured[0][0].categories, ('Tiefbau', 'Abbruch'))
        for values in ([], ['unknown'], ['Tiefbau', 'Tiefbau'], 'Tiefbau', [None]):
            self.assertFalse(self.api.start_run({**payload, 'categories': values})['ok'])

    def test_selected_portal_is_validated_and_passed_to_pipeline(self):
        self.assertFalse(self.api.start_run({**self.payload, 'portal': 'unknown'})['ok'])
        self.assertTrue(self.api.start_run({**self.payload, 'portal': '11880'})['ok'])
        self.finish()
        self.assertEqual(self.captured[0][0].portal, '11880')

    def test_saved_folder_reports_its_portal(self):
        folder = self.base / 'saved'
        folder.mkdir()
        (folder / 'stav.sqlite3').touch()
        (folder / 'souhrn.json').write_text(json.dumps({'status': 'STOPPED', 'portal': '11880'}))
        result = self.api.folder_info(str(folder))
        self.assertTrue(result['resume'])
        self.assertEqual(result['portal'], '11880')

    def test_corrupt_categories_are_not_overwritten(self):
        path = self.base/'config'/'categories.local.json'
        path.write_text('broken', encoding='utf-8')
        reopened = DesktopAPI(self.base, settings=self.settings)
        self.assertTrue(reopened.bootstrap()['categories_error'])
        self.assertEqual(path.read_text(), 'broken')

    def test_failed_save_preserves_categories(self):
        self.api._write_categories = MagicMock(side_effect=OSError('read only'))
        self.assertFalse(self.api.save_categories(['Abbruch'])['ok'])
        self.assertEqual(self.api.bootstrap()['categories'], ['Tiefbau'])

    def test_file_run_preserves_config_and_delivery_arguments(self):
        self.assertTrue(self.api.start_run(self.payload)['ok'])
        self.finish()
        cfg,folder,kwargs = self.captured[0]
        self.assertEqual(cfg.wlw_mode,'browser')
        self.assertEqual(cfg.browser_channel,'msedge')
        self.assertEqual(cfg.delay,2.0)
        self.assertEqual(cfg.output_mode,'files')
        self.assertIsNone(cfg.group_id)
        self.assertIs(kwargs['mysql_settings'],self.settings)
        self.assertEqual(self.api.poll_events()[-1]['type'],'idle')

    def test_run_guard_rejects_double_start_and_settings_changes(self):
        self.assertTrue(self.api.start_run(self.payload)['ok'])
        self.assertFalse(self.api.start_run(self.payload)['ok'])
        self.assertFalse(self.api.save_settings({})['ok'])
        self.assertFalse(self.api.connect_database()['ok'])
        self.assertFalse(self.api.new_folder()['ok'])
        self.finish()

    def test_mysql_requires_groups_and_valid_selection(self):
        self.payload.update(output_mode='mysql',group_id='4')
        self.assertFalse(self.api.start_run(self.payload)['ok'])
        self.api._groups = [(4,'Tiefbau')]
        self.assertTrue(self.api.start_run(self.payload)['ok'])
        self.finish()
        self.assertEqual(self.captured[0][0].group_id,4)
        self.payload['group_id']='5'
        self.assertFalse(self.api.start_run(self.payload)['ok'])

    def test_mysql_default_group_is_none(self):
        self.payload['output_mode']='mysql'
        self.api._groups=[]
        self.assertTrue(self.api.start_run(self.payload)['ok'])
        self.finish()
        self.assertIsNone(self.captured[0][0].group_id)

    def test_captcha_requires_active_run_and_respects_stop(self):
        self.assertFalse(self.api.confirm_verification()['ok'])
        self.api.start_run(self.payload)
        self.assertFalse(self.api.confirm_verification()['ok'])
        self.api._emit({'type':'manual','active':True})
        self.assertTrue(self.api.confirm_verification()['ok'])
        self.assertTrue(self.api._continue.is_set())
        self.api.stop_run()
        self.assertTrue(self.api._stop.is_set())
        self.assertFalse(self.api.confirm_verification()['ok'])
        self.finish()

    def test_password_blank_preserves_existing_and_local_settings_saved(self):
        settings = self.api.bootstrap()['settings']
        settings['password']=''
        result=self.api.save_settings(settings)
        self.assertTrue(result['ok'])
        self.assertEqual(self.api._settings.password,self.settings.password)
        self.assertEqual(MySQLSettings.load(self.base/'config'/'mysql.local.json').password,self.settings.password)
        self.assertEqual(self.api.settings_password()['password'],self.settings.password)
        self.assertNotIn(self.settings.password,json.dumps(result))

    def test_validation_and_password_error_redaction(self):
        for key,value in [('query','other'),('max_pages','1.5'),('workers','0'),('wlw_mode','other'),
                          ('browser_channel','other'),('output_mode','other'),('skip_existing','false'),('folder','')]:
            with self.subTest(key=key):
                payload={**self.payload,key:value}
                self.assertFalse(self.api.start_run(payload)['ok'])
        self.assertNotIn(self.settings.password,self.api._error(Exception(self.settings.password))['message'])

    def test_connect_loads_real_group_ids_async(self):
        class Contacts:
            def __init__(self,settings): pass
            def groups(self): return [(4,'Tiefbau'),(9,'Abbruch')]
            def close(self): pass
        self.api._contacts_factory=Contacts
        self.assertTrue(self.api.connect_database()['ok'])
        self.api._worker.join(2)
        self.assertEqual(self.api.poll_events(),[{'type':'groups','groups':[(4,'Tiefbau'),(9,'Abbruch')]}])
        self.assertFalse(self.api._db_busy)

    def test_connect_failure_restores_controls_and_invalidates_groups(self):
        def fail(_): raise RuntimeError('connection failed')
        self.api._contacts_factory=fail
        self.api._groups=[(4,'old')]
        self.api.connect_database(); self.api._worker.join(2)
        self.assertFalse(self.api._db_busy)
        self.assertIsNone(self.api._groups)
        self.assertEqual(self.api.poll_events()[0]['type'],'groups_error')

    def test_worker_failure_emits_fatal_and_idle(self):
        class Failed:
            def __init__(self,*a,**kw): pass
            def run(self): raise ValueError('cannot resume')
        self.api._pipeline_factory=Failed
        self.api.start_run(self.payload); self.api._worker.join(2)
        self.assertEqual([e['type'] for e in self.api.poll_events()],['fatal','browser','idle'])
        self.assertFalse(self.api._running)

    def test_close_waits_for_saved_work(self):
        self.api._window=MagicMock()
        self.api.start_run(self.payload)
        self.assertFalse(self.api._on_closing())
        self.assertTrue(self.api._stop.is_set())
        self.assertFalse(self.api._on_closing())
        self.finish()

    def test_event_batches_and_resume_detection(self):
        for i in range(151): self.api._emit({'type':'log','message':str(i)})
        self.assertEqual(len(self.api.poll_events()),150)
        self.assertEqual(len(self.api.poll_events()),1)
        self.assertFalse(self.api.folder_info(str(self.base))['resume'])
        (self.base/'stav.sqlite3').touch()
        self.assertTrue(self.api.folder_info(str(self.base))['resume'])

    def test_folder_info_distinguishes_stopped_failed_and_completed_runs(self):
        (self.base/'stav.sqlite3').touch()
        summary = self.base/'souhrn.json'
        for status in ('STOPPED', 'FAILED', 'BLOCKED'):
            summary.write_text(json.dumps({'status': status}), encoding='utf-8')
            info = self.api.folder_info(str(self.base))
            self.assertTrue(info['resume'])
            self.assertFalse(info['completed'])
            self.assertEqual(info['status'], status)
        for status in ('DONE', 'PARTIAL'):
            summary.write_text(json.dumps({'status': status}), encoding='utf-8')
            info = self.api.folder_info(str(self.base))
            self.assertFalse(info['resume'])
            self.assertTrue(info['completed'])

    def test_finish_saved_run_starts_pipeline_with_finish_event_set(self):
        result = self.api.finish_run(self.payload)
        self.assertTrue(result['ok'])
        self.assertTrue(self.captured[0][2]['finish_event'].is_set())
        self.assertTrue(self.api._running)
        self.finish()


if __name__ == '__main__':
    unittest.main()
