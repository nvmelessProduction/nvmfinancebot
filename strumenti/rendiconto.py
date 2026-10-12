"""Il rendiconto delle operazioni vere, dal libro a prova di manomissione (`nvm/vivo/libro.py`).

    python -m strumenti.rendiconto                     # sulla VPS: il libro del bot
    python -m strumenti.rendiconto --cartella dati/vps/vivo   # qui: il libro arrivato dalla VPS
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nvm.vivo import libro

RADICE = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "vivo"))
    a = parser.parse_args()
    print(libro.rendiconto(Path(a.cartella)))


if __name__ == "__main__":
    main()
