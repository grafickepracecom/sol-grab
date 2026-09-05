"""Přihlášení do **webové aplikace** ŠOL a stažení stránek formulářů.

Proč ne REST API: ``/solapi/api/v1/timeTable`` vrací podle vlastní dokumentace
„rozvrh pro přihlášeného uživatele“. Účet, který sám neučí, tudy nedostane nic —
ověřeno i s ``ClassId`` a s ``StudentId`` skutečného žáka, na celé pololetí.
Webová aplikace přitom stejnému účtu rozvrh všech tříd ukazuje, takže se bere
odtud. Podrobnosti v README.

Přihlášení je prostý POST na ``/SOL/Prihlaseni.aspx`` (bez captchy a bez
předchozího VIEWSTATE), relace pak drží cookie ``.ASPXAUTH``.
"""

from __future__ import annotations

import gzip
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from .config import Nastaveni


class SolWebChyba(RuntimeError):
    pass


class SolWebKlient:
    PRIHLASENI = "/SOL/Prihlaseni.aspx"
    DENNI_PODLE_TRID = "/SOL/App/Rozvrh/KRO029_VypisTridDenni.aspx"
    ROZVRH_TRIDY = "/SOL/App/Rozvrh/KRO003_VypisTridy.aspx"

    def __init__(self, nastaveni: Nastaveni | None = None) -> None:
        self.n = nastaveni or Nastaveni()
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies))
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (sol-grab)"),
            ("Accept-Language", "cs"),
        ]
        self._prihlasen = False

    def _nacti(self, url: str, data: bytes | None = None) -> str:
        hlavicky = {"Content-Type": "application/x-www-form-urlencoded"} if data else {}
        try:
            with self.opener.open(
                    urllib.request.Request(url, data=data, headers=hlavicky), timeout=45) as o:
                telo = o.read()
                if o.headers.get("Content-Encoding") == "gzip":
                    telo = gzip.decompress(telo)
        except urllib.error.HTTPError as e:
            raise SolWebChyba(f"HTTP {e.code} na {url}") from None
        except urllib.error.URLError as e:
            raise SolWebChyba(f"Nepodařilo se spojit se ŠOL ({url}): {e.reason}") from None
        return telo.decode("utf-8", "replace")

    def prihlas(self) -> None:
        self.n.zkontroluj()
        self._nacti(
            self.n.web_url + self.PRIHLASENI,
            urllib.parse.urlencode({
                "JmenoUzivatele": self.n.username,
                "HesloUzivatele": self.n.password,
                "btnLogin": "Přihlásit",
            }).encode(),
        )
        if not any(c.name == ".ASPXAUTH" for c in self.cookies):
            raise SolWebChyba(
                "Přihlášení do webové aplikace ŠOL selhalo — nevrátila se cookie .ASPXAUTH. "
                "Zkontrolujte SOL_USERNAME a SOL_PASSWORD."
            )
        self._prihlasen = True

    def stranka(self, cesta: str) -> str:
        """Vrátí HTML formuláře ŠOL; podle potřeby se nejdřív přihlásí."""
        if not self._prihlasen:
            self.prihlas()
        html = self._nacti(self.n.web_url + cesta)
        if "Prihlaseni.aspx" in html[:2000] and "JmenoUzivatele" in html:
            raise SolWebChyba(f"Relace vypršela při načítání {cesta}.")
        return html

    def post(self, cesta: str, data: dict) -> str:
        """POST formuláře ŠOL (ASP.NET postback); vrátí výsledné HTML."""
        if not self._prihlasen:
            self.prihlas()
        telo = urllib.parse.urlencode(data, encoding="utf-8").encode()
        html = self._nacti(self.n.web_url + cesta, data=telo)
        if "Prihlaseni.aspx" in html[:2000] and "JmenoUzivatele" in html:
            raise SolWebChyba(f"Relace vypršela při POST na {cesta}.")
        return html

    def denni_podle_trid(self) -> str:
        """Formulář KRO029 „Denní podle tříd“ — rozvrh všech tříd na **dnešek**.

        Datum se vybírá Infragistics kalendářem, jehož postback se zatím
        nepodařilo napodobit, takže jiný než dnešní den tudy nejde (viz README).
        """
        return self.stranka(self.DENNI_PODLE_TRID)
