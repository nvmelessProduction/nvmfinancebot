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
from core import duka_dxy
from core.duka_minuti import (
    BLOCCHI,
    aggrega,
    minuti_del_giorno,
    orarie_dai_minuti,
)
from core.fonte_dukascopy import orarie_del_mese
from core.log import diario
from core.models import AlertIn
from core.parametri import GERARCHIA_COMPLETA, TF, UNIVERSO

log = diario("mercato_duka")

# Ogni quanto puo' chiudersi una candela nuova. E' la misura che decide se ha
# senso chiedere una serie: prima che sia passato questo tempo dall'ultima
# candela in archivio, la richiesta non puo' portare nulla di nuovo.
DURATA: dict[TF, timedelta] = {
    TF.M1: timedelta(days=28),
    TF.W1: timedelta(days=7),
    TF.D1: timedelta(days=1),
    TF.H4: timedelta(hours=4),
    TF.H1: timedelta(hours=1),
    TF.MIN15: timedelta(minutes=15),
    TF.MIN5: timedelta(minutes=5),
    TF.MIN1: timedelta(minutes=1),
}

# Quanti giorni di minuti il ciclo e' disposto a recuperare da solo. Il suo
# mestiere e' stare al passo, non seminare: un archivio piu' indietro di cosi'
# si riempie con `importa_minuti.py`, che scarica in parallelo. Provare a
# farlo qui, un file alla volta, terrebbe il ciclo fermo per ore.
GIORNI_MINUTI_MASSIMI = 4

# Quanti mesi di orarie recuperare al massimo in un giro, per la stessa
# ragione. La semina e' `importa_dukascopy.py`.
MESI_ORARIE_MASSIMI = 2

# Ogni quanto ripescare il file dei minuti del giorno in corso.
#
# Il cancello sull'archivio qui non basta, ed e' il difetto piu' sottile dei
# tre che il ciclo ha avuto. `serie_da_chiedere(MIN1)` e' praticamente sempre
# vero -- un minuto nuovo si chiude ogni minuto -- quindi a ogni giro si
# riscaricava lo stesso file giornaliero, che intanto cresce. Fa 8.640
# richieste al giorno per sei strumenti: un terzo del difetto che ieri notte
# ha fatto chiudere la porta a Dukascopy, e sufficiente a tenerla chiusa.
#
# Due minuti e' il compromesso, e non e' arbitrario. La configurazione con il
# risultato migliore misurato e' `4h -> 15m`: una candela da un quarto d'ora
# si chiude ogni quindici minuti, quindi due minuti di ritardo nel vederla
# sono un ottavo della sua durata. Sarebbe troppo per `15m -> 1m`, che pero'
# e' la coppia peggiore misurata (-0,2195 R su 3.514 casi) e non e' quella
# che vogliamo far girare.
#
# Chi vuole l'altro compromesso abbassa questo numero sapendo cosa costa.
MINUTI_INTERVALLO_SEC = 120.0

# Dopo un guasto di rete su uno strumento, quanto aspettare prima di
# riprovare, e il tetto di quell'attesa.
#
# Serve perche' il cancello sull'archivio da solo non basta: quando
# Dukascopy non risponde nulla entra in archivio, quindi il cancello resta
# aperto e il giro successivo richiede le stesse cose. E' cosi' che un
# fornitore momentaneamente in difficolta' diventa un fornitore che ci
# chiude la porta in faccia.
RIPOSO_INIZIALE = timedelta(minutes=5)
RIPOSO_MASSIMO = timedelta(hours=1)


