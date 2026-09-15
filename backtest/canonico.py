"""Il CRT come lo descrive la letteratura, misurato contro il placebo.

Serve a rispondere a una domanda sola: **i 26.285 "CRT" che il motore trova
sono davvero dei CRT?** Se il pattern canonico mostra un vantaggio dove quello
implementato non ne mostra, il problema e' a monte — nella lettura del
grafico — e non nella validita' della strategia.

## Il modello canonico

Cinque fonti indipendenti (MQL5, GrandAlgo, TradingFinder, WritOfFinance,
JustWolves) concordano su una struttura a tre candele **dello stesso
timeframe**:

```
C1  candela di range. Il suo massimo (CRH) e il suo minimo (CRL) SONO i livelli.
C2  candela di manipolazione: supera uno dei due estremi di C1 e RICHIUDE
    dentro il range di C1.
C3  candela di distribuzione: rompe l'estremo di C2 nella direzione opposta
    allo spazzamento. E' la conferma, ed e' li' che si entra.
```

Target: *«il 50% e' il primo bersaglio sicuro, la distribuzione finale punta
al lato opposto del range»* — cioe' entrambi misurati **sul range di C1**.

## Le tre differenze con l'implementazione attuale

| | canonico | motore |
|---|---|---|
| livello spazzato | l'estremo di `C1` stesso | key level di un TF **strettamente superiore** (`SETUP-00`, `DEF-30`) |
| conferma | `C3` rompe l'estremo di `C2` | nessuna: si entra all'apertura di `C3` (`SETUP-04`) |
| filtro extra | nessuno | `close[N2] < close[N1]` (`SETUP-02A`) |

La prima e' quella che pesa: pretendere che lo stesso spazzamento superi sia
l'estremo di `C1` sia un livello di un timeframe piu' alto e' una coincidenza
rara, e riduce i CRT di un paio di ordini di grandezza.

## Cosa NON fa questo file

Non applica bias di comando, allineamento, filtri di contesto o rapporto
minimo. Isola il **pattern**, perche' la domanda e' se il pattern porti
informazione. I filtri si aggiungono dopo, e solo a quelli che superano il
placebo.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

from core.definizioni import Bias, Candela, liv_50

ORIZZONTE = 60          # barre di vita massima di un'operazione
CAMPIONI = 10           # entrate a caso per ogni segnale


@dataclass(frozen=True)
class Segnale:
    indice: int
    direzione: Bias
    ingresso: float
    stop: float
    tp1: float
    target: float


def _dentro(valore: float, basso: float, alto: float) -> bool:
    return basso <= valore <= alto


def trova(serie: Sequence[Candela], conferma: bool, filtro_chiusura: bool) -> list[Segnale]:
    """I CRT canonici della serie.

    `conferma`: se True si entra solo quando `C3` rompe l'estremo di `C2`, al
    prezzo di quella rottura. Se False si entra all'apertura di `C3`, come fa
    il motore oggi (`SETUP-04`).

    `filtro_chiusura`: se True si aggiunge `close[C2] < close[C1]` per gli
    short (a specchio per i long), che il motore ha e il canonico no. Serve a
    misurare quanto costa o renda quella condizione in piu'.
    """
    fuori: list[Segnale] = []
    for i in range(1, len(serie) - 1):
        c1, c2, c3 = serie[i - 1], serie[i], serie[i + 1]

        # --- short: C2 spazza il massimo di C1 e richiude dentro ----------
        if c2.massimo > c1.massimo and _dentro(c2.chiusura, c1.minimo, c1.massimo):
            if not (filtro_chiusura and c2.chiusura >= c1.chiusura):
                ingresso = c3.apertura
                if conferma:
                    ingresso = c2.minimo if c3.minimo <= c2.minimo else None
                if ingresso is not None and c2.massimo > ingresso:
                    fuori.append(Segnale(i + 1, Bias.SHORT, ingresso,
                                         c2.massimo, liv_50(c1), c1.minimo))

        # --- long: a specchio ---------------------------------------------
        if c2.minimo < c1.minimo and _dentro(c2.chiusura, c1.minimo, c1.massimo):
            if not (filtro_chiusura and c2.chiusura <= c1.chiusura):
                ingresso = c3.apertura
                if conferma:
                    ingresso = c2.massimo if c3.massimo >= c2.massimo else None
                if ingresso is not None and c2.minimo < ingresso:
                    fuori.append(Segnale(i + 1, Bias.LONG, ingresso,
                                         c2.minimo, liv_50(c1), c1.massimo))
    return fuori


def risolvi(serie, partenza: int, direzione: Bias, ingresso: float,
            stop: float, tp1: float, target: float) -> Optional[float]:
    """Risultato in R. 25% a TP1 e il resto al lato opposto (GEST-04, SETUP-14).

    Stesse convenzioni prudenti del resto del backtest: dentro una barra, a
    parita', vince lo stop.
    """
    rischio = abs(ingresso - stop)
    if rischio == 0:
        return None
    erre_tp1 = abs(tp1 - ingresso) / rischio
    erre_fine = abs(target - ingresso) / rischio
    preso_tp1 = False
    livello = stop

    for barra in serie[partenza:partenza + ORIZZONTE]:
        if direzione is Bias.SHORT:
            colpito_stop = barra.massimo >= livello
            colpito_obiettivo = barra.minimo <= (target if preso_tp1 else tp1)
        else:
            colpito_stop = barra.minimo <= livello
            colpito_obiettivo = barra.massimo >= (target if preso_tp1 else tp1)

        if colpito_stop:
            return 0.25 * erre_tp1 if preso_tp1 else -1.0      # pareggio o stop
        if colpito_obiettivo:
            if preso_tp1:
                return 0.25 * erre_tp1 + 0.75 * erre_fine
            preso_tp1, livello = True, ingresso               # break even
    return 0.25 * erre_tp1 if preso_tp1 else 0.0


def placebo(serie, segnali, seme: int = 20260915) -> list[float]:
    """Le stesse geometrie, su barre di partenza estratte a caso."""
    caso = random.Random(seme)
    fuori: list[float] = []
    for s in segnali:
        r = abs(s.ingresso - s.stop) / s.ingresso
        t = abs(s.ingresso - s.tp1) / s.ingresso
        f = abs(s.ingresso - s.target) / s.ingresso
        for _ in range(CAMPIONI):
            i = caso.randrange(1, max(2, len(serie) - ORIZZONTE - 1))
            ap = serie[i].apertura
            if s.direzione is Bias.SHORT:
                esito = risolvi(serie, i, s.direzione, ap, ap*(1+r), ap*(1-t), ap*(1-f))
            else:
                esito = risolvi(serie, i, s.direzione, ap, ap*(1-r), ap*(1+t), ap*(1+f))
            if esito is not None:
                fuori.append(esito)
    return fuori


def confronta(nome: str, veri: list[float], finti: list[float]) -> str:
    if len(veri) < 2 or len(finti) < 2:
        return f"{nome}: campione troppo piccolo"
    mv, mf = statistics.fmean(veri), statistics.fmean(finti)
    ev = statistics.stdev(veri) / len(veri) ** 0.5
    ef = statistics.stdev(finti) / len(finti) ** 0.5
    diff = mv - mf
    errore = (ev ** 2 + ef ** 2) ** 0.5
    return (f"{nome:34s} n={len(veri):6d}  CRT {mv:+.4f}  a caso {mf:+.4f}  "
            f"vantaggio {diff:+.4f} ±{errore:.4f}  ({diff/errore:+5.2f} sigma)")
