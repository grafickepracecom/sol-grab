# sol-grab

Čtení dat ze **Školy OnLine (ŠOL)** a jejich zobrazení. Prototyp — první krok
k signage aplikaci do sborovny (rozvrhy tříd, probíhající a příští hodina, akce tříd).

Napsáno v Pythonu **jen se standardní knihovnou** — žádný `pip install`, žádný
build. Běží pod Python 3.10+.

## Dvě oddělené části

```
ŠOL ──▶ bin/import_sol.py ──▶ rozvrh.sqlite ──▶ web.py ──▶ obrazovka
        (cron / tlačítko)      (bez historie)     (signage)
```

**Import** je jediné místo, které sahá na ŠOL. Pouští se z cronu, ručně nebo
tlačítkem na obrazovce, a výsledek uloží do SQLite.

**Signage** čte jen z SQLite. Na ŠOL nechodí, takže se překresluje jak často je
potřeba a výpadek ŠOL ji nezhasne — nejvýš zestárnou data, což obrazovka přizná
v hlavičce.

Databáze drží **jen poslední stav, bez historie** — každý import obsah nahradí
v jedné transakci. Když import selže, databáze se nemění.

## Rychlý start

```bash
cd /var/www/sol-grab
cp .env.example .env         # doplňte SOL_USERNAME a SOL_PASSWORD
chmod 600 .env

bin/import_sol.py            # naplní rozvrh.sqlite ze ŠOL
python3 web.py               # signage na http://localhost:8081/
```

| cesta | co dělá |
|---|---|
| `/` | signage obrazovka, sama se obnovuje (`SOL_OBNOVA`, výchozí 60 s) |
| `/seznam` | prostý výpis rozvrhu pro kontrolu dat |
| `/import` | POST — vynutí import ze ŠOL (tlačítko „Načíst ze ŠOL“) |

```bash
python3 web.py --port 9000
python3 web.py --generuj          # statické HTML do SOL_VYSTUP
python3 web.py --vypis            # HTML na stdout
bin/import_sol.py --tise          # jen chyby, pro cron
bin/dump.py denni                 # co vrací ŠOL, mimo databázi
```

### Simulovaný čas

`--cas` nahradí „teď“ zadaným okamžikem a kombinuje se se všemi třemi režimy.
Bez něj se bere systémový čas, takže v ostrém provozu se nikam nepíše.
Hodí se při ladění mimo vyučování — v noci by okno bylo prázdné:

```bash
python3 web.py --generuj --cas '3.9.2026 9:02'   # zapíše do SOL_VYSTUP
python3 web.py --vypis   --cas 9:02 > /tmp/x.html
python3 web.py --cas '3.9.2026 9:02'             # server se zastaveným časem
```

Přijímá `9:02` (dnešní den), `2026-09-03 09:02` (i s `T`) a české
`3.9.2026 9:02`. Pozor, `--cas` mění jen **zobrazovaný okamžik** — rozvrh se
bere z databáze, takže se simuluje ten den, který je naimportovaný.

## Obrazovka

Rozvržení jako televizní program: řádek = třída, vodorovná osa = čas, svislá
žlutá čára = aktuální chvíle. Okno je ve výchozím stavu tříhodinové s aktuální
chvílí ve třetině (`SOL_OKNO_ZPET=60`, `SOL_OKNO_VPRED=120` minut).

- Blok začíná a končí na pozici odpovídající času; co přesahuje okno, má
  useknutou hranu (čárkovaně).
- **Paralelní skupiny** téže třídy leží pod sebou — každému bloku se přidělí
  nejnižší dráha, kde se s ničím nepřekrývá. Řádky si dělí výšku flex poměrem
  podle počtu drah, takže se obrazovka vejde vždycky a nikdy neroluje.
- Školní akce jsou oranžové, běžná výuka modrá, právě probíhající blok má
  zvýrazněný rámeček.

## Provoz — uživatelé, práva, služba

Běží pod dvěma systémovými účty, aby zápis a čtení výstupu byly oddělené:

| účet | role |
|---|---|
| `sol` | vlastní projekt, importuje ze ŠOL, zapisuje výstup |
| `signage` | zobrazovací aplikace, výstup jen **čte** |

```
/var/www/sol-grab       sol:sol      2775   projekt (a git repozitář)
/var/www/signage-data   sol:signage  2750   sdílený výstup
/var/www/signage-data/index.html     0640   generovaná obrazovka
```

Výstupní adresář stojí **samostatně vedle obou projektů**, ne uvnitř některého
z nich. Je to rozhraní mezi dvěma službami, ne artefakt jedné z nich — a hlavně:
uvnitř projektu by ho rozbil první rekurzivní `chown`, musel by se ignorovat
v gitu a u převzaté signage aplikace by se do jejího stromu nemuselo dát
zapisovat.

Setgid bit (`2`) na adresáři drží skupinu i u nově vzniklých souborů, `umask 027`
v procesech pak dává souborům 640. Adresář je záměrně `2750`, ne `2775` — při
`2775` by skupina `signage` mohla do výstupu zapisovat a `index.html` i smazat.

`.env` a `.token-cache.json` jsou `640`, ne `664` jako zbytek projektu: je v nich
heslo do ŠOL, respektive platný token.

