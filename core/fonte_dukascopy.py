"""La fonte di prezzi per il tempo reale: Dukascopy, non un feed aggregato.

## Perche' non la fonte gratuita

`core/mercato.py` prendeva le barre da una fonte gratuita che serve **barre
aggregate**. Misurato: quelle barre hanno gli **estremi attenuati**, cioe'
massimi e minimi campionati invece che realmente toccati.

Su una strategia a stop e bersaglio quel difetto non e' un dettaglio. Provato
risolvendo gli stessi segnali sui due insiemi di prezzi: il **37,7% degli
esiti cambiava**, e 274 vittorie diventavano perdite
(`docs/SPOT-CONTRO-FUTURE-2026-09-16.md`). Un bot che valuta su estremi
attenuati vede setup che non ci sono e non vede stop che sono stati toccati.

Dukascopy serve il proprio book: prezzi che qualcuno ha davvero pagato, BID e
ASK separati, estremi toccati. Sono gli stessi dati su cui ogni misura di
questo progetto e' stata fatta — e far girare il bot su dati diversi da quelli
su cui e' stato misurato e' il modo piu' silenzioso di invalidare la misura.

## Cosa serve sapere sul formato

File `.bi5`, uno per mese, compressi LZMA. Record di 24 byte, big-endian,
`>I4If`, e l'ordine dei campi **non e' OHLC**:

    (secondi_dall_inizio, apertura, CHIUSURA, MINIMO, MASSIMO, volume)

Me ne sono accorto perche' le chiusure cadevano sopra i massimi. Chi legge
questo file lo dara' per scontato: non lo e'.

Il mese e' **indicizzato da zero** nell'URL: gennaio e' `00`. Un fuori-di-uno
qui sposta tutta la serie di un mese e non produce alcun errore visibile.
"""

from __future__ import annotations

import lzma
import random
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

import httpx

from core.definizioni import Candela
from core.log import diario

log = diario("dukascopy")

BASE = "https://datafeed.dukascopy.com/datafeed"
CAPO = {"User-Agent": "nvmfinancebot/1.0"}

# I file mensili gia' presi restano su disco. Un mese chiuso non cambia piu',
# quindi richiederlo e' solo carico inutile sulla fonte -- e soprattutto:
# quando meta' dei mesi falliscono per 503, il rilancio deve riprendere da
# dove si era fermato invece di ricominciare da capo. Senza questa cache
# "rilancia finche' il messaggio non sparisce" era un consiglio che poteva
# non finire mai, perche' ogni giro rimetteva sotto sforzo anche i mesi gia'
# riusciti.
#
# Il mese IN CORSO non si mette in cache: cresce mentre lo si guarda.
DEPOSITO_ORE = Path("dukascopy_ore")

# Lo yen e l'oro quotano a tre decimali, tutto il resto a cinque.
SCALA: dict[str, float] = {"USDJPY": 1e3, "XAUUSD": 1e3}


def scala_di(simbolo: str) -> float:
    return SCALA.get(simbolo, 1e5)


def _decodifica(grezzo: bytes, inizio: datetime, scala: float) -> list[Candela]:
    """Da `.bi5` decompresso a candele. Scarta i record incoerenti."""
    fuori: list[Candela] = []
    for i in range(0, len(grezzo) - 23, 24):
        sec, ap, ch, mi, ma, vol = struct.unpack(">I4If", grezzo[i:i + 24])
        if vol <= 0 and ap == ch == mi == ma:
            continue                       # ora senza scambi
        ap, ch, mi, ma = ap / scala, ch / scala, mi / scala, ma / scala
        if not (mi <= min(ap, ch) and ma >= max(ap, ch)):
            continue                       # record rotto: si scarta, non si aggiusta
        # L'orario nel file e' l'APERTURA; le candele del motore portano la
        # chiusura, che e' un'ora dopo.
        fuori.append(Candela(
            inizio + timedelta(seconds=sec) + timedelta(hours=1), ap, ma, mi, ch
        ))
    return fuori


# Quali percorsi hanno risposto 404, cioe' "questo mese non esiste". Serve a
# `severo`: senza, un 404 e un guasto di rete sono indistinguibili da fuori,
# perche' entrambi tornano None.
_e_mancante: dict[str, bool] = {}


