"""Come sarebbe finita un'operazione, candela per candela, sui prezzi veri.

Le regole che fanno la differenza fra una misura onesta e una che si
autoconvince:

- **lo spread si paga dove il mercato lo faceva pagare.** Un long compra in
  ASK e chiude in BID; uno short vende in BID e chiude in ASK. Lo stop di uno
  short scatta quando l'ASK tocca il livello, non il bid;
- **se una candela tocca stop e target insieme, conta lo stop.** Dentro una
  candela non si sa cosa e' successo prima: si sceglie la lettura peggiore;
- **la candela del primo target non si riesamina contro lo stop nuovo.**
  Prima del primo target quello stop non esisteva (errore gia' fatto nel
  vecchio progetto);
- **se una candela apre gia' oltre lo stop** (un salto, di solito dopo il
  fine settimana), si esce all'apertura, non allo stop: lo stop non poteva
  essere eseguito a un prezzo che il mercato non ha mai fatto;
- **le commissioni si tolgono**, in R.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO

# Commissione di un giro (apertura e chiusura), in prezzo per unita' di
# strumento. Circa 7 dollari per lotto standard, come un conto RAW.
COMMISSIONE = {
    "EURUSD": 0.00007,
    "GBPUSD": 0.00007,
    "AUDUSD": 0.00007,
    "USDCHF": 0.00007,
    "USDJPY": 0.007,
    "XAUUSD": 0.07,
}


class Uscita(str, Enum):
    STOP = "stop"
    TARGET = "target"
    PAREGGIO = "pareggio"
    SCADUTA = "scaduta"


@dataclass
class Operazione:
    strumento: str
    verso: Verso
    # L'istante in cui l'ordine parte: le candele che aprono da qui in poi
    # decidono l'esito.
    quando: int
    ingresso: float
    stop: float
    tp1: float
    tp2: float
    # Quanta parte si chiude al primo target, e se il resto va a pareggio.
    parziale: float = 0.5
    pareggio: bool = True
    # Quando lo stop va a pareggio: arrivati a questa frazione del cammino fra
    # l'ingresso e il primo target (1 = al primo target, prima meno di 1, dopo
    # piu' di 1). La impara Livelli (`nvm/agenti/manopole.py`).
    pareggio_a: float = 1.0

    def __post_init__(self) -> None:
        segno = 1 if self.verso is Verso.LONG else -1
        if segno * (self.ingresso - self.stop) <= 0:
            raise ValueError("lo stop deve stare dalla parte opposta al guadagno")
        if segno * (self.tp1 - self.ingresso) <= 0 or segno * (self.tp2 - self.tp1) < 0:
            raise ValueError("i target devono stare davanti all'ingresso, il secondo non prima del primo")
        if not 0 <= self.parziale <= 1:
            raise ValueError("il parziale e' una frazione fra 0 e 1")

    @property
    def rischio(self) -> float:
        return abs(self.ingresso - self.stop)


@dataclass
class Esito:
    erre: float
    uscita: Uscita
    quando: int
    tp1_preso: bool
    costo_erre: float


def simula(op: Operazione, basse: Candele, scadenza: Optional[int] = None) -> Esito:
    """L'esito dell'operazione sulle candele basse, fino alla scadenza."""
    commissione = COMMISSIONE[op.strumento] / op.rischio
    long = op.verso is Verso.LONG
    segno = 1 if long else -1
    # Per chiudere un long si vende in bid, per chiudere uno short si compra in ask.
    lato = basse.bid if long else basse.ask

    i = int(np.searchsorted(basse.inizio, op.quando))
    j = len(basse) if scadenza is None else int(np.searchsorted(basse.inizio, scadenza))
    stop, tp1_preso, incassato = op.stop, False, 0.0
    aperta = 1.0

    def risultato(prezzo: float, uscita: Uscita, quando: int) -> Esito:
        erre = incassato + aperta * segno * (prezzo - op.ingresso) / op.rischio
        return Esito(erre - commissione, uscita, quando, tp1_preso, commissione)

    livello_pareggio = op.ingresso + op.pareggio_a * (op.tp1 - op.ingresso)
    for n in range(i, j):
        alto, basso = float(lato[n, MASSIMO]), float(lato[n, MINIMO])
        contro, favore = (basso, alto) if long else (alto, basso)
        stop_toccato = contro <= stop if long else contro >= stop
        if stop_toccato:
            uscita = Uscita.PAREGGIO if stop == op.ingresso else Uscita.STOP
            apertura = float(lato[n, APERTURA])
            prezzo = min(stop, apertura) if long else max(stop, apertura)
            return risultato(prezzo, uscita, int(basse.fine[n]))
        if segno * (favore - op.tp2) >= 0:
            return risultato(op.tp2, Uscita.TARGET, int(basse.fine[n]))
        if not tp1_preso and segno * (favore - op.tp1) >= 0:
            tp1_preso = True
            incassato += op.parziale * segno * (op.tp1 - op.ingresso) / op.rischio
            aperta -= op.parziale
        # Lo stop va a pareggio quando il prezzo arriva al livello scelto: vale dalla candela dopo.
        if op.pareggio and stop != op.ingresso and segno * (favore - livello_pareggio) >= 0:
            stop = op.ingresso
    ultima = j - 1
    if ultima < i:
        return risultato(op.ingresso, Uscita.SCADUTA, op.quando)
    return risultato(float(lato[ultima, CHIUSURA]), Uscita.SCADUTA, int(basse.fine[ultima]))
