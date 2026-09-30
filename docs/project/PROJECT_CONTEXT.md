# WebScraper — společný kontext projektu

Aktualizováno: 30. 9. 2026

Tento soubor je stručný aktuální přehled pro všechny chaty pracující v tomto repozitáři. Pravidla práce jsou v kořenovém `AGENTS.md`; důvody dlouhodobých rozhodnutí jsou v `docs/project/DECISIONS.md`. Při rozporu se vždy ověří skutečný stav zdrojového kódu a testů.

## Cíl produktu

Windows desktopová aplikace získává firemní profily z WLW.de a 11880.com, dohledává firemní weby a e-mailové kontakty, průběžně ukládá obnovitelný stav a exportuje výsledky. Volitelně předává kontakty do MySQL pro FebaMont Emailapp.

## Aktuální technický tvar

- `system/app.py` spouští pywebview okno; běžný uživatelský vstup je `_SPUSTIT.bat`.
- `system/desktop.py` propojuje HTML/JavaScript UI s Python backendem a řídí životní cyklus desktopového běhu.
- `system/core.py` obsahuje konfiguraci, pipeline, perzistenci průběhu, parsování, exporty a doménovou logiku.
- `system/browser_fetcher.py` obsluhuje viditelný Playwright prohlížeč, ruční ověření a portálově specifické stránkování.
- `system/mysql_contacts.py` zajišťuje nastavení a odložené předání kontaktů do MySQL.
- `system/paths.py` určuje kanonické cesty aplikace; `system/run_all.py` je CLI vstup.
- `ui/index.html`, `ui/app.js`, `ui/app.css` a `ui/theme.js` tvoří desktopové rozhraní. `ui/app.css` je jediný vlastník vizuálních tokenů a komponent; lokální Poppins a Inter jsou v `ui/assets/fonts/`. DOM ID a JS handlery jsou funkční smlouva, ne pouze vzhled.
- Lineone designový systém je popsán v kořenovém `DESIGN.md`, chování a vlastnictví komponent v `docs/project/UX-CONTRACT.md` a strojově čitelný rozsah auditu v `premium-ui.json`.
- Při startu je pracovní plocha skrytá preloaderem, který zobrazuje živou fázi, procenta a progress bar. Čeká na Python bootstrap a úvodní výsledek EmailApp/MySQL; chybějící heslo nebo chyba MySQL zpřístupní aplikaci a nabídnou opravu místo trvalého zablokování.
- Levá ikonová lišta nyní obsahuje jedinou funkční akci pro otevření a skrytí sloupce nastavení. Nehotové odkazy na budoucí sekce se nevykreslují; tlačítko nemění URL ani neposouvá dokument. Logo FEBA-MONT je v hlavičce vlevo před názvem aplikace.
- Jednotná motion vrstva v `ui/app.css` a `ui/app.js` animuje otevření i zavření dialogů a backdropu, toast zprávy, dynamické panely a změnu šířky nastavení. Používá nativní CSS/Web Animations API bez externí runtime závislosti a respektuje systémové i uživatelské omezení pohybu.
- `config/` obsahuje distribuovanou konfiguraci. Lokální `config/mysql.local.json` může obsahovat tajné údaje a nesmí se sdílet.
- `vysledky/`, `.ui-state/`, `.venv/` a testovací dočasné adresáře jsou místní provozní stav, nikoli zdrojová pravda projektu.

## Zachovávané chování

- Podporované portály jsou `wlw` a `11880`; změna portálu nesmí smíchat nesouvisející uložené běhy.
- Kategorie, stránka původu a vazba profilu na zdrojový výpis se musí zachovat napříč pipeline a exporty.
- Uložený běh lze bezpečně zastavit, pokračovat v něm, dokončit jej s aktuálními daty nebo zahodit podle zvoleného ovládacího toku.
- MySQL zápis je odložený do finalizace; testy používají simulované připojení, nikoli produkční databázi.
- WLW může vyžadovat viditelný prohlížeč a ruční CAPTCHA. Pro 11880 se stránkování řídí stavem portálu a viditelným ovládáním další stránky, nikoli slepým předpokladem libovolné URL stránky.

## Ověřování

Příkazy spouštěj z kořene repozitáře:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -q
& '.\.venv\Scripts\python.exe' tests\ui_smoke.py
& '.\.venv\Scripts\python.exe' tests\desktop_smoke.py
git diff --check
```

Testy používají `tempfile` a na omezeném Windows hostu mohou skončit `PermissionError`. Takový běh není aplikační regrese ani úspěšné ověření. Použij skutečně zapisovatelný dočasný adresář nebo schválený běh mimo sandbox a u výsledku vždy uveď, co přesně proběhlo.

## Aktuální stav ověření

- Výchozí revize při založení tohoto kontextu: větev `main`, commit `208901d` (`WebScraper: current verified version`).
- Dne 30. 9. 2026 prošlo mimo omezený sandbox všech 109 unit testů, `tests/ui_smoke.py` i `tests/desktop_smoke.py`. Desktop smoke ověřil skutečný WebView2, Python bootstrap, oba portály, práci se složkou a nastavení MySQL. Nešlo o živý hromadný scraping ani připojení k produkční databázi.
- Po čistém Lineone redesignu dne 30. 9. 2026 znovu prošlo 109 unit testů, rozšířený UI smoke a skutečný WebView2 desktop smoke. UI smoke ověřuje světlý i tmavý motiv, rozměry až 900 × 560, omezený pohyb, živé fáze preloaderu, úspěšné MySQL skupiny, chybějící heslo, chybu MySQL, vlastní potvrzovací dialog, zobrazení hesla a vymazání hledání.
- Statický nebo designový audit nenahrazuje funkční testy. Živý hromadný scraping a produkční MySQL vyžadují samostatné výslovné ověření.

## Známé hranice a otevřená práce

- Dokumentace obsahuje historické názvy a starší instalační formulace; při změnách rozlišuj funkční identifikátory portálů od značky aplikace.
- Při dalších UI změnách je nutné zachovat jedinou vrstvu `ui/app.css`, DOM/JS vazby a znovu ověřit UI smoke i skutečný WebView2 desktop.
- `README.md` a dokumenty v `docs/` mohou popisovat různé etapy vývoje. Změna chování musí aktualizovat všechny relevantní uživatelské návody, ne pouze tento soubor.

## Jak tento soubor udržovat

Aktualizuj pouze současnou pravdu: účel, komponenty, zachovávané smlouvy, ověřený stav, známá omezení a bezprostřední priority. Historické důvody patří do `docs/project/DECISIONS.md`; detailní návody do `README.md` nebo ostatních souborů v `docs/`; běžný průběh práce zůstává v chatu a Git historii.
