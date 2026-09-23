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
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from core import storage
from core.aggregazione import chiave_sessione
from core.definizioni import Candela
from core.log import diario
from core.mercato_duka import DURATA, _alert, ultima_archiviata
from core.models import AlertIn
from core.parametri import GERARCHIA_COMPLETA, TF, UNIVERSO
from core import riepilogo
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

# Quante barre chiedere per timeframe. Serve a coprire un riavvio, non a
# riportare la storia: quella sta gia' in archivio e non si richiede a ogni
# giro. Numeri scesi il 2026-09-21 (erano 1500/1000/1000/800): con sei
# strumenti e quattro serie ciascuno sono ventiquattro chiamate a giro, e
# chiedere millecinquecento barre al minuto per scoprire che ne e' arrivata
# una sola costava minuti di giro - il ciclo era passato da uno a sette
# minuti, fino a non rispondere piu' su /salute. Quel che resta copre
# comunque uno spegnimento di ore.
QUANTE: dict[TF, int] = {
    TF.MIN1: 400, TF.MIN5: 300, TF.MIN15: 300,
    TF.H1: 400, TF.H4: 500, TF.D1: 400, TF.W1: 200, TF.M1: 120,
}

# Le uniche native da chiedere dal vivo. TF.H4, D1, W1 e M1 di MT5 nascono
# dal calendario del server, non da UTC: misurato su questo conto, l'H4
# nativo chiude alle 1-5-9-13-17-21 UTC contro le 0-4-8-12-16-20 su cui ogni
# misura del progetto e' stata fatta (+0,3613 R su 4h->15m), e il D1 nativo
# chiude alle 21:00 fisse contro le 22:00 di Dukascopy. Usarli live
# sposterebbe il range su cui il CRT cerca il key level su un'altra serie,
# senza che nulla lo segnali: stesso aspetto, range diverso.
#
# Si ricostruiscono tutti dalle orarie (`_ricostruisci_superiori`), con le
# funzioni di `core/aggregazione` misurate contro l'archivio Dukascopy:
# D1 identico al 99,8%, W1 al 98%, M1 al 99% sugli stessi orari.
TIMEFRAME_DAL_VIVO: tuple[TF, ...] = (TF.MIN1, TF.MIN5, TF.MIN15, TF.H1)

# Quante orarie leggere dall'archivio per ricostruire i timeframe superiori.
# Con ~2.500 ore si coprono tre mesi e mezzo: abbastanza perche' il mensile
# abbia almeno due mesi interi fra quello troncato dall'inizio della finestra
# e quello ancora in formazione.
ORARIE_PER_SUPERIORI = 2500

