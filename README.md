# WebScraper · WLW.de / 11880.com

Společný kontext pro vývojové chaty je v [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md),
trvalá pravidla v [AGENTS.md](AGENTS.md) a dlouhodobá rozhodnutí v
[DECISIONS.md](DECISIONS.md).

## Spuštění

1. Při první instalaci spusťte **_INSTALOVAT.bat**.
2. Aplikaci otevírejte pomocí **_SPUSTIT.bat**.
3. Vlevo vyberte databázi firem **WLW.de** nebo **11880.com**, kategorie a způsob ukládání.

`ui/index.html` je pouze rozhraní; samostatným otevřením se Python nespustí.
Po uspořádání souborů stačí aplikaci znovu otevřít. Existující `.venv` lze dál používat.

## První spuštění ve Windows

1. Rozbalte celý ZIP do vlastní složky, například `C:\WLW_Studio`. Nespouštějte soubory přímo uvnitř ZIPu.
2. Spusťte `INSTALOVAT.bat`. Vytvoří místní `.venv` a nainstaluje balíčky stejným Pythonem, který aplikaci spouští. Je potřeba internet, Python 3.11 nebo novější a Microsoft Edge WebView2 Runtime (viz [UI.md](UI.md)).
3. Spusťte `SPUSTIT.bat`.
4. V poli **Kategorie** zaškrtněte požadované kategorie. Při prvním spuštění je připravená **Tiefbau**, další si můžete přidat nebo smazat. Aplikace postupně získá firemní profily ze všech vybraných kategorií. Nastavte počáteční stránku a maximální počet stránek pro každou kategorii.
5. Pro WLW zvolte **Prohlížeč + ruční ověření** a **Chromium** (instalátor jej stáhne). Microsoft Edge / Google Chrome lze vybrat, pokud je již máte nainstalované.
6. Zvolte výstupní složku a stiskněte **Spustit / pokračovat**. Při CAPTCHA ji vyřešte přímo v otevřeném okně a potom v aplikaci stiskněte **Ověřeno — pokračovat**.

**Aktualizace původní verze:** zavřete aplikaci, překopírujte zdrojové soubory z balíčku do původní složky a znovu spusťte `INSTALOVAT.bat`. Ponechte své `vysledky` a `.venv`. Podrobnosti k této opravě jsou v `OPRAVA_CAPTCHA.md`.

Pokud Python není nainstalován, použijte instalátor z [python.org](https://www.python.org/downloads/windows/) s komponentami Tcl/Tk a Python Launcher. Chyba `No module named httpx` se řeší opětovným spuštěním `INSTALOVAT.bat`, nikoli instalací do náhodného jiného Pythonu.

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
| `tests/` | Automatické testy; náhledy rozhraní v `tests/artifacts/` |
| `.venv/` | Nainstalované Python prostředí |
| `.ui-state/` | Místní stav desktopového rozhraní |

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
