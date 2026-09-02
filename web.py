#!/usr/bin/env python3
"""Náhled denního rozvrhu všech tříd ze Školy OnLine.

Prototyp — vestavěný HTTP server ze standardní knihovny, žádné závislosti.
Podklad pro signage do sborovny.

    python3 web.py              # poslouchá na portu z .env (výchozí 8081)
    python3 web.py --port 9000
    python3 web.py --vypis      # vypíše HTML na stdout a skončí

Data se berou z formuláře ŠOL „Denní podle tříd“ (KRO029), který vrací rozvrh
všech tříd na **dnešek** — jiný den zatím vybrat nejde, viz README.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from sol.config import Nastaveni
from sol.denni_rozvrh import DenniRozvrh, datum_iso, parsuj_denni_rozvrh
from sol.web_klient import SolWebKlient

DNY = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]

STYL = """
body { font-family: system-ui, sans-serif; margin: 1.5rem; color: #222; }
h1 { font-size: 1.4rem; margin: 0 0 .2rem; }
.hlavicka { color: #666; font-size: .85rem; margin-bottom: 1.2rem; }
.mrizka { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
.trida { border: 1px solid #ccc; border-radius: 6px; padding: .6rem .8rem; }
.trida h2 { font-size: 1.1rem; margin: 0 0 .4rem; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
td { padding: .2rem .3rem; vertical-align: top; border-top: 1px solid #eee; }
td.cas { white-space: nowrap; color: #666; width: 1%; }
td.predmet { font-weight: 600; }
.detail { font-weight: 400; color: #666; }
.akce td.predmet { color: #a35200; }
tr.ted { background: #fff6d9; }
tr.ted td.cas::after { content: " ▸"; color: #c08a00; }
.prazdno { color: #999; font-style: italic; font-size: .85rem; }
.chyba { color: #b00; white-space: pre-wrap; font-size: .85rem; }
"""


def _stranka(telo: str, nadpis: str) -> bytes:
    return (f"<!doctype html><html lang=cs><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(nadpis)}</title><style>{STYL}</style>{telo}").encode("utf-8")


def _minuty(cas: str) -> int | None:
    try:
        h, _, m = cas.partition(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def vykresli(rozvrh: DenniRozvrh, ted: dt.datetime | None = None) -> bytes:
    ted = ted or dt.datetime.now()
    iso = datum_iso(rozvrh)
    nadpis = rozvrh.datum or "?"
    if iso:
        d = dt.date.fromisoformat(iso)
        nadpis = f"{DNY[d.weekday()]} {d.day}. {d.month}. {d.year}"
    # zvýrazňovat „právě teď“ dává smysl jen když se zobrazuje dnešek
    minuty_ted = ted.hour * 60 + ted.minute if iso == ted.date().isoformat() else None

    cast = [
        f"<h1>Rozvrhy tříd — {html.escape(nadpis)}</h1>",
        f"<p class=hlavicka>Škola OnLine, formulář „Denní podle tříd“ (KRO029) · "
        f"{len(rozvrh.tridy)} tříd, {rozvrh.pocet_hodin} položek · "
        f"načteno {ted.strftime('%H:%M:%S')}</p>",
        "<div class=mrizka>",
    ]

    for t in rozvrh.tridy:
        cast.append(f"<div class=trida><h2>{html.escape(t.trida)}</h2>")
        if not t.hodiny:
            cast.append("<p class=prazdno>Žádné hodiny</p>")
        else:
            cast.append("<table>")
            for h in t.hodiny:
                zac, kon = _minuty(h.od), _minuty(h.do)
                probiha = (minuty_ted is not None and zac is not None and kon is not None
                           and zac <= minuty_ted < kon)
                detaily = " · ".join(filter(None, [h.ucitele, h.ucebna, h.zaci]))
                cast.append(
                    f"<tr class='{'akce ' if h.akce else ''}{'ted' if probiha else ''}'>"
                    f"<td class=cas>{html.escape(h.od)}–{html.escape(h.do)}</td>"
                    f"<td class=predmet>{html.escape(h.popis)}"
                    + (f"<div class=detail>{html.escape(detaily)}</div>" if detaily else "")
                    + "</td></tr>"
                )
            cast.append("</table>")
        cast.append("</div>")

    cast.append("</div>")
    if not rozvrh.pocet_hodin:
        cast.append("<p class=prazdno>ŠOL pro dnešek nevrátila žádné hodiny.</p>")
    return _stranka("".join(cast), f"Rozvrhy tříd {iso or ''}".strip())


def nacti_a_vykresli() -> bytes:
    return vykresli(parsuj_denni_rozvrh(SolWebKlient().denni_podle_trid()))


class Handler(BaseHTTPRequestHandler):
    server_version = "sol-grab"

    def do_GET(self) -> None:  # noqa: N802 (jméno předepisuje BaseHTTPRequestHandler)
        if urlparse(self.path).path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            telo, kod = nacti_a_vykresli(), 200
        except Exception:
            telo = _stranka(
                f"<h1>Chyba</h1><pre class=chyba>{html.escape(traceback.format_exc())}</pre>",
                "Chyba")
            kod = 500
        self.send_response(kod)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(telo)))
        self.end_headers()
        self.wfile.write(telo)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    n = Nastaveni()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=n.web_port)
    p.add_argument("--vypis", action="store_true", help="vypíše HTML na stdout a skončí")
    args = p.parse_args()

    if args.vypis:
        print(nacti_a_vykresli().decode("utf-8"))
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
