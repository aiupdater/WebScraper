"""Reproducible local/CI packaging; never copy repository configuration."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from system.version import VERSION
from system.updates import ASSET_NAME, version_tuple


def run(*args, env=None):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, env=env, check=True)


def audit_bundle(folder):
    forbidden = {'mysql.local.json', 'categories.local.json', '.env', '.env.example',
                 'mysql.example.json', '_SPUSTIT_LINEONE.bat', 'stav.sqlite3', 'souhrn.json'}
    for path in folder.rglob('*'):
        if path.name in forbidden or any(part in ('lineone', 'vysledky', '.venv', 'tests', '.ui-state') for part in path.relative_to(folder).parts):
            raise RuntimeError('Soukromý nebo experimentální soubor v balíčku: ' + str(path))
    required = ['WebScraper.exe', 'WebScraper-Updater.exe', '_internal/ui/index.html']
    for name in required:
        if not (folder / name).is_file():
            raise RuntimeError('V balíčku chybí ' + name)
    if not list((folder / '_internal/browsers').glob('chromium-*/chrome-win*/chrome.exe')):
        raise RuntimeError('V balíčku chybí Chromium.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iscc')
    parser.add_argument('--bundle-only', action='store_true')
    parser.add_argument('--skip-browser-download', action='store_true')
    args = parser.parse_args()
    if not args.bundle_only and not args.iscc:
        parser.error('--iscc je potřeba pro sestavení instalátoru.')
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 11):
        parser.error('Vydání sestavujte pomocí Pythonu 3.11 x64 na Windows.')
    if sys.maxsize <= 2 ** 32:
        parser.error('Je potřeba 64bitový Python.')
    version = version_tuple(VERSION)
    (ROOT / 'build').mkdir(exist_ok=True)
    numeric = ', '.join(map(str, (*version, 0)))
    (ROOT / 'build/version-info.txt').write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers=({numeric}), prodvers=({numeric}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo([StringTable('040504B0', [StringStruct('CompanyName', 'FEBA-MONT'), StringStruct('FileDescription', 'WebScraper'), StringStruct('FileVersion', '{VERSION}'), StringStruct('ProductName', 'WebScraper'), StringStruct('ProductVersion', '{VERSION}')])]), VarFileInfo([VarStruct('Translation', [1029, 1200])])])",
        encoding='utf-8')
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(ROOT / 'build/browsers'))
    if not args.skip_browser_download:
        run(sys.executable, '-m', 'playwright', 'install', 'chromium', env=env)
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', 'packaging/WebScraper.spec', env=env)
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', 'packaging/WebScraper-Updater.spec', env=env)
    shutil.copy2(ROOT / 'dist/WebScraper-Updater.exe', ROOT / 'dist/WebScraper/WebScraper-Updater.exe')
    audit_bundle(ROOT / 'dist/WebScraper')
    if args.bundle_only:
        print('BUNDLE OK:', ROOT / 'dist/WebScraper')
        return
    run(args.iscc, '/DAppVersion=' + VERSION, 'packaging/installer.iss')
    installer = ROOT / 'release' / ASSET_NAME
    digest = hashlib.sha256()
    with installer.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    manifest = {'version': VERSION, 'asset': ASSET_NAME, 'size': installer.stat().st_size, 'sha256': digest.hexdigest()}
    (ROOT / 'release/update.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(ROOT / 'packaging/release-notes.md', ROOT / 'release/release-notes.md')
    print('BUILD OK:', installer)


if __name__ == '__main__':
    main()
