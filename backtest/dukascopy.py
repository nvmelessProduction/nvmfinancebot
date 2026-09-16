"""Prezzi veri da Dukascopy: candele orarie, BID e ASK separati.

## Perche' questa fonte

Tutto il progetto ha misurato su barre di Yahoo. Il test sullo spot ha
mostrato cosa succede quando un feed ha gli estremi attenuati: il 37,7% degli
esiti cambia, e un vantaggio inesistente sembra reale. **Quel controllo non e'
mai stato fatto sulle barre dei future**, cioe' sul dato che regge ogni altra
conclusione.

Dukascopy serve i prezzi del proprio book: scambi veri, e soprattutto **BID e
ASK separati**. Due conseguenze:

- gli estremi sono quelli realmente toccati, non campionati;
- lo spread non si assume piu': si misura. Uno short si chiude in ask e un
  long in bid, ed e' esattamente la distinzione che `sentinella.livello_toccato`
  fa dal vivo.

## Il formato

`{SIMBOLO}/{anno}/{mese-1:02d}/BID_candles_hour_1.bi5`: un file al mese, LZMA,
record da 24 byte `>I4If`.

**L'ordine dei campi non e' OHLC**: e' (secondi dall'inizio del mese, **open,
close, low, high**, volume). Preso per OHLC produce candele che chiudono sopra
il proprio massimo — che e' come me ne sono accorto. I prezzi sono interi da
dividere per la scala del simbolo.

Un file al mese invece di 24 al giorno: vent'anni per sei strumenti sono circa
1.440 richieste invece di 700.000.
"""
from __future__ import annotations

import lzma
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

import httpx

from core.definizioni import Candela

BASE = "https://datafeed.dukascopy.com/datafeed"
CAPO = {"User-Agent": "nvmfinancebot/1.0 (ricerca, non commerciale)"}
DEPOSITO = Path("dukascopy")

# Quanto vale un'unita' intera nel formato. Lo yen e l'oro quotano a tre
# decimali, tutto il resto a cinque.
SCALA = {"USDJPY": 1e3, "XAUUSD": 1e3}
PREDEFINITA = 1e5


def scala_di(simbolo: str) -> float:
    return SCALA.get(simbolo, PREDEFINITA)


def _assicura_deposito() -> None:
    """La cartella della cache esiste, e se al suo posto c'e' altro lo dice.

    `mkdir(exist_ok=True)` fallisce con `WinError 183` quando esiste gia'
    qualcosa con quel nome che NON e' una cartella. E' successo davvero: un
    collegamento simbolico `dukascopy` era finito nel repository, e git su
    Windows lo scarica come un file di testo col percorso dentro.

    Il messaggio di `mkdir` in quel caso dice "impossibile creare un file
    quando quel file esiste gia'", che manda a cercare nella direzione
    sbagliata. Qui si dice cosa c'e' e cosa fare.
    """
    if DEPOSITO.is_dir():
        return
    if DEPOSITO.exists():
        raise SystemExit(
            f"'{DEPOSITO}' esiste ma NON e' una cartella. Cancellalo e "
            f"rilancia:\n    del {DEPOSITO}      (Windows)\n"
            f"    rm {DEPOSITO}       (Linux, macOS)"
        )
    DEPOSITO.mkdir(parents=True, exist_ok=True)


def _scarica(percorso: str, tentativi: int = 5) -> Optional[bytes]:
    """Un file, con attesa crescente sui 503. None se non esiste davvero."""
    cache = DEPOSITO / percorso.replace("/", "_")
    if cache.exists():
        return cache.read_bytes() or None
    _assicura_deposito()
    for n in range(tentativi):
        try:
            r = httpx.get(f"{BASE}/{percorso}", headers=CAPO, timeout=90,
                          follow_redirects=True)
            if r.status_code == 200:
                cache.write_bytes(r.content)
                return r.content or None
            if r.status_code == 404:
                cache.write_bytes(b"")          # assente per davvero
                return None
        except Exception:
            pass
        time.sleep(1.0 * (2 ** n))
    return None


def mese(simbolo: str, anno: int, mese_numero: int, lato: str = "BID") -> list[tuple]:
    """Le candele orarie di un mese: (orario di apertura, o, h, l, c)."""
    grezzo = _scarica(f"{simbolo}/{anno}/{mese_numero - 1:02d}/{lato}_candles_hour_1.bi5")
    if not grezzo:
        return []
    try:
        dati = lzma.LZMADecompressor().decompress(grezzo)
    except lzma.LZMAError:
        return []
    inizio = datetime(anno, mese_numero, 1, tzinfo=timezone.utc)
    s = scala_di(simbolo)
    fuori = []
    for i in range(0, len(dati) - 23, 24):
        salto, ap, chi, basso, alto, vol = struct.unpack(">I4If", dati[i:i + 24])
        if vol <= 0 and ap == alto == basso == chi:
            continue                            # ora senza scambi
        fuori.append((inizio + timedelta(seconds=salto),
                      ap / s, alto / s, basso / s, chi / s))
    return fuori


def orarie(simbolo: str, da: int, a: int) -> tuple[tuple[Candela, ...], tuple[Candela, ...]]:
    """Le orarie BID e ASK fra due anni, gia' marcate sulla CHIUSURA (DEF-02).

    Dukascopy marca le candele sull'APERTURA. `Candela.orario` e' la chiusura,
    quindi si somma un'ora: per le barre a passo fisso e' esatto, e non serve
    la scorciatoia di `orari_di_chiusura` che vale sui periodi irregolari.
    """
    fuori = {}
    for lato in ("BID", "ASK"):
        righe = []
        for anno in range(da, a + 1):
            for m in range(1, 13):
                righe.extend(mese(simbolo, anno, m, lato))
        righe.sort(key=lambda r: r[0])
        fuori[lato] = tuple(
            Candela(orario=t + timedelta(hours=1), apertura=o,
                    massimo=h, minimo=l, chiusura=c)
            for t, o, h, l, c in righe
            if l <= min(o, c) and h >= max(o, c)   # invariante di DEF-02
        )
    return fuori["BID"], fuori["ASK"]
