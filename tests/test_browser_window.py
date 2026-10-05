import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from system.browser_control import BrowserControl
from system.core import BlockingAccessError
from system.browser_window import BrowserWindowController
from system.desktop import DesktopAPI
from system.mysql_contacts import MySQLSettings
from system.notifications import notify_verification
from test_browser import BrowserTests, FakePage, RESULT, URL


class Native:
    def __init__(self):
        self.pid_value = 20
        self.shown = True
        self.iconic = False
        self.calls = []
    def windows(self): return [(7, self.pid_value), (8, 30)]
    def pid(self, hwnd): return self.pid_value
    def visible(self, hwnd): return self.shown
    def minimized(self, hwnd): return self.iconic
    def rect(self, hwnd): return (80, 80, 1000, 700)
    def show(self, hwnd, command):
        self.calls.append(('show', hwnd, command))
        self.shown = command != 0
        self.iconic = False
    def place(self, hwnd, normal): self.calls.append(('place', hwnd, normal))
    def activate(self, hwnd): self.calls.append(('activate', hwnd))


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.profile = Path(tempfile.gettempdir()) / 'browser-unit-profile'
        self.items = [self.process(10, 'other')]
        self.native = Native()
        self.controller = BrowserWindowController(self.profile, processes=lambda fields: self.items, native=self.native)
        self.items += [self.process(20, str(self.profile)), self.process(30, 'user-profile')]

    def process(self, pid, profile, created=1):
        return SimpleNamespace(info=dict(pid=pid, name='chrome.exe', cmdline=['--user-data-dir=' + profile], create_time=created, ppid=0))

    def test_only_current_profile_is_selected(self):
        self.assertTrue(self.controller.find())
        self.controller.hide()
        self.controller.show()
        self.assertTrue(self.controller.visible())
        self.assertTrue(all(call[1] == 7 for call in self.native.calls))

    def test_reused_hwnd_owner_is_rejected_before_manipulation(self):
        self.controller.find()
        self.native.pid_value = 30
        with self.assertRaises(RuntimeError): self.controller.hide()
        self.assertEqual(self.native.calls, [])

    def test_reused_pid_creation_time_is_rejected(self):
        self.controller.find()
        self.items[1] = self.process(20, 'unrelated', created=2)
        with self.assertRaises(RuntimeError): self.controller.show()
        self.assertEqual(self.native.calls, [])

    def test_existing_profile_process_is_not_claimed(self):
        controller = BrowserWindowController(self.profile, processes=lambda fields: self.items, native=self.native)
        self.assertFalse(controller.find())

    def test_minimized_window_counts_as_hidden(self):
        self.controller.find()
        self.native.iconic = True
        self.assertFalse(self.controller.visible())
        self.controller.show()
        self.assertTrue(self.controller.visible())

    def test_owner_thread(self):
        self.controller.find()
        errors = []
        def wrong_thread():
            try: self.controller.hide()
            except RuntimeError as exc: errors.append(exc)
        thread = threading.Thread(target=wrong_thread)
        thread.start(); thread.join()
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.native.calls, [])


