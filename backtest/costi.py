"""Spread e commissioni, e la size minima che un broker accetta.

Il backtest fin qui misurava un mondo senza attrito. Qui si aggiunge
l'attrito, e si aggiunge nel modo che pesa di piu' su questa strategia: gli
stop sono **stretti** — l'estremo di `N2` dista in media un decimo di punto
percentuale dall'ingresso — e su uno stop stretto il costo fisso di un giro
vale una frazione grande del rischio.

## Il conto, in forma adimensionale

Tutto e' espresso in **frazione di prezzo**, cosi' non serve sapere in che
valuta e' il conto e i future (che per `6J` e `6S` quotano il reciproco del
CFD) non creano confusione. `DEF-47` usa gia' questa forma per la size.

```
costo_relativo = spread / prezzo  +  commissione_giro / (contratto x prezzo)
costo_in_R     = costo_relativo / r          con r = |ingresso - stop| / ingresso
```

Lo spread si paga **una volta per giro** (si compra in ask e si vende in bid),
la commissione e' quella di andata e ritorno.

## I numeri, e da dove vengono

Valori tipici di un conto retail a spread grezzo tipo FP Markets, il broker
citato dai documenti. Sono **assunzioni**, non dati del tuo conto: cambiali
qui e la misura si rifa' da sola. `MOLTIPLICATORE` permette di vedere quanto
la conclusione dipende da questi numeri.

| CFD | spread | prezzo | contratto | comm. giro |
|---|---|---|---|---|
| XAUUSD | 0,25 | 4.700 | 100 oz | 6 $ |
| EURUSD | 0,00002 | 1,10 | 100.000 | 6 $ |
| GBPUSD | 0,00003 | 1,30 | 100.000 | 6 $ |
| AUDUSD | 0,00003 | 0,68 | 100.000 | 6 $ |
| USDCHF | 0,00003 | 0,85 | 100.000 | 6 $ |
| USDJPY | 0,003 | 155 | 100.000 | 6 $ |
"""
from __future__ import annotations

from dataclasses import dataclass

# Quanto moltiplicare i costi. 1.0 = conto a spread grezzo; 3.0 circa un conto
# a spread standard senza commissioni; 0.0 spegne i costi.
MOLTIPLICATORE: float = 1.0

# Il lotto minimo che un broker retail accetta.
LOTTO_MINIMO: float = 0.01


@dataclass(frozen=True)
class Strumento:
    spread: float          # in unita' di prezzo del CFD
    prezzo: float          # prezzo tipico del CFD
    contratto: float       # unita' per lotto standard
    commissione: float     # dollari per lotto standard, andata e ritorno
    valuta_base_e_dollaro: bool = True   # False per USDCHF e USDJPY

    @property
    def nozionale_per_lotto(self) -> float:
        """Nozionale in dollari di un lotto standard.

        Per `USDCHF` e `USDJPY` il contratto e' gia' in dollari: 100.000 USD
        contro franchi o yen. Per gli altri e' in valuta base, e va convertito.
        """
        if not self.valuta_base_e_dollaro:
            return self.contratto
        return self.contratto * self.prezzo

    @property
    def costo_relativo(self) -> float:
        """Costo di un giro completo, in frazione di prezzo."""
        spread = self.spread / self.prezzo
        commissione = self.commissione / self.nozionale_per_lotto
        return (spread + commissione) * MOLTIPLICATORE

    @property
    def nozionale_minimo(self) -> float:
        """Nozionale in dollari della posizione piu' piccola apribile."""
        return LOTTO_MINIMO * self.nozionale_per_lotto


TABELLA: dict[str, Strumento] = {
    "XAUUSD": Strumento(0.25, 4700.0, 100.0, 6.0),
    "EURUSD": Strumento(0.00002, 1.10, 100_000.0, 6.0),
    "GBPUSD": Strumento(0.00003, 1.30, 100_000.0, 6.0),
    "AUDUSD": Strumento(0.00003, 0.68, 100_000.0, 6.0),
    "USDCHF": Strumento(0.00003, 0.85, 100_000.0, 6.0, valuta_base_e_dollaro=False),
    "USDJPY": Strumento(0.003, 155.0, 100_000.0, 6.0, valuta_base_e_dollaro=False),
}


def costo_in_erre(strumento: str, ingresso: float, stop: float) -> float:
    """Quanto costa un giro completo, in multipli del rischio dell'operazione.

    E' il numero da sottrarre al risultato in R. Non dipende dalla size: sia il
    costo sia il rischio crescono con i lotti, e il rapporto resta.
    """
    dati = TABELLA[strumento]
    r = abs(ingresso - stop) / abs(ingresso)
    if r == 0:
        return float("inf")
    return dati.costo_relativo / r


def rischio_alla_size_minima(strumento: str, ingresso: float, stop: float) -> float:
    """Quanti dollari si rischiano con il lotto piu' piccolo apribile.

    Sotto una certa equity `RISK-01` diventa ineseguibile: l'1% del conto e'
    meno di quello che si rischia comunque aprendo il minimo, e `RISK-03`
    arrotonda per difetto a zero — cioe' non si opera mai.
    """
    dati = TABELLA[strumento]
    r = abs(ingresso - stop) / abs(ingresso)
    return r * dati.nozionale_minimo


def equity_minima(strumento: str, ingresso: float, stop: float, rischio: float = 0.01) -> float:
    """L'equity sotto la quale questa operazione non e' apribile a regola."""
    return rischio_alla_size_minima(strumento, ingresso, stop) / rischio
