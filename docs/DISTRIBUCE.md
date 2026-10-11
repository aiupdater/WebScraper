# Distribuce WebScraperu pro Windows

## Zákaznický postup

Stáhněte `WebScraper-Setup.exe` z veřejného stabilního GitHub Release v `aiupdater/WebScraper`. Instalátor je český, určený pro Windows 10/11 x64 a instaluje pro aktuálního uživatele. Obsahuje Python runtime i Chromium; zákazník nemusí spouštět BAT soubory. Pokud chybí WebView2, interaktivní instalátor nabídne oficiální Microsoft bootstrapper. Ten vyžaduje internet a může požádat o oprávnění.

Spouštění: nabídka Start → WebScraper. Ikona na ploše je volitelná. Nepodepsané první vydání může vyvolat upozornění Windows na neznámého vydavatele.

V Nastavení aplikace najdete verzi, kontrolu aktualizace a přechod ze staré distribuce. Aktualizaci potvrzujete sami. Stahování může běžet během sběru; instalace je blokovaná během sběru, MySQL operace a importu. Tlačítko instalace zavře aplikaci, spustí ověřený instalátor a otevře novou verzi. Pokud operace selže, zůstane srozumitelná zpráva; lze zopakovat kontrolu a stažení nebo použít předchozí instalátor z Releases. Automatická kontrola neblokuje start a probíhá nejvýše jednou denně.

## Cesty a import

Program: `%LOCALAPPDATA%\Programs\WebScraper`. Data: `%LOCALAPPDATA%\WebScraper` obsahuje `config`, `vysledky`, `.ui-state`, `logs` a `updates`. Vlastní výstupní složky jsou nadále podporované. Odinstalace neodstraňuje datovou složku.

Import vyžaduje samostatnou původní složku se `system` a `ui`. Předem zavřete původní aplikaci a její prohlížeče, data OneDrive stáhněte lokálně. Zobrazí se soubory nastavení a běhy, které budou zkopírované. Konflikt zastaví celý import před kopírováním do cíle. Kopie vzniká nejprve ve staging složce, ověřuje se SHA-256 zdrojů i kopií a teprve potom se zpřístupní. Původní soubory zůstávají zachované. Odkazy, junctions a cloudové zástupné soubory jsou odmítané.

Při chybě zpřístupnění některé již zkopírované položky zůstanou zachované; import není označený jako úspěšný. `logs/import.json` zaznamenává dokončené položky a stav. Import nikdy neslučuje konfliktní běhy. Stav zobrazení WebView2 se nepřenáší. Pro pokračování vyberte importovanou složku běhu a stejné zadání.

## Sestavení a vydávání

Jediný zdroj verze je `system/version.py`. Pro release musí tag přesně odpovídat `vMAJOR.MINOR.PATCH`. Build vyžaduje Windows a Python 3.11 x64; projektové `.venv` zůstává vývojovým prostředím. Doporučený build používá vlastní `.build-venv`:

```powershell
py -3.11 -m venv .build-venv
& .\.build-venv\Scripts\python.exe -m pip install -r config\requirements.txt -r packaging\build-requirements.txt
& .\.build-venv\Scripts\python.exe packaging\build.py --iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
& .\.venv\Scripts\python.exe tests\packaged_smoke.py --exe dist\WebScraper\WebScraper.exe
```

Použitý kompilátor: Inno Setup 6.7.3. Lze použít přenosný balíček Tools.InnoSetup stejné verze; před použitím ověřte platný digitální podpis `ISCC.exe`. Build stáhne příslušné Chromium, vytvoří onedir aplikaci a samostatný onefile updater, zkontroluje distribuovaný obsah a vytvoří `release/WebScraper-Setup.exe` a `release/update.json`. `--bundle-only` sestaví pouze aplikaci pro rychlé ověření; `--skip-browser-download` použije již stažené build prohlížeče. Headless shell není distribuovaný: desktop používá plné Chromium.

Konfigurace a výsledky se do balíčku nekopírují. Produkční UI je výhradně `ui/index.html`, `app.js`, `app.css`, `theme.js` a lokální assets. Experimentální `ui/lineone` ani jeho BAT nejsou součástí balení. UI soubory jsou servírované pouze z vlastní složky, nikoliv z datového kořene.

GitHub Actions na tagu provede unit testy, UI a WebView2 smoke, build, skutečný packaged smoke a izolovaný test instalátoru/updateru; nahraje instalační artefakty a vytvoří **koncept** Release. `workflow_dispatch` jen sestaví artefakty. Stabilní Release se zveřejňuje ručně až po níže uvedeném checklistu. Workflow vyžaduje povolené Actions a oprávnění vytvořit Release. Při změně verze aktualizujte také české poznámky v `packaging/release-notes.md`.

Manifest obsahuje pouze `version`, `asset`, `size` a `sha256`. Aktualizační klient vybírá jednoznačné soubory ze stejného stabilního vydání, kontroluje HTTPS i cílové servery přesměrování a opakuje hash před spuštěním. Manifest nemůže zadat příkaz. Aplikace neobsahuje GitHub token. SHA-256 není podpis vydavatele. Stažené instalátory se ponechávají; automatické mazání dat ani automatický rollback nejsou implementované.

## Checklist před zveřejněním

- [ ] Změnit případné dříve používané zveřejněné databázové přihlašovací údaje u poskytovatele. Staré commity se tímto úkolem nepřepisují.
- [ ] Doplnit český přehled změn do konceptu vydání.
- [ ] Na čistých Windows 10 a 11 x64 bez Pythonu nainstalovat EXE jako běžný uživatel; ověřit nabídku Start, volitelnou plochu a WebView2 přítomný/chybějící.
- [ ] Ověřit produkční UI a oba portály; skutečné CAPTCHA ověřit ručně s omezeným zadáním, nikoliv hromadným sběrem.
- [ ] Ověřit vlastní výstupní složku, zastavení a pokračování uloženého běhu.
- [ ] Ověřit import, konflikt a zachování původních dat včetně zavřeného profilu.
- [ ] Ověřit aktualizaci mezi dvěma verzemi včetně pomocného EXE, zachování dat a startu nové verze; neinstalovat během práce.
- [ ] Ověřit poškozený download, nedostatek místa, chybu instalátoru a opakování.
- [ ] Ověřit odinstalaci se zachováním dat, opětovnou instalaci a ruční návrat ke staršímu instalátoru.
- [ ] Teprve potom zveřejnit stabilní Release; předchozí instalátory ponechat dostupné.

Offline packaged smoke skutečně spouští EXE, WebView2 a přibalené Chromium, testuje oba portály na lokálních fixtures a zobrazení/skrytí prohlížeče. Odstraní Python z PATH a používá izolovanou českou cestu. Nenahrazuje instalaci na čistých Windows ani živé portály. Diagnostický parametr `--diagnostic-report <soubor>` je opt-in, automaticky izoluje data i databázové proměnné prostředí a nepřistupuje k portálům či databázi.

`python tests/installer_smoke.py --installer release/WebScraper-Setup.exe` ověřuje na aktuálním Windows hostu instalaci do nové dočasné složky, zástupce Start, běh EXE, skutečný zabalený updater s handshake a restartem, reinstalaci stejné verze a odinstalaci se zachováním dat. Odmítne běh, pokud již existuje uživatelská instalace nebo zástupce WebScraperu. Při chybě ponechá testovací instalaci a logy pro diagnostiku. Nenahrazuje upgrade mezi dvěma verzemi a čisté OS.
