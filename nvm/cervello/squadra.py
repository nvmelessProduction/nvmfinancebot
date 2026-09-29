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
from nvm.cervello.genoma import Genoma
from nvm.cervello.rete import PASSO, Rete
from nvm.cervello.viste import AGENTI

# In quante parti si divide la scuola per avere giudizi su esempi mai visti.
PARTI = 3
# Quanto si sposta il Capo dal vivo, a ogni risultato.
PASSO_CAPO = 0.02


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


def _rete_prima(v, y, pesi, a, i, genomi):
    g = (genomi or {}).get(a, Genoma())
    return Rete.allena(v[a], y, pesi, nascosti=g.neuroni, seme=i, penalita=g.freno, colonne=g.colonne(a))


def _rete_seconda(x, y, pesi, a, i, genomi, n_vista):
    """Il cervello del confronto: la sua vista (le parti che guarda) piu' i giudizi dei colleghi."""
    g = (genomi or {}).get(a, Genoma())
    colonne = g.colonne(a)
    if colonne is not None:
        colonne = np.r_[colonne, np.arange(n_vista, x.shape[1])]
    return Rete.allena(x, y, pesi, nascosti=g.neuroni, seme=10 + i, penalita=g.freno, colonne=colonne)


def _primi(v, y, pesi, genomi=None):
    reti = {a: _rete_prima(v, y, pesi, a, i, genomi) for i, a in enumerate(AGENTI)}
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
               parti: int = PARTI, genomi: Optional[dict] = None) -> "Squadra":
        """`v`: per agente, le sue viste (una riga per esempio, in ordine di tempo); `y`: primo
        obiettivo preso (0/1); `genomi`: com'e' fatto il cervello di ognuno (`genoma.py`)."""
        y = np.asarray(y, float)
        pesi = np.ones(len(y)) if pesi is None else np.asarray(pesi, float)
        primi_fuori = _fuori(v, y, pesi, parti, lambda vv, yy, ww: _primi(vv, yy, ww, genomi))
        primi = {a: _rete_prima(v, y, pesi, a, i, genomi) for i, a in enumerate(AGENTI)}
        if not confronto:
            capo = Logistica(1.0).allena(np.column_stack([primi_fuori[a] for a in AGENTI]), y, pesi=pesi)
            return cls(primi, {}, capo, False)

        def secondi_su(vv, yy, ww, gg):
            return {a: _rete_seconda(_con_colleghi(vv[a], gg, a), yy, ww, a, i, genomi, vv[a].shape[1])
                    for i, a in enumerate(AGENTI)}

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

    def larghezza(self, a: str) -> int:
        """Quanti numeri della vista di `a` conoscono i suoi cervelli: quelli della vista con cui
        sono nati."""
        altri = len(AGENTI) - 1
        s = self.secondi.get(a) if self.confronto else None
        if s is not None:
            # Nel confronto, dopo la vista vengono i giudizi dei colleghi.
            return int(s.colonne[-altri]) if s.colonne is not None else len(s.media) - altri
        p = self.primi[a]
        return len(p.media) if p.colonne is None else int(p.colonne.max()) + 1

    def adatta(self, v: dict) -> dict:
        """Gli occhi nuovi si aggiungono in fondo alla vista: cervelli nati prima guardano solo i
        numeri che conoscono, e in un esempio salvato prima, piu' corto, quelli che mancano valgono
        zero."""
        fuori = {}
        for a in AGENTI:
            x, n = np.atleast_2d(np.asarray(v[a], float)), self.larghezza(a)
            fuori[a] = x[:, :n] if x.shape[1] >= n else np.pad(x, ((0, 0), (0, n - x.shape[1])))
        return fuori

    def giudica(self, v: dict) -> tuple[dict, dict, np.ndarray]:
        """Il primo giro, il confronto e la probabilita' del primo obiettivo per il Capo."""
        v = self.adatta(v)
        primo = {a: self.primi[a].logit(v[a]) for a in AGENTI}
        if not self.confronto:
            return primo, primo, self.capo.probabilita(np.column_stack([primo[a] for a in AGENTI]))
        dopo = {a: self.secondi[a].logit(_con_colleghi(v[a], primo, a)) for a in AGENTI}
        return primo, dopo, self.capo.probabilita(np.column_stack([dopo[a] for a in AGENTI]))


    # --- Dal vivo ------------------------------------------------------------------------------

    def chi_ha_convinto(self, v: dict) -> dict[str, tuple[str, float]]:
        """Per ogni agente, il collega che nel confronto gli ha fatto cambiare idea di piu', e di
        quanto (sul logaritmo delle quote): il suo giudizio rifatto senza quel collega (al posto
        del suo parere, un parere neutro) meno quello vero."""
        if not self.confronto:
            return {}
        v = self.adatta(v)
        primo = {a: self.primi[a].logit(v[a]) for a in AGENTI}
        fuori = {}
        for a in AGENTI:
            vero = self.secondi[a].logit(_con_colleghi(v[a], primo, a))
            effetti = {}
            for b in AGENTI:
                if b == a:
                    continue
                neutro = dict(primo)
                neutro[b] = np.zeros_like(primo[b])
                effetti[b] = float((vero - self.secondi[a].logit(_con_colleghi(v[a], neutro, a)))[0])
            chi = max(effetti, key=lambda b: abs(effetti[b]))
            fuori[a] = (chi, effetti[chi])
        return fuori

    def aggiorna(self, v: dict, y: np.ndarray, pesi: Optional[np.ndarray] = None, passi: int = 3,
                 passo: float = PASSO / 3) -> "Squadra":
        """Dal vivo, dopo ogni operazione finita: ogni cervello impara dal risultato vero, di
        `passo` in `passo` (`esperienza.py` mescola la lezione con i ricordi da ripassare)."""
        y = np.atleast_1d(np.asarray(y, float))
        w = np.ones(len(y)) if pesi is None else np.atleast_1d(np.asarray(pesi, float))
        v = self.adatta(v)
        primo = {a: self.primi[a].logit(v[a]) for a in AGENTI}
        for a in AGENTI:
            self.primi[a].aggiorna(v[a], y, passi=passi, passo=passo, pesi=w)
            if self.confronto:
                self.secondi[a].aggiorna(_con_colleghi(v[a], primo, a), y, passi=passi, passo=passo, pesi=w)
        # Anche il Capo impara quanto fidarsi di ognuno, dal risultato della squadra.
        for _ in range(passi):
            primo = {a: self.primi[a].logit(v[a]) for a in AGENTI}
            giudizi = ({a: self.secondi[a].logit(_con_colleghi(v[a], primo, a)) for a in AGENTI}
                       if self.confronto else primo)
            z = np.column_stack([giudizi[a] for a in AGENTI])
            d = w * (self.capo.probabilita(z) - y) / np.sum(w)
            # Il Capo mette insieme giudizi grandi: si sposta piano, o rovina quello che la squadra sa.
            self.capo.pesi = self.capo.pesi - min(PASSO_CAPO, passo / 15) * np.r_[d.sum(), z.T @ d]
        return self

    def come_dati(self) -> dict:
        return {"confronto": self.confronto, "primi": {a: r.come_dati() for a, r in self.primi.items()},
                "secondi": {a: r.come_dati() for a, r in self.secondi.items()},
                "capo": self.capo.pesi.tolist()}

    @classmethod
    def da_dati(cls, d: dict) -> "Squadra":
        capo = Logistica(1.0)
        capo.pesi = np.array(d["capo"])
        return cls({a: Rete.da_dati(x) for a, x in d["primi"].items()},
                   {a: Rete.da_dati(x) for a, x in d["secondi"].items()}, capo, bool(d["confronto"]))
