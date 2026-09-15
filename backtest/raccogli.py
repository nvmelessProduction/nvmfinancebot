"""Scansione una volta sola, con GEST-01 disattivato, e segnali su disco.

`GEST-01` e' un filtro sull'ultimo numero calcolato: scansionare a soglia zero
e scartare dopo da' gli stessi segnali che darebbe una scansione a 1.5, piu'
quelli che servono a misurare cosa cambierebbe abbassando la soglia. Il giro
sui prezzi e' l'unica parte cara: si fa una volta.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import core.contesto as ctx
from archivio import carica, indice_temporale
from esegui import scansiona
from core.parametri import UNIVERSO

USCITA = Path("segnali.pickle")


def main() -> int:
    ctx.RR_MINIMO = 0.0
    raccolto = {}
    for strumento, dati in UNIVERSO.items():
        storico = carica(dati.future)
        tempi = indice_temporale(storico)
        segnali, funnel = scansiona(strumento, dati.future, storico, tempi)
        raccolto[strumento] = {"segnali": segnali, "funnel": funnel}
        print(f"{strumento} ({dati.future}): {len(segnali)} segnali "
              f"(GEST-01 disattivato)", flush=True)
    USCITA.write_bytes(pickle.dumps(raccolto))
    print(f"\nscritto {USCITA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
