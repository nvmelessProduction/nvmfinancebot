"""Il Rischio: quanto mettere su questa operazione.

Regole in `spec/rischio.md`. Decide il bot, con le sue stime: dal Capo
arrivano la probabilita' del primo target (`p1`) e del secondo dopo il primo
(`q`); da Livelli le distanze dei target in R. Con quelle il Rischio sceglie
la frazione del conto che fa crescere di piu' il conto nel tempo (il
criterio di Kelly). Nessun tetto: le stime migliorano con l'addestramento.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

USCITE = ("due meta'", "primo target", "secondo target")


@dataclass(frozen=True)
class Esiti:
    """I possibili esiti di un'operazione, in R, con le loro probabilita'."""

    erre: tuple[float, ...]
    probabilita: tuple[float, ...]

    @property
    def atteso(self) -> float:
        return float(np.dot(self.erre, self.probabilita))


def esiti(p1: float, q: float, rr1: float, rr2: float, costi: float, uscita: str = USCITE[0]) -> Esiti:
    """Due meta' (una al primo target, l'altra al secondo con lo stop a pareggio),
    oppure tutta al primo target, oppure tutta al secondo con lo stop a pareggio."""
    vinte = {
        USCITE[0]: (0.5 * rr1, 0.5 * rr1 + 0.5 * rr2),
        USCITE[1]: (rr1, rr1),
        USCITE[2]: (0.0, rr2),
    }[uscita]
    return Esiti((-1.0 - costi, vinte[0] - costi, vinte[1] - costi), (1 - p1, p1 * (1 - q), p1 * q))


def crescita(e: Esiti, f: float) -> float:
    """La crescita attesa del conto (media del logaritmo) rischiando la frazione `f`."""
    x = np.array(e.erre)
    if f <= 0:
        return 0.0
    if np.any(1 + f * x <= 0):
        return -np.inf
    return float(np.dot(e.probabilita, np.log1p(f * x)))


def kelly(e: Esiti) -> float:
    """La frazione del conto da rischiare che fa crescere di piu' il conto."""
    if e.atteso <= 0:
        return 0.0
    x, p = np.array(e.erre), np.array(e.probabilita)
    tetto = 1.0 / -x.min() if x.min() < 0 else 1.0
    f = np.linspace(0, tetto * 0.999, 4000)
    valori = (p[None, :] * np.log1p(f[:, None] * x[None, :])).sum(axis=1)
    return float(f[int(np.argmax(valori))])


# Le parti del Kelly che il Rischio prova quando si addestra.
PARTI = np.round(np.arange(0.02, 1.0001, 0.02), 2)


def impara_parte(f: np.ndarray, r: np.ndarray) -> float:
    """Quanta parte del Kelly usare: quella che, sulle operazioni passate
    (puntata di Kelly `f` e risultato `r` in R, in ordine di tempo), ha fatto
    crescere di piu' il conto. Se il Capo sopravvaluta le sue stime, il
    Rischio impara a fidarsene meno; se le azzecca, a fidarsene di piu'."""
    f, r = np.asarray(f, float), np.asarray(r, float)
    if not len(f):
        return 1.0
    migliore, parte = -np.inf, PARTI[0]
    for p in PARTI:
        x = 1 + p * f * r
        g = -np.inf if np.any(x <= 0) else float(np.log(x).sum())
        if g > migliore:
            migliore, parte = g, p
    return float(parte)
