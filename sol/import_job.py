"""Importní úloha: ŠOL -> SQLite.

Jediné místo, které sahá na ŠOL. Volá ji jak CLI ``bin/import_sol.py`` (cron),
tak tlačítko na signage obrazovce, aby se obě cesty chovaly stejně.
"""

from __future__ import annotations

import sys

from .denni_rozvrh import datum_iso, parsuj_denni_rozvrh
from .uloziste import nacti, pripoj, uloz
from .web_klient import SolWebKlient


def importuj(tise: bool = False) -> int:
    """Naimportuje dnešní rozvrh. Vrací 0 při úspěchu, 1 při chybě.

    Při chybě se databáze nemění — signage tak dál běží na předchozích datech
    místo aby zhasla.
    """
    try:
        rozvrh = parsuj_denni_rozvrh(SolWebKlient().denni_podle_trid())
    except Exception as e:
        print(f"Import ze ŠOL selhal: {type(e).__name__}: {e}", file=sys.stderr)
        spojeni = pripoj()
        try:
            if nacti(spojeni):
                print("V databázi zůstává předchozí rozvrh.", file=sys.stderr)
        finally:
            spojeni.close()
        return 1

    spojeni = pripoj()
    try:
        uloz(spojeni, rozvrh, datum_iso(rozvrh))
    finally:
        spojeni.close()

    if not tise:
        print(f"Naimportováno: {rozvrh.datum} — {len(rozvrh.tridy)} tříd, "
              f"{rozvrh.pocet_hodin} položek.")
    return 0
