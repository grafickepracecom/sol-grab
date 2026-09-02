"""Ukázková data ve tvaru, v jakém je vrací ŠOL.

Rozvrh na 2026/2027 ve ŠOL zatím zadaný není, takže se na skutečných datech
nedá vyzkoušet vykreslování. Tenhle vzorek jde stejnou cestou jako ostrá
odpověď (``Hodina.z_api``), takže ověřuje reálný kód, ne jeho obdobu.
Struktura odpovídá schématu ``SOL.API.Models.Timetable.ScheduledHour``
z ``/solapi/swagger/v1/swagger.json``.
"""

from __future__ import annotations

from typing import Any


def _hodina(poradi: int, od: str, do: str, predmet: str, ucitel: str,
            ucebna: str, skupina: str | None = None) -> dict[str, Any]:
    return {
        "scheduledHourId": f"E{900000 + poradi}",
        "scheduledHourOrder": poradi,
        "lessonIdFrom": str(poradi),
        "lessonIdTo": str(poradi),
        "beginTime": f"1900-01-01T{od}:00",
        "endTime": f"1900-01-01T{do}:00",
        "subject": {"id": "E1", "abbrev": predmet[:3], "name": predmet},
        "teachers": [{"id": "E2", "abbrev": "XX", "surname": ucitel.split()[-1],
                      "displayName": ucitel}],
        "rooms": [{"id": "E3", "abbrev": ucebna, "name": ucebna}],
        "groups": ([{"id": "E4", "name": skupina}] if skupina else []),
        "hourColour": "#e8f0fe",
        "description": "",
    }


UKAZKA: dict[str, list[dict[str, Any]]] = {
    "I.": [
        _hodina(1, "08:30", "09:20", "Hlavní vyučování", "Jana Nováková", "1.tř"),
        _hodina(2, "09:20", "10:10", "Hlavní vyučování", "Jana Nováková", "1.tř"),
        _hodina(3, "10:30", "11:15", "Eurytmie", "Petr Svoboda", "sál"),
    ],
    "VI.": [
        _hodina(1, "08:30", "09:20", "Matematika", "Eva Dvořáková", "6.tř"),
        _hodina(2, "09:20", "10:10", "Matematika", "Eva Dvořáková", "6.tř"),
        _hodina(3, "10:30", "11:15", "Angličtina", "Tom Marek", "jaz", "AJ1"),
        _hodina(4, "11:25", "12:10", "Tělesná výchova", "Petr Svoboda", "tělo"),
    ],
    "IX.": [
        _hodina(3, "10:30", "11:15", "Fyzika", "Karel Beneš", "lab"),
        _hodina(4, "11:25", "12:10", "Dějepis", "Alena Horáková", "9.tř"),
    ],
}


def ukazkova_odpoved(nazev_tridy: str) -> dict[str, Any]:
    """Odpověď /api/v1/timeTable pro jednu třídu, jak by ji vrátila ŠOL."""
    return {"days": [{"date": "2026-09-02T00:00:00", "schedules": UKAZKA.get(nazev_tridy, [])}],
            "lessons": []}
