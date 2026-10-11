"""Cesty nezávislé na pracovním adresáři a přesunu Python modulů."""
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def data_root(base=None):
    """Explicit bases and source checkouts retain their historical layout."""
    if base is not None:
        return Path(base).resolve()
    if getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('Nelze najít uživatelskou složku LOCALAPPDATA.')
        return Path(local).resolve() / 'WebScraper'
    return APP_ROOT


def configure_bundled_browser():
    if getattr(sys, 'frozen', False):
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(APP_ROOT / 'browsers')


def config_path(name, base=None):
    """Převezme staré lokální nastavení, pokud nová konfigurace ještě neexistuje."""
    if name not in ('mysql.local.json', 'categories.local.json', '.env'):
        raise ValueError('Neznámý konfigurační soubor.')
    root = data_root(base)
    target = root / 'config' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy = root / name
    if legacy.is_file() and not target.exists():
        legacy.replace(target)
    return target
