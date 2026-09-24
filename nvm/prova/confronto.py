"""Una conferma contro la base (Fase E): le operazioni col si' rendono di piu'?

Si divide la base in due, si' e no, e si guarda la differenza fra le due
medie. L'intervallo si calcola a blocchi di una settimana, come per la base
(`nvm.prova.base`): si ripescano settimane intere, con dentro sia i si'
sia i no. Poi si conta in quanti anni la differenza ha il segno di quella
totale: il cancello chiede almeno l'80% (`PIANO.md` §2).

Qui si misura e basta. Se tenere la conferma, e quanto pesarla, lo decide
il Capo nella Fase F, anno per anno, senza guardare avanti.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from nvm.prova.base import SETTIMANA, Risultato


@dataclass
class Confronto:
    n_si: int
    n_no: int
    media_si: float
    media_no: float
    differenza: float
    basso: float
    alto: float
    anni_concordi: float
    anni: int

    def testo(self) -> str:
        if not self.n_si or not self.n_no:
            return f"si' {self.n_si}, no {self.n_no}: non si confronta"
        quota = self.n_si / (self.n_si + self.n_no)
        return (
            f"si' {self.n_si} ({quota:.0%}) {self.media_si:+.3f}R  no {self.n_no} {self.media_no:+.3f}R  "
            f"differenza {self.differenza:+.3f} IC95 [{self.basso:+.3f}, {self.alto:+.3f}]  "
            f"stesso segno in {self.anni_concordi:.0%} di {self.anni} anni"
        )


def confronta(risultati: list[Risultato], si: np.ndarray, ripetizioni: int = 4000, seme: int = 0) -> Confronto:
    si = np.asarray(si, bool)
    erre = np.array([r.erre for r in risultati], float)
    n_si, n_no = int(si.sum()), int((~si).sum())
    if not n_si or not n_no:
        nan = float("nan")
        return Confronto(n_si, n_no, nan, nan, nan, nan, nan, nan, 0)

    settimana = np.array([r.quando // SETTIMANA for r in risultati])
    _, gruppo = np.unique(settimana, return_inverse=True)
    w = int(gruppo.max()) + 1
    somme_si = np.bincount(gruppo, weights=erre * si, minlength=w)
    conti_si = np.bincount(gruppo, weights=si.astype(float), minlength=w)
    somme_no = np.bincount(gruppo, weights=erre * ~si, minlength=w)
    conti_no = np.bincount(gruppo, weights=(~si).astype(float), minlength=w)
    rng = np.random.default_rng(seme)
    scelte = rng.integers(0, w, size=(ripetizioni, w))
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = somme_si[scelte].sum(1) / conti_si[scelte].sum(1) - somme_no[scelte].sum(1) / conti_no[scelte].sum(1)
    diff = diff[np.isfinite(diff)]

    media_si, media_no = float(erre[si].mean()), float(erre[~si].mean())
    differenza = media_si - media_no
    anni = np.array([datetime.fromtimestamp(r.quando, tz=timezone.utc).year for r in risultati])
    segni = []
    for a in np.unique(anni):
        d = anni == a
        if (si & d).any() and (~si & d).any():
            segni.append(np.sign(erre[si & d].mean() - erre[~si & d].mean()) == np.sign(differenza))
    return Confronto(
        n_si, n_no, media_si, media_no, differenza,
        float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5)),
        float(np.mean(segni)) if segni else float("nan"), len(segni),
    )