class Freno:
    """Un rallentatore condiviso da TUTTI i richiedenti insieme.

    Serve perche' l'attesa crescente del singolo tentativo non basta, e il
    motivo e' aritmetico: con dodici richieste in parallelo, quando la fonte
    protesta ognuna raddoppia la **propria** attesa, ma le altre undici
    continuano. La pressione complessiva non cala, i 503 si moltiplicano, e
    quel che si vede e' un muro di righe rosse in cui ogni singolo tentativo
    sta facendo la cosa giusta.

    E' successo due volte in questo progetto: nel ciclo dal vivo, dove aveva
    fatto smettere Dukascopy di rispondere del tutto, e poi di nuovo nel
    seminatore, dove avevo corretto il primo e lasciato il secondo.

    Qui l'attesa e' una sola, e vale per chiunque chieda. Raddoppia a ogni
    protesta e cala piano a ogni successo, cosi' si trova da sola il passo
    che la fonte accetta invece di indovinarlo a priori -- e il passo giusto
    non e' una costante: dipende da quanto quell'indirizzo ha gia' chiesto
    oggi, cosa che dallo script non si puo' sapere.
    """

    def __init__(self, attesa_minima: float = 0.0, attesa_massima: float = 20.0):
        self._lucchetto = threading.Lock()
        self._attesa = attesa_minima
        self._minima = attesa_minima
        self._massima = attesa_massima
        self._prossima = 0.0

    def aspetta(self) -> None:
        """Prende il proprio turno. Va chiamata PRIMA di ogni richiesta."""
        with self._lucchetto:
            adesso = time.monotonic()
            turno = max(adesso, self._prossima)
            # Un pizzico di casualita': senza, dopo una protesta tutti i
            # richiedenti ripartono nello stesso istante e la fonte riceve
            # di nuovo una raffica invece di un flusso.
            self._prossima = turno + self._attesa * random.uniform(0.85, 1.15)
        pausa = turno - time.monotonic()
        if pausa > 0:
            time.sleep(pausa)

    def protesta(self) -> None:
        """La fonte ha detto no: tutti rallentano, non solo chi ha chiesto."""
        with self._lucchetto:
            self._attesa = min(max(self._attesa * 2, 0.5), self._massima)

    def contento(self) -> None:
        """Una richiesta e' andata bene: si riaccelera, ma piano."""
        with self._lucchetto:
            self._attesa = max(self._attesa * 0.85, self._minima)

    @property
    def attesa(self) -> float:
        return self._attesa


freno = Freno()


def _con_tentativi(
    percorso: str, etichetta: str, tentativi: int = 5
) -> Optional[httpx.Response]:
    """Scarica con attesa crescente. `None` quando non c'e' nulla da avere.

    Due esiti vanno tenuti distinti e non lo sono di natura:

    - **404** e' una risposta: quel mese non esiste (futuro, o non ancora
      pubblicato). Non si ritenta, e non e' un errore.
    - **rete interrotta, 503, connessione chiusa a meta'** sono guasti
      temporanei. Dukascopy chiude le connessioni sotto carico, e un
      tunnel di rete puo' cadere a meta' trasferimento. Si ritenta.

    Trattarli allo stesso modo darebbe uno di due danni: o si martella un
    mese che non esistera' mai, o si rinuncia a un mese che c'e' per una
    connessione caduta — e il secondo lascia un buco nell'archivio che
    nessuno nota finche' il motore non valuta su una serie incompleta.
    """
    attesa = 1.0
    for n in range(tentativi):
        freno.aspetta()
        try:
            risposta = httpx.get(
                f"{BASE}/{percorso}", headers=CAPO, timeout=90, follow_redirects=True
            )
        except httpx.HTTPError as errore:
            freno.protesta()
            log.warning("%s: tentativo %d/%d fallito (%r)", etichetta, n + 1, tentativi, errore)
            time.sleep(attesa * random.uniform(0.85, 1.15))
            attesa *= 2
            continue

        if risposta.status_code == 404:
            _e_mancante[percorso] = True   # non esiste: non e' un guasto
            freno.contento()
            return None
        if risposta.status_code == 200:
            freno.contento()
            return risposta

        freno.protesta()
        log.warning("%s: HTTP %s, tentativo %d/%d (il freno e' a %.1fs)",
                    etichetta, risposta.status_code, n + 1, tentativi, freno.attesa)
        time.sleep(attesa * random.uniform(0.85, 1.15))
        attesa *= 2

    log.error("%s: nessun tentativo riuscito. L'archivio restera' incompleto "
              "su questo mese e il motore non deve valutarlo (CTX-10).", etichetta)
    return None


