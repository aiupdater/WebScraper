# WebScraper — kontrakt chování desktopového UI

Tento dokument doplňuje kořenový `DESIGN.md`. Vzhled vlastní `DESIGN.md`; tento soubor vlastní pozorovatelné chování, stavy a obnovu.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
| --- | --- | --- | --- | --- |
| Select/Listbox | Nativní WebView2 select | `ui/index.html` + `ui/app.css` | native | klávesnice, změna hodnoty a čitelnost v obou motivech v UI smoke |
| Form | Formulář nastavení MySQL | `ui/index.html` + `ui/app.js` | authored validation | chyby u polí, submit a obnovení focusu v UI smoke |
| Scrollbar | Globální Lineone scrollbar a vlastní scroll panelů | `ui/app.css` | global + panel geometry | 900 × 560, 200% zoom a tabulka/nastavení samostatně |
| Toast | Jediný aplikační toast | `ui/index.html#toast` + `ui/app.js` | success / info / error | viditelnost, live region a automatické skrytí v UI smoke |

Nativní výběry jsou záměrné: WebScraper přijímá systémový popup WebView2 a vlastní pouze vzhled zavřeného ovládacího prvku. Nevytváří vlastní ARIA listbox.

## Start aplikace

1. HTML se otevře s viditelným preloaderem a skrytým nebo inertním pracovním rozhraním.
2. JavaScript čeká na `window.pywebview.api` a oznámí fázi „Připojuji aplikační jádro“.
3. Úspěšný `bootstrap` naplní kategorie, cestu běhu, nastavení a základní stav.
4. Pokud je dostupné uložené MySQL heslo, aplikace vyvolá `connect_database` a preloader čeká na událost `groups` nebo `groups_error`.
5. Bez uloženého hesla se databázová fáze označí jako vyžadující nastavení; aplikace se zpřístupní a následně otevře nastavení MySQL.
6. Preloader má bezpečný timeout. Při zpoždění nabídne pokračování do rozhraní se stavovou zprávou; nesmí aplikaci navždy zablokovat.
7. Odhalení aplikace obnoví focus na hlavní nadpis nebo první smysluplnou akci. Při omezeném pohybu proběhne bez animace.

## Stav databáze

Stavy jsou `připojuji`, `připojeno`, `nepřipojeno` a `chyba`. Každý má text i ikonu; barevná tečka je pouze doplněk. Selhání MySQL neblokuje otevření UI ani lokální výstup, ale zablokuje spuštění s cílem MySQL, dokud nejsou skupiny připravené.

## Běh scraperu

- `Spustit sběr` přejde do busy stavu, zabrání dvojímu spuštění a po přijetí výsledku zobrazí `Zastavit sběr`.
- `Zastavit sběr` zachová obnovitelný stav.
- Zastavený běh nabízí `Pokračovat`, `Použít aktuální data` a `Zahodit běh`.
- `Zahodit běh` používá vlastní potvrzovací dialog s přesným následkem a počátečním focusem na bezpečné akci.
- Dokončený běh nabízí přípravu nového běhu bez míchání předchozích výsledků.

## Výsledky a tabulka

Tabulka používá nativní sémantické `<table>`. Zachovává kategorii a stránku původu. Vždy existuje stabilní loading, empty, no-results, partial/error a populated stav. Vyhledávání má vlastní tlačítko pro okamžité vymazání a vrácení focusu.

Tabulka vlastní vnitřní scroll. Nastavení vlevo vlastní oddělený scroll. Změna velikosti okna ani loading nesmí přesunout hlavní ovládací tlačítka.

## Navigace a nastavení

Při čekajícím přepnutí se blokují další kliknutí, ale ikona prohlížeče nebledne; pulzuje jen stavové kolečko. Vypnutý stav je tlumený. Nastavení a Prohlížeč mají neutrální barvu odpovídající ikonám hlavičky. Windows startuje prohlížeč nativně minimalizovaný a bez emulace viewportu, aby obnova uložené pozice nezobrazila okno před jeho skrytím.

Tlačítko `browser-toggle` ovládá stejné samostatné Playwright okno. Stavy jsou vypnutý, skrytý a zobrazený; CAPTCHA je nezávislý příznak. Bridge jen zařadí jeden příkaz, UI čeká na potvrzenou událost a blokuje duplicitní kliknutí. Bootstrap vrací skutečný poslední stav. Skrytí nezastaví sběr, minimalizované okno další kliknutí obnoví. CAPTCHA neotevírá okno automaticky; potvrzení „Ověřeno — pokračovat“ zůstává nutné. První výzva během minimalizace vyvolá jeden pokus o Windows toast. Bez bezpečné identifikace controller neovládá HWND: ověřená vazba CDP zpřístupní vlastní stránku, při selhání přeruší obnovitelný běh a nabídne viditelné pokračování. Rozhodnutí: D-007.

Levá ikonová lišta zobrazuje nastavení a sběrný prohlížeč. Tlačítko nastavení používá `aria-controls` a `aria-expanded`, nemění URL ani neposouvá dokument na kotvu. Skrytí nastavení rozšíří hlavní pracovní plochu; opětovné otevření obnoví samostatný scroll nastavení.

## Dialogy a zpětná vazba

Používají se pouze vlastní `<dialog>` komponenty s titulkem, popisem, Escape, obnovením focusu a českými názvy akcí. Toast potvrzuje úspěch; opravitelné chyby zůstávají také u příslušného pole nebo sekce.

## Přístupnost a pohyb

Cílem je WCAG 2.2 AA. Každé ovládání je dostupné klávesnicí, má viditelný focus a minimálně textový nebo přístupný název. Animace jsou významové, krátké a vypnutelné pomocí uživatelské volby i `prefers-reduced-motion`.

## Ověřovací brány

Po implementaci musí projít celá unit sada, `tests/ui_smoke.py`, `tests/desktop_smoke.py`, `tests/browser_desktop_smoke.py`, `git diff --check` a vizuální kontrola světlého/tmavého motivu při 1320 × 850, 1366 × 768, 1000 × 650 a 900 × 560. Samostatně se ověří úspěšný bootstrap, chybějící heslo, úspěšné MySQL skupiny, chyba MySQL, timeout preloaderu, omezený pohyb a všechny stavy řízení běhu. Nasazovací brány pro prohlížeč zahrnují skutečnou CAPTCHA, Windows upozornění a změny monitorů/DPI; fixture test je nenahrazuje.
