# Desktopové rozhraní FebaMont

Ikony Nastavení a Prohlížeč jsou sladěné s hlavičkou. Při přepínání prohlížeče ikona nebledne; pulzuje jen stavové kolečko. Tlumené tlačítko znamená vypnutý prohlížeč.

Levá lišta obsahuje tlačítko **Prohlížeč**: mimo běh je vypnuté, během sběru ukazuje skryté nebo zobrazené okno. Přepnutí má busy stav až do potvrzení vláknem sběru. Odznak CAPTCHA zůstává aktivní nezávisle na viditelnosti. Tlačítko lze ovládat Enterem i mezerníkem; přístupný popis oznamuje skutečný stav. Při nemožnosti bezpečné obnovy nabídne pokračování ve viditelném režimu. Omezený pohyb platí i pro indikátor čekající akce.

Lokální HTML/CSS rozhraní uvnitř Python okna pomocí pywebview 6.1. Scraper, pokračování běhů, exporty a MySQL adapter zůstávají beze změny. Nejde o vzdálenou webovou aplikaci.

## Aktualizace

1. Zavřete aplikaci a aktualizujte zdroje včetně celé složky `ui/` a složky `system/`. Zachovejte vlastní výsledky a nastavení připojení.
2. Znovu spusťte `_INSTALOVAT.bat`, potom `_SPUSTIT.bat`.
3. Pokud okno hlásí chybějící WebView2, doinstalujte [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Chromium instalované pro scraper a WebView2 pro rozhraní jsou dvě odlišné součásti.

## Rozložení a ovládání

- Po otevření aplikace se zobrazí úvodní obrazovka WebScraperu. Obsahuje barevnou animaci, procentní ukazatel, průběhovou lištu a živý text aktuální fáze: načtení rozhraní, propojení s Pythonem, načtení nastavení a přípravu MySQL. Dashboard se odkryje až po dokončení bootstrapu a úvodním výsledku databázového připojení.
- Pokud připojení k MySQL selže nebo chybí nastavení, aplikace se nezablokuje. Zpřístupní dashboard a umožní připojení opravit v nastavení. Při neobvykle dlouhém startu nabídne bezpečné pokračování do aplikace.
- Vlevo jsou obor firem, počet stránek, výstup a složka běhu. Další parametry jsou pod rozbalovacím pokročilým nastavením.
- Skupina se zobrazuje pouze při ukládání do EmailApp. Připojení databáze se zobrazuje při tomto výstupu nebo při zapnutí kontroly známých adres.
- Při spuštění je vybrané **EmailApp (MySQL)** a zapnuté **Přeskočit známé e-maily**. Databáze se připojí automaticky a načte skupiny. Tlačítkem připojení lze seznam obnovit. **Nastavení připojení** předvyplní uložené heslo; prázdné heslo zachová stávající. Parametry včetně hesla se ukládají do místního `config/mysql.local.json`.
- Vpravo je statistika, průběh a tabulka. Nastavení a tabulka mají vlastní posuvník; spodní výpis neodsunuje dlouhý formulář mimo okno. Minimální velikost okna je 900 × 560.
- **Ctrl+F**, hledání a filtr usnadňují práci s posledními 500 výsledky. Kliknutí na řádek otevře detail a kopírování kontaktu. Úplné výsledky zůstávají v souborech běhu.
- Po spuštění se nastavení uzamkne. Ruční ověření se zobrazí pouze při čekání na CAPTCHA. Po zastavení lze pokračovat, zpracovat dosud získaná data nebo běh ukončit a data zahodit. Nové kontakty se do MySQL zapíší až po dokončení nebo po volbě použití aktuálních dat.
- Ikona měsíce/slunce přepíná vzhled. Nastavení zobrazení umožňuje omezit animace; respektována je i systémová preference omezeného pohybu. Volby vzhledu jsou v `.ui-state/`.

## Původ vzhledu

Aktuální vizuální systém je zdokumentovaný v kořenovém `DESIGN.md` a vychází z lokální šablony Lineone 3.1.1, zejména z CRM Analytics dashboardu a jeho komponent. Používá Lineone paletu, navigační lištu, modulární karty, barevné stavové ikony, světlý a tmavý motiv a krátké významové animace. Poppins a Inter jsou přibalené lokálně v `ui/assets/fonts`; rozhraní proto nepotřebuje Google Fonts ani CDN.

Pozorovatelné chování startu, databáze, běhu, tabulky, dialogů a animací popisuje `docs/project/UX-CONTRACT.md`. Vizuální úpravy musí zachovat DOM identifikátory používané `ui/app.js` a Python bridge.

Grafika, CSS a JavaScript jsou lokální, bez CDN. Lokální HTTP server pywebview obsluhuje pouze složku `ui/`, nikoli konfiguraci MySQL. Heslo se do UI načte pouze při otevření nastavení a po zavření dialogu se pole vyprázdní. Výsledky scraperu se vykreslují jako text, nikoli HTML.

## Testování

`python -m unittest discover -s tests -q` — aktuálně 109 testů. Žádná živá databáze ani rozesílání.

`python tests/ui_smoke.py [cesta-k-chromium]` — kontrola vykreslení přes Playwright s falešným Python bridge, testovacími kontakty v doméně `.example` a lokálním serverem. Ověřuje také živé fáze preloaderu, číselný průběh a čekání na úvodní výsledek MySQL. Snímky ukládá do ignorované složky `tests/artifacts/`.

Ověřeno v headless Chromium: 1320 × 850, 1366 × 768, 1000 × 650 a 900 × 560; tabulka s 80 řádky, CAPTCHA, světlý/tmavý vzhled, hledání, detail, záložky, dynamická pole a ovládání běhu. Bez JavaScript chyb. Náhledy `tests/artifacts/light.png` a `tests/artifacts/dark.png`, které vytvoří test rozhraní, obsahují pouze testovací data.

Skutečné propojení WebView2 s Pythonem na Windows ověřuje `tests/desktop_smoke.py` s izolovaným nastavením; test byl po přesunu modulů úspěšně spuštěn. Testy rozhraní nenahrazují živý test CAPTCHA ani MySQL.
