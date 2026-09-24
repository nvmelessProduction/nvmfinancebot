"""Importa i file di Dukascopy scaricati dal vecchio bot, senza riscaricarli.

Il vecchio bot teneva i file originali di Dukascopy in due cartelle:

    dukascopy/       EURUSD_2024_00_BID_candles_hour_1.bi5      (mese da zero)
    dukascopy_min/   EURUSD_2026_07_15_BID_candles_min_1.bi5

Sono gli stessi file che scarica `scarica.py`: qui si copiano nella cache
nuova con i nomi nuovi, e poi `scarica.py` li trova gia' li'. Un file vuoto
era il modo del vecchio bot di ricordare "Dukascopy non ce l'ha": si copia
cosi' com'e'.

    python importa_vecchi.py import/dukascopy-ore.zip import/dukascopy-minuti.zip
    python scarica.py --ore --dal 2006-01 --al 2026-08

Accetta cartelle o file zip.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from typing import Iterator

RADICE = Path(__file__).resolve().parent
CACHE = RADICE / "dati" / "grezzi" / "cache"

ORE = re.compile(r"([A-Z]{6})_(\d{4})_(\d{2})_(BID|ASK)_candles_hour_1\.bi5$")
MINUTI = re.compile(r"([A-Z]{6})_(\d{4})_(\d{2})_(\d{2})_(BID|ASK)_candles_min_1\.bi5$")


def destinazione(nome: str, cache: Path = CACHE) -> Path | None:
    """Dove va un file del vecchio bot nella cache nuova. None se non e' un file di Dukascopy."""
    nome = Path(nome).name
    if m := ORE.match(nome):
        strumento, anno, mese0, lato = m.groups()
        return cache / strumento / "ore" / f"{anno}-{int(mese0) + 1:02d}_{lato}.bi5"
    if m := MINUTI.match(nome):
        strumento, anno, mese0, giorno, lato = m.groups()
        return cache / strumento / anno / f"{int(mese0) + 1:02d}" / f"{giorno}_{lato}.bi5"
    return None


def _file(sorgente: Path) -> Iterator[tuple[str, bytes]]:
    if sorgente.is_dir():
        for percorso in sorted(sorgente.rglob("*.bi5")):
            yield percorso.name, percorso.read_bytes()
    else:
        with zipfile.ZipFile(sorgente) as archivio:
            for nome in sorted(archivio.namelist()):
                if nome.endswith(".bi5"):
                    yield nome, archivio.read(nome)


def importa(sorgenti: list[Path], cache: Path = CACHE) -> dict[str, int]:
    conti = {"copiati": 0, "gia_presenti": 0, "vuoti": 0, "ignorati": 0}
    for sorgente in sorgenti:
        for nome, contenuto in _file(sorgente):
            dove = destinazione(nome, cache)
            if dove is None:
                conti["ignorati"] += 1
                continue
            if dove.exists():
                conti["gia_presenti"] += 1
                continue
            dove.parent.mkdir(parents=True, exist_ok=True)
            dove.write_bytes(contenuto)
            conti["copiati"] += 1
            conti["vuoti"] += not contenuto
    return conti


def main() -> None:
    sorgenti = [Path(a) for a in sys.argv[1:]]
    if not sorgenti:
        sys.exit(__doc__)
    conti = importa(sorgenti)
    print(
        f"copiati {conti['copiati']} file ({conti['vuoti']} vuoti), "
        f"{conti['gia_presenti']} c'erano gia', {conti['ignorati']} non erano di Dukascopy"
    )


if __name__ == "__main__":
    main()
