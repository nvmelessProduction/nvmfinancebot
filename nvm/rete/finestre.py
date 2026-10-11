"""Quello che la rete vede a un istante: le ultime candele chiuse di ogni timeframe, con le candele di MT5.

Per ogni istante `t` e ogni timeframe di `TF_RETE` si prendono le ultime `LUNGHEZZA` candele gia' chiuse a `t` (mai
una candela che chiude dopo: niente futuro). I prezzi si scrivono rispetto all'ultima chiusura a 1 ora e in unita'
del range medio giornaliero, compressi con l'arcoseno iperbolico: cosi' una candela mensile di tre anni fa e una a
1 ora di adesso stanno sulla stessa scala, e la rete vale per tutti gli strumenti. Le candele che mancano (inizio
dello storico) sono segnate in `vuote`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import TF, scarti_ny

# I timeframe che la rete guarda, dal piu' piccolo al piu' grande, e quante candele per ognuno.
TF_RETE = (TF.H1, TF.H4, TF.D1, TF.W1, TF.MN)
LUNGHEZZA = 40
# Per ogni candela: apertura, massimo, minimo, chiusura (scalati), se e' salita, l'ora di New York (seno, coseno).
CARATTERISTICHE = 7
# Su quante giornate si misura il range medio, l'unita' dei prezzi.
GIORNI_SCALA = 14


@dataclass
class Storia:
    """Le candele di ogni timeframe di uno strumento, costruite una volta sola."""

    strumento: str
    candele: dict

    @classmethod
    def da(cls, ore: Minuti) -> "Storia":
        return cls(ore.strumento, {tf: costruisci(ore, tf) for tf in TF_RETE})

    def istanti(self, dal: int, al: int) -> np.ndarray:
        """Gli istanti in cui la rete guarda: le aperture delle candele a 4 ore in [dal, al). Li' aprono anche le
        candele 3 dei CRT a 4 ore e di quelli del giorno (le candele di MT5)."""
        c = self.candele[TF.H4]
        return c.inizio[(c.inizio >= dal) & (c.inizio < al)].astype(np.int64)


def _ultime(c: Candele, t: np.ndarray) -> np.ndarray:
    """Per ogni istante, l'indice dell'ultima candela chiusa (fine <= t); -1 se nessuna."""
    return np.searchsorted(c.fine, t, side="right") - 1


def finestre(st: Storia, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Le finestre a ogni istante di `t`: (x [N, n_tf, LUNGHEZZA, CARATTERISTICHE] float32, vuote [N, n_tf,
    LUNGHEZZA] bool). La candela piu' recente e' l'ultima."""
    t = np.asarray(t, np.int64)
    n = len(t)
    ore = st.candele[TF.H1]
    k = _ultime(ore, t)
    rif = np.where(k >= 0, ore.bid[np.maximum(k, 0), CHIUSURA], np.nan)
    giorni = st.candele[TF.D1]
    kd = _ultime(giorni, t)
    passi = np.arange(-GIORNI_SCALA + 1, 1)
    idx = kd[:, None] + passi[None, :]
    ok = idx >= 0
    rng = np.where(ok, giorni.bid[np.maximum(idx, 0), MASSIMO] - giorni.bid[np.maximum(idx, 0), MINIMO], np.nan)
    with np.errstate(invalid="ignore"):
        scala = np.nanmean(np.where(ok, rng, np.nan), axis=1)
    scala = np.where(np.isfinite(scala) & (scala > 0), scala, np.nan)
    x = np.zeros((n, len(TF_RETE), LUNGHEZZA, CARATTERISTICHE), np.float32)
    vuote = np.ones((n, len(TF_RETE), LUNGHEZZA), bool)
    passi = np.arange(-LUNGHEZZA + 1, 1)
    for i, tf in enumerate(TF_RETE):
        c = st.candele[tf]
        idx = _ultime(c, t)[:, None] + passi[None, :]
        buone = (idx >= 0) & np.isfinite(rif)[:, None] & np.isfinite(scala)[:, None]
        j = np.maximum(idx, 0)
        prezzi = c.bid[j][..., [APERTURA, MASSIMO, MINIMO, CHIUSURA]]
        rel = (prezzi - rif[:, None, None]) / scala[:, None, None]
        x[:, i, :, :4] = np.where(buone[..., None], np.arcsinh(rel), 0.0)
        x[:, i, :, 4] = np.where(buone, (c.bid[j, CHIUSURA] > c.bid[j, APERTURA]).astype(np.float32), 0.0)
        inizi = c.inizio[j]
        ora = ((inizi + scarti_ny(inizi.ravel()).reshape(inizi.shape)) % 86400) / 3600.0
        x[:, i, :, 5] = np.where(buone, np.sin(2 * np.pi * ora / 24), 0.0)
        x[:, i, :, 6] = np.where(buone, np.cos(2 * np.pi * ora / 24), 0.0)
        vuote[:, i, :] = ~buone
    return x, vuote
