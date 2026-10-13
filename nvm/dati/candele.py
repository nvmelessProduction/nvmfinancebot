"""Dalle candele da un minuto a quelle di ogni timeframe, bid e ask.

I confini vengono tutti da `nvm.tempo`: le candele aprono come quelle di MT5,
alle 17:00 di New York; quelle delle crypto sul calendario UTC. Qui si raggruppa e basta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import ORE_18, PASSO, TF, fine_candela, inizio_candela


def weekend(strumento: str) -> bool:
    """Lo strumento scambia anche sabato e domenica (le crypto): i suoi giorni non si spostano al lunedi'."""
    s = STRUMENTI.get(strumento)
    # La TOTAL di TradingView (la capitalizzazione di tutte le crypto) ha gli orari delle crypto.
    return strumento == "TOTAL" or (s is not None and s.famiglia == "crypto")


# Sui grafici di TradingView: il calendario del grafico collegato, per strumento (l'ora di New York in cui apre la
# sessione, o True se le sue candele seguono l'UTC). Lo scrive il bot all'avvio leggendo le candele a 4 ore di
# TradingView (`vivo.Bot._candele_tradingview`): il proprietario, 13/10/2026, *"i grafici che noi abbiamo collegato
# già vanno 0, 4, 8, 12, 16, 20. Deve essere uguale"*.
SESSIONI: dict = {}


def calendario(strumento: str):
    """Il calendario delle candele dello strumento, per `tempo.inizio_candela`: quello del grafico di TradingView
    collegato (`SESSIONI`), se c'e'; se no vero per le crypto, `tempo.ORE_18` per i metalli (le candele partono alle
    18 di New York, come su TradingView), falso per il resto (dalle 17, come MT5)."""
    if strumento in SESSIONI:
        return SESSIONI[strumento]
    if weekend(strumento):
        return True
    s = STRUMENTI.get(strumento)
    return ORE_18 if s is not None and s.famiglia == "metalli" else False


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

    fine_sett = calendario(minuti.strumento)
    inizi_minuti = inizio_candela(minuti.t, tf, fine_sett)
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
        fini = np.fromiter((fine_candela(int(i), tf, fine_sett) for i in inizi), dtype=np.int64, count=len(inizi))
    volume = np.add.reduceat(minuti.volume_bid.astype(np.float64), nuove)
    return Candele(minuti.strumento, tf, inizi, fini, raggruppa(minuti.bid), raggruppa(minuti.ask), volume)


def raggruppa(c: Candele, tf: TF) -> Candele:
    """Mette insieme candele gia' fatte (le ore o i mesi di TradingView) in quelle di `tf`, sulla griglia del
    calendario dello strumento: per i timeframe che TradingView non da' (6 e 12 ore, 3, 6 e 12 mesi)."""
    if not len(c):
        return Candele(c.strumento, tf, c.inizio[:0], c.fine[:0], c.bid[:0], c.ask[:0], c.volume[:0])
    cal = calendario(c.strumento)
    chiavi = inizio_candela(c.inizio, tf, cal)
    nuove = np.flatnonzero(np.r_[True, chiavi[1:] != chiavi[:-1]])
    ultime = np.r_[nuove[1:] - 1, len(c) - 1]

    def insieme(p: np.ndarray) -> np.ndarray:
        return np.c_[p[nuove, APERTURA], np.maximum.reduceat(p[:, MASSIMO], nuove),
                     np.minimum.reduceat(p[:, MINIMO], nuove), p[ultime, CHIUSURA]]
    inizi = chiavi[nuove]
    fini = np.fromiter((fine_candela(int(i), tf, cal) for i in inizi), dtype=np.int64, count=len(inizi))
    return Candele(c.strumento, tf, inizi, fini, insieme(c.bid), insieme(c.ask), np.add.reduceat(c.volume, nuove))


def unisci(vecchie: Optional[Candele], nuove: Candele) -> Candele:
    """Le candele gia' avute piu' quelle appena arrivate: dove si sovrappongono valgono le nuove."""
    if vecchie is None or not len(vecchie):
        return nuove
    if not len(nuove):
        return vecchie
    k = int(np.searchsorted(vecchie.inizio, nuove.inizio[0]))
    return Candele(nuove.strumento, nuove.tf, np.r_[vecchie.inizio[:k], nuove.inizio], np.r_[vecchie.fine[:k], nuove.fine],
                   np.r_[vecchie.bid[:k], nuove.bid], np.r_[vecchie.ask[:k], nuove.ask],
                   np.r_[vecchie.volume[:k], nuove.volume])
