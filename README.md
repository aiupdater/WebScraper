# WebScraper · WLW.de / 11880.com

Společný kontext a dlouhodobá rozhodnutí pro vývojové chaty jsou uklizené v
[`docs/project/`](docs/project/). Kořenový [AGENTS.md](AGENTS.md) zůstává na
technicky nutném místě, aby jeho pravidla Codex automaticky načetl pro celý repozitář.

## Instalovaná aplikace pro Windows

Zákaznická distribuce používá jediný `WebScraper-Setup.exe` z [GitHub Releases](https://github.com/aiupdater/WebScraper/releases). Podporuje Windows 10/11 x64, nepotřebuje instalovaný Python a obsahuje Chromium. První vydání není podepsané certifikátem vydavatele.

1. Spusťte instalační EXE. Instalace vytvoří položku v nabídce Start; ikona na ploše je volitelná.
2. Aplikaci otevírejte ikonou WebScraperu. V nastavení MySQL zadejte vlastní údaje, nebo zvolte lokální ukládání a vypněte kontrolu známých e-mailů.
3. Vyberte WLW.de či 11880.com, kategorie, způsob ukládání a spusťte sběr.
4. Při požadavku na CAPTCHA otevřete **Prohlížeč**, dokončete ověření a stiskněte **Ověřeno, pokračovat**.

**Aktualizace:** Nastavení aplikace v hlavičce zobrazuje verzi a kontrolu aktualizací. Novou verzi stáhněte a zvolte **Instalovat a restartovat**. Instalace je dostupná až po dokončení sběru a ukládání; nastavení a výsledky zachová. Automatická kontrola probíhá nejvýše jednou denně. Nová vydání se zveřejňují až po ověření instalačního balíčku.

**Přechod z původní složky:** zavřete původní aplikaci i její prohlížeč. V Nastavení aplikace vyberte původní složku, zkontrolujte přehled a potvrďte **Zkopírovat data**. Existující cílové položky se nepřepisují. Import kopíruje nastavení a obsah `vysledky`; původní soubory zachová. Importovaný běh vyberte pomocí **Změnit…** v sekci Složka běhu. Stav zobrazení z původního WebView2 se nepřenáší.

Program je standardně v `%LOCALAPPDATA%\Programs\WebScraper`; soukromé nastavení, výsledky a stav rozhraní jsou v `%LOCALAPPDATA%\WebScraper`. Odinstalace ponechá uživatelská data.

Podrobný návod a vydávací checklist: [Distribuce pro Windows](docs/DISTRIBUCE.md).

## Spouštění ze zdrojů (vývoj)

Rozbalte zdroje do vlastní složky. S Pythonem 3.11+ spusťte `_INSTALOVAT.bat`, potom `_SPUSTIT.bat`. Je potřeba Microsoft Edge WebView2 Runtime. Zdrojová verze zachovává místní `.venv`, `config`, `.ui-state` a `vysledky` v checkoutu. BAT skripty nejsou součástí zákaznického instalátoru.

`ui/index.html` je pouze rozhraní; samostatným otevřením se Python nespustí. Produkční rozhraní je pouze `ui/index.html`; experimentální spouštění a `ui/lineone` nejsou součástí balíčku.

## Aktuální stav WLW a rozsah ověření

Kontrola ze 16. 9. 2026 potvrdila, že původní URL `/de/suche?q=Tiefbau` vrací HTML bez profilových odkazů. `/de/suche/tiefbau` poskytla 30 unikátních profilů. Stránkování má tvar `/de/suche/tiefbau/page/2`. Aplikace používá tento formát. Okno nabízí pevný výběr sedmi kategorií; vlastní dotaz nebo URL lze nadále předat přes CLI.

Na jednom živém profilu byla ověřena extrakce skutečného webu z veřejných SSR dat `__NUXT_DATA__`: pole `homepage` se přiřazuje pouze objektu s přesně odpovídajícím slugem profilu. Odkaz není vždy přímo v atributu `href`. Nejde o plošné ověření všech variant profilů.

Aplikace robots.txt nestahuje ani nevyhodnocuje. V rozhraní není přepínač této kontroly. Viditelný prohlížeč umožňuje ruční dokončení CAPTCHA. Při importu firemních webů se WLW vůbec nenavštěvuje.

Automatické testy ověřují parsování, celou pipeline na připravených datech, opakování požadavků, přerušení, pokračování a exporty. Nová obsluha ručního ověření je testována simulovaným prohlížečem. Skutečný prohlížeč se zde nepodařilo stáhnout (síťový timeout), takže spuštění okna, ruční CAPTCHA na WLW a BAT soubory na Windows nebyly ověřeny. Hromadný sběr na živých webech ani rychlostní benchmark neproběhly.

## Co vidíte v okně

- Čtyři samostatné ukazatele: získání profilů, firemní weby, čištění a hledání e-mailů.
- Počty zpracovaných profilů, unikátních e-mailů a chyb v aktuálním běhu.
- Aktuální požadavek, uplynulý čas, posledních 500 výsledků a živý protokol.
- **Zastavit sběr**: zruší další práci a počká na rozpracované síťové požadavky. Potom lze pokračovat, použít aktuální data, nebo běh ukončit a data zahodit. Zastavení není okamžité během blokujícího síťového čtení.
- **Otevřít výsledky**: otevře výstupní složku.
- **Ověřeno — pokračovat**: po ručním ověření zkontroluje původní požadovanou stránku; stále viditelnou CAPTCHA ani jinou adresu nepovažuje za výsledek. Čekání končí po 10 minutách, zavření prohlížeče nebo zastavení úlohy.

Postup jednotlivých kroků není odhad celkového času dokončení. Počet webů je znám až po extrakci a vyčištění. Tabulka i živý log mají omezenou historii kvůli paměti; úplné výsledky zůstávají na disku.

## Import existujících souborů přes CLI

Z okna byl odstraněn řádek pro výběr zdroje a TXT souboru. Import zůstává dostupný pouze přes příkazový řádek: `--input soubor.txt --kind profiles` načte profily a `--input soubor.txt --kind websites` načte firemní weby a přeskočí WLW. Doplňte také `--output slozka`; příklady jsou níže. Každý řádek obsahuje jednu URL začínající `https://` nebo `http://`; kódování UTF-8, případně UTF-8 BOM. Relativní WLW profilové cesty jsou také přijímány. Duplicity se odstraní, počet neplatných řádků se vypíše.

Pro pokračování vyberte stejnou složku, stejný vstup a stejné zadání. Cestu k importu lze změnit, pokud jsou jeho bajty stejné. Počet pracovníků, prodlevu, timeout, způsob načítání WLW, i prohlížeč lze změnit. Verze migruje také identitu starého běhu. Změna dotazu, rozsahu stránek nebo obsahu vstupu vyžaduje novou výstupní složku. Kontrola identity chrání před smícháním nesouvisejících výsledků.

## Výstupy

## Kde co najdete

| Soubor / složka | Účel |
| --- | --- |
| `_SPUSTIT.bat` | Běžné spuštění aplikace |
| `_INSTALOVAT.bat` | Instalace a aktualizace závislostí |
| `vysledky/` | Výsledky sběru a uložený průběh |
| `config/` | Místní nastavení MySQL, kategorie, vzory a jediný `requirements.txt` |
| `system/` | Python backend a vstupní bod aplikace |
| `ui/` | HTML, JavaScript, styly a logo |
| `docs/` | Podrobné návody a technická dokumentace |
| `docs/project/` | Společný kontext a dlouhodobá rozhodnutí pro vývojové chaty |
| `tests/` | Automatické testy; náhledy rozhraní v `tests/artifacts/` |
| `.venv/` | Nainstalované Python prostředí |
| `.ui-state/` | Místní stav desktopového rozhraní |
| `AGENTS.md` | Automaticky načítaná pravidla Codexu; kvůli platnosti pro celý projekt musí zůstat v kořeni |

Nastavení připojení měňte v aplikaci. Soubor `config/mysql.local.json` obsahuje
soukromé přihlašovací údaje; neposílejte jej spolu se zdrojovým kódem.
Šablony `*.example` se automaticky nepoužívají jako aktivní nastavení.

Podrobnosti: [používání aplikace](docs/POUZITI.md), [MySQL](docs/MYSQL.md),
[rozhraní](docs/UI.md), [konfigurace](config/README.md).

## Pro vývojáře

Příkazy spouštějte z kořenové složky aplikace:

```bat
.venv\Scripts\python.exe -m system.run_all --help
.venv\Scripts\python.exe -m unittest discover -s tests -q
.venv\Scripts\python.exe tests/ui_smoke.py
.venv\Scripts\python.exe tests/desktop_smoke.py
```

CLI pro 11880.com používá `--portal 11880`, pro WLW.de `--portal wlw`.
