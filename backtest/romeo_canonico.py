"""Il CRT con le due regole di selezione che mancavano.

## Cosa mancava

Le misure precedenti trattavano **ogni** candela come possibile range, e
cercavano lo sweep solo nella candela immediatamente successiva. Due fonti
dicono altro:

1. *«A CRT candle is a single candle that has both the highest high AND the
   lowest low over a user-defined period»* — non ogni candela e' un CRT: deve
   essere la **piu' ampia** del suo intorno, cioe' contenere massimo e minimo
   delle ultime `N`.

2. *«Inside bars that appear within a CRT represent the accumulation of
   interest around CRT. The greater the number of inside bars, the better the
   CRT»* — dopo la candela di range ci si aspetta **compressione dentro di
   essa**, e piu' e' lunga piu' il setup vale.

La seconda ha una conseguenza che le misure precedenti non potevano cogliere:
**lo sweep non arriva nella candela dopo, arriva dopo l'accumulazione**. Un
codice che guarda solo la candela successiva vede il pattern solo quando
l'accumulazione dura zero — cioe' nel caso peggiore, quello senza interesse
accumulato.

## Il modello

```
1. CANDELA CRT      la piu' ampia delle ultime N: contiene i loro massimi e minimi
2. ACCUMULAZIONE    una o piu' candele interamente dentro il suo range
3. MANIPOLAZIONE    una candela esce da un lato e RICHIUDE dentro
4. DISTRIBUZIONE    si va verso il lato opposto
```

La fase 3 invalida il setup se il prezzo **resta** fuori: *«a sweep that holds
beyond the range is a breakout, not a CRT»*.
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
    inside: int              # quante candele di accumulazione
    ampiezza_relativa: float # quanto la candela CRT e' piu' ampia della media


def candela_crt(serie: Sequence[Candela], i: int, periodo: int) -> bool:
    """La candela `i` ha massimo piu' alto e minimo piu' basso delle `periodo` precedenti."""
    if i < periodo:
        return False
    finestra = serie[i - periodo:i]
    return (serie[i].massimo > max(c.massimo for c in finestra)
            and serie[i].minimo < min(c.minimo for c in finestra))


def conta_inside(serie: Sequence[Candela], i: int, massimo_da_guardare: int) -> int:
    """Quante candele consecutive dopo `i` stanno interamente dentro il suo range."""
    n = 0
    for j in range(i + 1, min(i + 1 + massimo_da_guardare, len(serie))):
        if serie[j].massimo <= serie[i].massimo and serie[j].minimo >= serie[i].minimo:
            n += 1
        else:
            break
    return n


def _primo_oltre(direzione: Bias, ingresso: float, livelli) -> Optional[float]:
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
    periodo: int = 5,
    inside_minime: int = 0,
    attesa_massima: int = 6,
) -> list[Setup]:
    """I setup CRT con selezione della candela e accumulazione.

    `periodo`: quante candele la candela CRT deve contenere.
    `inside_minime`: quante candele di accumulazione servono prima dello sweep.
    `attesa_massima`: entro quante candele HTF dopo il range cercare lo sweep.
    """
    fuori: list[Setup] = []
    ampiezze = [c.massimo - c.minimo for c in htf]

    for i in range(len(htf) - 1):
        if not candela_crt(htf, i, periodo):
            continue
        rif = htf[i]
        alto, basso = rif.massimo, rif.minimo
        meta = (alto + basso) / 2.0
        ampiezza = alto - basso
        if ampiezza <= 0:
            continue

        inside = conta_inside(htf, i, attesa_massima)
        if inside < inside_minime:
            continue

        media = sum(ampiezze[max(0, i - periodo):i]) / max(1, min(periodo, i))
        relativa = ampiezza / media if media else 0.0

        # La finestra di esecuzione parte DOPO l'accumulazione: e' li' che
        # secondo il modello arriva la manipolazione.
        primo = i + inside + 1
        if primo >= len(htf):
            continue
        ultimo = min(primo + 1, len(htf) - 1)
        inizio = bisect_right(tempi_ltf, htf[primo - 1].orario)
        fine = bisect_right(tempi_ltf, htf[ultimo].orario)
        if fine - inizio < 2:
            continue

        for direzione in (Bias.SHORT, Bias.LONG):
            corto = direzione is Bias.SHORT
            picco: Optional[float] = None
            for k in range(inizio, fine):
                barra = ltf[k]
                if (barra.massimo > alto) if corto else (barra.minimo < basso):
                    picco = (max(picco, barra.massimo) if picco is not None else barra.massimo) \
                            if corto else \
                            (min(picco, barra.minimo) if picco is not None else barra.minimo)
                if picco is None:
                    continue
                rientrato = (barra.chiusura < alto) if corto else (barra.chiusura > basso)
                if not rientrato:
                    continue
                ingresso = barra.chiusura
                if not ((picco > ingresso) if corto else (picco < ingresso)):
                    break
                bersaglio = _primo_oltre(direzione, ingresso,
                                         (meta, basso) if corto else (meta, alto))
                if bersaglio is None:
                    break
                fuori.append(Setup(barra.orario, direzione, ingresso, picco, bersaglio,
                                   k + 1, abs(bersaglio - ingresso) / abs(ingresso - picco),
                                   inside, relativa))
                break
    return fuori
