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
    "SOL_CLIENT_ID": "test_client",
    "SOL_WEB_PORT": "8081",
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
        self.client_id = ber("SOL_CLIENT_ID")
        self.web_port = int(ber("SOL_WEB_PORT") or 8081)

    def zkontroluj(self) -> None:
        if not self.username or not self.password:
            raise SystemExit(
                "Chybí přihlašovací údaje do ŠOL.\n"
                f"Vytvořte {KOREN / '.env'} podle .env.example "
                "nebo nastavte SOL_USERNAME a SOL_PASSWORD v prostředí."
            )
