"""Perzistence naimportovaného rozvrhu v SQLite.

Dělí import od zobrazení: importní job (cron) sem rozvrh zapíše, signage si ho
odsud čte. Signage tak nezávisí na dostupnosti ŠOL a nechodí tam při každém
překreslení obrazovky.

**Historie se nedrží** — je tu vždycky jen poslední naimportovaný stav, každý
import celý obsah nahradí v jedné transakci. Kdyby někdy byla potřeba historie,
přibude do klíče datum a záznamy se přestanou mazat.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from .config import KOREN
from .denni_rozvrh import DenniRozvrh, Hodina, RozvrhTridy

SOUBOR = KOREN / "rozvrh.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stav (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    datum        TEXT NOT NULL,   -- datum rozvrhu, ISO (RRRR-MM-DD)
    datum_text   TEXT NOT NULL,   -- jak ho vypsala ŠOL ("2. 9. 2026")
    naimportovano TEXT NOT NULL   -- ISO čas posledního úspěšného importu
);

CREATE TABLE IF NOT EXISTS cas_hodiny (
    poradi INTEGER PRIMARY KEY,   -- 1..9
    cislo  TEXT NOT NULL,         -- popisek hodiny, jak ho dává ŠOL
    od     TEXT NOT NULL,         -- "08:30"
    do_    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trida (
    poradi INTEGER PRIMARY KEY,   -- pořadí, v jakém je vypisuje ŠOL
    nazev  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hodina (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trida       TEXT NOT NULL REFERENCES trida(nazev),
    od_hodiny   INTEGER NOT NULL,
    do_hodiny   INTEGER NOT NULL,
    od          TEXT NOT NULL,
    do_         TEXT NOT NULL,
    nazev       TEXT NOT NULL,
    plny_nazev  TEXT NOT NULL,
    ucitele     TEXT NOT NULL,
    ucebna      TEXT NOT NULL,
    zaci        TEXT NOT NULL,
    akce        INTEGER NOT NULL  -- 1 = školní akce, 0 = běžná výuka
);
CREATE INDEX IF NOT EXISTS hodina_trida ON hodina(trida);
"""


def pripoj(soubor: Path | None = None) -> sqlite3.Connection:
    spojeni = sqlite3.connect(soubor or SOUBOR)
    spojeni.row_factory = sqlite3.Row
    spojeni.execute("PRAGMA foreign_keys = ON")
    spojeni.executescript(SCHEMA)
    return spojeni


def uloz(spojeni: sqlite3.Connection, rozvrh: DenniRozvrh, datum_iso: str) -> None:
    """Nahradí obsah databáze naimportovaným rozvrhem (bez historie)."""
    with spojeni:  # jedna transakce — buď se vymění celý rozvrh, nebo nic
        spojeni.execute("DELETE FROM hodina")
        spojeni.execute("DELETE FROM trida")
        spojeni.execute("DELETE FROM cas_hodiny")
        spojeni.execute("DELETE FROM stav")

        spojeni.execute(
            "INSERT INTO stav (id, datum, datum_text, naimportovano) VALUES (1, ?, ?, ?)",
            (datum_iso, rozvrh.datum, dt.datetime.now().isoformat(timespec="seconds")))
        spojeni.executemany(
            "INSERT INTO cas_hodiny (poradi, cislo, od, do_) VALUES (?, ?, ?, ?)",
            [(i, c[0], c[1], c[2]) for i, c in enumerate(rozvrh.casy, start=1)])
        spojeni.executemany(
            "INSERT INTO trida (poradi, nazev) VALUES (?, ?)",
            [(i, t.trida) for i, t in enumerate(rozvrh.tridy, start=1)])
        spojeni.executemany(
            "INSERT INTO hodina (trida, od_hodiny, do_hodiny, od, do_, nazev, plny_nazev,"
            " ucitele, ucebna, zaci, akce) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(t.trida, h.od_hodiny, h.do_hodiny, h.od, h.do, h.nazev, h.plny_nazev,
              h.ucitele, h.ucebna, h.zaci, int(h.akce))
             for t in rozvrh.tridy for h in t.hodiny])


def nacti(spojeni: sqlite3.Connection) -> tuple[DenniRozvrh, str, dt.datetime] | None:
    """Vrátí ``(rozvrh, datum_iso, čas importu)``; None, když se ještě neimportovalo."""
    stav = spojeni.execute("SELECT * FROM stav WHERE id = 1").fetchone()
    if stav is None:
        return None

    rozvrh = DenniRozvrh(datum=stav["datum_text"])
    rozvrh.casy = [(r["cislo"], r["od"], r["do_"]) for r in
                   spojeni.execute("SELECT * FROM cas_hodiny ORDER BY poradi")]

    for t in spojeni.execute("SELECT nazev FROM trida ORDER BY poradi"):
        hodiny = [Hodina(od_hodiny=h["od_hodiny"], do_hodiny=h["do_hodiny"],
                         od=h["od"], do=h["do_"], nazev=h["nazev"],
                         plny_nazev=h["plny_nazev"], ucitele=h["ucitele"],
                         ucebna=h["ucebna"], zaci=h["zaci"], akce=bool(h["akce"]))
                  for h in spojeni.execute(
                      "SELECT * FROM hodina WHERE trida = ? ORDER BY od_hodiny, id",
                      (t["nazev"],))]
        rozvrh.tridy.append(RozvrhTridy(trida=t["nazev"], hodiny=hodiny))

    return rozvrh, stav["datum"], dt.datetime.fromisoformat(stav["naimportovano"])
