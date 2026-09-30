# Python backend

Tato složka je Python balíček `system`. Z kořene aplikace jej spusťte příkazem
`.venv\Scripts\python.exe -m system.run_all`, případně přes `_SPUSTIT.bat`.
Jednotlivé moduly nespouštějte dvojklikem ani přímou cestou.

- `run_all.py` – vstupní bod desktopové aplikace a CLI.
- `app.py` – vytvoření okna WebView2 a připojení Python API.
- `desktop.py` – komunikace s rozhraním a správa běhu.
- `core.py` – sběr z WLW.de / 11880.com, zpracování kontaktů a exporty.
- `browser_fetcher.py` – prohlížeč, stránkování a čekání na ruční ověření.
- `access.py` – rozpoznání ochranných stránek a blokací.
- `mysql_contacts.py` – ukládání do EmailApp a kontrola duplicit.
- `paths.py` – společné cesty a převzetí starého nastavení z kořene.

Při aktualizaci se starý místní konfigurační soubor přesune do `config/`, pokud
tam ještě není. Existující konfigurace v `config/` má přednost a nepřepisuje se.
