"""Esporta lo storico delle candele dall'archivio in `dati/candele/`.

Un file `STRUMENTO_TF.csv.gz` per ogni coppia strumento/timeframe, con tutte
le origini dentro (yahoo, dukascopy, mt5, mercato): l'archivio bot.db resta
fuori da git perche' contiene anche lo stato della macchina, ma le candele
sono dati che vale la pena avere al sicuro nel repository.

In `dati/candele/grezzi/` finiscono invece i `.bi5` in cache decodificati,
BID e ASK: `STRUMENTO_LATO_H1.csv.gz` e `STRUMENTO_LATO_M1.csv.gz`.

    python esporta_candele.py [percorso/bot.db]
"""
import csv
import gzip
import io
import lzma
import re
import sqlite3
import struct
import sys
from datetime import datetime, timedelta, timezone
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
    esporta_bi5(uscita / "grezzi")


# L'archivio tiene solo il BID: gli ASK orari servono a misurare lo spread e
# poi restano nei `.bi5` in cache, come le coppie del DXY (USDCAD, USDSEK).
# Qui si decodificano tutti, grezzi: orario di APERTURA come nel file, volume
# compreso, nessun record scartato.
CACHE_BI5 = ["dukascopy", "dukascopy_ore", "dukascopy_min"]
NOME_BI5 = re.compile(
    r"^([A-Z]+)_(\d{4})_(\d{2})(?:_(\d{2}))?_(BID|ASK)_candles_(hour|min)_1\.bi5$")
SCALA = {"USDJPY": 1e3, "XAUUSD": 1e3}


def esporta_bi5(uscita: Path):
    serie: dict[tuple, dict] = {}
    for cartella in CACHE_BI5:
        for file in sorted(Path(cartella).glob("*.bi5")) if Path(cartella).is_dir() else []:
            m = NOME_BI5.match(file.name)
            if not m:
                print(f"saltato, nome sconosciuto: {file}")
                continue
            simbolo, anno, mese0, giorno, lato, tf = m.groups()
            inizio = datetime(int(anno), int(mese0) + 1, int(giorno or 1),
                              tzinfo=timezone.utc)
            grezzo = file.read_bytes()
            if not grezzo:
                continue
            try:
                dati = lzma.LZMADecompressor().decompress(grezzo)
            except lzma.LZMAError:
                print(f"saltato, illeggibile: {file}")
                continue
            scala = SCALA.get(simbolo, 1e5)
            righe = serie.setdefault((simbolo, lato, "H1" if tf == "hour" else "M1"), {})
            for i in range(0, len(dati) - 23, 24):
                sec, ap, ch, mi, ma, vol = struct.unpack(">I4If", dati[i:i + 24])
                orario = (inizio + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
                # Lo stesso mese puo' stare in due cache: vince la prima.
                righe.setdefault(orario, (ap / scala, ma / scala, mi / scala,
                                          ch / scala, round(vol, 6)))
    uscita.mkdir(parents=True, exist_ok=True)
    for (simbolo, lato, tf), righe in sorted(serie.items()):
        file = uscita / f"{simbolo}_{lato}_{tf}.csv.gz"
        with open(file, "wb") as grezzo, \
                gzip.GzipFile(fileobj=grezzo, mode="wb", mtime=0) as gz, \
                io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["apertura_utc", "apertura", "massimo", "minimo",
                        "chiusura", "volume"])
            for orario in sorted(righe):
                w.writerow((orario, *righe[orario]))
        print(f"{file}  {len(righe)} candele")


if __name__ == "__main__":
    main()
