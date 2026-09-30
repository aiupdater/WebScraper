# Desktopové rozhraní FebaMont

Lokální HTML/CSS rozhraní uvnitř Python okna pomocí pywebview 6.1. Scraper, pokračování běhů, exporty a MySQL adapter zůstávají beze změny. Nejde o vzdálenou webovou aplikaci.

## Aktualizace

1. Zavřete aplikaci a aktualizujte zdroje včetně celé složky `ui/` a složky `system/`. Zachovejte vlastní výsledky a nastavení připojení.
2. Znovu spusťte `_INSTALOVAT.bat`, potom `_SPUSTIT.bat`.
3. Pokud okno hlásí chybějící WebView2, doinstalujte [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Chromium instalované pro scraper a WebView2 pro rozhraní jsou dvě odlišné součásti.

## Rozložení a ovládání

- Vlevo jsou obor firem, počet stránek, výstup a složka běhu. Další parametry jsou pod rozbalovacím pokročilým nastavením.
- Skupina se zobrazuje pouze při ukládání do EmailApp. Připojení databáze se zobrazuje při tomto výstupu nebo při zapnutí kontroly známých adres.
- Při spuštění je vybrané **EmailApp (MySQL)** a zapnuté **Přeskočit známé e-maily**. Databáze se připojí automaticky a načte skupiny. Tlačítkem připojení lze seznam obnovit. **Nastavení připojení** předvyplní uložené heslo; prázdné heslo zachová stávající. Parametry včetně hesla se ukládají do místního `config/mysql.local.json`.
- Vpravo je statistika, průběh a tabulka. Nastavení a tabulka mají vlastní posuvník; spodní výpis neodsunuje dlouhý formulář mimo okno. Minimální velikost okna je 900 × 560.
- **Ctrl+F**, hledání a filtr usnadňují práci s posledními 500 výsledky. Kliknutí na řádek otevře detail a kopírování kontaktu. Úplné výsledky zůstávají v souborech běhu.
- Po spuštění se nastavení uzamkne. Ruční ověření se zobrazí pouze při čekání na CAPTCHA. Po zastavení lze pokračovat, zpracovat dosud získaná data nebo běh ukončit a data zahodit. Nové kontakty se do MySQL zapíší až po dokončení nebo po volbě použití aktuálních dat.
- Ikona měsíce/slunce přepíná vzhled. Nastavení zobrazení umožňuje omezit animace; respektována je i systémová preference omezeného pohybu. Volby vzhledu jsou v `.ui-state/`.

## Původ vzhledu

`ui/emailapp.css` přebírá konkrétní deklarace z [EmailApp/style.css](https://github.com/aiupdater/febamont-emailapp/blob/main/style.css): barvy, pozadí, karty, stíny, formulářová pole, focus efekty, řádky tabulky a tmavý režim. `ui/theme.js` adaptuje efekty přepínání motivu. `ui/app.css` přidává rozložení pro desktop scraper. Logo je lokální kopie původního loga FebaMont. Font používá stejný systémový fallback; externí Wotfard není přibalen. Rozložení není kopií webového dashboardu, ale používá jeho vizuální styl.

Grafika, CSS a JavaScript jsou lokální, bez CDN. Lokální HTTP server pywebview obsluhuje pouze složku `ui/`, nikoli konfiguraci MySQL. Heslo se do UI načte pouze při otevření nastavení a po zavření dialogu se pole vyprázdní. Výsledky scraperu se vykreslují jako text, nikoli HTML.

## Testování

`python -m unittest discover -s tests -v` — 77 testů, včetně 13 testů nového Python bridge. Žádná živá databáze ani rozesílání.

`python tests/ui_smoke.py [cesta-k-chromium]` — volitelná kontrola vykreslení přes Playwright s falešným Python bridge, testovacími kontakty v doméně `.example` a lokálním serverem. Snímky ukládá do ignorované složky `tests/artifacts/`.

Ověřeno v headless Chromium: 1320 × 850, 1366 × 768, 1000 × 650 a 900 × 560; tabulka s 80 řádky, CAPTCHA, světlý/tmavý vzhled, hledání, detail, záložky, dynamická pole a ovládání běhu. Bez JavaScript chyb. Náhledy `tests/artifacts/light.png` a `tests/artifacts/dark.png`, které vytvoří test rozhraní, obsahují pouze testovací data.

Skutečné propojení WebView2 s Pythonem na Windows ověřuje `tests/desktop_smoke.py` s izolovaným nastavením; test byl po přesunu modulů úspěšně spuštěn. Testy rozhraní nenahrazují živý test CAPTCHA ani MySQL.
