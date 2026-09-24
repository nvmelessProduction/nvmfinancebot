"""Le candele di base con bid e ask: la materia prima di tutte le altre.

Di solito sono minuti; per lo storico lungo delle coppie lente bastano le
ore (`passo` = 3600). I prezzi stanno in punti interi, come li da'
Dukascopy, cosi' non si perde precisione: si convertono in prezzi solo
quando servono.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Quanto vale un punto, per strumento. Sono i divisori di Dukascopy.
PUNTO = {
    "EURUSD": 1e-5,
    "GBPUSD": 1e-5,
    "AUDUSD": 1e-5,
    "USDCHF": 1e-5,
    "USDJPY": 1e-3,
    "XAUUSD": 1e-3,
}

APERTURA, MASSIMO, MINIMO, CHIUSURA = range(4)


@dataclass
class Minuti:
    """Candele di base di uno strumento, ordinate nel tempo.

    `t` e' l'istante UTC (secondi) in cui apre ogni candela, lunga `passo`
    secondi. `bid` e `ask` hanno quattro colonne: apertura, massimo, minimo,
    chiusura, in punti.
    """

    strumento: str
    t: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    volume_bid: np.ndarray
    volume_ask: np.ndarray
    passo: int = 60

    def __post_init__(self) -> None:
        n = len(self.t)
        for nome in ("bid", "ask"):
            if getattr(self, nome).shape != (n, 4):
                raise ValueError(f"{nome}: attese {n} righe da 4 colonne")
        if n and np.any(np.diff(self.t) <= 0):
            raise ValueError("i minuti devono essere in ordine e senza doppioni")

    def __len__(self) -> int:
        return len(self.t)

    @property
    def punto(self) -> float:
        return PUNTO[self.strumento]

    @classmethod
    def vuoti(cls, strumento: str, passo: int = 60) -> "Minuti":
        return cls(
            strumento,
            np.empty(0, np.int64),
            np.empty((0, 4), np.int32),
            np.empty((0, 4), np.int32),
            np.empty(0, np.float32),
            np.empty(0, np.float32),
            passo,
        )

    @classmethod
    def unisci(cls, pezzi: list["Minuti"]) -> "Minuti":
        pezzi = [p for p in pezzi if len(p)]
        if not pezzi:
            raise ValueError("niente da unire")
        strumento, passo = pezzi[0].strumento, pezzi[0].passo
        if any(p.passo != passo for p in pezzi):
            raise ValueError("non si uniscono candele di passo diverso")
        return cls(
            strumento,
            np.concatenate([p.t for p in pezzi]),
            np.concatenate([p.bid for p in pezzi]),
            np.concatenate([p.ask for p in pezzi]),
            np.concatenate([p.volume_bid for p in pezzi]),
            np.concatenate([p.volume_ask for p in pezzi]),
            passo,
        )

    def fra(self, dal: int, al: int) -> "Minuti":
        """I minuti che aprono in [dal, al)."""
        i, j = np.searchsorted(self.t, [dal, al])
        return Minuti(
            self.strumento, self.t[i:j], self.bid[i:j], self.ask[i:j],
            self.volume_bid[i:j], self.volume_ask[i:j], self.passo,
        )

    def salva(self, percorso: Path) -> None:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            percorso, strumento=np.array(self.strumento), t=self.t, bid=self.bid,
            ask=self.ask, volume_bid=self.volume_bid, volume_ask=self.volume_ask,
            passo=np.array(self.passo),
        )

    @classmethod
    def carica(cls, percorso: Path) -> "Minuti":
        with np.load(percorso) as f:
            passo = int(f["passo"]) if "passo" in f else 60
            return cls(
                str(f["strumento"]), f["t"], f["bid"], f["ask"],
                f["volume_bid"], f["volume_ask"], passo,
            )


def cartella_strumento(radice: Path, strumento: str) -> Path:
    return radice / strumento


def file_del_mese(radice: Path, strumento: str, anno: int, mese: int) -> Path:
    return cartella_strumento(radice, strumento) / f"{strumento}-{anno:04d}-{mese:02d}.npz"


def carica_periodo(radice: Path, strumento: str, dal: int, al: int) -> Minuti:
    """Tutti i minuti salvati di uno strumento fra due istanti UTC."""
    inizio = np.datetime64(dal, "s").astype("datetime64[M]")
    fine = np.datetime64(al - 1, "s").astype("datetime64[M]")
    pezzi = []
    mese = inizio
    while mese <= fine:
        anno, m = int(str(mese)[:4]), int(str(mese)[5:7])
        percorso = file_del_mese(radice, strumento, anno, m)
        if percorso.exists():
            pezzi.append(Minuti.carica(percorso).fra(dal, al))
        mese += 1
    pezzi = [p for p in pezzi if len(p)]
    return Minuti.unisci(pezzi) if pezzi else Minuti.vuoti(strumento)
