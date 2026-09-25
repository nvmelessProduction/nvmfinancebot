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

from nvm.agenti.cacciatore import CRT, Verso
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
# La liquidita' presa (Grilletto): un massimo di swing e' piu' alto di tante candele per lato.
LATO_LIQUIDITA = 2
# Sconto e premio (Bias): un long e' a sconto sotto questa frazione della settimana chiusa prima,
# uno short a premio sopra 1 - SCONTO. 0,5 e' la meta' del range (msg 6110, "50% = halfway point").
SCONTO = 0.5

# La Golden candle time di Romeo: 9:00-13:00 di New York (msg 6110).
GCT = (9, 13)
# Le ore in cui entra Romeo, di New York (`spec/conferme.md`, le risposte alla Romeo).
LONDRA = (1, 5)
NEW_YORK = (8, 11)
# Quale range e' piu' grande: una coppia sta dentro l'altra se il suo range e' piu' piccolo.
GRANDEZZA = {TF.MN: 4, TF.W1: 3, TF.D1: 2, TF.H4: 1}


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


@dataclass(frozen=True)
class AllaRomeo:
    """Le quattro domande di `spec/conferme.md`, "le risposte alla Romeo"."""

    londra: bool
    new_york: bool
    # Un CRT di una coppia piu' grande armato nello stesso verso (msg 5121).
    annidato: bool
    # Long nella meta' bassa della settimana chiusa prima, short in quella alta.
    # None se la settimana manca.
    sconto: Optional[bool]


def _ore_toccate(inizio: int, fine: int) -> set[int]:
    passi = np.arange(inizio, fine, 900, dtype=np.int64)
    return set(((passi + scarti_ny(passi)) % 86400 // 3600).tolist())


@dataclass
class Grandi:
    """I CRT delle coppie, pronti per la domanda "chi era armato a quell'istante?".

    Per ogni verso e grandezza del range: gli istanti in cui si armano, in
    ordine, e il piu' tardo fra quelli in cui decadono, fino a li'. Un CRT
    era armato all'istante t se si e' armato entro t e decade dopo t: basta
    che il piu' tardo a decadere, fra quelli armati entro t, decada dopo t.
    """

    armati: dict[tuple[Verso, int], np.ndarray]
    decadono: dict[tuple[Verso, int], np.ndarray]

    @classmethod
    def da(cls, crt: list[CRT]) -> "Grandi":
        armati, decadono = {}, {}
        for chiave in {(c.verso, GRANDEZZA.get(c.alto_tf, 0)) for c in crt}:
            scelti = sorted((c for c in crt if (c.verso, GRANDEZZA.get(c.alto_tf, 0)) == chiave),
                            key=lambda c: c.armato_quando)
            armati[chiave] = np.array([c.armato_quando for c in scelti], np.int64)
            decadono[chiave] = np.maximum.accumulate(np.array([c.decaduto_quando for c in scelti], np.int64))
        return cls(armati, decadono)

    def armato(self, verso: Verso, piu_grande_di: int, istante: int) -> bool:
        return self.livelli(verso, piu_grande_di, istante) > 0

    def livelli(self, verso: Verso, piu_grande_di: int, istante: int) -> int:
        """Su quante grandezze piu' grandi c'era un CRT armato nello stesso verso a quell'istante."""
        n = 0
        for (v, grandezza), inizi in self.armati.items():
            if v is not verso or grandezza <= piu_grande_di:
                continue
            k = int(np.searchsorted(inizi, istante, side="right"))
            if k and self.decadono[(v, grandezza)][k - 1] > istante:
                n += 1
        return n


def alla_romeo(s: Scatto, basse: Candele, settimane: Candele, grandi: Grandi) -> AllaRomeo:
    """Le risposte alla Romeo per uno scatto, con quello che si sapeva allo scatto.

    `settimane` sono le candele settimanali dello strumento, `grandi` i CRT
    delle coppie: conta solo chi era armato all'istante dello scatto.
    """
    crt = s.crt
    ore = _ore_toccate(int(basse.inizio[s.indice]), int(basse.fine[s.indice]))
    londra = any(LONDRA[0] <= h < LONDRA[1] for h in ore)
    new_york = any(NEW_YORK[0] <= h < NEW_YORK[1] for h in ore)
    annidato = grandi.armato(crt.verso, GRANDEZZA.get(crt.alto_tf, 0), s.quando)
    k = int(np.searchsorted(settimane.fine, s.quando, side="right"))
    sconto = None
    if k >= 1:
        alto, basso = float(settimane.bid[k - 1, MASSIMO]), float(settimane.bid[k - 1, MINIMO])
        if alto > basso:
            dove = (float(basse.bid[s.indice, CHIUSURA]) - basso) / (alto - basso)
            sconto = dove < SCONTO if crt.verso is Verso.LONG else dove > 1 - SCONTO
    return AllaRomeo(londra, new_york, annidato, sconto)


@dataclass(frozen=True)
class Liquidita:
    """La terza gamba del manuale di Romeo: *"Mark a pre-manipulation swing
    high/low"* (msg 6718), *"pre-manipulation liquidity pool"* (msg 3860).
    La risposta del Grilletto, che guarda il timeframe basso (`spec/conferme.md`)."""

    # La manipolazione supera un massimo di swing del timeframe basso, nato
    # dopo l'inizio del range e non ancora preso prima del turtle soup.
    presa: bool
    # ...e quel massimo stava sopra il CRT high: il prezzo era gia' uscito dal
    # range, e' tornato giu', e la manipolazione torna a prenderlo.
    sopra_il_crt: bool


def liquidita(s: Scatto, basse: Candele) -> Liquidita:
    """La manipolazione di questo scatto ha preso la liquidita' lasciata prima di lei?"""
    crt = s.crt
    short = crt.verso is Verso.SHORT
    # Tutto si scrive per lo short; il long e' lo specchio.
    segno = 1.0 if short else -1.0
    estremo = crt.estremo_a(s.quando)
    if estremo is None:
        return Liquidita(False, False)
    estremo *= segno
    lato = crt.crt_high if short else -crt.crt_low
    a, t = np.searchsorted(basse.inizio, [crt.range_inizio, s.turtle_soup_inizio])
    h = (basse.bid[a:t, MASSIMO] if short else -basse.bid[a:t, MINIMO])
    presa = sopra = False
    lato_swing = LATO_LIQUIDITA
    if len(h) >= 2 * lato_swing + 1:
        # Il punto piu' alto da ogni candela fino al turtle soup escluso.
        dopo = np.maximum.accumulate(h[::-1])[::-1]
        for i in range(lato_swing, len(h) - lato_swing):
            vicini = np.r_[h[i - lato_swing:i], h[i + 1:i + 1 + lato_swing]]
            if h[i] > vicini.max() and dopo[i + 1] < h[i] and estremo > h[i]:
                presa = True
                sopra |= bool(h[i] > lato)
    return Liquidita(presa, sopra)


def tutti_i_pareri(s: Scatto, alte: Candele, basse: Candele, sopra: Candele, settimane: Candele, grandi: Grandi):
    """Le risposte di tutte le conferme a uno scatto, nell'ordine che vuole il Capo."""
    return (key_level(s, sopra, basse), orario(s, basse), contesto(s, alte, sopra),
            alla_romeo(s, basse, settimane, grandi), liquidita(s, basse))
