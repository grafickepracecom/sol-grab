#!/usr/bin/env python3
"""Import rozvrhu ze Školy OnLine do SQLite (pouští se z cronu).

    bin/import_sol.py            # naimportuje a vypíše souhrn
    bin/import_sol.py --tise     # jen chyby, pro cron

Návratový kód 0 = úspěch, 1 = import selhal. Při selhání zůstává v databázi
předchozí rozvrh, takže signage běží dál na starších datech.
Nastavení cronu viz bin/crontab.priklad.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signage.import_job import importuj  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tise", action="store_true", help="vypisovat jen chyby (pro cron)")
    argumenty = p.parse_args()
    os.umask(0o027)   # databáze ani token ať nejsou čitelné pro kohokoli
    raise SystemExit(importuj(argumenty.tise))
