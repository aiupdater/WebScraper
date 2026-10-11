# WebScraper — společný kontext projektu

Aktualizováno: 11. 10. 2026

Tento soubor je stručný aktuální přehled pro všechny chaty pracující v tomto repozitáři. Pravidla práce jsou v kořenovém `AGENTS.md`; důvody dlouhodobých rozhodnutí jsou v `docs/project/DECISIONS.md`. Při rozporu se vždy ověří skutečný stav zdrojového kódu a testů.

## Cíl produktu

Windows desktopová aplikace získává firemní profily z WLW.de a 11880.com, dohledává firemní weby a e-mailové kontakty, průběžně ukládá obnovitelný stav a exportuje výsledky. Volitelně předává kontakty do MySQL pro FebaMont Emailapp.

## Aktuální technický tvar

- `system/app.py` spouští pywebview okno. Zákaznický vstup je instalovaný `WebScraper.exe` (verze 1.0.0); `_SPUSTIT.bat` zůstává pro zdrojový vývoj. Distribuuje se pouze produkční rozhraní `ui/index.html`; experimentální vstup a `ui/lineone` se nebalí.
- `system/desktop.py` propojuje HTML/JavaScript UI s Python backendem a řídí životní cyklus desktopového běhu.
- `system/core.py` obsahuje konfiguraci, pipeline, perzistenci průběhu, parsování, exporty a doménovou logiku.
- `system/browser_fetcher.py` obsluhuje Playwright prohlížeč, ruční ověření a portálově specifické stránkování. Windows desktop startuje skrytě, CLI a jiné systémy viditelně. `system/browser_window.py` ověřuje proces/profil a HWND, `system/browser_control.py` vlastní veřejný stav a frontu jednoho příkazu, `system/notifications.py` je volitelný Windows toast adaptér.
- `system/mysql_contacts.py` zajišťuje nastavení a odložené předání kontaktů do MySQL.
- `system/paths.py` odděluje neměnné prostředky od uživatelských dat. EXE ukládá konfiguraci, výsledky, stav WebView2, logy a aktualizace do `%LOCALAPPDATA%\WebScraper`; vývoj a CLI zachovávají cesty checkoutu, explicitní testovací kořen má přednost. `system/run_all.py` zůstává zdrojový CLI vstup.
- `ui/index.html`, `ui/app.js`, `ui/app.css` a `ui/theme.js` tvoří desktopové rozhraní. `ui/app.css` je jediný vlastník vizuálních tokenů a komponent; lokální Poppins a Inter jsou v `ui/assets/fonts/`. DOM ID a JS handlery jsou funkční smlouva, ne pouze vzhled.
- Lineone designový systém je popsán v kořenovém `DESIGN.md`, chování a vlastnictví komponent v `docs/project/UX-CONTRACT.md` a strojově čitelný rozsah auditu v `premium-ui.json`.
- Při startu je pracovní plocha skrytá preloaderem, který zobrazuje živou fázi, procenta a progress bar. Čeká na Python bootstrap a úvodní výsledek EmailApp/MySQL; chybějící heslo nebo chyba MySQL zpřístupní aplikaci a nabídnou opravu místo trvalého zablokování.
- Levá ikonová lišta obsahuje nastavení a tlačítko Prohlížeč. Tlačítko přepíná stejné okno bez zastavení sběru; stav potvrzuje vlastnické vlákno. CAPTCHA má samostatný odznak a okno neotevírá; při minimalizaci aplikace první výzva zkusí jeden toast. Bez ověřeného HWND se obnoví vlastní stránka přes CDP, při neúspěchu se zachová běh a nabídne viditelné pokračování.
- Jednotná motion vrstva v `ui/app.css` a `ui/app.js` animuje otevření i zavření dialogů a backdropu, toast zprávy, dynamické panely a změnu šířky nastavení. Používá nativní CSS/Web Animations API bez externí runtime závislosti a respektuje systémové i uživatelské omezení pohybu.
- `config/` obsahuje závislosti a bezpečné šablony bez hesla. Lokální `config/mysql.local.json` je ignorovaný a nesmí se sdílet; přihlašovací údaje zůstávají na disku uživatele. Nová instalace nemá výchozí databázové heslo.
- `vysledky/`, `.ui-state/`, `.venv/` a testovací dočasné adresáře jsou místní provozní stav, nikoli zdrojová pravda projektu.

