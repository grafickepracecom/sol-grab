# sol-grab

Čtení dat ze **Školy OnLine (ŠOL)** a jejich zobrazení. Prototyp — první krok
k signage aplikaci do sborovny (aktuální a příští hodina po třídách, akce tříd).

Napsáno v Pythonu **jen se standardní knihovnou** — žádný `pip install`, žádný
build. Běží pod Python 3.10+.

## Rychlý start

```bash
cd /var/www/sol-grab
cp .env.example .env         # doplňte SOL_USERNAME a SOL_PASSWORD
chmod 600 .env

python3 web.py               # http://localhost:8081/
python3 web.py --port 9000
python3 web.py --datum 2026-09-02          # vypíše HTML na stdout
python3 web.py --datum 2026-09-02 --ukazka # ukázková data místo ŠOL
```

Datum se dá přepnout i v URL: `/?datum=2026-09-02`. Bez parametru se bere dnešek.

Ladicí nástroj na syrové odpovědi:

```bash
bin/dump.py user                    # profil + schoolYearId
bin/dump.py tridy
bin/dump.py rozvrh 2026-09-02       # rozvrh přihlášeného
bin/dump.py rozvrh 2026-09-02 E560992
bin/dump.py ciselniky               # pololetí, rozsah školního roku
bin/dump.py get /api/v1/user        # libovolný endpoint
bin/dump.py endpointy               # výpis endpointů ze swaggeru serveru
```

## Přístupové údaje

Heslo **nikdy nepatří do kódu ani do gitu.** Čte se z `.env` vedle projektu
(v `.gitignore`, vzor v `.env.example`) nebo z proměnných prostředí, které mají
přednost:

```bash
SOL_USERNAME=... SOL_PASSWORD=... python3 web.py
```

Klient si mezi běhy ukládá token do `.token-cache.json` (rovněž v `.gitignore`,
práva 600), aby se nepřihlašoval znovu při každém spuštění; po vypršení použije
`refresh_token`, a když ani ten neprojde, přihlásí se heslem.

## Co se zjistilo o API ŠOL

ŠOL **oficiální API nemá**. Existují komunitní pokusy o dokumentaci —
[Libre-SkolaOnline/API-docs](https://github.com/Libre-SkolaOnline/API-docs)
(OpenAPI odposlechnutý z provozu) a neudržovaný
[reŠOL](https://codeberg.org/resol/resol). Obojí ale popisuje jen **žákovskou**
část.

Podstatnější nález: **server publikuje vlastní OpenAPI popis** a je veřejně
čitelný bez přihlášení:

```
https://aplikace.skolaonline.cz/solapi/swagger/v1/swagger.json
```

Je v něm 107 endpointů včetně učitelských, které komunitní dokumentace nezná —
je to spolehlivější zdroj pravdy. (`/solapi/swagger/index.html` je 404, tj. jen
JSON, ne Swagger UI.) Vypíše ho `bin/dump.py endpointy`.

### Přihlášení

`POST /solapi/api/connect/token`, `application/x-www-form-urlencoded`,
OAuth2 s `grant_type=password` nebo `refresh_token`, `client_id=test_client`,
`scope=openid offline_access profile sol_api`. Vrací `access_token` (JWT,
platnost cca 1 h), `refresh_token` a `expires_in`.

V JWT je řada užitečných claimů: `sol.UserType` (`Employee` / student),
`sol.SchoolYearId`, `sol.OrganizationId`, `sol.ModuleRights`. Stejné údaje
čitelněji vrací `GET /api/v1/user`.

### Endpointy, na kterých projekt stojí

| endpoint | k čemu |
|---|---|
| `GET /api/v1/user` | profil, `schoolYearId` = **aktuální školní rok** |
| `GET /api/v1/teacher/behaviors/classes?SchoolYearId=` | seznam tříd školy |
| `GET /api/v1/timeTable?SchoolYearId&DateFrom&DateTo&ClassId` | rozvrh třídy za období |
| `GET /api/v1/timeTable/codeLists?schoolYearId=` | pololetí, rozsah roku, zda se zobrazuje víkend |

Poznámky z testování:

- **Rozvrh třídy jde přes `ClassId` u `/api/v1/timeTable`.** Komunitní
  dokumentace zná jen `StudentId`; `ClassId`, `LessonId` a `SubjectId` jsou ve
  swaggeru serveru navíc. Bez `ClassId` vrátí rozvrh přihlášeného uživatele.
- **Samostatný číselník tříd v API není.** `/if/2/common/classes` vypadá jako
  ten pravý, ale s tokenem z `/connect/token` vrací 401 (jiný způsob ověření).
  Použitelný seznam tříd dává modul třídní knihy
  (`/api/v1/teacher/behaviors/classes`, právo `api_chovani_zam`).
- **Dostupný je jen aktuální školní rok.** Dotaz na `timeTable/codeLists`
  s jiným `schoolYearId` končí 404, historii tedy tudy vytáhnout nelze.
- Odpověď `/api/v1/timeTable` je `{"days": [...], "lessons": [...]}`, kde
  `lessons` je číselník časů vyučovacích hodin školy (1. = 8:30–9:20 atd.)
  a vrací se i tehdy, když je `days` prázdné.

### Práva účtu

Účet, pod kterým se to vyvíjelo, je typu **učitel** s moduly `api_dom_ukoly_zam`,
`api_hodnoceni_zam`, `api_chovani_zam`, `api_rozvrh_zam` a `api_zpravy_zam`.
Endpointy mimo přidělené moduly vracejí 403 s textem, které právo chybí —
například omluvenky (`api_omluvenky_zam`) tenhle účet nemá.

## Stav dat

**Rozvrh na školní rok 2026/2027 zatím ve ŠOL zadaný není.** Dotaz na celý rok
(2026‑09‑01 – 2027‑06‑30) i na jednotlivé dny vrací pro všech 13 tříd prázdné
`days`; totéž hlásí třídní kniha. Není to chyba napojení — jakmile škola rozvrh
zadá, stránka ho vypíše. Do té doby je vidět hlášku „Pro tento den nevrátila ŠOL
žádné rozvrhované hodiny“ a vykreslování se dá zkoušet přes `--ukazka`.

## Struktura

```
sol/config.py    načtení .env / proměnných prostředí
sol/client.py    HTTP klient ŠOL — přihlášení, refresh, cache tokenu, volání API
sol/rozvrhy.py   převod odpovědí na Hodina / RozvrhTridy pro zobrazení
sol/ukazka.py    ukázková data ve tvaru odpovědi ŠOL (pro --ukazka)
web.py           vestavěný HTTP server + vykreslení HTML
bin/dump.py      ladicí výpis syrových odpovědí
```

## Co dál (k signage)

- Aktuální a příští hodina — má se počítat z `beginTime`/`endTime` proti
  aktuálnímu času; číselník `lessons` už k tomu je.
- Akce tříd — `/api/v1/timeTable` vrací i `monitorings`, `emergencies`
  a `teachingInformations`, teď se nezobrazují.
- Automatické obnovování stránky a rozvržení na velkou obrazovku.
