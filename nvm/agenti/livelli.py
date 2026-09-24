"""Livelli: dove vanno stop, primo target e target finale.

Il manuale (`spec/grilletto.md`, "Da passare agli altri agenti"):

- **stop** appena oltre l'estremo del turtle soup: "turtle soup high has to
  be the ceiling" (Romeo, msg 163);
- **primo target** al 50% del range: "the 50% is almost always guaranteed"
  (msg 6561);
- **target finale** al lato opposto del range: "take profit at 50% and then
  CRTH/L";
- **niente operazione** se l'ingresso e' gia' oltre il 50%: il primo target
  starebbe alle spalle.

L'operazione dura fino alla fine della **candela 3** del CRT: "you only need
3 candles", e nel suo CRT mensile di EURUSD (msg 5623, ottobre 2024) si entra
a settembre, nella candela 2, e il target 2 arriva a ottobre, nella candela
3. Una prima versione chiudeva alla fine della candela d'ingresso: quel caso
l'ha smentita.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import MAI, Verso
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA
from nvm.prova.campo import Operazione
from nvm.tempo import fine_candela, inizio_candela


def piano(s: Scatto, basse: Candele, parziale: float = 0.5, pareggio: bool = True) -> Optional[Operazione]:
    """L'operazione del manuale per uno scatto, o None se non si puo' fare."""
    crt = s.crt
    short = crt.verso is Verso.SHORT
    # Si vende in bid e si compra in ask, alla chiusura della candela che scatta.
    ingresso = float((basse.bid if short else basse.ask)[s.indice, CHIUSURA])
    stop = crt.estremo_a(s.quando)
    if stop is None:
        return None
    tp1, tp2 = crt.crt_50, (crt.crt_low if short else crt.crt_high)
    segno = -1 if short else 1
    if segno * (ingresso - stop) <= 0 or segno * (tp1 - ingresso) <= 0:
        return None
    return Operazione(
        strumento=crt.strumento, verso=crt.verso, quando=s.quando,
        ingresso=ingresso, stop=stop, tp1=tp1, tp2=tp2,
        parziale=parziale, pareggio=pareggio,
    )


def scadenza(s: Scatto) -> int:
    """La fine della candela 3 del CRT. Se non e' ancora nota (la candela 3
    non e' iniziata), la fine della candela in cui si entra piu' una."""
    if s.crt.fine_candela_3 < MAI:
        return s.crt.fine_candela_3
    inizio = int(inizio_candela(np.array([s.quando]), s.crt.alto_tf)[0])
    fine = fine_candela(inizio, s.crt.alto_tf)
    return fine_candela(int(inizio_candela(np.array([fine]), s.crt.alto_tf)[0]), s.crt.alto_tf)
