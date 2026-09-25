"""Quello che si vede dai timeframe grandi: l'allineamento e i gap.

Due agenti nuovi (l'utente, 25/09/2026: *"bisogna anche insegnargli
l'allineamento dei timeframe e i gap"*):

- **Allineamento**: su ogni timeframe grande (4 ore, giorno, settimana, mese)
  il bias di Romeo sulle ultime due candele chiuse (msg 5754, `conferme.bias`):
  a favore, contro o neutro. E su quanti livelli ci sono CRT piu' grandi
  armati nello stesso verso.
- **Gap**: i fair value gap ancora aperti di un timeframe (tre candele: il
  minimo della terza sopra il massimo della prima, o il contrario) e il gap
  di apertura della settimana, finche' il prezzo non torna a chiuderlo.

Tutto guarda solo candele chiuse prima dell'istante: niente futuro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import GRANDEZZA, Bias, Grandi, bias
from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import TF

MAI = np.iinfo(np.int64).max
GRANDI = (TF.H4, TF.D1, TF.W1, TF.MN)


# --- Allineamento ------------------------------------------------------------------------

def bias_a(c: Candele, t: int) -> Bias:
    """Il bias di Romeo dalle ultime due candele di `c` chiuse entro t."""
    k = int(np.searchsorted(c.fine, t, side="right"))
    if k < 2:
        return Bias.NEUTRO
    return bias(c.bid[k - 2], c.bid[k - 1])


def a_favore(b: Bias, verso: Verso) -> Optional[bool]:
    if b is Bias.NEUTRO:
        return None
    return (b is Bias.RIBASSISTA) == (verso is Verso.SHORT)


# --- Gap: i fair value gap ------------------------------------------------------------------

@dataclass
class Buchi:
    """I fair value gap di un timeframe, in ordine di nascita."""

    basso: np.ndarray
    alto: np.ndarray
    nato: np.ndarray        # la chiusura della terza candela: da li' si sa che c'e'
    chiuso: np.ndarray      # la chiusura della candela che lo riempie tutto (MAI se ancora aperto)
    rialzista: np.ndarray   # nato da una spinta in su (il buco sta sotto il prezzo)
    indice: np.ndarray      # l'indice della terza candela


def _primo(valori: np.ndarray, da: int, soglia: float, sotto: bool) -> int:
    """Il primo indice >= da dove valori <= soglia (sotto) o >= soglia; -1 se mai."""
    n = len(valori)
    passo = 16
    while da < n:
        a = min(n, da + passo)
        pezzo = valori[da:a]
        dove = np.flatnonzero(pezzo <= soglia if sotto else pezzo >= soglia)
        if len(dove):
            return da + int(dove[0])
        da, passo = a, passo * 4
    return -1


def buchi(c: Candele) -> Buchi:
    h, l = c.bid[:, MASSIMO].astype(float), c.bid[:, MINIMO].astype(float)
    if len(h) < 3:
        vuoto = np.zeros(0)
        return Buchi(vuoto, vuoto, vuoto.astype(np.int64), vuoto.astype(np.int64), vuoto.astype(bool), vuoto.astype(np.int64))
    su = np.flatnonzero(l[2:] > h[:-2]) + 2
    giu = np.flatnonzero(h[2:] < l[:-2]) + 2
    indice = np.r_[su, giu]
    rialzista = np.r_[np.ones(len(su), bool), np.zeros(len(giu), bool)]
    ordine = np.argsort(indice, kind="stable")
    indice, rialzista = indice[ordine], rialzista[ordine]
    basso = np.where(rialzista, h[indice - 2], h[indice])
    alto = np.where(rialzista, l[indice], l[indice - 2])
    chiuso = np.full(len(indice), MAI, np.int64)
    for j, (i, r) in enumerate(zip(indice, rialzista)):
        # Rialzista: si chiude quando il prezzo torna giu' fino al fondo; ribassista: su fino al tetto.
        k = _primo(l, i + 1, basso[j], True) if r else _primo(h, i + 1, alto[j], False)
        if k >= 0:
            chiuso[j] = int(c.fine[k])
    return Buchi(basso, alto, c.fine[indice].astype(np.int64), chiuso, rialzista, indice.astype(np.int64))


def aperti(b: Buchi, c: Candele, t: int, candele: int, da: float, a: float) -> np.ndarray:
    """Quali buchi, nati nelle ultime `candele` candele chiuse entro t, sono ancora aperti a t
    e toccano i prezzi fra `da` e `a`."""
    lo, hi = min(da, a), max(da, a)
    k = int(np.searchsorted(c.fine, t, side="right"))
    i0 = int(np.searchsorted(b.indice, k - candele))
    i1 = int(np.searchsorted(b.nato, t, side="right"))
    if i1 <= i0:
        return np.zeros(0, np.int64)
    s = slice(i0, i1)
    dentro = (b.chiuso[s] > t) & (b.alto[s] > lo) & (b.basso[s] < hi)
    return np.flatnonzero(dentro) + i0


# --- Gap: l'apertura della settimana ----------------------------------------------------------

@dataclass
class Aperture:
    """I gap di apertura della settimana: dove ha chiuso venerdi', dove ha aperto, quando si chiude."""

    inizio: np.ndarray      # l'inizio della prima ora della settimana
    prima: np.ndarray       # la chiusura dell'ultima ora prima del fine settimana
    apertura: np.ndarray
    chiuso: np.ndarray      # la chiusura dell'ora in cui il prezzo torna a `prima` (MAI se mai)
    giorno_medio: np.ndarray  # l'ampiezza media dei 20 giorni chiusi prima


