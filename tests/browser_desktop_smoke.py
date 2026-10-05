"""Real Windows browser windows on isolated fixtures; no live scraping or database."""
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from system.browser_fetcher import BrowserFetcher
from system.browser_control import BrowserControl
from system.core import Config
from system.browser_window import BrowserWindowController, WindowsNative

URL = 'http://www.wlw.de/de/suche/window-smoke'
HTML = '<h1>Fixture</h1><a href="/de/firma/fixture">Fixture</a>'


def observe_start(fetch, runtime):
    """Read-only polling also covers the interval inside Playwright launch."""
    profile = fetch.folder / ('prohlizec_' + fetch.config.browser_channel)
    probe = BrowserWindowController(profile)
    stop = threading.Event()
    visible_samples, errors = [], []
    def observe():
        try:
            native = WindowsNative()
            while not stop.is_set():
                pids = {identity[0] for identity in probe.owned()}
                for hwnd, pid in native.windows():
                    if pid in pids and native.visible(hwnd) and not native.minimized(hwnd):
                        left, top, width, height = native.rect(hwnd)
                        if left > -10000 and top > -10000:
                            visible_samples.append((left, top, width, height))
                stop.wait(.01)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=observe)
    thread.start()
    try:
        with patch('playwright.sync_api.sync_playwright', return_value=SimpleNamespace(start=lambda: runtime)):
            fetch.start()
    finally:
        stop.set()
        thread.join(5)
    assert not errors, errors
    assert not visible_samples, visible_samples


def main():
    if sys.platform != 'win32':
        print('UNVERIFIED: Windows required')
        return
    with tempfile.TemporaryDirectory(prefix='webscraper-window-smoke-') as folder:
        for channel in ('chromium', 'msedge', 'chrome'):
            events = []
            control = BrowserControl()
            http = SimpleNamespace(validate_target=lambda u: None, pace=lambda u: None)
            fetch = BrowserFetcher(Config(browser_channel=channel, delay=0), threading.Event(),
                                   lambda kind, **data: events.append(dict(type=kind, **data)),
                                   folder, threading.Event(), http, browser_control=control)
            user_context = user_pw = None
            try:
                # A concurrent window of the same channel must remain untouched.
                user_profile = Path(folder) / ('user_' + channel)
                user_controller = BrowserWindowController(user_profile)
                # Reuse one Playwright runtime; multiple Sync API loops in a thread are unsupported.
                user_pw = sync_playwright().start()
                options = dict(headless=False)
                if channel != 'chromium': options['channel'] = channel
                user_context = user_pw.chromium.launch_persistent_context(str(user_profile), **options)
                for _ in range(25):
                    if user_controller.find(): break
                    user_context.pages[0].wait_for_timeout(100)
                assert user_controller.visible(), 'Fixture user window not found'
                user_hwnd = user_controller.hwnd
                observe_start(fetch, user_pw)
                assert control.snapshot()['visibility'] == 'hidden', control.snapshot()
                assert fetch.controller and not fetch.controller.visible()
                page = fetch.page
                completed = threading.Event()
                entered = threading.Event()
                class Fixture(BaseHTTPRequestHandler):
                    def do_GET(self):
                        entered.set()
                        time.sleep(2)
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(HTML.encode())
                        completed.set()
                    def log_message(self, *args): pass
                server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                # Rewrite only in the test fixture; production navigation guard is unchanged.
                fetch.context.route(URL, lambda route: route.continue_(url=f'http://127.0.0.1:{server.server_port}/'))
                def toggle_during_navigation():
                    assert entered.wait(5)
                    control.toggle()
                thread = threading.Thread(target=toggle_during_navigation)
                thread.start()
                toggled_before_response = []
                original_emit = fetch.emit
                def observe(kind, **data):
                    if kind == 'browser' and data.get('visibility') == 'shown':
                        toggled_before_response.append(not completed.is_set())
                    original_emit(kind, **data)
                fetch.emit = observe
                try:
                    # The rewritten response URL differs; override only the fixture readiness comparison.
                    with patch('system.browser_fetcher.same_page', return_value=True), patch('system.browser_fetcher.content_ready', return_value=True):
                        assert fetch.get(URL)[0].find('Fixture') >= 0
                finally:
                    thread.join(5)
                    server.shutdown()
                    server.server_close()
                assert toggled_before_response == [True], toggled_before_response
                assert completed.is_set()
                assert control.snapshot()['visibility'] == 'shown'
                assert fetch.page is page
                fetch.controller.native.show(fetch.controller.hwnd, 2)
                assert not fetch.controller.visible()
                assert control.toggle()
                fetch.tick()
                assert fetch.controller.visible()
                assert control.toggle()
                fetch.tick()
                assert control.snapshot()['visibility'] == 'hidden'
                fetch.context.unroute(URL)
                fetch.context.route(URL, lambda route: route.fulfill(status=200, content_type='text/html', body=HTML))
                assert fetch.get(URL)[0].find('Fixture') >= 0
                assert user_controller.hwnd == user_hwnd and user_controller.visible()
                # Safely exercise identification-loss fallback through the page CDP session.
                with patch.object(fetch.controller, 'visible', side_effect=RuntimeError('lost HWND')):
                    assert control.toggle()
                    fetch.tick()
                assert control.snapshot()['fallback'] and control.snapshot()['visibility'] == 'shown'
                bounds = fetch.cdp.send('Browser.getWindowForTarget')['bounds']
                assert bounds['left'] >= 0 and bounds['top'] >= 0, bounds
                assert user_controller.visible()
                page.close()
                try:
                    fetch.check()
                except Exception as exc:
                    assert exc.code == 'BROWSER_CLOSED'
                else:
                    raise AssertionError('Closing the browser must report BROWSER_CLOSED')
                # Keep the fixture runtime alive and relaunch the same saved profile.
                fetch.playwright = None
                fetch.close()
                fetch = BrowserFetcher(Config(browser_channel=channel, delay=0), threading.Event(),
                                       lambda *args, **kwargs: None, folder, threading.Event(), http, browser_control=control)
                observe_start(fetch, user_pw)
                assert control.snapshot()['visibility'] == 'hidden'
                fetch.controller.show()
                assert fetch.controller.visible()
                print(f'PASS: {channel}: start/resume without sampled visible window, hidden/show/hide, loading, same page, foreign window unchanged, CDP recovery', flush=True)
            except Exception as exc:
                if 'Executable doesn' in str(exc) or 'distribution' in str(exc):
                    print(f'UNVERIFIED: {channel}: missing installation', flush=True)
                else:
                    raise
            finally:
                if user_context: user_context.close()
                fetch.close()
                if user_pw and fetch.playwright is None:
                    try: user_pw.stop()
                    except Exception: pass


if __name__ == '__main__':
    main()
