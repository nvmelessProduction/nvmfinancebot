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
from typing import Optional, Sequence

import httpx

from core.definizioni import Candela
from core.fonte_dukascopy import freno
from core.log import diario
from core.parametri import TF

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


def _scarica(
    percorso: str, tentativi: int = 5, fresco: bool = False
) -> Optional[bytes]:
    """Con cache su disco e attesa crescente. `None` = non c'e' nulla da avere.

    Un 404 e' una risposta (quel giorno non esiste); una connessione caduta e'
    un guasto. Il file vuoto in cache e' la memoria del 404, cosi' non si
    richiede mille volte un giorno che non esistera' mai.

    `fresco` esiste per il **giorno in corso**, e la cache li' e' un veleno:
    Dukascopy pubblica il file di oggi man mano, quindi il primo scaricamento
    della giornata prende un file troncato. Metterlo in cache lo
    cristallizzerebbe — il bot leggerebbe per sempre una giornata che si
    ferma all'ora in cui e' partito, senza che nulla protesti. Con `fresco`
    la cache non si legge **e non si scrive**.
    """
    cache = DEPOSITO / percorso.replace("/", "_")
    if cache.exists() and not fresco:
        dati = cache.read_bytes()
        return dati or None
    _assicura_deposito()

    attesa = 1.0
    for _ in range(tentativi):
        # Lo stesso freno delle orarie, e per la stessa ragione: e' condiviso
        # fra tutti i richiedenti, quindi quando la fonte protesta rallenta
        # l'insieme e non solo chi ha preso il no. Con sedici lavoratori in
        # parallelo l'attesa del singolo non sposta niente.
        freno.aspetta()
        try:
            r = httpx.get(f"{BASE}/{percorso}", headers=CAPO,
                          timeout=90, follow_redirects=True)
        except httpx.HTTPError:
            freno.protesta()
            time.sleep(attesa)
            attesa *= 2
            continue
        if r.status_code == 404:
            freno.contento()
            if not fresco:
                cache.write_bytes(b"")      # il giorno non esiste: ricordalo
            return None
        if r.status_code == 200:
            freno.contento()
            if not fresco:
                cache.write_bytes(r.content)
            return r.content or None
        freno.protesta()
        time.sleep(attesa)
        attesa *= 2
    return None


def minuti_del_giorno(
    simbolo: str, giorno: date, lato: str = "BID", fresco: bool = False
) -> tuple[Candela, ...]:
    """Le candele al minuto di un giorno. Vuoto se chiuso o non disponibile.

    `fresco` salta la cache: lo usa il ciclo di mercato per il giorno in
    corso, che cambia mentre lo si guarda.
    """
    percorso = (
        f"{simbolo}/{giorno.year}/{giorno.month - 1:02d}/{giorno.day:02d}"
        f"/{lato}_candles_min_1.bi5"
    )
    grezzo = _scarica(percorso, fresco=fresco)
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


# Quanti blocchi da un minuto fa ciascun timeframe intraday.
BLOCCHI: dict[TF, int] = {TF.MIN1: 1, TF.MIN5: 5, TF.MIN15: 15}


