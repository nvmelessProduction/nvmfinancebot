"""Il bot si prende i dati da solo: niente alert da configurare a mano.

## Perche' esiste

La prima versione aspettava che TradingView bussasse con un webhook. Funziona,
ma costringe chi lo usa a creare un alert per ogni strumento e per ogni
timeframe, tenere aperto un tunnel con un indirizzo che cambia, e sbagliare
un ticker senza che nessuno lo dica. Sette strumenti per quattro timeframe
sono ventotto alert da rifare a ogni riavvio del tunnel.

Qui il verso e' rovesciato: **e' il bot che va a prendersi le candele**, dagli
stessi future di `PRIN-08`, con lo stesso codice gia' usato per seminare lo
storico. Sparisce il tunnel, sparisce il segreto del webhook, spariscono gli
alert, e sparisce la classe di errori "ticker non riconosciuto".

## Cosa NON cambia

L'architettura resta quella che i documenti prescrivono: **si analizza sul
future e si opera sul CFD** (`DEF-32`, `DEF-33`, `DEF-34`). Cambia solo il
mezzo con cui i prezzi del future arrivano: non piu' un webhook di
TradingView, ma una richiesta fatta dal bot allo stesso fornitore gratuito.
Nessun prezzo attraversa il confine, quindi `ESCL-12` regge esattamente come
prima. Da MT5 continuano ad arrivare solo conto ed esecuzione.

## Il cuore: solo candele chiuse, e una volta sola

Ogni giro chiede le barre recenti e scarta sempre l'ultima, che e' quella in
formazione (`ESCL-13`): `in_candele` fa gia' questo, ed e' lo stesso codice
collaudato dell'importatore. Cio' che resta sono candele **chiuse**.

Una candela chiusa che non era in archivio e' un fatto nuovo, e vale una
valutazione. Quelle gia' viste non si rivalutano: l'impronta dell'alert
(strumento, timeframe, chiusura) le riconosce, quindi anche se il ciclo
ripassa mille volte sullo stesso periodo, l'ordine parte una volta sola.

**Al riavvio non si recupera il passato.** Se il bot e' stato spento due
giorni, al ritorno trova venti candele nuove: le archivia tutte, ma valuta
**solo l'ultima**. Rivalutare le altre significherebbe decidere adesso su
prezzi di ieri e sparare venti ordini in fila.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import httpx

from core import storage
from core.log import diario
from core.models import AlertIn
from core.parametri import TF
from core.simboli import DXY_FUTURE, FUTURE_A_CFD

log = diario("mercato")

# Quanto dura un periodo di ciascun timeframe. Serve a chiedere una serie solo
# quando puo' essersi chiusa qualcosa di nuovo, invece che a ogni giro: e'
# gentilezza verso il fornitore e meno rumore nel diario.
DURATA: dict[TF, timedelta] = {
    TF.H1: timedelta(hours=1),
    TF.D1: timedelta(days=1),
    TF.W1: timedelta(days=7),
    TF.M1: timedelta(days=28),
}

# I timeframe su cui il bot puo' cercare un ingresso. Il fornitore gratuito
# non ha TF_H4, TF_H6 e TF_H12: quelli restano vuoti e le regole che li
# richiedono tacciono, dichiarandolo.
TF_OPERATIVI: tuple[TF, ...] = (TF.H1, TF.D1)

# Il ticker con cui il resto dell'impianto riconosce il future.
def ticker_di(future: str) -> str:
    """`GC` -> `GC1!`, la forma che `future_da_ticker` sa leggere."""
    return f"{future}1!" if future != DXY_FUTURE else DXY_FUTURE


@dataclass
class Nuova:
    """Una candela chiusa che l'archivio non aveva."""

    future: str
    tf: TF
    riga: dict


