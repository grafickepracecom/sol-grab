# sol-grab

Čtení dat ze **Školy OnLine (ŠOL)** a jejich zobrazení. Prototyp — první krok
k signage aplikaci do sborovny (rozvrhy tříd, probíhající a příští hodina, akce tříd).

Napsáno v Pythonu **jen se standardní knihovnou** — žádný `pip install`, žádný
build. Běží pod Python 3.10+.

## Rychlý start

```bash
cd /var/www/sol-grab
cp .env.example .env         # doplňte SOL_USERNAME a SOL_PASSWORD
chmod 600 .env

python3 web.py               # http://localhost:8081/
python3 web.py --port 9000
python3 web.py --vypis       # vypíše HTML na stdout

bin/dump.py denni            # rozvrh všech tříd do konzole
```

Stránka ukazuje rozvrh všech tříd na dnešek, zvýrazňuje právě probíhající hodinu
a barevně odlišuje školní akce od běžné výuky.

## Odolnost proti výpadku

Zdrojem je cizí aplikace, takže se počítá s tím, že se rozbije:

* **Cache** (`.rozvrh-cache.json`, `SOL_CACHE_TTL`, výchozí 120 s) — během TTL se
  na ŠOL nechodí znovu; signage si stránku tahá pořád dokola a ŠOL to nezatěžuje.
* **Výpadek ŠOL** — když se načtení nepovede, zobrazí se poslední úspěšně načtený
  rozvrh se žlutým upozorněním, jak je starý. Obrazovka ve sborovně kvůli
  krátkému výpadku nezhasne.
* **Změna HTML ŠOL** — parser strukturu kontroluje a hlásí konkrétně, co chybí
  (`StrukturaZmenena`: chybí mřížka / hlavička hodin / třídy / rozbité časy),
  místo aby tiše vrátil prázdný rozvrh.
* **Chybné přihlášení** — pozná se podle chybějící cookie `.ASPXAUTH` a hlásí se
  jako taková, ne jako prázdná stránka.
* Chybová stránka ukazuje jednu větu, **traceback jde do logu serveru**.

## Odkud se data berou (a proč ne z REST API)

ŠOL má neveřejné REST API, které používá jejich mobilní aplikace, a server k němu
publikuje **vlastní OpenAPI popis** — bez přihlášení, 107 endpointů:

```
https://aplikace.skolaonline.cz/solapi/swagger/v1/swagger.json
```

