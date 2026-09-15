"""Il CRT come lo insegna @Romeotpt: range su HTF, esecuzione su LTF.

## Perche' questo file esiste

Le misure precedenti cercavano il CRT come **tre candele consecutive dello
stesso timeframe**, che e' come lo implementa `core/setup.py` e come lo
descrive `SETUP-01`. Con quella geometria l'operazione perde per costruzione:
si rischia l'intero range di `C2` per guadagnare quel che resta del range di
`C1`, e infatti la vincita media misurata era +0,27 R contro perdite da 1 R.

Il modello originale e' un altro. Romeo accoppia due timeframe:

```
CRT mensile      ->  ingresso sul giornaliero
CRT giornaliero  ->  ingresso su 1 ora
CRT su 4 ore     ->  ingresso su 15 minuti
CRT su 1 ora     ->  ingresso su 5 minuti
```

La candela HTF **e'** il range: il suo massimo e' `CRT-High`, il suo minimo
`CRT-Low`. Dentro la candela HTF **successiva** si svolge il Power of Three:
accumulazione, manipolazione (lo sweep di uno dei due estremi), distribuzione
verso il lato opposto. Lo sweep e il rientro si leggono sull'LTF.

## La differenza che conta: dove va lo stop

```
tre candele stesso TF   stop = estremo opposto di C2   -> largo
                        bersaglio = resto del range C1 -> stretto

Romeo (HTF + LTF)       stop = estremo del wick di sweep sull'LTF -> STRETTO
                        bersaglio = lato opposto del range HTF     -> LARGO
```

E' il rovescio esatto, ed e' la ragione per cui `GEST-01` ha senso: con questa
geometria un rapporto sopra 1,5 e' naturale, non impossibile.

## L'ingresso: Turtle Soup

Non si entra sullo sweep, si entra sul suo **fallimento**. Il prezzo supera
`CRT-High`, poi **richiude dentro il range** sull'LTF: quella richiusura e' la
prova che la rottura era falsa, ed e' il grilletto. Stop appena oltre il
massimo dello sweep, bersaglio l'EQ del range e poi il lato opposto.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional, Sequence

from core.definizioni import Bias, Candela


@dataclass(frozen=True)
class Setup:
    orario: object
    direzione: Bias
    ingresso: float
    stop: float
    bersaglio: float
    lato_opposto: float
    indice_ltf: int


def _primo_oltre(direzione: Bias, ingresso: float, livelli: Sequence[float]) -> Optional[float]:
    """Il primo livello ancora davanti all'ingresso. None se sono tutti dietro."""
    for livello in livelli:
        if direzione is Bias.SHORT and livello < ingresso:
            return livello
        if direzione is Bias.LONG and livello > ingresso:
            return livello
    return None


def cerca(
    htf: Sequence[Candela],
    ltf: Sequence[Candela],
    tempi_ltf: Sequence,
    una_sola: bool = True,
) -> list[Setup]:
    """I setup CRT di Romeo su una coppia di timeframe.

    Per ogni candela HTF si guarda cosa succede **dentro la candela HTF
    successiva**, barra LTF per barra LTF: se il prezzo spazza uno dei due
    estremi e poi richiude dentro il range, quello e' il setup.

    `una_sola`: al massimo un setup per candela HTF e per direzione. Il primo
    rientro e' il segnale; quelli dopo sono la stessa storia raccontata due
    volte.
    """
    fuori: list[Setup] = []

    for i in range(len(htf) - 1):
        candela = htf[i]
        alto, basso = candela.massimo, candela.minimo
        meta = (alto + basso) / 2.0

        inizio = bisect_right(tempi_ltf, candela.orario)
        fine = bisect_right(tempi_ltf, htf[i + 1].orario)
        if fine - inizio < 2:
            continue                       # non c'e' abbastanza LTF dentro l'HTF

        picco_alto: Optional[float] = None      # estremo dello sweep sopra CRT-High
        picco_basso: Optional[float] = None
        fatto_corto = fatto_lungo = False

        for k in range(inizio, fine):
            barra = ltf[k]

            # --- manipolazione sopra CRT-High -> si cerca uno short --------
            if barra.massimo > alto:
                picco_alto = barra.massimo if picco_alto is None else max(picco_alto, barra.massimo)
            if picco_alto is not None and not (una_sola and fatto_corto):
                if barra.chiusura < alto:               # rientro: turtle soup
                    obiettivo = _primo_oltre(Bias.SHORT, barra.chiusura, (meta, basso))
                    if obiettivo is not None and picco_alto > barra.chiusura:
                        fuori.append(Setup(barra.orario, Bias.SHORT, barra.chiusura,
                                           picco_alto, obiettivo, basso, k + 1))
                        fatto_corto = True

            # --- manipolazione sotto CRT-Low -> si cerca un long ----------
            if barra.minimo < basso:
                picco_basso = barra.minimo if picco_basso is None else min(picco_basso, barra.minimo)
            if picco_basso is not None and not (una_sola and fatto_lungo):
                if barra.chiusura > basso:
                    obiettivo = _primo_oltre(Bias.LONG, barra.chiusura, (meta, alto))
                    if obiettivo is not None and picco_basso < barra.chiusura:
                        fuori.append(Setup(barra.orario, Bias.LONG, barra.chiusura,
                                           picco_basso, obiettivo, alto, k + 1))
                        fatto_lungo = True

    return fuori
