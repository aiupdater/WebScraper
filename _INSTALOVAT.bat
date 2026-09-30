@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo WebScraper - instalace a aktualizace prostredi
if exist ".venv\Scripts\python.exe" goto install
py -3 --version >nul 2>&1
if errorlevel 1 goto fallback
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto version_error
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:fallback
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto version_error
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r config\requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import webview, httpx, bs4, tldextract"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto browser_failed
echo.
echo Hotovo. Spustte _SPUSTIT.bat.
echo Rozhrani vyuziva Microsoft Edge WebView2 Runtime.
echo Pokud chybi: https://developer.microsoft.com/microsoft-edge/webview2/
pause
exit /b 0
:version_error
echo Nainstalujte Python 3.11 nebo novejsi vcetne Python Launcheru.
pause
exit /b 1
:failed
echo Instalace selhala. Podrobnosti jsou vyse. Overte internet a instalaci Pythonu.
pause
exit /b 1

:browser_failed
echo Prohlizec Chromium se nepodarilo stahnout. Overte internet a spustte instalaci znovu.
echo Alternativne muzete v aplikaci vybrat jiz nainstalovany Microsoft Edge nebo Google Chrome.
pause
exit /b 1
