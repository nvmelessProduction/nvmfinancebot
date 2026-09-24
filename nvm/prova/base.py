"""La base (Fase D): prendere tutti i CRT col manuale, e vedere quanto rendono.

Cacciatore -> Grilletto -> Livelli -> campo di prova, per ogni CRT. Il
numero che esce e' quello da battere (`PIANO.md` §3).

L'intervallo di confidenza si calcola **a blocchi di una settimana**: due
operazioni della stessa settimana, anche su strumenti diversi, spesso sono
la stessa scommessa (sul dollaro, per esempio) e contarle come due prove
indipendenti farebbe sembrare il risultato piu' sicuro di quanto e'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Variante, Verso, caccia
from nvm.agenti.grilletto import Scatto, scatto
from nvm.agenti.livelli import piano, scadenza
from nvm.dati.candele import Candele
from nvm.prova.campo import Uscita, simula
from nvm.tempo import TF

SETTIMANA = 7 * 86400


@dataclass
class Risultato:
    strumento: str
    alto_tf: TF
    basso_tf: TF
    verso: Verso
    quando: int
    erre: float
    uscita: Uscita
    tp1_preso: bool
    costo_erre: float
    rischio: float
    # Lo scatto da cui e' nata: le Conferme rispondono su questo.
    scatto: Optional[Scatto] = field(default=None, repr=False, compare=False)
    # Per il Capo: quale colpo sul CRT (1, 2, 3), i target in R, lo stop in
    # proporzione all'ampiezza del CRT, e quando l'operazione si e' chiusa.
    colpo: int = 1
    rr1: float = 0.0
    rr2: float = 0.0
    stop_su_ampiezza: float = 0.0
    chiusa_quando: int = 0


# Quante volte il Grilletto puo' sparare sullo stesso CRT: dopo la prima,
# solo dopo uno stop e con un turtle soup nuovo (`spec/grilletto.md`). La
# candela che prende lo stop puo' essere lei stessa il turtle soup nuovo: e'
# la spinta che spazza e poi crolla ("one last turtle soup", il KOD).
COLPI_PER_CRT = 3


def opera(
    alte: Candele, basse: Candele, dal: int, al: int,
    variante: Variante = Variante.MANUALE, stop_stretto: bool = False,
) -> list[Risultato]:
    """Tutte le operazioni del manuale con ingresso in [dal, al)."""
    risultati = []
    for crt in caccia(alte, basse, variante):
        dopo = None
        for colpo in range(1, COLPI_PER_CRT + 1):
            s = scatto(crt, basse, dopo)
            if s is None:
                break
            op = piano(s, basse, stop_stretto=stop_stretto)
            if op is None:
                break
            esito = simula(op, basse, scadenza(s))
            if dal <= s.quando < al:
                risultati.append(Risultato(
                    op.strumento, alte.tf, basse.tf, op.verso, op.quando, esito.erre,
                    esito.uscita, esito.tp1_preso, esito.costo_erre, op.rischio, s,
                    colpo=colpo,
                    rr1=abs(op.tp1 - op.ingresso) / op.rischio,
                    rr2=abs(op.tp2 - op.ingresso) / op.rischio,
                    stop_su_ampiezza=op.rischio / (crt.crt_high - crt.crt_low),
                    chiusa_quando=esito.quando,
                ))
            if esito.uscita is not Uscita.STOP:
                break
            # Il turtle soup nuovo puo' cominciare dalla candela dello stop.
            dopo = int(basse.inizio[int(np.searchsorted(basse.fine, esito.quando))])
    risultati.sort(key=lambda r: r.quando)
    return risultati


@dataclass
class Riassunto:
    n: int
    settimane: int
    media: float
    basso: float
    alto: float
    vincenti: float
    per_anno: dict[int, tuple[int, float]]

    def testo(self) -> str:
        if not self.n:
            return "nessuna operazione"
        anni = "  ".join(f"{a}:{m:+.2f}({k})" for a, (k, m) in sorted(self.per_anno.items()))
        return (
            f"n={self.n} ({self.settimane} settimane)  R medio {self.media:+.3f}  "
            f"IC95 [{self.basso:+.3f}, {self.alto:+.3f}]  in utile {self.vincenti:.0%}\n  per anno: {anni}"
        )


def riassumi(risultati: list[Risultato], ripetizioni: int = 4000, seme: int = 0) -> Riassunto:
    if not risultati:
        return Riassunto(0, 0, float("nan"), float("nan"), float("nan"), float("nan"), {})
    erre = np.array([r.erre for r in risultati])
    settimana = np.array([r.quando // SETTIMANA for r in risultati])
    uniche, gruppo = np.unique(settimana, return_inverse=True)
    somme = np.bincount(gruppo, weights=erre)
    conteggi = np.bincount(gruppo)
    rng = np.random.default_rng(seme)
    scelte = rng.integers(0, len(uniche), size=(ripetizioni, len(uniche)))
    medie = somme[scelte].sum(axis=1) / conteggi[scelte].sum(axis=1)
    anni: dict[int, list[float]] = {}
    for r in risultati:
        anni.setdefault(datetime.fromtimestamp(r.quando, tz=timezone.utc).year, []).append(r.erre)
    return Riassunto(
        n=len(erre), settimane=len(uniche), media=float(erre.mean()),
        basso=float(np.percentile(medie, 2.5)), alto=float(np.percentile(medie, 97.5)),
        vincenti=float((erre > 0).mean()),
        per_anno={a: (len(v), float(np.mean(v))) for a, v in anni.items()},
    )
