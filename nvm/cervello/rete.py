"""Il cervello di un agente: una rete neurale piccola, scritta da noi (solo numpy).

Riceve quello che l'agente vede (`viste.py`) e dice quanto crede che l'operazione arrivi al
primo obiettivo, come logaritmo delle quote. Impara dagli esempi: a scuola sui vent'anni,
poi dal vivo, un'operazione alla volta (`aggiorna`). Quello che sa sta nei suoi pesi: per
decidere non ha bisogno di rileggere lo storico.

Com'e' fatta: gli ingressi passano per un logaritmo con segno (un valore dieci volte piu'
grande non deve contare dieci volte di piu'), si standardizzano, poi uno strato nascosto di
neuroni (tanh) e un'uscita. Si allena con la discesa del gradiente (Adam), con una penalita'
sui pesi e fermandosi quando smette di migliorare su esempi che non ha visto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

NASCOSTI = 16
PENALITA = 1e-3
PASSO = 3e-3
LOTTO = 512
GIRI = 60
PAZIENZA = 6


def _entra(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(np.asarray(x, float), nan=0.0, posinf=0.0, neginf=0.0)
    return np.sign(x) * np.log1p(np.abs(x))


def _perdita(logit: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    return float(np.sum(w * (np.logaddexp(0, logit) - y * logit)) / np.sum(w))


@dataclass
class Rete:
    media: np.ndarray
    scala: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: float

    @classmethod
    def nuova(cls, entrate: int, nascosti: int = NASCOSTI, seme: int = 0) -> "Rete":
        rng = np.random.default_rng(seme)
        return cls(np.zeros(entrate), np.ones(entrate), rng.normal(0, 1 / np.sqrt(entrate), (entrate, nascosti)),
                   np.zeros(nascosti), rng.normal(0, 1 / np.sqrt(nascosti), nascosti), 0.0)

    def _z(self, x: np.ndarray) -> np.ndarray:
        return (_entra(x) - self.media) / self.scala

    def nascosto(self, x: np.ndarray) -> np.ndarray:
        """Cosa "pensa" dentro: l'attivita' dei neuroni nascosti."""
        return np.tanh(self._z(np.atleast_2d(x)) @ self.w1 + self.b1)

    def logit(self, x: np.ndarray) -> np.ndarray:
        return self.nascosto(x) @ self.w2 + self.b2

    def probabilita(self, x: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-self.logit(x)))

    @classmethod
    def allena(cls, x: np.ndarray, y: np.ndarray, pesi: Optional[np.ndarray] = None, nascosti: int = NASCOSTI,
               seme: int = 0, controllo: float = 0.15) -> "Rete":
        """A scuola: impara da `x` (una riga per esempio) a prevedere `y` (0/1). Gli ultimi
        `controllo` esempi (i piu' recenti, se sono in ordine di tempo) non li usa per imparare
        ma per capire quando fermarsi."""
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        w = np.ones(len(y)) if pesi is None else np.asarray(pesi, float)
        rete = cls.nuova(x.shape[1], nascosti, seme)
        z = _entra(x)
        rete.media = z.mean(axis=0)
        s = z.std(axis=0)
        rete.scala = np.where(s > 1e-9, s, 1.0)
        taglio = int(len(y) * (1 - controllo))
        rete.b2 = float(np.log(max(y[:taglio].mean(), 1e-3) / max(1 - y[:taglio].mean(), 1e-3)))
        rete._impara(x[:taglio], y[:taglio], w[:taglio], x[taglio:], y[taglio:], w[taglio:], seme)
        return rete

    def aggiorna(self, x: np.ndarray, y: np.ndarray, passi: int = 1, passo: float = PASSO / 3,
                 pesi: Optional[np.ndarray] = None) -> "Rete":
        """Dal vivo: impara da poche operazioni nuove, senza dimenticare la scuola (passi piccoli)."""
        x, y = np.atleast_2d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        w = np.ones(len(y)) if pesi is None else np.atleast_1d(np.asarray(pesi, float))
        for _ in range(passi):
            g = self._gradiente(self._z(x), y, w)
            for nome, dg in zip(("w1", "b1", "w2", "b2"), g):
                setattr(self, nome, getattr(self, nome) - passo * dg)
        return self

    def _gradiente(self, z, y, w):
        h = np.tanh(z @ self.w1 + self.b1)
        logit = h @ self.w2 + self.b2
        d = w * (1 / (1 + np.exp(-logit)) - y) / np.sum(w)
        g_w2 = h.T @ d + PENALITA * self.w2
        g_b2 = float(d.sum())
        dh = np.outer(d, self.w2) * (1 - h ** 2)
        g_w1 = z.T @ dh + PENALITA * self.w1
        g_b1 = dh.sum(axis=0)
        return g_w1, g_b1, g_w2, g_b2

    def _impara(self, x, y, w, xc, yc, wc, seme):
        rng = np.random.default_rng(seme)
        z, zc = self._z(x), self._z(xc)
        m = [np.zeros_like(self.w1), np.zeros_like(self.b1), np.zeros_like(self.w2), 0.0]
        v = [np.zeros_like(self.w1), np.zeros_like(self.b1), np.zeros_like(self.w2), 0.0]
        migliore, copia, fermo, t = np.inf, None, 0, 0
        for _ in range(GIRI):
            ordine = rng.permutation(len(y))
            for i in range(0, len(y), LOTTO):
                k = ordine[i:i + LOTTO]
                g = self._gradiente(z[k], y[k], w[k])
                t += 1
                for j, nome in enumerate(("w1", "b1", "w2", "b2")):
                    m[j] = 0.9 * m[j] + 0.1 * g[j]
                    v[j] = 0.999 * v[j] + 0.001 * g[j] * g[j]
                    mh, vh = m[j] / (1 - 0.9 ** t), v[j] / (1 - 0.999 ** t)
                    setattr(self, nome, getattr(self, nome) - PASSO * mh / (np.sqrt(vh) + 1e-8))
            if len(yc):
                p = _perdita(np.tanh(zc @ self.w1 + self.b1) @ self.w2 + self.b2, yc, wc)
                if p < migliore - 1e-5:
                    migliore, copia, fermo = p, (self.w1.copy(), self.b1.copy(), self.w2.copy(), float(self.b2)), 0
                else:
                    fermo += 1
                    if fermo >= PAZIENZA:
                        break
        if copia is not None:
            self.w1, self.b1, self.w2, self.b2 = copia

    def come_dati(self) -> dict:
        return {"media": self.media.tolist(), "scala": self.scala.tolist(), "w1": self.w1.tolist(),
                "b1": self.b1.tolist(), "w2": self.w2.tolist(), "b2": float(self.b2)}

    @classmethod
    def da_dati(cls, d: dict) -> "Rete":
        return cls(np.array(d["media"]), np.array(d["scala"]), np.array(d["w1"]), np.array(d["b1"]),
                   np.array(d["w2"]), float(d["b2"]))
