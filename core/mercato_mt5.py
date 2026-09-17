"""Il ciclo di mercato su MT5: le candele del broker su cui si esegue.

## Perche' esiste, dopo Dukascopy

Dukascopy e' una fonte pubblica servita come file statici, e ha due limiti
che non sono difetti del nostro codice:

1. **limita gli indirizzi che chiedono troppo.** Prima 503, poi connessioni
   che non si aprono. Una macchina che ha seminato vent'anni di storia ci
   finisce dentro, e ci resta per ore;
2. **non pubblica il mese in corso.** I file orari escono a mese chiuso: fino
   al primo del mese dopo, `H1`, `H4` e `D1` si possono solo ricostruire dai
   minuti. Funziona -- misurato identico -- ma e' un giro largo per avere una
   cosa che il broker da' diretta.

MT5 non ha nessuno dei due. E' gia' connesso e autenticato, non ha limiti di
richieste, e serve ogni timeframe nativamente, mese in corso compreso.

## Il vantaggio che non si vede subito

Sono le **stesse candele su cui si esegue**. Con Dukascopy si analizza su un
listino e si manda l'ordine su un altro: due feed veri, entrambi
tradeable, ma non lo stesso. Ogni scostamento fra i due e' rumore che
nessuna regola puo' recuperare, perche' nasce dopo la decisione.

Qui il prezzo su cui il CRT si forma e il prezzo a cui l'ordine parte sono la
stessa serie.

## Il prezzo da pagare, dichiarato

Ogni misura di questo progetto e' stata fatta su Dukascopy. `+0,3613 R` su
`4h -> 15m` e' un numero misurato su quelle candele, non su queste. Le due
serie saranno vicine -- sono entrambe il vero mercato -- ma "vicine" non e'
"uguali", e finche' non e' misurato non si sa quanto.

Per questo `confronta_feed.py` esiste e va girato PRIMA di spostare il
motore qui. E per questo la storia profonda resta di Dukascopy: MT5 la serve
corta e dipende dal broker, mentre per misurare servono anni.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from core import storage
from core.definizioni import Candela
from core.log import diario
from core.mercato_duka import DURATA, _alert, ultima_archiviata
from core.models import AlertIn
from core.parametri import GERARCHIA_COMPLETA, TF, UNIVERSO
from core.simboli import simbolo_esecuzione

log = diario("mercato_mt5")

# I codici dei timeframe di MT5. Non sono progressivi ne' deducibili: 16385 e'
# un'ora, 16388 quattro ore. Scriverli a mano una volta sola e' meno rischioso
# che calcolarli.
TIMEFRAME_MT5: dict[TF, int] = {
    TF.MIN1: 1,
    TF.MIN5: 5,
    TF.MIN15: 15,
    TF.H1: 16385,
    TF.H4: 16388,
    TF.D1: 16408,
    TF.W1: 32769,
    TF.M1: 49153,
}

# Quante barre chiedere per timeframe. Serve a coprire un riavvio e a dare al
# motore la storia che DEF-26 vuole; la storia profonda sta gia' in archivio e
# non si richiede a ogni giro.
QUANTE: dict[TF, int] = {
    TF.MIN1: 1500, TF.MIN5: 1000, TF.MIN15: 1000,
    TF.H1: 800, TF.H4: 500, TF.D1: 400, TF.W1: 200, TF.M1: 120,
}


def in_candele(barre: list[dict], tf: TF) -> list[Candela]:
    """Da barre MT5 a candele del motore.

    Due conversioni, e sbagliarne una non produce errori ma candele spostate:

    - MT5 marca la barra sull'**apertura**, `Candela.orario` porta la
      chiusura. Si somma la durata del timeframe.
    - l'**ultima barra e' in formazione** e va scartata: `ESCL-13` vieta di
      valutare una candela che non ha finito di formarsi, e qui -- a
      differenza di Dukascopy -- la si riconosce con certezza, perche' e'
      sempre e solo l'ultima.
    """
    if len(barre) < 2:
        return []
    durata = DURATA[tf]
    return [
        Candela(b["apertura_utc"] + durata, b["open"], b["high"], b["low"], b["close"])
        for b in barre[:-1]
    ]


@dataclass
class MercatoMT5:
    """Tiene l'archivio aggiornato leggendo dal terminale MT5."""

    intervallo_sec: float = 60.0
    su_candela: Optional[Callable[[AlertIn], None]] = None
    segreto: str = ""
    suffisso: str = ""

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
            target=self._ciclo, name="mercato-mt5", daemon=True)
        self._thread.start()
        log.info("mercato MT5 avviato, ogni %.0fs", self.intervallo_sec)

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

        L'ordine e' quello di CTX-10 e vale qui come sulla via Dukascopy:
        prima si aggiorna tutto, poi si valuta. Valutare un timeframe basso
        prima che il suo superiore sia aggiornato darebbe una decisione presa
        su una bias vecchia.
        """
        adesso = adesso or datetime.now(timezone.utc)
        self.giri += 1
        nuove_per_strumento: dict[str, dict[TF, Candela]] = {}

        for strumento in UNIVERSO:
            if self._stop.is_set():
                break
            try:
                nuove = self.aggiorna(strumento, adesso)
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

    def serie_da_chiedere(self, strumento: str, tf: TF, adesso: datetime) -> bool:
        """Ha senso chiedere questa serie adesso?

        MT5 non ha limiti di richieste, quindi questo cancello non serve a
        proteggere la fonte come su Dukascopy: serve a non rileggere e
        riscrivere migliaia di barre al minuto per scoprire che non e'
        cambiato nulla.
        """
        ultima = ultima_archiviata(strumento, tf)
        if ultima is None:
            return True
        return adesso - ultima >= DURATA[tf]

    def aggiorna(self, strumento: str, adesso: datetime) -> dict[TF, Candela]:
        """Legge da MT5 i timeframe che possono avere qualcosa di nuovo."""
        from core import broker

        simbolo = simbolo_esecuzione(strumento, self.suffisso)
        ultime: dict[TF, Candela] = {}

        for tf, codice in TIMEFRAME_MT5.items():
            if not self.serie_da_chiedere(strumento, tf, adesso):
                continue
            ok, barre, messaggio = broker.candele(simbolo, codice, QUANTE[tf])
            if not ok:
                log.warning("%s %s: %s", simbolo, tf.value, messaggio)
                continue
            candele = in_candele(barre, tf)
            if not candele:
                continue
            righe = [{
                "strumento": strumento, "tf": tf.value,
                "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apertura": c.apertura, "massimo": c.massimo,
                "minimo": c.minimo, "chiusura": c.chiusura,
            } for c in candele]
            nuove, _ = storage.salva_candele(righe, origine="mt5")
            self.candele_nuove += nuove
            if nuove:
                ultime[tf] = candele[-1]
        return ultime

    def _valuta(self, strumento: str, per_tf: dict[TF, Candela]) -> None:
        """Una valutazione per ogni timeframe aggiornato che conta."""
        from core.mercato import TF_INGRESSO_OPERATIVI, TF_OPERATIVI

        if self.su_candela is None:
            return
        contano = set(TF_OPERATIVI) | set(TF_INGRESSO_OPERATIVI)
        in_ordine = sorted(
            per_tf.items(), key=lambda coppia: GERARCHIA_COMPLETA.index(coppia[0]))
        for tf, candela in in_ordine:
            if tf not in contano:
                continue
            self.valutazioni += 1
            try:
                self.su_candela(_alert(strumento, tf, candela, self.segreto))
            except Exception:
                log.exception("valutazione fallita su %s %s", strumento, tf.value)


mercato_mt5 = MercatoMT5()
