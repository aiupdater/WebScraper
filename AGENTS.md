# Pravidla práce na WebScraperu

## Komunikace a rozsah

- S uživatelem komunikuj česky, pokud výslovně nepožádá o jiný jazyk.
- Před zahájením práce přečti `docs/project/PROJECT_CONTEXT.md` a relevantní záznamy v `docs/project/DECISIONS.md`.
- Ověř skutečný stav zdrojů; historii chatu ani paměť nepovažuj za aktuálnější než repozitář.
- Pokud uživatel požádá pouze o audit nebo nejprve vyžaduje schválení, neupravuj kód před jeho výslovným souhlasem.
- Zachovej nesouvisející lokální změny a nikdy neodstraňuj uživatelská data, výsledky ani přihlašovací údaje.

## Implementace a ověření

- Před změnou určete její hranice a akceptační kritéria. Změň pouze soubory potřebné pro daný výsledek.
- Desktopové UI je navázané na DOM identifikátory a obsluhu v `ui/app.js`; při vizuálních úpravách zachovej existující funkční vazby nebo je současně uprav a otestuj.
- Chraň podporu obou portálů (`wlw` a `11880`), pokračování uloženého běhu, původ kategorií a odložené ukládání do MySQL, pokud zadání výslovně nemění některou z těchto oblastí.
- Tajné údaje patří pouze do lokálních ignorovaných souborů, zejména `config/mysql.local.json`. Nikdy je nevkládej do dokumentace, testů ani commitu.
- Pro přiměřené ověření používej projektové `.venv`; základní příkazy jsou uvedené v `docs/project/PROJECT_CONTEXT.md`.
- Neoznačuj výsledek za ověřený, pokud testy neběžely, proběhlo `Ran 0 tests`, kontrola skončila chybou prostředí nebo chybí odpovídající UI/desktop důkaz.

## Průběžná projektová paměť

- Po dokončení úkolu aktualizuj `docs/project/PROJECT_CONTEXT.md` pouze tehdy, když se změnil aktuální stav, architektura, ověřovací postup, známé omezení nebo další priorita.
- Do `docs/project/DECISIONS.md` přidej záznam pouze při skutečném dlouhodobém rozhodnutí. Starý záznam nemaž; při změně jej označ jako nahrazený a odkaž na nové rozhodnutí.
- Nezapisuj průběh konverzace, dočasné pokusy ani podrobnosti zjistitelné přímo ze zdrojového kódu. Dokumenty mají zůstat krátké a použitelné pro další chaty.
- Před ukončením práce zkontroluj soulad změn v kódu, testech, uživatelské dokumentaci, `docs/project/PROJECT_CONTEXT.md` a `docs/project/DECISIONS.md`.