def ultima_archiviata(strumento: str, tf: TF) -> Optional[datetime]:
    """La chiusura dell'ultima candela in archivio, o `None` se non ce n'e'."""
    righe = storage.candele_archiviate(strumento, tf.value, limite=1)
    if not righe:
        return None
    try:
        quando = datetime.fromisoformat(
            str(righe[0]["chiusura_utc"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def _giorno_di(momento: datetime) -> datetime:
    """La chiusura giornaliera: 22:00 UTC, cioe' le 17:00 di New York.

    E' la chiusura di sessione che il forex usa davvero. Usare la mezzanotte
    UTC spezzerebbe ogni giornata a meta' della sessione americana, e i range
    giornalieri — su cui vive `M1 -> D1` — sarebbero un'altra cosa.
    """
    limite = momento.replace(hour=22, minute=0, second=0, microsecond=0)
    return limite + timedelta(days=1) if momento > limite else limite


def _raggruppa(candele: list[Candela], chiave: Callable) -> list[Candela]:
    """Aggrega candele per una chiave, scartando l'ultimo gruppo in formazione.

    Lo scarto dell'ultimo gruppo non e' prudenza: senza, il ciclo archiviava
    la giornata **in corso** come se fosse chiusa. E `salva_candele` fa
    `INSERT OR IGNORE`, quindi la prima versione scritta vinceva e non veniva
    piu' aggiornata: una candela giornaliera vista per la prima volta alle
    00:30 restava per sempre quella di trenta minuti di scambi, con il suo
    massimo e il suo minimo sbagliati, e su quella serie il motore calcolava
    bias, key level e range del CRT.

    Un gruppo e' chiuso quando ne esiste uno successivo. Nel fine settimana
    l'ultimo gruppo del venerdi' resta in sospeso fino alla riapertura della
    domenica sera, cioe' prima che si valuti qualunque ora del lunedi'.

    E' la stessa regola di `importa_dukascopy._raggruppa`: se le due
    divergessero, le candele seminate e quelle prese dal vivo sarebbero
    costruite in due modi diversi sulla stessa serie.
    """
    gruppi: dict = {}
    for candela in candele:
        gruppi.setdefault(chiave(candela), []).append(candela)
    fuori = []
    for k in sorted(gruppi)[:-1]:
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
    # Fino a quando non riprovare una fonte, e quanto durera' la prossima
    # attesa. Chiave: (strumento, "ore" | "minuti").
    _riposo: dict = field(default_factory=dict, init=False)
    _attesa: dict = field(default_factory=dict, init=False)
    # Quando si e' chiesto l'ultima volta il file dei minuti, per strumento.
    _minuti_chiesti: dict = field(default_factory=dict, init=False)
    # Quante richieste di rete ha fatto il ciclo, da quando e' partito. Sta
    # in `/salute` perche' il volume era invisibile, ed e' cosi' che un ciclo
    # da 26.000 richieste al giorno e' rimasto in piedi senza che nessuno se
    # ne accorgesse: i log dicevano cosa falliva, mai quanto si chiedeva.
    richieste: int = field(default=0, init=False)
    _acceso: Optional[datetime] = field(default=None, init=False)
    giri: int = field(default=0, init=False)
    candele_nuove: int = field(default=0, init=False)
    valutazioni: int = field(default=0, init=False)
    ultimo_errore: Optional[str] = field(default=None, init=False)

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._acceso = datetime.now(timezone.utc)
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

    @property
    def richieste_al_giorno(self) -> Optional[float]:
        """Il ritmo verso la fonte, proiettato su ventiquattro ore.

        Il totale da solo non dice niente: mille richieste sono poche in un
        giorno e tante in dieci minuti. E' il ritmo che fa chiudere la porta,
        ed e' il numero che mancava quando il ciclo ne faceva 26.000 al
        giorno senza che nulla lo dicesse.
        """
        if self._acceso is None or not self.richieste:
            return None
        ore = (datetime.now(timezone.utc) - self._acceso).total_seconds() / 3600
        if ore < 0.05:                     # meno di tre minuti: non significa nulla
            return None
        return round(self.richieste / ore * 24, 1)

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

        # Il DXY per primo, e fuori dal giro degli strumenti: non si opera
        # (PRIN-08) ma cinque coppie su sei dipendono dalla sua bias, e
        # CTX-10 vuole che chi comanda sia aggiornato prima di chi segue.
        try:
            self._aggiorna_dxy(adesso)
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

        return {
            "strumenti": len(nuove_per_strumento),
            "candele_nuove": self.candele_nuove,
            "valutazioni": self.valutazioni,
            "richieste": self.richieste,
        }

    # ------------------------------------------------------------------
    # Il cancello: chiedere solo cio' che puo' essere cambiato
    # ------------------------------------------------------------------

    def serie_da_chiedere(self, strumento: str, tf: TF, adesso: datetime) -> bool:
        """Ha senso chiedere questa serie adesso?

        Solo se dall'ultima candela in archivio e' passato abbastanza tempo
        perche' una nuova possa essersi chiusa. Un archivio vuoto si chiede
        sempre: e' il primo avvio.

        Questo cancello esisteva in `core/mercato.py` e **qui mancava**. Senza,
        il ciclo richiedeva a Dukascopy tre mesi di orarie per sei strumenti a
        ogni giro — diciotto file al minuto, circa ventiseimila al giorno, per
        ricevere quasi sempre esattamente le stesse candele gia' in archivio.
        Il risultato misurato sulla VPS: 503 a raffica, poi connessioni che non
        rispondevano piu' affatto. Non era Dukascopy ad avere un problema.
        """
        ultima = ultima_archiviata(strumento, tf)
        if ultima is None:
            return True
        return adesso - ultima >= DURATA[tf]

    def _in_riposo(self, chiave: tuple[str, str], adesso: datetime) -> bool:
        fino_a = self._riposo.get(chiave)
        return fino_a is not None and adesso < fino_a

    def _guasto(self, chiave: tuple[str, str], adesso: datetime) -> None:
        """Un giro a vuoto su questa fonte: si allunga l'attesa."""
        attesa = self._attesa.get(chiave, RIPOSO_INIZIALE)
        self._riposo[chiave] = adesso + attesa
        self._attesa[chiave] = min(attesa * 2, RIPOSO_MASSIMO)
        log.warning("%s %s: nessun dato, riprovo fra %d minuti",
                    chiave[0], chiave[1], int(attesa.total_seconds() // 60))

    def _riuscito(self, chiave: tuple[str, str]) -> None:
        self._riposo.pop(chiave, None)
        self._attesa.pop(chiave, None)

    # ------------------------------------------------------------------
    # L'aggiornamento
    # ------------------------------------------------------------------

    def aggiorna(
        self, strumento: str, adesso: Optional[datetime] = None
    ) -> dict[TF, Candela]:
        """Porta in archivio cio' che manca, dalle mensili al minuto.

        Restituisce, per ogni timeframe, l'ULTIMA candela davvero nuova: e'
        quella che fa scattare una valutazione. Le arretrate entrano in
        archivio — servono alla storia — ma non si valutano: dopo uno
        spegnimento di una settimana ci sarebbero sette valutazioni su prezzi
        vecchi, e sette ordini.
        """
        adesso = adesso or datetime.now(timezone.utc)
        ultime: dict[TF, Candela] = {}
        ultime.update(self._aggiorna_orarie(strumento, adesso))
        ultime.update(self._aggiorna_minuti(strumento, adesso))
        return ultime

    def _aggiorna_orarie(self, strumento: str, adesso: datetime) -> dict[TF, Candela]:
        """Le orarie, e i quattro timeframe che se ne ricavano."""
        chiave = (strumento, "ore")
        if self._in_riposo(chiave, adesso):
            return {}
        if not self.serie_da_chiedere(strumento, TF.H1, adesso):
            return {}

        orarie: list[Candela] = []
        for anno, mese in self._mesi_da_chiedere(strumento, adesso):
            self.richieste += 1
            orarie.extend(orarie_del_mese(strumento, anno, mese))

        # Il mese IN CORSO non c'e' come file orario: Dukascopy li pubblica a
        # mese chiuso e prima risponde 404. Senza questo pezzo H1, H4 e D1 --
        # dove vive il range del CRT -- resterebbero fermi all'ultimo giorno
        # del mese scorso per un tempo che cresce fino a trentun giorni, e il
        # bot vedrebbe un grafico congelato senza che nulla lo dica.
        #
        # E' la spiegazione vera dell'archivio della VPS fermo al 31 agosto,
        # che avevo attribuito ai 503. I 503 c'erano; la causa era un'altra.
        #
        # I file al minuto invece sono giornalieri e ci sono anche per oggi.
        primo = adesso.date().replace(day=1)
        orarie.extend(orarie_dai_minuti(strumento, primo, adesso.date()))
        self.richieste += (adesso.day + 1) // 2      # stima: i chiusi sono in cache

        if not orarie:
            self._guasto(chiave, adesso)
            return {}
        self._riuscito(chiave)
        orarie.sort(key=lambda c: c.orario)

        return self._archivia(strumento, costruisci(orarie))

    def _mesi_da_chiedere(
        self, strumento: str, adesso: datetime
    ) -> list[tuple[int, int]]:
        """Quali file mensili servono davvero.

        Quasi sempre uno solo: il mese in corso. I mesi chiusi non cambiano
        piu', e richiederli ogni ora significa scaricare qualche megabyte per
        riscoprire candele che stanno gia' in archivio. Si torna indietro solo
        quando l'archivio e' indietro — cioe' dopo uno spegnimento lungo, o al
        primo avvio.
        """
        ultima = ultima_archiviata(strumento, TF.H1)
        # Il mese in corso NON e' nell'elenco: come file orario non esiste
        # ancora (404 fino a mese chiuso) e lo si ricostruisce dai minuti.
        # Chiederlo sarebbe una richiesta buttata a ogni giro.
        mesi: list[tuple[int, int]] = []
        if ultima is None:
            indietro = MESI_ORARIE_MASSIMI
        else:
            indietro = (adesso.year - ultima.year) * 12 + adesso.month - ultima.month
            indietro = max(1, min(indietro, MESI_ORARIE_MASSIMI))
        for passo in range(1, indietro + 1):
            anno, mese = adesso.year, adesso.month - passo
            while mese <= 0:
                mese += 12
                anno -= 1
            mesi.append((anno, mese))
        return sorted(mesi)

    def _aggiorna_minuti(self, strumento: str, adesso: datetime) -> dict[TF, Candela]:
        """I minuti, e i tre timeframe di INGRESSO che se ne ricavano.

        Questa meta' del ciclo non esisteva, ed e' la meta' che fa operare il
        bot. `CRT-04` accoppia un range a un timeframe di ingresso, e quattro
        coppie su sei entrano sotto l'ora: `4h -> 15m`, `1h -> 5m`,
        `15m -> 1m`. Senza minuti dal vivo il motore poteva armare un setup su
        `4h` e poi **non vedere mai** il CISD su `15m` che lo fa scattare.

        Il bot non dava errori: restava semplicemente fermo sulle tre coppie
        lente, quelle da 413 segnali in vent'anni. La configurazione misurata
        migliore — `4h -> 15m`, +0,3613 R — non poteva proprio girare.
        """
        chiave = (strumento, "minuti")
        if self._in_riposo(chiave, adesso):
            return {}
        if not self.serie_da_chiedere(strumento, TF.MIN1, adesso):
            return {}

        ultima_richiesta = self._minuti_chiesti.get(strumento)
        if (ultima_richiesta is not None
                and (adesso - ultima_richiesta).total_seconds()
                < MINUTI_INTERVALLO_SEC):
            return {}
        self._minuti_chiesti[strumento] = adesso

        oggi = adesso.date()
        minuti: list[Candela] = []
        for giorno in self._giorni_da_chiedere(strumento, adesso):
            # Il giorno in corso si ripesca sempre: il file cresce mentre lo
            # si guarda, e la copia in cache sarebbe quella di un'ora fa.
            self.richieste += 1
            minuti.extend(minuti_del_giorno(strumento, giorno, fresco=(giorno >= oggi)))
        if len(minuti) < 2:
            self._guasto(chiave, adesso)
            return {}
        self._riuscito(chiave)
        minuti.sort(key=lambda c: c.orario)

        # L'ultimo minuto si scarta: il file del giorno corrente si pubblica
        # man mano e la riga in coda puo' essere incompleta (ESCL-13).
        chiusi = minuti[:-1]
        limite = chiusi[-1].orario
        per_tf = {
            tf: aggrega(chiusi, quanti, fino_a=limite)
            for tf, quanti in BLOCCHI.items()
        }
        return self._archivia(strumento, per_tf)

    def _giorni_da_chiedere(self, strumento: str, adesso: datetime) -> list:
        """Quali file giornalieri servono. Di norma solo oggi."""
        oggi = adesso.date()
        ultima = ultima_archiviata(strumento, TF.MIN1)
        if ultima is None:
            log.warning(
                "%s: nessun minuto in archivio. Il ciclo prende solo il giorno "
                "in corso; la storia si semina con `python importa_minuti.py`, "
                "e senza il motore non arma i setup intraday.", strumento)
            return [oggi]
        indietro = (oggi - ultima.date()).days
        indietro = max(0, min(indietro, GIORNI_MINUTI_MASSIMI))
        return [oggi - timedelta(days=n) for n in range(indietro, -1, -1)]

    def _aggiorna_dxy(self, adesso: datetime) -> None:
        """Il dollar index, calcolato dai suoi sei costituenti.

        Non produce valutazioni: sul DXY si analizza e non si opera mai
        (`PRIN-08`). Produce la serie da cui `SETUP-19` ricava la bias di
        comando, e senza quella il motore si astiene su tutte le coppie
        tranne l'oro.

        Due dei sei costituenti — `USDCAD` e `USDSEK` — non stanno
        nell'`UNIVERSO` e si scaricano solo per questo. Sono due file al
        mese: il prezzo di non avere un bot fermo.
        """
        chiave = (duka_dxy.NOME_ARCHIVIO, "ore")
        if self._in_riposo(chiave, adesso):
            return
        if not self.serie_da_chiedere(duka_dxy.NOME_ARCHIVIO, TF.H1, adesso):
            return

        mesi = self._mesi_da_chiedere(duka_dxy.NOME_ARCHIVIO, adesso)
        self.richieste += len(mesi) * len(duka_dxy.PESI)
        serie = {
            simbolo: [c for anno, mese in mesi
                      for c in orarie_del_mese(simbolo, anno, mese)]
            for simbolo in duka_dxy.PESI
        }
        dxy = duka_dxy.componi(serie)
        if not dxy:
            self._guasto(chiave, adesso)
            return
        self._riuscito(chiave)
        self._archivia(duka_dxy.NOME_ARCHIVIO, costruisci(dxy))

    def _archivia(
        self, strumento: str, per_tf: dict[TF, list[Candela]]
    ) -> dict[TF, Candela]:
        """Scrive le candele e dice quali timeframe hanno davvero qualcosa di nuovo."""
        ultime: dict[TF, Candela] = {}
        for tf, candele in per_tf.items():
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
        """Fa scattare una valutazione per ogni timeframe aggiornato che conta.

        Sono due famiglie, e tenerne solo una non ha senso:

        - `TF_OPERATIVI` sono i timeframe di **range**, dove il CRT si forma;
        - `TF_INGRESSO_OPERATIVI` sono i secondi tempi di `CRT-04`, dove il
          setup gia' armato **scatta**. Qui prima si fermava a `TF_OPERATIVI`,
          e un setup armato su `4h` non trovava mai nessuno che guardasse i
          `15m`: restava armato fino a scadere.

        L'ordine e' quello della gerarchia, dal mensile al minuto, perche'
        `CTX-10` vuole il timeframe superiore ricalcolato prima che si operi
        su quelli sotto.
        """
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


# L'istanza unica, come per `core/mercato.py`: il ciclo e' uno e lo stato che
# `/salute` mostra deve essere quello del ciclo che gira davvero.
mercato_duka = MercatoDukascopy()


def _alert(strumento: str, tf: TF, candela: Candela, segreto: str) -> AlertIn:
    """La candela appena chiusa, nella forma che tutto il resto sa leggere.

    Qui c'erano **tre** errori nello stesso oggetto, e nessuno di essi
    produceva un log utile: `AlertIn` alzava `ValidationError`, `_valuta` la
    catturava, e il contatore `valutazioni` di `/salute` si incrementava lo
    stesso. Il quadro era quello di un bot che valuta e non trova nulla. In
    realta' **nessuna valutazione era mai arrivata al motore**.

    1. I nomi dei campi. `AlertIn` nasce dal JSON di TradingView e i suoi
       alias sono `symbol`, `tf`, `open`, `high`, `low`, `close`. Passare
       `interval=` e la sola chiusura non riempie nulla: apertura, massimo e
       minimo mancavano, e sono proprio i tre numeri su cui il CRT si misura.

    2. Il nome dello strumento. Il ciclo lavora sui CFD (`EURUSD`), ma chi
       riceve l'alert applica `future_da_ticker`, che su `EURUSD` risponde
       None — lo strumento risultava fuori da PRIN-08. Il ticker del future
       e' la forma giusta: `6E1!`.

    3. Il timeframe. `tf.value` e' `TF_M15`, la forma interna dell'archivio.
       Chi legge l'alert si aspetta `{{interval}}` di TradingView, dove quel
       timeframe si chiama `M15`.
    """
    from core.mercato import ticker_di
    from core.simboli import future_di

    future = future_di(strumento) or strumento
    return AlertIn(
        secret=segreto,
        symbol=ticker_di(future),
        tf=tf.value.replace("TF_", ""),
        candle_close_time_utc=candela.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
        open=candela.apertura,
        high=candela.massimo,
        low=candela.minimo,
        close=candela.chiusura,
        note="dukascopy",
    )
