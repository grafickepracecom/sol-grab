#!/usr/bin/env python3
"""Ladicí nástroj — syrové odpovědi ŠOL na stdout.

    bin/dump.py user
    bin/dump.py tridy
    bin/dump.py rozvrh 2026-09-02 [ID_TRIDY]
    bin/dump.py ciselniky
    bin/dump.py get /api/v1/user            # libovolný endpoint
    bin/dump.py endpointy                   # výpis endpointů ze swaggeru serveru

Webová aplikace (odtud se bere rozvrh tříd, viz README):

    bin/dump.py denni                       # rozparsovaný denní rozvrh všech tříd
    bin/dump.py html                        # syrové HTML formuláře KRO029
    bin/dump.py html /SOL/App/Rozvrh/KSU016_SuplovaniVypis.aspx
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sol.client import SolClient  # noqa: E402
from sol.denni_rozvrh import dily_text, parsuj_denni_rozvrh  # noqa: E402
from sol.web_klient import SolWebKlient  # noqa: E402


def vypis(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    prikaz, *zbytek = sys.argv[1:]

    if prikaz == "denni":
        r = parsuj_denni_rozvrh(SolWebKlient().denni_podle_trid())
        print(f"Datum: {r.datum}   ({len(r.tridy)} tříd, {r.pocet_hodin} položek)")
        for t in r.tridy:
            print(f"\n== {t.trida} ==")
            for h in t.hodiny:
                rozsah = (str(h.od_hodiny) if h.od_hodiny == h.do_hodiny
                          else f"{h.od_hodiny}-{h.do_hodiny}")
                znacka = "AKCE" if h.akce else "    "
                print(f"  [{rozsah:>3}] {h.od:>5}-{h.do:<5} {znacka} {h.popis[:38]:40} "
                      f"{dily_text(h.ucitele)[:30]:32} {dily_text(h.ucebna)[:8]:8} {dily_text(h.zaci)}")
        return

    if prikaz == "html":
        w = SolWebKlient()
        print(w.stranka(zbytek[0]) if zbytek else w.denni_podle_trid())
        return

    k = SolClient()

    if prikaz == "endpointy":
        with urllib.request.urlopen(f"{k.n.base_url}/swagger/v1/swagger.json", timeout=30) as f:
            s = json.load(f)
        for cesta, operace in sorted(s["paths"].items()):
            for metoda, o in operace.items():
                par = ",".join(p["name"] for p in o.get("parameters", []) if p.get("name") != "app-lang")
                print(f"{metoda.upper():6} {cesta:60} [{par}]")
        return

    if prikaz == "user":
        vypis(k.uzivatel())
    elif prikaz == "ciselniky":
        vypis(k.ciselniky_rozvrhu(k.aktualni_skolni_rok()))
    elif prikaz == "tridy":
        vypis(k.tridy(k.aktualni_skolni_rok()))
    elif prikaz == "rozvrh":
        if not zbytek:
            raise SystemExit("Chybí datum, např.: bin/dump.py rozvrh 2026-09-02")
        datum = zbytek[0]
        trida = zbytek[1] if len(zbytek) > 1 else None
        vypis(k.rozvrh(k.aktualni_skolni_rok(), datum, datum, trida))
    elif prikaz == "get":
        if not zbytek:
            raise SystemExit("Chybí cesta, např.: bin/dump.py get /api/v1/user")
        vypis(k.get(zbytek[0]))
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
