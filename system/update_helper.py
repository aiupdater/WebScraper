"""A separate one-file updater, copied out of the installation before use."""
import argparse
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

from filelock import FileLock
import psutil
from system.paths import data_root
from system.updates import ASSET_NAME, atomic_json, file_digest, version_tuple


def wait_for_parent(pid, created):
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - created) < .01:
            process.wait(timeout=120)
    except psutil.NoSuchProcess:
        pass


def install_request(request_path, *, root=None, runner=subprocess.run, launcher=subprocess.Popen, waiter=wait_for_parent):
    root = data_root(root)
    updates = (root / 'updates').resolve()
    request_path = Path(request_path).resolve()
    if not request_path.is_relative_to(updates) or request_path.name != 'request.json':
        raise ValueError('Neplatný požadavek aktualizace.')
    request = json.loads(request_path.read_text(encoding='utf-8'))
    version_tuple(request['version'])
    folder = updates / request['version']
    if request_path.parent != folder:
        raise ValueError('Verze neodpovídá požadavku.')
    installer = folder / ASSET_NAME
    metadata = json.loads((folder / 'verified.json').read_text(encoding='utf-8'))
    if metadata['version'] != request['version'] or metadata['asset'] != ASSET_NAME:
        raise ValueError('Neplatná ověřená aktualizace.')
    if installer.stat().st_size != metadata['size'] or file_digest(installer) != metadata['sha256']:
        raise ValueError('Poškozený instalační soubor.')
    # Restart is derived from our installed executable, never a manifest command.
    executable = Path(request['executable']).resolve()
    if executable.name != 'WebScraper.exe' or not executable.is_file():
        raise ValueError('Neplatná cesta aplikace.')
    with FileLock(str(root / '.update.lock'), timeout=0):
        atomic_json(folder / 'helper-ready.json', {'token': request['token']})
        waiter(request['parent_pid'], request['parent_created'])
        with FileLock(str(root / '.instance.lock'), timeout=120):
            command = [str(installer), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                       '/SP-', '/DIR=' + str(executable.parent), '/LOG=' + str(folder / 'installer.log')]
            result = runner(command, check=False)
            if result.returncode != 0:
                raise RuntimeError('Instalátor skončil chybou. Původní data byla zachována.')
    atomic_json(folder / 'result.json', {'ok': True, 'version': request['version']})
    launcher([str(executable)], cwd=str(executable.parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        install_request(args.request)
        return 0
    except Exception:
        root = data_root()
        atomic_json(root / 'updates' / 'last-error.json', {'message': 'Aktualizace selhala. Spusťte aplikaci a opakujte ji, případně použijte předchozí instalátor.'})
        if sys.platform == 'win32':
            ctypes.windll.user32.MessageBoxW(None, 'Aktualizace se nezdařila. Vaše výsledky a nastavení zůstávají zachované. Spusťte WebScraper a aktualizaci opakujte.', 'WebScraper – aktualizace', 0x10)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
