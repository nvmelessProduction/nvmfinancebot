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
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import httpx

from core.definizioni import Candela
from core.log import diario

log = diario("dukascopy")

BASE = "https://datafeed.dukascopy.com/datafeed"
CAPO = {"User-Agent": "nvmfinancebot/1.0"}

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
        try:
            risposta = httpx.get(
                f"{BASE}/{percorso}", headers=CAPO, timeout=90, follow_redirects=True
            )
        except httpx.HTTPError as errore:
            log.warning("%s: tentativo %d/%d fallito (%r)", etichetta, n + 1, tentativi, errore)
            time.sleep(attesa)
            attesa *= 2
            continue

        if risposta.status_code == 404:
            _e_mancante[percorso] = True   # non esiste: non e' un guasto
            return None
        if risposta.status_code == 200:
            return risposta

        log.warning("%s: HTTP %s, tentativo %d/%d",
                    etichetta, risposta.status_code, n + 1, tentativi)
        time.sleep(attesa)
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
    risposta = _con_tentativi(percorso, etichetta)
    if risposta is None:
        if severo and not _e_mancante.get(percorso):
            raise MeseNonScaricato(etichetta)
        return ()
    if not risposta.content:
        return ()

    try:
        grezzo = lzma.LZMADecompressor().decompress(risposta.content)
    except lzma.LZMAError:
        log.warning("%s %d-%02d: file illeggibile", simbolo, anno, mese)
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
