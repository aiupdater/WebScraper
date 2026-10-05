"""Delete an explicitly discarded run, including read-only Chromium/OneDrive files."""
import os
from pathlib import Path
import shutil
import stat
import sys
import time


def remove_run_folder(folder, results_root):
    folder, root = Path(folder).resolve(), Path(results_root).resolve()
    if root not in folder.parents:
        raise ValueError('Lze zrušit pouze běh uvnitř složky vysledky.')

    def remove_readonly(function, path, exception):
        if not isinstance(exception, PermissionError):
            raise exception
        info = os.stat(path, follow_symlinks=False)
        if not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_READONLY:
            raise exception
        # Clear a Windows read-only attribute; never change ACL ownership/permissions.
        os.chmod(path, stat.S_IWRITE)
        function(path)

    def remove(path):
        resolved = path.resolve()
        if root not in resolved.parents or (resolved != folder and folder not in resolved.parents):
            raise ValueError('Profil směřuje mimo rušený běh.')
        for attempt in range(4):
            try:
                if sys.version_info >= (3, 12):
                    shutil.rmtree(path, onexc=remove_readonly)
                else:
                    shutil.rmtree(path, onerror=lambda function, failed, info: remove_readonly(function, failed, info[1]))
                return
            except FileNotFoundError:
                if not path.exists():
                    return
                raise
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(.15 * (attempt + 1))

    # An inaccessible browser profile must fail before saved results are removed.
    for name in ('prohlizec_chromium', 'prohlizec_msedge', 'prohlizec_chrome'):
        profile = folder / name
        if profile.is_dir():
            remove(profile)
    remove(folder)
