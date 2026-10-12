"""Misura la base: tutti i CRT col manuale, sui prezzi veri, con i costi.

    python -m strumenti.misura                                  # le tre coppie orarie, 2006-2023
    python -m strumenti.misura --coppie D1-H1 --strumenti EURUSD --dal 2015-01
    python -m strumenti.misura --variante "chiusura dentro"
    python -m strumenti.misura --conferme                       # la base divisa in si'/no per ogni conferma

Gli anni 2024-2026 sono chiusi (`documenti/PIANO.md` §2): si aprono una volta sola,
nella Fase G, con --apri-holdout. Ogni misura va scritta in
`documenti/registro/tentativi.md`, anche quando va male.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nvm.agenti.cacciatore import Variante
from nvm.agenti.conferme import SOPRA, Contesto, contesto, key_level, orario
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO, carica_periodo
from nvm.dati.ore import carica as carica_ore
from nvm.prova.base import opera, riassumi
from nvm.prova.confronto import confronta
from nvm.tempo import TF

RADICE = Path(__file__).resolve().parent.parent
COPPIE = {"MN-D1": (TF.MN, TF.D1), "W1-H4": (TF.W1, TF.H4), "D1-H1": (TF.D1, TF.H1), "H4-M15": (TF.H4, TF.M15)}
# La variante "un gradino sotto" (spec/grilletto.md): stesso range, ingresso sul timeframe della coppia sotto.
COPPIE |= {"MN-H4": (TF.MN, TF.H4), "W1-H1": (TF.W1, TF.H1), "D1-M15": (TF.D1, TF.M15)}
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
    parser.add_argument("--conferme", action="store_true", help="dividi la base per ogni conferma (Fase E)")
    a = parser.parse_args()

    dal, al = _istante(a.dal), _istante(a.al, fine=True)
    if al > FINE_HOLDOUT_CHIUSO and not a.apri_holdout:
        parser.error("il 2024-2026 e' chiuso fino alla Fase G (documenti/PIANO.md §2): usa --al 2023-12")
    variante = Variante(a.variante)
    radice = Path(a.cartella)

    tutti, pareri_tutti = [], []
    for nome in a.coppie.split(","):
        alto, basso = COPPIE[nome]
        unita = "minuti" if basso is TF.M15 else "ore"
        risultati, pareri = [], []
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
            if a.conferme:
                sopra = costruisci(base, SOPRA[alto]).chiuse_entro(int(base.t[-1]) + base.passo)
                pareri += [
                    (key_level(x.scatto, sopra, basse), orario(x.scatto, basse), contesto(x.scatto, alte, sopra))
                    for x in r
                ]
        print(f"== {nome}, tutti gli strumenti: {riassumi(risultati).testo()}")
        if a.conferme:
            stampa_conferme(risultati, pareri)
        print()
        tutti += risultati
        pareri_tutti += pareri
    print(f"== TUTTO ({variante.value}): {riassumi(tutti).testo()}")
    if a.conferme:
        stampa_conferme(tutti, pareri_tutti)


def stampa_conferme(risultati, pareri) -> None:
    """Per ogni conferma, le operazioni col si' contro quelle col no."""
    noti = [i for i, p in enumerate(pareri) if p[0] is not None]
    r_kl = [risultati[i] for i in noti]
    kl = [pareri[i][0] for i in noti]
    print(f"   key level (risponde su {len(noti)} di {len(risultati)}):")
    for nome, si in (
        ("massimo", [k.massimo for k in kl]),
        ("arriva al massimo", [k.tocca for k in kl]),
        ("rejection block", [k.rejection_block for k in kl]),
        ("fvg", [k.fvg for k in kl]),
        ("almeno uno", [k.quanti >= 1 for k in kl]),
        ("almeno due", [k.quanti >= 2 for k in kl]),
    ):
        print(f"     {nome:17} {confronta(r_kl, np.array(si)).testo()}")
    ore = [p[1] for p in pareri]
    print("   orario:")
    print(f"     {'gct 9-13 NY':16} {confronta(risultati, np.array([o.gct for o in ore])).testo()}")
    erre = np.array([r.erre for r in risultati])
    scatto = np.array([o.ora_scatto for o in ore])
    righe = [f"{h:02d}:{int((scatto == h).sum())}/{erre[scatto == h].mean():+.2f}" for h in range(24) if (scatto == h).any()]
    print("     per ora NY dello scatto (ora:n/R medio):")
    for k in range(0, len(righe), 8):
        print("       " + "  ".join(righe[k:k + 8]))
    print("   bias (a favore del verso contro il resto; contro contro il resto):")
    for nome in ("range", "sopra"):
        lati = [None if p[2] is None else Contesto.dalla_parte(getattr(p[2], nome), r.verso) for p, r in zip(pareri, risultati)]
        print(f"     {nome + ' a favore':16} {confronta(risultati, np.array([x is True for x in lati])).testo()}")
        print(f"     {nome + ' contro':16} {confronta(risultati, np.array([x is False for x in lati])).testo()}")


if __name__ == "__main__":
    main()
