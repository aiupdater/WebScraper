"""Frozen desktop entry; source CLI remains system.run_all."""
import logging
import sys
from system.paths import configure_bundled_browser, data_root

configure_bundled_browser()
logs = data_root() / 'logs'
logs.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(logs / 'desktop.log'), level=logging.WARNING,
                    format='%(asctime)s %(levelname)s %(message)s')
from system.app import App

if len(sys.argv) == 3 and sys.argv[1] == '--diagnostic-report':
    from system.package_diagnostics import run
    raise SystemExit(run(sys.argv[2]))
raise SystemExit(App().mainloop())
