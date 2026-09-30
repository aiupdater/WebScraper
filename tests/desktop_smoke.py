r"""Actual Windows WebView2 / Python bridge smoke, with isolated local settings.

Run: .venv\Scripts\python.exe tests/desktop_smoke.py
No external database connection or scraping is performed.
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import webview
from system import app
from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix='webscraper-desktop-') as temporary:
        base = Path(temporary)

        class Contacts:
            def __init__(self, settings): pass
            def groups(self): return [(7, 'Testovací skupina')]
            def close(self): pass

        api = DesktopAPI(base, settings=MySQLSettings(host='test.invalid', user='test',
                         database='test', password='desktop-smoke-only'), contacts_factory=Contacts)
        original_create, original_start = webview.create_window, webview.start

        def create(*args, **kwargs):
            kwargs['hidden'] = True
            return original_create(*args, **kwargs)

        def checks(window):
            def until(expression):
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if window.evaluate_js(expression):
                        return
                    time.sleep(.1)
                raise AssertionError('WebView2 podmínka nesplněna: ' + expression)

            try:
                assert window.events.loaded.wait(20), 'WebView2 stránka se nenačetla.'
                until("document.querySelector('#category input') !== null && !document.querySelector('#start').disabled")
                assert window.evaluate_js("typeof window.pywebview.api.bootstrap") == 'function'
                assert window.evaluate_js("Array.from(document.querySelector('#portal').options).map(o=>o.value)") == ['wlw', '11880']
                window.evaluate_js("document.querySelector('#portal').value='11880'; document.querySelector('#portal').dispatchEvent(new Event('change'))")
                until("document.querySelector('#portal-help').textContent.includes('přímo z profilů')")
                before = api._folder
                window.evaluate_js("document.querySelector('#new-folder').click()")
                until("document.querySelector('#folder').value !== " + json.dumps(before))
                assert window.evaluate_js("document.querySelector('#folder').value") == api._folder
                chosen = base / 'chosen'
                chosen.mkdir()
                # The operating-system picker is replaced, the real Python handler
                # and JavaScript promise/event path are exercised unchanged.
                with patch.object(window, 'create_file_dialog', return_value=[str(chosen)]):
                    window.evaluate_js("document.querySelector('#choose-folder').click()")
                    until("document.querySelector('#folder').value === " + json.dumps(str(chosen)))
                window.evaluate_js("document.querySelector('#mysql-toggle').click()")
                until("document.querySelector('#settings-dialog').open && document.querySelector('#db-password').value === 'desktop-smoke-only'")
                # WebView2 defers rendering-task events (including dialog close)
                # while its window is hidden. Password clearing is covered by
                # ui_smoke.py in a rendered browser page.
                window.evaluate_js("document.querySelector('#settings-dialog').close()")
                print('PASS: skutečný WebView2, Python bootstrap, oba portály, nová/vybraná složka a nastavení MySQL')
            except Exception as exc:
                failures.append(exc)
            finally:
                window.destroy()

        def start(**kwargs):
            kwargs['storage_path'] = str(base/'webview-state')
            kwargs['private_mode'] = True
            original_start(checks, (api._window,), **kwargs)

        with patch.object(app, 'DesktopAPI', return_value=api), \
             patch.object(webview, 'create_window', side_effect=create), \
             patch.object(webview, 'start', side_effect=start):
            app.App()._launch()
    if failures:
        raise failures[0]


if __name__ == '__main__':
    main()
