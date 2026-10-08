"""Parser formuláře KRO029 „Denní podle tříd“ — rozvrh všech tříd na jeden den.

Mřížka je ``<table id="CCADynamicCalendarTable">``: řádek = třída, sloupec =
vyučovací hodina. Dvě věci ji komplikují:

* **colspan** — akce nebo dvouhodinovka zabírá víc sloupců,
* **rowspan** — třída s paralelními skupinami má víc řádků a název třídy je
  vypsaný jen u prvního.

Proto se buňky skládají do obsazovací matice, ne po pořadí.

Každá buňka nese v atributu ``onmouseover`` volání
``onMouseOverTooltip('<nadpis>', 'Učitel:~…~Třída:~…~Učebna:~…')`` — odtud se
berou přesné údaje včetně plného názvu předmětu; viditelné ``<span>``\\y jsou
jen zkratky.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dom import Uzel, parsuj

# buňka běžné vyučovací hodiny vs. školní akce (výlet, kurz, …)
TRIDA_HODINY = "DctInnerTableType10DataTD"
TRIDA_AKCE = "KuvSkolniAkceHodina"

_TOOLTIP = re.compile(r"onMouseOverTooltip\('(.*?)'\s*,\s*'(.*?)'\)", re.S)
_DATUM = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")

# tooltip ze ŠOL může u některých údajů (chybějící učitel/učebna) obalit část
# textu do <span class=...>. HTML ze ŠOL na výstup nikdy nepustíme; zachytíme
# jen název class a použijeme ho 1:1 s prefixem "sol_" kolem zaescapovaného
# textu, ostatní značky zahodíme.
_SPAN = re.compile(r'<span\s+class=["\']?([\w-]+)["\']?\s*>(.*?)</span>', re.I | re.S)
_TAG = re.compile(r'<[^>]+>')


def _ocisti(text: str) -> str:
    """Zahodí zbytkové HTML značky a srovná bílé znaky.

    Hraniční mezeru zachová — oddělovače mezi jmény (", ") jsou v okolních
    dílcích a nesmí se ztratit při skládání zpět."""
    bez = _TAG.sub("", text)
    if not bez.strip():
        return ""
    vlevo = " " if bez[:1].isspace() else ""
    vpravo = " " if bez[-1:].isspace() else ""
    return vlevo + " ".join(bez.split()) + vpravo


def rozdel_dily(hodnota: str) -> list[dict]:
    """Rozloží hodnotu z tooltipu na dílky ``{"t": text, "c": třída}``.

    Text uvnitř ``<span class=X>`` dostane třídu ``"sol_X"`` (prefix, aby se
    nepletl s našimi vlastními třídami); zbytek má ``"c": ""``. Oddělovače mezi
    jmény (", ") zůstávají v okolních dílcích, takže se skládají zpět bez ztráty.
    """
    dily: list[dict] = []
    i = 0
    for m in _SPAN.finditer(hodnota):
        pred = _ocisti(hodnota[i:m.start()])
        if pred:
            dily.append({"t": pred, "c": ""})
        vnitrek = _ocisti(m.group(2))
        if vnitrek:
            dily.append({"t": vnitrek, "c": "sol_" + m.group(1)})
        i = m.end()
    zbytek = _ocisti(hodnota[i:])
    if zbytek:
        dily.append({"t": zbytek, "c": ""})
    return dily


def dily_text(dily: list[dict]) -> str:
    """Prostý text dílků (pro tituly, konzoli, plain výpisy)."""
    return "".join(d["t"] for d in dily)
_CAS = re.compile(r"^\d{1,2}:\d{2}$")


class StrukturaZmenena(RuntimeError):
    """HTML formuláře KRO029 nevypadá, jak parser čeká.

    Scrapujeme cizí aplikaci, takže tohle je očekávatelný způsob rozbití —
    chyba proto říká konkrétně, co chybí, ať se to dá rychle dohledat.
    """


@dataclass
class Hodina:
    od_hodiny: int              # pořadí první vyučovací hodiny (1..9)
    do_hodiny: int              # pořadí poslední (u dvouhodinovky vyšší)
    od: str = ""                # čas začátku, "8:30"
    do: str = ""                # čas konce
    nazev: str = ""             # zkratka, jak ji ŠOL zobrazuje ("C (AJ)")
    plny_nazev: str = ""        # z tooltipu ("Cizí jazyky (angličtina)")
    # učitelé/učebny/žáci jako dílky {t, c}; c="sol_AbsZdroj" = absentující zdroj
    ucitele: list = field(default_factory=list)
    ucebna: list = field(default_factory=list)
    zaci: list = field(default_factory=list)
    akce: bool = False          # školní akce, ne běžná hodina

    @property
    def popis(self) -> str:
        return self.plny_nazev or self.nazev


@dataclass
class RozvrhTridy:
    trida: str
    hodiny: list[Hodina] = field(default_factory=list)


@dataclass
class DenniRozvrh:
    datum: str = ""                                     # jak ho vypsala ŠOL
    casy: list[tuple[str, str, str]] = field(default_factory=list)  # (číslo, od, do)
    tridy: list[RozvrhTridy] = field(default_factory=list)

    @property
    def pocet_hodin(self) -> int:
        return sum(len(t.hodiny) for t in self.tridy)


def _tooltip(bunka: Uzel) -> tuple[str, dict[str, str]]:
    """Rozebere ``onMouseOverTooltip('nadpis','Klíč:~hodnota~Klíč:~hodnota')``."""
    m = _TOOLTIP.search(bunka.attrs.get("onmouseover", ""))
    if not m:
        return "", {}
    nadpis = m.group(1).strip()
    casti = [c.strip() for c in m.group(2).split("~")]
    udaje: dict[str, str] = {}
    klic = None
    for c in casti:
        if c.endswith(":"):
            klic = c[:-1]
        elif klic is not None:
            udaje[klic] = c
            klic = None
    return nadpis, udaje


def _plny_nazev(nadpis: str, zkratka: str) -> str:
    """Z „C (AJ) (Cizí jazyky (angličtina))“ vybere text v poslední závorce."""
    zbytek = nadpis[len(zkratka):].strip() if nadpis.startswith(zkratka) else nadpis
    if zbytek.startswith("(") and zbytek.endswith(")"):
        return zbytek[1:-1].strip()
    return zbytek or nadpis


def _hodina_z_bunky(vnitrni: Uzel, od: int, do: int) -> Hodina:
    nadpis, udaje = _tooltip(vnitrni)
    zkratka = ""
    for s in vnitrni.najdi("span"):
        if "KuvBunkaRozvrhNadpis" in s.tridy:
            zkratka = s.txt()
            break
    return Hodina(
        od_hodiny=od,
        do_hodiny=do,
        nazev=zkratka,
        plny_nazev=_plny_nazev(nadpis, zkratka) if nadpis else "",
        ucitele=rozdel_dily(udaje.get("Učitel", "")),
        ucebna=rozdel_dily(udaje.get("Učebna", "")),
        zaci=rozdel_dily(udaje.get("Žáci", "")),
        akce=TRIDA_AKCE in vnitrni.tridy,
    )


def _mrizka(tabulka: Uzel) -> list[list[Uzel | None]]:
    """Rozprostře buňky do matice a respektuje colspan i rowspan.

    Na pozicích, které zabírá roztažená buňka, zůstává ``None`` — díky tomu
    pořadí sloupců odpovídá vyučovacím hodinám i u tříd s víc řádky.
    """
    rodic = tabulka.primi("tbody")[0] if tabulka.primi("tbody") else tabulka
    radky = rodic.primi("tr")
    matice: list[list[Uzel | None]] = [[] for _ in radky]
    obsazeno: dict[tuple[int, int], bool] = {}

    for r, tr in enumerate(radky):
        sloupec = 0
        for bunka in tr.primi("td", "th"):
            while obsazeno.get((r, sloupec)):
                sloupec += 1
                matice[r].append(None)
            try:
                colspan = max(1, int(bunka.attrs.get("colspan", "1")))
                rowspan = max(1, int(bunka.attrs.get("rowspan", "1")))
            except ValueError:
                colspan = rowspan = 1
            matice[r].append(bunka)
            for dr in range(rowspan):
                for dc in range(colspan):
                    if (dr, dc) != (0, 0):
                        obsazeno[(r + dr, sloupec + dc)] = True
            # držíme šířku řádku, aby index sloupce = pořadí hodiny
            matice[r] += [None] * (colspan - 1)
            sloupec += colspan
    return matice


def parsuj_denni_rozvrh(html: str) -> DenniRozvrh:
    koren = parsuj(html)

    vysledek = DenniRozvrh()
    for span in koren.najdi("span"):
        if span.attrs.get("id") == "lDatum":
            vysledek.datum = span.txt()
            break

    tabulky = koren.najdi("table", id="CCADynamicCalendarTable")
    if not tabulky:
        raise StrukturaZmenena(
            "Ve stránce KRO029 není mřížka rozvrhu (table#CCADynamicCalendarTable). "
            "Buď se změnilo HTML ŠOL, nebo se nepodařilo přihlášení a přišla "
            "přihlašovací stránka.")
    matice = _mrizka(tabulky[0])
    if not matice:
        raise StrukturaZmenena("Mřížka rozvrhu (CCADynamicCalendarTable) nemá žádné řádky.")

    # hlavička: první sloupec je popisek tříd, dál jdou vyučovací hodiny
    for bunka in matice[0][1:]:
        if bunka is None:
            continue
        radky = [td.txt() for td in bunka.najdi("td")]
        cislo = radky[0] if radky else ""
        cas = radky[1] if len(radky) > 1 else ""
        od, _, do = (c.strip() for c in cas.partition("-"))
        vysledek.casy.append((cislo, od, do))

    if not vysledek.casy:
        raise StrukturaZmenena(
            "V hlavičce mřížky nejsou žádné vyučovací hodiny — čekaly se buňky "
            "s KuvHeaderNadpis (číslo) a KuvHeaderText (čas).")
    spatne = [c for c in vysledek.casy if not (_CAS.match(c[1]) and _CAS.match(c[2]))]
    if spatne:
        raise StrukturaZmenena(
            f"Časy vyučovacích hodin nejdou přečíst, čekal se tvar 'HH:MM - HH:MM': {spatne[:3]}")

    aktualni: RozvrhTridy | None = None
    for radek in matice[1:]:
        if not radek:
            continue
        zahlavi = radek[0]
        if zahlavi is not None and zahlavi.txt():
            aktualni = RozvrhTridy(trida=zahlavi.txt())
            vysledek.tridy.append(aktualni)
        if aktualni is None:
            continue
        for i, bunka in enumerate(radek[1:], start=1):
            if bunka is None:
                continue
            for vnitrni in bunka.najdi("td"):
                if not (vnitrni.tridy & {TRIDA_HODINY, TRIDA_AKCE}):
                    continue
                sirka = max(1, int(bunka.attrs.get("colspan", "1") or 1))
                h = _hodina_z_bunky(vnitrni, i, i + sirka - 1)
                if h.od_hodiny - 1 < len(vysledek.casy):
                    h.od = vysledek.casy[h.od_hodiny - 1][1]
                if h.do_hodiny - 1 < len(vysledek.casy):
                    h.do = vysledek.casy[h.do_hodiny - 1][2]
                aktualni.hodiny.append(h)

    if not vysledek.tridy:
        raise StrukturaZmenena(
            "V mřížce se nenašla žádná třída — čekal se <th> s názvem třídy "
            "na začátku každého řádku.")

    for t in vysledek.tridy:
        t.hodiny.sort(key=lambda h: h.od_hodiny)
    return vysledek


def datum_iso(rozvrh: DenniRozvrh) -> str:
    """„2. 9. 2026“ -> „2026-09-02“; prázdný řetězec, když se to nepovede."""
    m = _DATUM.search(rozvrh.datum or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""
