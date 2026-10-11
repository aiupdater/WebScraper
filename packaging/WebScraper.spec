from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = [(str(root / 'ui' / name), 'ui') for name in ('index.html', 'app.js', 'app.css', 'theme.js')]
datas += [(str(root / 'ui' / 'assets'), 'ui/assets')]
datas += [(str(folder), 'browsers/' + folder.name) for folder in (root / 'build/browsers').iterdir()
          if folder.is_dir() and folder.name.startswith(('chromium-', 'ffmpeg-', 'winldd-'))]
datas += collect_data_files('webview')
datas += collect_data_files('tldextract')
a = Analysis([str(root / 'packaging' / 'desktop_entry.py')], pathex=[str(root)],
             binaries=[], datas=datas, hiddenimports=
             ['clr', 'pythonnet', 'webview.platforms.winforms', 'webview.platforms.edgechromium', 'windows_toasts'],
             excludes=['pytest', 'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='WebScraper', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          version=str(root / 'build' / 'version-info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='WebScraper')