@dataclass
class Mercato:
    """Il ciclo che va a prendersi le candele, in un thread suo."""

    intervallo_sec: float = 60.0
    su_candela: Optional[Callable[[AlertIn], None]] = None
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    giri: int = field(default=0, init=False)
    candele_nuove: int = field(default=0, init=False)
    valutazioni: int = field(default=0, init=False)
    ultimo_errore: Optional[str] = field(default=None, init=False)

    # -- ciclo di vita ----------------------------------------------------
    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, name="mercato", daemon=True)
        self._thread.start()
        log.info("mercato avviato: il bot si prende i dati da solo ogni %.0fs",
                 self.intervallo_sec)

    def ferma(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._thread = None

    @property
    def in_funzione(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _ciclo(self) -> None:
        while not self._stop.is_set():
            try:
                self.giro()
            except Exception as errore:          # il ciclo non deve morire mai
                self.ultimo_errore = repr(errore)
                log.exception("giro di mercato fallito")
            self._stop.wait(self.intervallo_sec)

    # -- un giro ----------------------------------------------------------
    def giro(self, adesso: Optional[datetime] = None) -> list[Nuova]:
        """Un passaggio su tutte le serie che possono avere qualcosa di nuovo."""
        adesso = adesso or datetime.now(timezone.utc)
        self.giri += 1
        raccolte: list[Nuova] = []

        with httpx.Client(headers=_INTESTAZIONI, timeout=30.0, follow_redirects=True) as cliente:
            for future in _strumenti():
                for tf in DURATA:
                    if not self.serie_da_chiedere(future, tf, adesso):
                        continue
                    try:
                        raccolte.extend(self.aggiorna(future, tf, cliente))
                    except Exception as errore:
                        self.ultimo_errore = f"{future} {tf.value}: {errore!r}"
                        log.warning("aggiornamento fallito su %s %s: %s",
                                    future, tf.value, errore)

        self._valuta_le_ultime(raccolte)
        return raccolte

    def serie_da_chiedere(self, future: str, tf: TF, adesso: datetime) -> bool:
        """Ha senso chiedere questa serie adesso?

        Solo se dall'ultima candela in archivio e' passato abbastanza tempo
        perche' una nuova possa essersi chiusa. Un archivio vuoto si chiede
        sempre: e' il primo avvio.
        """
        righe = storage.candele_archiviate(future, tf.value, limite=1)
        if not righe:
            return True
        try:
            ultima = datetime.fromisoformat(str(righe[0]["chiusura_utc"]).replace("Z", "+00:00"))
        except ValueError:
            return True
        if ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
        return adesso - ultima >= DURATA[tf]

    def aggiorna(self, future: str, tf: TF, cliente) -> list[Nuova]:
        """Chiede una serie, archivia le candele chiuse che mancavano."""
        from importa_storico import in_candele
        from scarica_storico import DERIVATI, INTERVALLI, TICKER_FONTE, deriva, scarica

        if tf in DERIVATI:
            # Le mensili non si scaricano: la fonte le serve bucate. Si
            # costruiscono dalle giornaliere, che sono complete.
            righe, _ = deriva(future, tf, cliente)
        else:
            barre = scarica(TICKER_FONTE[future], INTERVALLI[tf], cliente)
            righe, _ = in_candele(barre, future, tf)
        if not righe:
            return []

        gia_viste = {
            str(r["chiusura_utc"])
            for r in storage.candele_archiviate(future, tf.value)
        }
        mancanti = [r for r in righe if str(r["chiusura_utc"]) not in gia_viste]
        if not mancanti:
            return []

        storage.salva_candele(mancanti, origine="mercato")
        self.candele_nuove += len(mancanti)
        log.info("%s %s: %d candele nuove in archivio", future, tf.value, len(mancanti))
        return [Nuova(future=future, tf=tf, riga=r) for r in mancanti]

    def _valuta_le_ultime(self, raccolte: list[Nuova]) -> None:
        """Una valutazione per serie, sulla candela piu' recente.

        Non si rivaluta il passato: se il bot e' stato spento, le candele
        arretrate entrano in archivio (servono alla storia) ma decidere adesso
        su prezzi di ieri sarebbe sbagliato, e farlo venti volte di fila
        sarebbe peggio.
        """
        if self.su_candela is None:
            return
        ultime: dict[tuple[str, TF], Nuova] = {}
        for nuova in raccolte:
            chiave = (nuova.future, nuova.tf)
            corrente = ultime.get(chiave)
            if corrente is None or nuova.riga["chiusura_utc"] > corrente.riga["chiusura_utc"]:
                ultime[chiave] = nuova

        for (future, tf), nuova in sorted(ultime.items(), key=lambda kv: kv[0][0]):
            if future == DXY_FUTURE:
                continue                 # PRIN-08: si analizza, non si opera
            if tf not in TF_OPERATIVI:
                continue                 # non e' un timeframe d'ingresso
            self.valutazioni += 1
            try:
                self.su_candela(in_alert(nuova))
            except Exception:
                log.exception("valutazione fallita su %s %s", future, tf.value)


def in_alert(nuova: Nuova) -> AlertIn:
    """Da candela chiusa a `AlertIn`, cosi' il resto dell'impianto non cambia.

    Tutto quello che sta a valle — archiviazione, impronta contro i duplicati,
    salvaguardie, esecuzione, notifica — e' gia' scritto e collaudato intorno
    a `AlertIn`. Costruirne uno invece di duplicare quel percorso e' il modo
    piu' sicuro di aggiungere una sorgente: il segreto e' quello configurato,
    perche' qui la richiesta nasce dentro casa e non da internet.
    """
    from core.config import impostazioni

    riga = nuova.riga
    return AlertIn(
        secret=impostazioni().WEBHOOK_SECRET,
        symbol=ticker_di(nuova.future),
        tf=nuova.tf.value.replace("TF_", ""),
        candle_close_time_utc=str(riga["chiusura_utc"]),
        open=float(riga["apertura"]),
        high=float(riga["massimo"]),
        low=float(riga["minimo"]),
        close=float(riga["chiusura"]),
        note="mercato",
    )


def _strumenti() -> tuple[str, ...]:
    """I sei future operativi piu' il DXY, che serve solo all'analisi."""
    return tuple(FUTURE_A_CFD) + (DXY_FUTURE,)


_INTESTAZIONI = {"User-Agent": "nvmfinancebot/1.0 (uso personale)"}

mercato = Mercato()
