"""Esecuzione con BID e ASK veri: lo spread non si assume, e' nei prezzi.

## Perche' cambia tutto

Finora il costo di un giro era una **stima**: uno spread tipico preso da un
listino, moltiplicato per un nozionale. Con le due serie di Dukascopy non
serve piu' stimare niente, perche' la meccanica reale e' gia' dentro i dati:

```
LONG    si compra in ASK   e si chiude in BID
SHORT   si vende  in BID   e si chiude in ASK
```

E' la stessa regola che `sentinella.livello_toccato` applica dal vivo, e
applicarla qui significa che lo spread viene pagato esattamente dove e quando
il mercato lo faceva pagare — allargato durante le news, stretto a mezzogiorno
di Londra, enorme alla riapertura della domenica.

Un costo medio non puo' rappresentare questo, perche' lo spread non e'
indipendente dal resto: si allarga proprio quando i prezzi corrono, cioe'
quando gli stop vengono presi.

## La conseguenza sullo stop

Uno stop short viene colpito quando **l'ASK** tocca il livello, non il bid. Su
uno stop stretto la differenza fra i due e' una frazione significativa della
distanza, e decide se l'operazione e' persa o no. E' il motivo per cui questa
misura puo' dare un risultato diverso da tutte le precedenti.
"""
from __future__ import annotations

from typing import Optional, Sequence

from core.definizioni import Bias, Candela


def allinea(bid: Sequence[Candela], ask: Sequence[Candela]) -> tuple[tuple, tuple]:
    """Le due serie ridotte agli istanti presenti in entrambe."""
    per_ask = {c.orario: c for c in ask}
    coppie = [(b, per_ask[b.orario]) for b in bid if b.orario in per_ask]
    return tuple(c[0] for c in coppie), tuple(c[1] for c in coppie)


def prezzo_ingresso(direzione: Bias, bid: Candela, ask: Candela) -> float:
    """Si entra dalla parte sfavorevole dello spread, sempre."""
    return bid.chiusura if direzione is Bias.SHORT else ask.chiusura


def risolvi(
    bid: Sequence[Candela],
    ask: Sequence[Candela],
    partenza: int,
    direzione: Bias,
    ingresso: float,
    stop: float,
    bersaglio: float,
    orizzonte: int,
) -> Optional[float]:
    """Il risultato in R, con lo spread pagato dove il mercato lo faceva pagare.

    A parita' dentro la barra vince lo stop: fra due letture possibili si
    prende la peggiore, perche' non si sa in che ordine il prezzo ci sia
    passato. E' la convenzione di tutto il progetto.
    """
    rischio = abs(ingresso - stop)
    if rischio == 0:
        return None
    guadagno = abs(bersaglio - ingresso) / rischio

    for i in range(partenza, min(partenza + orizzonte, len(bid))):
        if direzione is Bias.SHORT:
            # Si ricompra in ask: conta l'ASK per lo stop e per il bersaglio.
            if ask[i].massimo >= stop:
                return -1.0
            if ask[i].minimo <= bersaglio:
                return guadagno
        else:
            # Si rivende in bid.
            if bid[i].minimo <= stop:
                return -1.0
            if bid[i].massimo >= bersaglio:
                return guadagno
    return 0.0
