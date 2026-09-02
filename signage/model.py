"""Sestavení pohledu pro signage obrazovku.

Obrazovka vypadá jako televizní program: řádek = třída, vodorovná osa = čas.
Tenhle modul z naimportovaného rozvrhu spočítá, kde který blok na ose leží;
vykreslením se zabývá ``signage.render``.

Dvě věci, které to řeší:

* **okno** — zobrazuje se jen výsek dne kolem aktuální chvíle, takže se bloky
  ořezávají na jeho okraje (a pamatuje si, že přesahují),
* **dráhy** — paralelní skupiny téže třídy běží ve stejný čas, takže se skládají
  pod sebe; přiděluje se první dráha, která je v daném čase volná.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sol.denni_rozvrh import DenniRozvrh, Hodina


def minuty(cas: str) -> int | None:
    """„08:30“ -> 510 minut od půlnoci."""
    try:
        h, _, m = cas.partition(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


@dataclass
class Blok:
    nazev: str
    ucitel: str
    ucebna: str
    akce: bool
    od: str                 # čas začátku, jak se zobrazí
    do: str
    zleva: float            # pozice v % šířky časové osy
    sirka: float            # šířka v %
    draha: int = 0          # pořadí dráhy (paralelní skupiny pod sebou)
    presah_vlevo: bool = False   # blok začal před oknem
    presah_vpravo: bool = False  # a/nebo končí až za ním
    probiha: bool = False


@dataclass
class RadekTridy:
    trida: str
    bloky: list[Blok] = field(default_factory=list)
    drahy: int = 1          # kolik drah řádek potřebuje


@dataclass
class Znacka:
    popisek: str
    zleva: float


@dataclass
class Obrazovka:
    od_minut: int
    do_minut: int
    ted_minut: int
    ted_zleva: float
    znacky: list[Znacka] = field(default_factory=list)
    radky: list[RadekTridy] = field(default_factory=list)

    @property
    def delka_minut(self) -> int:
        return self.do_minut - self.od_minut


def _prirad_drahy(bloky: list[tuple[int, int, Hodina]]) -> dict[int, int]:
    """Každému bloku dá nejnižší dráhu, kde se s ničím nepřekrývá.

    Vrací mapu index bloku -> dráha. Bloky musí přijít seřazené podle začátku.
    """
    konce: list[int] = []       # konec posledního bloku v každé dráze
    drahy: dict[int, int] = {}
    for i, (zac, kon, _) in enumerate(bloky):
        for d, konec in enumerate(konce):
            if zac >= konec:
                drahy[i] = d
                konce[d] = kon
                break
        else:
            drahy[i] = len(konce)
            konce.append(kon)
    return drahy


def sestav(rozvrh: DenniRozvrh, ted_minut: int,
           zpet: int = 60, vpred: int = 120, krok_znacek: int = 30) -> Obrazovka:
    """Postaví pohled na okno ``<ted-zpet, ted+vpred>``.

    Výchozí hodnoty dávají tříhodinové okno se současnou chvílí v jeho třetině.
    """
    od = ted_minut - zpet
    do = ted_minut + vpred
    delka = max(1, do - od)

    def pct(m: int) -> float:
        return (m - od) / delka * 100

    obrazovka = Obrazovka(od_minut=od, do_minut=do, ted_minut=ted_minut,
                          ted_zleva=pct(ted_minut))

    # značky času zarovnané na celé násobky kroku
    znacka = od + (-od) % krok_znacek
    while znacka <= do:
        obrazovka.znacky.append(
            Znacka(popisek=f"{znacka // 60 % 24}:{znacka % 60:02d}", zleva=pct(znacka)))
        znacka += krok_znacek

    for t in rozvrh.tridy:
        viditelne: list[tuple[int, int, Hodina]] = []
        for h in t.hodiny:
            zac, kon = minuty(h.od), minuty(h.do)
            if zac is None or kon is None or kon <= od or zac >= do:
                continue        # mimo okno
            viditelne.append((zac, kon, h))
        viditelne.sort(key=lambda x: (x[0], x[1]))

        drahy = _prirad_drahy(viditelne)
        radek = RadekTridy(trida=t.trida, drahy=max(drahy.values(), default=-1) + 1 or 1)
        for i, (zac, kon, h) in enumerate(viditelne):
            zleva, zprava = pct(max(zac, od)), pct(min(kon, do))
            radek.bloky.append(Blok(
                nazev=h.popis, ucitel=h.ucitele, ucebna=h.ucebna, akce=h.akce,
                od=h.od, do=h.do, zleva=zleva, sirka=max(0.0, zprava - zleva),
                draha=drahy[i], presah_vlevo=zac < od, presah_vpravo=kon > do,
                probiha=zac <= ted_minut < kon))
        obrazovka.radky.append(radek)

    return obrazovka
