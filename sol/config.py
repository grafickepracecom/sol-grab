"""Načtení konfigurace z .env / proměnných prostředí.

Přístupové údaje do ŠOL se drží mimo repozitář — v souboru .env vedle tohoto
projektu (viz .env.example), který je v .gitignore. Proměnná prostředí má
přednost před hodnotou z .env, takže se dá běh přebít i bez editace souboru.
"""

from __future__ import annotations

import os
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent

VYCHOZI = {
    "SOL_BASE_URL": "https://aplikace.skolaonline.cz/solapi",
    "SOL_WEB_URL": "https://aplikace.skolaonline.cz",
    "SOL_CLIENT_ID": "test_client",
    "SOL_WEB_PORT": "8081",
    "SOL_OKNO_ZPET": "60",
    "SOL_OKNO_VPRED": "120",
    "SOL_OBNOVA": "60",
    "SOL_VAROVANI_MIN": "60",
    "SOL_PREKRYV_HODIN": "24",
    "SOL_VYSTUP": "/var/www/signage-data/index.html",
}


def nacti_env(cesta: Path | None = None) -> dict[str, str]:
    """Přečte jednoduchý .env (KLIC=hodnota, # komentář) do slovníku."""
    cesta = cesta or KOREN / ".env"
    hodnoty: dict[str, str] = {}
    if not cesta.exists():
        return hodnoty
    for radek in cesta.read_text(encoding="utf-8").splitlines():
        radek = radek.strip()
        if not radek or radek.startswith("#") or "=" not in radek:
            continue
        klic, _, hodnota = radek.partition("=")
        hodnoty[klic.strip()] = hodnota.strip().strip('"').strip("'")
    return hodnoty


class Nastaveni:
    def __init__(self, cesta_env: Path | None = None) -> None:
        soubor = nacti_env(cesta_env)

        def ber(klic: str) -> str:
            return os.environ.get(klic) or soubor.get(klic) or VYCHOZI.get(klic, "")

        self.username = ber("SOL_USERNAME")
        self.password = ber("SOL_PASSWORD")
        self.base_url = ber("SOL_BASE_URL").rstrip("/")
        self.web_url = ber("SOL_WEB_URL").rstrip("/")
        self.client_id = ber("SOL_CLIENT_ID")
        self.web_port = int(ber("SOL_WEB_PORT") or 8081)
        # časové okno signage obrazovky v minutách (zpět / vpřed od teď)
        self.okno_zpet = int(ber("SOL_OKNO_ZPET") or 60)
        self.okno_vpred = int(ber("SOL_OKNO_VPRED") or 120)
        # jak často se obrazovka sama překreslí (s)
        self.obnova = int(ber("SOL_OBNOVA") or 60)
        # stáří poslední synchronizace (min), nad kterým hlavička zčervená
        self.varovani_min = int(ber("SOL_VAROVANI_MIN") or 60)
        # stáří (h), nad kterým se přes data položí překryv „není aktuální“
        self.prekryv_hodin = int(ber("SOL_PREKRYV_HODIN") or 24)
        # kam se zapisuje staticky generovaná obrazovka pro signage
        self.vystup = Path(ber("SOL_VYSTUP"))

    def zkontroluj(self) -> None:
        if not self.username or not self.password:
            raise SystemExit(
                "Chybí přihlašovací údaje do ŠOL.\n"
                f"Vytvořte {KOREN / '.env'} podle .env.example "
                "nebo nastavte SOL_USERNAME a SOL_PASSWORD v prostředí."
            )
