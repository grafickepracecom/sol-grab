#!/usr/bin/env python3
"""Jednoduchý náhled rozvrhů tříd ze Školy OnLine.

Prototyp — vestavěný HTTP server ze standardní knihovny, žádné závislosti,
minimum formátování. Cílem je ověřit napojení a mít podklad pro pozdější
signage aplikaci do sborovny.

    python3 web.py                 # poslouchá na portu z .env (výchozí 8081)
    python3 web.py --datum 2026-09-02
    python3 web.py --port 9000

Datum jde přepnout i v URL: /?datum=2026-09-02
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sol.client import SolClient
from sol.config import Nastaveni
from sol.rozvrhy import DNY_CESKY, rozvrhy_trid_na_den

STYL = """
body { font-family: system-ui, sans-serif; margin: 1.5rem; color: #222; }
h1 { font-size: 1.4rem; margin: 0 0 .2rem; }
.hlavicka { color: #666; font-size: .85rem; margin-bottom: 1.2rem; }
.mrizka { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
.trida { border: 1px solid #ccc; border-radius: 6px; padding: .6rem .8rem; }
.trida h2 { font-size: 1.1rem; margin: 0 0 .4rem; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
td { padding: .18rem .3rem; vertical-align: top; border-top: 1px solid #eee; }
td.cas { white-space: nowrap; color: #666; width: 1%; }
td.predmet { font-weight: 600; }
.detail { font-weight: 400; color: #666; }
.prazdno { color: #999; font-style: italic; font-size: .85rem; }
.chyba { color: #b00; font-size: .85rem; white-space: pre-wrap; }
form { margin-bottom: 1rem; }
"""


def _stranka(telo: str, nadpis: str) -> bytes:
    return (f"<!doctype html><html lang=cs><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(nadpis)}</title><style>{STYL}</style>{telo}"
            ).encode("utf-8")


def vykresli(datum: str, ukazka: bool = False) -> bytes:
    klient = SolClient()
    rozvrhy, kontext = rozvrhy_trid_na_den(klient, datum, ukazka=ukazka)

    d = dt.date.fromisoformat(datum)
    u = kontext["uzivatel"]
    rok = kontext["rok_od_do"]
    rozsah = ""
    if rok.get("dateFrom") and rok.get("dateTo"):
        rozsah = (f' ({rok["dateFrom"][:10]} – {rok["dateTo"][:10]})')

    cast = [
        f"<h1>Rozvrhy tříd — {DNY_CESKY[d.weekday()]} {d.day}. {d.month}. {d.year}</h1>",
        "<p class=hlavicka>"
        f"{html.escape(u.get('schoolOrganizationName', ''))} · "
        f"přihlášen {html.escape(u.get('fullName', ''))} ({html.escape(u.get('userTypeText', ''))}) · "
        f"školní rok {html.escape(kontext['skolni_rok'])}{html.escape(rozsah)}</p>",
        f"<form><label>Datum: <input type=date name=datum value='{html.escape(datum)}'></label> "
        "<button>Zobrazit</button></form>",
        "<div class=mrizka>",
    ]

    for r in rozvrhy:
        cast.append(f"<div class=trida><h2>{html.escape(r.trida)}</h2>")
        if r.chyba:
            cast.append(f"<p class=chyba>{html.escape(r.chyba)}</p>")
        elif not r.hodiny:
            cast.append("<p class=prazdno>Žádné hodiny</p>")
        else:
            cast.append("<table>")
            for h in r.hodiny:
                detaily = " · ".join(filter(None, [
                    ", ".join(h.ucitele), ", ".join(h.ucebny), ", ".join(h.skupiny), h.poznamka,
                ]))
                cast.append(
                    "<tr>"
                    f"<td class=cas>{html.escape(h.od)}–{html.escape(h.do)}</td>"
                    f"<td class=predmet>{html.escape(h.predmet)}"
                    + (f"<div class=detail>{html.escape(detaily)}</div>" if detaily else "")
                    + "</td></tr>"
                )
            cast.append("</table>")
        cast.append("</div>")

    cast.append("</div>")
    if not any(r.hodiny for r in rozvrhy):
        cast.append("<p class=prazdno>Pro tento den nevrátila ŠOL žádné rozvrhované hodiny "
                    "— rozvrh na dané období zřejmě ještě není ve ŠOL zadaný.</p>")
    return _stranka("".join(cast), f"Rozvrhy tříd {datum}")


class Handler(BaseHTTPRequestHandler):
    server_version = "sol-grab"

    def do_GET(self) -> None:  # noqa: N802 (jméno předepisuje BaseHTTPRequestHandler)
        adresa = urlparse(self.path)
        if adresa.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        datum = (parse_qs(adresa.query).get("datum") or [dt.date.today().isoformat()])[0]
        try:
            dt.date.fromisoformat(datum)
        except ValueError:
            telo = _stranka(f"<h1>Chybné datum</h1><p>„{html.escape(datum)}“ není datum "
                            "ve tvaru RRRR-MM-DD.</p>", "Chybné datum")
            self._odesli(400, telo)
            return
        try:
            telo, kod = vykresli(datum), 200
        except Exception:
            telo = _stranka(f"<h1>Chyba</h1><pre class=chyba>{html.escape(traceback.format_exc())}</pre>",
                            "Chyba")
            kod = 500
        self._odesli(kod, telo)

    def _odesli(self, kod: int, telo: bytes) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(telo)))
        self.end_headers()
        self.wfile.write(telo)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}")


def main() -> None:
    n = Nastaveni()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=n.web_port)
    p.add_argument("--datum", help="jen vypíše HTML na stdout a skončí")
    p.add_argument("--ukazka", action="store_true",
                   help="místo dat ze ŠOL použije ukázkový rozvrh (sol/ukazka.py)")
    args = p.parse_args()

    if args.datum:
        print(vykresli(args.datum, ukazka=args.ukazka).decode("utf-8"))
        return

    n.zkontroluj()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Běží na http://localhost:{args.port}/  (Ctrl-C ukončí)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkonec")


if __name__ == "__main__":
    main()
