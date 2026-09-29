"""Il cervello del Rischio: quanto puntare su un'operazione.

Prima la puntata era una formula fissa (2 x fiducia - 1, "il Kelly pieno"), e il Rischio del conto
intero sceglieva solo la dose (`portafoglio.scegli`). Adesso il Rischio ha un cervello suo: vede
quanto ci crede la squadra e com'e' fatta l'operazione (obiettivi, stop, costi: la vista dei
Livelli) e dice quanto puntare, da 0 (niente) a 1 (il massimo che ha imparato a dare).

Impara a far crescere il conto: il suo obiettivo e' la crescita logaritmica, cioe' la media di
log(1 + puntata x R). Una perdita grande pesa piu' di un guadagno uguale e perdere tutto vale meno
infinito: nessuno gli scrive un tetto, capisce da solo che puntare tanto sull'incerto non conviene.
La dose finale (quanta parte del conto per ogni 1 del suo giudizio) la sceglie ancora la
simulazione del conto intero con le operazioni aperte insieme e la regola della rovina.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# Nella scuola, un giudizio di 1 vale questa parte del conto (all'incirca il Kelly pieno, come la
# formula di prima): da' la forma alla prudenza (quanto conta una perdita); la dose vera la sceglie
# poi il conto intero. Con R fino a -1,5 il conto non puo' andare sotto zero (1 - 0,6 x 1,5 > 0).
SCALA = 0.6
NEURONI = 8
FRENO = 1e-3
PASSO = 0.02
GIRI = 800
# Si parte puntando poco: e' la puntata grande che deve guadagnarsi il posto.
PARTENZA = -2.0
# I risultati si imparano dentro questa misura, in R.
TETTO = (-1.5, 6.0)


def vista_del_rischio(p: np.ndarray, livelli: np.ndarray) -> np.ndarray:
    """Quello che vede il Rischio: quanto ci crede la squadra (in log-quote) e la vista dei Livelli."""
    p = np.clip(np.atleast_1d(np.asarray(p, float)), 1e-4, 1 - 1e-4)
    return np.c_[np.log(p / (1 - p)), np.atleast_2d(np.asarray(livelli, float))]


def _sigmoide(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


@dataclass
class CervelloRischio:
    media: np.ndarray
    scala: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: float

    def _avanti(self, x):
        z = (np.atleast_2d(np.asarray(x, float)) - self.media) / self.scala
        h = np.tanh(z @ self.w1 + self.b1)
        return z, h, _sigmoide(h @ self.w2 + self.b2)

    def quanto(self, x: np.ndarray) -> np.ndarray:
        """Quanto puntare, da 0 a 1, per ogni riga di `x` (`vista_del_rischio`)."""
        return self._avanti(x)[2]

    def _gradiente(self, x, erre, w):
        z, h, f = self._avanti(x)
        r = np.clip(erre, *TETTO)
        # d/d(uscita) di log(1 + SCALA f R), per ogni esempio, pesato.
        d = -(w / w.sum()) * SCALA * r / (1 + SCALA * f * r) * f * (1 - f)
        g_w2 = h.T @ d + FRENO * self.w2
        dh = np.outer(d, self.w2) * (1 - h ** 2)
        return z.T @ dh + FRENO * self.w1, dh.sum(axis=0), g_w2, float(d.sum())

    def crescita(self, x, erre, w=None) -> float:
        w = np.ones(len(erre)) if w is None else np.asarray(w, float)
        f = self.quanto(x)
        return float(np.sum(w * np.log1p(SCALA * f * np.clip(erre, *TETTO))) / w.sum())

    @classmethod
    def allena(cls, x: np.ndarray, erre: np.ndarray, pesi: Optional[np.ndarray] = None, seme: int = 0,
               controllo: float = 0.15) -> "CervelloRischio":
        """A scuola, sugli esempi in ordine di tempo: gli ultimi `controllo` servono a capire quando
        fermarsi (si tiene il cervello che faceva crescere di piu' il conto su quelli)."""
        x, erre = np.asarray(x, float), np.asarray(erre, float)
        w = np.ones(len(erre)) if pesi is None else np.asarray(pesi, float)
        rng = np.random.default_rng(seme)
        s = x.std(axis=0)
        cervello = cls(x.mean(axis=0), np.where(s > 1e-9, s, 1.0), rng.normal(0, 1 / np.sqrt(x.shape[1]), (x.shape[1], NEURONI)),
                       np.zeros(NEURONI), rng.normal(0, 1 / np.sqrt(NEURONI), NEURONI), PARTENZA)
        taglio = int(len(erre) * (1 - controllo))
        xa, ra, wa, xc, rc, wc = x[:taglio], erre[:taglio], w[:taglio], x[taglio:], erre[taglio:], w[taglio:]
        m = [np.zeros_like(p) for p in (cervello.w1, cervello.b1, cervello.w2)] + [0.0]
        v = [np.zeros_like(p) for p in (cervello.w1, cervello.b1, cervello.w2)] + [0.0]
        migliore, copia = -np.inf, None
        for giro in range(1, GIRI + 1):
            g = cervello._gradiente(xa, ra, wa)
            for j, nome in enumerate(("w1", "b1", "w2", "b2")):
                m[j] = 0.9 * m[j] + 0.1 * g[j]
                v[j] = 0.999 * v[j] + 0.001 * np.square(g[j])
                passo = PASSO * (m[j] / (1 - 0.9 ** giro)) / (np.sqrt(v[j] / (1 - 0.999 ** giro)) + 1e-8)
                setattr(cervello, nome, getattr(cervello, nome) - passo)
            if giro % 10 == 0 and len(rc):
                c = cervello.crescita(xc, rc, wc)
                if c > migliore:
                    migliore, copia = c, cervello.come_dati()
        return cls.da_dati(copia) if copia is not None else cervello

    def aggiorna(self, x: np.ndarray, erre: np.ndarray, passo: float = 1e-3) -> "CervelloRischio":
        """Dal vivo, dopo un'operazione vera: un passo piccolo verso quello che avrebbe fatto crescere di piu'."""
        g = self._gradiente(np.atleast_2d(x), np.atleast_1d(np.asarray(erre, float)), np.ones(len(np.atleast_1d(erre))))
        self.w1, self.b1, self.w2 = self.w1 - passo * g[0], self.b1 - passo * g[1], self.w2 - passo * g[2]
        self.b2 = self.b2 - passo * g[3]
        return self

    def come_dati(self) -> dict:
        return {"media": self.media.tolist(), "scala": self.scala.tolist(), "w1": self.w1.tolist(),
                "b1": self.b1.tolist(), "w2": self.w2.tolist(), "b2": float(self.b2)}

    @classmethod
    def da_dati(cls, d: dict) -> "CervelloRischio":
        return cls(np.array(d["media"]), np.array(d["scala"]), np.array(d["w1"]), np.array(d["b1"]), np.array(d["w2"]),
                   float(d["b2"]))
