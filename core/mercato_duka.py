"""Il ciclo di mercato su Dukascopy: le stesse candele su cui si e' misurato.

## Perche' esiste accanto a `core/mercato.py`

`core/mercato.py` prende barre aggregate da una fonte gratuita. Quelle barre
hanno gli **estremi attenuati** — massimi e minimi campionati invece che
toccati — e su una strategia a stop e bersaglio il difetto e' letale: risolti
gli stessi segnali sui due insiemi di prezzi, il **37,7% degli esiti
cambiava**.

Questo ciclo prende gli **stessi dati su cui ogni misura del progetto e'
stata fatta**. Far girare il bot su dati diversi da quelli su cui e' stato
misurato e' il modo piu' silenzioso di invalidare la misura: nessun test
fallisce, nessun log protesta, e i numeri promessi semplicemente non
arrivano.

## Lo strumento, detto chiaramente

Dukascopy serve il book di un broker, **non il future CME**. E' della stessa
famiglia del CFD su cui `DEF-34` fa eseguire, e per questo le candele si
archiviano sotto il nome del CFD (`EURUSD`) e non del future (`6E`).

E' uno scostamento da `DEF-32`, che vuole l'analisi sul future, ed e'
dichiarato invece che nascosto. Lo scambio e': si rinuncia al future e si
guadagnano estremi veri e spread misurato. Misurando, la seconda cosa pesa di
piu' — ma resta una scelta, non un fatto, e chi legge deve poterla ribaltare.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from core import storage
from core.definizioni import Candela
from core.fonte_dukascopy import orarie_recenti
from core.log import diario
from core.models import AlertIn
from core.parametri import TF, UNIVERSO

log = diario("mercato_duka")

# I timeframe che si costruiscono dalle orarie, e ogni quanto ha senso
# richiedere la serie. Chiedere piu' spesso e' solo rumore sul server.
DURATA: dict[TF, timedelta] = {
    TF.H1: timedelta(hours=1),
    TF.H4: timedelta(hours=4),
    TF.D1: timedelta(days=1),
    TF.W1: timedelta(days=7),
    TF.M1: timedelta(days=28),
}


def _giorno_di(momento: datetime) -> datetime:
    """La chiusura giornaliera: 22:00 UTC, cioe' le 17:00 di New York.

    E' la chiusura di sessione che il forex usa davvero. Usare la mezzanotte
    UTC spezzerebbe ogni giornata a meta' della sessione americana, e i range
    giornalieri — su cui vive `M1 -> D1` — sarebbero un'altra cosa.
    """
    limite = momento.replace(hour=22, minute=0, second=0, microsecond=0)
    return limite + timedelta(days=1) if momento > limite else limite


def _raggruppa(candele: list[Candela], chiave: Callable) -> list[Candela]:
    """Aggrega candele per una chiave, tenendo l'ordine del tempo."""
    gruppi: dict = {}
    for candela in candele:
        gruppi.setdefault(chiave(candela), []).append(candela)
    fuori = []
    for k in sorted(gruppi):
        pezzi = gruppi[k]
        fuori.append(Candela(
            pezzi[-1].orario, pezzi[0].apertura,
            max(p.massimo for p in pezzi), min(p.minimo for p in pezzi),
            pezzi[-1].chiusura,
        ))
    return fuori


