"""Opt-in offline diagnostics for the actual frozen desktop and browser."""
import json
import threading
import time
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from system.paths import data_root, configure_bundled_browser
from system.version import VERSION
from system.updates import atomic_json
from system.instance import Instance


def run(report_path):
    # Never inspect real customer settings or inherit database credentials.
    keys = [name for name in os.environ if name.startswith('MYSQL')] + ['LOCALAPPDATA']
    previous = {name: os.environ.get(name) for name in keys}
    with tempfile.TemporaryDirectory(prefix='WebScraper diagnostics ', ignore_cleanup_errors=True) as local:
        try:
            for name in keys:
                os.environ.pop(name, None)
            os.environ['LOCALAPPDATA'] = local
            return _run(report_path)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _run(report_path):
    from system.app import App
    from system.browser_fetcher import BrowserFetcher
    from system.browser_control import BrowserControl
    from system.core import Config, search_profiles
    configure_bundled_browser()
    result = {'ok': False, 'version': VERSION, 'checks': []}
    def verify(window):
        try:
            if not window.events.loaded.wait(30):
                raise RuntimeError('WebView2 did not load')
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if window.evaluate_js("document.querySelector('#category input') !== null && !document.querySelector('#startup-loader')"):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Desktop bootstrap failed')
            assert window.evaluate_js("typeof window.pywebview.api.install_update") == 'function'
            assert window.evaluate_js("Array.from(document.querySelector('#portal').options).map(o=>o.value)") == ['wlw','11880']
            assert window.evaluate_js("document.querySelector('#app-version').textContent") == VERSION
            assert str(data_root() / 'vysledky') in window.evaluate_js("document.querySelector('#folder').value")
            result['checks'].extend(['WebView2', 'desktop bootstrap', 'both portal choices', 'installed data paths', 'update bridge'])
            window.evaluate_js("document.querySelector('#settings-dialog').close(); document.querySelector('#preferences-toggle').click()")
            time.sleep(.5)
            assert window.evaluate_js("document.querySelector('#preferences-dialog').open")
            result['checks'].append('application settings dialog')
            # Route every request locally. This never contacts a portal or database.
            for portal, url, markup in [
                ('wlw','https://www.wlw.de/de/suche/tiefbau','<a href="/de/firma/example-123">Firma</a>'),
                ('11880','https://www.11880.com/suche/Tiefbau/deutschland','<a href="/branchenbuch/dortmund/123B456/acme.html">Mehr Details</a>')]:
                control = BrowserControl(hidden=True)
                fetch = BrowserFetcher(Config(portal=portal), threading.Event(), lambda *args, **kwargs: None,
                    data_root() / 'diagnostics' / portal, threading.Event(),
                    SimpleNamespace(validate_target=lambda url: None, pace=lambda url: None), browser_control=control)
                try:
                    fetch.start()
                    fetch.context.route('**/*', lambda route: route.fulfill(content_type='text/html', body=markup))
                    fetch.page.goto(url)
                    assert search_profiles(fetch.page.content(), url, portal)
                    assert control.snapshot()['visibility'] == 'hidden'
                    assert control.toggle()
                    fetch.tick()
                    assert control.snapshot()['visibility'] == 'shown'
                    assert control.toggle()
                    fetch.tick()
                    assert control.snapshot()['visibility'] == 'hidden'
                    result['checks'].append('bundled Chromium ' + portal + ' navigation/show/hide')
                finally:
                    fetch.close()
            result['ok'] = True
        except Exception as exc:
            result['error'] = str(exc)
        finally:
            atomic_json(report_path, result)
            window.destroy()
    try:
        with Instance():
            App()._launch(verify=verify)
    except Exception as exc:
        result['error'] = str(exc)
        atomic_json(report_path, result)
    return 0 if result['ok'] else 1
