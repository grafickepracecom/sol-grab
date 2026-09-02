"""Minimalistický DOM nad standardním ``html.parser``.

ŠOL vykresluje rozvrh jako ASP.NET tabulku s **vnořenými tabulkami** a atributy,
které samy obsahují HTML (tooltipy). Regulárními výrazy se to parsovat nedá —
proto tenhle malý strom. Žádná externí závislost (BeautifulSoup) není potřeba.
"""

from __future__ import annotations

from html.parser import HTMLParser

# značky, které se nezavírají a nesmí se tedy dostat na zásobník
PRAZDNE = {"br", "img", "input", "hr", "meta", "link", "col", "area", "base", "source"}


class Uzel:
    def __init__(self, tag: str = "", attrs=None) -> None:
        self.tag = tag
        self.attrs: dict[str, str] = {k: (v or "") for k, v in (attrs or [])}
        self.deti: list = []

    @property
    def tridy(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def primi(self, *tagy: str) -> list["Uzel"]:
        """Přímí potomci daných značek — na rozdíl od ``najdi`` neleze hlouběji.

        Klíčové pro vnořené tabulky: řádky mřížky se nesmí míchat s řádky
        tabulek uvnitř buněk.
        """
        return [d for d in self.deti if isinstance(d, Uzel) and d.tag in tagy]

    def najdi(self, tag: str | None = None, trida: str | None = None,
              id: str | None = None) -> list["Uzel"]:
        """Rekurzivně najde potomky odpovídající značce / CSS třídě / id."""
        nalez = []
        for d in self.deti:
            if not isinstance(d, Uzel):
                continue
            if ((tag is None or d.tag == tag)
                    and (trida is None or trida in d.tridy)
                    and (id is None or d.attrs.get("id") == id)):
                nalez.append(d)
            nalez += d.najdi(tag, trida, id)
        return nalez

    def txt(self) -> str:
        """Veškerý text potomků, zploštělý do jednoho řádku."""
        return " ".join(" ".join(self._casti()).split())

    def radky(self) -> list[str]:
        """Text rozdělený podle ``<br>`` — buňka rozvrhu má takhle
        pod sebou třídu, učitele a učebnu."""
        out, akt = [], []
        for c in self._casti(br=True):
            if c == "\n":
                out.append(" ".join(" ".join(akt).split()))
                akt = []
            else:
                akt.append(c)
        out.append(" ".join(" ".join(akt).split()))
        return [r for r in out if r]

    def _casti(self, br: bool = False) -> list[str]:
        casti = []
        for d in self.deti:
            if isinstance(d, Uzel):
                if br and d.tag == "br":
                    casti.append("\n")
                casti += d._casti(br)
            else:
                casti.append(d)
        return casti


class _Stavitel(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.koren = Uzel("#root")
        self.zasobnik = [self.koren]

    def handle_starttag(self, tag, attrs):
        u = Uzel(tag, attrs)
        self.zasobnik[-1].deti.append(u)
        if tag not in PRAZDNE:
            self.zasobnik.append(u)

    def handle_startendtag(self, tag, attrs):
        self.zasobnik[-1].deti.append(Uzel(tag, attrs))

    def handle_endtag(self, tag):
        # zavři až k nejbližšímu odpovídajícímu otevření; nepárové značky
        # v cizím HTML tak strom nerozhodí
        for i in range(len(self.zasobnik) - 1, 0, -1):
            if self.zasobnik[i].tag == tag:
                del self.zasobnik[i:]
                return

    def handle_data(self, data):
        if data.strip():
            self.zasobnik[-1].deti.append(data)


def parsuj(html: str) -> Uzel:
    stavitel = _Stavitel()
    stavitel.feed(html)
    return stavitel.koren
