"""Il Grilletto: sul CRT armato, e' scattato il Model#1?

Regole in `spec/grilletto.md`. Il Model#1 come lo disegna Romeo (msg 4836):
una candela bassa rialzista che spazza il `CRT high` e' il turtle soup, la
sua apertura e' il livello, e lo scatto e' la prima chiusura sotto il
livello. Per il long e' lo specchio.

Come il Cacciatore, ogni decisione usa solo candele gia' chiuse: lo scatto
di un CRT e' quello che il Grilletto avrebbe visto in quel momento.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import CRT, Verso
from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO


@dataclass
class Scatto:
    crt: CRT
    # La candela bassa che ha rotto il livello: si entra alla sua chiusura.
    quando: int
    indice: int
    livello: float
    turtle_soup_inizio: int
    # Massimo e minimo della candela del turtle soup: servono allo stop stretto.
    turtle_soup_massimo: float
    turtle_soup_minimo: float


def scatto(crt: CRT, basse: Candele, dopo: Optional[int] = None) -> Optional[Scatto]:
    """Il Model#1 su un CRT, se scatta mentre il CRT e' armato.

    Con `dopo` si guardano solo le candele che aprono da quell'istante in poi:
    serve per sparare di nuovo dopo uno stop, con un turtle soup nuovo.
    """
    inizio = crt.manipolazione_inizio if dopo is None else max(crt.manipolazione_inizio, dopo)
    i = int(np.searchsorted(basse.inizio, inizio))
    # Le candele che chiudono prima che il CRT decada: quella che lo fa
    # decadere (per esempio toccando il lato opposto) e' gia' troppo tardi.
    j = int(np.searchsorted(basse.fine, crt.decaduto_quando, side="left"))
    short = crt.verso is Verso.SHORT
    livello: Optional[float] = None
    ts = (0, 0.0, 0.0)
    for n in range(i, j):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        # Si scatta solo sul CRT gia' armato. Col manuale e' sempre cosi'; con
        # la chiusura dentro il CRT si arma alla fine della candela 2, e una
        # chiusura sotto il livello prima di allora non si poteva usare.
        armato = int(basse.fine[n]) >= crt.armato_quando
        if livello is not None and armato and (c < livello if short else c > livello):
            return Scatto(crt, int(basse.fine[n]), n, livello, *ts)
        # La candela del turtle soup: rialzista oltre CRT high per uno short,
        # ribassista oltre CRT low per un long. Una piu' recente sposta il livello.
        if (c > o and h > crt.crt_high) if short else (c < o and l < crt.crt_low):
            livello, ts = o, (int(basse.inizio[n]), h, l)
    return None


def scatti(crt: list[CRT], basse: Candele) -> list[Scatto]:
    trovati = [s for c in crt if (s := scatto(c, basse)) is not None]
    trovati.sort(key=lambda s: (s.quando, s.crt.range_inizio, s.crt.verso.value))
    return trovati
