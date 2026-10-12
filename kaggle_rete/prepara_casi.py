"""I casi della scuola dell'esperienza per tutti gli strumenti, dallo storico di HistData gia' scaricato.

    python -m kaggle_rete.prepara_casi CARTELLA_DATI casi.npz

Ogni strumento si divide nei pezzi buoni (`histdata.pezzi_buoni`), e i casi di ogni pezzo partono quando il pezzo ha
`MESI_PRIMA` mesi di storia (come gli istanti della scuola 2). Un processo per strumento.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from kaggle_rete.esperienza import casi, con_spread
from kaggle_rete.histdata import NOMI, pezzi_buoni
from nvm.dati.ore import carica
from nvm.tempo import utc

MESI_PRIMA = 41


def _uno(arg):
    radice, s = arg
    m, _ = carica(Path(radice), s, utc(1999, 1, 1), utc(2100, 1, 1), solo_bid=True)
    pezzi, _ = pezzi_buoni(m)
    fuori = []
    for p in pezzi:
        dal = np.datetime64(int(p.t[0]), "s").astype("datetime64[M]") + MESI_PRIMA
        dal = int(dal.astype("datetime64[s]").astype(np.int64))
        if dal >= int(p.t[-1]):
            continue
        c = casi(con_spread(p), dal, int(p.t[-1]) + 1, scrivi=lambda x: print(x, flush=True))
        fuori.append((s, int(p.t[0]), c))
    return fuori


def prepara(radice: Path, uscita: Path, strumenti=None, processi: int = 4) -> None:
    strumenti = list(strumenti or NOMI)
    with Pool(processi) as pool:
        tutti = [x for r in pool.imap_unordered(_uno, [(str(radice), s) for s in strumenti]) for x in r]
    tutti.sort(key=lambda x: (x[0], x[1]))
    np.savez_compressed(
        uscita,
        strumento=np.concatenate([np.full(len(c), s) for s, _, c in tutti]),
        pezzo_dal=np.concatenate([np.full(len(c), d, np.int64) for _, d, c in tutti]),
        t=np.concatenate([c.t for _, _, c in tutti]),
        scheda=np.concatenate([c.scheda for _, _, c in tutti]),
        erre=np.concatenate([c.erre for _, _, c in tutti]),
        uscita=np.concatenate([c.uscita for _, _, c in tutti]))
    print(f"{sum(len(c) for _, _, c in tutti)} casi in {uscita}", flush=True)


if __name__ == "__main__":
    prepara(Path(sys.argv[1]), Path(sys.argv[2]))
