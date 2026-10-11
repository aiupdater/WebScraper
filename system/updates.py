"""Bounded public GitHub release checks; never execute manifest commands."""
import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from filelock import FileLock
from system.version import VERSION

REPOSITORY = 'aiupdater/WebScraper'
LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET_NAME = 'WebScraper-Setup.exe'
MAX_SIZE = 2 * 1024 ** 3


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Neplatná stabilní verze vydání.')
    return tuple(map(int, value.split('.')))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_asset_url(value, tag, name):
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    if value != expected:
        raise ValueError('Soubor nepatří do očekávaného GitHub vydání.')
    return value


def safe_download_url(value):
    parts = urlsplit(value)
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Aktualizace vyžaduje důvěryhodné HTTPS spojení.')
    if parts.hostname not in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com',
                              'objects.githubusercontent.com'):
        raise ValueError('Nepovolený server aktualizací.')


class Updates:
    def __init__(self, base, emit, *, client_factory=None, clock=time.time):
        self.root = Path(base) / 'updates'
        self.emit = emit
        self.clock = clock
        self.client_factory = client_factory or (lambda: httpx.Client(
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
            headers={'Accept': 'application/vnd.github+json', 'User-Agent': f'WebScraper/{VERSION}'},
            trust_env=False))
        self.lock = threading.Lock()
        self.release = None
        self.status = {'state': 'idle', 'message': 'Aktualizace zatím nebyly zkontrolovány.', 'version': VERSION}
        self.worker = None

    def snapshot(self):
        with self.lock:
            return dict(self.status)

    def _report(self, state, message, **values):
        with self.lock:
            self.status = {'state': state, 'message': message, 'version': VERSION, **values}
        self.emit({'type': 'update', **self.snapshot()})

    def _read(self, client, url, limit, sink=None, progress=None):
        for _ in range(6):
            safe_download_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers['location']))
                    continue
                if response.status_code == 404 and url == LATEST:
                    return None
                response.raise_for_status()
                output, total = bytearray(), 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ValueError('Stažený soubor překročil povolenou velikost.')
                    if sink:
                        sink.write(chunk)
                    else:
                        output.extend(chunk)
                    if progress:
                        progress(total)
                return total if sink else bytes(output)
        raise ValueError('Příliš mnoho přesměrování při stahování.')

    def _fetch_release(self, client):
        raw = self._read(client, LATEST, 1024 * 1024)
        if raw is None:
            return None
        release = json.loads(raw)
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
            return None
        tag = release.get('tag_name', '')
        version = tag.removeprefix('v')
        version_tuple(version)
        if tag != 'v' + version:
            raise ValueError('Vydání musí mít označení vMAJOR.MINOR.PATCH.')
        if version_tuple(version) <= version_tuple(VERSION):
            return None
        assets = release.get('assets', [])
        if not isinstance(assets, list):
            raise ValueError('Neplatný seznam souborů vydání.')
        def asset(name):
            matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name]
            if len(matches) != 1:
                raise ValueError('Vydání nemá jednoznačný instalační balíček a manifest.')
            found = matches[0]
            validate_asset_url(found.get('browser_download_url'), tag, name)
            return found
        setup, manifest_asset = asset(ASSET_NAME), asset('update.json')
        manifest = json.loads(self._read(client, manifest_asset['browser_download_url'], 16 * 1024))
        if not isinstance(manifest, dict) or manifest.get('version') != version or manifest.get('asset') != ASSET_NAME:
            raise ValueError('Manifest neodpovídá vydání.')
        size, digest = manifest.get('size'), manifest.get('sha256')
        if type(size) is not int or not 1 <= size <= MAX_SIZE or size != setup.get('size'):
            raise ValueError('Neplatná velikost instalačního souboru.')
        if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Neplatný kontrolní součet vydání.')
        return {**manifest, 'url': setup['browser_download_url'], 'notes': str(release.get('body') or '')[:8000]}

    def _start(self, operation):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return {'ok': False, 'message': 'Aktualizace již probíhá.'}
            self.worker = threading.Thread(target=self._run, args=(operation,), name='webscraper-update', daemon=True)
            self.worker.start()
        return {'ok': True}

    def _run(self, operation):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with FileLock(str(self.root / '.download.lock'), timeout=0):
                operation()
        except Exception:
            # Do not surface URLs, server payloads, local secrets or credentials.
            self._report('error', 'Aktualizaci nelze dokončit. Ověřte internet a volné místo, potom akci opakujte.')

    def check(self, automatic=False):
        if automatic:
            try:
                last = json.loads((self.root / 'checked.json').read_text(encoding='utf-8'))['at']
                if self.clock() - float(last) < 86400:
                    return {'ok': True, 'skipped': True}
            except (OSError, ValueError, TypeError, KeyError):
                pass
        def work():
            atomic_json(self.root / 'checked.json', {'at': self.clock()})
            self._report('checking', 'Kontroluji nové vydání…')
            with self.client_factory() as client:
                self.release = self._fetch_release(client)
            if self.release:
                self._report('available', f"Je dostupná verze {self.release['version']}.",
                             available_version=self.release['version'], notes=self.release['notes'])
            else:
                self._report('current', 'Používáte nejnovější dostupnou stabilní verzi.')
        return self._start(work)

    def download(self):
        if not self.release:
            return {'ok': False, 'message': 'Nejprve zkontrolujte aktualizace.'}
        release = dict(self.release)
        def work():
            folder = self.root / release['version']
            folder.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(folder).free < release['size'] * 2 + 100 * 1024 ** 2:
                raise OSError('Nedostatek místa.')
            temporary = folder / (ASSET_NAME + '.part')
            try:
                self._report('downloading', 'Stahuji aktualizaci…', progress=0)
                last_progress = -1
                def progress(count):
                    nonlocal last_progress
                    percent = min(100, count * 100 // release['size'])
                    if percent != last_progress:
                        last_progress = percent
                        self._report('downloading', f'Stahuji aktualizaci… {percent} %', progress=percent)
                with self.client_factory() as client, temporary.open('wb') as stream:
                    size = self._read(client, release['url'], release['size'], stream, progress)
                if size != release['size'] or file_digest(temporary) != release['sha256']:
                    raise ValueError('Poškozený instalační soubor.')
                temporary.replace(folder / ASSET_NAME)
                atomic_json(folder / 'verified.json', {k: release[k] for k in ('version', 'size', 'sha256', 'asset')})
                self._report('ready', 'Aktualizace je ověřená. Instalace zavře aplikaci a zachová vaše data.',
                             available_version=release['version'])
            finally:
                temporary.unlink(missing_ok=True)
        return self._start(work)

    def verified_installer(self):
        if self.snapshot()['state'] != 'ready' or not self.release:
            raise ValueError('Aktualizace ještě není připravená.')
        release = self.release
        installer = self.root / release['version'] / ASSET_NAME
        if installer.stat().st_size != release['size'] or file_digest(installer) != release['sha256']:
            raise ValueError('Instalační soubor neprošel opakovanou kontrolou.')
        return installer
