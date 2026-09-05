"""Parser formuláře KRO003 „Rozvrh třídy“ v **měsíčním** režimu.

KRO029 (denní, všechny třídy) umí jen dnešek — datum v kalendáři nejde
spolehlivě přepnout. KRO003 v měsíčním režimu naopak vrátí celý aktuální měsíc
pro **jednu** třídu bez nutnosti navigovat kalendář, takže se z něj dá naplnit
rozvrh na dnešek i dny dopředu. Cenou je jeden dotaz na třídu.

Mřížka je tatáž ``<table id="CCADynamicCalendarTable">`` jako u KRO029, jen
řádek = **den** (label „Út 1.9.“), ne třída. Proto se použije stejný maticový
parser i stejné čtení buněk (tooltip, AbsZdroj) z ``denni_rozvrh``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .denni_rozvrh import (
    TRIDA_AKCE,
    TRIDA_HODINY,
    Hodina,
    _hodina_z_bunky,
    _mrizka,
)
from .dom import parsuj

if TYPE_CHECKING:
    from .web_klient import SolWebKlient

MRIZKA_ID = "CCADynamicCalendarTable"
# druhé pole igcal_init: "selY,selM,selD,zobrY,zobrM,..." → zobrazený rok
_IGCAL = re.compile(r'igcal_init\("[^"]+","(\d+),\d+,\d+,(\d+),(\d+)')
_DEN = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.")


def _zobrazeny_rok(html: str) -> int:
    m = _IGCAL.search(html)
    return int(m.group(2)) if m else 0


def _vybrana_trida(koren) -> str:
    for sel in koren.najdi("select"):
        if "DDLTrida" in (sel.attrs.get("name", "") + sel.attrs.get("id", "")):
            for opt in sel.najdi("option"):
                if "selected" in opt.attrs:
                    return opt.txt()
    return ""


def _casy(matice) -> list[tuple[str, str, str]]:
    casy = []
    for bunka in matice[0][1:]:
        if bunka is None:
            continue
        r = [td.txt() for td in bunka.najdi("td")]
        cislo = r[0] if r else ""
        od, _, do = (c.strip() for c in (r[1] if len(r) > 1 else "").partition("-"))
        casy.append((cislo, od, do))
    return casy


def parsuj_mesicni(html: str) -> tuple[str, list[tuple[str, str, str]], dict[str, list[Hodina]]]:
    """Vrátí ``(trida, casy, {datum_iso: [Hodina, …]})`` pro jednu třídu.

    ``casy`` je číselník časů vyučovacích hodin (stejný pro všechny dny).
    """
    koren = parsuj(html)
    trida = _vybrana_trida(koren)
    rok = _zobrazeny_rok(html)

    tabulky = koren.najdi("table", id=MRIZKA_ID)
    if not tabulky:
        raise ValueError(f"Ve stránce KRO003 chybí mřížka {MRIZKA_ID}.")
    matice = _mrizka(tabulky[0])
    casy = _casy(matice) if matice else []

    dny: dict[str, list[Hodina]] = {}
    aktualni: str | None = None
    for radek in matice[1:]:
        if not radek:
            continue
        zahlavi = radek[0]
        if zahlavi is not None and zahlavi.txt():
            m = _DEN.search(zahlavi.txt())
            aktualni = f"{rok}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if (m and rok) else None
            if aktualni is not None:
                dny.setdefault(aktualni, [])
        if aktualni is None:
            continue
        for i, bunka in enumerate(radek[1:], start=1):
            if bunka is None:
                continue
            for vnitrni in bunka.najdi("td"):
                if not (vnitrni.tridy & {TRIDA_HODINY, TRIDA_AKCE}):
                    continue
                sirka = max(1, int(bunka.attrs.get("colspan", "1") or 1))
                h = _hodina_z_bunky(vnitrni, i, i + sirka - 1)
                if h.od_hodiny - 1 < len(casy):
                    h.od = casy[h.od_hodiny - 1][1]
                if h.do_hodiny - 1 < len(casy):
                    h.do = casy[h.do_hodiny - 1][2]
                dny[aktualni].append(h)

    for d in dny.values():
        d.sort(key=lambda h: h.od_hodiny)
    return trida, casy, dny


_HIDDEN = re.compile(r'<input[^>]*type="hidden"[^>]*>')


def _skryta_pole(html: str) -> dict[str, str]:
    pole = {}
    for m in _HIDDEN.finditer(html):
        n = re.search(r'name="([^"]+)"', m.group())
        v = re.search(r'value="([^"]*)"', m.group())
        if n:
            pole[n.group(1)] = v.group(1) if v else ""
    return pole


def _ddl(koren):
    """Vrátí (name, [(value, text), …]) rozbalovacího seznamu tříd."""
    for sel in koren.najdi("select"):
        jmeno = sel.attrs.get("name", "") or sel.attrs.get("id", "")
        if "DDLTrida" in jmeno:
            opts = [(o.attrs.get("value", ""), o.txt())
                    for o in sel.najdi("option") if o.attrs.get("value")]
            return sel.attrs.get("name", jmeno), opts
    raise ValueError("KRO003: rozbalovaci seznam trid (DDLTrida) nenalezen.")


def stahni_mesicni_rozvrh(klient):
    """Stáhne měsíční rozvrh všech tříd z KRO003.

    Jeden GET (kvůli VIEWSTATE a seznamu tříd) + jeden POST na třídu (přepnutí
    do měsíčního režimu a výběr třídy); VIEWSTATE se řetězí. Vrací
    ``(casy, tridy_poradi, {datum: {trida: [Hodina]}}, datum_od, datum_do)``.
    """
    uvod = klient.stranka(klient.ROZVRH_TRIDY)
    ddl_name, opce = _ddl(parsuj(uvod))
    pole = _skryta_pole(uvod)

    casy = []
    tridy_poradi = []
    dny = {}

    for cid, nazev in opce:
        data = dict(pole)
        data[ddl_name] = cid
        data["calendarPart$kalendar$RBSelectionMode"] = "Month"
        data["__EVENTTARGET"] = ddl_name
        data["__EVENTARGUMENT"] = ""
        html = klient.post(klient.ROZVRH_TRIDY, data)
        pole = _skryta_pole(html)  # VIEWSTATE pro další kolo

        trida, tridni_casy, tridni_dny = parsuj_mesicni(html)
        trida = trida or nazev
        casy = casy or tridni_casy
        tridy_poradi.append(trida)
        for datum, hodiny in tridni_dny.items():
            dny.setdefault(datum, {})[trida] = hodiny

    if not dny:
        raise ValueError("KRO003 nevratil zadne dny.")
    return casy, tridy_poradi, dny, min(dny), max(dny)
