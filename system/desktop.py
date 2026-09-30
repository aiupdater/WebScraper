"""Thread-safe bridge. UI assets have no database credentials or network logic."""
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
from system.core import Config, Pipeline
from system.mysql_contacts import MySQLSettings, MySQLContacts
from system.paths import APP_ROOT, config_path

class DesktopAPI:
    def __init__(self, base=None, *, settings=None, pipeline_factory=Pipeline,
                 contacts_factory=MySQLContacts):
        self._base = Path(base or APP_ROOT).resolve()
        self._window = None
        self._pipeline_factory, self._contacts_factory = pipeline_factory, contacts_factory
        self._events = queue.Queue()
        self._lock = threading.RLock()
        self._stop, self._continue, self._finish = threading.Event(), threading.Event(), threading.Event()
        self._worker = None
        self._running = self._db_busy = self._closing = self._manual = False
        self._discard_requested = False
        self._groups = None
        self._settings_error = ''
        self._categories_error = ''
        self._categories = []
        self._categories_path = config_path('categories.local.json', self._base)
        try:
            if self._categories_path.exists():
                self._categories = self._validate_categories(json.loads(self._categories_path.read_text(encoding='utf-8')))
            else:
                self._write_categories(['Tiefbau'])
                self._categories = ['Tiefbau']
        except (ValueError, OSError):
            self._categories_error = 'Nelze načíst nebo uložit categories.local.json. Zkontrolujte soubor kategorií.'
        try:
            config_path('.env', self._base)
            self._settings = settings or MySQLSettings.load(config_path('mysql.local.json', self._base))
        except (ValueError, TypeError, OSError):
            self._settings = MySQLSettings()
            self._settings_error = 'Nelze načíst mysql.local.json. Opravte nastavení připojení.'
        self._folder = self._new_folder()

    def _new_folder(self):
        return str(self._base / 'vysledky' / datetime.now().strftime('%Y%m%d_%H%M%S_%f'))

    @staticmethod
    def _validate_categories(values):
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() or len(v.strip()) > 150 for v in values):
            raise ValueError('Kategorie musí mít název o délce 1–150 znaků.')
        values = [v.strip() for v in values]
        if len({v.casefold() for v in values}) != len(values):
            raise ValueError('Kategorie s tímto názvem již existuje.')
        return values

    def _write_categories(self, values):
        temporary = self._categories_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self._categories_path)

    def save_categories(self, values):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Kategorie nelze měnit během běhu.'}
            try:
                values = self._validate_categories(values)
                self._write_categories(values)
                self._categories = values
                self._categories_error = ''
                return {'ok': True, 'categories': list(values)}
            except (ValueError, OSError) as exc:
                return self._error(exc)

    def _public_settings(self):
        result = {key: getattr(self._settings, key) for key in
                  ('host', 'port', 'database', 'user', 'tls', 'ca_file')}
        result['has_password'] = bool(self._settings.password)
        return result

    def _error(self, exc):
        text = str(exc)
        if self._settings.password:
            text = text.replace(self._settings.password, '[skryto]')
        return {'ok': False, 'message': text}

    def _busy(self):
        return self._running or self._db_busy or self._closing

    def bootstrap(self):
        with self._lock:
            return {'ok': True, 'categories': list(self._categories), 'categories_error': self._categories_error, 'folder': self._folder,
                    'settings': self._public_settings(), 'settings_error': self._settings_error,
                    'running': self._running, 'groups': self._groups}

    def poll_events(self):
        events = []
        for _ in range(150):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def _emit(self, event):
        with self._lock:
            if event['type'] == 'manual':
                self._manual = bool(event['active'])
        self._events.put(event)

    def _config(self, data):
        if not isinstance(data, dict):
            raise ValueError('Vyberte alespoň jednu kategorii.')
        categories = data.get('categories', [data.get('query')])
        categories = self._validate_categories(categories)
        if not categories or any(v not in self._categories for v in categories):
            raise ValueError('Vyberte alespoň jednu kategorii ze seznamu.')
        if data.get('output_mode') not in ('files', 'mysql'):
            raise ValueError('Vyberte způsob ukládání kontaktů.')
        if type(data.get('skip_existing')) is not bool:
            raise ValueError('Neplatné nastavení kontroly duplicit.')
        save_best_email = data.get('save_best_email', True)
        if type(save_best_email) is not bool:
            raise ValueError('Neplatné nastavení způsobu ukládání e-mailů.')
        try:
            group = data.get('group_id')
            group_id = None if group in ('', None) else int(str(group))
            numbers = {key: int(str(data.get(key, default))) for key, default in
                       [('start_page', 1), ('max_pages', 20), ('workers', 6)]}
            numbers['delay'] = float(str(data.get('delay', 2)).replace(',', '.'))
        except (ValueError, TypeError):
            raise ValueError('Počty stránek a webů musí být celá čísla. Prodleva může být desetinná.') from None
        if data['output_mode'] == 'mysql':
            if self._groups is None:
                raise ValueError('Nejprve připojte databázi a načtěte skupiny EmailApp.')
            if group_id is not None and group_id not in {g[0] for g in self._groups}:
                raise ValueError('Skupina již neexistuje. Obnovte seznam skupin.')
        else:
            group_id = None
        if data['output_mode'] == 'mysql' or data['skip_existing']:
            self._settings.validate()
        config = Config(query=categories[0], categories=tuple(categories) if len(categories) > 1 else (), output_mode=data['output_mode'],
                        skip_existing=data['skip_existing'], save_best_email=save_best_email, group_id=group_id,
                        wlw_mode=data.get('wlw_mode', 'browser'), portal=data.get('portal', 'wlw'),
                        browser_channel=data.get('browser_channel', 'chromium'), **numbers)
        config.validate()
        return config

    def _start_run(self, data, *, finish_now=False):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Již probíhá sběr nebo připojování databáze.'}
            try:
                config = self._config(data)
                folder = str(data.get('folder', '')).strip()
                if not folder:
                    raise ValueError('Vyberte složku pro výsledky a pokračování běhu.')
                self._folder = str(Path(folder).resolve())
            except (ValueError, OSError) as exc:
                return self._error(exc)
            self._stop.clear()
            self._continue.clear()
            self._finish.clear()
            if finish_now:
                self._finish.set()
            self._discard_requested = False
            self._manual = False
            self._running = True
            settings, folder = self._settings, self._folder
            def work():
                try:
                    self._pipeline_factory(config, Path(folder), self._emit, self._stop,
                        continue_event=self._continue, mysql_settings=settings,
                        finish_event=self._finish).run()
                except Exception as exc:
                    self._emit({'type': 'fatal', 'message': self._error(exc)['message']})
                finally:
                    if self._discard_requested:
                        run_folder = Path(folder).resolve()
                        results_root = (self._base / 'vysledky').resolve()
                        if results_root in run_folder.parents and run_folder != results_root:
                            try:
                                shutil.rmtree(run_folder)
                                self._events.put({'type': 'discarded', 'folder': str(run_folder)})
                            except OSError as exc:
                                self._events.put({'type': 'fatal', 'message': f'Běh se nepodařilo zahodit: {exc}'})
                        else:
                            self._events.put({'type': 'fatal', 'message': 'Z bezpečnostních důvodů lze zahodit pouze běh ve složce vysledky.'})
                    with self._lock:
                        self._running = self._manual = False
                        self._events.put({'type': 'idle'})
            self._worker = threading.Thread(target=work, name='wlw-pipeline', daemon=False)
            self._worker.start()
            return {'ok': True, 'folder': folder}

    def start_run(self, data):
        return self._start_run(data)

    def stop_run(self):
        with self._lock:
            self._stop.set()
            self._manual = False
            return {'ok': True}

    def finish_run(self, data=None):
        with self._lock:
            if self._running:
                self._finish.set()
                self._manual = False
                return {'ok': True, 'folder': self._folder}
        return self._start_run(data or {}, finish_now=True)

    def discard_run(self):
        with self._lock:
            if not self._running:
                return {'ok': False, 'message': 'Sběr již neběží.'}
            self._discard_requested = True
            self._stop.set()
            self._manual = False
            return {'ok': True}

    def discard_saved_run(self, folder):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Běh se ještě ukončuje. Vyčkejte prosím.'}
            run_folder = Path(folder).resolve()
            results_root = (self._base / 'vysledky').resolve()
            if results_root not in run_folder.parents or run_folder == results_root:
                return {'ok': False, 'message': 'Z bezpečnostních důvodů lze zrušit pouze běh ve složce vysledky.'}
            if not (run_folder / 'stav.sqlite3').is_file():
                return {'ok': False, 'message': 'Tato složka neobsahuje uložený běh ke zrušení.'}
            try:
                shutil.rmtree(run_folder)
            except OSError as exc:
                return {'ok': False, 'message': f'Běh se nepodařilo zrušit: {exc}'}
            self._events.put({'type': 'discarded', 'folder': str(run_folder)})
            return {'ok': True}

    def confirm_verification(self):
        with self._lock:
            if not self._running or not self._manual or self._stop.is_set():
                return {'ok': False, 'message': 'Běh nyní nečeká na ruční ověření.'}
            self._continue.set()
            return {'ok': True}

    def settings_password(self):
        with self._lock:
            return {'ok': True, 'password': self._settings.password}

    def save_settings(self, values):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Nastavení nelze měnit během běhu.'}
            try:
                if not isinstance(values, dict) or type(values.get('tls')) is not bool:
                    raise ValueError('Neplatné nastavení připojení.')
                kwargs = {key: str(values.get(key, '')).strip() for key in
                          ('host', 'database', 'user', 'ca_file')}
                settings = replace(self._settings, **kwargs, port=int(str(values.get('port', 3306))),
                                   tls=values['tls'], password=values.get('password') or self._settings.password)
                settings.validate()
                settings.save_local(config_path('mysql.local.json', self._base))
                self._settings = settings
                self._groups = None
                self._settings_error = ''
                return {'ok': True, 'settings': self._public_settings()}
            except (ValueError, TypeError, OSError):
                return {'ok': False, 'message': 'Ověřte server, databázi, uživatele, port a heslo. Zkontrolujte možnost uložit nastavení.'}

    def connect_database(self):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Vyčkejte na dokončení probíhající operace.'}
            try:
                self._settings.validate()
            except ValueError as exc:
                return self._error(exc)
            self._db_busy = True
            settings = self._settings
            def work():
                contacts = None
                event = None
                try:
                    contacts = self._contacts_factory(settings)
                    groups = contacts.groups()
                    with self._lock:
                        self._groups = groups
                    event = {'type': 'groups', 'groups': groups}
                except Exception as exc:
                    with self._lock:
                        self._groups = None
                    event = {'type': 'groups_error', 'message': self._error(exc)['message']}
                finally:
                    if contacts is not None:
                        contacts.close()
                    with self._lock:
                        self._db_busy = False
                        if event:
                            self._events.put(event)
            self._worker = threading.Thread(target=work, name='wlw-groups', daemon=False)
            self._worker.start()
            return {'ok': True}

    def choose_folder(self):
        with self._lock:
            if self._busy() or self._window is None:
                return {'ok': False, 'message': 'Složku nyní nelze změnit.'}
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return {'ok': True, 'folder': str(paths[0]) if paths else None}

    def new_folder(self):
        with self._lock:
            if self._busy():
                return {'ok': False, 'message': 'Složku nelze měnit během běhu.'}
            self._folder = self._new_folder()
            return {'ok': True, 'folder': self._folder}

    def folder_info(self, folder):
        try:
            if not folder:
                return {'ok': True, 'resume': False, 'completed': False, 'status': ''}
            folder_path = Path(folder).resolve()
            status = ''
            portal = 'wlw'
            summary_path = folder_path / 'souhrn.json'
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding='utf-8'))
                status = str(summary.get('status', ''))
                portal = summary.get('portal', 'wlw')
            has_state = (folder_path / 'stav.sqlite3').is_file()
            completed = status in ('DONE', 'PARTIAL')
            resume = has_state and not completed
            return {'ok': True, 'resume': resume, 'completed': completed, 'status': status,
                    'portal': portal if has_state else None}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {'ok': True, 'resume': False, 'completed': False, 'status': ''}

    def open_folder(self, folder):
        try:
            path = Path(folder).resolve()
            if not path.is_dir():
                return {'ok': False, 'message': 'Složka vznikne po spuštění sběru.'}
            if sys.platform == 'win32':
                os.startfile(str(path))
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
            return {'ok': True}
        except (OSError, TypeError, ValueError):
            return {'ok': False, 'message': 'Složku se nepodařilo otevřít.'}

    def _on_closing(self):
        with self._lock:
            if not self._running and not self._db_busy:
                return True
            if self._closing:
                return False
            self._closing = True
            self._stop.set()
            self._events.put({'type': 'closing'})
            worker = self._worker
        def finish_close():
            if worker:
                worker.join()
            if self._window:
                self._window.destroy()
        threading.Thread(target=finish_close, name='wlw-close', daemon=True).start()
        return False
