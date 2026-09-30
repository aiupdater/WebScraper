import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from system.core import Config, Pipeline, Store
from system.mysql_contacts import MySQLContacts, MySQLError, MySQLSettings, friendly_error


class SettingsTests(unittest.TestCase):
    def test_password_never_in_repr_or_saved_settings(self):
        settings = MySQLSettings(password='test-only-secret')
        self.assertNotIn('test-only-secret', repr(settings))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mysql.local.json'
            settings.save_public(path)
            self.assertNotIn('password', path.read_text())
            with patch.dict('os.environ', {'MYSQLPASSWORD': 'from-env', 'MYSQLPORT': '3307'}):
                loaded = MySQLSettings.load(path)
            self.assertEqual(loaded.password, 'from-env')
            self.assertEqual(loaded.port, 3307)

    def test_endpoint_identity_excludes_password_but_includes_destination(self):
        original = MySQLSettings(password='a')
        self.assertEqual(original.identity(), replace(original, password='b').identity())
        self.assertNotEqual(original.identity(), replace(original, database='another').identity())

    def test_driver_error_redacts_raw_message(self):
        self.assertNotIn('secret', friendly_error(Exception(1045, 'password=secret')))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        import pymysql
        self.adapter = MySQLContacts.__new__(MySQLContacts)
        self.adapter.integrity_error = pymysql.err.IntegrityError
        self.connection = MagicMock()
        self.adapter.connection = self.connection
        self.cursor = self.connection.cursor.return_value.__enter__.return_value

    def test_insert_only_contact_fields_parameterized(self):
        self.assertEqual(self.adapter.add(' INFO@Acme.de ', 7), 'INSERTED')
        sql, params = self.cursor.execute.call_args.args
        self.assertEqual(params, ('info@acme.de', 'acme.de', 7))
        self.assertNotIn('info@', sql)
        self.assertNotIn('UPDATE', sql)
        self.assertNotIn('email_queue', sql)
        self.assertNotIn('confirmed_at', sql)

    def test_default_group_is_sql_null(self):
        self.adapter.add('info@acme.de', None)
        self.assertIsNone(self.cursor.execute.call_args.args[1][2])

    def test_duplicate_is_noop_but_other_integrity_errors_fail(self):
        self.cursor.execute.side_effect = self.adapter.integrity_error(1062, 'duplicate')
        self.assertEqual(self.adapter.add('info@acme.de', 7), 'EXISTING')
        self.cursor.execute.side_effect = self.adapter.integrity_error(1452, 'foreign key')
        with self.assertRaises(MySQLError):
            self.adapter.add('info@acme.de', 7)

    def test_existing_addresses_are_global_normalized_and_streamed(self):
        self.cursor.fetchmany.side_effect = [[(' INFO@ACME.DE ',), ('unsubscribed@acme.de',)], []]
        emails = self.adapter.existing_emails()
        self.assertEqual(emails, {'info@acme.de', 'unsubscribed@acme.de'})
        sql = self.cursor.execute.call_args.args[0]
        self.assertNotIn('group_id', sql)
        self.assertNotIn('archived', sql)
        self.assertNotIn('unsubscribed_at', sql)

    def test_groups_keep_real_ids(self):
        self.cursor.fetchall.return_value = [(4, 'Tiefbau'), (9, 'Abbruch')]
        self.assertEqual(self.adapter.groups(), [(4, 'Tiefbau'), (9, 'Abbruch')])


