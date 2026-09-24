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

from nvm.agenti.cacciatore import CRT, caccia
from nvm.agenti.capo import Capo, riga
from nvm.agenti.conferme import SOPRA, AllaRomeo, Contesto, KeyLevel, Orario, tutti_i_pareri
from nvm.agenti.livelli import piano, scadenza
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import Risultato, opera
from nvm.prova.campo import Operazione
from nvm.prova.romeo import grandi
from nvm.tempo import TF

# Le coppie che si guardano con le orarie, ogni ora.
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
# La quarta coppia di Romeo si guarda con i quarti d'ora di MT5, ogni quarto d'ora.
COPPIA_VELOCE = (TF.H4, TF.M15)


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
    # Le risposte alla Romeo, e quanto il Capo pensa che somigli a una sua entrata.
    alla_romeo: Optional[AllaRomeo] = None
    romeo: float = 1.0
    soglia: float = 0.0
    # La decisione del Capo: guadagno atteso sopra zero e abbastanza simile a Romeo.
    scelta: Optional[bool] = None

    @property
    def entra(self) -> bool:
        return self.atteso > 0 if self.scelta is None else self.scelta

    @property
    def chiave(self) -> str:
        r = self.r
        return f"{r.strumento} {r.alto_tf.value}-{r.basso_tf.value} {r.verso.value} {r.quando} colpo {r.colpo}"


def giro(basi: dict[str, Minuti], dal: int, adesso: int, capo: Capo, coppie=COPPIE,
         orarie: Optional[dict[str, Minuti]] = None) -> list[Decisione]:
    """Le decisioni con lo scatto in [dal, adesso], su candele chiuse entro `adesso`.

    `orarie` sono le ore di ogni strumento, se `basi` sono i quarti d'ora: da
    li' vengono il timeframe sopra, la settimana e i CRT piu' grandi.
    """
    orarie = basi if orarie is None else orarie
    decisioni = []
    for strumento, base in basi.items():
        ore = orarie.get(strumento, base)
        if not len(base) or not len(ore):
            continue
        g = grandi(ore, adesso)
        settimane = costruisci(ore, TF.W1).chiuse_entro(adesso)
        for alto, basso in coppie:
            alte = costruisci(base, alto).chiuse_entro(adesso)
            basse = costruisci(base, basso).chiuse_entro(adesso)
            sopra = costruisci(ore, SOPRA[alto]).chiuse_entro(adesso)
            for r in opera(alte, basse, dal, adesso + 1):
                op = piano(r.scatto, basse)
                kl, ora, ctx, ar = tutti_i_pareri(r.scatto, alte, basse, sopra, settimane, g)
                x = riga(r, kl, ora, ctx, ar)[None]
                p1, q = capo.probabilita(x)
                atteso = capo.valore_atteso(x, np.array([r.rr1]), np.array([r.rr2]), np.array([r.costo_erre]))
                decisioni.append(Decisione(
                    r, op, scadenza(r.scatto), kl, ora, ctx, float(p1[0]), float(q[0]), float(atteso[0]), x[0],
                    ar, float(capo.somiglianza(x)[0]), capo.soglia_romeo,
                    bool(capo.entra(x, np.array([r.rr1]), np.array([r.rr2]), np.array([r.costo_erre]))[0])))
    decisioni.sort(key=lambda d: (d.r.quando, d.r.strumento))
    return decisioni


def armati(basi: dict[str, Minuti], dal: int, adesso: int, coppie=COPPIE) -> list[CRT]:
    """I CRT che il Cacciatore ha visto armarsi in [dal, adesso]."""
    trovati = []
    for base in basi.values():
        if not len(base):
            continue
        for alto, basso in coppie:
            alte = costruisci(base, alto).chiuse_entro(adesso)
            basse = costruisci(base, basso).chiuse_entro(adesso)
            trovati += [c for c in caccia(alte, basse) if dal <= c.armato_quando <= adesso]
    trovati.sort(key=lambda c: (c.armato_quando, c.strumento))
    return trovati
