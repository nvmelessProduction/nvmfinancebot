"""I piani fra cui i cervelli scelgono, su ogni operazione.

Non piu' uno stop e un obiettivo fissi per tutti: per ogni occasione ci sono piu' piani, e i
cervelli imparano quale rende di piu' in quella situazione (o se non conviene nessuno).

- **Dove va lo stop**: *stretto* (appena oltre il livello della conferma, come fa Romeo
  nelle operazioni pubblicate), *all'estremo* (oltre l'estremo della manipolazione, almeno
  un quarto del range: il manuale di oggi), *largo* (un quarto di range piu' in la').
- **Come si prende il profitto**: *tutto al primo obiettivo* (meta' range), *meta' e meta'*
  (meta' al primo, il resto al secondo col pareggio: il manuale di oggi), *tutto al secondo*
  (oltre il lato opposto, con lo stop a pareggio arrivati al primo).

Sui vent'anni ogni operazione si rifa' con tutti i piani, sugli stessi prezzi: e' da li' che i
cervelli imparano. Dal vivo si apre il piano scelto.
"""

from __future__ import annotations

from typing import Optional

from nvm.agenti import livelli
from nvm.agenti.cacciatore import Verso
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA
from nvm.prova.campo import Operazione, simula

STOP = ("stretto", "estremo", "largo")
USCITE = ("primo", "meta", "secondo")
PIANI = tuple((s, u) for s in STOP for u in USCITE)
# Di quanto lo stop largo sta oltre quello all'estremo, in ampiezze del range.
PIU_LARGO = 0.25
NOMI = {"stretto": "stop stretto", "estremo": "stop all'estremo", "largo": "stop largo",
        "primo": "tutto al primo obiettivo", "meta": "metà al primo e metà al secondo",
        "secondo": "tutto al secondo obiettivo"}


def nome(piano: tuple[str, str]) -> str:
    return f"{NOMI[piano[0]]}, {NOMI[piano[1]]}"


def operazione(s: Scatto, basse: Candele, stop: str, uscita: str) -> Optional[Operazione]:
    """L'operazione di uno scatto con un piano. None se il piano non si puo' fare."""
    crt = s.crt
    short = crt.verso is Verso.SHORT
    segno = -1 if short else 1
    ingresso = float((basse.bid if short else basse.ask)[s.indice, CHIUSURA])
    ampiezza = crt.crt_high - crt.crt_low
    estremo = crt.estremo_a(s.quando)
    if estremo is None or ampiezza <= 0:
        return None
    all_estremo = (max(estremo, ingresso + livelli.STOP_MINIMO * ampiezza) if short
                   else min(estremo, ingresso - livelli.STOP_MINIMO * ampiezza))
    if stop == "stretto":
        margine = livelli.MARGINE_STOP_STRETTO * (s.turtle_soup_massimo - s.turtle_soup_minimo)
        prezzo_stop = s.livello + margine if short else s.livello - margine
    elif stop == "largo":
        prezzo_stop = all_estremo + segno * -PIU_LARGO * ampiezza
    else:
        prezzo_stop = all_estremo
    tp1 = crt.crt_50
    tp2 = crt.crt_low - livelli.OLTRE * ampiezza if short else crt.crt_high + livelli.OLTRE * ampiezza
    if segno * (ingresso - prezzo_stop) <= 0 or segno * (tp1 - ingresso) <= 0:
        return None
    parziale = {"primo": 1.0, "meta": 0.5, "secondo": 0.0}[uscita]
    try:
        return Operazione(crt.strumento, crt.verso, s.quando, ingresso, prezzo_stop, tp1, tp2, parziale=parziale,
                          pareggio=uscita != "primo", pareggio_a=livelli.PAREGGIO, livello_model1=s.livello,
                          invalida_candele=livelli.INVALIDAZIONE, tempo_candele=livelli.TEMPO)
    except ValueError:
        return None


def tutti(s: Scatto, basse: Candele) -> list[Optional[Operazione]]:
    return [operazione(s, basse, st, u) for st, u in PIANI]


def risultati(s: Scatto, basse: Candele) -> list[float]:
    """Come sarebbe finita l'operazione con ogni piano, in R (NaN se il piano non si puo' fare)."""
    fuori = []
    for op in tutti(s, basse):
        fuori.append(float("nan") if op is None else simula(op, basse, livelli.scadenza(s)).erre)
    return fuori
