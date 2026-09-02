"""Převod odpovědí ŠOL na jednoduchou strukturu pro zobrazení.

Odpovědi API jsou hodně rozvětvené a řada polí je volitelných (nullable), proto
se tu všechno tahá defenzivně přes .get() — chybějící údaj se jen nevypíše.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import SolClient

DNY_CESKY = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]


def _nazev(uzel: Any, *klice: str) -> str:
    """Vytáhne první neprázdný z klíčů; snese None i prostý řetězec."""
    if uzel is None:
        return ""
    if isinstance(uzel, str):
        return uzel
    if not isinstance(uzel, dict):
        return str(uzel)
    for k in klice:
        h = uzel.get(k)
        if h:
            return str(h)
    return ""


def _cas(hodnota: str | None) -> str:
    """'1900-01-01T08:30:00' i '08:30:00' -> '8:30'."""
    if not hodnota:
        return ""
    cast = hodnota.split("T")[-1]
    hodiny, _, zbytek = cast.partition(":")
    minuty = zbytek.split(":")[0] if zbytek else "00"
    try:
        return f"{int(hodiny)}:{minuty}"
    except ValueError:
        return cast


def _klic_razeni(h: "Hodina") -> tuple[int, int, int]:
    """Řadí podle času začátku; '10:30' se nesmí porovnávat jako řetězec."""
    hod, _, minuty = h.od.partition(":")
    try:
        cas = (int(hod), int(minuty))
    except ValueError:
        cas = (99, 99)
    try:
        poradi = int(h.poradi)
    except ValueError:
        poradi = 99
    return (*cas, poradi)


@dataclass
class Hodina:
    poradi: str = ""
    od: str = ""
    do: str = ""
    predmet: str = ""
    ucitele: list[str] = field(default_factory=list)
    ucebny: list[str] = field(default_factory=list)
    skupiny: list[str] = field(default_factory=list)
    poznamka: str = ""
    barva: str = ""

    @classmethod
    def z_api(cls, h: dict[str, Any]) -> "Hodina":
        return cls(
            poradi=str(h.get("scheduledHourOrder") or h.get("lessonIdFrom") or ""),
            od=_cas(h.get("beginTime")),
            do=_cas(h.get("endTime")),
            predmet=(_nazev(h.get("subject"), "name", "abbrev")
                     or h.get("title") or _nazev(h.get("hourType"), "name") or "—"),
            ucitele=[_nazev(u, "displayName", "surname", "abbrev")
                     for u in (h.get("teachers") or []) if _nazev(u, "displayName", "surname", "abbrev")],
            ucebny=[_nazev(m, "abbrev", "name") for m in (h.get("rooms") or []) if _nazev(m, "abbrev", "name")],
            skupiny=[_nazev(s, "name") for s in (h.get("groups") or []) if _nazev(s, "name")],
            poznamka=(h.get("description") or "").strip(),
            barva=h.get("hourColour") or "",
        )


@dataclass
class RozvrhTridy:
    trida: str
    hodiny: list[Hodina] = field(default_factory=list)
    chyba: str = ""


def rozvrhy_trid_na_den(klient: SolClient, datum: str, skolni_rok: str | None = None,
                        ukazka: bool = False) -> tuple[list[RozvrhTridy], dict[str, Any]]:
    """Načte rozvrh všech tříd pro jeden den (``datum`` ve tvaru RRRR-MM-DD).

    Vrací seznam rozvrhů v pořadí tříd a slovník s kontextem (uživatel, školní
    rok, číselník časů hodin) pro hlavičku stránky.
    """
    uzivatel = klient.uzivatel()
    skolni_rok = skolni_rok or uzivatel["schoolYearId"]

    vysledek: list[RozvrhTridy] = []
    casy_hodin: list[dict[str, Any]] = []

    for trida in klient.tridy(skolni_rok):
        r = RozvrhTridy(trida=trida.get("name") or trida["classId"])
        try:
            if ukazka:
                from .ukazka import ukazkova_odpoved
                odpoved = ukazkova_odpoved(r.trida)
            else:
                odpoved = klient.rozvrh(skolni_rok, datum, datum, trida["classId"])
        except Exception as e:  # jedna rozbitá třída nesmí shodit celou stránku
            r.chyba = str(e)
            vysledek.append(r)
            continue
        casy_hodin = casy_hodin or odpoved.get("lessons") or []
        for den in odpoved.get("days") or []:
            for h in den.get("schedules") or []:
                r.hodiny.append(Hodina.z_api(h))
        r.hodiny.sort(key=_klic_razeni)
        vysledek.append(r)

    kontext = {
        "uzivatel": uzivatel,
        "skolni_rok": skolni_rok,
        "rok_od_do": klient.ciselniky_rozvrhu(skolni_rok).get("schoolYear", {}),
        "casy_hodin": casy_hodin,
    }
    return vysledek, kontext
