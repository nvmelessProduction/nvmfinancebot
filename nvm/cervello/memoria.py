"""La memoria del Capo e il confronto fra agenti con le prove.

Il Capo stima ogni operazione con una formula imparata su tutti i vent'anni insieme: vede
bene la media, ma in certe situazioni particolari sbaglia sempre nello stesso verso. La
memoria serve a questo. Davanti a un'occasione nuova il Capo:

1. **ricorda** i casi dei vent'anni piu' simili: prima gli stessi segnali dei due agenti che
   si stanno confrontando (quello che spinge di piu' a entrare e quello che frena di piu'),
   poi degli altri, uno alla volta, finche' i casi bastano;
2. **guarda come aveva sbagliato** in quei casi: il risultato vero meno quello che aveva
   stimato *allora*, con quello che sapeva allora (mai col senno di poi);
3. **decide chi aveva ragione** fra i due agenti: se in quei casi le cose sono andate meglio
   di quanto stimava, aveva ragione chi spingeva a entrare; se peggio, chi frenava;
4. **corregge la stima** di quell'errore, tanto di piu' quanti piu' casi ha (con pochi casi
   si fida poco del ricordo).

Tutto e' conto: quante volte, di quanto, con quanta incertezza.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from nvm.vivo.dialogo import firma

# Gli agenti che la memoria sa riconoscere, con i loro segnali ("firme").
AGENTI = ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias")
# Sotto questi casi un ricordo non basta.
N_MINIMO = 100
# Quanto il Capo si fida del ricordo: la correzione e' l'errore medio per n / (n + FIDUCIA).
# Con FIDUCIA casi il ricordo pesa meta'. La sceglie la prova sui vent'anni (`spec/cervello.md`).
FIDUCIA = 400.0


def firme(x: np.ndarray) -> np.ndarray:
    """I segnali di ogni agente, caso per caso: una colonna per agente."""
    x = np.atleast_2d(x)
    return np.array([[firma(a, riga) for a in AGENTI] for riga in x], dtype=object).reshape(len(x), len(AGENTI))


@dataclass
class Memoria:
    """I casi passati: i segnali degli agenti, il risultato vero (R, primo obiettivo) e
    l'errore del Capo (risultato vero meno quello che aveva stimato allora)."""

    firme: np.ndarray
    erre: np.ndarray
    errore: np.ndarray
    chiusa: np.ndarray
    _colonne: dict = field(default_factory=dict, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.erre)

    def uguale(self, agente: str, f: str) -> np.ndarray:
        """I casi in cui l'agente aveva dato lo stesso segnale."""
        k = (agente, f)
        if k not in self._colonne:
            self._colonne[k] = self.firme[:, AGENTI.index(agente)] == f
        return self._colonne[k]

    def prima_di(self, istante: int) -> "Memoria":
        m = self.chiusa < istante
        return Memoria(self.firme[m], self.erre[m], self.errore[m], self.chiusa[m])

    def con(self, altra: "Memoria") -> "Memoria":
        return Memoria(np.vstack([self.firme, altra.firme]), np.r_[self.erre, altra.erre],
                       np.r_[self.errore, altra.errore], np.r_[self.chiusa, altra.chiusa])


@dataclass(frozen=True)
class Ricordo:
    """Quello che il Capo ricorda di un'occasione."""

    condizioni: tuple            # ((agente, segnale), ...): cosa hanno in comune i casi ricordati
    n: int                       # quanti casi
    erre: float                  # come sono andati in media, in R
    errore: float                # di quanto il Capo aveva sbagliato in media (vero - stimato)
    incertezza: float            # l'errore standard di quella media
    correzione: float            # quanto correggere la stima adesso

    @property
    def netto(self) -> bool:
        """Se l'errore e' chiaro: almeno due volte la sua incertezza."""
        return abs(self.errore) >= 2 * self.incertezza


def ordine(spinte: dict[str, float]) -> list[str]:
    """In che ordine ricordare: prima chi spinge di piu' a entrare e chi frena di piu' (il
    confronto), poi gli altri, dal piu' ascoltato."""
    ag = [a for a in AGENTI if a in spinte]
    favore = max(ag, key=lambda a: spinte[a], default=None)
    contro = min(ag, key=lambda a: spinte[a], default=None)
    primi = [a for a in (favore, contro) if a is not None]
    primi = list(dict.fromkeys(primi))
    return primi + sorted((a for a in ag if a not in primi), key=lambda a: -abs(spinte[a]))


def ricorda(mem: Memoria, segnali: dict[str, str], chi: list[str], n_minimo: int = N_MINIMO,
            fiducia: float = FIDUCIA) -> Optional[Ricordo]:
    """I casi passati con gli stessi segnali degli agenti in `chi`, nell'ordine: si aggiunge un
    agente alla volta finche' restano almeno `n_minimo` casi. Nessun ricordo se gia' il primo
    agente ne ha meno."""
    if not len(mem):
        return None
    scelti = np.ones(len(mem), bool)
    condizioni = []
    for a in chi:
        prova = scelti & mem.uguale(a, segnali[a])
        if prova.sum() < n_minimo:
            break
        scelti = prova
        condizioni.append((a, segnali[a]))
    if not condizioni:
        return None
    n = int(scelti.sum())
    e = mem.errore[scelti]
    errore = float(e.mean())
    incertezza = float(e.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
    return Ricordo(tuple(condizioni), n, float(mem.erre[scelti].mean()), errore, incertezza,
                   errore * n / (n + fiducia))


def chi_aveva_ragione(r: Ricordo, spinte: dict[str, float]) -> Optional[str]:
    """Fra i due agenti del confronto: se nei casi ricordati e' andata meglio di quanto il Capo
    stimava, aveva ragione chi spingeva a entrare; se peggio, chi frenava. Nessuno se l'errore
    non e' chiaro."""
    if not r.netto or len(r.condizioni) < 1:
        return None
    del_confronto = [a for a, _ in r.condizioni[:2]]
    favore = max(del_confronto, key=lambda a: spinte.get(a, 0.0))
    contro = min(del_confronto, key=lambda a: spinte.get(a, 0.0))
    if r.errore > 0:
        return favore if spinte.get(favore, 0.0) > 0 else None
    return contro if spinte.get(contro, 0.0) < 0 else None


def correggi_p1(p1: float, correzione: float, rr1: float, rr2: float, q: float) -> float:
    """La probabilita' del primo obiettivo che rende la stima corretta. Il guadagno atteso del
    Capo e' p1 x (meta' RR1 + meta' q RR2) - (1 - p1) - costi: cresce di (meta' RR1 + meta'
    q RR2 + 1) per ogni punto di p1."""
    pendenza = 0.5 * rr1 + 0.5 * q * rr2 + 1.0
    return float(np.clip(p1 + correzione / pendenza, 0.01, 0.99))
