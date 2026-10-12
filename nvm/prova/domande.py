"""Domande provate per gli agenti, per il banco di prova (`strumenti/banco.py`).

Ogni gruppo e' una lista di nomi e una funzione che, per un'operazione, le
sue candele basse e le candele del contesto, risponde con un numero per nome
(0 = no). Qui restano anche quelle che non hanno aiutato: il registro
(`documenti/registro/tentativi.md`, 25/09/2026) le cita, e cosi' si possono rifare.
Quelle entrate nel bot vivono negli agenti (`nvm/agenti/conferme.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import GCT, LONDRA, NEW_YORK, SOPRA, Bias, _ora_ny, bias, key_level, liquidita
from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.prova.base import Risultato
from nvm.tempo import NEW_YORK as FUSO, TF


@dataclass
class Contesto:
    """Le candele chiuse di uno strumento che servono alle domande."""

    ore: Candele
    h4: Candele
    giorni: Candele
    settimane: Candele
    mesi: Candele

    def alte(self, tf: TF) -> Candele:
        return {TF.H1: self.ore, TF.H4: self.h4, TF.D1: self.giorni, TF.W1: self.settimane, TF.MN: self.mesi}[tf]


def _prima(c: Candele, t: int) -> int:
    """L'indice dell'ultima candela chiusa entro t (-1 se nessuna)."""
    return int(np.searchsorted(c.fine, t, side="right")) - 1


def _alto(c: Candele, k: int, short: bool) -> float:
    """Il lato da prendere di una candela, scritto per lo short (il long cambia segno)."""
    return float(c.bid[k, MASSIMO]) if short else -float(c.bid[k, MINIMO])


def liquidita_e_livelli(r: Risultato, basse: Candele, c: Contesto) -> list[float]:
    s = r.scatto
    crt = s.crt
    short = crt.verso is Verso.SHORT
    segno = 1.0 if short else -1.0
    estremo = crt.estremo_a(s.quando) * segno
    ampiezza = crt.crt_high - crt.crt_low
    t = s.turtle_soup_inizio
    kd, kw, km = _prima(c.giorni, t), _prima(c.settimane, t), _prima(c.mesi, t)
    giorno, settimana, mese = _alto(c.giorni, kd, short), _alto(c.settimane, kw, short), _alto(c.mesi, km, short)
    liq = liquidita(s, basse)
    # L'Asia: 20-24 di New York del giorno del turtle soup, se il turtle soup e' dopo mezzanotte.
    ny = datetime.fromtimestamp(t, tz=FUSO)
    asia = 0.0
    if ny.hour < 12:
        mezzanotte = int(ny.replace(hour=0, minute=0, second=0).timestamp())
        i0, i1 = np.searchsorted(c.ore.inizio, [mezzanotte - 4 * 3600, mezzanotte])
        if i1 > i0:
            alti = c.ore.bid[i0:i1, MASSIMO] if short else -c.ore.bid[i0:i1, MINIMO]
            asia = float(estremo > alti.max())
    ingresso = float(basse.bid[s.indice, CHIUSURA])
    sopra = []
    for candele, k in ((c.giorni, kd), (c.settimane, kw)):
        apertura = candele.bid[k + 1, APERTURA] if k + 1 < len(candele) else np.nan
        sopra.append(float(ingresso > apertura if short else ingresso < apertura))
    return [estremo > giorno, abs(estremo - giorno) <= 0.1 * ampiezza, estremo > settimana,
            liq.presa, liq.sopra_il_crt, asia, *sopra, estremo > mese]


def orario_e_key_level(r: Risultato, basse: Candele, c: Contesto) -> list[float]:
    s = r.scatto
    crt = s.crt
    h = _ora_ny(s.turtle_soup_inizio)
    risposte = [LONDRA[0] <= h < LONDRA[1], NEW_YORK[0] <= h < NEW_YORK[1], GCT[0] <= h < GCT[1], 19 <= h]
    kl = key_level(s, c.alte(SOPRA[SOPRA[crt.alto_tf]]), basse)
    risposte += [0, 0, 0, 0] if kl is None else [kl.massimo, kl.rejection_block, kl.fvg, kl.tocca]
    # "Third tap+": quante candele basse della candela 2, prima del turtle soup, hanno superato il lato e richiuso dentro.
    a, t = np.searchsorted(basse.inizio, [crt.manipolazione_inizio, s.turtle_soup_inizio])
    if crt.verso is Verso.SHORT:
        tocchi = ((basse.bid[a:t, MASSIMO] > crt.crt_high) & (basse.bid[a:t, CHIUSURA] <= crt.crt_high)).sum()
    else:
        tocchi = ((basse.bid[a:t, MINIMO] < crt.crt_low) & (basse.bid[a:t, CHIUSURA] >= crt.crt_low)).sum()
    return [*risposte, tocchi >= 2]


def candela_del_range(r: Risultato, basse: Candele, c: Contesto) -> list[float]:
    crt = r.scatto.crt
    alte = c.alte(crt.alto_tf)
    short = crt.verso is Verso.SHORT
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    if k < 21 or k >= len(alte):
        return [0.0] * 7
    o, h, l, cl = (float(alte.bid[k, j]) for j in (APERTURA, MASSIMO, MINIMO, CHIUSURA))
    mediana = float(np.median(alte.bid[k - 20:k, MASSIMO] - alte.bid[k - 20:k, MINIMO]))
    ampiezza = h - l
    if short:
        swing = h > alte.bid[k - 2:k, MASSIMO].max()
        presa = h > alte.bid[k - 1, MASSIMO]
        vicino = (h - cl) <= 0.25 * ampiezza
    else:
        swing = l < alte.bid[k - 2:k, MINIMO].min()
        presa = l < alte.bid[k - 1, MINIMO]
        vicino = (cl - l) <= 0.25 * ampiezza
    return [cl > o if short else cl < o, ampiezza > mediana, ampiezza < 0.5 * mediana, swing, presa, vicino,
            abs(cl - o) > 0.6 * ampiezza if ampiezza > 0 else 0.0]


def _bias(c: Candele, t: int, verso: Verso) -> tuple[float, float]:
    k = int(np.searchsorted(c.fine, t, side="right"))
    if k < 2:
        return 0.0, 0.0
    b = bias(c.bid[k - 2], c.bid[k - 1])
    if b is Bias.NEUTRO:
        return 0.0, 0.0
    favore = (b is Bias.RIALZISTA) == (verso is Verso.LONG)
    return float(favore), float(not favore)


def _sconto(c: Candele, t: int, prezzo: float, verso: Verso) -> float:
    k = int(np.searchsorted(c.fine, t, side="right"))
    if k < 1:
        return 0.0
    h, l = c.bid[k - 1, MASSIMO], c.bid[k - 1, MINIMO]
    if h <= l:
        return 0.0
    dove = (prezzo - l) / (h - l)
    return float(dove < 0.5 if verso is Verso.LONG else dove > 0.5)


def direzione(r: Risultato, basse: Candele, c: Contesto) -> list[float]:
    s = r.scatto
    t, v, p = s.quando, r.verso, float(basse.bid[s.indice, CHIUSURA])
    return [*_bias(c.giorni, t, v), *_bias(c.settimane, t, v), *_bias(c.mesi, t, v),
            _sconto(c.mesi, t, p, v), _sconto(c.giorni, t, p, v)]


GRUPPI: dict[str, tuple[tuple[str, ...], Callable[[Risultato, Candele, Contesto], list[float]]]] = {
    "liquidita": (("giorno prima preso", "giorno prima vicino", "settimana prima presa", "liquidità presa prima",
                   "liquidità presa sopra il CRT", "Asia presa", "oltre l'apertura del giorno",
                   "oltre l'apertura della settimana", "mese prima preso"), liquidita_e_livelli),
    "orario": (("turtle soup nell'ora di Londra", "turtle soup nell'ora di New York", "turtle soup 9-13",
                "turtle soup 19-24", "key level due sopra: massimo preso", "key level due sopra: rejection block",
                "key level due sopra: FVG", "key level due sopra: arriva", "due o più tocchi del lato"), orario_e_key_level),
    "cacciatore": (("candela 1 opposta (order block)", "range grande", "range piccolo", "candela 1 massimo di swing",
                    "candela 1 prende la candela prima", "candela 1 chiude vicino al lato", "candela 1 corpo grande"),
                   candela_del_range),
    "bias": (("bias del giorno a favore", "bias del giorno contro", "bias della settimana a favore",
              "bias della settimana contro", "bias del mese a favore", "bias del mese contro", "a sconto sul mese",
              "a sconto sul giorno prima"), direzione),
}
