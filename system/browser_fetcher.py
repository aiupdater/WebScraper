"""Viditelný prohlížeč pro vybraný katalog; CAPTCHA řeší výhradně uživatel.

Nepoužívá stealth, proxy rotaci, solver ani přenos ověřovacích cookies do HTTPX.
Jedna instance je vlastněna vláknem Pipeline od vytvoření až po zavření.
"""
from __future__ import annotations

import threading
import queue
import sys
import json
from concurrent.futures import ThreadPoolExecutor
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from bs4 import BeautifulSoup

from system.access import detect_access_problem
from system.core import BlockingAccessError, Cancelled, FetchError, Fetcher, clean_url, host, search_profiles, search_url


def is_wlw(url):
    return host(url) in ('wlw.de', 'www.wlw.de')


def is_portal(url, portal):
    return host(url) in (('11880.com', 'www.11880.com') if portal == '11880' else ('wlw.de', 'www.wlw.de'))


def same_page(expected, actual):
    if not (is_portal(expected, 'wlw') and is_portal(actual, 'wlw') or
            is_portal(expected, '11880') and is_portal(actual, '11880')):
        return False
    a, b = urlsplit(expected), urlsplit(actual)
    return unquote(a.path).rstrip('/') == unquote(b.path).rstrip('/') and a.query == b.query


