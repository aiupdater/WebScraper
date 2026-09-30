"""Desktop entrypoint: local web UI, existing Python scraping pipeline."""
import sys
from pathlib import Path
from system.desktop import DesktopAPI
from system.paths import APP_ROOT


class App:
    def mainloop(self):
        try:
            self._launch()
            return 0
        except Exception as exc:
            message = ('Rozhraní nelze spustit. Nejprve spusťte INSTALOVAT.bat.\n'
                       'Ve Windows je potřeba Microsoft Edge WebView2 Runtime:\n'
                       'https://developer.microsoft.com/microsoft-edge/webview2/\n\n'
                       f'Podrobnosti: {exc}')
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, 'WebScraper – spuštění', 0x10)
            elif sys.stderr is not None:
                print(message, file=sys.stderr)
            return 1

    def _launch(self):
        import webview
        base = APP_ROOT
        api = DesktopAPI(base)
        window = webview.create_window(
            'WebScraper | FEBA-MONT', str(base / 'ui' / 'index.html'), js_api=api,
            width=1320, height=850, min_size=(900, 560), background_color='#eef2f8',
            text_select=True,
        )
        api._window = window
        window.events.closing += api._on_closing
        # The server root is ui/, never the project or its database configuration.
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None,
                      http_server=True, private_mode=False, storage_path=str(base / '.ui-state'))


if __name__ == '__main__':
    App().mainloop()
