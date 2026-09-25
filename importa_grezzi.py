"""Importa le ore di Dukascopy con bid e ask dai file del vecchio bot.

    python importa_grezzi.py cartella_con_i_csv

La cartella contiene `STRUMENTO_BID_H1.csv.gz` e `STRUMENTO_ASK_H1.csv.gz`,
come `dati/candele/grezzi/` sul vecchio branch. Verificati il 24/09/2026:
identici, bid e ask, ai mesi scaricati direttamente da Dukascopy
(`registro/verifica-dati-vecchi.md`). Vanno in `dati/grezzi/ore/`, come
quelli scaricati.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nvm.dati.strumenti import BASE
from nvm.dati.vecchio import leggi_grezzi, salva_per_mese

RADICE = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cartella = Path(sys.argv[1])
    for strumento in BASE:
        bid, ask = cartella / f"{strumento}_BID_H1.csv.gz", cartella / f"{strumento}_ASK_H1.csv.gz"
        if not (bid.exists() and ask.exists()):
            print(f"{strumento}: mancano i file")
            continue
        ore = leggi_grezzi(bid, ask, strumento)
        n = salva_per_mese(ore, RADICE / "dati" / "grezzi" / "ore")
        print(f"{strumento}: {len(ore)} ore in {n} mesi")


if __name__ == "__main__":
    main()