Je to spolehlivější zdroj pravdy než komunitní dokumentace
([Libre-SkolaOnline/API-docs](https://github.com/Libre-SkolaOnline/API-docs),
[reŠOL](https://codeberg.org/resol/resol)), které popisují jen žákovskou část.
Vypíše ho `bin/dump.py endpointy`.

**Rozvrh tříd z něj ale nedostaneme.** Jediný rozvrhový endpoint
`/api/v1/timeTable` je v popisu samotné ŠOL definovaný jako „rozvrh za požadované
období ve školním roce **pro přihlášeného uživatele**“. Účet, který sám neučí,
tudy nedostane nic — ověřeno, že vrací prázdné `days`:

- s `ClassId` každé z 13 tříd (a `ClassId` se *neignoruje* — nesmyslné ID vrací
  404 „Není k dispozici požadovaná třída“, takže parametr projde validací),
- s `StudentId` skutečného žáka získaného z modulu třídní knihy,
- na jeden den, na celé pololetí i na celý školní rok,
- totéž hlásí `/api/v1/classBooks` (třídní kniha).

Integrační rozhraní `/if/2/…` (autentizace přes Basic nebo `X-Api-Key`) umí jen
žáky, třídy a GDPR souhlasy — **žádný rozvrh** tam není.

**Nepomůže ani přidání práv.** Číselník API modulů je uzavřený (19 hodnot) a
jediný učitelský rozvrhový modul `api_rozvrh_zam` účet už má; není co dalšího
zapnout. `timeTableDetail` a `teacher/markingStudents` na konkrétní cizí hodinu
(`UdalostId` vyčtené ze stránky) vracejí prázdno a 404 — API je navržené jako
**osobní** rozhraní pro mobilní aplikaci, ne jako školní datové rozhraní.
Neověřeno zůstává jen to, zda by účet s reálným úvazkem přes `ClassId` viděl
celou třídu, nebo zase jen vlastní hodiny.

**Webová aplikace ale stejnému účtu rozvrh všech tříd ukazuje.** Ve webu má účet
role „Obecný uživatel, Učitel, Vedoucí pracovník“ a plné menu *Rozvrh a suplování*;
přes REST API dostane jen 5 modulů. Rozvrh se proto bere odtud:

| co | jak |
|---|---|
| přihlášení | `POST /SOL/Prihlaseni.aspx` — pole `JmenoUzivatele`, `HesloUzivatele`; bez captchy a bez VIEWSTATE, relace pak drží cookie `.ASPXAUTH` |
| rozvrh všech tříd na dnešek | `GET /SOL/App/Rozvrh/KRO029_VypisTridDenni.aspx` („Denní podle tříd“) |

Stránka je klasické ASP.NET WebForms, žádný AJAX — mřížka rozvrhu přijde rovnou
v HTML prvního GETu. Parsuje se `<table id="CCADynamicCalendarTable">`:

- řádek = třída, sloupec = vyučovací hodina,
- **colspan** = délka (dvouhodinovka, celodenní akce),
- **rowspan** = třída s paralelními skupinami má víc řádků a název jen u prvního,
- každá buňka nese v atributu `onmouseover` volání
  `onMouseOverTooltip('<nadpis>', 'Učitel:~…~Třída:~…~Žáci:~…~Učebna:~…')` — odtud
  se berou přesné údaje včetně **plného** názvu předmětu (viditelné `<span>`\y
  mají jen zkratky),
- školní akce mají třídu `KuvSkolniAkceHodina`, běžná výuka `DctInnerTableType10DataTD`.

### Známé omezení: jen dnešek

`KRO029` vybírá datum Infragistics kalendářem, jehož postback se nepodařilo
napodobit — hidden pole `calendarPart_kalendar` se serializuje uvnitř knihovny
(`igcal_init` / `calendar.setSelectedDate()`) a prosté POSTy s datem ve všech
zkoušených tvarech vrátí stále dnešek. Pro signage to nevadí, ta zobrazuje dnešek.
Až bude potřeba jiný den, nabízí se dekódovat formát toho pole ze skriptu
`ScriptResource.axd`, nebo stránku obsloužit headless prohlížečem.

### Další formuláře, které se můžou hodit

Účet na ně má právo a berou se stejnou cestou (`bin/dump.py html <cesta>`):

| formulář | co obsahuje |
|---|---|
| `/SOL/App/Rozvrh/KRO029_VypisTridDenni.aspx` | denní rozvrh všech tříd |
| `/SOL/App/Rozvrh/KRO003_VypisTridy.aspx` | rozvrh jedné třídy (výběr `DDLTrida`), týden/měsíc |
| `/SOL/App/Rozvrh/KRO016_VypisUciteluDenni.aspx` | denní rozvrh podle učitelů |
| `/SOL/App/Rozvrh/KSU013_ZmenyRozvrhuTrid.aspx` | změny v rozvrhu tříd (suplování) |
| `/SOL/App/Rozvrh/KSU016_SuplovaniVypis.aspx` | výpis suplování |
| `/SOL/App/Administrace/KSK006_SkolniAkce.aspx` | evidence školních akcí |

## Přístupové údaje

Heslo **nikdy nepatří do kódu ani do gitu.** Čte se z `.env` vedle projektu
(v `.gitignore`, vzor v `.env.example`) nebo z proměnných prostředí, které mají
přednost:

```bash
SOL_USERNAME=... SOL_PASSWORD=... python3 web.py
```

REST klient si mezi běhy ukládá token do `.token-cache.json` (také v `.gitignore`,
práva 600) a obnovuje ho přes `refresh_token`. Webová relace se nedrží, přihlašuje
se při každém načtení stránky.

## Ladicí nástroj

```bash
bin/dump.py denni                   # rozparsovaný denní rozvrh všech tříd
bin/dump.py html [cesta]            # syrové HTML formuláře ŠOL
bin/dump.py user                    # profil z REST API + schoolYearId
bin/dump.py tridy                   # seznam tříd z REST API
bin/dump.py rozvrh 2026-09-02       # REST rozvrh (vrací prázdno, viz výše)
bin/dump.py ciselniky               # pololetí, rozsah školního roku
bin/dump.py get /api/v1/user        # libovolný REST endpoint
bin/dump.py endpointy               # výpis endpointů ze swaggeru serveru
```

## Struktura

```
sol/config.py        načtení .env / proměnných prostředí
sol/web_klient.py    přihlášení do webové aplikace ŠOL a stažení formulářů
sol/dom.py           minimalistický DOM nad html.parser (vnořené tabulky)
sol/denni_rozvrh.py  parser mřížky KRO029 -> Hodina / RozvrhTridy
sol/cache.py         cache posledního rozvrhu (šetří ŠOL, přežije výpadek)
sol/client.py        klient REST API (rozvrh nedává, ale zbytek funguje)
web.py               vestavěný HTTP server + vykreslení HTML
bin/dump.py          ladicí výpisy
```

## Co dál (k signage)

- Příští hodina, odpočet do zvonění — časy hodin i konce se už parsují.
- Suplování a změny v rozvrhu — `KSU013` / `KSU016`.
- Rozvržení na velkou obrazovku a automatické obnovování.
- Jiný den než dnešek — viz omezení výše.
