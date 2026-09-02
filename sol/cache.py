"""Cache posledního úspěšně načteného rozvrhu.

Signage běží celý den a stránku si tahá opakovaně. Cache plní dvě role:

* **šetří ŠOL** — během ``ttl`` se nechodí na server znovu,
* **přežije výpadek** — když ŠOL nebo přihlášení selže, vrátí se poslední
  známá data označená jako zastaralá, místo aby na obrazovce byla chyba.

Ukládá se rozparsovaný rozvrh (JSON), ne HTML — kdyby se rozbil parser,
zastaralá data se pak dají zobrazit i tak.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .config import KOREN
from .denni_rozvrh import DenniRozvrh, Hodina, RozvrhTridy

SOUBOR = KOREN / ".rozvrh-cache.json"


def uloz(rozvrh: DenniRozvrh, soubor: Path | None = None) -> None:
    soubor = soubor or SOUBOR
    try:
        soubor.write_text(json.dumps(
            {"ulozeno": time.time(), "rozvrh": asdict(rozvrh)},
            ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # cache je jen pojistka, její selhání nesmí shodit stránku


def nacti(soubor: Path | None = None) -> tuple[DenniRozvrh, float] | None:
    """Vrátí ``(rozvrh, stáří v sekundách)``, nebo None když cache není/je vadná."""
    soubor = soubor or SOUBOR
    try:
        data = json.loads(soubor.read_text(encoding="utf-8"))
        r = data["rozvrh"]
        rozvrh = DenniRozvrh(
            datum=r.get("datum", ""),
            casy=[tuple(c) for c in r.get("casy", [])],
            tridy=[RozvrhTridy(trida=t["trida"],
                               hodiny=[Hodina(**h) for h in t.get("hodiny", [])])
                   for t in r.get("tridy", [])],
        )
        return rozvrh, max(0.0, time.time() - float(data["ulozeno"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
