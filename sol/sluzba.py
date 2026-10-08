"""Lokální RPC služba nad knihovnou ŠOL (sidecar).

Smysl: **centrální autentizace k ŠOL**. Přístupové údaje do ŠOL zná jen tahle
služba (ze svého prostředí). Konzumenti (PHP, Python, cokoli) se k ní hlásí
vlastními, lokálně nastavenými údaji ``rpcuser`` / ``rpcpassword`` a dostanou
data jako JSON — **ke ŠOL se nepřipojují sami a jeho heslo nikdy nevidí**.

╔═══════════════════════════════════════════════════════════════════════════╗
║  BEZPEČNOST — ČTI, NEŽ TO SPUSTÍŠ                                          ║
║                                                                           ║
║  * Služba naslouchá JEN na localhostu (127.0.0.1). NIKDY ji nevystavuj   ║
║    na 0.0.0.0 ani veřejnou IP. Kdo na port dosáhne a zná rpcuser/         ║
║    rpcpassword, čte data ze ŠOL jménem účtu služby.                       ║
║  * Autorizace je HTTP Basic přes rpcuser/rpcpassword. Je to slabá         ║
║    ochrana vhodná POUZE pro lokální meziprocesovou komunikaci na jednom   ║
║    stroji. Bez TLS se heslo přenáší v kódování base64 (= čitelně).        ║
║  * Potřebuješ-li k službě z jiného stroje, NEDÁVEJ ji přímo ven —         ║
║    postav před ni reverzní proxy s TLS a omez přístup firewallem /        ║
║    seznamem IP. Port služby samotné drž na 127.0.0.1.                     ║
║  * rpcuser/rpcpassword NEJSOU přihlašovací údaje do ŠOL. Jsou to          ║
║    samostatné, lokální údaje jen pro přístup k téhle službě.              ║
║  * Služba se bez nastaveného rpcuser/rpcpassword odmítne spustit.         ║
╚═══════════════════════════════════════════════════════════════════════════╝

Spuštění (údaje v prostředí, viz níže):

    python3 -m sol.sluzba

Konfigurace z prostředí:

    SOL_RPC_USER        uživatel pro přístup ke službě (povinné)
    SOL_RPC_PASSWORD    heslo pro přístup ke službě (povinné)
    SOL_RPC_BIND        adresa pro naslouchání (výchozí 127.0.0.1)
    SOL_RPC_PORT        port (výchozí 8899)
    SOL_RPC_CACHE       jak dlouho (s) držet stažený měsíc v paměti (výchozí 300)
    SOL_USERNAME, SOL_PASSWORD, ...   přihlášení ke ŠOL (viz sol.config)

Endpointy (vše vyžaduje HTTP Basic rpcuser/rpcpassword, odpověď je JSON):

    GET /ping                     { "ok": true, "sluzba": "sol", "verze": 1 }
    GET /rozvrh/mesic             celý aktuální měsíc, všechny třídy
    GET /rozvrh/den?datum=RRRR-MM-DD   jeden den (výřez z měsíce)
"""

from __future__ import annotations

import base64
import dataclasses
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Nastaveni
from .mesicni_rozvrh import stahni_mesicni_rozvrh
from .web_klient import SolWebKlient

VERZE = 1


class _Mesic:
    """Vlákno-bezpečná cache staženého měsíce (stažení trvá ~20 s)."""

    def __init__(self, sol_nastaveni: Nastaveni, ttl: int) -> None:
        self._n = sol_nastaveni
        self._ttl = ttl
        self._zamek = threading.Lock()
        self._data: dict | None = None
        self._cas = 0.0

    def ziskej(self) -> dict:
        with self._zamek:
            if self._data is None or time.time() - self._cas > self._ttl:
                self._data = self._stahni()
                self._cas = time.time()
            return self._data

    def _stahni(self) -> dict:
        casy, tridy, dny, od, do = stahni_mesicni_rozvrh(SolWebKlient(self._n))
        return {
            "datum_od": od,
            "datum_do": do,
            "casy": [{"cislo": c[0], "od": c[1], "do": c[2]} for c in casy],
            "tridy": tridy,
            "dny": {
                datum: {trida: [dataclasses.asdict(h) for h in hodiny]
                        for trida, hodiny in podle_trid.items()}
                for datum, podle_trid in dny.items()
            },
        }


