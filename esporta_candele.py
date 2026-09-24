"""Esporta lo storico delle candele dall'archivio in `dati/candele/`.

Un file `STRUMENTO_TF.csv.gz` per ogni coppia strumento/timeframe, con tutte
le origini dentro (yahoo, dukascopy, mt5, mercato): l'archivio bot.db resta
fuori da git perche' contiene anche lo stato della macchina, ma le candele
sono dati che vale la pena avere al sicuro nel repository.

    python esporta_candele.py [percorso/bot.db]
"""
import csv
import gzip
import io
import sqlite3
import sys
from pathlib import Path

COLONNE = ["strumento", "tf", "chiusura_utc", "apertura", "massimo", "minimo",
           "chiusura", "origine", "ricevuta_utc"]


def main():
    db = Path(sys.argv[1] if len(sys.argv) > 1 else "bot.db")
    uscita = Path("dati/candele")
    uscita.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    coppie = con.execute(
        "SELECT DISTINCT strumento, tf FROM candela ORDER BY 1, 2").fetchall()
    for strumento, tf in coppie:
        righe = con.execute(
            f"SELECT {', '.join(COLONNE)} FROM candela "
            "WHERE strumento = ? AND tf = ? ORDER BY chiusura_utc, origine",
            (strumento, tf))
        file = uscita / f"{strumento}_{tf}.csv.gz"
        # mtime=0: lo stesso contenuto da' lo stesso file, e git non vede
        # modifiche finte a ogni esportazione.
        with open(file, "wb") as grezzo, \
                gzip.GzipFile(fileobj=grezzo, mode="wb", mtime=0) as gz, \
                io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(COLONNE)
            n = 0
            for r in righe:
                w.writerow(r)
                n += 1
        print(f"{file}  {n} candele")


if __name__ == "__main__":
    main()
