# Konfigurace aplikace (config/)

Tato složka obsahuje konfigurační soubory a šablony pro WebScraper.

## Obsah složky:

- **`mysql.example.json`** – Vzorový konfigurační soubor pro připojení k databázi MySQL (EmailApp).
- **`mysql.local.json`** – Místní konfigurace připojení k databázi včetně hesla (tento soubor je soukromý a neukládá se do gitu). Vytvoří se automaticky po zadání údajů v aplikaci.
- **`categories.local.json`** – Uložený seznam naposledy použitých kategorií firem.
- **`.env.example`** – Vzor pro nastavení proměnných prostředí.
- **`requirements.txt`** – Seznam závislostí a balíčků pro Python prostředí.

Aktivní nastavení proměnných prostředí patří do `config/.env`; vzor `.env.example` se sám nenačítá. Používají se názvy `MYSQLHOST`, `MYSQLPORT`, `MYSQLDATABASE`, `MYSQLUSER`, `MYSQLPASSWORD`, `MYSQLTLS` a `MYSQLCA_FILE`. Běžně stačí nastavení přes aplikaci.
