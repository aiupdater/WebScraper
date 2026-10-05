"""Only manipulate HWNDs belonging to the current persistent browser profile."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import threading


class BrowserWindowController:
    def __init__(self, profile, *, processes=None, native=None):
        import psutil
        self.processes = processes or psutil.process_iter
        self.native = native or WindowsNative()
        self.profile = os.path.normcase(str(Path(profile).resolve()))
        self.owner = threading.get_ident()
        self.before = set(self.identities())
        self.hwnd = self.identity = None
        self.normal = None

    def identities(self):
        import psutil
        result = {}
        for process in self.processes(['pid', 'name', 'cmdline', 'create_time', 'ppid']):
            try:
                info = process.info
                if info['name'].lower() in ('chrome.exe', 'msedge.exe', 'chromium.exe'):
                    result[(info['pid'], info['create_time'])] = info
            except (psutil.Error, OSError, KeyError, TypeError):
                continue
        return result

    def owned(self):
        processes = self.identities()
        roots = set()
        for identity, info in processes.items():
            args = info.get('cmdline') or []
            profiles = [arg.split('=', 1)[1] for arg in args if arg.startswith('--user-data-dir=')]
            if '--user-data-dir' in args:
                index = args.index('--user-data-dir') + 1
                profiles += args[index:index + 1]
            if identity not in self.before and any(os.path.normcase(str(Path(p.strip('"')).resolve())) == self.profile for p in profiles):
                roots.add(identity)
        # Only a profile-bound root may introduce descendants.
        owned = set(roots)
        while True:
            pids = {i[0] for i in owned}
            more = {i for i, p in processes.items() if i not in self.before and p['ppid'] in pids
                    and any(parent[0] == p['ppid'] and parent[1] <= i[1] for parent in owned)}
            if more <= owned:
                return owned
            owned |= more

    def verify(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Ovládání prohlížeče patří vláknu sběru.')
        if not self.hwnd or self.identity not in self.owned() or self.native.pid(self.hwnd) != self.identity[0]:
            raise RuntimeError('Okno sběrného prohlížeče nelze bezpečně identifikovat.')

    def find(self):
        owned = self.owned()
        candidates = [(hwnd, identity) for hwnd, pid in self.native.windows()
                      for identity in owned if identity[0] == pid]
        if len(candidates) != 1:
            return False
        self.hwnd, self.identity = candidates[0]
        self.verify()
        return True

    def visible(self):
        self.verify()
        return self.native.visible(self.hwnd) and not self.native.minimized(self.hwnd)

    def hide(self):
        self.verify()
        if self.visible():
            rect = self.native.rect(self.hwnd)
            if rect[0] > -10000 and rect[1] > -10000:
                self.normal = rect
        self.verify()
        self.native.show(self.hwnd, 0)

    def show(self):
        self.verify()
        self.native.place(self.hwnd, self.normal)
        self.verify()
        self.native.show(self.hwnd, 9)
        self.verify()
        self.native.activate(self.hwnd)


class WindowsNative:
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Ovládání oken vyžaduje Windows.')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        for name in ('IsWindowVisible', 'IsIconic', 'SetForegroundWindow'):
            getattr(self.user, name).argtypes = [wintypes.HWND]
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        self.user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.user.MonitorFromWindow.restype = wintypes.HANDLE
        self.user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.user.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        self.user.GetWindow.restype = wintypes.HWND
        self.user.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.last_dpi = None

    def pid(self, hwnd):
        value = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(value))
        return value.value

    def windows(self):
        result = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _):
            name = ctypes.create_unicode_buffer(256)
            self.user.GetClassNameW(hwnd, name, len(name))
            if name.value == 'Chrome_WidgetWin_1' and not self.user.GetWindow(hwnd, 4):
                result.append((hwnd, self.pid(hwnd)))
            return True
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.EnumWindows(callback_type(collect), 0)
        return result

    def visible(self, hwnd):
        return bool(self.user.IsWindowVisible(hwnd))

    def minimized(self, hwnd):
        return bool(self.user.IsIconic(hwnd))

    def rect(self, hwnd):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.last_dpi = self.user.GetDpiForWindow(hwnd) or 96
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    def place(self, hwnd, normal):
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = self.user.MonitorFromWindow(hwnd, 2)
        if not self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        area = info.work
        x, y, width, height = normal or (area.left + 40, area.top + 40, 1280, 900)
        dpi = self.user.GetDpiForWindow(hwnd) or 96
        if normal and self.last_dpi:
            width, height = round(width * dpi / self.last_dpi), round(height * dpi / self.last_dpi)
        self.last_dpi = dpi
        # Physical Win32 coordinates are recalculated on every restore, including DPI changes.
        width, height = min(width, area.right - area.left), min(height, area.bottom - area.top)
        x, y = max(area.left, min(x, area.right - width)), max(area.top, min(y, area.bottom - height))
        if not self.user.SetWindowPos(hwnd, None, x, y, width, height, 0x14):
            raise ctypes.WinError(ctypes.get_last_error())

    def show(self, hwnd, command):
        self.user.ShowWindow(hwnd, command)

    def activate(self, hwnd):
        self.user.SetForegroundWindow(hwnd)


def recovery_bounds():
    """Primary work area can be queried without selecting or manipulating a window."""
    area = wintypes.RECT()
    user = ctypes.WinDLL('user32', use_last_error=True)
    if not user.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return dict(left=area.left, top=area.top, width=min(1000, area.right-area.left), height=min(700, area.bottom-area.top))
