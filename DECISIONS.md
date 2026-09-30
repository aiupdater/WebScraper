# WebScraper — dlouhodobá rozhodnutí

Tento soubor zachycuje rozhodnutí, která mají ovlivnit více budoucích úkolů. Nové rozhodnutí přidej pouze tehdy, když bude užitečné i pro další chaty. Existující záznam nemaž; změněné rozhodnutí označ jako nahrazené a připoj odkaz na nové ID.

## D-001: Repozitářová dokumentace je zdroj trvalého projektového kontextu

- Datum: 30. 9. 2026
- Stav: platí
- Rozhodnutí: Každý chat pracující na repozitáři načte `AGENTS.md`, `PROJECT_CONTEXT.md` a relevantní záznamy tohoto souboru. Po významné změně aktualizuje společný kontext a případně přidá nové rozhodnutí.
- Důvod: Historie jednotlivých chatů je oddělená a automatická paměť nemusí být okamžitá ani úplná. Verzionované soubory poskytují všem chatům stejnou kontrolovatelnou výchozí pravdu.
- Důsledek: Do těchto dokumentů se nezapisují přepisy chatů ani každá drobná změna. Stav musí být stručný, aktuální a ověřitelný proti repozitáři.

## D-002: Jeden chat řeší jeden konkrétní výsledek

- Datum: 30. 9. 2026
- Stav: platí
- Rozhodnutí: Související práce zůstává v projektu WebScraper, ale samostatné výsledky se řeší v samostatných pojmenovaných chatech.
- Důvod: Oddělené chaty omezují míchání témat; společné repozitářové dokumenty přenášejí jen kontext, který má být dlouhodobý.
- Důsledek: Nový chat nemá kopírovat celý předchozí rozhovor. Má převzít aktuální stav ze zdrojů a společné dokumentace.

## D-003: Audit a implementace jsou oddělené kroky, když uživatel vyžaduje schválení

- Datum: 30. 9. 2026
- Stav: platí
- Rozhodnutí: Pokud zadání požaduje audit bez úprav nebo schválení před implementací, nejprve se pouze prozkoumá stav a předloží zjištění. Kód se mění až po výslovném souhlasu.
- Důvod: Uživatel potřebuje kontrolovat hranice zásahu a rozhodnutí s dopadem na stávající funkce.
- Důsledek: Diagnostické kontroly mohou být provedeny, ale nesmí se při nich nenápadně opravovat kód.

## D-004: Důkaz odpovídá tvrzení o výsledku

- Datum: 30. 9. 2026
- Stav: platí
- Rozhodnutí: Úspěch lze deklarovat jen na základě odpovídajícího ověření. Unit testy, UI smoke, desktop smoke, živý portál a produkční MySQL jsou různé úrovně důkazu a nesmějí se zaměňovat.
- Důvod: `Ran 0 tests`, statický audit nebo chyba prostředí nepotvrzují funkční stav aplikace.
- Důsledek: Každé předání uvede skutečně spuštěné kontroly, jejich výsledek a neověřené oblasti.