def content_ready(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    if is_portal(url, '11880'):
        if urlsplit(url).path.startswith('/suche/'):
            return bool(search_profiles(html, url, '11880'))
        if urlsplit(url).path.startswith('/branchenbuch/'):
            return bool(soup.select_one('h1'))
    if '/de/suche/' in urlsplit(url).path:
        return bool(soup.select_one('a[href*="/de/firma/"]'))
    if '/de/firma/' in urlsplit(url).path:
        return bool(soup.select_one('h1'))
    return False


class BrowserFetcher:
    def __init__(self, config, stop, emit, folder, continue_event, http,
                 *, context_factory=None, clock=time.monotonic, browser_control=None, controller_factory=None):
        self.config, self.stop, self.emit = config, stop, emit
        self.folder, self.continue_event, self.http = Path(folder), continue_event, http
        self.context_factory, self.clock = context_factory, clock
        self.owner = threading.get_ident()
        self.context = self.page = self.playwright = None
        self.last_status, self.last_headers = 0, {}
        self.navigation_error = ''
        self.waiting = False
        self.manual_problem = None
        self.control = browser_control
        self.controller_factory = controller_factory
        self.controller = self.cdp = None
        self.navigation_marker = None
        self.hidden_mode = bool(browser_control and browser_control.hidden and sys.platform == 'win32')

    def browser_state(self, **values):
        if self.control:
            self.emit('browser', **self.control.update(**values))

    def recover_window(self):
        # This session is bound to this Playwright page, never to an arbitrary HWND.
        try:
            if self.cdp is None:
                self.cdp = self.context.new_cdp_session(self.page)
            window = self.cdp.send('Browser.getWindowForTarget')['windowId']
            self.cdp.send('Browser.setWindowBounds', {'windowId': window, 'bounds': {'windowState': 'normal'}})
            from system.browser_window import recovery_bounds
            bounds = recovery_bounds() if sys.platform == 'win32' else dict(left=40, top=40, width=1000, height=700)
            self.cdp.send('Browser.setWindowBounds', {'windowId': window, 'bounds': bounds})
            actual = self.cdp.send('Browser.getWindowBounds', {'windowId': window})['bounds']
            if actual.get('windowState') != 'normal' or actual['left'] < bounds['left'] or actual['top'] < bounds['top']:
                raise RuntimeError('Obnova okna nebyla potvrzena.')
            self.page.bring_to_front()
            self.controller = None
            self.browser_state(visibility='shown', fallback=True, pending=False)
            message = 'Ovládání okna není dostupné. Prohlížeč zůstává viditelný; tlačítko jej pouze přenese do popředí.'
            self.emit('log', level='WARN', message=message)
            self.emit('browser_warning', message=message)
        except Exception as exc:
            try:
                self.close()
            except Exception:
                self.emit('log', level='WARN', message='Ukončení nedostupného sběrného prohlížeče nebylo potvrzeno.')
            self.emit('browser_retry', message='Okno nelze zpřístupnit. Uložený běh je zachovaný. Tlačítkem Pokračovat jej spustíte ve viditelném režimu.')
            raise BlockingAccessError('Okno nelze bezpečně zpřístupnit. Uložený běh zůstává zachovaný. Pokračujte ve viditelném režimu prohlížeče.', 'BROWSER_WINDOW_UNAVAILABLE') from exc

    def service_commands(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Příkazy prohlížeče se provádějí ve vlákně sběru.')
        if not self.control or not self.page:
            return
        try:
            command = self.control.commands.get_nowait()
        except queue.Empty:
            return
        if command == 'toggle':
            try:
                if self.controller:
                    was_visible = self.controller.visible()
                    if was_visible:
                        self.controller.hide()
                    else:
                        self.controller.show()
                    actual = self.controller.visible()
                    self.browser_state(visibility='shown' if actual else 'hidden', pending=False)
                    if actual == was_visible:
                        self.emit('browser_warning', message='Windows nepotvrdil změnu zobrazení prohlížeče. Zkuste tlačítko znovu.')
                else:
                    self.page.bring_to_front()
                    self.browser_state(visibility='shown', pending=False)
            except Exception:
                try:
                    actual = self.controller.visible()
                except Exception:
                    # Never use a stale/unverified HWND. CDP can safely restore our page.
                    self.recover_window()
                else:
                    self.browser_state(visibility='shown' if actual else 'hidden', pending=False)
                    self.emit('browser_warning', message='Zobrazení prohlížeče se nepodařilo změnit. Zkuste tlačítko znovu.')

    def cooperative(self, operation, *args):
        if not self.control:
            return operation(*args)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(operation, *args)
            while not future.done():
                self.tick()
            return future.result()

    def check(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Prohlížeč byl zavolán z jiného vlákna.')
        if self.stop.is_set():
            raise Cancelled()
        if self.page and self.page.is_closed():
            raise BlockingAccessError('Okno prohlížeče bylo zavřeno. Spusťte pokračování.', 'BROWSER_CLOSED')

    def start(self):
        self.check()
        if self.context:
            return
        if self.context_factory:
            self.context = self.context_factory()
        else:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise BlockingAccessError('Chybí Playwright. Spusťte INSTALOVAT.bat.', 'BROWSER_MISSING') from exc
            self.playwright = sync_playwright().start()
            options = {'headless': False, 'viewport': {'width': 1280, 'height': 900},
                       'accept_downloads': False, 'timeout': 30000}
            if self.config.browser_channel != 'chromium':
                options['channel'] = self.config.browser_channel
            profile = self.folder / ('prohlizec_' + self.config.browser_channel)
            if self.hidden_mode:
                try:
                    from system.browser_window import BrowserWindowController
                    self.controller = (self.controller_factory or BrowserWindowController)(profile)
                    # Native startup minimization prevents painting even when Chromium
                    # restores saved window placement. Avoid viewport emulation resizing
                    # the window back onto the desktop before HWND identification.
                    options['viewport'] = None
                    options['no_viewport'] = True
                    options['args'] = ['--start-minimized', '--window-position=-32000,-32000', '--window-size=1280,900', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']
                except Exception:
                    # If ownership cannot be established before launch, start visibly.
                    self.controller = None
                    self.emit('log', level='WARN', message='Skrytý start není dostupný. Prohlížeč bude otevřený.')
            try:
                self.context = self.playwright.chromium.launch_persistent_context(str(profile), **options)
            except Exception as exc:
                self.playwright.stop()
                self.playwright = None
                raise BlockingAccessError(
                    'Prohlížeč se nepodařilo otevřít. Zavřete jeho staré okno; pro Chromium '
                    'spusťte INSTALOVAT.bat. Edge/Chrome musí být nainstalován. ' + str(exc).splitlines()[0][:250],
                    'BROWSER_START_FAILED') from exc
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(5000)
        self.page.on('response', self.on_response)
        # Povolujeme hlavní stránku pouze na vybraném portálu; vložené CAPTCHA a běžné
        # prostředky třetích stran potřebuje prohlížeč k ručnímu ověření.
        self.context.route('**/*', self.guard_navigation)
        if self.hidden_mode and self.controller:
            try:
                for _ in range(25):
                    if self.controller.find():
                        break
                    self.page.wait_for_timeout(100)
                self.controller.hide()
                self.browser_state(visibility='hidden')
            except Exception:
                self.recover_window()
        else:
            self.browser_state(visibility='shown', fallback=True)
        self.emit('log', message=f'Otevřen prohlížeč {self.config.browser_channel}. Portál se zpracovává postupně.')

    def guard_navigation(self, route):
        request = route.request
        if request.is_navigation_request() and request.frame == self.page.main_frame:
            if not clean_url(request.url) or not is_portal(request.url, self.config.portal):
                self.navigation_error = 'Přesměrování hlavní stránky mimo vybraný portál; ověřte adresu ručně.'
                route.abort()
                return
        route.fallback()

    def on_response(self, response):
        if response.request.is_navigation_request() and response.request.frame == self.page.main_frame:
            self.last_status = response.status
            self.last_headers = {k: v for k, v in response.headers.items()
                                 if k.lower() in ('x-amzn-waf-action', 'retry-after', 'allow', 'content-type')}

    def tick(self):
        self.check()
        self.service_commands()
        # Playwright při tomto čekání obsluhuje události načtení / ručního ověření.
        self.page.wait_for_timeout(200)
        self.check()
        self.refresh_visibility()

    def refresh_visibility(self):
        if self.controller and not self.control.snapshot()['pending']:
            try:
                actual = 'shown' if self.controller.visible() else 'hidden'
                if actual != self.control.snapshot()['visibility']:
                    self.browser_state(visibility=actual)
            except Exception:
                self.recover_window()

    def snapshot(self):
        self.check()
        if self.navigation_error:
            raise BlockingAccessError(self.navigation_error, 'UNEXPECTED_REDIRECT')
        try:
            if self.navigation_marker is not None and self.page.evaluate('window.__webscraperNavigation === ' + json.dumps(self.navigation_marker)):
                return None
            html = self.page.content()
        except Exception:
            self.check()
            return None  # Může právě probíhat přesměrování po ručním ověření.
        if len(html.encode('utf-8')) > 3_000_000:
            raise FetchError('Stránka přesahuje limit 3 MB')
        return html, self.page.url

    def wait_for_manual(self, url, message):
        deadline = self.clock() + self.config.manual_timeout
        self.continue_event.clear()
        self.waiting = True
        if not self.hidden_mode:
            self.page.bring_to_front()
        self.browser_state(captcha=True)
        self.emit('log', level='WARN', message=message + ' Sběr čeká na ruční ověření a potvrzení.')
        self.emit('manual', active=True, url=url,
                  message='Dokončete ověření v otevřeném prohlížeči. Pak stiskněte Ověřeno — pokračovat.')
        try:
            while self.clock() < deadline:
                self.tick()
                if not self.continue_event.is_set():
                    continue
                self.continue_event.clear()
                result = self.read_ready(url, max_seconds=8)
                if result:
                    self.emit('log', message='Ruční ověření potvrzeno; obsah stránky je dostupný. Pokračuji.')
                    return result
                self.emit('manual', active=True, url=url,
                          message='Ověření ještě není dokončené nebo chybí výsledky. Dokončete je v prohlížeči a potvrďte znovu.')
            raise BlockingAccessError('Vypršel čas na ruční ověření. Uloženou práci lze obnovit.', 'MANUAL_TIMEOUT')
        finally:
            self.waiting = False
            self.browser_state(captcha=False)
            self.emit('manual', active=False, url=url)

    def read_ready(self, url, max_seconds=12):
        deadline = self.clock() + max_seconds
        while self.clock() < deadline:
            result = self.snapshot()
            if result:
                html, actual = result
                problem = detect_access_problem(self.last_status, self.last_headers, html)
                if problem:
                    if problem.manual:
                        self.manual_problem = problem
                        return None
                    error = FetchError if problem.code == 'HTTP_ERROR' else BlockingAccessError
                    raise error(problem.message, problem.code)
                if self.last_status and same_page(url, actual) and content_ready(html, actual):
                    return result
            self.tick()
        return None

    def get(self, url):
        # 11880 stránkuje POST formulářem. Samotné GET ?page=N může být odmítnuto.
        # Použijeme skutečné tlačítko, včetně přechodu na zvolenou počáteční stránku.
        parts = urlsplit(url)
        if self.config.portal == '11880' and parts.path.startswith('/suche/'):
            target = int(parse_qs(parts.query).get('page', ['1'])[0])
            if target > 1:
                self.check()
                actual = urlsplit(self.page.url) if self.page else None
                current = int(parse_qs(actual.query).get('page', ['1'])[0]) if actual else 0
                if not actual or not is_portal(self.page.url, '11880') or actual.path != parts.path or not 1 <= current < target:
                    self._get(search_url(url, 1, '11880'))
                    current = 1
                for page_number in range(current + 1, target + 1):
                    result = self._get(search_url(url, page_number, '11880'), use_next=True)
                return result
        return self._get(url)

    def _get(self, url, *, use_next=False):
        self.check()
        if not clean_url(url) or not is_portal(url, self.config.portal):
            raise FetchError('Prohlížeč je vyhrazen pouze veřejným stránkám vybraného portálu.')
        self.start()
        self.service_commands()
        self.cooperative(self.http.validate_target, url)
        self.cooperative(self.http.pace, url)
        self.last_status, self.last_headers, self.navigation_error = 0, {}, ''
        self.manual_problem = None
        self.emit('request', url=url)
        try:
            if use_next:
                deadline = self.clock() + self.config.timeout
                while True:
                    try:
                        self.page.locator('button[aria-label="Zur nächsten Seite"]').click(timeout=250, no_wait_after=True)
                        break
                    except Exception:
                        if self.clock() >= deadline:
                            raise
                        self.tick()
                response = None
            elif self.control and not self.context_factory:
                # CDP initiates navigation without waiting for DOMContentLoaded.
                # The ordinary readiness/CAPTCHA loop pumps commands every 200 ms.
                if self.cdp is None:
                    self.cdp = self.context.new_cdp_session(self.page)
                # Schedule the navigation after Runtime.evaluate has returned;
                # Page.navigate itself can wait on a slow response before commit.
                self.navigation_marker = str(time.monotonic_ns())
                self.cdp.send('Runtime.evaluate', {'expression': 'window.__webscraperNavigation = ' + json.dumps(self.navigation_marker) + '; setTimeout(() => location.assign(' + json.dumps(url) + '), 0)'})
                deadline = self.clock() + self.config.timeout
                while not self.last_status and self.clock() < deadline:
                    self.tick()
                response = None
            else:
                response = self.page.goto(url, wait_until='domcontentloaded', timeout=self.config.timeout * 1000)
            if response and not self.last_status:
                self.on_response(response)
        except Exception as exc:
            self.check()
            # Timeout může nastat i u již zobrazené stránky. Zkusíme číst DOM,
            # nikdy kvůli němu neobnovujeme CAPTCHA a nevytváříme retry smyčku.
            if not self.last_status:
                raise FetchError('Načtení v prohlížeči selhalo: ' + str(exc).splitlines()[0][:250]) from exc
        result = self.read_ready(url)
        if result:
            return result
        if self.manual_problem:
            return self.wait_for_manual(url, self.manual_problem.message)
        snap = self.snapshot()
        if snap:
            problem = detect_access_problem(self.last_status, self.last_headers, snap[0])
            if problem and problem.manual:
                return self.wait_for_manual(url, problem.message)
        raise FetchError('Stránka neobsahuje očekávané výsledky/profil. Zkontrolujte dotaz, stránkování nebo HTML.', 'CONTENT_NOT_READY')

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Prohlížeč se musí zavřít ve vlákně, ve kterém vznikl.')
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = self.page = None
            self.controller = self.cdp = None
            if self.control:
                self.control.reset()
                self.emit('browser', **self.control.snapshot())
            if self.playwright:
                self.playwright.stop()
                self.playwright = None


class HybridFetcher:
    # Také přímý HTTP režim WLW je sekvenční: blokace zastaví další profily.
    serial_wlw = True

    def __init__(self, config, stop, emit, folder, continue_event, browser_control=None):
        self.config, self.stop, self.emit = config, stop, emit
        self.folder, self.continue_event = folder, continue_event
        self.http = Fetcher(config, stop, emit)
        self.browser = None
        self.browser_control = browser_control
        self.owner = threading.get_ident()

    def pump(self):
        if self.browser and threading.get_ident() == self.owner:
            self.browser.check()
            self.browser.service_commands()
            self.browser.page.wait_for_timeout(1)
            self.browser.refresh_visibility()

    def get(self, url):
        if is_portal(url, self.config.portal) and self.config.wlw_mode == 'browser':
            if self.browser is None:
                self.browser = BrowserFetcher(self.config, self.stop, self.emit,
                                              self.folder, self.continue_event, self.http, browser_control=self.browser_control)
            return self.browser.get(url)
        if self.browser and threading.get_ident() == self.owner:
            return self.browser.cooperative(self.http.get, url)
        return self.http.get(url)

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            self.http.close()
