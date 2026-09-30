# Audit původního scraperu

Zkontrolováno všech pět nahraných souborů. Náhrada je dodána jako samostatný projekt, nikoliv jako pět navzájem závislých subprocess skriptů. Původní soubory nejsou v balíčku potřeba.

| Původní soubor | Zjištění a dopad | Náhrada |
| --- | --- | --- |
| `1_extract_wlw_urls(1).py` | Živá kontrola potvrdila, že `/de/suche?q=Tiefbau` nyní vrací HTML bez profilových odkazů. Binární hledání poslední stránky předpokládá monotónní existenci výsledků; timeout či HTTP chyba je zaměněna za konec. Neřeší opakující se stránky. Dotaz není URL-enkódován. Název souboru nahrazuje pouze mezery. Dávky přepisují společné vstupy, nemají skutečné pokračování. Chyba následného procesu končí `exit()` bez nenulového statusu. | Aktuální `/de/suche/<výraz>/page/<n>`, podpora URL z prohlížeče, explicitní limit a detekce opakování, oddělené chyby, průběžná databáze a zámek běhu. Prázdné nebo opakované výsledky nejsou vydávány za potvrzený konec. |
| `2_extract_websites(1).py` | Vybírá z libovolných URL v HTML včetně skriptů a technických domén. První slovo firemního slugu je slabá heuristika. Přesný blacklist nezachytí všechny subdomény. Redirect parametry se parsují ručně. Sériový průchod, velká část chyb se projeví až v CSV a průběh se vypisuje jen po 50 položkách. | Explicitní webové odkazy, JSON-LD a homepage z veřejných Nuxt dat ověřená proti přesnému slugu profilu; nejednoznačnost zůstává k ruční kontrole. Parser query parametrů, omezená souběžnost, znovupoužití spojení a okamžité ukládání položek. |
| `3_clean_websites(1).py` | Odstraňuje `www` i ze skutečně navštěvované adresy, což může poškodit dostupnost. Doména se bere z `netloc`, nikoli `hostname`. Nedostatečná validace schémat a hostů, slabý blacklist. Poslední položka přepíše variantu domény bez promyšlené preference. | Navštěvovaná adresa zachovává `www`; normalizace pouze v deduplikačním klíči. Validace HTTP(S), hostů a portů, odfiltrování technických subdomén, preference existující HTTPS varianty. |
| `4_email_scraper(1).py` | Dvacet vláken přepisuje `scraper_progress.txt` režimem `w`; stav není použitelný pro pokračování. E-mailový regex prohledává celý HTML zdroj včetně skriptů. Shoda pomocí podřetězce zamění cizí doménu za firemní; selhává u veřejných suffixů typu `co.uk`. Kontaktní stránky se hádají a vrací se první sada adres i tehdy, když není firemní. Nová HTTP spojení pro každou URL; žádné retry. Podmínka `len(collected) % 50 == 0` negarantuje pravidelné ukládání a může opakovaně zapisovat stejný stav. Chybějící vstup může skončit úspěšným návratovým kódem. | Výsledky zapisuje jediný koordinátor do SQLite; e-mail se páruje podle registratelné domény a priorit, zachovává zdroj. Skutečné kontaktní odkazy mají přednost. Cizí adresy se neztrácejí, ale jdou do kontroly. Retry, časové limity, průběžné exporty a rozlišené stavy. |
| `run_all.py` | Očekává názvy bez `(1)`, zatímco čtyři nahrané soubory mají tento suffix. Neřeší instalaci závislostí. Spouští jen kroky 2–4 a po zdánlivém úspěchu maže i mapovací CSV, tedy důležitou auditní stopu. Nulový exit kód podřízených skriptů nemusí znamenat skutečný úspěch. | Jediná orchestrace kroků 1–4, GUI i CLI, izolované prostředí `.venv`, žádné mazání výsledků a rozlišené exit kódy. |

## Rozhodnutí a omezení

Původní režimy „počet dávek“ a „ptát se po každé dávce“ nahrazuje rozsah stránek, tlačítko zastavení a pokračování ze stejné složky. Jde o změnu ovládání, nikoli kompatibilní náhradu starých souborových protokolů. Původní `email_output_name.txt` se nepoužívá.

Každý pracovník zpracovává jednu síťovou úlohu. Přidávání pracovníků nezvyšuje neomezeně rychlost vůči WLW: požadavky ke stejné doméně jsou časově omezeny. Přínos souběžnosti je hlavně u různých firemních webů. Konkrétní násobek zrychlení nebyl měřen.

Pro přesnost má přednost nevybrat žádný web před zvolením technického nebo cizího odkazu. Totéž platí pro e-maily na jiné doméně. To může snížit počet automaticky vybraných kontaktů, proto CSV uchovává kandidáty a důvody. Neověřuje se doručitelnost ani aktuálnost schránky.

Při původním auditu kontrola robots.txt blokovala WLW. V aktuální verzi je tato kontrola odstraněná. Živě byla ověřena jedna stránka vyhledávání a jeden profil, nikoli kompletní sběr. Windows GUI nebylo vizuálně ověřeno.

## Podklady k technickým rozhodnutím

- [HTTPX: clients a znovupoužití spojení](https://www.python-httpx.org/advanced/clients/).
- [Aktuální vyhledávání Tiefbau](https://www.wlw.de/de/suche/tiefbau) a [ověřený profil](https://www.wlw.de/de/firma/geser-gmbh-949554).
- [Robots pravidla WLW](https://www.wlw.de/robots.txt).

Kontrola provedena 16. 9. 2026. Změna HTML, pravidel nebo ochrany webu může vyžadovat úpravu parseru. Kontrolní HTML není přibalené; balíček neobsahuje nasbíranou databázi firem ani kontakty ze živého webu.


## Doplnění po chybě HTTP 405

Uživatel doložil HTML s titulkem Human Verification a skripty AWS WAF CAPTCHA. V této konkrétní odpovědi znamená 405 výzvu k ověření, nikoli požadavek přepnout GET na POST. Nový `access.py` rozlišuje WAF CAPTCHA, prohlížečovou challenge, obecnou 405, 403 a 429.

Nové řešení načítá WLW ve viditelném prohlížeči přes Playwright. Ověření provádí uživatel; aplikace před pokračováním vyžaduje jeho potvrzení a kontroluje obsah, stav i původní URL. Prohlížeč používá samostatný profil v adresáři běhu; jeho stav se nepřenáší do HTTPX. Celý životní cyklus Playwright zůstává v jednom vlákně, firemní weby jsou nadále souběžné.

Blokovaný požadavek nezanechá prázdný úspěšný výsledek. Při přetrvávajícím zákazu nebo nedokončeném ověření se další profily neposílají, výstupy se uloží a úloha skončí stavem BLOCKED. Přepnutí režimu je nyní možné u stejného zadání ve stejné výstupní složce.

Oprava je ověřena unit a integračními testy se simulovaným prohlížečem. Stažení skutečného prohlížeče v tomto prostředí selhalo na síťovém timeoutu; úspěšné vyřešení skutečné WLW CAPTCHA nebylo ověřeno. Není tvrzeno, že Playwright zaručuje přijetí automatizovaného přístupu.

Podklady: [AWS WAF CAPTCHA / Challenge](https://docs.aws.amazon.com/waf/latest/developerguide/waf-captcha-and-challenge-actions.html), [Playwright – instalace a práce s vlákny](https://playwright.dev/python/docs/library), [perzistentní kontext prohlížeče](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context).
