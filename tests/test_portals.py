import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from system.browser_fetcher import BrowserFetcher, content_ready, is_portal, same_page
from system.core import Config, Pipeline, Store, directory_contact, directory_has_next, profile_url, search_profiles, search_url

PROFILE = 'https://www.11880.com/branchenbuch/dortmund/123B456/acme.html'
OTHER = 'https://www.11880.com/branchenbuch/berlin/789B123/other.html'


def card(email, website=''):
    return '<h1>Firma</h1><meta itemprop="email" content="' + email + '">' + (
        f'<a href="{website}">Website</a>' if website else '')


class PortalParsers(unittest.TestCase):
    def test_search_urls_and_encoding(self):
        self.assertEqual(search_url('Tiefbau', 1, '11880'), 'https://www.11880.com/suche/Tiefbau/deutschland')
        self.assertEqual(search_url('Hoch & Tiefbau', 2, '11880'), 'https://www.11880.com/suche/Hoch%20%26%20Tiefbau/deutschland?page=2')
        self.assertEqual(search_url('https://www.11880.com/suche/Tiefbau/deutschland?page=8', 3, '11880'), 'https://www.11880.com/suche/Tiefbau/deutschland?page=3')
        with self.assertRaises(ValueError):
            search_url('https://www.wlw.de/de/suche/tiefbau', 1, '11880')

    def test_profile_canonicalization_and_portal_isolation(self):
        html = f'<a href="{PROFILE}?x=1">Mehr Details</a><a href="{PROFILE}#x">Firma</a><a href="https://evil.de/branchenbuch/a/b/c.html">X</a>'
        self.assertEqual(search_profiles(html, PROFILE, '11880'), [PROFILE])
        self.assertEqual(search_profiles(html, PROFILE), [])
        self.assertIsNone(profile_url('https://www.11880.com/branchenbuch/dortmund', portal='11880'))

    def test_metadata_and_matching_jsonld_only(self):
        html = card('info@acme.de') + '<script type="application/ld+json">' + json.dumps([
            {'url': PROFILE, 'email': 'office@acme.de'},
            {'url': OTHER, 'email': 'other@other.de'}]) + '</script><footer>support@11880.com</footer><p>review@example.de</p>'
        self.assertEqual(directory_contact(html, PROFILE)['profile_emails'], ['info@acme.de', 'office@acme.de'])

    def test_obfuscated_email_and_mailto_in_contact_card(self):
        encoded = bytes([42] + [ord(c) ^ 42 for c in 'info@acme.de']).hex()
        html = f'<div class="entry-detail-list"><span data-cfemail="{encoded}"></span><a href="mailto:office@acme.de?subject=x">Email</a></div>'
        self.assertEqual(directory_contact(html, PROFILE)['profile_emails'], ['info@acme.de', 'office@acme.de'])

    def test_missing_email_and_website(self):
        result = directory_contact('<h1>Firma</h1><p>Žádný kontakt</p>', PROFILE)
        self.assertEqual(result['profile_emails'], [])
        self.assertEqual(result['website'], '')

    def test_browser_readiness_and_navigation(self):
        listing = search_url('Tiefbau', 1, '11880')
        self.assertTrue(content_ready(f'<a href="{PROFILE}">Mehr Details</a>', listing))
        self.assertTrue(content_ready('<h1>Firma</h1>', PROFILE))
        self.assertFalse(content_ready('<h1>Access denied</h1>', listing))
        self.assertFalse(same_page(listing, listing.replace('11880.com', 'wlw.de')))
        self.assertFalse(is_portal(PROFILE, 'wlw'))
        self.assertTrue(is_portal(PROFILE, '11880'))

    def test_browser_uses_next_buttons_including_nonfirst_start(self):
        fetch = object.__new__(BrowserFetcher)
        fetch.config = Config(portal='11880')
        fetch.page = None
        fetch.check = lambda: None
        calls = []
        def navigate(url, use_next=False):
            calls.append((url, use_next))
            fetch.page = SimpleNamespace(url=url)
            return '<h1>Results</h1>', url
        fetch._get = navigate
        fetch.get(search_url('Tiefbau', 3, '11880'))
        self.assertEqual(calls, [(search_url('Tiefbau', n, '11880'), n > 1) for n in range(1, 4)])
        calls.clear()
        fetch.get(search_url('Tiefbau', 4, '11880'))
        self.assertEqual(calls, [(search_url('Tiefbau', 4, '11880'), True)])

    def test_last_page_is_recognized_only_with_known_markup(self):
        self.assertIsNone(directory_has_next('<h1>Unexpected page</h1>'))
        card_html = f'<a class="entry-detail-link" href="{PROFILE}">Firma</a>'
        self.assertFalse(directory_has_next(card_html))
        self.assertTrue(directory_has_next(card_html + '<button aria-label="Zur nächsten Seite"></button>'))


class PortalPipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.config = Config(query='Tiefbau', portal='11880', max_pages=2)
        self.calls = []
        self.pages = {
            search_url('Tiefbau', 1, '11880'): f'<a href="{PROFILE}">Mehr Details</a>',
            search_url('Tiefbau', 2, '11880'): f'<a href="{PROFILE}">Anzeige</a><a href="{OTHER}">Mehr Details</a>',
            PROFILE: card('info@acme.de', 'https://acme.de/'),
            OTHER: card('office@other.de'),
        }
        parent = self
        class Fetch:
            serial_wlw = True
            def __init__(self, *args): pass
            def get(self, url):
                parent.calls.append(url)
                return parent.pages[url], url
            def close(self): pass
        self.fetch = Fetch

    def run_pipeline(self, **kwargs):
        return Pipeline(self.config, self.folder, fetch_factory=self.fetch, **kwargs).run()

    def test_pages_direct_emails_without_visiting_company_websites_and_resume(self):
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(set(self.calls), set(self.pages))
        self.assertEqual((self.folder / 'emaily.txt').read_text(), 'info@acme.de\noffice@other.de\n')
        with (self.folder / 'firmy.csv').open(encoding='utf-8-sig') as f:
            records = {r['profil']: r for r in csv.DictReader(f, delimiter=';')}
        self.assertEqual(records[OTHER]['email'], 'office@other.de')
        self.assertEqual(records[PROFILE]['zdroj_emailu'], PROFILE)
        self.calls.clear()
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(self.calls, [])

    def test_missing_contact_is_no_email(self):
        self.pages[OTHER] = '<h1>Firma</h1>'
        self.assertEqual(self.run_pipeline(), 'DONE')
        store = Store(self.folder, self.config)
        try:
            self.assertEqual(store.get(4, OTHER)['status'], 'NO_EMAIL')
        finally:
            store.close()

    def test_categories_stay_with_each_profile_in_results_and_log_on_resume(self):
        self.config.categories = ('Tiefbau', 'Abbruch')
        self.pages[search_url('Abbruch', 1, '11880')] = f'<a class="entry-detail-link" href="{OTHER}">Firma</a>'
        events = []
        expected = {
            PROFILE: {('Tiefbau', 1), ('Tiefbau', 2)},
            OTHER: {('Tiefbau', 2), ('Abbruch', 1)},
        }
        for resumed in (False, True):
            events.clear()
            self.calls.clear()
            self.assertEqual(self.run_pipeline(callback=events.append), 'DONE')
            contacts = {e['url']: e['data'] for e in events if e['type'] == 'result' and e['stage'] == 4}
            for profile, origins in expected.items():
                self.assertEqual({(o['category'], o['page']) for o in contacts[profile]['origins']}, origins)
                logs = [e['message'] for e in events if e['type'] == 'log' and e['message'].startswith(profile + ' → ')]
                self.assertEqual(len(logs), 2)
                for category, page in origins:
                    self.assertTrue(all(f'{category} · stránka {page}' in message for message in logs))
            if resumed:
                self.assertFalse(self.calls)
            else:
                store = Store(self.folder, self.config)
                try:
                    for stage in (1, 2, 4):
                        for url, data in store.rows(stage):
                            for key in ('origins', 'category', 'page'):
                                data.pop(key, None)
                            store.put(stage, url, data)
                finally:
                    store.close()

    def test_last_page_stops_cleanly_before_page_limit(self):
        self.pages[search_url('Tiefbau', 2, '11880')] = f'<a class="entry-detail-link" href="{OTHER}">Mehr Details</a>'
        self.config.max_pages = 20
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertEqual(len(self.calls), 4)

    def test_portal_change_cannot_resume_same_folder(self):
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.config.portal = 'wlw'
        with self.assertRaises(ValueError):
            self.run_pipeline()

    def test_cancel_then_resume_profiles(self):
        stop = threading.Event()
        def callback(event):
            if event['type'] == 'result' and event['stage'] == 2:
                stop.set()
        self.assertEqual(self.run_pipeline(stop=stop, callback=callback), 'STOPPED')
        first_profile = self.calls[-1]
        self.calls.clear()
        self.assertEqual(self.run_pipeline(), 'DONE')
        self.assertNotIn(first_profile, self.calls)

    def test_profile_email_filter_and_best_choice(self):
        p = Pipeline(self.config, self.folder)
        p.existing = {'info@acme.de'}
        self.assertEqual(p.select_contact({'info@acme.de': PROFILE, 'office@acme.de': PROFILE}, PROFILE)['email'], 'office@acme.de')
        self.assertEqual(p.select_contact({'info@acme.de': PROFILE}, PROFILE)['status'], 'SKIPPED_EXISTING')
        self.config.save_best_email = False
        self.assertEqual(p.select_contact({'a@acme.de': PROFILE, 'b@acme.de': PROFILE}, PROFILE)['emails'], ['a@acme.de', 'b@acme.de'])
