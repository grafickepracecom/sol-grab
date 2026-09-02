"""Klient neoficiálního REST API Školy OnLine (ŠOL).

ŠOL oficiální API nemá; tohle staví na rozhraní, které používá jejich mobilní
aplikace. Server naštěstí publikuje vlastní OpenAPI popis na
``/solapi/swagger/v1/swagger.json`` — to je nejspolehlivější zdroj pravdy,
spolehlivější než komunitní dokumentace (Libre-SkolaOnline/API-docs), která
popisuje jen žákovskou část.

Ověřeno proti účtu typu *učitel*; pod žákovským účtem část endpointů chybí.
Používá jen standardní knihovnu, takže projekt nemá žádné závislosti.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import KOREN, Nastaveni

CACHE_TOKENU = KOREN / ".token-cache.json"


class SolChyba(RuntimeError):
    pass


class SolClient:
    def __init__(self, nastaveni: Nastaveni | None = None) -> None:
        self.n = nastaveni or Nastaveni()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._plati_do: float = 0.0

    # ------------------------------------------------------------------ HTTP

    def _pozadavek(self, url: str, data: bytes | None = None,
                   hlavicky: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(url, data=data, headers=hlavicky or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as odpoved:
                telo = odpoved.read()
        except urllib.error.HTTPError as e:
            telo = e.read().decode("utf-8", "replace")
            raise SolChyba(f"HTTP {e.code} na {url}\n{telo[:500]}") from None
        except urllib.error.URLError as e:
            raise SolChyba(f"Nepodařilo se spojit se ŠOL ({url}): {e.reason}") from None
        return json.loads(telo) if telo else None

    # ------------------------------------------------------- přihlášení

    def _uloz_token(self, odpoved: dict[str, Any]) -> None:
        self._access_token = odpoved["access_token"]
        self._refresh_token = odpoved.get("refresh_token")
        # rezerva 60 s, ať nevyprší uprostřed série dotazů
        self._plati_do = time.time() + int(odpoved.get("expires_in", 3600)) - 60
        try:
            CACHE_TOKENU.write_text(json.dumps({
                "refresh_token": self._refresh_token,
                "access_token": self._access_token,
                "plati_do": self._plati_do,
            }), encoding="utf-8")
            CACHE_TOKENU.chmod(0o600)
        except OSError:
            pass  # cache je jen pohodlí, bez ní se prostě přihlásíme znovu

    def _token_endpoint(self, pole: dict[str, str]) -> dict[str, Any]:
        return self._pozadavek(
            f"{self.n.base_url}/api/connect/token",
            data=urllib.parse.urlencode(pole).encode(),
            hlavicky={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def prihlas(self) -> None:
        """Přihlásí se heslem (grant_type=password)."""
        self.n.zkontroluj()
        self._uloz_token(self._token_endpoint({
            "grant_type": "password",
            "username": self.n.username,
            "password": self.n.password,
            "client_id": self.n.client_id,
            "scope": "openid offline_access profile sol_api",
        }))

    def _zkus_cache(self) -> bool:
        """Zkusí navázat na dřívější běh — platným tokenem nebo refreshem."""
        if not CACHE_TOKENU.exists():
            return False
        try:
            c = json.loads(CACHE_TOKENU.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if c.get("access_token") and c.get("plati_do", 0) > time.time():
            self._access_token = c["access_token"]
            self._refresh_token = c.get("refresh_token")
            self._plati_do = c["plati_do"]
            return True
        if c.get("refresh_token"):
            try:
                self._uloz_token(self._token_endpoint({
                    "grant_type": "refresh_token",
                    "refresh_token": c["refresh_token"],
                    "client_id": self.n.client_id,
                }))
                return True
            except SolChyba:
                return False
        return False

    def _token(self) -> str:
        if self._access_token and time.time() < self._plati_do:
            return self._access_token
        if not self._zkus_cache():
            self.prihlas()
        assert self._access_token
        return self._access_token

    # ------------------------------------------------------------ dotazy

    def get(self, cesta: str, **parametry: Any) -> Any:
        """GET na API; None hodnoty parametrů se vynechají."""
        parametry = {k: v for k, v in parametry.items() if v is not None}
        url = f"{self.n.base_url}{cesta}"
        if parametry:
            url += "?" + urllib.parse.urlencode(parametry)
        try:
            return self._pozadavek(url, hlavicky={"Authorization": f"Bearer {self._token()}"})
        except SolChyba as e:
            if "HTTP 401" not in str(e):
                raise
            self.prihlas()  # token mohl padnout dřív, než jsme čekali
            return self._pozadavek(url, hlavicky={"Authorization": f"Bearer {self._token()}"})

    # ----------------------------------------------------- konkrétní volání

    def uzivatel(self) -> dict[str, Any]:
        """Profil přihlášeného uživatele; obsahuje i ``schoolYearId``."""
        return self.get("/api/v1/user")

    def aktualni_skolni_rok(self) -> str:
        return self.uzivatel()["schoolYearId"]

    def ciselniky_rozvrhu(self, skolni_rok: str | None = None) -> dict[str, Any]:
        """Pololetí, rozsah školního roku, zda se zobrazuje víkend."""
        return self.get("/api/v1/timeTable/codeLists", schoolYearId=skolni_rok)

    def tridy(self, skolni_rok: str) -> list[dict[str, Any]]:
        """Seznam tříd školy.

        Jde přes modul třídní knihy (``api_chovani_zam``) — samostatný číselník
        tříd API nenabízí a ``/if/2/common/classes`` tímhle tokenem neprojde.
        """
        odpoved = self.get("/api/v1/teacher/behaviors/classes", SchoolYearId=skolni_rok)
        return sorted(odpoved.get("classes", []), key=lambda t: t.get("order", 0))

    def rozvrh(self, skolni_rok: str, datum_od: str, datum_do: str,
               trida: str | None = None) -> dict[str, Any]:
        """Rozvrh za období. Bez ``trida`` vrací rozvrh přihlášeného uživatele.

        Data jsou ``RRRR-MM-DD``. Vrací ``{"days": [...], "lessons": [...]}``,
        kde ``lessons`` je číselník časů vyučovacích hodin.
        """
        return self.get(
            "/api/v1/timeTable",
            SchoolYearId=skolni_rok, DateFrom=datum_od, DateTo=datum_do, ClassId=trida,
        )
