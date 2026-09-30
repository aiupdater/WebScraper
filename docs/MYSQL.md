# Propojení s FebaMont Emailapp

Scraper může ukládat nové kontakty přímo do MySQL nebo dál vytvářet seznam
`emaily.txt`. V obou režimech lze zapnout kontrolu adres, které už Emailapp zná.

## První spuštění ve Windows

1. Aktualizujte soubory aplikace a spusťte `_INSTALOVAT.bat` (doplní PyMySQL a pywebview; viz [UI.md](UI.md)).
2. Spusťte `_SPUSTIT.bat`. Výchozí ukládání je **EmailApp (MySQL)** se zapnutým přeskakováním známých e-mailů. Připojení a načtení skupin se spustí automaticky.
3. Server `nch06.vas-server.cz`, databáze `dbemailapp_1`, uživatel `dbemailapp.1`
   a port `3306` jsou předvyplněné. Zadejte heslo a klikněte **Uložit a připojit**.
4. Aplikace načte skupiny. Tlačítko připojení databáze aktualizuje seznam po
   změnách v Emailapp. Načítání probíhá na pozadí, během něj nelze spustit sběr.
5. V **Kam uložit e-maily** vyberte soubor nebo MySQL. Pro MySQL vyberte
   **Skupina v EmailApp**; `Bez skupiny (výchozí)` uloží `group_id = NULL`.
   Číslo vedle názvu odlišuje i skupiny se stejným názvem.
6. **Přeskočit známé e-maily** je zapnuté; podle potřeby jej můžete vypnout.
7. Pro první běh s novým nastavením použijte novou výstupní složku a spusťte sběr.

Heslo a ostatní parametry se ukládají do místního `config/mysql.local.json`. Při otevření nastavení je heslo předvyplněné v maskovaném poli;
prázdné pole při uložení zachová stávající heslo. Heslo se nezapisuje do protokolu,
identity běhu ani exportů. Proměnná prostředí `MYSQLPASSWORD` má při načítání
přednost před místním souborem.

## Co znamenají jednotlivé režimy

| Režim | Kontrola existujících | Chování |
|---|---|---|
| Soubor | Vypnutá | Původní sběr do `emaily.txt`, bez připojení MySQL při běhu. |
| Soubor | Zapnutá | Načte seznam z MySQL, do `emaily.txt` exportuje nové adresy. Do MySQL nezapisuje. |
| MySQL | Vypnutá | Po dokončení vloží nalezené kontakty. Unikátní index brání duplicitám; existující kontakt zůstává beze změny. |
| MySQL | Zapnutá | Načte seznam z MySQL, přeskočí známé adresy a nové vloží do vybrané skupiny až po dokončení nebo použití aktuálních dat. |

Kontrola porovnává celé e-mailové adresy bez rozdílu velikosti písmen a okolních
mezer. Zahrnuje **všechny skupiny, nezařazené, archivované i odhlášené kontakty**.
Výběr skupiny určuje pouze skupinu nově vložených kontaktů, nikoliv rozsah kontroly.

Seznam se načítá po dávkách jednou na začátku každého běhu a používá se v paměti.
Kontrola nesmí při nedostupné databázi tiše pokračovat bez filtrování. V režimu MySQL
navíc unikátní index ošetřuje souběžné vložení stejné adresy z Emailapp. V souborovém
režimu jde o stav databáze při zahájení běhu; pozdější změny se projeví při dalším běhu.

Scraper nadále vybírá jeden vhodný kontakt na web. Pokud je preferovaný e-mail
známý, zkusí jiný vhodný e-mail na stejné stránce, případně kontaktní stránky.
**Celý web ani doménu nepřeskakuje**, protože firma může mít další neznámou adresu.
Stránku je nejprve potřeba načíst, aby bylo možné zjistit její e-maily.

## Ukládání a výpadky

Každý nález se nejprve uloží do místního `stav.sqlite3`. Do MySQL se nové kontakty
odešlou až při dokončení sběru nebo po volbě **Použít aktuální data**. Zastavený běh
proto lze ukončit a zahodit bez zanechání nových kontaktů v EmailApp. Zápisy provádí
jedno koordinační vlákno; pracovní vlákna stahující weby nesdílejí MySQL spojení.
Rozhraní používá pro seznam skupin vlastní spojení.

Při chybě zápisu se běh zastaví. Nález zůstane označený `PENDING`. Po obnovení
připojení spusťte **Spustit / pokračovat** ve stejné složce se stejným nastavením.
Nedokončené zápisy se zopakují před dalším sběrem, hotové se neopakují. Pokud server
zápis provedl, ale potvrzení se ztratilo, opakování narazí na existující adresu a
nevytvoří duplicitu; v souhrnu bude tento případ započten mezi existující.

