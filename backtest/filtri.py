"""I filtri che la letteratura di Romeo dichiara, misurati uno per uno.

Nessuno di questi e' inventato. Ognuno viene da una fonte, citata qui sotto, e
viene applicato **da solo** al setup base per vedere quanto vale. Il bersaglio
e' dichiarato prima: servono **+7 punti percentuali di winrate** su
`TF_H4`->`TF_M15` per arrivare al pareggio.

| filtro | fonte |
|---|---|
| killzone Londra / New York | *«the range liquidity sweep should occur during the London session (3:00-6:00 AM NY) or New York session (8:30-11:30 AM)»* — TradingFinder |
| premium / discount | *«Bearish CRT is only valid if the sweep candle closes in the Premium Zone (above the 50% EQ), bullish only if it closes in the Discount Zone»* — GrandAlgo |
| confluenza con key level | *«when CRT-High coincides with prior day high/low or aligns with a session high, the setup gains a second layer of confluence and the win rate increases»* — GrandAlgo |
| sweep efficiente | *«a small wick relative to the candle body suggests the sweep absorbed liquidity efficiently»* — ICT Killzone |
| bias del timeframe superiore | *«always trade in line with market bias (Daily/Weekly)»* — thread CRT |
| inside bar | *«the integration of inside bars and key levels to enhance trading accuracy»* — CRT Secrets |

Il rischio del provarne sette e' che uno esca bene per caso. Per questo ogni
filtro si riporta comunque, anche quando peggiora, e il vincitore deve reggere
su una divisione del campione prima di essere creduto.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Optional, Sequence

from core.definizioni import Bias, Candela

# Ore UTC delle due killzone, con l'ora legale americana (UTC-4).
LONDRA = range(7, 10)          # 3:00 - 6:00 New York
NEWYORK = range(12, 16)        # 8:30 - 11:30 New York, arrotondato all'ora


def in_killzone(orario, ore: Sequence[int]) -> bool:
    return orario.hour in ore


def premium_discount(direzione: Bias, chiusura_sweep: float, eq: float) -> bool:
    """La barra che spazza deve chiudere dalla parte 'cara' del range.

    Short valido solo se chiude sopra l'equilibrio, long solo se sotto. E' la
    condizione che rende il 50% un bersaglio ancora davanti al prezzo.
    """
    return chiusura_sweep > eq if direzione is Bias.SHORT else chiusura_sweep < eq


def sweep_efficiente(picco: float, crt_livello: float, range_crt: float,
                     soglia: float = 0.25) -> bool:
    """Lo sweep ha superato il livello di poco rispetto al range spazzato.

    Un'ombra lunga dice che il prezzo e' andato oltre e ci e' rimasto: e'
    un'espansione, non una presa di liquidita'.
    """
    if range_crt <= 0:
        return False
    return abs(picco - crt_livello) / range_crt <= soglia


def vicino_a_livello(valore: float, livelli: Sequence[float], tolleranza: float) -> bool:
    """Il livello spazzato coincide con un massimo/minimo notevole."""
    return any(abs(valore - l) <= tolleranza for l in livelli if l is not None)


def e_inside(candela: Candela, precedente: Candela) -> bool:
    """La candela di riferimento e' contenuta nella precedente (DEF-22 di ICT)."""
    return candela.massimo <= precedente.massimo and candela.minimo >= precedente.minimo


def bias_da_candela(candela: Candela, precedente: Candela) -> Bias:
    """Bias grezza del timeframe: chiusura sopra o sotto la precedente.

    Deliberatamente povera: serve a dire da che parte guarda il timeframe
    superiore, non a costruire un modello. `DEF-16` ne ha una piu' ricca, ma
    qui si misura il filtro, non la definizione.
    """
    if candela.chiusura > precedente.massimo:
        return Bias.LONG
    if candela.chiusura < precedente.minimo:
        return Bias.SHORT
    return Bias.NESSUNA


def aggrega(fini: Sequence[Candela], minuti: int) -> tuple[Candela, ...]:
    """Raggruppa barre fini in barre da `minuti`, per indice di periodo UTC."""
    gruppi: dict[int, list[Candela]] = {}
    for c in fini:
        chiave = int((c.orario - timedelta(microseconds=1)).timestamp()) // (minuti * 60)
        gruppi.setdefault(chiave, []).append(c)
    return tuple(
        Candela(g[-1].orario, g[0].apertura, max(x.massimo for x in g),
                min(x.minimo for x in g), g[-1].chiusura)
        for g in (gruppi[k] for k in sorted(gruppi))
    )
