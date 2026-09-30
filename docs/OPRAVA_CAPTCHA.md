# Oprava HTTP 405 / Human Verification

## Co tato verze řeší

Na doložené odpovědi AWS WAF nestačí samotný HTTP klient: stránka vyžaduje JavaScript a ruční CAPTCHA. Nová výchozí volba **Prohlížeč + ruční ověření** otevře skutečný prohlížeč. Ruční ověření provede uživatel a aplikace potom pracuje ve stejné relaci. Nejde o automatický řešič CAPTCHA a nelze zaručit, že server další automatizaci přijme.

## Aktualizace ve Windows

1. Zavřete starou aplikaci.
2. Rozbalte ZIP. Soubory z jeho složky `wlw_studio` překopírujte do původního adresáře aplikace; aktualizujte i `config/requirements.txt`, `_INSTALOVAT.bat` a složku `system/`. Složku `vysledky` ponechte.
3. Spusťte `_INSTALOVAT.bat`. Doplní Playwright a stáhne Chromium. Instalátor používá existující `.venv`, pokud existuje.
4. Spusťte `_SPUSTIT.bat`. Nadpis aplikace je nyní **WebScraper**.
5. Vyberte **Prohlížeč + ruční ověření**, prohlížeč **Chromium**, počáteční stránku **1**, počet stránek **1** a prodlevu **2** sekundy pro první malý běh.
6. Kontrola robots.txt je odstraněná; není potřeba nic přepínat.
7. Zvolte původní výstupní složku se stejným zadáním pro pokračování, nebo novou pro test s jiným počtem stránek. Nově lze změnit způsob přístupu u stejné úlohy bez nové složky.
8. Klikněte **Spustit / pokračovat**. V otevřeném prohlížeči případnou CAPTCHA ručně dokončete. Vraťte se do aplikace a stiskněte **Ověřeno — pokračovat**.

Během ověření prohlížeč nezavírejte a nepřecházejte v jeho hlavní záložce na jiné stránky. Tlačítko potvrzení samo ověření neprovádí. Pokud zůstane zobrazená ochranná stránka, sběr se nerozběhne. Na ověření se čeká nejvýše 10 minut. Zastavení nebo zavření okna uloží práci; další spuštění opakuje nedokončenou položku.

## Výběr prohlížeče

Výchozí Chromium je verze dodávaná s Playwright. Pokud jej instalátor nedokáže stáhnout, aplikace umí také již nainstalovaný **Microsoft Edge** nebo **Google Chrome**. Výběr jiného prohlížeče je možnost kompatibility, nikoli záruka přijetí serverem. Aplikace neotevírá váš běžný osobní profil: pro každý běh a prohlížeč vytváří vlastní adresář `prohlizec_*`.

Veškerý profil prohlížeče ponechte na svém počítači. Pro předání diagnostiky stačí `chyby.csv` nebo konkrétní řádky `prubeh.log`; profil s relací není potřeba.

## Co znamená výsledek

| Hlášení | Co udělat |
| --- | --- |
| `CAPTCHA_REQUIRED` / „Čekám na ruční ověření“ | Dokončit výzvu v otevřeném prohlížeči a potvrdit tlačítkem v aplikaci. |
| `MANUAL_TIMEOUT` | Ověření nebylo potvrzeno včas. Spustit pokračování ve stejné složce. |
| `BROWSER_CLOSED` | Okno bylo zavřeno. Spustit pokračování. |
| `BROWSER_START_FAILED` / `BROWSER_MISSING` | Spustit instalátor, případně zvolit již nainstalovaný Edge/Chrome. |
| `ACCESS_DENIED` | Server přístup odmítá; sběr se zastaví. Ruční ověření samo nezaručuje přístup. |
| `RATE_LIMITED` | Respektovat uvedenou dobu čekání, případně snížit tempo; aplikace další WLW stránky nezkouší. |
| `CONTENT_NOT_READY` | Po načtení chybí očekávané výsledky/profil; ověřit adresu, dotaz a vzhled stránky. |

Pokud WLW přístup odmítá i po ověření, aplikace to neopravuje opakovaným obnovováním stránky. Pro automatický provoz je pak potřeba povolený datový přístup od provozovatele. Import webů přes CLI (`--input soubor.txt --kind websites --output slozka`) umožní mezitím zpracovat firemní weby z vašeho vlastního seznamu nebo exportu bez návštěv WLW.

## Ověření dodávky

Testy zahrnují rozpoznání dodaného typu odpovědi, pozastavení a pokračování, chybné předčasné potvrzení, odlišnou stránku, zavření prohlížeče, zastavení uživatelem, omezení požadavků a zachování starého stavu. Používají připravené HTML a simulovaný prohlížeč. V tomto prostředí se nepodařilo stáhnout skutečný Chromium (timeout); Windows GUI a skutečné ruční ověření proti WLW proto nebyly ověřeny. Výpis je v `TESTY.txt`.
