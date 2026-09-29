"""Imparare da ogni esperienza, come una persona.

Quando un'occasione finisce e si sa com'e' andata, la squadra impara subito:

1. **la lezione pesa di piu' quando si era sicuri e si e' sbagliato** (la sorpresa), e quando
   l'operazione ha mosso tanto;
2. **ripassa quello che sa gia'**: ogni passo mescola la lezione nuova con ricordi di scuola
   (`ricordi.npz`, casi dei vent'anni) e con le esperienze vissute prima, cosi' impara la cosa
   nuova senza dimenticare il resto. Piu' esperienze vive ha, piu' contano rispetto alla scuola
   (fino al 70% del ripasso): un errore che si ripete si somma e cambia davvero il cervello;
3. **si controlla**: se dopo la lezione sbaglia di piu' sui ricordi di controllo, torna indietro
   e riprova piu' piano; se sbaglia ancora, la lezione non resta (meglio non imparare che
   impazzire).

La squadra dopo ogni esperienza si salva (`dal_vivo.py`), e non si perde quando il bot riparte.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI

# Passi di studio per ogni esperienza, quanti ricordi si ripassano a ogni passo, quanto e' lungo
# un passo, e quanto puo' peggiorare sui ricordi di controllo prima di tornare indietro.
PASSI = 12
LOTTO = 128
PASSO = 0.03
TOLLERANZA = 0.01
# La parte di ogni passo che va alla lezione nuova: da meta' (nessuna sorpresa) al doppio.
QUOTA = 0.1
CONTROLLO = 400
# Quanto del ripasso va alle esperienze vissute: cresce con quante sono, fino a VISSUTE_MAX.
VISSUTE_MAX = 0.7
VISSUTE_PIENE = 500


@dataclass
class Memoria:
    """Esempi da ripassare: cosa vedeva ogni agente, se l'operazione ha guadagnato, quanto pesa."""

    viste: dict
    y: np.ndarray
    w: np.ndarray

    @classmethod
    def vuota(cls) -> "Memoria":
        return cls({a: np.zeros((0, 0)) for a in AGENTI}, np.zeros(0), np.zeros(0))

    def __len__(self) -> int:
        return len(self.y)

    def aggiungi(self, v: dict, y: float, w: float) -> None:
        for a in AGENTI:
            x = np.atleast_2d(np.asarray(v[a], float))
            self.viste[a] = x if not len(self.viste[a]) else np.vstack([self.viste[a], x])
        self.y = np.r_[self.y, float(y)]
        self.w = np.r_[self.w, float(w)]

    def adattata(self, squadra: Squadra) -> "Memoria":
        return Memoria(squadra.adatta(self.viste) if len(self) else dict(self.viste), self.y, self.w)

    def salva(self, file: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(file, y=self.y, w=self.w, **{f"vista {a}": self.viste[a].astype(np.float32) for a in AGENTI})

    @classmethod
    def carica(cls, file: Path) -> "Memoria":
        if not file.exists():
            return cls.vuota()
        d = np.load(file)
        return cls({a: d[f"vista {a}"].astype(float) for a in AGENTI}, d["y"].astype(float), d["w"].astype(float))


def ricordi_di_scuola(viste: dict, y: np.ndarray, w: np.ndarray, quanti: int = 2000, seme: int = 0) -> Memoria:
    """I ricordi che il bot porta con se' dalla scuola: casi dei vent'anni, piu' spesso i recenti e
    quelli che pesano (`w` gia' con l'eta')."""
    rng = np.random.default_rng(seme)
    p = w / w.sum() if w.sum() > 0 else None
    i = np.sort(rng.choice(len(y), size=min(quanti, len(y)), replace=False, p=p))
    return Memoria({a: np.asarray(viste[a])[i] for a in AGENTI}, np.asarray(y)[i].astype(float), np.ones(len(i)))


def perdita(squadra: Squadra, m: Memoria) -> float:
    """Quanto sbaglia la squadra su questi esempi (log-loss pesata)."""
    if not len(m):
        return 0.0
    p = np.clip(squadra.giudica(m.viste)[2], 1e-6, 1 - 1e-6)
    return float(-np.sum(m.w * (m.y * np.log(p) + (1 - m.y) * np.log(1 - p))) / np.sum(m.w))


def impara(squadra: Squadra, vista: dict, y: float, w: float, ricordi: Memoria, vissute: Memoria,
           seme: int) -> dict:
    """Una esperienza finita: la squadra impara la lezione ripassando, e si controlla. Restituisce
    com'e' andata: la sorpresa, la fiducia prima e dopo sullo stesso caso, se la lezione e' rimasta."""
    rng = np.random.default_rng(seme)
    v = squadra.adatta(vista)
    ricordi, vissute = ricordi.adattata(squadra), vissute.adattata(squadra)
    prima = float(squadra.giudica(v)[2][0])
    sorpresa = abs(float(y) - prima)
    quanto_vissute = VISSUTE_MAX * min(len(vissute) / VISSUTE_PIENE, 1.0) if len(ricordi) else 1.0
    controlli = [(1 - quanto_vissute, _pezzo(ricordi, slice(0, CONTROLLO))),
                 (quanto_vissute, _pezzo(vissute, slice(max(0, len(vissute) - CONTROLLO), len(vissute))))]
    sbagli = _perdita_mista(squadra, controlli)
    quota = min(0.5, QUOTA * (0.5 + sorpresa) * np.sqrt(min(max(w, 0.05), 4.0)))
    stato = squadra.come_dati()
    tenuta = False
    for passo in (PASSO, PASSO / 3):
        for _ in range(PASSI):
            lotto, yy, ww = _lotto(rng, ricordi, vissute, quanto_vissute)
            lotto = {a: np.vstack([v[a], lotto[a]]) for a in AGENTI} if len(yy) else v
            yy = np.r_[float(y), yy]
            ww = np.r_[quota, ww * (1 - quota)] if len(ww) else np.array([1.0])
            squadra.aggiorna(lotto, yy, ww, passi=1, passo=passo)
        dopo = _perdita_mista(squadra, controlli)
        if np.isfinite(dopo) and np.all(np.isfinite(squadra.giudica(v)[2])) and dopo <= sbagli * (1 + TOLLERANZA) + 1e-9:
            tenuta = True
            break
        _ripristina(squadra, stato)
    return {"prima": prima, "dopo": float(squadra.giudica(v)[2][0]), "sorpresa": sorpresa, "tenuta": tenuta}


def _pezzo(m: Memoria, quali) -> Memoria:
    return Memoria({a: x[quali] for a, x in m.viste.items()}, m.y[quali], m.w[quali]) if len(m) else m


def _perdita_mista(squadra: Squadra, controlli: list) -> float:
    return sum(peso * perdita(squadra, m) for peso, m in controlli if peso > 0 and len(m))


def _lotto(rng, ricordi: Memoria, vissute: Memoria, quanto_vissute: float) -> tuple[dict, np.ndarray, np.ndarray]:
    """I ricordi da ripassare in un passo: una parte dalla scuola, una dalle esperienze vissute;
    i pesi sommano a uno."""
    pezzi = []
    for m, parte in ((ricordi, 1 - quanto_vissute), (vissute, quanto_vissute)):
        k = int(round(LOTTO * parte))
        if k and len(m):
            i = rng.integers(0, len(m), k)
            pezzi.append(({a: m.viste[a][i] for a in AGENTI}, m.y[i], m.w[i] / max(m.w[i].sum(), 1e-12) * parte))
    if not pezzi:
        return {a: np.zeros((0, 0)) for a in AGENTI}, np.zeros(0), np.zeros(0)
    viste = {a: np.vstack([p[0][a] for p in pezzi]) for a in AGENTI}
    ww = np.concatenate([p[2] for p in pezzi])
    return viste, np.concatenate([p[1] for p in pezzi]), ww / ww.sum()


def _ripristina(squadra: Squadra, stato: dict) -> None:
    r = Squadra.da_dati(stato)
    squadra.primi, squadra.secondi, squadra.capo = r.primi, r.secondi, r.capo


def ricordi_del_bot(file: Optional[Path]) -> Memoria:
    return Memoria.carica(file) if file is not None else Memoria.vuota()