def costruisci(orarie: list[Candela]) -> dict[TF, list[Candela]]:
    """Dalle orarie ai cinque timeframe che il motore usa.

    L'ultima oraria si scarta: Dukascopy pubblica il mese corrente man mano,
    e l'ultima riga di un file appena scritto puo' essere incompleta. ESCL-13
    vieta di valutare una candela in formazione, e qui non c'e' modo di
    saperlo dal dato — si scarta e basta.
    """
    if len(orarie) < 2:
        return {}
    chiuse = orarie[:-1]
    giornaliere = _raggruppa(chiuse, lambda c: _giorno_di(c.orario))
    return {
        TF.H1: chiuse,
        TF.H4: _raggruppa(chiuse, lambda c: (
            c.orario.date(), (c.orario.hour - 1) // 4)),
        TF.D1: giornaliere,
        TF.W1: _raggruppa(
            giornaliere,
            lambda c: (c.orario - timedelta(microseconds=1)).isocalendar()[:2],
        ),
        TF.M1: _raggruppa(giornaliere, lambda c: (
            (c.orario - timedelta(microseconds=1)).year,
            (c.orario - timedelta(microseconds=1)).month)),
    }


@dataclass
class MercatoDukascopy:
    """Il ciclo che tiene l'archivio aggiornato e fa scattare le valutazioni."""

    intervallo_sec: float = 900.0          # un quarto d'ora: le orarie bastano
    su_candela: Optional[Callable[[AlertIn], None]] = None
    segreto: str = ""

    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    giri: int = field(default=0, init=False)
    candele_nuove: int = field(default=0, init=False)
    valutazioni: int = field(default=0, init=False)
    ultimo_errore: Optional[str] = field(default=None, init=False)

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._ciclo, name="mercato-duka", daemon=True)
        self._thread.start()
        log.info("mercato Dukascopy avviato, ogni %.0fs", self.intervallo_sec)

    def ferma(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
        self._thread = None

    @property
    def in_funzione(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _ciclo(self) -> None:
        while not self._stop.wait(self.intervallo_sec):
            try:
                self.giro()
                self.ultimo_errore = None
            except Exception as errore:
                self.ultimo_errore = repr(errore)
                log.exception("giro di mercato fallito")

    def giro(self, adesso: Optional[datetime] = None) -> dict:
        """Un passaggio su tutti gli strumenti. Archivia, poi valuta.

        L'ordine conta ed e' quello di CTX-10: **prima** si aggiorna tutto,
        **poi** si valuta. Valutare uno strumento mentre un altro si aggiorna
        andrebbe bene; valutare un timeframe basso prima che il suo superiore
        sia aggiornato no, ed e' proprio cio' che questo ordine impedisce.
        """
        adesso = adesso or datetime.now(timezone.utc)
        self.giri += 1
        nuove_per_strumento: dict[str, dict[TF, Candela]] = {}

        for strumento in UNIVERSO:
            if self._stop.is_set():
                break
            try:
                nuove = self.aggiorna(strumento)
                if nuove:
                    nuove_per_strumento[strumento] = nuove
            except Exception as errore:
                self.ultimo_errore = f"{strumento}: {errore!r}"
                log.warning("aggiornamento fallito su %s: %r", strumento, errore)

        for strumento, per_tf in nuove_per_strumento.items():
            self._valuta(strumento, per_tf)

        return {
            "strumenti": len(nuove_per_strumento),
            "candele_nuove": self.candele_nuove,
            "valutazioni": self.valutazioni,
        }

    def aggiorna(self, strumento: str) -> dict[TF, Candela]:
        """Scarica le orarie recenti e archivia cio' che manca.

        Restituisce, per ogni timeframe, l'ULTIMA candela davvero nuova: e'
        quella che fa scattare una valutazione. Le arretrate entrano in
        archivio — servono alla storia — ma non si valutano: dopo uno
        spegnimento di una settimana ci sarebbero sette valutazioni su prezzi
        vecchi, e sette ordini.
        """
        orarie = list(orarie_recenti(strumento, mesi=2))
        if not orarie:
            return {}

        ultime: dict[TF, Candela] = {}
        for tf, candele in costruisci(orarie).items():
            if not candele:
                continue
            righe = [{
                "strumento": strumento, "tf": tf.value,
                "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apertura": c.apertura, "massimo": c.massimo,
                "minimo": c.minimo, "chiusura": c.chiusura,
            } for c in candele]
            nuove, _ = storage.salva_candele(righe, origine="dukascopy")
            self.candele_nuove += nuove
            if nuove:
                ultime[tf] = candele[-1]
        return ultime

    def _valuta(self, strumento: str, per_tf: dict[TF, Candela]) -> None:
        """Fa scattare una valutazione per ogni timeframe operativo aggiornato."""
        from core.mercato import TF_OPERATIVI

        if self.su_candela is None:
            return
        for tf, candela in per_tf.items():
            if tf not in TF_OPERATIVI:
                continue
            self.valutazioni += 1
            try:
                self.su_candela(AlertIn(
                    secret=self.segreto,
                    symbol=strumento,
                    interval=tf.value,
                    candle_close_time_utc=candela.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    close=candela.chiusura,
                ))
            except Exception:
                log.exception("valutazione fallita su %s %s", strumento, tf.value)


# L'istanza unica, come per `core/mercato.py`: il ciclo e' uno e lo stato che
# `/salute` mostra deve essere quello del ciclo che gira davvero.
mercato_duka = MercatoDukascopy()
