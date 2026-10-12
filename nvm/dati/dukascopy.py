"""Lo scaricamento dei minuti da Dukascopy, con bid e ask separati.

Un file per giorno UTC e per lato (BID, ASK), compresso LZMA. Ogni minuto e'
un record da 24 byte:

    secondi dall'inizio del giorno   int32
    apertura, chiusura, minimo, massimo   int32, in punti
    volume                           float32

Dukascopy riempie anche i minuti senza scambi, ripetendo l'ultimo prezzo con
volume zero: quei minuti si scartano (`documenti/spec/dati.md`).

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
from nvm.dati.strumenti import STRUMENTI

INDIRIZZO = "https://datafeed.dukascopy.com/datafeed/{strumento}/{anno:04d}/{mese0:02d}/{giorno:02d}/{lato}_candles_min_1.bi5"
# Le ore: un file per mese, con i secondi contati dall'inizio del mese.
INDIRIZZO_ORE = "https://datafeed.dukascopy.com/datafeed/{strumento}/{anno:04d}/{mese0:02d}/{lato}_candles_hour_1.bi5"
RECORD = struct.Struct(">iiiiif")
LATI = ("BID", "ASK")


def _codice(strumento: str) -> str:
    """Il nome sul datafeed di Dukascopy (il petrolio WTI e' LIGHTCMDUSD, l'S&P 500 USA500IDXUSD...)."""
    s = STRUMENTI.get(strumento)
    return s.codice if s is not None else strumento


def indirizzo(strumento: str, giorno: date, lato: str) -> str:
    # Dukascopy conta i mesi da zero.
    return INDIRIZZO.format(
        strumento=_codice(strumento), anno=giorno.year, mese0=giorno.month - 1,
        giorno=giorno.day, lato=lato,
    )


def indirizzo_ore(strumento: str, anno: int, mese: int, lato: str) -> str:
    return INDIRIZZO_ORE.format(strumento=_codice(strumento), anno=anno, mese0=mese - 1, lato=lato)


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


def _da_bi5(strumento: str, origine: int, bid: bytes, ask: bytes, passo: int, cosa: str) -> Minuti:
    b, a = leggi_bi5(bid), leggi_bi5(ask)
    if not len(b) or not len(a):
        return Minuti.vuoti(strumento, passo)
    if len(b) != len(a) or np.any(b[:, 0] != a[:, 0]):
        raise ValueError(f"{strumento} {cosa}: bid e ask non hanno le stesse candele")
    con_scambi = (b[:, 5] > 0) | (a[:, 5] > 0)
    b, a = b[con_scambi], a[con_scambi]
    return Minuti(
        strumento,
        origine + b[:, 0].astype(np.int64),
        b[:, 1:5].astype(np.int32),
        a[:, 1:5].astype(np.int32),
        b[:, 5].astype(np.float32),
        a[:, 5].astype(np.float32),
        passo,
    )


def minuti_del_giorno(strumento: str, giorno: date, bid: bytes, ask: bytes) -> Minuti:
    """I minuti con scambi di un giorno UTC, dai due file bi5."""
    mezzanotte = int(datetime(giorno.year, giorno.month, giorno.day, tzinfo=timezone.utc).timestamp())
    return _da_bi5(strumento, mezzanotte, bid, ask, 60, str(giorno))


def ore_del_mese(strumento: str, anno: int, mese: int, bid: bytes, ask: bytes) -> Minuti:
    """Le ore con scambi di un mese UTC, dai due file bi5 orari."""
    inizio = int(datetime(anno, mese, 1, tzinfo=timezone.utc).timestamp())
    return _da_bi5(strumento, inizio, bid, ask, 3600, f"{anno}-{mese:02d}")


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
        return self._file(percorso, indirizzo(strumento, giorno, lato), recente)

    def file_ore(self, strumento: str, anno: int, mese: int, lato: str, recente: bool = False) -> bytes:
        """Il file orario di un mese e di un lato."""
        percorso = self.cache / strumento / "ore" / f"{anno:04d}-{mese:02d}_{lato}.bi5"
        return self._file(percorso, indirizzo_ore(strumento, anno, mese, lato), recente)

    def _file(self, percorso: Path, url: str, recente: bool) -> bytes:
        if percorso.exists():
            return percorso.read_bytes()
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


def giorni_del_mese(anno: int, mese: int, fino_a: date, sabato: bool = False) -> list[date]:
    """I giorni UTC da scaricare: tutti tranne il sabato (le crypto anche il sabato), e mai oggi o dopo."""
    giorno = date(anno, mese, 1)
    giorni = []
    while giorno.month == mese and giorno < fino_a:
        if sabato or giorno.weekday() != 5:  # il sabato il mercato e' chiuso, tranne le crypto
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
    crypto = strumento in STRUMENTI and STRUMENTI[strumento].famiglia == "crypto"
    for giorno in giorni_del_mese(anno, mese, oggi, sabato=crypto):
        recente = giorno >= oggi - timedelta(days=7)
        bid = scaricatore.file(strumento, giorno, "BID", recente)
        ask = scaricatore.file(strumento, giorno, "ASK", recente)
        pezzi.append(minuti_del_giorno(strumento, giorno, bid, ask))
    pezzi = [p for p in pezzi if len(p)]
    minuti = Minuti.unisci(pezzi) if pezzi else Minuti.vuoti(strumento)
    minuti.salva(percorso)
    return percorso


def scarica_ore_mese(
    scaricatore: Scaricatore, radice: Path, strumento: str, anno: int, mese: int,
    oggi: Optional[date] = None,
) -> Path:
    """Le ore di un mese, in un file solo. Dukascopy pubblica il file orario
    solo a mese finito: per il mese in corso servono i minuti."""
    oggi = oggi or datetime.now(timezone.utc).date()
    percorso = file_del_mese(radice, strumento, anno, mese)
    fine_mese = (date(anno, mese, 28) + timedelta(days=4)).replace(day=1)
    if percorso.exists():
        return percorso
    if fine_mese > oggi:
        raise ValueError(f"{anno}-{mese:02d} non e' ancora finito: il file orario non esiste")
    recente = fine_mese >= oggi - timedelta(days=7)
    bid = scaricatore.file_ore(strumento, anno, mese, "BID", recente)
    ask = scaricatore.file_ore(strumento, anno, mese, "ASK", recente)
    ore_del_mese(strumento, anno, mese, bid, ask).salva(percorso)
    return percorso


def completa_con_ask(scaricatore: Scaricatore, radice: Path, strumento: str, anno: int, mese: int) -> Optional[Path]:
    """Un mese col solo bid (`ore_bid`) diventa esatto (`ore`) scaricando solo l'ask.

    Il bid del vecchio archivio e' il BID di Dukascopy (verificato), quindi
    basta meta' delle richieste. Se all'ask manca anche una sola ora del bid,
    il mese non si salva: meglio stimato che sbagliato.
    """
    esatto = file_del_mese(radice / "ore", strumento, anno, mese)
    if esatto.exists():
        return esatto
    solo_bid = file_del_mese(radice / "ore_bid", strumento, anno, mese)
    if not solo_bid.exists():
        return None
    bid = Minuti.carica(solo_bid)
    tabella = leggi_bi5(scaricatore.file_ore(strumento, anno, mese, "ASK"))
    inizio = int(datetime(anno, mese, 1, tzinfo=timezone.utc).timestamp())
    istanti = inizio + tabella[:, 0].astype(np.int64)
    posizioni = np.searchsorted(istanti, bid.t)
    if not len(istanti) or np.any(posizioni >= len(istanti)) or np.any(istanti[np.minimum(posizioni, len(istanti) - 1)] != bid.t):
        return None
    ask = tabella[posizioni]
    Minuti(
        strumento, bid.t, bid.bid, ask[:, 1:5].astype(np.int32),
        bid.volume_bid, ask[:, 5].astype(np.float32), 3600,
    ).salva(esatto)
    return esatto


def mesi_a_campione(dal: str, al: str) -> list[tuple[int, int]]:
    """I mesi in un ordine che copre subito tutti gli anni: prima ogni gennaio,
    poi ogni luglio, poi aprile e ottobre, poi il resto."""
    priorita = {1: 0, 7: 1, 4: 2, 10: 2}
    return sorted(mesi(dal, al), key=lambda am: (priorita.get(am[1], 3), am[1], am[0]))


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
    ore: bool = False, pausa: float = 0.5, scrivi: Callable[..., None] = print,
) -> None:
    """Scarica minuti (o ore) per ogni strumento e ogni mese, riprendendo da dove era."""
    scaricatore = Scaricatore(cache, pausa=pausa)
    oggi = datetime.now(timezone.utc).date()
    for strumento in strumenti:
        for anno, mese in mesi(dal, al):
            inizio = time.monotonic()
            if ore:
                if (date(anno, mese, 28) + timedelta(days=4)).replace(day=1) > oggi:
                    continue  # il mese in corso non ha ancora il file orario
                percorso = scarica_ore_mese(scaricatore, radice, strumento, anno, mese, oggi)
            else:
                percorso = scarica_mese(scaricatore, radice, strumento, anno, mese, oggi)
            n = len(Minuti.carica(percorso))
            unita = "ore" if ore else "minuti"
            scrivi(f"{strumento} {anno}-{mese:02d}: {n} {unita} ({time.monotonic() - inizio:.0f} s)", flush=True)
    scrivi(f"fatto: {scaricatore.richieste} richieste a Dukascopy")


if __name__ == "__main__":  # pragma: no cover
    sys.exit("usa: python -m strumenti.scarica")
