"""Il dollar index, calcolato dai suoi costituenti. Senza, il bot non opera.

## Perche' questo file esiste

`SETUP-19` fa dipendere cinque coppie su sei dalla bias del DXY, e dice che
con bias DXY `NESSUNA` **non si opera su alcuna coppia**. L'archivio del DXY
non e' un di piu': senza, il bot si astiene sempre, su tutto tranne l'oro
(`PRIN-09` esenta `XAUUSD`).

Dukascopy pubblica `USDIDX`, e sembra la risposta. Non lo e': il file c'e' ma
e' inerte — 744 record al mese, volume zero su tutti, un solo valore distinto
ripetuto per l'intero mese. L'ho verificato su 2020, 2025 e 2026. Metterlo in
archivio avrebbe dato una serie piatta, quindi una bias sempre `NESSUNA`,
quindi esattamente il bot fermo di prima ma con l'aria di essere a posto.

I **sei costituenti** dell'indice, invece, ci sono tutti e sono veri.

## La formula, e cosa e' esatto e cosa no

L'indice ICE e' una media geometrica pesata dei tassi contro dollaro:

    DXY = 50,14348112 x EURUSD^-0,576 x USDJPY^0,136 x GBPUSD^-0,119
                      x USDCAD^0,091  x USDSEK^0,042 x USDCHF^0,036

I pesi con segno negativo sono le coppie quotate al contrario (`EURUSD` sale
quando il dollaro scende).

**Apertura e chiusura sono esatte**: l'indice a un istante e' la formula
applicata ai sei tassi di quell'istante, e le aperture (come le chiusure)
dei sei costituenti sono simultanee.

**Massimo e minimo no, e va detto.** L'indice e' monotono in ciascun tasso —
cresce con `USDJPY`, `USDCAD`, `USDSEK`, `USDCHF` e cala con `EURUSD` e
`GBPUSD` — quindi applicando a ogni coppia l'estremo che spinge l'indice
verso l'alto si ottiene un massimo **almeno pari** a quello vero. E' un
involucro: corretto come limite, largo se i sei estremi non sono simultanei.
Essendo tutti e sei mossi dallo stesso dollaro, in pratica lo sono quasi.
Quanto quasi e' misurato in `docs/DXY-INVOLUCRO.md`, non supposto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from core.definizioni import Candela
from core.log import diario

log = diario("duka_dxy")

# Il nome sotto cui il DXY sta in archivio: e' `DXY_FUTURE` di `core/simboli`,
# lo strumento di sola analisi di PRIN-08.
NOME_ARCHIVIO = "ICEUS"

# I sei costituenti dell'indice ICE, col loro peso. Il segno negativo marca
# le coppie quotate xxx/USD invece che USD/xxx.
PESI: dict[str, float] = {
    "EURUSD": -0.576,
    "USDJPY": 0.136,
    "GBPUSD": -0.119,
    "USDCAD": 0.091,
    "USDSEK": 0.042,
    "USDCHF": 0.036,
}
COSTANTE = 50.14348112


def indice(tassi: dict[str, float]) -> float:
    """L'indice a un istante, dai sei tassi di quell'istante."""
    valore = COSTANTE
    for simbolo, peso in PESI.items():
        valore *= tassi[simbolo] ** peso
    return valore


def _estremi(candela: Candela, peso: float) -> tuple[float, float]:
    """(valore che spinge l'indice in alto, valore che lo spinge in basso)."""
    if peso < 0:
        return candela.minimo, candela.massimo
    return candela.massimo, candela.minimo


def candela_dxy(pezzi: dict[str, Candela]) -> Optional[Candela]:
    """Una candela del DXY dalle sei candele simultanee dei costituenti.

    `None` se manca anche uno solo dei sei: un indice a cinque valute non e'
    il DXY, e sostituire il sesto con l'ultimo valore noto inventerebbe un
    prezzo. Meglio un buco, che `DEF-26` sa gia' trattare.
    """
    if any(s not in pezzi for s in PESI):
        return None
    alto = {s: _estremi(pezzi[s], p)[0] for s, p in PESI.items()}
    basso = {s: _estremi(pezzi[s], p)[1] for s, p in PESI.items()}
    orario = max(pezzi[s].orario for s in PESI)
    return Candela(
        orario,
        indice({s: pezzi[s].apertura for s in PESI}),
        indice(alto),
        indice(basso),
        indice({s: pezzi[s].chiusura for s in PESI}),
    )


def componi(
    serie: dict[str, Iterable[Candela]]
) -> list[Candela]:
    """Le candele del DXY dagli storici dei sei costituenti.

    Si tengono solo gli istanti in cui **tutte e sei** hanno una candela. Le
    sei serie non coincidono mai del tutto: ogni coppia ha le sue ore senza
    scambi, e su `USDSEK` sono parecchie.
    """
    per_simbolo: dict[str, dict[datetime, Candela]] = {
        s: {c.orario: c for c in candele} for s, candele in serie.items()
    }
    mancanti = [s for s in PESI if s not in per_simbolo]
    if mancanti:
        log.warning("DXY non calcolabile: mancano %s", ", ".join(mancanti))
        return []

    comuni = set.intersection(*(set(m) for m in per_simbolo.values()))
    fuori = []
    for orario in sorted(comuni):
        candela = candela_dxy({s: per_simbolo[s][orario] for s in PESI})
        if candela is not None:
            fuori.append(candela)
    return fuori
