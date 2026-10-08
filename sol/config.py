"""Konfigurace **připojení k ŠOL** pro knihovnu sol.

Knihovna nezná aplikaci ani rozložení projektu — drží jen to, co potřebuje
k přihlášení a spojení se ŠOL. Hodnoty si buď předá volající explicitně
(``Nastaveni(...)``), nebo se načtou z prostředí (``Nastaveni.z_env()``).
Čtení souboru ``.env`` a cesty v projektu jsou záležitost aplikace.
"""

from __future__ import annotations

import os
from pathlib import Path

VYCHOZI_BASE_URL = "https://aplikace.skolaonline.cz/solapi"
VYCHOZI_WEB_URL = "https://aplikace.skolaonline.cz"
VYCHOZI_CLIENT_ID = "test_client"


class Nastaveni:
    """Přístup k ŠOL: přihlašovací údaje, adresy, volitelná cache tokenu."""

    def __init__(self, username: str, password: str,
                 base_url: str = VYCHOZI_BASE_URL,
                 web_url: str = VYCHOZI_WEB_URL,
                 client_id: str = VYCHOZI_CLIENT_ID,
                 cache_tokenu: Path | str | None = None) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.web_url = web_url.rstrip("/")
        self.client_id = client_id
        # kam si REST klient ukládá token mezi běhy; None = necachovat
        self.cache_tokenu = Path(cache_tokenu) if cache_tokenu else None

    @classmethod
    def z_env(cls, env: dict[str, str] | None = None) -> "Nastaveni":
        """Sestaví nastavení z prostředí (nebo z předaného slovníku).

        Klíče: ``SOL_USERNAME``, ``SOL_PASSWORD``, volitelně ``SOL_BASE_URL``,
        ``SOL_WEB_URL``, ``SOL_CLIENT_ID``, ``SOL_CACHE_TOKENU``.
        """
        g = (env if env is not None else os.environ).get
        return cls(
            username=g("SOL_USERNAME", "") or "",
            password=g("SOL_PASSWORD", "") or "",
            base_url=g("SOL_BASE_URL") or VYCHOZI_BASE_URL,
            web_url=g("SOL_WEB_URL") or VYCHOZI_WEB_URL,
            client_id=g("SOL_CLIENT_ID") or VYCHOZI_CLIENT_ID,
            cache_tokenu=g("SOL_CACHE_TOKENU") or None,
        )

    def zkontroluj(self) -> None:
        if not self.username or not self.password:
            raise SystemExit(
                "Chybí přihlašovací údaje do ŠOL — nastavte SOL_USERNAME a SOL_PASSWORD "
                "(v prostředí nebo v .env aplikace)."
            )
