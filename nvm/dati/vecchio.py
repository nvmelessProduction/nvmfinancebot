"""Le orarie del vecchio archivio: il BID di Dukascopy dal 2006, senza ask.

Verificate il 24/09/2026 (`registro/verifica-dati-vecchi.md`): su gennaio-
luglio 2006 di EURUSD, 3.627 ore su 3.627 sono identiche al BID scaricato
da Dukascopy. Si prendono solo le righe con origine "dukascopy": nello
stesso archivio ci sono anche candele di MT5 e di Yahoo, che sono un'altra
fonte e non si mescolano (`spec/dati.md`).

L'ask qui non c'e': si mette uguale al bid, e chi carica questi mesi deve
sostituirlo con quello vero (`nvm.dati.ask`) o con lo spread misurato
(`nvm.dati.spread`).
"""

from __future__ import annotations

import csv
import gzip
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nvm.dati.minuti import PUNTO, Minuti, file_del_mese


def leggi(percorso: Path, strumento: str) -> Minuti:
    """Le ore "dukascopy" di un file `STRUMENTO_TF_H1.csv.gz` del vecchio archivio."""
    t, prezzi = [], []
    with gzip.open(percorso, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["origine"] != "dukascopy" or r["strumento"] != strumento:
                continue
            chiusura = datetime.strptime(r["chiusura_utc"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            t.append(int(chiusura.timestamp()) - 3600)
            prezzi.append([float(r[k]) for k in ("apertura", "massimo", "minimo", "chiusura")])
    ordine = np.argsort(t, kind="stable")
    t = np.array(t, np.int64)[ordine]
    punti = np.rint(np.array(prezzi)[ordine] / PUNTO[strumento]).astype(np.int32)
    tenuti = np.r_[True, np.diff(t) > 0]  # niente doppioni
    n = int(tenuti.sum())
    return Minuti(
        strumento, t[tenuti], punti[tenuti], punti[tenuti].copy(),
        np.ones(n, np.float32), np.zeros(n, np.float32), 3600,
    )


def salva_per_mese(ore: Minuti, radice: Path) -> int:
    """Un file per mese UTC, come quelli scaricati. Restituisce quanti file."""
    mesi = ore.t.astype("datetime64[s]").astype("datetime64[M]")
    n = 0
    for mese in np.unique(mesi):
        anno, m = int(str(mese)[:4]), int(str(mese)[5:7])
        dentro = mesi == mese
        Minuti(
            ore.strumento, ore.t[dentro], ore.bid[dentro], ore.ask[dentro],
            ore.volume_bid[dentro], ore.volume_ask[dentro], 3600,
        ).salva(file_del_mese(radice, ore.strumento, anno, m))
        n += 1
    return n


def leggi_grezzi(bid_csv: Path, ask_csv: Path, strumento: str) -> Minuti:
    """Le ore con bid e ask dai file .bi5 del vecchio bot, decodificati in csv.

    Sono i file di Dukascopy cosi' come sono (`dati/candele/grezzi/` sul
    vecchio branch): tutte le ore, anche quelle senza scambi, con il volume.
    Si tengono le ore dove almeno un lato ha scambiato, come in
    `nvm.dati.dukascopy`.
    """
    def tabella(percorso: Path) -> dict[int, tuple[list[float], float]]:
        righe = {}
        with gzip.open(percorso, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t = int(datetime.strptime(r["apertura_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
                righe[t] = ([float(r[k]) for k in ("apertura", "massimo", "minimo", "chiusura")], float(r["volume"]))
        return righe

    bid, ask = tabella(bid_csv), tabella(ask_csv)
    comuni = sorted(t for t in bid.keys() & ask.keys() if bid[t][1] > 0 or ask[t][1] > 0)
    punto = PUNTO[strumento]
    return Minuti(
        strumento,
        np.array(comuni, np.int64),
        np.rint(np.array([bid[t][0] for t in comuni]) / punto).astype(np.int32),
        np.rint(np.array([ask[t][0] for t in comuni]) / punto).astype(np.int32),
        np.array([bid[t][1] for t in comuni], np.float32),
        np.array([ask[t][1] for t in comuni], np.float32),
        3600,
    )