class _Nastaveni:
    def __init__(self) -> None:
        g = os.environ.get
        self.rpcuser = g("SOL_RPC_USER", "")
        self.rpcpassword = g("SOL_RPC_PASSWORD", "")
        self.bind = g("SOL_RPC_BIND") or "127.0.0.1"
        self.port = int(g("SOL_RPC_PORT") or 8899)
        self.cache = int(g("SOL_RPC_CACHE") or 300)
        self.sol = Nastaveni.z_env()

    def zkontroluj(self) -> None:
        if not self.rpcuser or not self.rpcpassword:
            raise SystemExit(
                "Služba se nespustí: chybí SOL_RPC_USER / SOL_RPC_PASSWORD "
                "(lokální přístup k RPC, nezaměňovat s přihlášením do ŠOL)."
            )
        self.sol.zkontroluj()


def _spravne_udaje(hlavicka: str, user: str, password: str) -> bool:
    """Konstantně-časové ověření HTTP Basic hlavičky."""
    if not hlavicka.startswith("Basic "):
        return False
    try:
        dekod = base64.b64decode(hlavicka[6:]).decode("utf-8", "replace")
    except Exception:
        return False
    jmeno, _, heslo = dekod.partition(":")
    # oba hmac.compare_digest, ať se neprozradí, co nesedí
    return (hmac.compare_digest(jmeno, user) & hmac.compare_digest(heslo, password))


def vytvor_handler(nast: _Nastaveni, mesic: _Mesic):
    class Handler(BaseHTTPRequestHandler):
        server_version = "sol-rpc"

        def _json(self, kod: int, data: dict) -> None:
            telo = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(telo)))
            self.end_headers()
            self.wfile.write(telo)

        def _autorizovan(self) -> bool:
            if _spravne_udaje(self.headers.get("Authorization", ""),
                              nast.rpcuser, nast.rpcpassword):
                return True
            telo = json.dumps({"chyba": "neautorizováno"}).encode()
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="sol"')
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(telo)))
            self.end_headers()
            self.wfile.write(telo)
            return False

        def do_GET(self) -> None:  # noqa: N802
            if not self._autorizovan():
                return
            adresa = urlparse(self.path)
            try:
                if adresa.path == "/ping":
                    self._json(200, {"ok": True, "sluzba": "sol", "verze": VERZE})
                elif adresa.path == "/rozvrh/mesic":
                    self._json(200, mesic.ziskej())
                elif adresa.path == "/rozvrh/den":
                    datum = (parse_qs(adresa.query).get("datum") or [""])[0]
                    if not datum:
                        self._json(400, {"chyba": "chybí parametr datum=RRRR-MM-DD"})
                        return
                    m = mesic.ziskej()
                    self._json(200, {
                        "datum": datum,
                        "v_okne": m["datum_od"] <= datum <= m["datum_do"],
                        "casy": m["casy"],
                        "tridy": m["tridy"],
                        "hodiny": m["dny"].get(datum, {}),
                    })
                else:
                    self._json(404, {"chyba": "neznámý endpoint"})
            except Exception as e:  # ŠOL výpadek, změna struktury…
                self._json(502, {"chyba": f"{type(e).__name__}: {e}"})

        def log_message(self, format: str, *args) -> None:
            print(f"{self.address_string()} {format % args}", flush=True)

    return Handler


def main() -> None:
    nast = _Nastaveni()
    nast.zkontroluj()
    mesic = _Mesic(nast.sol, nast.cache)
    server = ThreadingHTTPServer((nast.bind, nast.port), vytvor_handler(nast, mesic))
    print(f"sol RPC naslouchá na http://{nast.bind}:{nast.port}/  (jen lokálně; Ctrl-C ukončí)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkonec")


if __name__ == "__main__":
    main()