### Služba

```bash
sudo cp bin/sol-grab.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sol-grab

systemctl status sol-grab
journalctl -u sol-grab -f
```

Unit běží pod `sol`, má `UMask=0027` a `ProtectSystem=strict` se zápisem
povoleným jen do projektu a do výstupního adresáře — služba čte heslo do ŠOL,
tak ať nesahá nikam, kam nemusí.

## Cron

Připravený, ale **zatím zakomentovaný** rozpis je v [bin/crontab.priklad](bin/crontab.priklad):

```bash
sudo cp bin/crontab.priklad /etc/cron.d/sol-grab
sudo chown root:root /etc/cron.d/sol-grab && sudo chmod 644 /etc/cron.d/sol-grab
# a odkomentovat vybrané řádky
```

Rozvrh se během dne mění (suplování, přesuny), proto se počítá s opakovaným
importem — návrh je každých 15 minut ve všední dny mezi 6:00 a 17:00.

## Odolnost proti výpadku

Zdrojem je cizí aplikace, takže se počítá s tím, že se rozbije:

* **Oddělený import** — signage čte z SQLite, takže na ŠOL při překreslování
  vůbec nechodí a nezatěžuje ji.
* **Výpadek ŠOL** — import skončí nenulovým kódem a databázi nechá být; obrazovka
  dál ukazuje poslední známý rozvrh a v hlavičce oranžově přizná, jak je starý.
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

### Vícedenní data (KRO003)

Import bere rozvrh z **KRO003 „Rozvrh třídy" v měsíčním režimu**: jeden dotaz na
třídu vrátí celý aktuální měsíc, takže databáze drží dnešek i dny dopředu (typicky
2–4 týdny). KRO029 „Denní podle tříd" umí jen dnešek (datum v kalendáři nejde
spolehlivě přepnout), proto se pro vícedenní data nepoužívá — zůstává jen v
`bin/dump.py denni` pro ruční pohled na dnešek.

Cena: KRO003 je per-třída, takže import je 1 GET + 13 POSTů (VIEWSTATE se řetězí),
místo jednoho dotazu. Běží ~20 s, pro cron á 15 min v pohodě.

**Okno = aktuální kalendářní měsíc.** „Dnešek + zítřek" je tak pokrytý vždy kromě
posledního dne měsíce (zítřek je v dalším měsíci, který se natáhne až po půlnoci
nočním importem). Pro signage to stačí; tvrdá záruka přes hranici měsíce by
vyžadovala navigaci kalendáře, kterou ŠOL neumožňuje čistě replikovat.


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

Projekt se dělí na **knihovnu** (rozhraní k ŠOL, adresář `sol/`) a **aplikaci**
(signage, zbytek). Knihovna nezná aplikaci — závislost jde jen jedním směrem
(`signage` → `sol`). Knihovna se bude vyčleňovat do vlastního repozitáře.

Knihovna `sol/` — rozhraní k ŠOL (čistě standardní knihovna, bez závislostí):
```
sol/config.py        připojení k ŠOL (přístupy, adresy, cache tokenu); z_env()
sol/web_klient.py    přihlášení do webové aplikace ŠOL a stažení formulářů
sol/client.py        klient REST API ŠOL (OAuth token, /api/v1/*)
sol/dom.py           minimalistický DOM nad html.parser (vnořené tabulky)
sol/denni_rozvrh.py  parser KRO029 + datový model (Hodina/RozvrhTridy/DenniRozvrh)
sol/mesicni_rozvrh.py parser KRO003 (měsíc) + stažení všech tříd
sol/sluzba.py        sidecar: lokální RPC (HTTP+JSON) pro ne-Python konzumenty
sol/README.md        dokumentace knihovny (import i sidecar, klienti PHP/Python)
```

Z jiného jazyka (PHP) se knihovna nevolá přímo — běží jako **sidecar služba**
(`python3 -m sol.sluzba`), která drží přístup k ŠOL centrálně a nabízí data
lokálně přes HTTP+JSON s `rpcuser`/`rpcpassword`. Viz [sol/README.md](sol/README.md),
včetně bezpečnostních zásad a klientských ukázek.

Aplikace — signage postavené nad knihovnou:
```
signage/config.py    nastavení aplikace (porty, okno, prahy, cesty) + továrna na sol.config
signage/uloziste.py  SQLite — uložení a načtení rozvrhu
signage/import_job.py importní úloha ŠOL -> SQLite (sdílí ji cron i tlačítko)
signage/model.py     sestavení pohledu — okno, dráhy, pozice bloků
signage/render.py    vykreslení obrazovky do HTML (vč. dily_html)

web.py               HTTP server: signage, /seznam, vynucený import
bin/import_sol.py    CLI importu (pro cron)
bin/crontab.priklad  zakomentovaný rozpis pro /etc/cron.d/
bin/sol-grab.service systemd unit (běží pod uživatelem sol)
bin/dump.py          ladicí výpisy přímo ze ŠOL, mimo databázi
```

## Co dál

- Suplování a změny v rozvrhu — `KSU013` / `KSU016`.
- Odpočet do zvonění, jméno právě probíhající hodiny výrazněji.
- Jiný den než dnešek — viz omezení výše.
