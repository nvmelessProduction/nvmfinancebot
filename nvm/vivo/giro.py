"""Il giro di ogni ora: con le orarie chiuse fino ad adesso, cosa dice l'equipe.

E' la stessa catena delle prove sullo storico (`nvm/prova/base.opera`, con la
configurazione 1: manuale, stop all'estremo), chiamata sui soli dati gia'
chiusi. Per questo il bot dal vivo decide come avrebbe deciso sullo storico:
`tests/test_vivo.py` lo controlla ora per ora.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.capo import Capo, riga
from nvm.agenti.conferme import SOPRA, Contesto, KeyLevel, Orario, contesto, key_level, orario
from nvm.agenti.livelli import piano, scadenza
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import Risultato, opera
from nvm.prova.campo import Operazione
from nvm.tempo import TF

COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))


@dataclass
class Decisione:
    r: Risultato
    op: Operazione
    scadenza: int
    key_level: Optional[KeyLevel]
    orario: Orario
    contesto: Optional[Contesto]
    p1: float
    q: float
    atteso: float
    # Le colonne del Capo per questa decisione: servono al riaddestramento.
    x: np.ndarray

    @property
    def entra(self) -> bool:
        return self.atteso > 0

    @property
    def chiave(self) -> str:
        r = self.r
        return f"{r.strumento} {r.alto_tf.value}-{r.basso_tf.value} {r.verso.value} {r.quando} colpo {r.colpo}"


def giro(basi: dict[str, Minuti], dal: int, adesso: int, capo: Capo) -> list[Decisione]:
    """Le decisioni con lo scatto in [dal, adesso], su candele chiuse entro `adesso`."""
    decisioni = []
    for strumento, base in basi.items():
        if not len(base):
            continue
        for alto, basso in COPPIE:
            alte = costruisci(base, alto).chiuse_entro(adesso)
            basse = costruisci(base, basso).chiuse_entro(adesso)
            sopra = costruisci(base, SOPRA[alto]).chiuse_entro(adesso)
            for r in opera(alte, basse, dal, adesso + 1):
                op = piano(r.scatto, basse)
                kl, ora, ctx = key_level(r.scatto, sopra, basse), orario(r.scatto, basse), contesto(r.scatto, alte, sopra)
                x = riga(r, kl, ora, ctx)[None]
                p1, q = capo.probabilita(x)
                atteso = capo.valore_atteso(x, np.array([r.rr1]), np.array([r.rr2]), np.array([r.costo_erre]))
                decisioni.append(Decisione(
                    r, op, scadenza(r.scatto), kl, ora, ctx, float(p1[0]), float(q[0]), float(atteso[0]), x[0]))
    decisioni.sort(key=lambda d: (d.r.quando, d.r.strumento))
    return decisioni
