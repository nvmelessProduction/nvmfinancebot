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

L'operazione dura fino alla fine della candela alta in cui si entra: "where
is that candle likely to go... the journey till the candle's final
destination" (msg 5489). Deciso qui, perche' la durata Romeo non la scrive.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
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
    """La fine della candela alta in cui si entra."""
    inizio = int(inizio_candela(np.array([s.quando]), s.crt.alto_tf)[0])
    return fine_candela(inizio, s.crt.alto_tf)
