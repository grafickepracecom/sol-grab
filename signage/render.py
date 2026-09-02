"""Vykreslení signage obrazovky do HTML.

Rozvržení jako televizní program: vlevo sloupec tříd, nahoře časová osa,
bloky výuky umístěné absolutně podle procentuální pozice z ``signage.model``.
Svislá čára ukazuje aktuální chvíli.

Řádky se dělí o výšku flex poměrem podle počtu drah a bloky se uvnitř umísťují
procentuálně, takže se obrazovka vejde vždycky — i ve dnech s hodně paralelními
skupinami — a nikdy neroluje.
"""

from __future__ import annotations

import datetime as dt
import html

from .model import Obrazovka

STYL = """
* { box-sizing: border-box; }
body { margin: 0; background: #10151c; color: #e8edf4;
       font-family: system-ui, -apple-system, sans-serif; overflow: hidden; }
.obrazovka { height: 100vh; display: flex; flex-direction: column; padding: 1.2vh 1vw; }

header { display: flex; align-items: baseline; gap: 1.2vw; margin-bottom: 1vh; }
h1 { font-size: 2.6vh; margin: 0; font-weight: 600; }
header .cas { font-size: 3.4vh; font-weight: 700; color: #ffd479; margin-left: auto; }
header .zdroj { font-size: 1.5vh; color: #7f8c9b; }
header .zdroj.stary { color: #ffb454; }
header form { margin: 0; }
header button { font: inherit; font-size: 1.4vh; background: #1e2732; color: #9fb0c4;
                border: 1px solid #33415280; border-radius: 4px; padding: .3vh .7vw;
                cursor: pointer; }
header button:hover { background: #26313e; color: #e8edf4; }

.osa { display: flex; margin-left: var(--stitek); position: relative; height: 2.4vh;
       border-bottom: 1px solid #2b3644; }
.osa .znacka { position: absolute; font-size: 1.5vh; color: #8b9aab;
               transform: translateX(-50%); white-space: nowrap; }

.telo { position: relative; flex: 1; min-height: 0; display: flex;
        flex-direction: column; overflow: hidden; }
.radek { display: flex; align-items: stretch; border-bottom: 1px solid #1d2530;
         min-height: 0; }
.stitek { width: var(--stitek); flex: none; display: flex; align-items: center;
          font-size: 2vh; font-weight: 600; color: #b9c6d6; padding-left: .4vw; }
.stopa { position: relative; flex: 1; }

.blok { position: absolute; overflow: hidden; border-radius: 4px;
        padding: .2vh .35vw; background: #24405e; border: 1px solid #33587f;
        font-size: calc(var(--pismo) * 1.05); line-height: 1.15; white-space: nowrap; }
.blok .nazev { font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
.blok .detail { color: #a9bdd4; font-size: calc(var(--pismo) * .9); overflow: hidden; text-overflow: ellipsis; }
.blok.akce { background: #5a3f18; border-color: #8a6427; }
.blok.akce .detail { color: #d9c197; }
.blok.probiha { border-color: #ffd479; box-shadow: 0 0 0 1px #ffd47966; }
.blok.vlevo { border-top-left-radius: 0; border-bottom-left-radius: 0; border-left-style: dashed; }
.blok.vpravo { border-top-right-radius: 0; border-bottom-right-radius: 0; border-right-style: dashed; }

.mrizka { position: absolute; inset: 0; margin-left: var(--stitek); pointer-events: none; }
.mrizka .cara { position: absolute; top: 0; bottom: 0; width: 1px; background: #222c3866; }
.ted { position: absolute; top: 0; bottom: 0; width: 2px; background: #ffd479;
       box-shadow: 0 0 6px #ffd47999; }

.prazdno { color: #7f8c9b; font-size: 2vh; padding: 4vh 1vw; }
"""


def _blok(b, drah: int) -> str:
    tridy = ["blok"]
    if b.akce:
        tridy.append("akce")
    if b.probiha:
        tridy.append("probiha")
    if b.presah_vlevo:
        tridy.append("vlevo")
    if b.presah_vpravo:
        tridy.append("vpravo")

    detail = " · ".join(filter(None, [b.ucitel, b.ucebna]))
    # pozice uvnitř řádku v % jeho výšky — řádek si výšku bere z flexu
    styl = (f"left:{b.zleva:.3f}%;width:{b.sirka:.3f}%;"
            f"top:{b.draha / drah * 100:.3f}%;"
            f"height:calc({100 / drah:.3f}% - .4vh)")
    return (f'<div class="{" ".join(tridy)}" style="{styl}" '
            f'title="{html.escape(f"{b.od}–{b.do} {b.nazev} {detail}")}">'
            f'<div class=nazev>{html.escape(b.nazev)}</div>'
            + (f'<div class=detail>{html.escape(detail)}</div>' if detail else "")
            + "</div>")


def vykresli(obrazovka: Obrazovka, datum_text: str, naimportovano: dt.datetime,
             ted: dt.datetime, obnova_s: int = 60, sirka_stitku: str = "5vw") -> bytes:
    stari = int((ted - naimportovano).total_seconds() // 60)
    stary = stari > 60
    popis_stari = "právě teď" if stari < 1 else (
        f"před {stari} min" if stari < 60 else f"před {stari // 60} h {stari % 60} min")

    # při hodně drahách se zmenší písmo, ať se do bloku pořád něco vejde
    celkem_drah = sum(r.drahy for r in obrazovka.radky) or 1
    pismo = min(1.6, max(0.9, 32.0 / celkem_drah))

    trida_zdroje = "zdroj stary" if stary else "zdroj"
    cast = [
        "<div class=obrazovka>",
        "<header>",
        f"<h1>Rozvrh — {html.escape(datum_text)}</h1>",
        f"<span class='{trida_zdroje}'>data ze ŠOL {popis_stari}</span>",
        '<form method=post action="/import"><button>Načíst ze ŠOL</button></form>',
        f"<span class=cas>{ted.strftime('%H:%M')}</span>",
        "</header>",
        "<div class=osa>",
    ]
    for z in obrazovka.znacky:
        cast.append(f'<span class=znacka style="left:{z.zleva:.3f}%">{html.escape(z.popisek)}</span>')
    cast.append("</div>")

    cast.append("<div class=telo>")
    if not obrazovka.radky:
        cast.append("<p class=prazdno>V databázi není žádný rozvrh — spusťte import.</p>")
    for r in obrazovka.radky:
        # flex-grow podle počtu drah: třída se třemi skupinami dostane 3x víc místa
        cast.append(f'<div class=radek style="flex:{r.drahy} 1 0">'
                    f'<div class=stitek>{html.escape(r.trida)}</div>'
                    f'<div class=stopa>')
        cast += [_blok(b, r.drahy) for b in r.bloky]
        cast.append("</div></div>")

    # mřížka a čára "teď" leží přes celé tělo, aby procházely všemi třídami
    cast.append('<div class=mrizka>')
    cast += [f'<div class=cara style="left:{z.zleva:.3f}%"></div>' for z in obrazovka.znacky]
    cast.append(f'<div class=ted style="left:{obrazovka.ted_zleva:.3f}%"></div>')
    cast.append("</div></div></div>")

    return (
        "<!doctype html><html lang=cs><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv=refresh content='{obnova_s}'>"
        f"<title>Rozvrh {html.escape(datum_text)}</title>"
        f"<style>:root{{--stitek:{sirka_stitku};--pismo:{pismo:.2f}vh}}{STYL}</style>"
        + "".join(cast)
    ).encode("utf-8")
