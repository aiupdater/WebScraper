from pathlib import Path
root = Path(SPECPATH).parent
a = Analysis([str(root / 'packaging' / 'updater_entry.py')], pathex=[str(root)],
             binaries=[], datas=[], hiddenimports=[], excludes=['webview', 'playwright', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='WebScraper-Updater', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          version=str(root / 'build' / 'version-info.txt'))