- Windows balení v `packaging/` používá Python 3.11 x64, PyInstaller onedir, přibalené plné Chromium a český Inno Setup 6.7.3. Instalátor je per-user; odinstalace ponechá data. Jedinou verzi vlastní `system/version.py`.
- Aktualizace jsou z veřejných stabilních GitHub Releases `aiupdater/WebScraper`. Manifest ověřuje verzi, instalační asset, velikost a SHA-256; souběh chrání zámky. Kontrola je asynchronní, automaticky nejvýše jednou denně. Instalace vyžaduje potvrzení a volný backend; oddělený onefile updater běží z cache mimo instalaci, čeká na ukončení procesu a po úspěchu restartuje aplikaci.
- Nastavení aplikace obsahuje verzi, aktualizace a explicitní import původních nastavení/běhů bez přepisování. Kopie prochází stagingem a kontrolou hashů, konflikty a běžící profily import blokují; původní data zůstávají zachovaná. Nedokončený import není hlášen jako úspěšný.
- GitHub Actions na verzovacím tagu testuje a sestaví instalátor, provede EXE/instalační smoke a připraví koncept Release. Zákaznický a vydávací postup vlastní `docs/DISTRIBUCE.md`; stabilní zveřejnění je ruční brána.

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
& '.\.venv\Scripts\python.exe' tests\browser_desktop_smoke.py
& '.\.venv\Scripts\python.exe' tests\packaged_smoke.py --exe dist\WebScraper\WebScraper.exe
git diff --check
```

Testy používají `tempfile` a na omezeném Windows hostu mohou skončit `PermissionError`. Takový běh není aplikační regrese ani úspěšné ověření. Použij skutečně zapisovatelný dočasný adresář nebo schválený běh mimo sandbox a u výsledku vždy uveď, co přesně proběhlo.

## Aktuální stav ověření

- Dne 11. 10. 2026 prošlo 161 unit testů v projektovém `.venv` i build Pythonu 3.11, rozšířený UI smoke (aktualizace/import, potvrzení a Escape, konflikty, busy blokování, světlý/tmavý motiv a čtyři velikosti) a skutečný zdrojový WebView2 smoke. Browser desktop smoke prošel pro Chromium a Chrome; Edge kanál chybí.
- Sestavený `release/WebScraper-Setup.exe` 1.0.0 obsahuje produkční UI a Chromium. Skutečné EXE prošlo v izolované české cestě bez Pythonu/Playwrightu v PATH: WebView2, bootstrap, datové cesty, nový bridge a Chromium pro oba portály na offline fixtures včetně zobrazení/skrytí. Diagnostika sama izoluje data a databázové proměnné prostředí.
- Izolovaný instalační test na aktuálním Windows hostu prošel: per-user instalace, zástupce Start, běh instalovaného EXE, skutečný zabalený updater (handshake, čekání, instalace, restart), reinstalace stejné verze a odinstalace se zachováním nastavení/výsledků. Nejde o čistý OS ani upgrade mezi dvěma verzemi. Důkazy jsou v ignorovaných `tests/artifacts/packaged-smoke.json`, `installer-smoke.json` a UI náhledech.
- Přísný UI audit zůstává červený: produkční porovnání proti HEAD má stejných 33 nerozpoznaných JS handlerů, bez nového nálezu. Celkový lokální audit zahrnuje také ignorované experimentální UI (69 nálezů); toto UI se nedistribuuje. Runtime workflow testy prošly. Výsledky porovnání jsou v `tests/artifacts/premium-production-comparison.json`.

- Následná oprava dne 4. 10. 2026: prošlo 140 unit testů, UI smoke a skutečný WebView2 smoke. Chromium a Chrome prošly i monitorovaným startem a opětovným spuštěním stejného profilu bez zaznamenaného viditelného okna. Windows start používá `--start-minimized` bez emulovaného viewportu. UI při přepínání nebledne; pulzuje kolečko, ikony lišty odpovídají hlavičce.
- Rušení běhu přes `system/run_cleanup.py` odstraňuje read-only atributy Chromium/OneDrive, krátce opakuje dočasné zámky a maže profil před výsledky. Při trvale zamčeném profilu zůstávají uložené výsledky. Skutečný Windows test ověřil read-only Crashpad včetně desktopového bridge. Kontrola se omezuje na výslovně rušený běh uvnitř `vysledky`.

- Dne 4. 10. 2026 prošlo 135 unit testů, rozšířený UI smoke a skutečný WebView2 desktop smoke. `browser_desktop_smoke.py` ověřil na skutečných Windows oknech Chromium a Chrome skrytý stav po startu, zobrazení/skrytí, přepnutí během zpožděné síťové odpovědi, načítání skrytě, obnovu minimalizace, stejnou stránku, nedotčené souběžné okno a obnovu po ztrátě identifikace přes CDP. Zavření stránky zachovalo `BROWSER_CLOSED`. Edge není dostupný pro Playwright a zůstává neověřený.
- Přísný premium UI audit neprošel: 34 nálezů je již ve výchozí revizi (zejména nedetekované JS handlery), dalších 35 pochází z lokální ignorované experimentální `ui/lineone/`. Porovnání s HEAD neukázalo nový produkční nález. JSON je v lokálním `tests/artifacts/premium-audit.json`; runtime smoke ověřil změněné ovládání. Experimentální vstup `--lineone` bez nového tlačítka zachovává viditelný prohlížeč.
- Skutečná CAPTCHA, viditelné systémové upozornění, úplná absence krátkého probliknutí při startu a změny více monitorů/DPI nebyly ověřeny. Deduplikace toastu a CAPTCHA chování jsou pokryty simulovanými testy. Tyto chybějící důkazy brání tvrzení o plném splnění nasazovacích kritérií plánu.

- Výchozí revize při založení tohoto kontextu: větev `main`, commit `208901d` (`WebScraper: current verified version`).
- Dne 30. 9. 2026 prošlo mimo omezený sandbox všech 109 unit testů, `tests/ui_smoke.py` i `tests/desktop_smoke.py`. Desktop smoke ověřil skutečný WebView2, Python bootstrap, oba portály, práci se složkou a nastavení MySQL. Nešlo o živý hromadný scraping ani připojení k produkční databázi.
- Po čistém Lineone redesignu dne 30. 9. 2026 znovu prošlo 109 unit testů, rozšířený UI smoke a skutečný WebView2 desktop smoke. UI smoke ověřuje světlý i tmavý motiv, rozměry až 900 × 560, omezený pohyb, živé fáze preloaderu, úspěšné MySQL skupiny, chybějící heslo, chybu MySQL, vlastní potvrzovací dialog, zobrazení hesla a vymazání hledání.
- Statický nebo designový audit nenahrazuje funkční testy. Živý hromadný scraping a produkční MySQL vyžadují samostatné výslovné ověření.

## Známé hranice a otevřená práce

- Zdrojová implementace instalátoru a aktualizací je na `origin/main` (commit `19ca6d2`) a označena tagem `v1.0.0`. Na GitHubu byl vytvořen koncept WebScraper 1.0.0; stabilní vydání zatím není zveřejněné. Tagový workflow [38160977995](https://github.com/aiupdater/WebScraper/actions/runs/38160977995) se nespustil: GitHub zablokoval účet kvůli fakturaci. Vydání používá lokálně sestavené a ověřené artefakty; CI je potřeba zopakovat po odstranění blokace.
- Před zákaznickým vydáním zbývá checklist `docs/DISTRIBUCE.md`: čisté Windows 10/11 bez Pythonu, chybějící WebView2, přechod mezi různými verzemi, ruční návrat ke starší verzi, import/obnova skutečného starého běhu a živé portály/CAPTCHA. Dříve zveřejněné používané přihlašovací údaje je potřeba změnit u poskytovatele; historie Git se nepřepisovala. První instalátor nemá podpis vydavatele.

- Dokumentace obsahuje historické názvy a starší instalační formulace; při změnách rozlišuj funkční identifikátory portálů od značky aplikace.
- Při dalších UI změnách je nutné zachovat jedinou vrstvu `ui/app.css`, DOM/JS vazby a znovu ověřit UI smoke i skutečný WebView2 desktop.
- `README.md` a dokumenty v `docs/` mohou popisovat různé etapy vývoje. Změna chování musí aktualizovat všechny relevantní uživatelské návody, ne pouze tento soubor.

## Jak tento soubor udržovat

Aktualizuj pouze současnou pravdu: účel, komponenty, zachovávané smlouvy, ověřený stav, známá omezení a bezprostřední priority. Historické důvody patří do `docs/project/DECISIONS.md`; detailní návody do `README.md` nebo ostatních souborů v `docs/`; běžný průběh práce zůstává v chatu a Git historii.
