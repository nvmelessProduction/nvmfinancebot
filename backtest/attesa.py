"""Quanto deve durare l'attesa fra i due tempi di CRT-13, misurato.

## La domanda

`ATTESA_MASSIMA_BARRE = 16` e' un numero unico per tutte le coppie, e il
commento che lo accompagna dice da dove viene: *"su `4h -> 15m` sedici quarti
d'ora sono quattro ore: la durata della candela di range"*. E' stato tarato
su UNA coppia.

`SETUP-04` pero' dice che un CRT non eseguito decade all'apertura di `N3`,
cioe' che l'attesa dura quanto la candela di range. Tradotto in candele del
timeframe di ingresso e' un numero DIVERSO per ogni coppia:

    M -> D        30        D -> 1h       24        1h -> 5m      12
    W -> 4h       42        4h -> 15m     16        15m -> 1m     15

Quindi 16 e' giusto per una coppia, generoso per due, e taglia le altre tre
fra il 33% e il 62%.

## Cosa misura questo file

Per ogni coppia e per ogni attesa candidata: quanti ingressi produce, con che
winrate e che R. Non decide niente -- stampa i numeri e basta, perche' la
scelta fra "pochi ingressi buoni" e "molti ingressi mediocri" non e' una cosa
che si deduce da una formula.

    ATTESE=15,16,24,32,48  COPPIA=TF_M15->TF_M1min  python backtest/attesa.py

Senza `ATTESE` prova il valore di `SETUP-04` per quella coppia e il 16
attuale, che e' il confronto minimo per sapere se il parametro conta.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ingresso_ltf
from core.parametri import COPPIE_CRT, DURATA_TF, UNIVERSO

from coppie_romeo import _carica, misura, Operazione  # type: ignore


def attesa_di_setup04(tf_range, tf_ingresso) -> int:
    """Le candele di ingresso che stanno dentro una candela di range."""
    return DURATA_TF[tf_range] // DURATA_TF[tf_ingresso]


def _riga(ops: list) -> str:
    chiuse = [o for o in ops if o.esito in ("vinta", "persa")]
    if not chiuse:
        return f"{len(ops):>6}      --        --         --"
    vinte = sum(1 for o in chiuse if o.esito == "vinta")
    somma = sum(o.erre for o in chiuse)
    return (f"{len(chiuse):>6} {100 * vinte / len(chiuse):>7.1f}% "
            f"{somma / len(chiuse):>+9.4f} {somma:>+10.1f}")


def main() -> int:
    db = os.environ.get("DB_PATH", "bot.db")
    solo = os.environ.get("COPPIA", "")
    coppie = [(r, i) for r, i in COPPIE_CRT.items()
              if not solo or f"{r.value}->{i.value}" == solo]

    grezzo = os.environ.get("ATTESE", "")
    originale = ingresso_ltf.ATTESA_MASSIMA_BARRE

    for tf_range, tf_ing in coppie:
        nome = f"{tf_range.value} -> {tf_ing.value}"
        giusta = attesa_di_setup04(tf_range, tf_ing)
        attese = ([int(x) for x in grezzo.split(",") if x.strip()]
                  if grezzo else sorted({originale, giusta}))

        print(f"\n=== {nome} ===")
        print(f"    attesa di SETUP-04: {giusta} candele   "
              f"(nel codice: {originale})")
        print(f"\n    {'attesa':>7} {'ingressi':>8} {'winrate':>8} "
              f"{'R medio':>10} {'R totale':>10}")
        print("    " + "-" * 47)

        # Lo storico si carica UNA volta sola: e' la parte lenta, e rileggerlo
        # per ogni attesa moltiplicherebbe i minuti senza cambiare un dato.
        storici = {s: _carica(s, db) for s in UNIVERSO}

        for attesa in attese:
            ingresso_ltf.ATTESA_MASSIMA_BARRE = attesa
            try:
                ops: list = []
                for strumento in UNIVERSO:
                    ops += misura(strumento, storici[strumento],
                                  tf_range, tf_ing, None, Counter())
                marchio = "  <- SETUP-04" if attesa == giusta else ""
                print(f"    {attesa:>7} {_riga(ops)}{marchio}", flush=True)
            finally:
                ingresso_ltf.ATTESA_MASSIMA_BARRE = originale
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