class ControlTests(unittest.TestCase):
    def test_notification_thread_start_failure_is_nonfatal(self):
        with patch('system.notifications.threading.Thread', side_effect=RuntimeError('fixture')):
            with self.assertLogs('system.notifications', level='WARNING'):
                notify_verification()

    def test_notification_adapter_failure_is_nonfatal(self):
        adapter = SimpleNamespace(Toast=Mock(), WindowsToaster=Mock(side_effect=RuntimeError('fixture')))
        def immediate_thread(target, **kwargs):
            return SimpleNamespace(start=target)
        with patch.dict('sys.modules', windows_toasts=adapter), patch('system.notifications.sys.platform', 'win32'), patch('system.notifications.threading.Thread', side_effect=immediate_thread):
            with self.assertLogs('system.notifications', level='WARNING'):
                notify_verification()

    def test_bridge_enqueues_and_bootstrap_reflects_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            api = DesktopAPI(folder, settings=MySQLSettings())
            self.assertFalse(api.toggle_browser_visibility()['ok'])
            api._running = True
            api._browser_control.update(visibility='hidden')
            self.assertTrue(api.toggle_browser_visibility()['ok'])
            self.assertFalse(api.toggle_browser_visibility()['ok'])
            self.assertTrue(api.bootstrap()['browser']['pending'])
            self.assertEqual(api._browser_control.commands.get_nowait(), 'toggle')
            api._emit(dict(type='browser_retry', message='fixture'))
            self.assertTrue(api.bootstrap()['visible_browser_retry'])

    def test_pending_dedup_and_reset(self):
        control = BrowserControl()
        self.assertFalse(control.toggle())
        control.update(visibility='hidden')
        self.assertTrue(control.toggle())
        self.assertFalse(control.toggle())
        control.reset()
        self.assertEqual(control.snapshot(), dict(visibility='off', captcha=False, pending=False, fallback=False))
        with self.assertRaises(queue.Empty): control.commands.get_nowait()

    def test_notification_only_first_transition_while_minimized(self):
        with tempfile.TemporaryDirectory() as folder:
            api = DesktopAPI(folder, settings=MySQLSettings())
            api._on_minimized()
            with patch('system.desktop.notify_verification') as notify:
                api._emit(dict(type='manual', active=True))
                api._emit(dict(type='manual', active=True))
                self.assertEqual(notify.call_count, 1)
                api._emit(dict(type='manual', active=False))
                api._emit(dict(type='manual', active=True))
                self.assertEqual(notify.call_count, 2)
                api._on_restored()
                api._emit(dict(type='manual', active=False))
                api._emit(dict(type='manual', active=True))
                self.assertEqual(notify.call_count, 2)


class FetchControlTests(unittest.TestCase):
    make = BrowserTests.make
    def test_commands_outside_captcha_preserve_page_context(self):
        fetch, page, _, _, events, context = self.make(page=FakePage(RESULT, 200))
        fetch.control = BrowserControl()
        fetch.start()
        native = Native()
        fetch.controller = SimpleNamespace(visible=lambda: native.shown, hide=lambda: setattr(native, 'shown', False), show=lambda: setattr(native, 'shown', True))
        for expected in ('hidden', 'shown'):
            self.assertTrue(fetch.control.toggle())
            fetch.tick()
            self.assertEqual(fetch.control.snapshot()['visibility'], expected)
            self.assertIs(fetch.page, page)
            self.assertIs(fetch.context, context)
        fetch.close()
        self.assertEqual(fetch.control.snapshot()['visibility'], 'off')

    def test_desktop_captcha_does_not_bring_to_front(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                page.solve(); proceed.set()
        fetch, page, *_ = self.make(emit=callback)
        fetch.control = BrowserControl()
        fetch.hidden_mode = True
        with patch.object(page, 'bring_to_front') as front:
            fetch.get(URL)
            front.assert_not_called()
        self.assertFalse(fetch.control.snapshot()['captcha'])

    def test_cli_captcha_brings_to_front(self):
        def callback(kind, data, page, stop, proceed):
            if kind == 'manual' and data['active']:
                page.solve(); proceed.set()
        fetch, page, *_ = self.make(emit=callback)
        with patch.object(page, 'bring_to_front') as front:
            fetch.get(URL)
            front.assert_called_once()

    def test_failed_recovery_closes_only_context_and_offers_resume(self):
        fetch, _, _, _, events, context = self.make(page=FakePage(RESULT, 200))
        fetch.control = BrowserControl()
        fetch.start()
        with self.assertRaises(BlockingAccessError) as raised: fetch.recover_window()
        self.assertEqual(raised.exception.code, 'BROWSER_WINDOW_UNAVAILABLE')
        self.assertTrue(context.closed)
        self.assertTrue(any(e['type'] == 'browser_retry' for e in events))
