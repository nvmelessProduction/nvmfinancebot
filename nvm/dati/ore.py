"""Le ore di uno strumento per un periodo: esatte dove si ha l'ask, stimate altrove.

    dati/grezzi/ore/       mesi con bid e ask veri (scaricati da Dukascopy)
    dati/grezzi/ore_bid/   mesi col solo bid (il vecchio archivio, verificato)

Un mese esatto vince sempre. Per gli altri l'ask e' il bid piu' lo spread
misurato (`nvm.dati.spread`). Il resoconto dice quanti mesi sono esatti e
quanti stimati, perche' la misura lo deve dichiarare.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from nvm.dati.minuti import Minuti, file_del_mese
from nvm.dati.spread import ModelloSpread


@dataclass
class Resoconto:
    esatti: int
    stimati: int
    mancanti: int


def _mesi(dal: int, al: int) -> list[tuple[int, int]]:
    inizio = np.datetime64(dal, "s").astype("datetime64[M]")
    fine = np.datetime64(al - 1, "s").astype("datetime64[M]")
    return [(int(str(m)[:4]), int(str(m)[5:7])) for m in np.arange(inizio, fine + 1)]


def carica(radice: Path, strumento: str, dal: int, al: int, solo_bid: bool = False) -> tuple[Minuti, Resoconto]:
    """Le ore in [dal, al). `radice` contiene le cartelle `ore` e `ore_bid`.

    Con `solo_bid` i mesi senza ask si prendono anche senza modello di
    spread, con l'ask uguale al bid: serve per riconoscere i CRT, che
    guardano solo il bid. Mai per misurare risultati.
    """
    esatti_tutti = [Minuti.carica(p) for p in sorted((radice / "ore" / strumento).glob("*.npz"))]
    esatti_tutti = [m for m in esatti_tutti if len(m)]
    modello = ModelloSpread.da(esatti_tutti) if esatti_tutti else None
    pezzi, conti = [], Resoconto(0, 0, 0)
    for anno, mese in _mesi(dal, al):
        esatto = file_del_mese(radice / "ore", strumento, anno, mese)
        solo_bid_p = file_del_mese(radice / "ore_bid", strumento, anno, mese)
        if esatto.exists():
            pezzi.append(Minuti.carica(esatto))
            conti.esatti += 1
        elif solo_bid_p.exists() and modello is not None:
            pezzi.append(modello.applica(Minuti.carica(solo_bid_p)))
            conti.stimati += 1
        elif solo_bid_p.exists() and solo_bid:
            pezzi.append(Minuti.carica(solo_bid_p))
            conti.stimati += 1
        else:
            conti.mancanti += 1
    pezzi = [p.fra(dal, al) for p in pezzi if len(p)]
    pezzi = [p for p in pezzi if len(p)]
    minuti = Minuti.unisci(pezzi) if pezzi else Minuti.vuoti(strumento, 3600)
    return minuti, conti
