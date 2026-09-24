"""Lo scaricamento dei minuti da Dukascopy, con bid e ask separati.

Un file per giorno UTC e per lato (BID, ASK), compresso LZMA. Ogni minuto e'
un record da 24 byte:

    secondi dall'inizio del giorno   int32
    apertura, chiusura, minimo, massimo   int32, in punti
    volume                           float32

Dukascopy riempie anche i minuti senza scambi, ripetendo l'ultimo prezzo con
volume zero: quei minuti si scartano (`spec/dati.md`).

Il ritmo e' gentile: una richiesta alla volta, una pausa fra una e l'altra, e
se Dukascopy risponde "troppe richieste" si aspetta sempre di piu'. Lo
scaricamento riprende da dove si era fermato.
"""

from __future__ import annotations

import lzma
import struct
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from nvm.dati.minuti import Minuti, file_del_mese

INDIRIZZO = "https://datafeed.dukascopy.com/datafeed/{strumento}/{anno:04d}/{mese0:02d}/{giorno:02d}/{lato}_candles_min_1.bi5"
RECORD = struct.Struct(">iiiiif")
LATI = ("BID", "ASK")


def indirizzo(strumento: str, giorno: date, lato: str) -> str:
    # Dukascopy conta i mesi da zero.
    return INDIRIZZO.format(
        strumento=strumento, anno=giorno.year, mese0=giorno.month - 1,
        giorno=giorno.day, lato=lato,
    )


def leggi_bi5(grezzo: bytes) -> np.ndarray:
    """Da un file bi5 a una tabella: secondi, apertura, massimo, minimo, chiusura, volume."""
    if not grezzo:
        return np.empty((0, 6))
    dati = lzma.decompress(grezzo)
    if len(dati) % RECORD.size:
        raise ValueError(f"file bi5 troncato: {len(dati)} byte")
    righe = [RECORD.unpack_from(dati, i) for i in range(0, len(dati), RECORD.size)]
    tabella = np.array(righe, dtype=np.float64)
    # Nel file l'ordine e' apertura, chiusura, minimo, massimo.
    return tabella[:, [0, 1, 4, 3, 2, 5]]


def minuti_del_giorno(strumento: str, giorno: date, bid: bytes, ask: bytes) -> Minuti:
    """I minuti con scambi di un giorno UTC, dai due file bi5."""
    b, a = leggi_bi5(bid), leggi_bi5(ask)
    if not len(b) or not len(a):
        return Minuti.vuoti(strumento)
    if len(b) != len(a) or np.any(b[:, 0] != a[:, 0]):
        raise ValueError(f"{strumento} {giorno}: bid e ask non hanno gli stessi minuti")
    con_scambi = (b[:, 5] > 0) | (a[:, 5] > 0)
    b, a = b[con_scambi], a[con_scambi]
    mezzanotte = int(datetime(giorno.year, giorno.month, giorno.day, tzinfo=timezone.utc).timestamp())
    return Minuti(
        strumento,
        mezzanotte + b[:, 0].astype(np.int64),
        b[:, 1:5].astype(np.int32),
        a[:, 1:5].astype(np.int32),
        b[:, 5].astype(np.float32),
        a[:, 5].astype(np.float32),
    )


class TroppeRichieste(RuntimeError):
    """Dukascopy continua a dire "troppe richieste" anche dopo le attese."""


