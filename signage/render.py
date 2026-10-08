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

from sol.denni_rozvrh import dily_text

from .model import Obrazovka


def dily_html(dily: list[dict]) -> str:
    """Bezpečné HTML dílků z knihovny: text zaescapovaný, absentující zdroj
    (učitel/učebna mimo) obalený ``<span class="sol_…">`` k obarvení.
    Cizí HTML se na výstup nedostane — třída je jen jméno, text je escapovaný."""
    out = []
    for d in dily:
        t = html.escape(d["t"])
        out.append(f'<span class="{html.escape(d["c"])}">{t}</span>' if d["c"] else t)
    return "".join(out)

STYL = """
* { box-sizing: border-box; }
body { margin: 0; background: #10151c; color: #e8edf4;
       font-family: system-ui, -apple-system, sans-serif; overflow: hidden;
       animation: prichod .6s ease-out; }
/* fade-in při každém načtení: garlic-player mezi stránkami jen střihne,
   tak si přechod udělá stránka sama */
@keyframes prichod { from { opacity: 0 } to { opacity: 1 } }
.obrazovka { height: 100vh; display: flex; flex-direction: column; padding: 1.2vh 1vw; }

header { display: flex; align-items: baseline; gap: 1.2vw; margin-bottom: 1vh; }
h1 { font-size: 2.6vh; margin: 0; font-weight: 600; }
header .cas { font-size: 3.4vh; font-weight: 700; color: #ffd479; margin-left: auto; }
header .zdroj { font-size: 1.5vh; color: #7f8c9b; }
header .zdroj.stary { color: #ffb454; }
header .zdroj.kriticky { color: #ff6b6b; font-weight: 600; }
/* červená linka v záhlaví při kriticky starých datech */
header.kriticky { border-top: 3px solid #ff4d4d; padding-top: .6vh; }
/* chybějící zdroj (učitel/učebna mimo) — třída ze ŠOL s prefixem sol_ */
.sol_AbsZdroj { color: #ff6b6b; }
/* sudé/liché třídy jiným odstínem pro čitelnost; skupiny uvnitř sdílejí odstín */
.radek.licha { background: #0c1118; }
.radek.suda  { background: #141c26; }
/* překryv přes data, když nejsou aktuální */
.prekryv { position: absolute; inset: 0; display: flex; align-items: center;
           justify-content: center; background: rgba(16,21,28,.82); z-index: 10; }
.prekryv .panel { background: #1b2430; border: 2px solid #ff4d4d; border-radius: 10px;
                  padding: 3vh 4vw; text-align: center; max-width: 80%; }
.prekryv h2 { color: #ff6b6b; font-size: 3.4vh; margin: 0 0 1.2vh; }
.prekryv p { font-size: 2vh; margin: .4vh 0; color: #cdd6e0; }
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

    detail_html = " · ".join(filter(None, [dily_html(b.ucitel), dily_html(b.ucebna)]))
    detail_text = " · ".join(filter(None, [dily_text(b.ucitel), dily_text(b.ucebna)]))
    # pozice uvnitř řádku v % jeho výšky — řádek si výšku bere z flexu
    styl = (f"left:{b.zleva:.3f}%;width:{b.sirka:.3f}%;"
            f"top:{b.draha / drah * 100:.3f}%;"
            f"height:calc({100 / drah:.3f}% - .4vh)")
    return (f'<div class="{" ".join(tridy)}" style="{styl}" '
            f'title="{html.escape(f"{b.od}–{b.do} {b.nazev} {detail_text}")}">'
            f'<div class=nazev>{html.escape(b.nazev)}</div>'
            + (f'<div class=detail>{detail_html}</div>' if detail_html else "")
            + "</div>")


def vykresli(obrazovka: Obrazovka, datum_text: str, naimportovano: dt.datetime,
             ted: dt.datetime, obnova_s: int = 60, sirka_stitku: str = "5vw",
             v_okne: bool = True, varovani_min: int = 60, prekryv_hodin: int = 24) -> bytes:
    stari = max(0, int((ted - naimportovano).total_seconds() // 60))
    popis_stari = "právě teď" if stari < 1 else (
        f"před {stari} min" if stari < 60 else f"před {stari // 60} h {stari % 60} min")

    # dva nezávislé signály: stáří poslední synchronizace a zda je dnešek v datech
    den_sedi = v_okne
    stary = stari > 20                       # mírné zežloutnutí
    kriticky = stari > varovani_min          # červená linka v záhlaví
    # rozvrh pro jiný den se nesmí tvářit jako dnešní; totéž při >N h bez sync
    prekryt = (not den_sedi) or (stari > prekryv_hodin * 60)

    # při hodně drahách se zmenší písmo, ať se do bloku pořád něco vejde
    celkem_drah = sum(r.drahy for r in obrazovka.radky) or 1
    pismo = min(1.6, max(0.9, 32.0 / celkem_drah))

    trida_zdroje = "zdroj kriticky" if kriticky else ("zdroj stary" if stary else "zdroj")
    cast = [
        "<div class=obrazovka>",
        f"<header class={'kriticky' if kriticky else 'ok'}>",
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
    for i, r in enumerate(obrazovka.radky):
        # flex-grow podle počtu drah: třída se třemi skupinami dostane 3x víc místa;
        # sudé/liché třídy jiným odstínem (skupiny uvnitř sdílejí řádek = odstín)
        parita = "licha" if i % 2 else "suda"
        cast.append(f'<div class="radek {parita}" style="flex:{r.drahy} 1 0">'
                    f'<div class=stitek>{html.escape(r.trida)}</div>'
                    f'<div class=stopa>')
        cast += [_blok(b, r.drahy) for b in r.bloky]
        cast.append("</div></div>")

    # mřížka a čára "teď" leží přes celé tělo, aby procházely všemi třídami
    cast.append('<div class=mrizka>')
    cast += [f'<div class=cara style="left:{z.zleva:.3f}%"></div>' for z in obrazovka.znacky]
    cast.append(f'<div class=ted style="left:{obrazovka.ted_zleva:.3f}%"></div>')
    cast.append("</div>")  # /mrizka
    if prekryt:
        duvod = ("Data pro dnešek nejsou k dispozici." if not den_sedi
                 else "Rozvrh se dlouho nesynchronizoval.")
        cast.append(
            "<div class=prekryv><div class=panel>"
            "<h2>Rozvrh není aktuální</h2>"
            f"<p>{html.escape(duvod)}</p>"
            f"<p>Poslední data: {html.escape(datum_text or '—')}</p>"
            f"<p>Poslední synchronizace se ŠOL: {html.escape(popis_stari)}.</p>"
            "</div></div>")
    cast.append("</div></div>")  # /telo /obrazovka

    return (
        "<!doctype html><html lang=cs><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv=refresh content='{obnova_s}'>"
        f"<title>Rozvrh {html.escape(datum_text)}</title>"
        f"<style>:root{{--stitek:{sirka_stitku};--pismo:{pismo:.2f}vh}}{STYL}</style>"
        + "".join(cast)
    ).encode("utf-8")
