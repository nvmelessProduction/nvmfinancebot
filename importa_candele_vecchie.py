"""Importa le orarie Dukascopy del vecchio archivio (solo bid) in dati/grezzi/ore_bid.

    git show origin/claude/trading-bot-infrastructure-5rht0h:dati/candele/EURUSD_TF_H1.csv.gz > EURUSD_TF_H1.csv.gz
    python importa_candele_vecchie.py cartella_con_i_csv

Poi `python scarica.py --solo-ask` completa i mesi con l'ask vero, e
`nvm.dati.ore` usa lo spread misurato per quelli non ancora completati.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nvm.dati.minuti import PUNTO
from nvm.dati.vecchio import leggi, salva_per_mese

RADICE = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cartella = Path(sys.argv[1])
    for strumento in PUNTO:
        percorso = cartella / f"{strumento}_TF_H1.csv.gz"
        if not percorso.exists():
            print(f"{strumento}: manca {percorso.name}")
            continue
        ore = leggi(percorso, strumento)
        n = salva_per_mese(ore, RADICE / "dati" / "grezzi" / "ore_bid")
        print(f"{strumento}: {len(ore)} ore in {n} mesi")


if __name__ == "__main__":
    main()
