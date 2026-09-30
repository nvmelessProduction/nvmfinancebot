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

from nvm.agenti.cacciatore import CRT, MAI as MAI_3, Verso
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
    # Quale entrata: "model1" (sul turtle soup del CRT, candela 2 o 3) o "candela 3" (il metodo dei
    # video: aspettata la chiusura della candela 2, turtle soup nella candela 3 oltre la sua apertura).
    modello: str = "model1"
    # Per la candela 3: la punta della candela del turtle soup (lo stop di Romeo), quanto era spessa
    # rispetto alle 20 candele prima, e l'apertura della candela 3.
    punta: Optional[float] = None
    spessore: float = 0.0
    apertura_3: Optional[float] = None


# La candela del Model#1 dev'essere spessa: *"the thick candle that scares everyone"* (V1 37:18,
# V3 11:13, V8 18:21). Spessa = il corpo almeno tante volte il corpo medio delle 20 candele prima.
SPESSORE = 1.2
CANDELE_SPESSORE = 20


def _spessore(basse: Candele, n: int) -> float:
    corpi = np.abs(basse.bid[max(0, n - CANDELE_SPESSORE):n, CHIUSURA] - basse.bid[max(0, n - CANDELE_SPESSORE):n, APERTURA])
    medio = float(corpi.mean()) if len(corpi) else 0.0
    corpo = abs(float(basse.bid[n, CHIUSURA]) - float(basse.bid[n, APERTURA]))
    return corpo / medio if medio > 0 else 0.0


def scatto_candela_3(crt: CRT, basse: Candele, spessore: Optional[float] = None) -> Optional[Scatto]:
    """L'entrata dei video, nella candela 3 (`spec/metodo_romeo.md`, 2 e 6).

    Il CRT dev'essere della variante `CHIUSURA_DENTRO`: la candela 2 ha spazzato un lato e ha chiuso
    dentro (e' gia' chiusa). Nella candela 3, per vendere: una candela rialzista **spessa** fa un
    massimo nuovo della candela 3 (turtle soup), sopra l'apertura della candela 3; si entra alla prima
    chiusura sotto il suo corpo (la sua apertura). Stop alla sua punta. Se prima dello scatto il prezzo
    ha gia' toccato il 50% del range, il CRT ha gia' funzionato: niente entrata (V10 12:10). Per
    comprare e' lo specchio.
    """
    spessore = SPESSORE if spessore is None else spessore
    if crt.fine_candela_3 >= MAI_3 or crt.armato_quando >= crt.decaduto_quando:
        return None
    i = int(np.searchsorted(basse.inizio, crt.armato_quando))
    j = int(np.searchsorted(basse.fine, crt.decaduto_quando, side="left"))
    j = min(j, int(np.searchsorted(basse.fine, crt.fine_candela_3, side="right")))
    if i >= len(basse) or i >= j:
        return None
    short = crt.verso is Verso.SHORT
    apertura_3 = float(basse.bid[i, APERTURA])
    meta = crt.crt_50
    livello: Optional[float] = None
    ts = (0, 0.0, 0.0)
    punta, spessa = 0.0, 0.0
    estremo_3: Optional[float] = None
    for n in range(i, j):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        if livello is not None and (c < livello if short else c > livello):
            return Scatto(crt, int(basse.fine[n]), n, livello, *ts, modello="candela 3", punta=punta,
                          spessore=spessa, apertura_3=apertura_3)
        # Il 50% gia' preso: il CRT ha funzionato senza di noi.
        if (l <= meta) if short else (h >= meta):
            return None
        nuovo = estremo_3 is not None and ((h > estremo_3) if short else (l < estremo_3))
        if nuovo and ((c > o and o >= apertura_3) if short else (c < o and o <= apertura_3)):
            k = _spessore(basse, n)
            if k >= spessore:
                livello, ts, punta, spessa = o, (int(basse.inizio[n]), h, l), (h if short else l), k
        estremo_3 = (h if estremo_3 is None else max(estremo_3, h)) if short else \
            (l if estremo_3 is None else min(estremo_3, l))
    return None


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
