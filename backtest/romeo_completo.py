"""Il modello di Romeo per intero, compreso il pezzo che mancava.

La sequenza completa, come la descrivono le fonti:

```
1. la candela HTF definisce il range      CRT-High / CRT-Low
2. il prezzo SPAZZA uno dei due lati      manipolazione
3. il prezzo RIENTRA nel range            la rottura era falsa
4. sull'LTF avviene un MARKET STRUCTURE   <-- IL GRILLETTO
   SHIFT nella direzione opposta
5. ingresso alla chiusura dello shift,
   oppure sul FVG lasciato dal movimento
6. stop oltre il wick dello sweep
7. bersaglio: EQ del range, poi il lato opposto
```

Il punto 4 e' quello che `romeo.py` salta, ed e' l'avvertimento esplicito
della letteratura: *«the lower-timeframe market structure shift is the
trigger. Entering on the raid alone front-runs the setup.»* Entrare sul solo
rientro significa comprare il coltello che cade.

## Come e' definito qui il market structure shift

Serve una definizione meccanica, perche' "structure shift" nei video e' un
giudizio a occhio. Quella adottata:

```
minimo protetto = il minimo piu' basso fatto sull'LTF dall'inizio della
                  finestra fino alla barra che ha spazzato
MSS short       = una barra LTF CHIUDE sotto il minimo protetto
```

E' la lettura piu' stretta possibile — chiusura, non ombra — e a specchio per
i long. Se ne esistono di migliori si cambia qui, in un posto solo.

## Il FVG come ingresso

Il movimento che produce lo shift lascia quasi sempre un vuoto di prezzo sulle
tre barre che lo compongono (`DEF-10`/`DEF-11`). Chi non e' entrato sullo
shift puo' aspettare il ritorno dentro quel vuoto: prezzo migliore, stop
uguale, quindi rapporto migliore. Costa pero' le operazioni che non tornano
mai indietro.
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
    indice_ltf: int
    rapporto: float


def _primo_oltre(direzione: Bias, ingresso: float, livelli: Sequence[float]) -> Optional[float]:
    for livello in livelli:
        if direzione is Bias.SHORT and livello < ingresso:
            return livello
        if direzione is Bias.LONG and livello > ingresso:
            return livello
    return None


def _fvg_dopo(ltf: Sequence[Candela], indice: int, direzione: Bias) -> Optional[float]:
    """Il bordo del vuoto lasciato dalle tre barre che finiscono in `indice`.

    Short: vuoto ribassista, `high[P3] < low[P1]`, si rientra sul bordo alto.
    """
    if indice < 2:
        return None
    p1, p3 = ltf[indice - 2], ltf[indice]
    if direzione is Bias.SHORT and p3.massimo < p1.minimo:
        return p1.minimo
    if direzione is Bias.LONG and p3.minimo > p1.massimo:
        return p1.massimo
    return None


def cerca(
    htf: Sequence[Candela],
    ltf: Sequence[Candela],
    tempi_ltf: Sequence,
    con_mss: bool = True,
    con_fvg: bool = False,
    attesa_fvg: int = 10,
) -> list[Setup]:
    """I setup del modello completo su una coppia di timeframe."""
    fuori: list[Setup] = []

    for i in range(len(htf) - 1):
        candela = htf[i]
        alto, basso = candela.massimo, candela.minimo
        meta = (alto + basso) / 2.0

        inizio = bisect_right(tempi_ltf, candela.orario)
        fine = bisect_right(tempi_ltf, htf[i + 1].orario)
        if fine - inizio < 3:
            continue

        for direzione in (Bias.SHORT, Bias.LONG):
            corto = direzione is Bias.SHORT
            picco: Optional[float] = None       # estremo dello sweep
            protetto: Optional[float] = None    # il livello che l'MSS deve rompere
            rientrato = False

            for k in range(inizio, fine):
                barra = ltf[k]

                # --- 2. manipolazione ------------------------------------
                # La stessa barra puo' spazzare E richiudere dentro: e' il caso
                # piu' comune, la candela con l'ombra oltre il livello. Va
                # aggiornata la manipolazione e POI valutato il rientro, senza
                # saltare alla barra dopo.
                if (barra.massimo > alto) if corto else (barra.minimo < basso):
                    if picco is None:
                        picco = barra.massimo if corto else barra.minimo
                        finestra = ltf[inizio:k + 1]
                        protetto = (min(c.minimo for c in finestra) if corto
                                    else max(c.massimo for c in finestra))
                    else:
                        picco = (max(picco, barra.massimo) if corto
                                 else min(picco, barra.minimo))

                if picco is None:
                    continue

                # --- 3. rientro nel range --------------------------------
                if not rientrato:
                    rientrato = (barra.chiusura < alto) if corto else (barra.chiusura > basso)
                    if not rientrato:
                        continue

                # --- 4. market structure shift ---------------------------
                if con_mss and protetto is not None:
                    rotto = (barra.chiusura < protetto) if corto else (barra.chiusura > protetto)
                    if not rotto:
                        continue

                ingresso, indice = barra.chiusura, k + 1

                # --- 5. variante: si aspetta il ritorno dentro il FVG -----
                if con_fvg:
                    bordo = _fvg_dopo(ltf, k, direzione)
                    if bordo is None:
                        break
                    trovato = None
                    for j in range(k + 1, min(k + 1 + attesa_fvg, fine)):
                        tocca = (ltf[j].massimo >= bordo) if corto else (ltf[j].minimo <= bordo)
                        if tocca:
                            trovato, indice = bordo, j + 1
                            break
                    if trovato is None:
                        break
                    ingresso = trovato

                if picco is None or not ((picco > ingresso) if corto else (picco < ingresso)):
                    break
                bersaglio = _primo_oltre(direzione, ingresso,
                                         (meta, basso) if corto else (meta, alto))
                if bersaglio is None:
                    break
                fuori.append(Setup(barra.orario, direzione, ingresso, picco, bersaglio,
                                   indice, abs(bersaglio - ingresso) / abs(ingresso - picco)))
                break                   # un setup per candela HTF e per direzione

    return fuori
