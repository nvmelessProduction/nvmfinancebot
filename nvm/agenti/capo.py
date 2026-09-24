"""Il Capo: tutto considerato, conviene entrare?

Regole in `spec/capo.md`. Due regressioni logistiche: `p1`, la probabilita'
di arrivare al primo target prima dello stop, e `q`, quella di arrivare al
secondo dopo il primo. Si entra solo se il guadagno atteso

    E = p1 * (0.5 * RR1 + 0.5 * q * RR2) - (1 - p1) - costi

e' sopra zero. Il Capo vede solo le risposte degli agenti e i numeri del
piano, mai lo strumento; e ogni peso si legge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.conferme import Contesto, KeyLevel, Orario
from nvm.prova.base import Risultato
from nvm.prova.campo import Uscita
from nvm.tempo import TF

COLONNE = (
    "key level: massimo preso", "key level: arriva al massimo", "key level: rejection block",
    "key level: fvg", "key level: non so",
    "ora 21-01", "ora 01-05", "ora 05-09", "ora 09-13", "ora 13-17",
    "bias range a favore", "bias range contro", "bias sopra a favore", "bias sopra contro",
    "secondo colpo", "terzo colpo",
    "coppia W1-H4", "coppia D1-H1",
    "RR1", "RR2", "stop su ampiezza",
)
# Penalita' L2, fissata nella scheda.
PENALITA = 1.0


def riga(r: Risultato, kl: Optional[KeyLevel], ora: Orario, ctx: Optional[Contesto]) -> np.ndarray:
    """Le colonne del Capo per un'operazione, nell'ordine di `COLONNE`."""
    x = np.zeros(len(COLONNE))
    if kl is None:
        x[4] = 1
    else:
        x[0:4] = kl.massimo, kl.tocca, kl.rejection_block, kl.fvg
    fascia = ((ora.ora_scatto - 17) % 24) // 4  # 0 = 17-21 di New York
    if fascia:
        x[4 + fascia] = 1
    if ctx is not None:
        for k, b in ((10, ctx.range), (12, ctx.sopra)):
            lato = Contesto.dalla_parte(b, r.verso)
            if lato is not None:
                x[k if lato else k + 1] = 1
    if r.colpo >= 2:
        x[14 if r.colpo == 2 else 15] = 1
    x[16] = r.alto_tf is TF.W1
    x[17] = r.alto_tf is TF.D1
    x[18:21] = r.rr1, r.rr2, r.stop_su_ampiezza
    return x


def esiti(r: Risultato) -> tuple[bool, bool]:
    """Primo target preso, secondo target preso. Tutti e due nella stessa
    candela contano come tutti e due."""
    target = r.uscita is Uscita.TARGET
    return r.tp1_preso or target, target


class Logistica:
    """Regressione logistica con penalita' L2 (non sull'intercetta), col metodo di Newton."""

    def __init__(self, penalita: float = PENALITA):
        self.penalita = penalita
        self.pesi = np.zeros(0)

    def allena(self, x: np.ndarray, y: np.ndarray, giri: int = 50) -> "Logistica":
        a = np.c_[np.ones(len(x)), x]
        w = np.zeros(a.shape[1])
        freno = np.full(a.shape[1], self.penalita)
        freno[0] = 0.0
        for _ in range(giri):
            p = 1 / (1 + np.exp(-(a @ w)))
            gradiente = a.T @ (p - y) + freno * w
            hessiana = (a * (p * (1 - p))[:, None]).T @ a + np.diag(freno) + 1e-9 * np.eye(len(w))
            passo = np.linalg.solve(hessiana, gradiente)
            w -= passo
            if np.abs(passo).max() < 1e-8:
                break
        self.pesi = w
        return self

    def probabilita(self, x: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-(self.pesi[0] + x @ self.pesi[1:])))


@dataclass
class Capo:
    media: np.ndarray
    scala: np.ndarray
    primo: Logistica
    secondo: Logistica
    # Le combinazioni di due colonne che il Capo prova, nate dai consigli fra
    # agenti nella riunione: il prodotto delle due colonne diventa una colonna in piu'.
    interazioni: tuple[tuple[int, int], ...] = ()

    def _piena(self, x: np.ndarray) -> np.ndarray:
        return _con_interazioni(x, self.interazioni)

    @classmethod
    def allena(cls, x: np.ndarray, tp1: np.ndarray, tp2: np.ndarray,
               interazioni: tuple[tuple[int, int], ...] = ()) -> "Capo":
        xp = _con_interazioni(x, interazioni)
        media = xp.mean(axis=0)
        scala = xp.std(axis=0)
        scala[scala == 0] = 1.0
        z = (xp - media) / scala
        primo = Logistica().allena(z, tp1.astype(float))
        secondo = Logistica().allena(z[tp1], tp2[tp1].astype(float))
        return cls(media, scala, primo, secondo, tuple(tuple(c) for c in interazioni))

    def _z(self, x: np.ndarray) -> np.ndarray:
        return (self._piena(x) - self.media) / self.scala

    def valore_atteso(self, x: np.ndarray, rr1: np.ndarray, rr2: np.ndarray, costi: np.ndarray) -> np.ndarray:
        z = self._z(x)
        p1, q = self.primo.probabilita(z), self.secondo.probabilita(z)
        return p1 * (0.5 * rr1 + 0.5 * q * rr2) - (1 - p1) - costi

    def nomi(self) -> list[str]:
        return list(COLONNE) + [f"{COLONNE[i]} × {COLONNE[j]}" for i, j in self.interazioni]

    def fiducia(self) -> list[tuple[str, float, float]]:
        """Per ogni colonna, il peso nelle due regressioni (sulle colonne standardizzate)."""
        return [(n, float(a), float(b)) for n, a, b in zip(self.nomi(), self.primo.pesi[1:], self.secondo.pesi[1:])]

    def probabilita(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """p1 e q per ogni riga."""
        z = self._z(x)
        return self.primo.probabilita(z), self.secondo.probabilita(z)

    def spinte(self, x: np.ndarray) -> np.ndarray:
        """Di quanto ogni colonna sposta la stima del primo target per questa riga
        (sul logaritmo delle quote): sopra zero spinge a entrare, sotto frena."""
        return self.primo.pesi[1:] * self._z(x[None])[0]

    def come_dati(self) -> dict:
        return {
            "colonne": list(COLONNE), "media": self.media.tolist(), "scala": self.scala.tolist(),
            "primo": self.primo.pesi.tolist(), "secondo": self.secondo.pesi.tolist(),
            "interazioni": [list(c) for c in self.interazioni],
        }

    @classmethod
    def da_dati(cls, d: dict) -> "Capo":
        if tuple(d["colonne"]) != COLONNE:
            raise ValueError("il Capo salvato ha colonne diverse da quelle di oggi: va riallenato")
        primo, secondo = Logistica(), Logistica()
        primo.pesi, secondo.pesi = np.array(d["primo"]), np.array(d["secondo"])
        return cls(np.array(d["media"]), np.array(d["scala"]), primo, secondo,
                   tuple(tuple(c) for c in d.get("interazioni", [])))


def _con_interazioni(x: np.ndarray, interazioni) -> np.ndarray:
    if not interazioni:
        return x
    return np.c_[x, np.column_stack([x[:, i] * x[:, j] for i, j in interazioni])]
