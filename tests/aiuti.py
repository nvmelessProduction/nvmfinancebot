"""Dati sintetici per le prove."""

from __future__ import annotations

import lzma
import struct

import numpy as np

from nvm.dati.minuti import Minuti


def bi5(righe: list[tuple[int, int, int, int, int, float]]) -> bytes:
    """Un file bi5 come quelli di Dukascopy.

    Ogni riga: secondi dall'inizio del giorno, apertura, massimo, minimo,
    chiusura (in punti), volume. Nel file l'ordine e' apertura, chiusura,
    minimo, massimo.
    """
    grezzo = b"".join(
        struct.pack(">iiiiif", s, o, c, l, h, v) for s, o, h, l, c, v in righe
    )
    return lzma.compress(grezzo, format=lzma.FORMAT_ALONE)


def minuti(strumento: str, t: list[int], prezzi: list[tuple[float, float, float, float]], spread: float = 0.0) -> Minuti:
    """Minuti da prezzi (non punti). L'ask e' il bid piu' `spread`."""
    punto = Minuti.vuoti(strumento).punto
    bid = np.rint(np.array(prezzi) / punto).astype(np.int32)
    ask = bid + int(round(spread / punto))
    n = len(t)
    return Minuti(
        strumento, np.array(t, np.int64), bid, ask,
        np.ones(n, np.float32), np.ones(n, np.float32),
    )


def minuti_piatti(strumento: str, dal: int, al: int, prezzo: float = 1.1) -> Minuti:
    """Un minuto ogni minuto fra due istanti, tutti allo stesso prezzo."""
    t = list(range(dal, al, 60))
    return minuti(strumento, t, [(prezzo, prezzo, prezzo, prezzo)] * len(t))
