"""Install/reinstall/uninstall in a scratch directory on the current Windows host.

Refuses to run if this user already has WebScraper installed or its shortcut.
This is not a clean-Windows or cross-version upgrade certification.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import winreg
import time
import ctypes
import hashlib
import psutil
from filelock import FileLock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from system.version import VERSION

UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A5BEE571-741E-4A07-BF23-236EC693A026}_is1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installer', required=True)
    args = parser.parse_args()
    installer = Path(args.installer).resolve()
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view):
                raise RuntimeError('Test odmítnut: aktuální uživatel již má instalovaný WebScraper.')
        except FileNotFoundError:
            pass
    shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/WebScraper.lnk'
    if shortcut.exists():
        raise RuntimeError('Test odmítnut: existuje uživatelský zástupce WebScraperu.')
    scratch = Path(tempfile.mkdtemp(prefix='WebScraper installer česky ')).resolve()
    program = scratch / 'Program aplikace'
    local = scratch / 'LocalData'
    data = local / 'WebScraper'
    (data / 'config').mkdir(parents=True)
    (data / 'vysledky').mkdir()
    (data / 'config/categories.local.json').write_text('["Test importu"]', encoding='utf-8')
    sentinel = data / 'vysledky/preserved.txt'
    sentinel.write_text('installer-test-only', encoding='utf-8')
    env = dict(os.environ, LOCALAPPDATA=str(local))
    for name in list(env):
        if name.startswith('MYSQL') or name in ('PYTHONPATH','PYTHONHOME','PLAYWRIGHT_BROWSERS_PATH'):
            env.pop(name)
    finished = False
    checks = []
    try:
        command = [str(installer), '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
                   '/DIR=' + str(program), '/LOG=' + str(scratch / 'install.log')]
        subprocess.run(command, env=env, check=True, timeout=180)
        assert (program / 'WebScraper.exe').is_file()
        assert shortcut.is_file()
        checks.extend(['silent user installation', 'Start menu shortcut'])
        report = scratch / 'installed-report.json'
        subprocess.run([str(program / 'WebScraper.exe'), '--diagnostic-report', str(report)],
                       env=env, cwd=scratch, check=True, timeout=180)
        diagnostics = json.loads(report.read_text(encoding='utf-8'))
        assert diagnostics['ok'] and diagnostics['version'] == VERSION, diagnostics
        checks.extend(diagnostics['checks'])
        # Exercise the actual frozen updater outside the installation directory.
        folder = data / 'updates' / VERSION
        folder.mkdir(parents=True)
        cached_setup = folder / 'WebScraper-Setup.exe'
        shutil.copy2(installer, cached_setup)
        cached_helper = folder / 'WebScraper-Updater.exe'
        shutil.copy2(program / 'WebScraper-Updater.exe', cached_helper)
        digest = hashlib.sha256(cached_setup.read_bytes()).hexdigest()
        (folder / 'verified.json').write_text(json.dumps({'version':VERSION,'asset':'WebScraper-Setup.exe',
            'size':cached_setup.stat().st_size,'sha256':digest}),encoding='utf-8')
        parent = subprocess.Popen([sys.executable,'-c','import time; time.sleep(2)'])
        request = {'version':VERSION,'token':'installer-smoke-only','executable':str(program/'WebScraper.exe'),
                   'parent_pid':parent.pid,'parent_created':psutil.Process(parent.pid).create_time()}
        (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
        with FileLock(str(data/'.instance.lock')):
            helper = subprocess.Popen([str(cached_helper),'--request',str(folder/'request.json')],env=env,cwd=scratch)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline and not (folder/'helper-ready.json').exists():
                if helper.poll() is not None: raise AssertionError('Updater failed before handshake')
                time.sleep(.1)
            assert (folder/'helper-ready.json').exists(), 'Updater handshake timed out'
        parent.wait(timeout=10)
        assert helper.wait(timeout=180)==0, 'Actual updater failed'
        assert json.loads((folder/'result.json').read_text(encoding='utf-8'))['ok']
        deadline=time.monotonic()+30
        restarted=[]
        while time.monotonic()<deadline and not restarted:
            for process in psutil.process_iter(['exe']):
                try:
                    if process.info['exe'] and Path(process.info['exe']).resolve()==(program/'WebScraper.exe').resolve():
                        restarted.append(process)
                except (psutil.NoSuchProcess,psutil.AccessDenied): pass
            time.sleep(.1)
        assert restarted,'Updater did not restart WebScraper'
        # Close only the newly launched test application, before uninstalling.
        for process in restarted:
            @ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
            def close_window(hwnd,_):
                pid=ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),ctypes.byref(pid))
                if pid.value==process.pid:
                    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd),0x0010,0,0)
                return True
            deadline=time.monotonic()+30
            while process.is_running() and time.monotonic()<deadline:
                ctypes.windll.user32.EnumWindows(close_window,0)
                time.sleep(.2)
            process.wait(timeout=10)
        checks.append('actual frozen updater handshake/install/restart')
        assert sentinel.read_text(encoding='utf-8') == 'installer-test-only'
        assert json.loads((data / 'config/categories.local.json').read_text(encoding='utf-8')) == ['Test importu']
        checks.append('same-version reinstall preserves settings/results')
        subprocess.run([str(program / 'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],
                       env=env, check=True, timeout=180)
        assert not (program / 'WebScraper.exe').exists()
        assert not shortcut.exists()
        assert sentinel.is_file()
        checks.append('uninstall preserves user data')
        artifact = ROOT / 'tests/artifacts/installer-smoke.json'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({'ok':True,'version':VERSION,'checks':checks,
             'scope':'current host only; no clean OS or cross-version upgrade'},ensure_ascii=False,indent=2), encoding='utf-8')
        finished = True
        print('PASS: ' + ', '.join(checks))
    finally:
        if finished:
            # Only the freshly created test directory, after successful uninstall.
            if scratch.parent != Path(tempfile.gettempdir()).resolve() or not scratch.name.startswith('WebScraper installer '):
                raise RuntimeError('Unexpected test cleanup path')
            shutil.rmtree(scratch)
        else:
            print('Test evidence preserved:', scratch)


if __name__ == '__main__':
    main()
