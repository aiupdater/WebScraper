"""Bez parametrů otevře GUI. Parametry umožní automatizované spuštění."""
import argparse
import json
import signal
import sys
import threading
from pathlib import Path
from system.core import Config, Pipeline
from system.mysql_contacts import MySQLSettings


def main():
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == '--lineone'):
        from system.app import App
        return App().mainloop()
    parser = argparse.ArgumentParser(description='WebScraper - profily / weby / e-maily')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--query', help='Hledané odvětví')
    source.add_argument('--input', help='TXT: jedna absolutní URL na řádek')
    parser.add_argument('--kind', choices=['profiles', 'websites'], default='profiles')
    parser.add_argument('--output', required=True, help='Výstupní složka; stejná složka = pokračování')
    parser.add_argument('--start-page', type=int, default=1)
    parser.add_argument('--max-pages', type=int, default=20)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--delay', type=float, default=1.0)
    parser.add_argument('--ignore-robots', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--wlw-mode', choices=['browser', 'http'], default='browser')
    parser.add_argument('--portal', choices=['wlw', '11880'], default='wlw', help='Portál databáze firem')
    parser.add_argument('--browser', choices=['chromium', 'msedge', 'chrome'], default='chromium')
    parser.add_argument('--manual-timeout', type=float, default=600, help='Sekundy čekání na ruční ověření')
    parser.add_argument('--save-to', choices=['files', 'mysql'], default='files')
    parser.add_argument('--skip-existing', action='store_true', help='Přeskočit adresy ze všech skupin v MySQL')
    parser.add_argument('--group-id', type=int, help='ID skupiny pro nové kontakty v MySQL; bez volby NULL')
    args = parser.parse_args()
    config = Config(output_mode=args.save_to, skip_existing=args.skip_existing, group_id=args.group_id, query=args.query or '', input_file=args.input or '', input_kind=args.kind,
                    start_page=args.start_page, max_pages=args.max_pages, workers=args.workers, delay=args.delay,
                    portal=args.portal, wlw_mode=args.wlw_mode, browser_channel=args.browser, manual_timeout=args.manual_timeout)
    stop = threading.Event()
    continue_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    def emit(event):
        if event['type'] in ('log', 'stage', 'finish', 'manual'):
            print(json.dumps(event, ensure_ascii=False), flush=True)
        if event['type'] == 'manual' and event['active']:
            if not sys.stdin.isatty():
                stop.set()
                return
            def confirm():
                try:
                    input('Vyřešte CAPTCHA v otevřeném prohlížeči; pak zde stiskněte Enter.\n')
                    if not stop.is_set():
                        continue_event.set()
                except (EOFError, KeyboardInterrupt):
                    stop.set()
            threading.Thread(target=confirm, daemon=True).start()
    try:
        settings = MySQLSettings.load() if args.save_to == 'mysql' or args.skip_existing else None
        status = Pipeline(config, Path(args.output), emit, stop, continue_event=continue_event, mysql_settings=settings).run()
        return {'DONE': 0, 'PARTIAL': 2, 'STOPPED': 130, 'FAILED': 1, 'BLOCKED': 3}[status]
    except Exception as exc:
        print(f'CHYBA: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

