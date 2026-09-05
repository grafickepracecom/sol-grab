"""Perzistence rozvrhu v SQLite — více dní najednou.

Import (KRO003, měsíční pohled) sem uloží celé synchronizované okno (aktuální
měsíc pro všechny třídy), signage si pak z něj čte **den odpovídající dnešku**.
Signage tak nezávisí na dostupnosti ŠOL a při výpadku má rezervu dní dopředu.

**Historie se nedrží** — každý import celý obsah nahradí v jedné transakci.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .config import KOREN
from .denni_rozvrh import DenniRozvrh, Hodina, RozvrhTridy

SOUBOR = KOREN / "rozvrh.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stav (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    naimportovano TEXT NOT NULL,   -- ISO čas posledního úspěšného importu
    datum_od      TEXT NOT NULL,   -- první den synchronizovaného okna (ISO)
    datum_do      TEXT NOT NULL    -- poslední den okna (ISO)
);

CREATE TABLE IF NOT EXISTS cas_hodiny (
    poradi INTEGER PRIMARY KEY,   -- 1..9
    cislo  TEXT NOT NULL,
    od     TEXT NOT NULL,
    do_    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trida (
    poradi INTEGER PRIMARY KEY,
    nazev  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hodina (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    datum       TEXT NOT NULL,     -- ke kterému dni hodina patří (ISO)
    trida       TEXT NOT NULL,
    od_hodiny   INTEGER NOT NULL,
    do_hodiny   INTEGER NOT NULL,
    od          TEXT NOT NULL,
    do_         TEXT NOT NULL,
    nazev       TEXT NOT NULL,
    plny_nazev  TEXT NOT NULL,
    ucitele     TEXT NOT NULL,     -- JSON seznam dílků {t, c}
    ucebna      TEXT NOT NULL,
    zaci        TEXT NOT NULL,
    akce        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS hodina_den ON hodina(datum, trida);
"""


def pripoj(soubor: Path | None = None) -> sqlite3.Connection:
    spojeni = sqlite3.connect(soubor or SOUBOR)
    spojeni.row_factory = sqlite3.Row
    _preved_schema(spojeni)
    spojeni.executescript(SCHEMA)
    return spojeni


def _preved_schema(spojeni: sqlite3.Connection) -> None:
    """Zahodí staré tabulky, když neodpovídají aktuálnímu schématu.

    Databáze je jen cache (regeneruje ji import), takže při změně struktury je
    nejjednodušší staré tabulky zahodit a nechat je znovu vytvořit a naplnit.
    """
    existuje = spojeni.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='hodina'").fetchone()
    if not existuje:
        return
    sloupce = {r["name"] for r in spojeni.execute("PRAGMA table_info(hodina)")}
    if "datum" not in sloupce:
        for tab in ("hodina", "trida", "cas_hodiny", "stav"):
            spojeni.execute(f"DROP TABLE IF EXISTS {tab}")
        spojeni.commit()


def lidsky_datum(datum_iso: str) -> str:
    """'2026-09-05' -> '5. 9. 2026'."""
    try:
        d = dt.date.fromisoformat(datum_iso)
        return f"{d.day}. {d.month}. {d.year}"
    except ValueError:
        return datum_iso


def uloz_mesic(spojeni: sqlite3.Connection,
               casy: list[tuple[str, str, str]],
               tridy_poradi: list[str],
               dny: dict[str, dict[str, list[Hodina]]],
               datum_od: str, datum_do: str) -> None:
    """Nahradí obsah databáze synchronizovaným oknem.

    ``dny`` = ``{datum_iso: {nazev_tridy: [Hodina, …]}}``.
    """
    with spojeni:
        spojeni.execute("DELETE FROM hodina")
        spojeni.execute("DELETE FROM trida")
        spojeni.execute("DELETE FROM cas_hodiny")
        spojeni.execute("DELETE FROM stav")

        spojeni.execute(
            "INSERT INTO stav (id, naimportovano, datum_od, datum_do) VALUES (1, ?, ?, ?)",
            (dt.datetime.now().isoformat(timespec="seconds"), datum_od, datum_do))
        spojeni.executemany(
            "INSERT INTO cas_hodiny (poradi, cislo, od, do_) VALUES (?, ?, ?, ?)",
            [(i, c[0], c[1], c[2]) for i, c in enumerate(casy, start=1)])
        spojeni.executemany(
            "INSERT INTO trida (poradi, nazev) VALUES (?, ?)",
            [(i, t) for i, t in enumerate(tridy_poradi, start=1)])

        radky = []
        for datum, podle_trid in dny.items():
            for trida, hodiny in podle_trid.items():
                for h in hodiny:
                    radky.append((
                        datum, trida, h.od_hodiny, h.do_hodiny, h.od, h.do,
                        h.nazev, h.plny_nazev,
                        json.dumps(h.ucitele, ensure_ascii=False),
                        json.dumps(h.ucebna, ensure_ascii=False),
                        json.dumps(h.zaci, ensure_ascii=False), int(h.akce)))
        spojeni.executemany(
            "INSERT INTO hodina (datum, trida, od_hodiny, do_hodiny, od, do_, nazev,"
            " plny_nazev, ucitele, ucebna, zaci, akce)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", radky)


def nacti(spojeni: sqlite3.Connection, datum_iso: str
          ) -> tuple[DenniRozvrh, dt.datetime, bool] | None:
    """Vrátí ``(rozvrh dne, čas importu, v_okně)`` pro daný den.

    ``v_okně`` říká, zda datum spadá do synchronizovaného okna — když ne, jsou
    data neaktuální (signage přes ně položí překryv). Třídy se vracejí všechny
    (i s prázdným dnem), aby obrazovka vždy ukázala jejich popisky.
    Vrací None, když se ještě nikdy neimportovalo.
    """
    stav = spojeni.execute("SELECT * FROM stav WHERE id = 1").fetchone()
    if stav is None:
        return None

    rozvrh = DenniRozvrh(datum=lidsky_datum(datum_iso))
    rozvrh.casy = [(r["cislo"], r["od"], r["do_"]) for r in
                   spojeni.execute("SELECT * FROM cas_hodiny ORDER BY poradi")]

    for t in spojeni.execute("SELECT nazev FROM trida ORDER BY poradi"):
        hodiny = [Hodina(od_hodiny=h["od_hodiny"], do_hodiny=h["do_hodiny"],
                         od=h["od"], do=h["do_"], nazev=h["nazev"],
                         plny_nazev=h["plny_nazev"],
                         ucitele=json.loads(h["ucitele"]),
                         ucebna=json.loads(h["ucebna"]),
                         zaci=json.loads(h["zaci"]), akce=bool(h["akce"]))
                  for h in spojeni.execute(
                      "SELECT * FROM hodina WHERE datum = ? AND trida = ? ORDER BY od_hodiny, id",
                      (datum_iso, t["nazev"]))]
        rozvrh.tridy.append(RozvrhTridy(trida=t["nazev"], hodiny=hodiny))

    v_okne = stav["datum_od"] <= datum_iso <= stav["datum_do"]
    return rozvrh, dt.datetime.fromisoformat(stav["naimportovano"]), v_okne