# I timeframe ricostruiti dalle orarie, nell'ordine in cui dipendono l'uno
# dall'altro (settimanale e mensile si costruiscono dalle giornaliere).
SUPERIORI_RICOSTRUITI: tuple[TF, ...] = (TF.H4, TF.D1, TF.W1, TF.M1)


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
    # Quanto aspettare dopo la chiusura prima di chiedere la barra. Serve
    # solo a dare al terminale il tempo di pubblicarla: la barra che chiude
    # a :00 e' leggibile subito dopo, non a :00,000.
    margine_sec: float = 1.5
    su_candela: Optional[Callable[[AlertIn], None]] = None
    segreto: str = ""
    suffisso: str = ""

    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    giri: int = field(default=0, init=False)
    candele_nuove: int = field(default=0, init=False)
    valutazioni: int = field(default=0, init=False)
    ultimo_errore: Optional[str] = field(default=None, init=False)
    # L'ultima oraria da cui si e' gia' ricostruito, per strumento: senza
    # orarie nuove i timeframe superiori non possono cambiare.
    _ultima_h1: dict = field(default_factory=dict, init=False, repr=False)

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

    def attesa_fino_al_confine(self, adesso: Optional[datetime] = None) -> float:
        """Quanto dormire per svegliarsi subito DOPO una chiusura di candela.

        Dormire `intervallo_sec` fissi sembrava equivalente e non lo e'. Il
        sonno parte da quando finisce il giro, quindi il risveglio cade in un
        punto qualsiasi del minuto e ci resta: se il primo giro capita a :36,
        tutti i successivi capitano intorno a :36. La candela M1 pero' chiude
        sempre a :00, e l'alert nasce gia' vecchio di quei 36 secondi.

        Misurato il 2026-09-23 sui 4.385 alert della giornata: ritardo mediano
        **88,5 secondi**, e riga per riga il ritardo era esattamente il secondo
        del minuto del risveglio -- 17:12:36 -> 36,3s, 17:13:45 -> 45,8s. Non
        era il calcolo a essere lento: era il risveglio a cadere nel punto
        sbagliato. Con l'aggancio al confine il ritardo diventa il margine piu'
        la durata del giro, e il tetto di 15s su M1 torna raggiungibile.
        """
        passo = self.intervallo_sec if self.intervallo_sec > 0 else 60.0
        ora = (adesso or datetime.now(timezone.utc)).timestamp()
        # Il confine successivo sull'orologio del mondo, non su quello del
        # bot: e' sull'orologio del mondo che le candele chiudono.
        attesa = (passo - (ora % passo)) + self.margine_sec
        # Se siamo dentro il margine di un confine appena passato, la barra
        # potrebbe non essere ancora pubblicata: si finisce di aspettare il
        # margine e si prende questa, invece di dormire un minuto intero e
        # arrivare sulla prossima con un giro di ritardo.
        if attesa > passo:
            attesa -= passo
        return attesa

    def _ciclo(self) -> None:
        while not self._stop.wait(self.attesa_fino_al_confine()):
            try:
                self.giro()
                self.ultimo_errore = None
            except Exception as errore:
                self.ultimo_errore = repr(errore)
                log.exception("giro di mercato fallito")
            # Fuori dal try del giro: un riepilogo che fallisce non deve
            # contare come un giro fallito, e un giro fallito e' anzi il
            # momento in cui il riepilogo serve di piu'.
            riepilogo.forse_manda()

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

        # Il DXY per primo, e per la stessa ragione di CTX-10: SETUP-19 e
        # RISK-05 lo leggono ad ogni valutazione, quindi aggiornarlo dopo
        # significherebbe decidere su una bias vecchia di un giro.
        try:
            self.aggiorna_dxy(adesso)
        except Exception as errore:
            self.ultimo_errore = f"DXY: {errore!r}"
            log.warning("aggiornamento del DXY fallito: %r", errore)

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

        # Lo spread, campionato a intervalli regolari. Va IN FONDO al giro, e
        # non prima delle valutazioni, perche' non deve aggiungere un
        # millisecondo al percorso segnale -> ordine: su M1min il tetto e' 15
        # secondi. Serve alla stima dei costi sullo storico, che e' un lavoro
        # di settimane, non di adesso.
        self._campiona_spread()

        return {
            "strumenti": len(nuove_per_strumento),
            "candele_nuove": self.candele_nuove,
            "valutazioni": self.valutazioni,
        }

    def _campiona_spread(self) -> None:
        """Un bid/ask per strumento, una volta a giro.

        Serve a stimare i costi sullo storico. Finche' l'unico spread
        registrato era quello delle aperture, il campione era distorto: si
        misurava solo negli istanti in cui il bot aveva deciso di operare,
        cioe' plausibilmente quelli piu' stretti. Un percentile calcolato li'
        descrive il momento dell'apertura, non l'ora del giorno.

        Non solleva: un campionamento fallito non deve far cadere il giro.
        """
        from core import broker

        misure = []
        for strumento in UNIVERSO:
            simbolo = simbolo_esecuzione(strumento, self.suffisso)
            try:
                ok, tick, _ = broker.prezzo_corrente(simbolo)
            except Exception:
                continue
            if ok and tick:
                misure.append((simbolo, tick["bid"], tick["ask"]))
        if misure:
            storage.campiona_spread(misure)

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

        for tf in TIMEFRAME_DAL_VIVO:
            codice = TIMEFRAME_MT5[tf]
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

        # Si ricostruisce quando arriva un'ora nuova, ma anche quando uno dei
        # superiori e' scaduto per conto suo: senza la seconda condizione, un
        # bot rimasto spento due giorni non avrebbe mai richiuso il buco nelle
        # giornaliere - aspettava un'ora nuova che intanto era gia' arrivata.
        superiori_scaduti = any(
            self.serie_da_chiedere(strumento, tf, adesso)
            for tf in SUPERIORI_RICOSTRUITI
        )
        if TF.H1 in ultime or superiori_scaduti:
            ultime.update(self._ricostruisci_superiori(strumento))
        return ultime

    def _orarie_archiviate(self, strumento: str) -> list[Candela]:
        """Le ultime orarie in archivio, gia' come candele del motore."""
        righe = storage.candele_archiviate(
            strumento, TF.H1.value, limite=ORARIE_PER_SUPERIORI)
        return [
            Candela(
                orario=datetime.fromisoformat(
                    str(r["chiusura_utc"]).replace("Z", "+00:00")),
                apertura=float(r["apertura"]), massimo=float(r["massimo"]),
                minimo=float(r["minimo"]), chiusura=float(r["chiusura"]),
            )
            for r in righe
        ]

    def _sessioni_archiviate(self, strumento: str, tf: TF) -> set:
        """Le sessioni gia' coperte da una candela in archivio.

        Si guardano solo le piu' recenti: la ricostruzione tocca una finestra
        di tre mesi e mezzo, e leggere vent'anni di giornaliere ad ogni giro
        per confrontarne trenta sarebbe lo stesso spreco che ha gia' fatto
        rallentare il ciclo.
        """
        quante = {TF.H4: 700, TF.D1: 200, TF.W1: 40, TF.M1: 12}.get(tf, 200)
        righe = storage.candele_archiviate(strumento, tf.value, limite=quante)
        fuori = set()
        for r in righe:
            try:
                quando = datetime.fromisoformat(
                    str(r["chiusura_utc"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            fuori.add(chiave_sessione(tf, Candela(quando, 0.0, 0.0, 0.0, 0.0)))
        return fuori

    def _ricostruisci_superiori(self, strumento: str) -> dict[TF, Candela]:
        """H4, giornaliero, settimanale e mensile dalle orarie.

        Nessuno di questi quattro si chiede a MT5: i suoi confini sono quelli
        del server del broker, non quelli su cui il progetto ha misurato.
        `core/aggregazione` li ricostruisce sui confini di Dukascopy (H4 a
        0/4/8/12/16/20 UTC, giornata che chiude alle 22:00 UTC), e il
        risultato e' stato confrontato con l'archivio vero: giornaliere
        identiche al 99,8%, settimanali al 98%, mensili al 99%.

        Perche' conta: senza questa ricostruzione D1, W1 e mensile restavano
        fermi al giorno in cui Dukascopy ha smesso di girare - cinque giorni
        il giornaliero, venti il mensile - e `SETUP-05` continuava a chiedersi
        se i timeframe superiori fossero allineati leggendo candele vecchie di
        una settimana, senza che nulla lo segnalasse.
        """
        from core.aggregazione import (
            aggrega_giornaliere, aggrega_mensili, aggrega_orarie,
            aggrega_settimanali,
        )

        orarie = self._orarie_archiviate(strumento)
        if len(orarie) < 4:
            return {}

        # Senza orarie nuove non c'e' niente da ricostruire, e rifarlo a vuoto
        # costa: a mercato chiuso `serie_da_chiedere` resta vera per giorni
        # (il giornaliero non puo' avanzare, quindi e' sempre "scaduto"), e
        # senza questo confronto la ricostruzione ripartiva ogni minuto
        # leggendo 2.500 righe per strumento.
        if self._ultima_h1.get(strumento) == orarie[-1].orario:
            return {}
        self._ultima_h1[strumento] = orarie[-1].orario

        giornaliere = aggrega_giornaliere(orarie)
        per_tf: dict[TF, Sequence[Candela]] = {
            TF.H4: aggrega_orarie(orarie, quante=4),
            TF.D1: giornaliere,
            TF.W1: aggrega_settimanali(giornaliere),
            TF.M1: aggrega_mensili(giornaliere),
        }

        ultime: dict[TF, Candela] = {}
        for tf, serie in per_tf.items():
            # Si scarta il PRIMO periodo: la finestra comincia a meta'
            # giornata (o a meta' mese) e quel gruppo e' troncato, quindi
            # avrebbe l'apertura sbagliata e forse estremi mancanti.
            # L'ultimo, quello in formazione, lo scarta gia' l'aggregatore.
            # Tutti gli altri si riscrivono: `salva_candele` ignora quelli
            # gia' presenti, e cosi' un buco lasciato da uno spegnimento
            # lungo si richiude da solo invece di restare li'.
            #
            # `INSERT OR IGNORE` pero' confronta gli ORARI, e Dukascopy non
            # timbra sempre al confine: si scartano quindi anche i periodi
            # gia' coperti da una candela in archivio, riconosciuti per
            # sessione e non per orario.
            gia_presenti = self._sessioni_archiviate(strumento, tf)
            coda = [
                c for c in serie[1:]
                if chiave_sessione(tf, c) not in gia_presenti
            ]
            if not coda:
                continue
            righe = [{
                "strumento": strumento, "tf": tf.value,
                "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apertura": c.apertura, "massimo": c.massimo,
                "minimo": c.minimo, "chiusura": c.chiusura,
            } for c in coda]
            nuove, _ = storage.salva_candele(righe, origine="mt5")
            self.candele_nuove += nuove
            if nuove:
                ultime[tf] = coda[-1]
        return ultime

    def aggiorna_dxy(self, adesso: datetime) -> int:
        """Il DXY, calcolato dal vivo dai suoi sei costituenti su MT5.

        `SETUP-19` non abilita alcuna operazione su cinque coppie su sei senza
        la bias del dollaro, e `RISK-05` blocca ogni CRT che le vada contro.
        Finche' il DXY lo costruiva `importa_dxy.py` da Dukascopy, spegnere
        Dukascopy ha significato congelarlo: il 2026-09-21 era fermo a otto
        giorni prima, e ogni singolo blocco RISK-05 nel diario citava la
        stessa bias SHORT - una fotografia vecchia di una settimana che
        continuava a decidere.

        I sei costituenti (`core/duka_dxy.PESI`) sono quotati da MT5 come
        tutto il resto, USDCAD e USDSEK compresi. **Restano ingredienti, non
        strumenti**: si leggono in memoria, entrano nella formula dell'indice
        e non vengono ne' archiviati col loro nome ne' passati al motore.
        L'universo operativo resta quello di `PRIN-08`, sei strumenti, e il
        DXY resta di sola analisi (`SOLO_ANALISI` in `core/simboli`).
        """
        from core import broker
        from core.duka_dxy import NOME_ARCHIVIO, PESI, componi

        if not self.serie_da_chiedere(NOME_ARCHIVIO, TF.H1, adesso):
            return 0

        serie: dict[str, list[Candela]] = {}
        for costituente in PESI:
            simbolo = simbolo_esecuzione(costituente, self.suffisso)
            ok, barre, messaggio = broker.candele(
                simbolo, TIMEFRAME_MT5[TF.H1], QUANTE[TF.H1])
            if not ok:
                log.warning("DXY: %s non leggibile: %s", simbolo, messaggio)
                return 0
            serie[costituente] = in_candele(barre, TF.H1)

        orarie = componi(serie)
        if not orarie:
            log.warning("DXY: nessuna ora in comune fra i sei costituenti")
            return 0

        righe = [{
            "strumento": NOME_ARCHIVIO, "tf": TF.H1.value,
            "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "apertura": c.apertura, "massimo": c.massimo,
            "minimo": c.minimo, "chiusura": c.chiusura,
        } for c in orarie]
        nuove, _ = storage.salva_candele(righe, origine="mt5")
        self.candele_nuove += nuove
        if nuove:
            # Gli stessi superiori degli strumenti operativi: la bias di
            # SETUP-19 si legge sul giornaliero, non sull'ora.
            self._ricostruisci_superiori(NOME_ARCHIVIO)
            log.info("DXY aggiornato: %d ore nuove, ultima %s",
                     nuove, orarie[-1].orario.strftime("%Y-%m-%d %H:%M"))
        return nuove

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
