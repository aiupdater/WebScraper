"""Per-data-directory process lock and Windows installer mutex."""
import ctypes
import sys
from filelock import FileLock, Timeout
from system.paths import data_root

APP_MUTEX = r'Local\WebScraper.Desktop'


class Instance:
    def __init__(self, base=None):
        self.base = data_root(base)
        self.lock = FileLock(str(self.base / '.instance.lock'))
        self.handle = None

    def __enter__(self):
        self.base.mkdir(parents=True, exist_ok=True)
        # An updater holds this lock until the installer has completed.
        with FileLock(str(self.base / '.update.lock'), timeout=0):
            self.lock.acquire(timeout=0)
        if sys.platform == 'win32':
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.restype = ctypes.c_void_p
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            self.handle = kernel.CreateMutexW(None, False, APP_MUTEX)
            if not self.handle:
                self.lock.release()
                raise OSError('Nelze vytvořit zámek aplikace.')
        return self

    def __exit__(self, *args):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
        self.lock.release()
