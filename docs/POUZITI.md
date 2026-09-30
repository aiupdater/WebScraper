# WebScraper · verze s ručním ověřením

> **Nové desktopové UI ve stylu EmailApp:** světlý/tmavý režim, dynamická nastavení a samostatně posouvatelná tabulka. Po aktualizaci znovu spusťte `_INSTALOVAT.bat`. Návod a rozsah ověření: [UI.md](UI.md).

> **Nově: propojení s FebaMont Emailapp (MySQL)** — výběr skupiny, kontrola existujících adres a přímé ukládání. Postup nastavení a rozdíly výstupů: [MYSQL.md](MYSQL.md).

Přepracování pěti dodaných skriptů do jedné desktopové aplikace. Python 3.11+, primárně Windows 11. Zdroje jsou otevřené k úpravám; nejde o zkompilované EXE.

## Výběr portálu databáze firem

Vlevo v nastavení vyberte **WLW.de** (výchozí) nebo **11880.com**. Každý běh zpracovává pouze jeden vybraný portál a postupně všechny zvolené kategorie.

- WLW.de nadále získává firemní weby a hledá kontakty na nich.
- 11880.com používá `/suche/Tiefbau/deutschland` a stránkování `?page=2`. V režimu prohlížeče přechází tlačítkem „Zur nächsten Seite“ přes formulář portálu; přímé otevření stránkované URL může server odmítnout. Při vyšší počáteční stránce nejprve projde předchozí stránky bez sběru jejich profilů.
- E-maily 11880.com se čtou přímo z kontaktní části profilu, metadat a odpovídajících strukturovaných dat. Firemní web se kvůli tomu nenavštěvuje a není podmínkou získání e-mailu. Profil bez adresy má stav `NO_EMAIL`.
- Zůstává výběr nejlepšího nebo více e-mailů, kontrola duplicit, MySQL, exporty a pokračování. Pro jiný portál použijte novou složku běhu. Starší uložené běhy se považují za WLW.
- Obecný seznam profilů se ukládá do `company_urls.txt`; původní `wlw_company_urls.txt` zůstává kvůli kompatibilitě. Zdroj e-mailu v exportu ukazuje na konkrétní profil.

CLI podporuje `--portal 11880` (výchozí `--portal wlw`). Volba `--wlw-mode` je kvůli kompatibilitě pojmenovaná původním názvem, ale nastavuje způsob načítání pro oba portály.

Ochranné ověření řeší uživatel v otevřeném prohlížeči. Při skutečném zamítnutí přístupu se sběr zastaví a zachová uloženou práci.

Ověření 26. 9. 2026: 103 automatických testů prošlo; prošel i test rozhraní v Chromium včetně výběru portálu a POST stránkování na izolovaných testovacích stránkách. V připojeném uživatelském prohlížeči byly ověřeny první dvě stránky Tiefbau, 50 profilových odkazů na druhé stránce a otevření profilu Novus s e-mailem. Parser aplikace získal shodný e-mail i z živě staženého HTML profilu. MySQL je pokryto simulovanými integračními testy; hromadný ostrý sběr a zápis do skutečné databáze nebyly součástí ověření.

## První spuštění ve Windows

1. Rozbalte celý ZIP do vlastní složky, například `C:\WLW_Studio`. Nespouštějte soubory přímo uvnitř ZIPu.
2. Spusťte `_INSTALOVAT.bat`. Vytvoří místní `.venv` a nainstaluje balíčky stejným Pythonem, který aplikaci spouští. Je potřeba internet, Python 3.11 nebo novější a Microsoft Edge WebView2 Runtime (viz [UI.md](UI.md)).
3. Spusťte `_SPUSTIT.bat`.
4. V poli **Kategorie** zaškrtněte požadované kategorie. Při prvním spuštění je připravená **Tiefbau**, další si můžete přidat nebo smazat. Aplikace postupně získá firemní profily ze všech vybraných kategorií. Nastavte počáteční stránku a maximální počet stránek pro každou kategorii.
5. Pro WLW zvolte **Prohlížeč + ruční ověření** a **Chromium** (instalátor jej stáhne). Microsoft Edge / Google Chrome lze vybrat, pokud je již máte nainstalované.
6. Zvolte výstupní složku a stiskněte **Spustit / pokračovat**. Při CAPTCHA ji vyřešte přímo v otevřeném okně a potom v aplikaci stiskněte **Ověřeno — pokračovat**.

