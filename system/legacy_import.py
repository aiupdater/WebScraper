"""Explicit, non-destructive import of settings and saved runs."""
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

import psutil
from filelock import FileLock
from system.updates import atomic_json, file_digest


def _ordinary(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Import nepracuje se symbolickými odkazy ani zástupnými soubory. Nejprve stáhněte data z OneDrive.')
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise ValueError('Import obsahuje nepodporovaný soubor.')


def ensure_closed(source):
    source = Path(source).resolve()
    prefix = str(source).casefold()
    for process in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        if process.pid == os.getpid():
            continue
        try:
            name = (process.info['name'] or '').lower()
            if not any(item in name for item in ('python', 'webscraper', 'chrome', 'chromium', 'msedge')):
                continue
            exe = process.info.get('exe') or ''
            args = ' '.join(process.info.get('cmdline') or []).casefold()
            cwd = process.cwd().casefold()
            if (exe and Path(exe).resolve().is_relative_to(source)) or cwd == prefix or prefix in args:
                raise ValueError('Zavřete původní WebScraper i jeho prohlížeč a import opakujte.')
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied:
            # Unknown relevant process ownership is not evidence of a closed profile.
            raise ValueError('Nelze ověřit zavření prohlížečů. Zavřete je a import opakujte.') from None


def inventory(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_dir() or source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError('Vyberte samostatnou složku původní aplikace.')
    if not (source / 'system').is_dir() or not (source / 'ui').is_dir():
        raise ValueError('Složka neobsahuje původní WebScraper (system a ui).')
    _ordinary(source)
    if (source / 'config').exists():
        _ordinary(source / 'config')
    entries = []
    for name in ('mysql.local.json', 'categories.local.json', '.env'):
        old = source / 'config' / name
        legacy = source / name
        if old.exists() and legacy.exists():
            raise ValueError(f'Původní složka obsahuje dvě verze nastavení {name}; sjednoťte je před importem.')
        selected = old if old.exists() else legacy
        if selected.exists():
            if name.endswith('.json'):
                value = json.loads(selected.read_text(encoding='utf-8-sig'))
                if name == 'categories.local.json' and (not isinstance(value, list) or
                        any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 150 for item in value) or
                        len({item.casefold().strip() for item in value}) != len(value)):
                    raise ValueError('Původní seznam kategorií není platný.')
                if name == 'mysql.local.json' and not isinstance(value, dict):
                    raise ValueError('Původní nastavení MySQL není platné.')
            entries.append((selected, Path('config') / name))
    results = source / 'vysledky'
    if results.exists():
        _ordinary(results)
        entries.extend((item, Path('vysledky') / item.name) for item in sorted(results.iterdir()))
    if not entries:
        raise ValueError('Ve složce nebylo nalezeno nastavení ani uložené běhy.')
    files = []
    for item, relative in entries:
        _ordinary(item)
        if item.is_dir():
            for directory, directories, names in os.walk(item, followlinks=False):
                for name in directories + names:
                    _ordinary(Path(directory) / name)
                files.extend((Path(directory) / name, relative / (Path(directory) / name).relative_to(item)) for name in names)
        else:
            files.append((item, relative))
    sizes = [(relative.as_posix(), path.stat().st_size, path.stat().st_mtime_ns) for path, relative in files]
    fingerprint = hashlib.sha256(json.dumps(sizes, sort_keys=True).encode()).hexdigest()
    return source, entries, files, fingerprint


def inspect_import(source, target):
    source, entries, files, fingerprint = inventory(source, target)
    ensure_closed(source)
    for name in ('config', 'vysledky'):
        if (Path(target) / name).exists():
            _ordinary(Path(target) / name)
    conflicts = [relative.as_posix() for _, relative in entries if (Path(target) / relative).exists()]
    return {'source': str(source), 'items': [rel.as_posix() for _, rel in entries],
            'files': len(files), 'size': sum(path.stat().st_size for path, _ in files),
            'conflicts': conflicts, 'fingerprint': fingerprint}


def execute_import(source, target, expected_fingerprint):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with FileLock(str(Path(source).resolve() / '.instance.lock'), timeout=0):
        preview = inspect_import(source, target)
        if preview['conflicts']:
            raise ValueError('Import nic nepřepsal. Konflikty: ' + ', '.join(preview['conflicts']))
        if preview['fingerprint'] != expected_fingerprint:
            raise ValueError('Původní data se změnila. Zobrazte nový přehled importu.')
        _, entries, files, _ = inventory(source, target)
        required = preview['size'] * 2 + 100 * 1024 ** 2
        if shutil.disk_usage(target).free < required:
            raise OSError('Pro bezpečný import není dostatek volného místa.')
        with tempfile.TemporaryDirectory(prefix='.import-', dir=target) as temporary:
            stage = Path(temporary)
            before = {rel.as_posix(): file_digest(path) for path, rel in files}
            for path, rel in entries:
                destination = stage / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                if path.is_dir():
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)
            ensure_closed(source)
            after = inspect_import(source, target)
            if after['fingerprint'] != expected_fingerprint or after['conflicts']:
                raise ValueError('Data nebo cílová složka se během importu změnily. Import nebyl dokončen.')
            for path, rel in files:
                if file_digest(path) != before[rel.as_posix()] or file_digest(stage / rel) != before[rel.as_posix()]:
                    raise ValueError('Původní data se během kopírování změnila.')
            journal = target / 'logs' / 'import.json'
            published = []
            atomic_json(journal, {'state': 'incomplete', 'items': preview['items'], 'published': published})
            try:
                for _, rel in entries:
                    destination = target / rel
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # Windows rename never replaces an existing destination.
                    if destination.exists():
                        raise ValueError('Cílová položka již existuje: ' + rel.as_posix())
                    (stage / rel).rename(destination)
                    published.append(rel.as_posix())
                    atomic_json(journal, {'state': 'incomplete', 'items': preview['items'], 'published': published})
            except Exception:
                # Keep already copied data and report incomplete import honestly.
                atomic_json(journal, {'state': 'incomplete', 'items': preview['items'], 'published': published})
                raise
            atomic_json(journal, {'state': 'complete', 'items': published})
        return preview
