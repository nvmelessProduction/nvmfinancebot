"""Un cervello ad alberi per il Capo: il gradient boosting, scritto con numpy.

La regressione logistica del Capo somma i segnali uno per uno. Gli alberi
imparano anche le combinazioni ("FVG e ora di Londra e bias contro"): ogni
albero corregge un po' gli errori dei precedenti. Qui la versione piu'
semplice e robusta: alberi poco profondi, foglie con tante operazioni, passo
piccolo, con le colonne divise in fasce (istogrammi).
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def _sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class Alberi:
    def __init__(self, alberi: int = 150, profondita: int = 3, passo: float = 0.05, foglia: int = 300,
                 penalita: float = 1.0, fasce: int = 32):
        self.n, self.profondita, self.passo = alberi, profondita, passo
        self.foglia, self.penalita, self.fasce = foglia, penalita, fasce
        self.bordi: list[np.ndarray] = []
        self.base = 0.0
        # Ogni albero: per nodo (colonna, fascia di taglio, figlio sinistro, figlio destro, valore); -1 = foglia.
        self.alberi: list[np.ndarray] = []

    # --- fasce ---
    def _fasce(self, x: np.ndarray) -> np.ndarray:
        return np.column_stack([np.searchsorted(b, x[:, j], side="right") for j, b in enumerate(self.bordi)]).astype(np.int32)

    def allena(self, x: np.ndarray, y: np.ndarray, pesi: Optional[np.ndarray] = None) -> "Alberi":
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        w = np.ones(len(y)) if pesi is None else np.asarray(pesi, float)
        quantili = np.linspace(0, 1, self.fasce + 1)[1:-1]
        self.bordi = [np.unique(np.quantile(x[:, j], quantili)) for j in range(x.shape[1])]
        b = self._fasce(x)
        p0 = float(np.clip(np.average(y, weights=w), 1e-4, 1 - 1e-4))
        self.base = float(np.log(p0 / (1 - p0)))
        f = np.full(len(y), self.base)
        self.alberi = []
        for _ in range(self.n):
            p = _sigmoide(f)
            g, h = w * (p - y), w * p * (1 - p)
            albero = self._albero(b, g, h)
            f += self.passo * self._valuta(albero, b)
            self.alberi.append(albero)
        return self

    def _albero(self, b: np.ndarray, g: np.ndarray, h: np.ndarray) -> np.ndarray:
        nodi = [[-1, -1, -1, -1, 0.0]]
        foglia_di = np.zeros(len(g), np.int64)    # a quale nodo appartiene ogni operazione
        aperti = [0]
        k = self.fasce
        for _ in range(self.profondita):
            nuovi = []
            for nodo in aperti:
                dentro = foglia_di == nodo
                gt, ht, nt = g[dentro].sum(), h[dentro].sum(), int(dentro.sum())
                nodi[nodo][4] = -gt / (ht + self.penalita)
                if nt < 2 * self.foglia:
                    continue
                migliore = (0.0, -1, -1)
                bd, gd, hd = b[dentro], g[dentro], h[dentro]
                for j in range(b.shape[1]):
                    gs = np.bincount(bd[:, j], weights=gd, minlength=k)
                    hs = np.bincount(bd[:, j], weights=hd, minlength=k)
                    ns = np.bincount(bd[:, j], minlength=k)
                    gl, hl, nl = np.cumsum(gs)[:-1], np.cumsum(hs)[:-1], np.cumsum(ns)[:-1]
                    gr, hr, nr = gt - gl, ht - hl, nt - nl
                    guadagno = gl ** 2 / (hl + self.penalita) + gr ** 2 / (hr + self.penalita) - gt ** 2 / (ht + self.penalita)
                    guadagno[(nl < self.foglia) | (nr < self.foglia)] = 0.0
                    i = int(np.argmax(guadagno))
                    if guadagno[i] > migliore[0]:
                        migliore = (float(guadagno[i]), j, i)
                if migliore[1] < 0:
                    continue
                _, j, i = migliore
                sinistro, destro = len(nodi), len(nodi) + 1
                nodi[nodo][:4] = [j, i, sinistro, destro]
                nodi += [[-1, -1, -1, -1, 0.0], [-1, -1, -1, -1, 0.0]]
                va_a_destra = dentro & (b[:, j] > i)
                foglia_di[dentro & ~va_a_destra] = sinistro
                foglia_di[va_a_destra] = destro
                nuovi += [sinistro, destro]
            aperti = nuovi
        for nodo in aperti:
            dentro = foglia_di == nodo
            nodi[nodo][4] = -g[dentro].sum() / (h[dentro].sum() + self.penalita)
        return np.array(nodi, float)

    @staticmethod
    def _valuta(albero: np.ndarray, b: np.ndarray) -> np.ndarray:
        nodo = np.zeros(len(b), np.int64)
        for _ in range(64):
            colonna = albero[nodo, 0].astype(np.int64)
            foglia = colonna < 0
            if foglia.all():
                break
            taglio = albero[nodo, 1]
            destra = b[np.arange(len(b)), np.maximum(colonna, 0)] > taglio
            nodo = np.where(foglia, nodo, np.where(destra, albero[nodo, 3], albero[nodo, 2]).astype(np.int64))
        return albero[nodo, 4]

    def probabilita(self, x: np.ndarray) -> np.ndarray:
        b = self._fasce(np.atleast_2d(np.asarray(x, float)))
        f = np.full(len(b), self.base)
        for albero in self.alberi:
            f += self.passo * self._valuta(albero, b)
        return _sigmoide(f)

    # --- salvataggio ---
    def come_dati(self) -> dict:
        return {"parametri": [self.n, self.profondita, self.passo, self.foglia, self.penalita, self.fasce],
                "bordi": [b.tolist() for b in self.bordi], "base": self.base,
                "alberi": [a.tolist() for a in self.alberi]}

    @classmethod
    def da_dati(cls, d: dict) -> "Alberi":
        a = cls(*d["parametri"])
        a.bordi = [np.array(b, float) for b in d["bordi"]]
        a.base = float(d["base"])
        a.alberi = [np.array(x, float) for x in d["alberi"]]
        return a