def aggrega(
    minuti: Sequence[Candela], quanti: int, fino_a: Optional[datetime] = None
) -> list[Candela]:
    """Da candele al minuto a candele di `quanti` minuti.

    Sta qui, e non nello script di semina, perche' lo usano in due: la semina
    e il ciclo di mercato. Se le due aggregazioni divergessero, il bot
    valuterebbe candele di 15 minuti costruite in un modo e ne avrebbe in
    archivio di costruite in un altro — e la storia su cui il motore cerca il
    CISD non sarebbe piu' la stessa serie che gli arriva ora.

    Il raggruppamento e' su **minuti assoluti**, non su `(data, ora, minuto //
    quanti)`: quella forma, per blocchi da sessanta minuti in su, da' sempre
    zero e collassa tutto a un'ora. E' un errore che non produce eccezioni —
    produce candele sbagliate che sembrano giuste.

    I minuti senza scambi mancano gia' (volume zero, scartati a monte): un
    blocco puo' averne meno di `quanti`, ed e' giusto cosi'. Inventare i
    minuti mancanti inventerebbe prezzi.

    `fino_a` e' l'istante fino al quale i minuti sono noti, e serve a **non
    produrre l'ultima candela in formazione**. Alle 10:07 i minuti arrivano a
    10:06: senza questo filtro il blocco 10:00-10:15 uscirebbe lo stesso,
    fatto di sette minuti e datato 10:06. Sarebbe una candela da un quarto
    d'ora che non e' mai esistita, con un massimo e un minimo piu' stretti
    del vero, e finirebbe in archivio come le altre — `ESCL-13` vieta
    esattamente questo. Un blocco esce solo se il suo istante di chiusura e'
    gia' passato.
    """
    if quanti <= 0:
        return []
    gruppi: dict[int, list[Candela]] = {}
    for c in minuti:
        apertura = c.orario - timedelta(minutes=1)   # l'orario e' la CHIUSURA
        gruppi.setdefault(int(apertura.timestamp()) // 60 // quanti, []).append(c)

    fuori: list[Candela] = []
    for chiave in sorted(gruppi):
        if fino_a is not None:
            chiusura = datetime.fromtimestamp(
                (chiave + 1) * quanti * 60, tz=timezone.utc)
            if chiusura > fino_a:
                continue                     # blocco ancora aperto
        pezzi = gruppi[chiave]
        fuori.append(Candela(
            pezzi[-1].orario, pezzi[0].apertura,
            max(p.massimo for p in pezzi), min(p.minimo for p in pezzi),
            pezzi[-1].chiusura,
        ))
    return fuori


def orarie_dai_minuti(
    simbolo: str, da: date, a: date, oggi: Optional[date] = None
) -> list[Candela]:
    """Le candele ORARIE ricostruite dai file al minuto.

    ## Perche' serve

    Dukascopy pubblica i file orari **un mese alla volta, a mese chiuso**. Il
    mese in corso risponde `404`, non un file parziale: fino al primo del mese
    successivo quelle ore semplicemente non esistono come file orario.

    La conseguenza, se non si rimedia, e' che `H1`, `H4`, `D1` -- dove vive il
    range del CRT -- restano fermi all'ultimo giorno del mese scorso, per un
    tempo che cresce fino a trentun giorni. Il bot vedrebbe un grafico
    congelato senza che nulla lo dica, e con la protezione di
    `archivio_vecchio` si asterrebbe per quasi tutto il mese.

    I file al **minuto** invece sono giornalieri e ci sono anche per oggi.
    Un'ora sono sessanta minuti, e l'informazione c'e' tutta.

    ## Sono davvero le stesse candele?

    Misurato, non supposto: una settimana di agosto 2026 su `EURUSD`,
    ricostruita dai minuti e confrontata col file orario. **117 ore su 117
    identiche**, apertura massimo minimo e chiusura, scostamento zero.

    Era il risultato atteso -- il massimo di un'ora e' il massimo dei suoi
    minuti -- ma "atteso" e "verificato" non sono la stessa cosa, e qui in
    mezzo c'erano due aggregazioni e un fuso orario.

    `oggi` serve alle prove: il giorno in corso si riscarica sempre, gli altri
    vengono dalla cache.
    """
    oggi = oggi or datetime.now(timezone.utc).date()
    minuti: list[Candela] = []
    giorno = da
    while giorno <= a:
        if giorno.weekday() != 5:                 # il sabato e' chiuso
            minuti.extend(minuti_del_giorno(simbolo, giorno,
                                            fresco=(giorno >= oggi)))
        giorno += timedelta(days=1)
    if len(minuti) < 2:
        return []
    minuti.sort(key=lambda c: c.orario)
    # L'ultimo minuto si scarta (puo' essere incompleto) e `fino_a` scarta
    # l'ora ancora aperta: ESCL-13 vale qui come sui quarti d'ora.
    chiusi = minuti[:-1]
    return aggrega(chiusi, 60, fino_a=chiusi[-1].orario)
