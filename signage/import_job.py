"""Importní úloha: ŠOL -> SQLite.

Jediné místo, které sahá na ŠOL. Volá ji jak CLI ``bin/import_sol.py`` (cron),
tak tlačítko na signage obrazovce, aby se obě cesty chovaly stejně.

Zdrojem je KRO003 v měsíčním režimu (viz ``mesicni_rozvrh``): jeden dotaz na
třídu vrátí celý aktuální měsíc, takže má signage vždy dnešek i dny dopředu.
"""

from __future__ import annotations

import datetime as dt
import sys

from sol.mesicni_rozvrh import stahni_mesicni_rozvrh
from sol.web_klient import SolWebKlient

from .config import Nastaveni
from .uloziste import lidsky_datum, nacti, pripoj, uloz_mesic


def importuj(tise: bool = False, nastaveni: Nastaveni | None = None) -> int:
    """Naimportuje měsíční rozvrh všech tříd. Vrací 0 při úspěchu, 1 při chybě.

    Při chybě se databáze nemění — signage běží dál na předchozích datech.
    """
    n = nastaveni or Nastaveni()
    try:
        casy, tridy, dny, datum_od, datum_do = stahni_mesicni_rozvrh(SolWebKlient(n.sol))
    except Exception as e:
        print(f"Import ze ŠOL selhal: {type(e).__name__}: {e}", file=sys.stderr)
        spojeni = pripoj(n.databaze)
        try:
            if nacti(spojeni, dt.date.today().isoformat()):
                print("V databázi zůstává předchozí rozvrh.", file=sys.stderr)
        finally:
            spojeni.close()
        return 1

    spojeni = pripoj(n.databaze)
    try:
        uloz_mesic(spojeni, casy, tridy, dny, datum_od, datum_do)
    finally:
        spojeni.close()

    if not tise:
        pocet = sum(len(h) for d in dny.values() for h in d.values())
        print(f"Naimportováno: {lidsky_datum(datum_od)} – {lidsky_datum(datum_do)}, "
              f"{len(tridy)} tříd, {len(dny)} dní, {pocet} položek.")
    return 0
