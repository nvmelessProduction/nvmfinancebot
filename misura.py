"""Misura la base: tutti i CRT col manuale, sui prezzi veri, con i costi.

    python misura.py                                  # le tre coppie orarie, 2006-2023
    python misura.py --coppie D1-H1 --strumenti EURUSD --dal 2015-01
    python misura.py --variante "chiusura dentro"

Gli anni 2024-2026 sono chiusi (`PIANO.md` §2): si aprono una volta sola,
nella Fase G, con --apri-holdout. Ogni misura va scritta in
`registro/tentativi.md`, anche quando va male.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from nvm.agenti.cacciatore import Variante
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO, carica_periodo
from nvm.dati.ore import carica as carica_ore
from nvm.prova.base import opera, riassumi
from nvm.tempo import TF

RADICE = Path(__file__).resolve().parent
COPPIE = {"MN-D1": (TF.MN, TF.D1), "W1-H4": (TF.W1, TF.H4), "D1-H1": (TF.D1, TF.H1), "H4-M15": (TF.H4, TF.M15)}
FINE_HOLDOUT_CHIUSO = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
# Il range serve prima del periodo: un mese mensile piu' un margine.
MARGINE = 70 * 86400


def _istante(mese: str, fine: bool = False) -> int:
    anno, m = map(int, mese.split("-"))
    if fine:
        anno, m = (anno + 1, 1) if m == 12 else (anno, m + 1)
    return int(datetime(anno, m, 1, tzinfo=timezone.utc).timestamp())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--coppie", default="MN-D1,W1-H4,D1-H1")
    parser.add_argument("--strumenti", default=",".join(PUNTO))
    parser.add_argument("--dal", default="2006-01")
    parser.add_argument("--al", default="2023-12", help="ultimo mese compreso")
    parser.add_argument("--variante", default=Variante.MANUALE.value, choices=[v.value for v in Variante])
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--apri-holdout", action="store_true", help="solo nella Fase G, una volta")
    a = parser.parse_args()

    dal, al = _istante(a.dal), _istante(a.al, fine=True)
    if al > FINE_HOLDOUT_CHIUSO and not a.apri_holdout:
        parser.error("il 2024-2026 e' chiuso fino alla Fase G (PIANO.md §2): usa --al 2023-12")
    variante = Variante(a.variante)
    radice = Path(a.cartella)

    tutti = []
    for nome in a.coppie.split(","):
        alto, basso = COPPIE[nome]
        unita = "minuti" if basso is TF.M15 else "ore"
        risultati = []
        for strumento in a.strumenti.split(","):
            if unita == "ore":
                base, conti = carica_ore(radice, strumento, dal - MARGINE, al + MARGINE)
                nota = f" [mesi con ask vero {conti.esatti}, stimato {conti.stimati}, mancanti {conti.mancanti}]"
            else:
                base, nota = carica_periodo(radice / unita, strumento, dal - MARGINE, al + MARGINE), ""
            if not len(base):
                print(f"{nome} {strumento}: niente dati in {radice / unita}")
                continue
            alte = costruisci(base, alto).chiuse_entro(int(base.t[-1]) + base.passo)
            basse = costruisci(base, basso).chiuse_entro(int(base.t[-1]) + base.passo)
            r = opera(alte, basse, dal, al, variante)
            print(f"{nome} {strumento}{nota}: {riassumi(r).testo()}")
            risultati += r
        print(f"== {nome}, tutti gli strumenti: {riassumi(risultati).testo()}\n")
        tutti += risultati
    print(f"== TUTTO ({variante.value}): {riassumi(tutti).testo()}")


if __name__ == "__main__":
    main()