class IntegrationTests(unittest.TestCase):
    def test_11880_profiles_deliver_and_skip_existing_without_company_web(self):
        profile = 'https://www.11880.com/branchenbuch/dortmund/123B456/acme.html'
        self.source.write_text(profile)
        self.config.portal = '11880'
        self.config.input_kind = 'profiles'
        self.existing.add('info@acme.de')
        self.pages = {profile: '<h1>Acme</h1><meta itemprop="email" content="info@acme.de"><meta itemprop="email" content="office@acme.de">'}
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [profile])
        self.assertEqual(self.writes, [('office@acme.de', 7)])
        self.assertEqual(self.summary()['skipped_existing'], 1)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base / 'input.txt'
        self.source.write_text('https://acme.de/\n')
        self.output = self.base / 'run'
        self.settings = MySQLSettings(password='test-only-secret')
        self.config = Config(input_file=str(self.source), input_kind='websites',
                             output_mode='mysql', group_id=7, skip_existing=True)
        self.calls = []
        self.writes = []
        self.existing = set()
        self.fail_write = False
        self.commit_then_fail = False
        self.fail_connect = False
        self.groups = [(7, 'Tiefbau')]
        self.pages = {'https://acme.de/': 'info@acme.de'}
        parent = self
        class Fetch:
            def __init__(self, *args): pass
            def get(self, url):
                parent.calls.append(url)
                return parent.pages.get(url, ''), url
            def close(self): pass
        self.fetch_factory = Fetch
        class Contacts:
            def __init__(self, settings):
                if parent.fail_connect:
                    raise MySQLError('MySQL nedostupné')
                self.owner = threading.get_ident()
            def groups(self): return parent.groups
            def existing_emails(self, check=lambda: None):
                check()
                return frozenset(parent.existing)
            def add(self, email, group_id):
                assert self.owner == threading.get_ident()
                parent.writes.append((email, group_id))
                if parent.fail_write:
                    raise MySQLError('Výpadek')
                if email in parent.existing:
                    return 'EXISTING'
                parent.existing.add(email)
                if parent.commit_then_fail:
                    parent.commit_then_fail = False
                    raise MySQLError('Spojení ztraceno po COMMIT')
                return 'INSERTED'
            def close(self): pass
        self.contacts_factory = Contacts

    def run_pipeline(self, **kwargs):
        return Pipeline(self.config, self.output, fetch_factory=self.fetch_factory,
                        mysql_settings=self.settings, contacts_factory=self.contacts_factory, **kwargs).run()

    def summary(self):
        return json.loads((self.output / 'souhrn.json').read_text())

    def test_save_to_selected_group_without_mail_list_or_credentials(self):
        events = []
        self.assertEqual(self.run_pipeline(callback=events.append), 'DONE')
        self.assertEqual(self.writes, [('info@acme.de', 7)])
        update = [event for event in events if event.get('updated')]
        self.assertEqual(len(update), 1)
        self.assertEqual(update[0]['data']['delivery'], 'INSERTED')
        self.assertFalse((self.output / 'emaily.txt').exists())
        self.assertEqual(self.summary()['mysql'], {'INSERTED': 1})
        for file in self.output.iterdir():
            self.assertNotIn(b'test-only-secret', file.read_bytes())

    def test_restart_does_not_reinsert_or_recrawl_own_contacts(self):
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.calls.clear()
        self.writes.clear()
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.summary()['mysql'], {'INSERTED': 1})

    def test_existing_preferred_contact_falls_back_to_new_contact_page(self):
        self.existing.add('info@acme.de')
        self.pages['https://acme.de/'] = 'info@acme.de <a href="/kontakt">Kontakt</a>'
        self.pages['https://acme.de/kontakt'] = 'office@acme.de'
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.writes, [('office@acme.de', 7)])
        self.assertEqual(self.summary()['skipped_existing'], 1)

    def test_file_mode_filters_without_writes(self):
        self.config.output_mode = 'files'
        self.config.group_id = None
        self.existing.add('info@acme.de')
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual((self.output / 'emaily.txt').read_text(), '')
        self.assertEqual(self.writes, [])
        self.assertEqual(self.summary()['skipped_existing'], 1)

    def test_11880_profiles_deliver_and_skip_existing_without_company_web(self):
        profile = 'https://www.11880.com/branchenbuch/dortmund/123B456/acme.html'
        self.source.write_text(profile)
        self.config.portal = '11880'
        self.config.input_kind = 'profiles'
        self.existing.add('info@acme.de')
        self.pages = {profile: '<h1>Acme</h1><meta itemprop="email" content="info@acme.de"><meta itemprop="email" content="office@acme.de">'}
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [profile])
        self.assertEqual(self.writes, [('office@acme.de', 7)])
        self.assertEqual(self.summary()['skipped_existing'], 1)

    def test_file_mode_off_is_offline_and_keeps_existing(self):
        self.config.output_mode = 'files'
        self.config.group_id = None
        self.config.skip_existing = False
        self.fail_connect = True
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual((self.output / 'emaily.txt').read_text(), 'info@acme.de\n')
        self.assertEqual(self.writes, [])

    def test_mysql_without_filter_still_never_updates_existing(self):
        self.config.skip_existing = False
        self.existing.add('info@acme.de')
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.summary()['mysql'], {'EXISTING': 1})
        self.assertEqual(self.summary()['emails'], 0)

    def test_connection_failure_stops_before_crawl(self):
        self.fail_connect = True
        self.assertEqual(self.run_pipeline(), 'FAILED')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.writes, [])

    def test_deleted_group_stops_before_crawl(self):
        self.groups = []
        self.assertEqual(self.run_pipeline(), 'FAILED')
        self.assertEqual(self.calls, [])

    def test_write_failure_is_pending_then_resumed_without_recrawl(self):
        self.fail_write = True
        self.assertEqual(self.run_pipeline(), 'FAILED')
        self.assertEqual(self.summary()['mysql'], {'PENDING': 1})
        self.calls.clear()
        self.fail_write = False
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.summary()['mysql'], {'INSERTED': 1})

    def test_stop_keeps_mysql_unchanged_until_saved_data_are_used(self):
        stop = threading.Event()
        def callback(event):
            if event['type'] == 'result' and event['stage'] == 4:
                stop.set()
        self.assertEqual(self.run_pipeline(callback=callback, stop=stop), 'STOPPED')
        self.assertEqual(self.writes, [])
        self.assertEqual(self.summary()['mysql'], {})

        self.calls.clear()
        finish = threading.Event()
        finish.set()
        self.assertEqual(self.run_pipeline(finish_event=finish), 'DONE')
        self.assertEqual(self.writes, [('info@acme.de', 7)])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.summary()['mysql'], {'INSERTED': 1})

    def test_lost_commit_acknowledgement_retries_as_duplicate(self):
        self.commit_then_fail = True
        self.assertEqual(self.run_pipeline(), 'FAILED')
        self.calls.clear()
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.existing, {'info@acme.de'})
        self.assertEqual(self.summary()['mysql'], {'EXISTING': 1})

    def test_changed_group_or_destination_requires_new_folder(self):
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.config.group_id = 9
        with self.assertRaises(ValueError):
            self.run_pipeline()
        self.config.group_id = 7
        self.settings = replace(self.settings, database='different')
        with self.assertRaises(ValueError):
            self.run_pipeline()

    def test_legacy_file_run_identity_migrates(self):
        self.config.output_mode = 'files'
        self.config.skip_existing = False
        self.config.group_id = None
        store = Store(self.output, self.config)
        raw = store.db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0]
        identity = json.loads(raw)
        for key in ('output_mode', 'skip_existing', 'group_id', 'mysql_identity'):
            identity.pop(key)
        store.db.execute("UPDATE meta SET value=? WHERE key='config'", (json.dumps(identity),))
        store.db.commit()
        store.close()
        self.assertEqual(self.run_pipeline(), 'DONE')


if __name__ == '__main__':
    unittest.main()
