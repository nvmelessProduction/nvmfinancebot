"""Carica candele da un file, quando la fonte non e' raggiungibile.

## Perche' esiste

Dukascopy limita gli indirizzi che chiedono troppo. Una macchina che ha
seminato vent'anni di storia, e poi ci e' tornata sopra per riempire dei
buchi, puo' trovarsi la porta chiusa per ore: prima 503, poi connessioni che
non si aprono affatto.

Quando succede non c'e' niente da aggiustare nel codice e niente da
aspettare con profitto -- ma le candele mancanti sono poche centinaia di
kilobyte, e si possono consegnare dentro il repository invece che chiederle
alla fonte. E' quello che fa questo script.

Non sostituisce la semina: `importa_dukascopy.py` e `importa_minuti.py`
restano il modo normale di riempire l'archivio, e quando la porta e' aperta
sono anche il modo migliore, perche' prendono tutto e non solo il pezzo che
qualcuno ha impacchettato.

## Il formato

Un CSV, eventualmente compresso, con una riga di intestazione:

    strumento,tf,chiusura_utc,apertura,massimo,minimo,chiusura
    EURUSD,TF_H1,2026-09-01T01:00:00Z,1.08542,1.08611,1.08530,1.08598

Il timeframe e' nella forma interna dell'archivio (`TF_H1`, `TF_M15`), che e'
la stessa con cui le candele sono scritte: cosi' il file si legge accanto a
`storage.candele_archiviate` senza conversioni per strada.

## Cosa NON fa

Non sovrascrive. `salva_candele` fa `INSERT OR IGNORE`, quindi una candela
gia' presente resta com'e': il pacchetto riempie i buchi e non tocca il
resto. Se serve sostituire una serie perche' viene da un'altra fonte, quello
lo fa `storage.dimentica_candele`, ed e' un'operazione diversa che va chiesta
apposta.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from collections import Counter
from pathlib import Path

from core import storage
from core.log import configura as configura_log
from core.parametri import TF

ORIGINE = "dukascopy"
INTESTAZIONE = "strumento,tf,chiusura_utc,apertura,massimo,minimo,chiusura"


def leggi(percorso: Path) -> list[dict]:
    """Le righe del pacchetto, scartando quelle che non si capiscono.

    Una riga storta si salta; un'intestazione sbagliata ferma tutto. La
    differenza e' che nel primo caso il file e' quello giusto con un difetto,
    nel secondo e' un altro file -- e caricare numeri presi da un altro file
    e' il genere di errore che poi si cerca per giorni.
    """
    apri = gzip.open if percorso.suffix == ".gz" else open
    fuori: list[dict] = []
    saltate = 0
    with apri(percorso, "rt", encoding="utf-8") as file:
        prima = file.readline().strip()
        if prima != INTESTAZIONE:
            raise SystemExit(
                f"{percorso}: intestazione inattesa.\n"
                f"  attesa:  {INTESTAZIONE}\n"
                f"  trovata: {prima}")
        for riga in file:
            pezzi = riga.strip().split(",")
            if len(pezzi) != 7:
                saltate += 1
                continue
            try:
                fuori.append({
                    "strumento": pezzi[0], "tf": pezzi[1],
                    "chiusura_utc": pezzi[2],
                    "apertura": float(pezzi[3]), "massimo": float(pezzi[4]),
                    "minimo": float(pezzi[5]), "chiusura": float(pezzi[6]),
                })
            except ValueError:
                saltate += 1
    if saltate:
        print(f"  {saltate} righe illeggibili, saltate")
    return fuori


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("percorso", nargs="?", default="dati/pacchetto-2026-09.csv.gz",
                   help="il file da caricare")
    scelte = p.parse_args()

    percorso = Path(scelte.percorso)
    if not percorso.exists():
        raise SystemExit(f"non trovo {percorso}")

    configura_log()
    storage.inizializza()

    print(f"carico {percorso}")
    righe = leggi(percorso)
    if not righe:
        raise SystemExit("il pacchetto non contiene nemmeno una candela")

    # I timeframe sconosciuti si fermano qui e non in archivio: una `tf`
    # scritta male entrerebbe come stringa e poi nessuno la leggerebbe mai,
    # perche' il motore cerca per nome esatto.
    validi = {t.value for t in TF}
    ignoti = {r["tf"] for r in righe} - validi
    if ignoti:
        raise SystemExit(f"timeframe sconosciuti nel pacchetto: {sorted(ignoti)}")

    per_gruppo = Counter((r["strumento"], r["tf"]) for r in righe)
    nuove, gia_viste = storage.salva_candele(righe, origine=ORIGINE)

    for (strumento, tf), quante in sorted(per_gruppo.items()):
        print(f"  {strumento:8s} {tf:9s} {quante:7d}")
    print(f"\n{nuove} candele nuove, {gia_viste} gia' presenti "
          f"(non sovrascritte).")
    if not nuove:
        print("Tutto quello che c'era nel pacchetto era gia' in archivio.")
    print("\nAdesso: python prova_giro.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
