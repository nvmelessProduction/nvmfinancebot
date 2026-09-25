"""Il Capo: tutto considerato, conviene entrare?

Regole in `spec/capo.md`. Due regressioni logistiche: `p1`, la probabilita'
di arrivare al primo target prima dello stop, e `q`, quella di arrivare al
secondo dopo il primo. Si entra solo se il guadagno atteso

    E = p1 * (0.5 * RR1 + 0.5 * q * RR2) - (1 - p1) - costi

e' sopra zero. Il Capo vede solo le risposte degli agenti e i numeri del
piano, mai lo strumento; e ogni peso si legge.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence

import numpy as np

from nvm.agenti import inventate
from nvm.agenti.conferme import AllaRomeo, Contesto, KeyLevel, Liquidita, Orario
from nvm.prova.base import Risultato
from nvm.prova.campo import Uscita
from nvm.tempo import TF

COLONNE_BASE = (
    "key level: massimo preso", "key level: arriva al massimo", "key level: rejection block",
    "key level: fvg", "key level: non so",
    "ora 21-01", "ora 01-05", "ora 05-09", "ora 09-13", "ora 13-17",
    "bias range a favore", "bias range contro", "bias sopra a favore", "bias sopra contro",
    "secondo colpo", "terzo colpo",
    "coppia W1-H4", "coppia D1-H1",
    "RR1", "RR2", "stop su ampiezza",
    # Aggiunta il 24/09/2026 per il bot dal vivo: nello storico non ci sono i
    # 15 minuti di vent'anni, quindi il Capo su questa coppia impara dal vivo.
    "coppia H4-M15",
    # Le risposte alla Romeo (`spec/conferme.md`), aggiunte il 24/09/2026.
    "ora di Romeo: Londra", "ora di Romeo: New York", "dentro un CRT più grande", "a sconto sulla settimana",
    # La liquidita' presa dalla manipolazione (la terza gamba di Romeo), aggiunta il 25/09/2026.
    "liquidità presa prima", "liquidità presa sopra il CRT",
)
# Le domande che gli agenti hanno inventato e che la palestra ha tenuto
# (`nvm/agenti/inventate.py`): colonne in piu', dopo quelle di base.
INVENTATE = inventate.tenute()
COLONNE = COLONNE_BASE + tuple(f"💡 {d.agente}: {d.nome}" for d in INVENTATE)
# Penalita' L2, fissata nella scheda.
PENALITA = 1.0
# Dal vivo il Capo si riaddestra pesando di piu' i casi recenti: il peso di un
# caso si dimezza ogni EMIVITA_ANNI. Scelta addestrando sullo storico anno per
# anno (registro/tentativi.md, 24/09/2026): 1 anno ha fatto meglio di 2, 4, 8
# e di nessun peso.
EMIVITA_ANNI = 1.0
# La somiglianza a Romeo (`spec/capo.md`): la penalita' della sua regressione.
PENALITA_ROMEO = 10.0
# Le colonne che guarda la somiglianza a Romeo: solo le risposte alla Romeo e
# la liquidita' presa. Con tutte le colonne, fuori campione, riconosceva le sue
# scelte come il caso (registro/tentativi.md, 24/09/2026); con la liquidita'
# le riconosce meglio (25/09/2026).
COLONNE_ROMEO = tuple(range(22, 28))


def pesi_per_eta(quando: np.ndarray, adesso: int, emivita: float = EMIVITA_ANNI) -> np.ndarray:
    eta = np.maximum(adesso - np.asarray(quando, np.float64), 0) / (365.25 * 86400)
    w = 0.5 ** (eta / emivita)
    return w / w.mean()


def riga(r: Risultato, kl: Optional[KeyLevel], ora: Orario, ctx: Optional[Contesto],
         ar: Optional[AllaRomeo] = None, liq: Optional[Liquidita] = None,
         inv: Optional[Sequence[float]] = None) -> np.ndarray:
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
    x[21] = r.alto_tf is TF.H4
    if ar is not None:
        x[22:26] = ar.londra, ar.new_york, ar.annidato, bool(ar.sconto)
    if liq is not None:
        x[26:28] = liq.presa, liq.sopra_il_crt
    if inv is not None and len(inv):
        x[len(COLONNE_BASE):len(COLONNE_BASE) + len(inv)] = inv
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

    def allena(self, x: np.ndarray, y: np.ndarray, giri: int = 50, pesi: Optional[np.ndarray] = None) -> "Logistica":
        a = np.c_[np.ones(len(x)), x]
        c = np.ones(len(x)) if pesi is None else np.asarray(pesi, np.float64)
        w = np.zeros(a.shape[1])
        freno = np.full(a.shape[1], self.penalita)
        freno[0] = 0.0
        for _ in range(giri):
            p = 1 / (1 + np.exp(-(a @ w)))
            gradiente = a.T @ (c * (p - y)) + freno * w
            hessiana = (a * (c * p * (1 - p))[:, None]).T @ a + np.diag(freno) + 1e-9 * np.eye(len(w))
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
    # La somiglianza a Romeo (`spec/capo.md`, "Il Capo impara Romeo"): una
    # regressione imparata dalle sue entrate. E' un parere che l'equipe sente,
    # non un obbligo: il Capo decide col guadagno atteso.
    romeo: Optional[Logistica] = None
    romeo_media: Optional[np.ndarray] = None
    romeo_scala: Optional[np.ndarray] = None
    # La fiducia in Romeo: di quanto una somiglianza sopra la media alza la
    # stima del primo target (sul logaritmo delle quote). Non la sceglie
    # nessuno: il Capo la impara dai risultati, del 2023 e dal vivo.
    fiducia_in_romeo: float = 0.0
    romeo_logit_media: float = 0.0
    romeo_logit_scala: float = 1.0

    def _piena(self, x: np.ndarray) -> np.ndarray:
        return _con_interazioni(x, self.interazioni)

    @classmethod
    def allena(cls, x: np.ndarray, tp1: np.ndarray, tp2: np.ndarray,
               interazioni: tuple[tuple[int, int], ...] = (), pesi: Optional[np.ndarray] = None) -> "Capo":
        xp = _con_interazioni(x, interazioni)
        w = np.ones(len(x)) if pesi is None else np.asarray(pesi, np.float64)
        media = np.average(xp, axis=0, weights=w)
        scala = np.sqrt(np.average((xp - media) ** 2, axis=0, weights=w))
        scala[scala == 0] = 1.0
        z = (xp - media) / scala
        primo = Logistica().allena(z, tp1.astype(float), pesi=None if pesi is None else w)
        secondo = Logistica().allena(z[tp1], tp2[tp1].astype(float), pesi=None if pesi is None else w[tp1])
        return cls(media, scala, primo, secondo, tuple(tuple(c) for c in interazioni))

    def _z(self, x: np.ndarray) -> np.ndarray:
        return (self._piena(x) - self.media) / self.scala

    def valore_atteso(self, x: np.ndarray, rr1: np.ndarray, rr2: np.ndarray, costi: np.ndarray) -> np.ndarray:
        p1, q = self.probabilita(x)
        return p1 * (0.5 * rr1 + 0.5 * q * rr2) - (1 - p1) - costi

    def voce_di_romeo(self, x: np.ndarray) -> np.ndarray:
        """Quanto la somiglianza a Romeo sposta la stima del primo target, sul
        logaritmo delle quote: sopra zero spinge a entrare, sotto frena."""
        x = np.atleast_2d(x)
        if self.romeo is None or self.fiducia_in_romeo == 0:
            return np.zeros(len(x))
        return self.fiducia_in_romeo * self._romeo_z(x)

    def _romeo_z(self, x: np.ndarray) -> np.ndarray:
        s = np.clip(self.somiglianza(x), 1e-9, 1 - 1e-9)
        return (np.log(s / (1 - s)) - self.romeo_logit_media) / self.romeo_logit_scala

    def impara_fiducia(self, x: np.ndarray, tp1: np.ndarray) -> "Capo":
        """Lo stesso Capo, con la fiducia in Romeo imparata dai risultati: quanto,
        a parita' di tutto il resto, le operazioni che gli somigliano di piu'
        prendono davvero il primo target."""
        if self.romeo is None or len(x) == 0:
            return self
        s = np.clip(self.somiglianza(x), 1e-9, 1 - 1e-9)
        lg = np.log(s / (1 - s))
        media, scala = float(lg.mean()), float(lg.std()) or 1.0
        z = (lg - media) / scala
        base = self.primo.probabilita(self._z(x))
        base = np.clip(base, 1e-9, 1 - 1e-9)
        scarto = np.log(base / (1 - base))
        y = np.asarray(tp1, float)
        b = 0.0
        for _ in range(50):
            p = 1 / (1 + np.exp(-(scarto + b * z)))
            passo = (np.sum(z * (p - y)) + PENALITA * b) / (np.sum(z * z * p * (1 - p)) + PENALITA)
            b -= passo
            if abs(passo) < 1e-10:
                break
        return replace(self, fiducia_in_romeo=float(b), romeo_logit_media=media, romeo_logit_scala=scala)

    def somiglianza(self, x: np.ndarray) -> np.ndarray:
        """Quanto ogni operazione somiglia a una che Romeo prenderebbe, da 0 a 1.
        Senza la regressione di Romeo, 1: decide solo il guadagno atteso."""
        x = np.atleast_2d(x)
        if self.romeo is None:
            return np.ones(len(x))
        x = _di_romeo(x)
        return self.romeo.probabilita((x - self.romeo_media) / self.romeo_scala)

    def entra(self, x: np.ndarray, rr1: np.ndarray, rr2: np.ndarray, costi: np.ndarray) -> np.ndarray:
        """La decisione del Capo: entra se il guadagno atteso e' sopra zero."""
        return self.valore_atteso(x, rr1, rr2, costi) > 0

    def impara_romeo(self, x: np.ndarray, y: np.ndarray) -> "Capo":
        """Lo stesso Capo, che ha imparato dalle entrate di Romeo quanto
        un'operazione gli somiglia: `x` i candidati, `y` 1 per le scelte di Romeo."""
        xr = _di_romeo(x)
        media = xr.mean(axis=0)
        scala = xr.std(axis=0)
        scala[scala == 0] = 1.0
        romeo = Logistica(PENALITA_ROMEO).allena((xr - media) / scala, np.asarray(y, float))
        return replace(self, romeo=romeo, romeo_media=media, romeo_scala=scala)

    def fiducia_romeo(self) -> list[tuple[str, float]]:
        """I pesi della regressione di Romeo, colonna per colonna."""
        if self.romeo is None:
            return []
        return [(COLONNE[i], float(w)) for i, w in zip(COLONNE_ROMEO, self.romeo.pesi[1:])]

    def nomi(self) -> list[str]:
        return list(COLONNE) + [f"{COLONNE[i]} × {COLONNE[j]}" for i, j in self.interazioni]

    def fiducia(self) -> list[tuple[str, float, float]]:
        """Per ogni colonna, il peso nelle due regressioni (sulle colonne standardizzate)."""
        return [(n, float(a), float(b)) for n, a, b in zip(self.nomi(), self.primo.pesi[1:], self.secondo.pesi[1:])]

    def probabilita(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """p1 e q per ogni riga. La stima del primo target sente anche la voce di Romeo."""
        z = self._z(x)
        p1 = self.primo.probabilita(z)
        voce = self.voce_di_romeo(x)
        if voce.any():
            p1 = np.clip(p1, 1e-9, 1 - 1e-9)
            p1 = 1 / (1 + np.exp(-(np.log(p1 / (1 - p1)) + voce)))
        return p1, self.secondo.probabilita(z)

    def spinte(self, x: np.ndarray) -> np.ndarray:
        """Di quanto ogni colonna sposta la stima del primo target per questa riga
        (sul logaritmo delle quote): sopra zero spinge a entrare, sotto frena."""
        return self.primo.pesi[1:] * self._z(x[None])[0]

    def come_dati(self) -> dict:
        return {
            "colonne": list(COLONNE), "media": self.media.tolist(), "scala": self.scala.tolist(),
            "primo": self.primo.pesi.tolist(), "secondo": self.secondo.pesi.tolist(),
            "interazioni": [list(c) for c in self.interazioni],
            "romeo": None if self.romeo is None else {
                "pesi": self.romeo.pesi.tolist(), "media": self.romeo_media.tolist(),
                "scala": self.romeo_scala.tolist(), "fiducia": self.fiducia_in_romeo,
                "logit_media": self.romeo_logit_media, "logit_scala": self.romeo_logit_scala,
            },
        }

    @classmethod
    def da_dati(cls, d: dict) -> "Capo":
        if tuple(d["colonne"]) != COLONNE:
            raise ValueError("il Capo salvato ha colonne diverse da quelle di oggi: va riallenato")
        primo, secondo = Logistica(), Logistica()
        primo.pesi, secondo.pesi = np.array(d["primo"]), np.array(d["secondo"])
        capo = cls(np.array(d["media"]), np.array(d["scala"]), primo, secondo,
                   tuple(tuple(c) for c in d.get("interazioni", [])))
        r = d.get("romeo")
        if r and len(r["media"]) == len(COLONNE_ROMEO):
            capo.romeo = Logistica(PENALITA_ROMEO)
            capo.romeo.pesi = np.array(r["pesi"])
            capo.romeo_media, capo.romeo_scala = np.array(r["media"]), np.array(r["scala"])
            capo.fiducia_in_romeo = float(r.get("fiducia", 0.0))
            capo.romeo_logit_media = float(r.get("logit_media", 0.0))
            capo.romeo_logit_scala = float(r.get("logit_scala", 1.0))
        return capo


def _di_romeo(x: np.ndarray) -> np.ndarray:
    """Le colonne della somiglianza a Romeo; quelle che mancano (decisioni vecchie) valgono zero."""
    x = np.atleast_2d(np.asarray(x, float))
    if x.shape[1] < len(COLONNE):
        x = np.c_[x, np.zeros((len(x), len(COLONNE) - x.shape[1]))]
    return x[:, COLONNE_ROMEO]


def _con_interazioni(x: np.ndarray, interazioni) -> np.ndarray:
    if not interazioni:
        return x
    return np.c_[x, np.column_stack([x[:, i] * x[:, j] for i, j in interazioni])]
