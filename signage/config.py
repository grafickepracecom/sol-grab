"""Konfigurace **aplikace** signage.

Drží nastavení zobrazení a běhu (port, časové okno, prahy stáří, výstupní
soubor, cesta k databázi) a umí z téhož zdroje sestavit **knihovní** nastavení
připojení k ŠOL (``sol.config.Nastaveni``). Přístup k ŠOL je tak na jednom
místě — aplikace předává knihovně připojení, knihovna o aplikaci nic neví.

Hodnoty se čtou z ``.env`` v kořeni projektu a z prostředí (prostředí má přednost).
"""

from __future__ import annotations

import os
from pathlib import Path

from sol.config import Nastaveni as SolNastaveni

KOREN = Path(__file__).resolve().parent.parent

VYCHOZI = {
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
        self._soubor = nacti_env(cesta_env)

        def ber(klic: str) -> str:
            return os.environ.get(klic) or self._soubor.get(klic) or VYCHOZI.get(klic, "")

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
        # databáze s naimportovaným rozvrhem
        self.databaze = Path(ber("SOL_DB") or (KOREN / "rozvrh.sqlite"))

    @property
    def sol(self) -> SolNastaveni:
        """Knihovní nastavení připojení k ŠOL ze stejného zdroje.

        Cache tokenu drží aplikace v kořeni projektu, pokud ji prostředí
        neurčí jinak.
        """
        n = SolNastaveni.z_env({**self._soubor, **os.environ})
        if n.cache_tokenu is None:
            n.cache_tokenu = KOREN / ".token-cache.json"
        return n
