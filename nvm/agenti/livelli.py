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

L'operazione non ha un'uscita a tempo: esce con lo stop o col target, e dopo
il primo target il pareggio protegge il resto. Romeo non parla mai di
chiudere per tempo, e due suoi casi hanno smentito le durate provate prima:
nel CRT mensile di EURUSD (msg 5623) il target 2 arriva nella candela 3,
nel giornaliero di dicembre 2024 (msg 5730) nella candela 4. Per la
simulazione resta solo un tetto di sicurezza, largo (`TETTO`), e chi misura
conta quante operazioni ci arrivano.
"""

from __future__ import annotations

from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA
from nvm.prova.campo import Operazione
from nvm.tempo import TF


# Lo stop stretto sta oltre il livello del Model#1 di questa frazione
# dell'escursione della candela del turtle soup.
MARGINE_STOP_STRETTO = 0.10


def piano(
    s: Scatto, basse: Candele, parziale: float = 0.5, pareggio: bool = True,
    stop_stretto: bool = False,
) -> Optional[Operazione]:
    """L'operazione del manuale per uno scatto, o None se non si puo' fare.

    `stop_stretto` e' la variante dichiarata: lo stop appena oltre il livello
    del Model#1 (l'apertura della candela del turtle soup) invece che oltre
    l'estremo. E' quello che Romeo fa nelle operazioni che ha pubblicato:
    stop di 1-5 pip su EURUSD e GBPUSD, e sull'oro il 17/07/2024 stop a 2474
    con il livello a 2473,26 (`casi/CASO-004.md`).
    """
    crt = s.crt
    short = crt.verso is Verso.SHORT
    # Si vende in bid e si compra in ask, alla chiusura della candela che scatta.
    ingresso = float((basse.bid if short else basse.ask)[s.indice, CHIUSURA])
    if stop_stretto:
        margine = MARGINE_STOP_STRETTO * (s.turtle_soup_massimo - s.turtle_soup_minimo)
        stop = s.livello + margine if short else s.livello - margine
    else:
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


# Il tetto di sicurezza della simulazione, per timeframe del range: circa
# dieci candele alte.
TETTO = {TF.MN: 300 * 86400, TF.W1: 70 * 86400, TF.D1: 14 * 86400, TF.H4: 3 * 86400}


def scadenza(s: Scatto) -> int:
    """Il tetto di sicurezza: dopo, l'operazione si chiude al prezzo del momento."""
    return s.quando + TETTO[s.crt.alto_tf]
