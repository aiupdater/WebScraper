import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from system.access import detect_access_problem
from system.browser_fetcher import BrowserFetcher, HybridFetcher
from system.core import BlockingAccessError, Cancelled, Config, Fetcher, Pipeline, Store

URL = 'https://www.wlw.de/de/suche/tiefbau'
PROFILE = 'https://www.wlw.de/de/firma/acme-1'
RESULT = '<html><title>Tiefbau</title><a href="/de/firma/acme-1">Acme</a></html>'
CAPTCHA = '''<html><title>Human Verification</title><script src="https://id.captcha.awswaf.com/captcha.js"></script>
<script>CaptchaScript.renderCaptcha(container);</script></html>'''


class AccessTests(unittest.TestCase):
    def test_aws_captcha_405(self):
        p = detect_access_problem(405, {'x-amzn-waf-action': 'captcha'}, CAPTCHA)
        self.assertEqual(p.code, 'CAPTCHA_REQUIRED')
        self.assertTrue(p.manual)

    def test_plain_405_is_not_captcha(self):
        p = detect_access_problem(405, {'Allow': 'POST'}, '<h1>Method not allowed</h1>')
        self.assertEqual(p.code, 'HTTP_ERROR')
        self.assertIn('POST', p.message)

    def test_captcha_in_200_response(self):
        self.assertTrue(detect_access_problem(200, {}, CAPTCHA).manual)

    def test_normal_contact_form_is_not_challenge(self):
        self.assertIsNone(detect_access_problem(200, {}, '<title>Contact</title><script src="recaptcha.js"></script>'))

    def test_aws_challenge_202(self):
        self.assertEqual(detect_access_problem(202, {'x-amzn-waf-action': 'challenge'}, '').code, 'BROWSER_CHALLENGE')

    def test_403_is_not_manual_challenge(self):
        self.assertFalse(detect_access_problem(403, {}, 'Denied').manual)

    def test_httpx_classifies_response_before_discarding_body(self):
        calls = []
        def respond(request):
            calls.append(request.url)
            return httpx.Response(405, text=CAPTCHA, headers={'content-type': 'text/html'})
        fetch = Fetcher(Config(query='x', respect_robots=False), threading.Event(), lambda *a, **k: None,
                        transport=httpx.MockTransport(respond), check_dns=False)
        try:
            with self.assertRaises(BlockingAccessError) as raised:
                fetch.get(URL)
            self.assertEqual(raised.exception.code, 'CAPTCHA_REQUIRED')
            self.assertEqual(len(calls), 1)
        finally:
            fetch.close()


class FakePage:
    def __init__(self, html=CAPTCHA, status=405):
        self.html, self.status, self.url = html, status, URL
        self.headers = {'x-amzn-waf-action': 'captcha'} if status == 405 else {}
        self.main_frame = object()
        self.closed = False
        self.gotos = []
        self.responses = None
        self.on_tick = lambda: None
        self.ticks = 0

    def set_default_timeout(self, n):
        pass

    def on(self, name, callback):
        self.responses = callback

    def navigate_response(self):
        response = SimpleNamespace(status=self.status, headers=self.headers,
                                   request=SimpleNamespace(is_navigation_request=lambda: True, frame=self.main_frame))
        self.responses(response)
        return response

    def goto(self, url, **kwargs):
        self.url = url
        self.gotos.append(url)
        return self.navigate_response()

    def content(self):
        return self.html

    def is_closed(self):
        return self.closed

    def wait_for_timeout(self, n):
        self.ticks += 1
        self.on_tick()

    def bring_to_front(self):
        pass

    def solve(self):
        self.html, self.status, self.headers = RESULT, 200, {}
        self.navigate_response()


class FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self.closed = False

    def route(self, *args):
        pass

    def close(self):
        self.closed = True


