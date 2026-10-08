#!/usr/bin/env python3
"""Signage obrazovka s rozvrhem tříd.

Čte **jen z SQLite** — na ŠOL sama nechodí. Data tam plní importní job
`bin/import_sol.py` (cron), případně tlačítko „Načíst ze ŠOL“ na obrazovce.

    python3 web.py                     # http://localhost:8081/
    python3 web.py --port 9000
    python3 web.py --generuj /var/www/signage/index.html   # statické HTML
    python3 web.py --cas 11:00         # vykreslí jiný čas (ladění rozvržení)

Cesty:
    /          signage obrazovka (sama se obnovuje, SOL_OBNOVA)
    /seznam    prostý výpis rozvrhu pro kontrolu dat
    /import    POST — vynutí import ze ŠOL a vrátí se na /
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from signage.model import sestav  # noqa: E402
from signage.render import dily_html  # noqa: E402
from signage.render import vykresli  # noqa: E402
from signage.config import Nastaveni  # noqa: E402
from signage.import_job import importuj  # noqa: E402
from signage.uloziste import nacti, pripoj  # noqa: E402

DNY = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]

# Zadané --cas; None = brát systémový čas. Drží se stranou, aby ho viděl
# i HTTP handler, ne jen jednorázové vykreslení.
_PEVNY_CAS: dt.datetime | None = None


def aktualni_cas() -> dt.datetime:
    return _PEVNY_CAS or dt.datetime.now()


def parsuj_cas(zadani: str, dnes: dt.date | None = None) -> dt.datetime:
    """Přijme „9:02“, „2026-09-03 09:02“ i české „3.9.2026 9:02“."""
    zadani = zadani.strip()
    dnes = dnes or dt.date.today()

    try:                                   # ISO, s mezerou i s T
        return dt.datetime.fromisoformat(zadani.replace(" ", "T"))
    except ValueError:
        pass

    for tvar in ("%d.%m.%Y %H:%M", "%d. %m. %Y %H:%M"):
        try:
            return dt.datetime.strptime(zadani, tvar)
        except ValueError:
            pass

    try:                                   # jen čas -> dnešní den
        cas = dt.datetime.strptime(zadani, "%H:%M").time()
        return dt.datetime.combine(dnes, cas)
    except ValueError:
        raise SystemExit(
            f"Nerozumím času „{zadani}“. Přijímám:\n"
            "  9:02                  (dnešní den)\n"
            "  2026-09-03 09:02      (nebo 2026-09-03T09:02)\n"
            "  3.9.2026 9:02") from None


def _prosta_stranka(telo: str, nadpis: str) -> bytes:
    return (f"<!doctype html><html lang=cs><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(nadpis)}</title>"
            "<style>body{font-family:system-ui,sans-serif;margin:1.5rem;color:#222}"
            "table{border-collapse:collapse;font-size:.85rem}"
            "td,th{padding:.2rem .5rem;border-top:1px solid #eee;text-align:left}"
            ".akce{color:#a35200}.chyba{color:#b00;white-space:pre-wrap}.sol_AbsZdroj{color:#c0392b}"
            "</style>" + telo).encode("utf-8")


def obrazovka(ted: dt.datetime | None = None, nastaveni: Nastaveni | None = None) -> bytes:
    """Signage obrazovka z dat v databázi."""
    n = nastaveni or Nastaveni()
    ted = ted or aktualni_cas()

    spojeni = pripoj(n.databaze)
    try:
        ulozene = nacti(spojeni, ted.date().isoformat())
    finally:
        spojeni.close()

    if ulozene is None:
        return _prosta_stranka(
            "<h1>Zatím není co zobrazit</h1>"
            "<p>V databázi není žádný rozvrh. Spusťte <code>bin/import_sol.py</code>, "
            "nebo použijte tlačítko:</p>"
            "<form method=post action='/import'><button>Načíst ze ŠOL</button></form>",
            "Rozvrh — bez dat")

    rozvrh, naimportovano, v_okne = ulozene
    pohled = sestav(rozvrh, ted.hour * 60 + ted.minute,
                    zpet=n.okno_zpet, vpred=n.okno_vpred)
    return vykresli(pohled, rozvrh.datum, naimportovano, ted, obnova_s=n.obnova,
                    v_okne=v_okne, varovani_min=n.varovani_min,
                    prekryv_hodin=n.prekryv_hodin)


def seznam() -> bytes:
    """Prostý výpis rozvrhu — kontrola, co je v databázi."""
    spojeni = pripoj(Nastaveni().databaze)
    try:
        ulozene = nacti(spojeni, dt.date.today().isoformat())
    finally:
        spojeni.close()
    if ulozene is None:
        return _prosta_stranka("<h1>V databázi není žádný rozvrh</h1>", "Rozvrh")

    rozvrh, naimportovano, _v_okne = ulozene
    cast = [f"<h1>Rozvrh {html.escape(rozvrh.datum)}</h1>",
            f"<p>{len(rozvrh.tridy)} tříd, {rozvrh.pocet_hodin} položek · "
            f"naimportováno {naimportovano:%d.%m.%Y %H:%M:%S} · "
            f"<a href='/'>signage obrazovka</a></p>"]
    for t in rozvrh.tridy:
        cast.append(f"<h2>{html.escape(t.trida)}</h2><table>")
        for h in t.hodiny:
            trida = " class=akce" if h.akce else ""
            detail = " · ".join(filter(None, [dily_html(h.ucitele), dily_html(h.ucebna), dily_html(h.zaci)]))
            cast.append(f"<tr><td>{html.escape(h.od)}–{html.escape(h.do)}</td>"
                        f"<td{trida}>{html.escape(h.popis)}</td>"
                        f"<td>{detail}</td></tr>")
        cast.append("</table>")
    return _prosta_stranka("".join(cast), f"Rozvrh {rozvrh.datum}")


class Handler(BaseHTTPRequestHandler):
    server_version = "sol-grab"

    def _odesli(self, kod: int, telo: bytes, typ: str = "text/html; charset=utf-8") -> None:
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(telo)))
        # obrazovka se obnovuje sama, ať ji po cestě nikdo nekešuje
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(telo)

    def _chyba(self, e: Exception) -> None:
        traceback.print_exc()   # podrobnosti do logu, na obrazovku jen věta
        self._odesli(500, _prosta_stranka(
            f"<h1>Chyba</h1><p class=chyba>{html.escape(f'{type(e).__name__}: {e}')}</p>"
            "<p>Podrobnosti jsou v logu serveru.</p>", "Chyba"))

    def do_GET(self) -> None:  # noqa: N802 (jméno předepisuje BaseHTTPRequestHandler)
        cesta = urlparse(self.path).path
        try:
            if cesta in ("/", "/index.html"):
                self._odesli(200, obrazovka())
            elif cesta == "/seznam":
                self._odesli(200, seznam())
            else:
                self.send_error(404)
        except Exception as e:
            self._chyba(e)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/import":
            self.send_error(404)
            return
        try:
            kod = importuj(tise=True)
        except Exception as e:
            self._chyba(e)
            return
        # PRJ po POSTu, ať obnovení stránky import neopakuje
        self.send_response(303)
        self.send_header("Location", "/" if kod == 0 else "/?import=chyba")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    n = Nastaveni()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=n.web_port)
    p.add_argument("--generuj", metavar="SOUBOR", nargs="?", const=str(n.vystup),
                   help=f"zapíše obrazovku do souboru a skončí (výchozí {n.vystup})")
    p.add_argument("--vypis", action="store_true", help="vypíše HTML na stdout a skončí")
    p.add_argument("--cas", metavar="ČAS",
                   help="místo systémového času použít zadaný okamžik: "
                        "'9:02', '2026-09-03 09:02' nebo '3.9.2026 9:02'")
    args = p.parse_args()

    # 640 pro soubory / 750 pro adresáře: skupina signage čte, ostatní nic
    os.umask(0o027)

    global _PEVNY_CAS
    if args.cas:
        _PEVNY_CAS = parsuj_cas(args.cas)
    ted = aktualni_cas()

    if args.generuj:
        cil = Path(args.generuj)
        docasny = cil.with_suffix(cil.suffix + ".tmp")
        docasny.write_bytes(obrazovka(ted, n))
        # tmp soubor mohl přežít dřívější pád s jinými právy, srovnej je
        docasny.chmod(0o640)
        docasny.replace(cil)     # atomicky, ať prohlížeč nechytí půlku souboru
        print(f"Zapsáno do {cil}")
        return

    if args.vypis:
        sys.stdout.buffer.write(obrazovka(ted, n))
        return

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Signage běží na http://localhost:{args.port}/  (Ctrl-C ukončí)")
    if _PEVNY_CAS:
        print(f"POZOR: zastavený čas {_PEVNY_CAS:%-d.%-m.%Y %H:%M} — ne systémový.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkonec")


if __name__ == "__main__":
    main()
