import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path

import httpx
from system.core import (Config, Pipeline, Fetcher, FetchError, Store, best_email, clean_url,
                  extract_emails, profile_url, root_url, search_profiles, website_from_profile)


class ParserTests(unittest.TestCase):
    def test_profiles_are_canonical_and_not_foreign(self):
        self.assertEqual(profile_url('/de/firma/acme-123/produkte/a?x=1'), 'https://www.wlw.de/de/firma/acme-123')
        self.assertIsNone(profile_url('https://evil.example/de/firma/acme-123'))
        self.assertEqual(len(search_profiles('<a href="/de/firma/acme-1">A</a><a href="/de/firma/acme-1/produkte">B</a>', 'https://www.wlw.de')), 1)

    def test_preserves_www_and_filters_subdomains(self):
        self.assertEqual(root_url('https://www.acme.de/kontakt?a=1'), 'https://www.acme.de/')
        self.assertIsNone(root_url('https://hilfe.wlw.de/path'))
        self.assertIsNone(clean_url('http://127.0.0.1/'))
        self.assertIsNone(clean_url('https://user:pass@acme.de/'))
        self.assertIsNone(clean_url('https://acme.de:bad/'))

    def test_no_guess_from_technical_urls(self):
        html = '<script src="https://cdn.example.com/app.js"></script><a href="https://schema.org">Schema</a>'
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/acme-1')['status'], 'NO_WEBSITE')

    def test_explicit_redirect(self):
        html = '<a href="/out?url=https%3A%2F%2Fwww.acme.de%2Fde">Zur Website</a>'
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/acme-1')['website'], 'https://www.acme.de/de')

    def test_ambiguous_requires_review(self):
        html = '<a href="https://a.de">Website</a><a href="https://b.de">Website</a>'
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/acme-1')['status'], 'REVIEW')

    def test_jsonld_organization(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":"Organization","url":"https://acme.de"}]}</script>'
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/acme-1')['website'], 'https://acme.de/')

    def test_nuxt_homepage_matches_exact_profile(self):
        html = '<script id="__NUXT_DATA__" type="application/json">[{"slug":1,"homepage":2},"acme-1","https://www.acme.de",{"slug":4,"homepage":5},"other-2","https://other.de"]</script>'
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/acme-1')['website'], 'https://www.acme.de/')
        self.assertEqual(website_from_profile(html, 'https://www.wlw.de/de/firma/missing-3')['status'], 'NO_WEBSITE')

    def test_email_extraction(self):
        html = '<script>tracker@foreign.de</script><p>info [at] acme [dot] de</p><a href="mailto:sales%2Bde@acme.de?subject=X">Mail</a>'
        self.assertEqual(extract_emails(html), {'info@acme.de', 'sales+de@acme.de'})

    def test_exact_registrable_domain(self):
        emails = {'info@evil-acme.co.uk', 'office@acme.co.uk', 'info@other.co.uk'}
        self.assertEqual(best_email(emails, 'https://www.acme.co.uk'), 'office@acme.co.uk')
        self.assertEqual(best_email({'info@different.github.io'}, 'https://acme.github.io'), '')


class FetchTests(unittest.TestCase):
    def fetcher(self, handler):
        fetch = Fetcher(Config(query='x', delay=.2), threading.Event(), lambda *a, **k: None,
                        httpx.MockTransport(handler), check_dns=False)
        fetch.pause = lambda seconds: None
        self.addCleanup(fetch.close)
        return fetch

    def test_retry_429_without_robots(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path == '/robots.txt':
                return httpx.Response(200, text='User-agent: *\nAllow: /')
            if calls.count('/') == 1:
                return httpx.Response(429, headers={'Retry-After': '2'})
            return httpx.Response(200, text='<p>OK</p>', headers={'Content-Type': 'text/html'})
        fetch = self.fetcher(handler)
        self.assertIn('OK', fetch.get('https://acme.de/')[0])
        self.assertEqual(calls, ['/', '/'])

    def test_robots_never_requested_even_with_legacy_setting(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path == '/robots.txt':
                return httpx.Response(200, text='User-agent: *\nDisallow: /')
            return httpx.Response(200, text='<p>OK</p>', headers={'Content-Type': 'text/html'})
        fetch = self.fetcher(handler)
        fetch.config.respect_robots = True
        self.assertIn('OK', fetch.get('https://acme.de/')[0])
        self.assertEqual(calls, ['/'])

    def test_404_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(404)
        with self.assertRaisesRegex(FetchError, 'HTTP 404'):
            self.fetcher(handler).get('https://acme.de/')
        self.assertEqual(calls, ['/'])

    def test_redirect_to_private_address_rejected(self):
        def handler(request):
            if request.url.path == '/robots.txt':
                return httpx.Response(404)
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/admin'})
        with self.assertRaises(FetchError):
            self.fetcher(handler).get('https://acme.de/')

    def test_long_retry_after_not_shortened(self):
        def handler(request):
            if request.url.path == '/robots.txt':
                return httpx.Response(404)
            return httpx.Response(429, headers={'Retry-After': '3600'})
        with self.assertRaisesRegex(FetchError, '3600'):
            self.fetcher(handler).get('https://acme.de/')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base / 'input.txt'
        self.source.write_text('https://www.wlw.de/de/firma/acme-1\n')
        self.config = Config(input_file=str(self.source))
        self.calls = []
        parent = self
        class Fake:
            def __init__(self, *args):
                pass
            def get(self, url):
                parent.calls.append(url)
                if '/de/firma/' in url:
                    return '<a href="https://www.acme.de">Website</a>', url
                if url.endswith('/kontakt'):
                    return '<a href="mailto:info@acme.de">Mail</a>', url
                return '<a href="/kontakt">Kontakt</a>', url
            def close(self):
                pass
        self.factory = Fake

    def test_end_to_end_resume_and_provenance(self):
        output = self.base / 'run'
        events = []
        self.assertEqual(Pipeline(self.config, output, events.append, fetch_factory=self.factory).run(), 'DONE')
        self.assertEqual((output / 'emaily.txt').read_text(), 'info@acme.de\n')
        with (output / 'kontakty.csv').open(encoding='utf-8-sig') as f:
            row = list(csv.DictReader(f, delimiter=';'))[0]
        self.assertEqual(row['zdroj'], 'https://www.acme.de/kontakt')
        self.calls.clear()
        self.assertEqual(Pipeline(self.config, output, fetch_factory=self.factory).run(), 'DONE')
        self.assertEqual(self.calls, [])

    def test_exclusive_output_folder(self):
        store = Store(self.base / 'run', self.config)
        try:
            with self.assertRaisesRegex(ValueError, 'jiná instance'):
                Store(self.base / 'run', self.config)
        finally:
            store.close()

    def test_reject_changed_input(self):
        store = Store(self.base / 'run', self.config)
        store.close()
        self.source.write_text('https://www.wlw.de/de/firma/other-2\n')
        with self.assertRaises(ValueError):
            Store(self.base / 'run', self.config)

    def test_partial_then_retry(self):
        parent = self
        class Fail(self.factory):
            def get(self, url):
                if '/de/firma/' in url:
                    raise FetchError('HTTP 503')
                return super().get(url)
        output = self.base / 'run'
        self.assertEqual(Pipeline(self.config, output, fetch_factory=Fail).run(), 'PARTIAL')
        self.assertEqual(Pipeline(self.config, output, fetch_factory=self.factory).run(), 'DONE')
        self.assertEqual((output / 'emaily.txt').read_text(), 'info@acme.de\n')

    def test_cancel_then_resume(self):
        stop = threading.Event()
        def callback(event):
            if event['type'] == 'result' and event['stage'] == 2:
                stop.set()
        output = self.base / 'run'
        self.assertEqual(Pipeline(self.config, output, callback, stop, self.factory).run(), 'STOPPED')
        self.calls.clear()
        self.assertEqual(Pipeline(self.config, output, fetch_factory=self.factory).run(), 'DONE')
        self.assertFalse(any('/de/firma/' in u for u in self.calls))

    def test_search_repeated_pages_and_encoded_query(self):
        parent = self
        class Search(self.factory):
            def get(self, url):
                if '/de/suche' in url:
                    parent.calls.append(url)
                    return '<a href="/de/firma/acme-1">Firma</a>', url
                return super().get(url)
        config = Config(query='Hoch & Tiefbau', max_pages=5)
        self.assertEqual(Pipeline(config, self.base / 'run', fetch_factory=Search).run(), 'PARTIAL')
        searches = [u for u in self.calls if '/de/suche' in u]
        self.assertEqual(len(searches), 2)
        self.assertIn('/de/suche/hoch-%26-tiefbau', searches[0])

    def test_empty_search_is_not_false_success(self):
        class Empty(self.factory):
            def get(self, url):
                return '<p>Nothing</p>', url
        self.assertEqual(Pipeline(Config(query='x'), self.base / 'run', fetch_factory=Empty).run(), 'PARTIAL')

    def test_multiple_categories_overlap_and_resume(self):
        parent = self
        class Search(self.factory):
            def get(self, url):
                if '/de/suche/' in url:
                    parent.calls.append(url)
                    profile = 'other-2' if url.endswith('/abbruch/page/2') else 'acme-1'
                    return f'<a href="/de/firma/{profile}">Firma</a>', url
                return super().get(url)
        config = Config(query='Tiefbau', categories=('Tiefbau', 'Abbruch'), max_pages=2)
        output = self.base/'multi'
        events = []
        self.assertEqual(Pipeline(config, output, events.append, fetch_factory=Search).run(), 'PARTIAL')
        expected = {('Tiefbau', 1), ('Tiefbau', 2), ('Abbruch', 1), ('Abbruch', 2)}
        contact = next(e['data'] for e in events if e['type'] == 'result' and e['stage'] == 4)
        self.assertEqual({(o['category'], o['page']) for o in contact['origins']}, expected)
        result_logs = [e['message'] for e in events if e['type'] == 'log' and e['message'].startswith('https://') and ' → ' in e['message']]
        self.assertEqual(len(result_logs), 3)  # Two profiles and one shared website.
        self.assertTrue(all('Kategorie:' in message for message in result_logs))
        for category, page in expected:
            self.assertIn(f'{category} · stránka {page}', result_logs[-1])
        self.assertIn(result_logs[-1], (output/'prubeh.log').read_text(encoding='utf-8'))
        store = Store(output, config)
        self.assertEqual(store.rows(4)[0][1]['origins'], contact['origins'])
        # Simulate a run saved before explicit provenance was introduced.
        for stage in (1, 2, 4):
            for url, data in store.rows(stage):
                for key in ('origins', 'category', 'page'):
                    data.pop(key, None)
                store.put(stage, url, data)
        store.close()
        searches = [u for u in self.calls if '/de/suche/' in u]
        self.assertEqual(searches, ['https://www.wlw.de/de/suche/tiefbau',
            'https://www.wlw.de/de/suche/tiefbau/page/2',
            'https://www.wlw.de/de/suche/abbruch', 'https://www.wlw.de/de/suche/abbruch/page/2'])
        self.assertEqual(self.calls.count('https://www.wlw.de/de/firma/acme-1'), 1)
        self.assertIn('https://www.wlw.de/de/firma/other-2', self.calls)
        self.calls.clear()
        events.clear()
        self.assertEqual(Pipeline(config, output, events.append, fetch_factory=Search).run(), 'PARTIAL')
        contact = next(e['data'] for e in events if e['type'] == 'result' and e['stage'] == 4)
        self.assertEqual({(o['category'], o['page']) for o in contact['origins']}, expected)
        self.assertFalse(any('/de/firma/' in u for u in self.calls))
        restored_logs = [e['message'] for e in events if e['type'] == 'log' and e['message'].startswith('https://') and ' → ' in e['message']]
        self.assertEqual(len(restored_logs), 3)
        self.assertTrue(all('Kategorie:' in message and 'z uložených dat' in message for message in restored_logs))
        with self.assertRaises(ValueError):
            Store(output, Config(query='Tiefbau', categories=('Tiefbau', 'Stahlbau'), max_pages=2))

    def test_stop_prevents_next_category(self):
        stop = threading.Event()
        calls = []
        class Search(self.factory):
            def get(self, url):
                calls.append(url)
                stop.set()
                return '<a href="/de/firma/acme-1">Firma</a>', url
        config = Config(categories=('Tiefbau', 'Abbruch'), max_pages=1)
        self.assertEqual(Pipeline(config, self.base/'multi', stop=stop, fetch_factory=Search).run(), 'STOPPED')
        self.assertEqual(calls, ['https://www.wlw.de/de/suche/tiefbau'])

    def test_import_sites_deduplicates_www_without_changing_url(self):
        self.source.write_text('https://www.acme.de/contact\nhttp://acme.de/\n')
        config = Config(input_file=str(self.source), input_kind='websites')
        self.assertEqual(Pipeline(config, self.base / 'run', fetch_factory=self.factory).run(), 'DONE')
        self.assertEqual((self.base / 'run' / 'websites_clean.txt').read_text(), 'https://www.acme.de/\n')


if __name__ == '__main__':
    unittest.main()