class MeseNonScaricato(Exception):
    """I tentativi sono finiti e il mese non e' arrivato.

    Esiste per separare due esiti che `orarie_del_mese` restituiva allo
    stesso modo -- una tupla vuota -- e che vogliono due reazioni opposte:

    - **il mese non c'e'** (404: e' nel futuro, o Dukascopy non l'ha ancora
      pubblicato). Chi semina va avanti;
    - **il mese non e' arrivato** (503 a raffica, connessione caduta). Chi
      semina ha in mano un archivio con un buco, e se lo tratta come "quel
      mese e' vuoto" produce una serie troncata dichiarando di aver
      finito. E' successo: un archivio del DXY fermo a 47 giorni fa, con
      scritto sotto "Fatto".

    Il ciclo dal vivo non la vuole -- per lui un giro a vuoto e' normale e
    riprova dopo -- quindi si alza solo con `severo=True`.
    """


def _scrivi_cache(percorso: Path, contenuto: bytes) -> None:
    """Mette da parte un mese chiuso. Un guasto qui non deve fermare nulla.

    La cache e' una comodita': se il disco e' pieno o la cartella non e'
    scrivibile, si continua a scaricare. Alzare un'eccezione qui farebbe
    fallire una semina che stava andando bene.
    """
    try:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(contenuto)
    except OSError as errore:
        log.debug("cache non scritta (%s): %r", percorso.name, errore)


def orarie_del_mese(
    simbolo: str, anno: int, mese: int, lato: str = "BID", severo: bool = False
) -> tuple[Candela, ...]:
    """Le candele orarie di un mese. Vuoto se il mese non esiste ancora.

    `mese` e' 1-12 come lo scrive un essere umano; l'URL vuole 0-11 e la
    conversione avviene qui, una volta sola.

    Con `severo` un mese che **non e' arrivato** alza `MeseNonScaricato`
    invece di sembrare vuoto: lo usa chi semina, per cui la differenza fra
    "non c'e'" e "non e' arrivato" e' la differenza fra un archivio completo
    e uno bucato.
    """
    percorso = (
        f"{simbolo}/{anno}/{mese - 1:02d}/{lato}_candles_hour_1.bi5"
    )
    etichetta = f"{simbolo} {anno}-{mese:02d}"

    adesso = datetime.now(timezone.utc)
    chiuso = (anno, mese) < (adesso.year, adesso.month)
    cache = DEPOSITO_ORE / percorso.replace("/", "_")

    if chiuso and cache.exists():
        contenuto = cache.read_bytes()
        if not contenuto:
            # Il vuoto in cache e' la memoria di un 404: quel mese non
            # esiste, e non va confuso con un mese non arrivato.
            _e_mancante[percorso] = True
            return ()
    else:
        risposta = _con_tentativi(percorso, etichetta)
        if risposta is None:
            if severo and not _e_mancante.get(percorso):
                raise MeseNonScaricato(etichetta)
            if chiuso:
                _scrivi_cache(cache, b"")      # 404 di un mese chiuso: definitivo
            return ()
        contenuto = risposta.content
        if chiuso:
            _scrivi_cache(cache, contenuto)

    if not contenuto:
        return ()

    try:
        grezzo = lzma.LZMADecompressor().decompress(contenuto)
    except lzma.LZMAError:
        log.warning("%s %d-%02d: file illeggibile", simbolo, anno, mese)
        if chiuso:
            cache.unlink(missing_ok=True)      # non ricordare un file rotto
        return ()

    inizio = datetime(anno, mese, 1, tzinfo=timezone.utc)
    return tuple(_decodifica(grezzo, inizio, scala_di(simbolo)))


def orarie_recenti(simbolo: str, mesi: int = 2) -> tuple[Candela, ...]:
    """Le candele orarie degli ultimi `mesi`, in ordine di tempo.

    E' cio' che serve al ciclo di mercato: non tutta la storia, che sta gia'
    in archivio, ma abbastanza da coprire qualunque buco lasciato da uno
    spegnimento. Due mesi bastano per un riavvio di un fine settimana e per
    chiudere l'ultima candela mensile.

    Dukascopy pubblica il mese corrente man mano: l'ultima candela puo' essere
    di poche ore fa. La candela **in formazione** non c'e' — il file contiene
    solo ore chiuse — ed e' esattamente quello che ESCL-13 vuole.
    """
    adesso = datetime.now(timezone.utc)
    fuori: list[Candela] = []
    for indietro in range(mesi, -1, -1):
        anno, mese = adesso.year, adesso.month - indietro
        while mese <= 0:
            mese += 12
            anno -= 1
        fuori.extend(orarie_del_mese(simbolo, anno, mese))
    fuori.sort(key=lambda c: c.orario)
    return tuple(fuori)
