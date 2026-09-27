"""La squadra dei cervelli: ognuno giudica, poi si confrontano, poi il Capo decide.

1. **Primo giro.** Ogni agente guarda il mercato nel suo campo (`viste.py`) e il suo cervello
   (`rete.py`) dice quanto crede che l'operazione arrivi al primo obiettivo.
2. **Il confronto.** Ogni agente sente i giudizi dei colleghi e rivede il suo: il secondo
   cervello di ogni agente riceve quello che vede lui piu' quello che dicono gli altri, e ha
   imparato a scuola quando conviene cambiare idea e quando tenere il punto.
3. **Il Capo** mette insieme i giudizi dopo il confronto: ha imparato quanto fidarsi di
   ognuno.

A scuola ogni pezzo impara solo da esempi che non ha usato per allenare i pezzi prima di lui
(i giudizi dei colleghi che un agente sente sono quelli su esempi che quei colleghi non
avevano visto), come succede dal vivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from nvm.agenti.capo import Logistica
from nvm.cervello.rete import Rete
from nvm.cervello.viste import AGENTI

# In quante parti si divide la scuola per avere giudizi su esempi mai visti.
PARTI = 3


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _fuori(v: dict, y, pesi, parti, allena):
    """Per ogni esempio, il giudizio di un cervello allenato sulle altre parti."""
    n = len(y)
    fuori = {a: np.zeros(n) for a in v}
    blocchi = np.array_split(np.arange(n), parti)
    for b in blocchi:
        resto = np.setdiff1d(np.arange(n), b)
        for a, g in allena({k: x[resto] for k, x in v.items()}, y[resto], pesi[resto]).items():
            fuori[a][b] = g({k: x[b] for k, x in v.items()})
    return fuori


def _primi(v, y, pesi):
    reti = {a: Rete.allena(v[a], y, pesi, seme=i) for i, a in enumerate(AGENTI)}
    return {a: (lambda vv, a=a: reti[a].logit(vv[a])) for a in AGENTI}


def _con_colleghi(vista: np.ndarray, giudizi: dict, a: str) -> np.ndarray:
    return np.c_[vista, np.column_stack([giudizi[b] for b in AGENTI if b != a])]


@dataclass
class Squadra:
    primi: dict                      # agente -> Rete del primo giro
    secondi: dict                    # agente -> Rete del confronto (vista + giudizi dei colleghi)
    capo: Logistica                  # come il Capo mette insieme i giudizi dopo il confronto
    confronto: bool = True
    storia: list = field(default_factory=list)

    @classmethod
    def allena(cls, v: dict, y: np.ndarray, pesi: Optional[np.ndarray] = None, confronto: bool = True,
               parti: int = PARTI) -> "Squadra":
        """`v`: per agente, le sue viste (una riga per esempio, in ordine di tempo); `y`: primo
        obiettivo preso (0/1)."""
        y = np.asarray(y, float)
        pesi = np.ones(len(y)) if pesi is None else np.asarray(pesi, float)
        primi_fuori = _fuori(v, y, pesi, parti, _primi)
        primi = {a: Rete.allena(v[a], y, pesi, seme=i) for i, a in enumerate(AGENTI)}
        if not confronto:
            capo = Logistica(1.0).allena(np.column_stack([primi_fuori[a] for a in AGENTI]), y, pesi=pesi)
            return cls(primi, {}, capo, False)

        def secondi_su(vv, yy, ww, gg):
            return {a: Rete.allena(_con_colleghi(vv[a], gg, a), yy, ww, seme=10 + i) for i, a in enumerate(AGENTI)}

        # Il confronto a scuola: ogni agente sente i giudizi dei colleghi su esempi che loro non avevano visto.
        n = len(y)
        secondi_fuori = {a: np.zeros(n) for a in AGENTI}
        for b in np.array_split(np.arange(n), parti):
            resto = np.setdiff1d(np.arange(n), b)
            reti = secondi_su({k: x[resto] for k, x in v.items()}, y[resto], pesi[resto],
                              {k: g[resto] for k, g in primi_fuori.items()})
            for a in AGENTI:
                secondi_fuori[a][b] = reti[a].logit(_con_colleghi(v[a][b], {k: g[b] for k, g in primi_fuori.items()}, a))
        secondi = secondi_su(v, y, pesi, primi_fuori)
        capo = Logistica(1.0).allena(np.column_stack([secondi_fuori[a] for a in AGENTI]), y, pesi=pesi)
        return cls(primi, secondi, capo, True)

    def giudica(self, v: dict) -> tuple[dict, dict, np.ndarray]:
        """Il primo giro, il confronto e la probabilita' del primo obiettivo per il Capo."""
        primo = {a: self.primi[a].logit(v[a]) for a in AGENTI}
        if not self.confronto:
            return primo, primo, self.capo.probabilita(np.column_stack([primo[a] for a in AGENTI]))
        dopo = {a: self.secondi[a].logit(_con_colleghi(v[a], primo, a)) for a in AGENTI}
        return primo, dopo, self.capo.probabilita(np.column_stack([dopo[a] for a in AGENTI]))
