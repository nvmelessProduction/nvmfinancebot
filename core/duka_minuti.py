"""I dati al MINUTO di Dukascopy: quelli su cui Romeo opera davvero.

## Perche' esistono, e perche' prima non c'erano

Il bot produceva 413 segnali in vent'anni. Romeo ne apre cinque o sei **al
giorno**. E' un fattore cento, e non e' una configurazione da aggiustare: e'
la prova che il bot stava facendo un'altra strategia.

La causa e' una sola. Le coppie di Romeo sono in maggioranza **intraday** —
`1h -> 5m`, `15m -> 1m`, `4h -> 15m` — e il bot aveva solo dati orari, quindi
poteva usare soltanto `M1 -> D1`, `W1 -> H4` e `D1 -> H1`. Tre coppie su
sette, e le tre piu' lente.

`DEF-01` ammette dieci timeframe e 1, 5 e 15 minuti non ci sono. Quel vincolo
e' stato sollevato esplicitamente: la strategia di Romeo viene prima dei
documenti che la descrivevano male.

## Il formato, e i due dettagli che ingannano

I minuti stanno in file **giornalieri**, non mensili:

    {SIMBOLO}/{ANNO}/{MESE}/{GIORNO}/BID_candles_min_1.bi5

- il **mese e' indicizzato da zero** — gennaio e' `00`;
- il **giorno no**, e' il numero di calendario.

La combinazione e' insolita e non l'ho dedotta: l'ho **provata**. In gennaio
2024 il file `00/06` ha zero minuti scambiati e il `00/07` ne ha 114. Il 6
gennaio 2024 e' un sabato e il 7 una domenica, che riapre alle 22:00 UTC. Con
il giorno indicizzato da zero i conti non tornerebbero.

Un fuori-di-uno qui sposterebbe l'intera serie di un giorno senza produrre
alcun errore visibile.

Ogni file ha **1440 record**, uno per minuto, anche di sabato: i minuti senza
scambi ci sono e hanno volume zero. Vanno scartati, non interpolati.
"""

from __future__ import annotations

import lzma
import struct
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.definizioni import Candela
from core.log import diario

log = diario("duka_minuti")

BASE = "https://datafeed.dukascopy.com/datafeed"
CAPO = {"User-Agent": "nvmfinancebot/1.0"}
DEPOSITO = Path("dukascopy_min")

SCALA: dict[str, float] = {"USDJPY": 1e3, "XAUUSD": 1e3}


def scala_di(simbolo: str) -> float:
    return SCALA.get(simbolo, 1e5)


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
    """Con cache su disco e attesa crescente. `None` = non c'e' nulla da avere.

    Un 404 e' una risposta (quel giorno non esiste); una connessione caduta e'
    un guasto. Il file vuoto in cache e' la memoria del 404, cosi' non si
    richiede mille volte un giorno che non esistera' mai.
    """
    cache = DEPOSITO / percorso.replace("/", "_")
    if cache.exists():
        dati = cache.read_bytes()
        return dati or None
    _assicura_deposito()

    attesa = 1.0
    for _ in range(tentativi):
        try:
            r = httpx.get(f"{BASE}/{percorso}", headers=CAPO,
                          timeout=90, follow_redirects=True)
        except httpx.HTTPError:
            time.sleep(attesa)
            attesa *= 2
            continue
        if r.status_code == 404:
            cache.write_bytes(b"")          # il giorno non esiste: ricordalo
            return None
        if r.status_code == 200:
            cache.write_bytes(r.content)
            return r.content or None
        time.sleep(attesa)
        attesa *= 2
    return None


def minuti_del_giorno(
    simbolo: str, giorno: date, lato: str = "BID"
) -> tuple[Candela, ...]:
    """Le candele al minuto di un giorno. Vuoto se chiuso o non disponibile."""
    percorso = (
        f"{simbolo}/{giorno.year}/{giorno.month - 1:02d}/{giorno.day:02d}"
        f"/{lato}_candles_min_1.bi5"
    )
    grezzo = _scarica(percorso)
    if not grezzo:
        return ()
    try:
        dati = lzma.LZMADecompressor().decompress(grezzo)
    except lzma.LZMAError:
        log.warning("%s %s: file illeggibile", simbolo, giorno)
        return ()

    scala = scala_di(simbolo)
    mezzanotte = datetime(giorno.year, giorno.month, giorno.day, tzinfo=timezone.utc)
    fuori: list[Candela] = []
    for i in range(0, len(dati) - 23, 24):
        sec, ap, ch, mi, ma, vol = struct.unpack(">I4If", dati[i:i + 24])
        if vol <= 0:
            continue                        # minuto senza scambi: si scarta
        ap, ch, mi, ma = ap / scala, ch / scala, mi / scala, ma / scala
        if not (mi <= min(ap, ch) and ma >= max(ap, ch)):
            continue                        # record rotto
        # L'orario nel file e' l'APERTURA; le candele portano la chiusura.
        fuori.append(Candela(
            mezzanotte + timedelta(seconds=sec) + timedelta(minutes=1),
            ap, ma, mi, ch,
        ))
    return tuple(fuori)


def minuti(simbolo: str, da: date, a: date, lato: str = "BID") -> tuple[Candela, ...]:
    """Tutti i minuti fra due date, in ordine. I fine settimana sono vuoti."""
    fuori: list[Candela] = []
    giorno = da
    while giorno <= a:
        fuori.extend(minuti_del_giorno(simbolo, giorno, lato))
        giorno += timedelta(days=1)
    return tuple(fuori)
