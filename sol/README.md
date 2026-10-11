# sol — knihovna pro čtení dat ze Školy OnLine (ŠOL)

Python knihovna, která se přihlásí do ŠOL a vrátí jeho data (zatím rozvrhy tříd)
jako čisté Python objekty, případně jako JSON přes lokální službu. **Jen
standardní knihovna Pythonu, žádné závislosti.** Python 3.10+.

ŠOL oficiální API nemá; knihovna staví na webovém rozhraní a na neveřejném REST
API mobilní aplikace. Je to tedy křehké vůči změnám ŠOL — proto má parser kontroly
struktury a vrací srozumitelné chyby.

## Poděkování

ŠOL veřejné API nemá, takže knihovna vychází z práce komunity, která jeho
rozhraní zmapovala dřív:

- [Libre-SkolaOnline/API-docs](https://github.com/Libre-SkolaOnline/API-docs) —
  zpětně odvozená dokumentace REST API ŠOL (OpenAPI), licence GPL-3.0. Byla
  výchozím bodem pro napojení na REST (přihlášení, endpointy), než jsme objevili
  vlastní OpenAPI popis publikovaný přímo serverem ŠOL.
- [reŠOL](https://codeberg.org/resol/resol) — svobodný alternativní klient ŠOL,
  od kterého jsme se při orientaci odrazili.

Kód této knihovny je původní; uvedené projekty byly zdrojem poznání a inspirace.
Licenční podmínky každého z nich najdete v jeho repozitáři.

## Dva způsoby použití

| chci… | použij |
|---|---|
| volat z **Pythonu** | importuj balíček `sol` (níže) |
| volat z **PHP / jiného jazyka** | spusť **sidecar službu** a volej ji přes HTTP+JSON (níže) |

Mezi jazyky se nesdílí knihovna (PHP neumí `import` Pythonu), ale **rozhraní** —
proto je tu sidecar: jeden proces drží přístup k ŠOL a nabízí data komukoli
lokálně přes jednoduché JSON HTTP.

---

## A) Použití z Pythonu

Knihovnu zapoj jako **git submodul** do adresáře `sol` svého projektu:

```bash
git submodule add <URL-repozitáře-knihovny> sol
```

Pak `from sol… import …` funguje se systémovým Pythonem, bez venv:

```python
from sol.config import Nastaveni
from sol.web_klient import SolWebKlient
from sol.mesicni_rozvrh import stahni_mesicni_rozvrh

# připojení: buď explicitně, nebo z prostředí přes Nastaveni.z_env()
n = Nastaveni(username="jmeno", password="heslo")
casy, tridy, dny, od, do = stahni_mesicni_rozvrh(SolWebKlient(n))
# dny = { "2026-10-08": { "I.": [Hodina, …], … }, … }
```

Hlavní stavební kameny:

- `sol.config.Nastaveni` — připojení k ŠOL (přístupy, adresy, volitelná cache
  tokenu). `Nastaveni.z_env()` je načte z prostředí (`SOL_USERNAME`, `SOL_PASSWORD`,
  volitelně `SOL_BASE_URL`, `SOL_WEB_URL`, `SOL_CLIENT_ID`, `SOL_CACHE_TOKENU`).
- `sol.web_klient.SolWebKlient` — přihlášení do webu ŠOL a stažení formulářů.
- `sol.mesicni_rozvrh.stahni_mesicni_rozvrh(klient)` — rozvrh **všech tříd na
  celý aktuální měsíc** (KRO003). Jeden GET + jeden POST na třídu.
- `sol.denni_rozvrh` — datový model (`Hodina`, `RozvrhTridy`, `DenniRozvrh`),
  parser dne (KRO029) a `dily_text()` pro plochý text polí.
- `sol.client.SolClient` — klient REST API (profil, číselníky); rozvrh tříd
  přes něj nejde (vrací jen vlastní rozvrh přihlášeného), proto se pro rozvrhy
  používá web (`SolWebKlient`).

### Datový model `Hodina`

Pole `ucitele`, `ucebna`, `zaci` nejsou prostý text, ale **seznam dílků**
`{"t": text, "c": třída}`. Dílek s `"c": ""` je běžný text; dílek
s `"c": "sol_AbsZdroj"` je **absentující zdroj** — učitel/učebna, které ŠOL
u hodiny stále vede, ale ví se, že tam nebudou (učitel mimo, učebna obsazená
jiným programem). Konzument je typicky zvýrazní (červeně). Prefix `sol_` je
zachycený název CSS třídy ze ŠOL; kdyby ŠOL zavedl jinou, dílek prostě nebude
zvýrazněný, ale text zůstane.

---

## B) Sidecar služba (centrální přístup k ŠOL pro libovolný jazyk)

Služba `sol.sluzba` drží přístup k ŠOL na **jednom místě** a nabízí jeho data
lokálně přes HTTP+JSON. Konzumenti (PHP, …) se k ní hlásí vlastními údaji
`rpcuser`/`rpcpassword` — **ke ŠOL se nepřipojují a jeho heslo nevidí**.

```bash
python3 -m sol.sluzba
```

Konfigurace z prostředí:

| proměnná | význam | výchozí |
|---|---|---|
| `SOL_RPC_USER` | uživatel pro přístup ke **službě** (povinné) | — |
| `SOL_RPC_PASSWORD` | heslo pro přístup ke **službě** (povinné) | — |
| `SOL_RPC_BIND` | adresa naslouchání | `127.0.0.1` |
| `SOL_RPC_PORT` | port | `8899` |
| `SOL_RPC_CACHE` | jak dlouho (s) držet stažený měsíc v paměti | `300` |
| `SOL_USERNAME`, `SOL_PASSWORD`, … | přihlášení ke **ŠOL** (viz sekce A) | — |

Provoz přes systemd: viz [`sol-rpc.service`](sol-rpc.service) (přístupy v
`/etc/sol-rpc.env`, práva 600).

### Endpointy (vše vyžaduje HTTP Basic `rpcuser`/`rpcpassword`, odpověď JSON)

| endpoint | vrací |
|---|---|
| `GET /ping` | `{"ok": true, "sluzba": "sol", "verze": 1}` |
| `GET /rozvrh/mesic` | celý aktuální měsíc, všechny třídy |
| `GET /rozvrh/den?datum=RRRR-MM-DD` | jeden den (výřez z měsíce) |

`GET /rozvrh/den` vrací:

```json
{
  "datum": "2026-10-08",
  "v_okne": true,                     // je datum v naimportovaném měsíci?
  "casy": [{"cislo":"1","od":"08:30","do":"09:20"}, …],
  "tridy": ["I.","II.", …],
  "hodiny": {
    "I.": [
      {"od_hodiny":1,"do_hodiny":2,"od":"08:30","do":"10:10",
       "nazev":"H","plny_nazev":"Hlavní vyučování",
       "ucitele":[{"t":"Nováková J.","c":""}],
       "ucebna":[{"t":"I.","c":""}], "zaci":[{"t":"I. (celá třída)","c":""}],
       "akce": false}
    ], …
  }
}
```

Chyby: `401` neautorizováno, `400` chybný dotaz, `404` neznámý endpoint,
`502` problém se ŠOL (`{"chyba": "…"}`).

### ⚠️ BEZPEČNOST — NUTNO DODRŽET

- **Služba smí naslouchat jen na `127.0.0.1`.** Nikdy ji nespouštěj na `0.0.0.0`
  ani na veřejné IP. Kdo na port dosáhne a zná `rpcuser`/`rpcpassword`, čte data
  ze ŠOL jménem účtu služby.
- **HTTP Basic bez TLS přenáší heslo čitelně** (base64). Je to v pořádku **jen**
  pro komunikaci procesů na jednom stroji přes localhost.
- **Potřebuješ-li ke službě z jiného stroje:** nedávej ji ven přímo. Postav před
  ni reverzní proxy s TLS a omez přístup firewallem / seznamem IP; samotný port
  služby drž na `127.0.0.1`.
- **`rpcuser`/`rpcpassword` NEJSOU údaje do ŠOL.** Jsou to samostatné lokální
  údaje jen pro přístup ke službě. Heslo do ŠOL zná jen služba.
- Služba se bez `SOL_RPC_USER`/`SOL_RPC_PASSWORD` **odmítne spustit**.
- Soubor s přístupy (`/etc/sol-rpc.env`) drž s právy `600` a mimo git.

### Klient v PHP

```php
<?php
// Volání lokální sol služby z PHP. rpcuser/rpcpassword jsou LOKÁLNÍ údaje
// ke službě, ne přihlášení do ŠOL.
$rpcUser = 'rpc';
$rpcPass = getenv('SOL_RPC_PASSWORD');   // drž mimo kód
$url = 'http://127.0.0.1:8899/rozvrh/den?datum=' . date('Y-m-d');

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPAUTH       => CURLAUTH_BASIC,
    CURLOPT_USERPWD        => "$rpcUser:$rpcPass",
    CURLOPT_TIMEOUT        => 30,   // první dotaz stahuje měsíc (~20 s)
]);
$odpoved = curl_exec($ch);
$stav = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($stav !== 200) {
    throw new RuntimeException("sol služba vrátila HTTP $stav: $odpoved");
}
$data = json_decode($odpoved, true);

foreach ($data['hodiny'] as $trida => $hodiny) {
    foreach ($hodiny as $h) {
        // jméno učitele; absentující (c === 'sol_AbsZdroj') zvýrazni
        $ucitele = array_map(fn($d) => $d['t'], $h['ucitele']);
        echo "$trida {$h['od']}-{$h['do']} {$h['plny_nazev']} "
           . implode(', ', $ucitele) . "\n";
    }
}
```

### Klient v Pythonu (bez importu knihovny, jen přes službu)

```python
import base64, json, urllib.request

def sol_rpc(cesta, user, password, host="127.0.0.1", port=8899):
    req = urllib.request.Request(f"http://{host}:{port}{cesta}")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    with urllib.request.urlopen(req, timeout=30) as o:
        return json.loads(o.read())

den = sol_rpc("/rozvrh/den?datum=2026-10-08", "rpc", "…")
```

---

## Co knihovna umí a neumí

- **Umí:** přihlášení do ŠOL (web i REST), rozvrh tříd na den i na měsíc
  (všechny třídy), rozpoznání absentujících zdrojů, číselníky přes REST.
- **Zatím neumí:** zapisovat do ŠOL, jiné moduly než rozvrh. Rozšiřuje se.
- **Omezení:** rozvrh jde brát jen za aktuální měsíc (datum v kalendáři ŠOL
  nejde spolehlivě přepínat); historii ani libovolný budoucí měsíc neumí.