**Aktualizace původní verze:** zavřete aplikaci, překopírujte zdrojové soubory z balíčku do původní složky a znovu spusťte `_INSTALOVAT.bat`. Ponechte své `vysledky` a `.venv`. Podrobnosti k této opravě jsou v `OPRAVA_CAPTCHA.md`.

Pokud Python není nainstalován, použijte instalátor z [python.org](https://www.python.org/downloads/windows/) s komponentami Tcl/Tk a Python Launcher. Chyba `No module named httpx` se řeší opětovným spuštěním `_INSTALOVAT.bat`, nikoli instalací do náhodného jiného Pythonu.

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

| Soubor | Obsah |
| --- | --- |
| `firmy.csv` | Spojený přehled profil → web → e-mail → zdroj + stavy obou kroků. Pro import samotných webů používejte `kontakty.csv`. |
| `kontakty.csv` | Jeden řádek na web: e-mail, konečná URL, zdroj, stav, poznámka, další nalezené adresy. |
| `emaily.txt` | Unikátní automaticky vybrané e-maily, jeden na řádek. |
| `profily.csv` | Každý zpracovaný WLW profil a výsledek hledání firemního webu. |
| `chyby.csv` | Chyby, neúplné položky, nejednoznačné výsledky a nenalezené weby. |
| `wlw_company_urls.txt` | Získané normalizované WLW profily. |
| `websites_clean.txt` | Unikátní výchozí adresy firemních webů. |
| `prubeh.log` | Úplný protokol běhů a diagnostika. |
| `souhrn.json` | Souhrn posledního spuštění. |
| `stav.sqlite3` | Průběžně ukládané úlohy pro pokračování. Nemazat, chcete-li pokračovat. |
| `prohlizec_chromium/`, případně `prohlizec_msedge/` nebo `prohlizec_chrome/` | Samostatný profil prohlížeče daného běhu, včetně běžného stavu relace. Používá jej jen zvolený prohlížeč. |
| `beh.lock` | Zámek bránící souběžnému běhu dvou instancí do stejné složky. Přítomnost souboru sama neznamená aktivní běh. |

CSV používá UTF-8 BOM a středník pro český Excel. Hodnoty začínající znaky vzorců se neutralizují. Exporty jsou obnovovány po 20 položkách, po dokončení kroku a na konci / při zastavení. Databáze ukládá každou dokončenou položku ihned. Po tvrdém ukončení se rozpracovaná položka zopakuje; již uložené výsledky zůstanou.

Při otevřeném CSV může Excel blokovat jeho nahrazení. Soubor zavřete a spusťte pokračování: dokončená práce zůstává v databázi. Výstupní složku používejte na místním disku, nikoli na síťovém sdílení.

## Význam stavů

| Stav | Význam |
| --- | --- |
| `OK` | Web nebo e-mail byl nalezen. Neznamená ověření existence e-mailové schránky. |
| `NO_WEBSITE` | Profil nemá jednoznačně identifikovatelný veřejný firemní web. |
| `NO_EMAIL` | V omezeném rozsahu navštívených stránek se nenašel vhodný e-mail. |
| `REVIEW` | Více firemních webů nebo jen e-maily jiné domény; ruční kontrola. |
| `PARTIAL` | Část kontaktních stránek selhala a e-mail nebyl získán; při pokračování se opakuje. |
| `ERROR` | Síťová, HTTP nebo jiná konkrétní chyba; při pokračování se opakuje. |

Úspěšné i konečné negativní výsledky (`NO_EMAIL`, `NO_WEBSITE`, `REVIEW`) se při pokračování přeskočí. Pro jejich nové prověření použijte novou výstupní složku. `DONE` označuje dokončený průchod, nikoliv nalezení e-mailu pro každou firmu. Chybové položky vedou k celkovému stavu `PARTIAL`. Blokace WLW nebo neprovedené ruční ověření vede ke stavu `BLOCKED`; další WLW požadavky se neposílají. Důvod je ve sloupci `detail` a v protokolu.

## Jak se vybírají kontakty

Web se získává z jasně označeného odkazu, odpovídajících veřejných Nuxt dat nebo strukturovaných dat organizace. Náhodné URL ve skriptech se nepoužívají. Více stejně silných domén se označí `REVIEW`.

E-maily se čtou z viditelného textu a `mailto:` odkazů; podporované jsou i zápisy `[at]`, `(at)`, `[dot]`, `(dot)`. Preferuje se `info`, `kontakt`, `contact`, `office`, `mail`, `service`, `support`. Shoda firmy se posuzuje podle registratelné domény s přibaleným Public Suffix List, včetně `co.uk` a privátních suffixů. Cizí doména není automaticky považována za firemní; kandidáti zůstávají v CSV.

Na webu se nejprve zkusí úvodní stránka, potom nejvýše čtyři kontaktní / právní stránky. Přednost mají nalezené odkazy, až poté odhadované `/impressum`, `/kontakt`, `/contact`. Výběr skončí po nalezení vhodného e-mailu. Na firemních webech se JavaScript nespouští, OCR ani ověření SMTP se neprovádí. Na WLW se v prohlížečovém režimu JavaScript spouští standardním prohlížečem. Přesměrování na jinou doménu může znamenat změnu vlastníka webu; konečná URL je proto v CSV k ověření.

## Výkon a síť

Výchozí nastavení je šest pracovníků a nejméně jedna sekunda mezi začátky požadavků ke stejné registratelné doméně. WLW se načítá sekvenčně v jedné záložce; šest pracovníků se týká ostatních firemních webů. Stejný HTTP klient u těchto webů znovu používá spojení. Do fronty se zadává omezený počet úloh. Náhodná čekání po dávkách nahrazuje průběžné řízení tempa.

V HTTP režimu mají síťové chyby a HTTP 429/500/502/503/504 nejvýše tři pokusy s prodlevou; `Retry-After` se respektuje. Pokud požadované čekání překročí 60 sekund, položka se uloží jako chyba pro pozdější opakování. HTTP 404 se neopakuje. Limity: 3 MB rozbaleného obsahu na odpověď, nejvýše pět přesměrování, timeout 20 sekund na síťovou operaci. Není to absolutní limit celkového trvání úlohy. Prohlížeč automaticky neobnovuje ochrannou stránku; HTTP 403 nebo 429 na WLW zastaví běh. Při ručním ověření se pouze kontroluje lokální DOM, bez automatického obnovování stránky. Limity HTTP transportu se nevztahují na všechny obrázky a skripty, které si běžný prohlížeč sám načte.

Tempo požadavků nastavte polem prodlevy. Požadavky na neveřejné adresy se odmítají. Aplikace je místní nástroj, nikoli server pro nedůvěryhodné uživatele.

## Příkazová řádka

Z adresáře aplikace:

```bat
.venv\Scripts\python.exe -m system.run_all --query Tiefbau --max-pages 5 --output vysledky\tiefbau
.venv\Scripts\python.exe -m system.run_all --input websites_clean.txt --kind websites --output vysledky\import
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bez parametrů `python -m system.run_all` otevře okno. CLI vypisuje události jako JSON řádky, které lze přesměrovat do souboru. Návratové kódy: 0 dokončeno, 1 fatální chyba, 2 dokončeno s chybami, 3 blokováno / ověření nedokončeno, 130 zastaveno. Ctrl+C požádá o řízené zastavení. Starší přepínač `--ignore-robots` se nadále přijímá kvůli kompatibilitě, ale nemá žádný účinek; kontrola je odstraněná. `--wlw-mode browser` je výchozí; `--wlw-mode http` zvolí přímé HTTP. `--browser chromium|msedge|chrome` vybírá prohlížeč. V CLI se ruční ověření potvrzuje Enterem; bez interaktivního terminálu se při CAPTCHA běh zastaví. `--manual-timeout 600` určuje maximální čekání v sekundách.

## Struktura zdrojů

Python moduly jsou v `system/`, rozhraní v `ui/`, nastavení a závislosti v `config/`.
Přehled je v [hlavním návodu](../README.md), popis modulů v [system/README.md](../system/README.md).

## Kategorie

Při prvním spuštění se vytvoří kategorie **Tiefbau**. V rozbalovacím poli
**Kategorie** zaškrtněte jednu nebo více položek, případně použijte **Vybrat všechny**.
Novou kategorii přidáte polem pod seznamem, tlačítkem × ji smažete.
Seznam se ukládá do `config/categories.local.json` a načte se při dalším
spuštění. Smazání všech kategorií zachová prázdný seznam; sběr lze spustit až
po přidání a zaškrtnutí alespoň jedné kategorie.

Vyhledávání postupně projde všechny vybrané kategorie. Počet stránek platí
pro každou kategorii samostatně. Shodné profily a weby se zpracují jen jednou
a výsledky jsou společné v jedné složce běhu. Pro pokračování použijte stejný
výběr kategorií a nastavení, pro jiné zadání zvolte novou složku.
