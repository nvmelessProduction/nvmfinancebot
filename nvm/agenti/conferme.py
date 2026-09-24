"""Le prime Conferme: key level, orario e bias.

Regole in `spec/conferme.md`. Ogni conferma risponde a una domanda sola, su
uno scatto del Grilletto, e non decide niente: il Capo impara quanto
fidarsi. `None` vuol dire "non so" (non ci sono abbastanza candele).

Come gli altri agenti, ogni risposta usa solo quello che si sapeva
all'istante dello scatto: le zone vengono da candele gia' chiuse prima
della manipolazione, e l'estremo e' quello toccato fino allo scatto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import TF, scarti_ny

# Il key level si prende dal timeframe sopra il range [S]; per il mensile,
# dai mesi precedenti [D].
SOPRA = {TF.H4: TF.D1, TF.D1: TF.W1, TF.W1: TF.MN, TF.MN: TF.MN}
# Quante candele chiuse si guardano [D].
QUANTE = 24
# Un massimo di swing e' piu' alto delle due candele prima e delle due dopo.
LATO_SWING = 2
# "Arrivare" a un massimo: finirci entro il 10% dell'ampiezza del CRT, sopra o sotto [D].
TOLLERANZA = 0.10

# La Golden candle time di Romeo: 9:00-13:00 di New York (msg 6110).
GCT = (9, 13)


@dataclass(frozen=True)
class KeyLevel:
    massimo: bool
    rejection_block: bool
    fvg: bool
    # Il disegno del msg 6718: la manipolazione arriva al livello e si ferma li'.
    tocca: bool = False

    @property
    def quanti(self) -> int:
        return int(self.massimo) + int(self.rejection_block) + int(self.fvg)


def key_level(s: Scatto, sopra: Candele, basse: Candele) -> Optional[KeyLevel]:
    """La manipolazione di questo scatto e' entrata in una zona del timeframe sopra?

    `sopra` sono le candele del timeframe del key level (`SOPRA[alto_tf]`),
    `basse` quelle del Grilletto: servono a sapere se una zona era gia'
    stata presa prima della manipolazione.
    """
    crt = s.crt
    inizio = crt.manipolazione_inizio
    n = int(np.searchsorted(sopra.fine, inizio, side="right"))
    k0 = max(0, n - QUANTE)
    if n - k0 < 2 * LATO_SWING + 1:
        return None
    estremo = crt.estremo_a(s.quando)
    if estremo is None:
        return None

    # Tutto si scrive per lo short; il long e' lo specchio, coi prezzi cambiati di segno.
    short = crt.verso is Verso.SHORT
    p = sopra.bid[k0:n]
    if short:
        o, h, l, c = p[:, APERTURA], p[:, MASSIMO], p[:, MINIMO], p[:, CHIUSURA]
        alti_bassi = basse.bid[:, MASSIMO]
    else:
        o, h, l, c = -p[:, APERTURA], -p[:, MINIMO], -p[:, MASSIMO], -p[:, CHIUSURA]
        alti_bassi = -basse.bid[:, MINIMO]
        estremo = -estremo
    fini = sopra.fine[k0:n]

    # Il punto piu' alto toccato dalla fine di ogni candela alla manipolazione.
    b0, b1 = np.searchsorted(basse.inizio, [fini[0], inizio])
    dopo = np.maximum.accumulate(alti_bassi[b0:b1][::-1])[::-1] if b1 > b0 else np.empty(0)
    indici = np.searchsorted(basse.inizio[b0:b1], fini)

    def massimo_dopo(i: int) -> float:
        k = int(indici[i])
        return float(dopo[k]) if k < len(dopo) else -np.inf

    massimo = rejection = fvg = tocca = False
    vicino = TOLLERANZA * (crt.crt_high - crt.crt_low)
    m = len(h)
    for i in range(LATO_SWING, m - LATO_SWING):
        vicini = np.r_[h[i - LATO_SWING:i], h[i + 1:i + 1 + LATO_SWING]]
        if not h[i] > vicini.max() or massimo_dopo(i) >= h[i]:
            continue
        # Un massimo non ancora preso: la manipolazione lo supera?
        massimo |= estremo > h[i]
        # Ci arriva e si ferma li' vicino?
        tocca |= abs(estremo - h[i]) <= vicino
        # La sua ombra, fra il corpo e il massimo: la manipolazione ci entra?
        rejection |= estremo > max(o[i], c[i])
    for j in range(m - 2):
        # Il vuoto fra la prima e la terza candela, non ancora riempito.
        fondo, cima = h[j + 2], l[j]
        if fondo < cima and massimo_dopo(j + 2) < cima:
            fvg |= estremo > fondo
    return KeyLevel(bool(massimo), bool(rejection), bool(fvg), bool(tocca))


@dataclass(frozen=True)
class Orario:
    ora_scatto: int
    ora_manipolazione: int

    @property
    def gct(self) -> bool:
        return GCT[0] <= self.ora_scatto < GCT[1]


def _ora_ny(t: int) -> int:
    return int((t + int(scarti_ny(np.array([t]))[0])) % 86400 // 3600)


def orario(s: Scatto, basse: Candele) -> Orario:
    """L'ora di New York in cui apre la candela dello scatto, e quella della manipolazione."""
    return Orario(_ora_ny(int(basse.inizio[s.indice])), _ora_ny(s.crt.manipolazione_inizio))


class Bias(str, Enum):
    RIALZISTA = "rialzista"
    RIBASSISTA = "ribassista"
    NEUTRO = "neutro"


def bias(prima: np.ndarray, dopo: np.ndarray) -> Bias:
    """Il bias per la candela successiva, dal foglio di Romeo (msg 5754).

    Chiusura sopra il massimo di prima: prezzi piu' alti. Chiusura sotto il
    minimo: piu' bassi. Ombra sopra (supera il massimo e richiude sotto):
    piu' bassi. Ombra sotto: piu' alti. Se i segni si contraddicono, o la
    candela resta dentro, non c'e' bias.
    """
    alto, basso = float(prima[MASSIMO]), float(prima[MINIMO])
    h, l, c = float(dopo[MASSIMO]), float(dopo[MINIMO]), float(dopo[CHIUSURA])
    su = c > alto or (l < basso and c >= basso)
    giu = c < basso or (h > alto and c <= alto)
    if su == giu:
        return Bias.NEUTRO
    return Bias.RIALZISTA if su else Bias.RIBASSISTA


@dataclass(frozen=True)
class Contesto:
    # Il bias dato dalla candela del range rispetto a quella prima: vale per
    # la candela 2, dove avviene la manipolazione.
    range: Bias
    # Lo stesso sul timeframe sopra, con le ultime due candele chiuse.
    sopra: Bias

    @staticmethod
    def dalla_parte(b: Bias, verso: Verso) -> Optional[bool]:
        """Si' se il bias va nel verso del CRT, no se va contro, None se neutro."""
        if b is Bias.NEUTRO:
            return None
        return (b is Bias.RIBASSISTA) == (verso is Verso.SHORT)


def contesto(s: Scatto, alte: Candele, sopra: Candele) -> Optional[Contesto]:
    crt = s.crt
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    n = int(np.searchsorted(sopra.fine, crt.manipolazione_inizio, side="right"))
    if k < 1 or n < 2:
        return None
    return Contesto(bias(alte.bid[k - 1], alte.bid[k]), bias(sopra.bid[n - 2], sopra.bid[n - 1]))