V MySQL režimu nevzniká `emaily.txt`. Výstupní složka je stále nutná pro navázání,
protokol a kontrolní CSV s původem nálezů. `kontakty.csv` obsahuje také `mysql_stav`
a `preskocene_adresy`; `souhrn.json` uvádí počty `INSERTED`, `EXISTING`, `PENDING`
a unikátních přeskočených adres. CSV je audit průběhu, nikoli záruka úspěšného
zápisu všech uvedených adres; rozhoduje `mysql_stav`.

Změna cíle, skupiny, filtru nebo databáze vyžaduje novou výstupní složku, aby se
rozpracované výsledky omylem nezapsaly jinam. Změna hesla, TLS či prodlevy pokračování
neblokuje. Staré běhy bez MySQL lze obnovit s původním souborovým nastavením.

## Mapování na Emailapp

Ověřeno proti [mysql-struktura.sql](https://github.com/aiupdater/febamont-emailapp/blob/main/mysql-struktura.sql)
a vložení kontaktu v `backend.php`.

| Údaj | Tabulka / sloupec |
|---|---|
| Nabídka skupin | `contact_groups.id`, `contact_groups.name` |
| Kontrola existujících adres | `emails.email` napříč celou tabulkou |
| Nový kontakt | `emails.email`, `emails.email_domain`, `emails.group_id` |
| Zabránění duplicitám při zápisu | existující unikátní index `emails.email` |

Není potřeba měnit schéma. Databázový účet potřebuje `SELECT` na `contact_groups`
a `emails` a pro ukládání `INSERT` na `emails`. Scraper používá parametrizované SQL.
Nevykonává UPDATE ani DELETE existujících kontaktů a nemění jejich skupiny,
potvrzení, odhlášení, archivaci či historii. Novým kontaktům zůstávají výchozí
hodnoty schématu, včetně nepotvrzeného stavu. Nezakládá záznamy ve frontě rozesílek,
neodesílá zprávy a neprovádí validaci doručitelnosti ani obnovu MX cache Emailapp.

## Nastavení připojení

`config/mysql.example.json` obsahuje vzor bez hesla. Lze jej zkopírovat jako
`config/mysql.local.json`. Proměnné prostředí mají přednost před JSON:

- `MYSQLHOST`, `MYSQLPORT`, `MYSQLDATABASE`, `MYSQLUSER`
- `MYSQLPASSWORD`
- `MYSQLTLS` (`true` nebo `false`), `MYSQLCA_FILE`

Výchozí TLS ověřuje certifikát i jméno serveru. Pokud hosting používá vlastní CA,
vyberte její PEM soubor. Pro server bez TLS lze šifrování v dialogu výslovně vypnout;
nejprve ověřte možnosti připojení u hostingu. Kód TLS automaticky nevypíná při chybě.
Spojení má timeout 8 sekund, čtení a zápis 12 sekund. Parametry vycházejí z
[dokumentace PyMySQL](https://pymysql.readthedocs.io/en/latest/modules/connections.html).

Vzdálený přístup musí povolovat veřejnou IP počítače, na kterém aplikace běží.
Chyba připojení se zobrazí česky s číselným kódem, bez syrového výpisu ovladače.

## Příkazový řádek

Přihlašovací údaje načte z lokálního JSON / prostředí; heslo se nepředává argumentem:

```bat
.venv\Scripts\python.exe -m system.run_all --query Tiefbau --output vysledky\mysql-tiefbau --save-to mysql --group-id 7 --skip-existing
```

`7` nahraďte skutečným ID ze seznamu skupin. Bez `--group-id` se vloží nezařazený kontakt.
Pro soubor použijte `--save-to files`; `--skip-existing` funguje i v tomto režimu.

## Ověření této změny

`python -m unittest discover -s tests -v`: 64 úspěšných testů v Linuxu s Pythonem 3.12.
Zahrnují původní testy scraperu a testy MySQL adaptéru, filtru, vybraných skupin,
výpadku před zápisem i po potvrzení na serveru, opakování běhu a oddělení hesla.
MySQL a prohlížeč jsou v testech nahrazené simulacemi; běží skutečné místní SQLite
ukládání. Kompilace všech změněných Python modulů a kontrola diffu také prošly.

Živá MySQL nebyla ověřena: prostředí nedokázalo přeložit `nch06.vas-server.cz`
(DNS chyba). Do produkční databáze nebyla odeslána testovací data. Zobrazení okna
ve Windows a BAT soubory zde nebyly otestovány. První praktické ověření proveďte
přes **Připojit / obnovit skupiny**, potom malým během s jednou stránkou.
