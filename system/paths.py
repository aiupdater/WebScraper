"""Cesty nezávislé na pracovním adresáři a přesunu Python modulů."""
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def config_path(name, base=None):
    """Převezme staré lokální nastavení, pokud nová konfigurace ještě neexistuje."""
    if name not in ('mysql.local.json', 'categories.local.json', '.env'):
        raise ValueError('Neznámý konfigurační soubor.')
    root = Path(base or APP_ROOT).resolve()
    target = root / 'config' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy = root / name
    if legacy.is_file() and not target.exists():
        legacy.replace(target)
    return target
