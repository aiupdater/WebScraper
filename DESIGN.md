---
version: alpha
colors:
  primary: "#4F46E5"
  primary-focus: "#4338CA"
  accent-dark: "#5F5AF6"
  info: "#0EA5E9"
  success: "#10B981"
  warning: "#FF9800"
  danger: "#FF5724"
  canvas-light: "#F8FAFC"
  surface-light: "#FFFFFF"
  text-light: "#475569"
  canvas-dark: "#192132"
  surface-dark: "#26334D"
  text-dark: "#C2C9D6"
typography:
  interface:
    fontFamily: "Poppins, Segoe UI, sans-serif"
  data:
    fontFamily: "Inter, Segoe UI, sans-serif"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "16px"
spacing:
  unit: "4px"
components:
  card:
    rounded: "8px"
  navigationRail:
    width: "80px"
  settingsPanel:
    width: "240px"
  header:
    height: "61px"
---

# WebScraper designový systém

## Overview

WebScraper je pracovní desktopový nástroj pro dlouhé datové běhy. Rozhraní má působit jako přesný, klidný a důvěryhodný řídicí panel: uživatel musí během okamžiku poznat připravenost databáze, stav sběru, aktuální krok a kvalitu výsledku. Vizuální základ vychází přímo z lokální šablony Lineone 3.1.1, zejména z CRM Analytics dashboardu a jeho zdrojových komponent.

Pamětihodným prvkem je barevná navigační a stavová ikonografie. Barvy neslouží jako dekorace: indigo označuje hlavní akce, tyrkysová informace, zelená úspěch, oranžová čekání a červenooranžová chybu nebo nevratnou akci. Zbytek rozhraní zůstává střídmý.

Rozhraní nesmí připomínat marketingovou stránku, generický gradientový dashboard ani směs původního EmailApp CSS s dodatečným skinem. V produkci existuje jediná sada tokenů a jediný vlastník komponentových pravidel.

## Colors

Světlý motiv používá neutrální Slate plátno, bílé karty a modrošedý text. Tmavý motiv používá Lineone Navy škálu. Sémantická role barvy se mezi motivy nemění. Hlavní akce používají `primary`, focus používá `primary-focus`; nevratné akce používají `danger` pouze v posledním potvrzovacím kroku.

Barevné ikonky používají tónovaný podklad přibližně s 8–12% krytím a plnou barvu symbolu. Stav nesmí být sdělen pouze barvou; vždy jej doplňuje text, tvar nebo přístupný název.

## Typography

Poppins je hlavní písmo navigace, nadpisů, ovládacích prvků a formulářů. Inter se používá pro tabulková data, čítače, časy a technické hodnoty. Obě rodiny jsou přibalené lokálně v `ui/assets/fonts`; vzdálené fonty ani CDN nejsou povolené.

Základní velikost desktopového rozhraní je 14 px. Husté pomocné popisky mohou klesnout na 11–12 px, ale nesmějí nahrazovat skutečný label. Číselné statistiky používají tabulární číslice.

## Layout

Na desktopu je vlevo 80px ikonová lišta, vedle ní 240px nastavení a vpravo hlavní pracovní plocha. Dokud nevzniknou další skutečné sekce, lišta obsahuje pouze tlačítko pro otevření a skrytí nastavení; nehotové navigační odkazy se nezobrazují. Po skrytí nastavení se hlavní pracovní plocha plynule roztáhne. Hlavička má přibližně 61 px a logo FEBA-MONT stojí vlevo před názvem produktu. Hlavní plocha používá modulární karty a 4px násobky rozestupů. Tabulka vlastní svůj posuvník; dlouhé nastavení vlastní svůj posuvník. Minimální podporované okno zůstává 900 × 560.

Při užším okně může lišta klesnout na 64 px. Mobilní skládání je sekundární; nesmí poškodit desktopový WebView2 ani vytvořit nedostupná pole při 200% zvětšení.

## Elevation & Depth

Statické karty ve světlém motivu používají pouze měkký Lineone stín. Tmavý motiv staví hierarchii hlavně na rozdílu Navy ploch a hran, nikoli na výrazných stínech. Dialog je jediná vrstva s výraznější hloubkou a rozostřeným backdropem.

## Shapes

Ovládací prvky a karty používají 8px základní radius. Výraznější 12–16px radius je vyhrazen pro velké dialogy, prázdné stavy a barevné ikonové podklady. Badge a stavové tečky mohou být plně zakulacené.

## Components

Tlačítka mají jednotné kombinace důrazu (`solid`, `outline`, `ghost`) a významu (`primary`, `success`, `warning`, `danger`, `neutral`). Busy stav nemění rozměr tlačítka.

Každý interaktivní prvek má hover, pressed, focus-visible, disabled a případně busy stav. Ikonová tlačítka mají český přístupný název a tooltip. Všechny ikony jsou lokální SVG; dekorativní ikony jsou skryté asistivním technologiím.

Úvodní preloader zakrývá nehotové rozhraní. Zobrazuje značku WebScraperu, animovaný vícebarevný kruh, aktuální fázi a klidný tónovaný podklad. Postupně oznamuje načtení UI, propojení s Pythonem a přípravu EmailApp/MySQL. Zmizí až po dokončení bootstrapu a úvodním výsledku databázového připojení; při chybě zobrazí srozumitelný stav a dovolí vstoupit do aplikace s dostupným nastavením. Musí mít bezpečný timeout a respektovat omezený pohyb.

Animace používají převážně 160–240 ms a křivku `cubic-bezier(.4, 0, .2, 1)`. Povolené jsou jemné odhalení aplikace, stavová pulsace, progress a mikrointerakce ikon. Nepoužívají se nekonečné dekorativní pohyby mimo preloader nebo aktivní pracovní stav.

Změny většího rozložení a dialogy mohou používat 280–420 ms s přirozenou křivkou `cubic-bezier(.16, 1, .3, 1)`. Otevření i zavření musí být animované jako jeden systém: obsah, transformace a backdrop nesmějí blikat ani skokově mizet. WebView2 používá nativní CSS a Web Animations API; externí motion knihovna se přidá až tehdy, když bude potřeba časová osa nebo koordinace, kterou nativní vrstva neumí udržet.

## Do's and Don'ts

- Používej jeden tokenový systém a jednu komponentovou vrstvu v `ui/app.css`.
- Zachovej všechna funkční DOM ID a ověř jejich vazbu na `ui/app.js`.
- Používej barevnou ikonografii s jasným významem.
- Rezervuj prostor pro loading, chyby a dynamické zprávy, aby layout neskákal.
- Respektuj `prefers-reduced-motion` a uživatelskou volbu omezení animací.
- Nevkládej Tailwind, Alpine.js, vzdálené fonty ani CDN do produkčního UI.
- Nepřidávej další override vrstvu nad staré CSS; stará prezentace se nahradí jako celek.
- Nepoužívej `alert`, `confirm` ani `prompt`; nevratné akce řeší vlastní přístupný dialog.
