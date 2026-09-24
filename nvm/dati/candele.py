"""Dalle candele da un minuto a quelle di ogni timeframe, bid e ask.

I confini vengono tutti da `nvm.tempo`: la giornata chiude alle 17:00 di New
York. Qui si raggruppa e basta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import PASSO, TF, fine_candela, inizio_candela


@dataclass
class Candele:
    """Candele di uno strumento su un timeframe, in prezzi (non punti).

    `bid` e `ask` hanno quattro colonne: apertura, massimo, minimo, chiusura.
    `inizio` e `fine` sono gli istanti UTC nominali di apertura e chiusura.
    """

    strumento: str
    tf: TF
    inizio: np.ndarray
    fine: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.inizio)

    def chiuse_entro(self, istante: int) -> "Candele":
        """Solo le candele gia' chiuse a quell'istante: il futuro non si guarda."""
        n = int(np.searchsorted(self.fine, istante, side="right"))
        return self.prime(n)

    def prime(self, n: int) -> "Candele":
        return Candele(
            self.strumento, self.tf, self.inizio[:n], self.fine[:n],
            self.bid[:n], self.ask[:n], self.volume[:n],
        )

    def fra(self, dal: int, al: int) -> "Candele":
        """Le candele che aprono in [dal, al)."""
        i, j = np.searchsorted(self.inizio, [dal, al])
        return Candele(
            self.strumento, self.tf, self.inizio[i:j], self.fine[i:j],
            self.bid[i:j], self.ask[i:j], self.volume[i:j],
        )


def costruisci(minuti: Minuti, tf: TF) -> Candele:
    """Raggruppa le candele di base (minuti, o ore) nelle candele di `tf`."""
    if tf in PASSO and PASSO[tf] < minuti.passo:
        raise ValueError(f"non si costruisce {tf.value} da candele di {minuti.passo} secondi")
    if not len(minuti):
        vuoto = np.empty(0, np.int64)
        return Candele(minuti.strumento, tf, vuoto, vuoto, np.empty((0, 4)), np.empty((0, 4)), np.empty(0))

    inizi_minuti = inizio_candela(minuti.t, tf)
    # I minuti sono in ordine, quindi anche gli inizi: ogni cambio e' una candela nuova.
    nuove = np.flatnonzero(np.r_[True, inizi_minuti[1:] != inizi_minuti[:-1]])
    ultime = np.r_[nuove[1:] - 1, len(minuti) - 1]

    def raggruppa(punti: np.ndarray) -> np.ndarray:
        prezzi = np.empty((len(nuove), 4))
        prezzi[:, APERTURA] = punti[nuove, APERTURA]
        prezzi[:, MASSIMO] = np.maximum.reduceat(punti[:, MASSIMO], nuove)
        prezzi[:, MINIMO] = np.minimum.reduceat(punti[:, MINIMO], nuove)
        prezzi[:, CHIUSURA] = punti[ultime, CHIUSURA]
        return prezzi * minuti.punto

    inizi = inizi_minuti[nuove]
    if tf in (TF.M1, TF.M5, TF.M15, TF.H1):
        fini = inizi + PASSO[tf]
    else:
        fini = np.fromiter((fine_candela(int(i), tf) for i in inizi), dtype=np.int64, count=len(inizi))
    volume = np.add.reduceat(minuti.volume_bid.astype(np.float64), nuove)
    return Candele(minuti.strumento, tf, inizi, fini, raggruppa(minuti.bid), raggruppa(minuti.ask), volume)