def aperture(ore: Candele, giorni: Candele) -> Aperture:
    h, l = ore.bid[:, MASSIMO].astype(float), ore.bid[:, MINIMO].astype(float)
    salti = np.flatnonzero(ore.inizio[1:] - ore.fine[:-1] > 12 * 3600) + 1
    prima = ore.bid[salti - 1, CHIUSURA].astype(float)
    apertura = ore.bid[salti, APERTURA].astype(float)
    chiuso = np.full(len(salti), MAI, np.int64)
    for j, i in enumerate(salti):
        su = apertura[j] > prima[j]
        k = _primo(l, i, prima[j], True) if su else _primo(h, i, prima[j], False)
        if k >= 0:
            chiuso[j] = int(ore.fine[k])
    ampiezze = (giorni.bid[:, MASSIMO] - giorni.bid[:, MINIMO]).astype(float)
    somme = np.r_[0.0, np.cumsum(ampiezze)]
    medio = np.zeros(len(salti))
    for j, i in enumerate(salti):
        g = int(np.searchsorted(giorni.fine, ore.inizio[i], side="right"))
        if g >= 20:
            medio[j] = (somme[g] - somme[g - 20]) / 20
    return Aperture(ore.inizio[salti].astype(np.int64), prima, apertura, chiuso, medio)


def gap_della_settimana(a: Aperture, t: int) -> Optional[int]:
    """L'indice dell'ultima apertura di settimana prima di t, o None."""
    j = int(np.searchsorted(a.inizio, t, side="right")) - 1
    return j if j >= 0 else None


# --- Il contesto: le candele grandi di uno strumento ---------------------------------------

@dataclass
class Contesto:
    """Le candele di uno strumento che servono ad Allineamento, Gap e alle domande inventate,
    dalle ore: chiuse entro `fine`. `grandi` sono i CRT delle coppie; `pronti` i buchi e le
    aperture gia' trovati, calcolati una volta sola."""

    ore: Candele
    candele: dict
    grandi: Optional[Grandi] = None
    pronti: dict = field(default_factory=dict)

    @classmethod
    def da(cls, ore: Minuti, fine: int, grandi: Optional[Grandi] = None) -> "Contesto":
        tutte = {tf: costruisci(ore, tf).chiuse_entro(fine) for tf in GRANDI}
        return cls(costruisci(ore, TF.H1).chiuse_entro(fine), tutte, grandi)

    def tf(self, tf: TF) -> Candele:
        return self.ore if tf is TF.H1 else self.candele[tf]

    def buchi(self, tf: TF) -> Buchi:
        if ("buchi", tf) not in self.pronti:
            self.pronti[("buchi", tf)] = buchi(self.tf(tf))
        return self.pronti[("buchi", tf)]

    def aperture(self) -> Aperture:
        if "aperture" not in self.pronti:
            self.pronti["aperture"] = aperture(self.ore, self.candele[TF.D1])
        return self.pronti["aperture"]


# --- Cosa vedono, per la scheda dell'equipe -------------------------------------------------

@dataclass(frozen=True)
class Sguardo:
    # Per timeframe grande: il bias di Romeo a favore (True), contro (False) o neutro (None).
    lati: tuple
    # Su quanti livelli piu' grandi c'e' un CRT armato nello stesso verso.
    livelli: int
    # Il fair value gap aperto piu' vicino verso l'obiettivo (4 ore o giorno): (tf, basso, alto).
    fvg: Optional[tuple]
    # Il gap del weekend ancora aperto: (dove ha chiuso venerdi', se chiuderlo va a favore).
    weekend: Optional[tuple]


def sguardo(r, ctx: Contesto, candele: int = 50, soglia: float = 0.1) -> Sguardo:
    """Quello che Allineamento e Gap dicono di un'operazione, con le loro scelte di partenza."""
    crt = r.scatto.crt
    t = r.scatto.quando
    short = crt.verso is Verso.SHORT
    lati = tuple(a_favore(bias_a(ctx.candele[x], t), crt.verso) for x in GRANDI)
    livelli = ctx.grandi.livelli(crt.verso, GRANDEZZA.get(crt.alto_tf, 0), t) if ctx.grandi is not None else 0
    lato = crt.crt_low if short else crt.crt_high
    fvg = None
    for tf in (TF.H4, TF.D1):
        b = ctx.buchi(tf)
        trovati = aperti(b, ctx.tf(tf), t, candele, r.ingresso, lato)
        if len(trovati):
            vicino = min(trovati, key=lambda j: abs((b.alto[j] + b.basso[j]) / 2 - r.ingresso))
            fvg = (tf, float(b.basso[vicino]), float(b.alto[vicino]))
            break
    weekend = None
    ap = ctx.aperture()
    j = gap_della_settimana(ap, t)
    if (j is not None and ap.chiuso[j] > t and ap.giorno_medio[j] > 0
            and abs(ap.apertura[j] - ap.prima[j]) >= soglia * ap.giorno_medio[j]):
        weekend = (float(ap.prima[j]), bool((ap.apertura[j] > ap.prima[j]) == short))
    return Sguardo(lati, livelli, fvg, weekend)