class BrowserTests(unittest.TestCase):
    def make(self, page=None, emit=None):
        page = page or FakePage()
        stop, proceed = threading.Event(), threading.Event()
        context = FakeContext(page)
        events = []
        def callback(kind, **data):
            events.append({'type': kind, **data})
            if emit:
                emit(kind, data, page, stop, proceed)
        http = SimpleNamespace(validate_target=lambda u: None, pace=lambda u: None, allowed=lambda u: None)
        fetch = BrowserFetcher(Config(query='x', respect_robots=False, manual_timeout=10), stop, callback,
                               '.', proceed, http, context_factory=lambda: context, clock=lambda: page.ticks * .2)
        self.addCleanup(fetch.close)
        return fetch, page, stop, proceed, events, context

    def test_legacy_robots_setting_does_not_check_rules(self):
        fetch, page, *_ = self.make(page=FakePage(RESULT, 200))
        fetch.config.respect_robots = True
        def unexpected(url):
            self.fail('robots check must not run')
        fetch.http.allowed = unexpected
        self.assertEqual(fetch.get(URL), (RESULT, URL))

    def test_pause_waits_for_explicit_confirmation_and_uses_same_page(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                page.solve()
                proceed.set()
        fetch, page, stop, proceed, events, _ = self.make(emit=callback)
        self.assertEqual(fetch.get(URL), (RESULT, URL))
        self.assertEqual(page.gotos, [URL])
        self.assertEqual([e['active'] for e in events if e['type'] == 'manual'], [True, False])

    def test_stale_confirmation_is_cleared(self):
        fetch, page, _, proceed, _, _ = self.make()
        proceed.set()
        with self.assertRaises(BlockingAccessError) as raised:
            fetch.get(URL)
        self.assertEqual(raised.exception.code, 'MANUAL_TIMEOUT')
        self.assertFalse(proceed.is_set())
        self.assertEqual(len(page.gotos), 1)

    def test_unsolved_confirmation_does_not_proceed(self):
        prompts = []
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                prompts.append(data)
                if len(prompts) == 2:
                    page.solve()
                proceed.set()
        fetch, page, *_ = self.make(emit=callback)
        self.assertEqual(fetch.get(URL)[0], RESULT)
        self.assertEqual(len(prompts), 2)
        self.assertEqual(len(page.gotos), 1)

    def test_cancel_waiting(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                stop.set()
        fetch, _, _, _, events, _ = self.make(emit=callback)
        with self.assertRaises(Cancelled):
            fetch.get(URL)
        self.assertFalse([e for e in events if e['type'] == 'manual'][-1]['active'])

    def test_closed_window_reports_actionable_error(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                page.closed = True
        fetch, *_ = self.make(emit=callback)
        with self.assertRaises(BlockingAccessError) as raised:
            fetch.get(URL)
        self.assertEqual(raised.exception.code, 'BROWSER_CLOSED')

    def test_wrong_page_after_verification_not_accepted(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                page.solve()
                page.url = 'https://www.wlw.de/de/suche/other'
                proceed.set()
        fetch, *_ = self.make(emit=callback)
        with self.assertRaises(BlockingAccessError) as raised:
            fetch.get(URL)
        self.assertEqual(raised.exception.code, 'MANUAL_TIMEOUT')

    def test_http403_stops_without_waiting(self):
        fetch, page, _, _, events, _ = self.make(FakePage('<title>Forbidden</title>', 403))
        with self.assertRaises(BlockingAccessError) as raised:
            fetch.get(URL)
        self.assertEqual(raised.exception.code, 'ACCESS_DENIED')
        self.assertFalse(any(e['type'] == 'manual' for e in events))
        self.assertEqual(len(page.gotos), 1)

    def test_rate_limit_not_hammered(self):
        fetch, page, *_ = self.make(FakePage('Wait', 429))
        page.headers = {'retry-after': '3600'}
        with self.assertRaises(BlockingAccessError) as raised:
            fetch.get(URL)
        self.assertEqual(raised.exception.code, 'RATE_LIMITED')
        self.assertEqual(len(page.gotos), 1)

    def test_iframe_response_does_not_replace_main_status(self):
        fetch, page, *_ = self.make(FakePage(RESULT, 200))
        fetch.get(URL)
        fetch.on_response(SimpleNamespace(status=403, headers={}, request=SimpleNamespace(
            is_navigation_request=lambda: True, frame=object())))
        self.assertEqual(fetch.last_status, 200)

    def test_thread_ownership_is_enforced(self):
        fetch, *_ = self.make()
        errors = []
        def other_thread():
            try:
                fetch.get(URL)
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()
        self.assertIsInstance(errors[0], RuntimeError)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_old_task_identity_supports_browser_switch(self):
        config = Config(query='x')
        store = Store(self.path, config)
        old = json.loads(store.db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
        old['respect_robots'] = True
        store.db.execute("UPDATE meta SET value=? WHERE key='config'", (json.dumps(old),))
        store.db.commit()
        store.put(2, PROFILE, {'status': 'OK', 'website': 'https://acme.de/'})
        store.close()
        changed = Store(self.path, Config(query='x', respect_robots=False, browser_channel='msedge'))
        try:
            self.assertEqual(changed.get(2, PROFILE)['website'], 'https://acme.de/')
        finally:
            changed.close()

    def test_blocked_profile_stops_remaining_profiles_and_is_retryable(self):
        source = self.path / 'profiles.txt'
        source.write_text(PROFILE + '\nhttps://www.wlw.de/de/firma/zz-2\n')
        calls = []
        class Blocked:
            serial_wlw = True
            def __init__(self, *args):
                pass
            def get(self, url):
                calls.append(url)
                raise BlockingAccessError('Manual timeout', 'MANUAL_TIMEOUT')
            def close(self):
                pass
        config = Config(input_file=str(source))
        self.assertEqual(Pipeline(config, self.path / 'out', fetch_factory=Blocked).run(), 'BLOCKED')
        self.assertEqual(calls, [PROFILE])
        store = Store(self.path / 'out', config)
        try:
            self.assertIsNone(store.get(2, PROFILE))
            self.assertIn('MANUAL_TIMEOUT', store.rows(2)[0][1]['detail'])
        finally:
            store.close()

    def test_search_and_profiles_use_coordinator_thread(self):
        owner = threading.get_ident()
        calls, closed = [], []
        class Fake:
            serial_wlw = True
            def __init__(self, *args):
                pass
            def get(self, url):
                calls.append((url, threading.get_ident()))
                if '/de/suche/' in url:
                    return RESULT, url
                if '/de/firma/' in url:
                    return '<a href="https://acme.de">Website</a>', url
                return 'info@acme.de', url
            def close(self):
                closed.append(threading.get_ident())
        self.assertEqual(Pipeline(Config(query='tiefbau', max_pages=1), self.path,
                                  fetch_factory=Fake).run(), 'DONE')
        self.assertTrue(all(tid == owner for url, tid in calls if 'wlw.de' in url))
        self.assertTrue(all(tid != owner for url, tid in calls if 'acme.de' in url))
        self.assertEqual(closed, [owner])

    def test_websites_import_does_not_launch_browser(self):
        from unittest.mock import patch
        source = self.path / 'webs.txt'
        source.write_text('https://acme.de/\n')
        with patch('system.browser_fetcher.BrowserFetcher') as browser, patch('system.browser_fetcher.Fetcher') as http:
            http.return_value.get.return_value = ('info@acme.de', 'https://acme.de/')
            result = Pipeline(Config(input_file=str(source), input_kind='websites'), self.path / 'out').run()
        self.assertEqual(result, 'DONE')
        browser.assert_not_called()


if __name__ == '__main__':
    unittest.main()