@dataclass
class Scaricatore:
    """Scarica i file di Dukascopy con calma, e li tiene in una cache su disco."""

    cache: Path
    pausa: float = 0.5
    attese: tuple[float, ...] = (30, 60, 120, 240, 480)
    prendi: Optional[Callable[[str], bytes]] = None
    dormi: Callable[[float], None] = time.sleep
    richieste: int = field(default=0, init=False)

    def _prendi(self, url: str) -> bytes:
        if self.prendi is not None:
            return self.prendi(url)
        richiesta = urllib.request.Request(url, headers={"User-Agent": "nvmfinancebot/1.0"})
        with urllib.request.urlopen(richiesta, timeout=60) as risposta:
            return risposta.read()

    def file(self, strumento: str, giorno: date, lato: str, recente: bool = False) -> bytes:
        """Il file di un giorno e di un lato: dalla cache se c'e', se no da Dukascopy.

        Un giorno `recente` senza file non si ricorda come vuoto: Dukascopy
        pubblica con qualche ora di ritardo, e un vuoto in cache non si
        riscaricherebbe piu'.
        """
        percorso = self.cache / strumento / f"{giorno:%Y}" / f"{giorno:%m}" / f"{giorno:%d}_{lato}.bi5"
        if percorso.exists():
            return percorso.read_bytes()
        url = indirizzo(strumento, giorno, lato)
        for attesa in (*self.attese, None):
            try:
                self.richieste += 1
                grezzo = self._prendi(url)
                break
            except urllib.error.HTTPError as errore:
                if errore.code == 404:
                    grezzo = b""  # nessun file: giorno senza dati
                    break
                if errore.code not in (429, 500, 502, 503, 504):
                    raise
                if attesa is None:
                    raise TroppeRichieste(url) from errore
                self.dormi(attesa)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as errore:
                if attesa is None:
                    raise TroppeRichieste(url) from errore
                self.dormi(attesa)
            finally:
                self.dormi(self.pausa)
        if grezzo or not recente:
            percorso.parent.mkdir(parents=True, exist_ok=True)
            percorso.write_bytes(grezzo)
        return grezzo


def giorni_del_mese(anno: int, mese: int, fino_a: date) -> list[date]:
    """I giorni UTC da scaricare: tutti tranne il sabato, e mai oggi o dopo."""
    giorno = date(anno, mese, 1)
    giorni = []
    while giorno.month == mese and giorno < fino_a:
        if giorno.weekday() != 5:  # il sabato il mercato e' chiuso
            giorni.append(giorno)
        giorno += timedelta(days=1)
    return giorni


def scarica_mese(
    scaricatore: Scaricatore, radice: Path, strumento: str, anno: int, mese: int,
    oggi: Optional[date] = None,
) -> Path:
    """Scarica un mese e lo salva in un file solo. Un mese finito si scarica una volta."""
    oggi = oggi or datetime.now(timezone.utc).date()
    percorso = file_del_mese(radice, strumento, anno, mese)
    fine_mese = (date(anno, mese, 28) + timedelta(days=4)).replace(day=1)
    mese_finito = fine_mese <= oggi
    if percorso.exists() and mese_finito:
        return percorso
    pezzi = []
    for giorno in giorni_del_mese(anno, mese, oggi):
        recente = giorno >= oggi - timedelta(days=7)
        bid = scaricatore.file(strumento, giorno, "BID", recente)
        ask = scaricatore.file(strumento, giorno, "ASK", recente)
        pezzi.append(minuti_del_giorno(strumento, giorno, bid, ask))
    pezzi = [p for p in pezzi if len(p)]
    minuti = Minuti.unisci(pezzi) if pezzi else Minuti.vuoti(strumento)
    minuti.salva(percorso)
    return percorso


def mesi(dal: str, al: str) -> list[tuple[int, int]]:
    """I mesi da 'AAAA-MM' a 'AAAA-MM' compresi."""
    a0, m0 = map(int, dal.split("-"))
    a1, m1 = map(int, al.split("-"))
    elenco = []
    while (a0, m0) <= (a1, m1):
        elenco.append((a0, m0))
        a0, m0 = (a0 + 1, 1) if m0 == 12 else (a0, m0 + 1)
    return elenco


def scarica(
    strumenti: list[str], dal: str, al: str, radice: Path, cache: Path,
    scrivi: Callable[[str], None] = print,
) -> None:
    scaricatore = Scaricatore(cache)
    for strumento in strumenti:
        for anno, mese in mesi(dal, al):
            inizio = time.monotonic()
            percorso = scarica_mese(scaricatore, radice, strumento, anno, mese)
            n = len(Minuti.carica(percorso))
            scrivi(f"{strumento} {anno}-{mese:02d}: {n} minuti ({time.monotonic() - inizio:.0f} s)")
    scrivi(f"fatto: {scaricatore.richieste} richieste a Dukascopy")


if __name__ == "__main__":  # pragma: no cover
    sys.exit("usa: python scarica.py")
