"""Le coppie intraday di Romeo, misurate. E' qui che stanno le sue operazioni.

Il bot produceva 413 segnali in vent'anni; Romeo ne apre cinque o sei al
giorno. La differenza non era la configurazione: erano i **timeframe**. Le sue
coppie sono in maggioranza sotto l'ora, e senza dati al minuto il bot poteva
usare solo le tre piu' lente.

Questo modulo misura le tre che mancavano — `4h -> 15m`, `1h -> 5m`,
`15m -> 1m` — sulle stesse regole e con lo stesso costo delle altre.
"""
from __future__ import annotations

import bisect
import math
from datetime import timedelta
from typing import Callable, Optional, Sequence

from core.definizioni import Bias, Candela, cisd, peso_ombre


def aggrega(minuti: Sequence[Candela], quanti: int) -> list[Candela]:
    """Da candele al minuto a candele di `quanti` minuti.

    Il raggruppamento e' per **blocco di orologio**, non per conteggio: le
    candele a 5 minuti devono cadere su :00, :05, :10, altrimenti due
    esecuzioni dello stesso backtest su finestre diverse darebbero candele
    diverse, e nessun risultato sarebbe confrontabile.

    I minuti senza scambi mancano (volume zero, scartati a monte): un blocco
    puo' avere meno di `quanti` minuti, ed e' giusto cosi'. Inventare i minuti
    mancanti inventerebbe prezzi.
    """
    if quanti <= 0:
        return []
    gruppi: dict = {}
    for c in minuti:
        # L'orario della candela e' la CHIUSURA: il blocco e' quello del
        # minuto che l'ha aperta.
        apertura = c.orario - timedelta(minutes=1)
        # Minuti assoluti dall'epoca, poi diviso il blocco. La prima versione
        # usava `(data, ora, minuto // quanti)`, che per `quanti >= 60` da'
        # sempre `minuto // quanti == 0`: le candele a 4 ore e quelle
        # giornaliere venivano aggregate a UN'ORA, e i tre risultati
        # risultavano identici. Erano identici perche' erano la stessa cosa.
        assoluti = int(apertura.timestamp()) // 60
        gruppi.setdefault(assoluti // quanti, []).append(c)

    fuori = []
    for k in sorted(gruppi):
        p = gruppi[k]
        fuori.append(Candela(
            p[-1].orario, p[0].apertura,
            max(x.massimo for x in p), min(x.minimo for x in p), p[-1].chiusura,
        ))
    return fuori


def cerca_crt(alte: Sequence[Candela], mult: float = 3.0) -> list[tuple]:
    """Il CRT a due candele, con bersaglio a `mult` volte il rischio.

    `(indice, direzione, ingresso, stop, bersaglio, n1, n2)`.

    La chiusura di `N2` deve lasciare STRADA fino al bersaglio. Chiedere il
    contrario selezionerebbe i CRT gia' arrivati, che e' l'errore che in
    `canonico.py` produsse un falso "+19,9 sigma, 81% di winrate".
    """
    out = []
    for i in range(1, len(alte)):
        n1, n2 = alte[i - 1], alte[i]
        meta = (n1.massimo + n1.minimo) / 2
        if not (n1.minimo <= n2.chiusura <= n1.massimo):
            continue
        if n2.massimo > n1.massimo and n2.chiusura > meta:
            d, stop = Bias.SHORT, n2.massimo
        elif n2.minimo < n1.minimo and n2.chiusura < meta:
            d, stop = Bias.LONG, n2.minimo
        else:
            continue
        ing = n2.chiusura
        r = abs(ing - stop)
        if r <= 0:
            continue
        bers = ing - mult * r if d is Bias.SHORT else ing + mult * r
        out.append((i, d, ing, stop, bers, n1, n2))
    return out


def sigma(v: Sequence[float]) -> float:
    n = len(v)
    if n < 2:
        return 0.0
    m = sum(v) / n
    var = sum((x - m) ** 2 for x in v) / (n - 1)
    return m / math.sqrt(var / n) if var > 0 else 0.0


def misura(
    minuti_bid: Sequence[Candela],
    minuti_ask: Sequence[Candela],
    min_alto: int,
    min_basso: int,
    conferme: Optional[dict] = None,
    barre: int = 60,
    mult: float = 3.0,
) -> dict:
    """Una coppia intraday, dal minuto all'esito. Il costo e' lo spread vero."""
    conferme = conferme or {}
    alte = aggrega(minuti_bid, min_alto)
    basse = aggrega(minuti_bid, min_basso)
    if len(alte) < 10 or len(basse) < 10:
        return {"n": 0}

    t_basse = [c.orario for c in basse]
    t_ask = [c.orario for c in minuti_ask]
    t_bid = [c.orario for c in minuti_bid]

    res: list[float] = []
    costi: list[float] = []
    for (i, d, ing, stop, bers, n1, n2) in cerca_crt(alte, mult):
        j = bisect.bisect_right(t_basse, n2.orario)
        ingresso = basse[max(0, j - 12):j]

        if conferme.get("CRT-20"):
            p = peso_ombre(n2)
            if p is not None and p < 0.6:
                continue
        if conferme.get("CRT-11") and ingresso and cisd(ingresso, d) is None:
            continue

        ka = bisect.bisect_right(t_ask, n2.orario) - 1
        kb = bisect.bisect_right(t_bid, n2.orario) - 1
        if ka < 0 or kb < 0:
            continue
        sp = minuti_ask[ka].chiusura - minuti_bid[kb].chiusura
        rischio = abs(ing - stop)
        if not (0 < sp < rischio):
            continue

        costo = (2 * sp) / rischio
        erre = abs(bers - ing) / rischio
        esito = None
        for b in basse[j:j + barre]:
            if d is Bias.SHORT:
                if b.massimo >= stop:
                    esito = -1.0
                    break
                if b.minimo <= bers:
                    esito = erre
                    break
            else:
                if b.minimo <= stop:
                    esito = -1.0
                    break
                if b.massimo >= bers:
                    esito = erre
                    break
        if esito is None:
            seg = basse[j:j + barre]
            if not seg:
                continue
            sn = 1 if d is Bias.LONG else -1
            esito = sn * (seg[-1].chiusura - ing) / rischio
        res.append(esito - costo)
        costi.append(costo)

    if not res:
        return {"n": 0}
    giorni = max(1, (minuti_bid[-1].orario - minuti_bid[0].orario).days)
    return {
        "n": len(res),
        "al_giorno": len(res) / giorni * (7 / 5),   # solo giorni di mercato
        "winrate": 100 * sum(1 for x in res if x > 0) / len(res),
        "costo": sum(costi) / len(costi),
        "netto": sum(res) / len(res),
        "sigma": sigma(res),
    }
