"""Il fornitore conforme: analisi sul future di TradingView, esecuzione su CFD.

E' l'architettura che i documenti prescrivono, e si legge tutta nel vocabolario
di `01_definizioni.md` §7:

```
TradingView   symbol, tf, open/high/low/close, high_c1, low_c1,
              candle_close_time_utc, dxy_close        <- i PREZZI, dal future
server        bias, gap, key level, target, fasi...   <- tutto il RAGIONAMENTO
MT5           equity, valore_punto, pnl               <- solo il CONTO
```

Il bot **analizza sul future e opera sul CFD** (`DEF-32`, `DEF-33`, `DEF-34`).
Nessun prezzo attraversa il confine: `ESCL-12` lo vieta, e qui non succede mai,
perche' i prezzi di analisi arrivano solo da TradingView e da MT5 arrivano solo
numeri del conto.

## Come si accumula la storia

Ogni alert porta **una candela chiusa** di un timeframe. Il server la archivia
e ricalcola tutto dall'archivio. Non serve un abbonamento dati in piu': la
storia si costruisce da sola, un alert alla volta.

`DEF-26` pero' vuole cinque anni di storico, e aspettarli sarebbe assurdo.
Per questo si semina una volta sola, in due modi:

- `importa_storico.py` legge il CSV esportato da TradingView. E' la via
  migliore, ma l'export e' una funzione dei piani a pagamento.
- `scarica_storico.py` prende le stesse candele degli **stessi future** da una
  fonte gratuita. Cambia il fornitore, non lo strumento: `ESCL-12` regge.

Le righe seminate portano la loro provenienza in archivio, e il controllo di
allineamento qui sotto ne tiene conto invece di pretendere che due fornitori
coincidano al decimale.

## Il limite da conoscere

`RISK-12` sorveglia stop e target sul **prezzo scambiato** del future. Un
webhook consegna **chiusure di candela**, non tick. La sorveglianza e' quindi
fine quanto il timeframe piu' basso su cui mandi alert: con alert a un'ora, lo
stop viene controllato una volta l'ora. Se vuoi la sorveglianza al minuto, devi
mandare alert al minuto sul future — e il conteggio degli alert del tuo piano
TradingView diventa il vincolo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from core import broker, storage
from core.aggregazione import costruisci_superiori
from core.definizioni import Bias, Candela
from core.log import diario
from core.models import AlertIn
from core.motore import Fotografia
from core.config import impostazioni
from core.parametri import COMPAGNE_SMT, LOOKBACK_ANNI, TF, UNIVERSO
from core.simboli import (
    DXY_FUTURE,
    cfd_di,
    e_solo_analisi,
    future_da_ticker,
    simbolo_esecuzione,
    timeframe_da_intervallo,
)
from core.stato import Conto, bias_comando_dxy, costruisci_fotografia

log = diario("fornitore")


class FotografiaImpossibile(RuntimeError):
    """Non si puo' costruire la Fotografia, e si sa esattamente perche'.

    Restituire `None` e basta costringeva chi guarda l'archivio a leggere
    "il fornitore non ha potuto costruire la fotografia" senza sapere se
    mancava il conto, lo storico o il calendario. Il motivo e' la meta' utile
    del messaggio: senza, un'astensione legittima e un guasto si somigliano.
    """

# I timeframe che si accumulano dagli alert. TF_3M, TF_6M e TF_12M si
# aggregano dai mensili: aspettare un alert trimestrale per avere una candela
# significherebbe aspettare tre mesi.
TF_DA_ALERT: tuple[TF, ...] = (
    TF.M1, TF.W1, TF.D1, TF.H12, TF.H6, TF.H4, TF.H1,
    # I timeframe di INGRESSO delle coppie intraday di CRT-04. Senza di
    # essi il motore non vede le candele su cui cercare il CISD, l'FVG e il
    # ritorno: i setup non si armano, e la coppia `4h -> 15m` — quella col
    # risultato migliore misurato — non puo' girare.
    #
    # Averli in archivio non basta se chi costruisce la Fotografia non li
    # legge: e' la stessa forma di guasto silenzioso del nome sbagliato.
    TF.MIN15, TF.MIN5, TF.MIN1,
)


def _da_riga(riga: dict) -> Optional[Candela]:
    """Una riga dell'archivio diventa una Candela, o niente se e' incoerente."""
    try:
        momento = datetime.fromisoformat(str(riga["chiusura_utc"]).replace("Z", "+00:00"))
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=timezone.utc)
        return Candela(
            orario=momento.astimezone(timezone.utc),
            apertura=float(riga["apertura"]),
            massimo=float(riga["massimo"]),
            minimo=float(riga["minimo"]),
            chiusura=float(riga["chiusura"]),
        )
    except (ValueError, KeyError, TypeError) as errore:
        # Una riga rotta non deve far cadere l'intero storico, ma nemmeno
        # sparire in silenzio.
        log.warning("candela scartata dall'archivio: %r (%s)", riga, errore)
        return None


def archivia_candela(alert: AlertIn) -> tuple[bool, str]:
    """Archivia la candela portata dall'alert. Va fatto per ogni alert valido.

    Restituisce (archiviata, motivo). Un alert su uno strumento fuori da
    PRIN-08 o su un timeframe fuori da DEF-01 non viene archiviato: non e' un
    errore, e' un alert che non ci riguarda.
    """
    future = future_da_ticker(alert.simbolo)
    if future is None:
        return False, f"{alert.simbolo} non e' uno strumento di PRIN-08"

    tf = timeframe_da_intervallo(alert.tf)
    if tf is None:
        return False, f"timeframe {alert.tf!r} non e' fra i dieci di DEF-01"

    nuova = storage.salva_candela(
        strumento=future,
        tf=tf.value,
        chiusura_utc=alert.chiusura_candela_utc,
        apertura=alert.apertura,
        massimo=alert.massimo,
        minimo=alert.minimo,
        chiusura=alert.chiusura,
    )
    esito = "archiviata" if nuova else "gia' presente"
    return True, f"{future} {tf.value} {esito}"


def verifica_allineamento(alert: AlertIn, future: str, tf: TF) -> Optional[str]:
    """Confronta `high_c1`/`low_c1` dell'alert con la candela precedente in archivio.

    Il vocabolario elenca questi due campi fra i dati che TradingView manda.
    Servono a questo: se il grafico da cui parte l'alert e l'archivio del
    server non concordano sulla candela precedente, uno dei due e' sbagliato,
    e il motore starebbe ragionando su una storia che non esiste.

    Restituisce il motivo della discrepanza, o None se tutto torna. Senza i
    campi non si verifica nulla e non e' un errore: sono facoltativi.

    **Il confronto vale solo fra dati dello stesso fornitore.** L'archivio si
    puo' seminare da una fonte diversa da TradingView (`scarica_storico.py`),
    e due fornitori ricostruiscono il contratto continuo con regole di
    rollover proprie: pretendere che coincidano al decimale farebbe astenere
    il bot per sempre sulla giuntura fra storico seminato e alert dal vivo.
    Su una C1 di altra provenienza il controllo tace, e lo dice al diario.
    """
    if alert.massimo_c1 is None and alert.minimo_c1 is None:
        return None

    righe = storage.candele_archiviate(future, tf.value, limite=2)
    if len(righe) < 2:
        return None                     # non c'e' ancora una C1 con cui confrontare

    provenienza = str(righe[0].get("origine") or "")
    if provenienza != "tradingview":
        log.info(
            "allineamento non verificato su %s %s: la C1 in archivio viene da %r, "
            "non da TradingView", future, tf.value, provenienza or "origine ignota",
        )
        return None

    c1 = _da_riga(righe[0])
    if c1 is None:
        return None

    tolleranza = 1e-9
    if alert.massimo_c1 is not None and abs(alert.massimo_c1 - c1.massimo) > tolleranza:
        return (f"high_c1 dell'alert {alert.massimo_c1} contro {c1.massimo} in archivio")
    if alert.minimo_c1 is not None and abs(alert.minimo_c1 - c1.minimo) > tolleranza:
        return (f"low_c1 dell'alert {alert.minimo_c1} contro {c1.minimo} in archivio")
    return None


def archivio_vecchio(storico, adesso: datetime) -> Optional[str]:
    """L'archivio e' troppo indietro per operarci? Se si', da quando.

    Restituisce `None` quando va bene, altrimenti una descrizione pronta da
    mettere nel motivo dell'astensione -- perche' "l'archivio e' vecchio"
    senza la data non dice a chi legge se mancano due ore o due settimane, e
    sono due problemi diversi.

    La freschezza si misura sulla candela piu' recente di QUALUNQUE
    timeframe, non del solo timeframe valutato. Un archivio aggiornato ha per
    forza qualcosa di recente da qualche parte; uno fermo non ha niente da
    nessuna parte, ed e' proprio quello il caso da cogliere.
    """
    from core.parametri import RITARDO_MASSIMO_ARCHIVIO_GIORNI

    piu_recente = max(
        (c.orario for candele in storico.values() for c in candele),
        default=None,
    )
    if piu_recente is None:
        return None                       # archivio vuoto: lo dice gia' DEF-26
    if piu_recente.tzinfo is None:
        piu_recente = piu_recente.replace(tzinfo=timezone.utc)
    ritardo = adesso - piu_recente
    if ritardo <= timedelta(days=RITARDO_MASSIMO_ARCHIVIO_GIORNI):
        return None
    return (f"{piu_recente:%Y-%m-%d %H:%M} UTC, "
            f"{ritardo.total_seconds() / 86400:.1f} giorni fa")


@dataclass
class FornitoreTradingView:
    """Costruisce la Fotografia dai prezzi archiviati e dal conto MT5."""

    suffisso_broker: str = ""

    # -- storico ----------------------------------------------------------
    def nome_in_archivio(self, future: str) -> str:
        """Sotto quale nome sono archiviate le candele di questo strumento.

        Dipende da **chi le ha scritte**, e i due casi non coincidono:

        - TradingView e il ciclo su fonte gratuita archiviano il **future**
          (`6E`, `GC`), perche' e' quello che scaricano (DEF-32);
        - Dukascopy e MT5 servono il book di un broker, che e' della stessa
          famiglia del CFD: quelle candele sono archiviate sotto `EURUSD`,
          `XAUUSD` (entrambi iterano `UNIVERSO` e salvano con quel nome).

        Leggere col nome sbagliato non produce alcun errore: produce un
        archivio vuoto, quindi `DEF-26` fa tacere ogni timeframe, quindi il
        bot non opera mai — e nei log non compare nulla di anomalo. E' il
        modo piu' silenzioso possibile di avere un bot spento. E' successo
        davvero: aggiunto "mt5" come motore senza aggiornare questo confronto,
        il 2026-09-18 ogni valutazione leggeva l'archivio delle "6E"/"GC" da
        2,4 anni (l'isola vecchia di TradingView) invece di quello vero da
        vent'anni, e DEF-26 taceva su M15/M5/M1min per ogni singolo alert.
        """
        if impostazioni().FORNITORE_DATI not in ("dukascopy", "mt5"):
            return future
        return cfd_di(future) or future

    def storico(self, future: str) -> dict[TF, tuple[Candela, ...]]:
        """Lo storico dello strumento, dall'archivio, col nome giusto."""
        nome = self.nome_in_archivio(future)
        storico: dict[TF, tuple[Candela, ...]] = {}
        for tf in TF_DA_ALERT:
            righe = storage.candele_archiviate(nome, tf.value)
            candele = tuple(c for c in (_da_riga(r) for r in righe) if c is not None)
            storico[tf] = candele

        for tf, aggregate in costruisci_superiori(storico.get(TF.M1, ())).items():
            storico[tf] = aggregate

        self._segnala_storia_corta(future, storico)
        return storico

    def _segnala_storia_corta(self, future: str, storico: dict) -> None:
        """DEF-26 vuole cinque anni. Dove non ci sono, va detto.

        Un timeframe con poca storia produce meno livelli strutturali, quindi
        target piu' vicini, e con meno di tre candele tace del tutto. Non e'
        un errore ma cambia il comportamento, e tacerlo lo renderebbe
        inspiegabile.
        """
        soglia = datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_ANNI)
        for tf, candele in storico.items():
            if len(candele) < 3:
                log.warning(
                    "%s %s: %d candele, DEF-26 ne vuole almeno 3: il timeframe tace",
                    future, tf.value, len(candele),
                )
            elif candele[0].orario > soglia:
                anni = (candele[-1].orario - candele[0].orario).days / 365.0
                log.info(
                    "%s %s: %.1f anni di storia, DEF-26 ne vuole %d "
                    "(sulle orarie la fonte gratuita copre 2 anni: il resto "
                    "si accumula girando)",
                    future, tf.value, anni, LOOKBACK_ANNI,
                )

    # -- conto (solo da MT5) ----------------------------------------------
    def conto(self, cfd: str) -> Optional[Conto]:
        """Equity, posizioni e P&L. **Solo numeri del conto, nessun prezzo di analisi.**

        `prezzo_cfd` e' l'unico prezzo che entra da qui, ed e' quello di
        esecuzione: serve a convertire la distanza di stop, misurata sul
        future in forma adimensionale, in punti dello strumento operativo
        (`DEF-47`, `PA-62`). Non viene mai confrontato con un prezzo future.
        """
        simbolo = simbolo_esecuzione(cfd, self.suffisso_broker)

        ok_specifiche, specifiche, messaggio = broker.specifiche_simbolo(simbolo)
        if not ok_specifiche or specifiche is None:
            log.error("specifiche di %s non leggibili: %s", simbolo, messaggio)
            return None

        ok_prezzo, tick, messaggio = broker.prezzo_corrente(simbolo)
        if not ok_prezzo or tick is None:
            log.warning("nessuna quotazione per %s: %s", simbolo, messaggio)
            return None

        ok_conto, dati, messaggio = broker.info_conto()
        if not ok_conto or dati is None:
            log.error("conto non leggibile: %s", messaggio)
            return None

        _, posizioni, _ = broker.posizioni_per_strumento()

        adesso = datetime.now(timezone.utc)
        inizio_giorno = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
        inizio_settimana = inizio_giorno - timedelta(days=inizio_giorno.weekday())
        inizio_mese = inizio_giorno.replace(day=1)
        _, giornaliero, _ = broker.pnl_chiuso(inizio_giorno)
        _, settimanale, _ = broker.pnl_chiuso(inizio_settimana)
        _, mensile, _ = broker.pnl_chiuso(inizio_mese)

        equity = float(dati["equity"])
        return Conto(
            equity=equity,
            # Prezzo di mezzo: la direzione non e' ancora nota, quindi non si
            # sa se si entrera' in ask o in bid. L'esecuzione vera dista mezzo
            # spread, e CTX-03 accetta esplicitamente di non filtrare su questo.
            prezzo_cfd=(tick["bid"] + tick["ask"]) / 2,
            valore_punto=specifiche["valore_punto"],
            passo_broker=specifiche["volume_step"],
            spread=tick["ask"] - tick["bid"],
            posizioni_aperte_per_strumento=posizioni,
            pnl_giornaliero=giornaliero,
            equity_inizio_giornata=equity - giornaliero,
            pnl_settimanale=settimanale,
            equity_inizio_settimana=equity - settimanale,
            pnl_mensile=mensile,
            equity_inizio_mese=equity - mensile,
        )

    # -- freschezza --------------------------------------------------------
    def costruisci(self, alert: AlertIn) -> Optional[tuple[Fotografia, TF]]:
        """Da un alert di TradingView alla Fotografia su cui il motore decide."""
        future = future_da_ticker(alert.simbolo)
        if future is None:
            raise FotografiaImpossibile(
                f"{alert.simbolo} non e' uno strumento di PRIN-08")

        tf_trigger = timeframe_da_intervallo(alert.tf)
        if tf_trigger is None:
            raise FotografiaImpossibile(
                f"il timeframe {alert.tf!r} non e' fra i dieci di DEF-01")

        if e_solo_analisi(future):
            # Il DXY aggiorna l'archivio e non innesca nulla: PRIN-08 dice
            # che non si opera mai su di lui.
            raise FotografiaImpossibile(
                "PRIN-08: sul DXY si analizza, non si opera")

        cfd = cfd_di(future)
        if cfd is None or cfd not in UNIVERSO:
            raise FotografiaImpossibile(
                f"nessun CFD operativo corrisponde al future {future}")

        discrepanza = verifica_allineamento(alert, future, tf_trigger)
        if discrepanza is not None:
            # PRIN-99: se il grafico e l'archivio non concordano, uno dei due
            # e' sbagliato e non si opera su nessuno dei due.
            raise FotografiaImpossibile(
                f"archivio disallineato su {future} {tf_trigger.value}: {discrepanza}")

        adesso = datetime.now(timezone.utc)
        vecchiaia = archivio_vecchio(self.storico(future), adesso)
        if vecchiaia is not None:
            # PRIN-99, e qui il costo di sbagliare e' massimo. Il CRT si cerca
            # sulle candele in archivio; l'ordine parte al prezzo CORRENTE.
            # Con un archivio fermo, stop e bersaglio nascono da livelli
            # vecchi mentre l'ingresso avviene oggi -- un'operazione costruita
            # su un grafico e aperta su un altro.
            #
            # `verifica_allineamento` non lo intercetta: confronta l'alert con
            # l'archivio, e sulla via Dukascopy l'alert NASCE dall'archivio,
            # quindi combacia sempre. `DEF-26` nemmeno: conta le candele e non
            # ne guarda la data.
            raise FotografiaImpossibile(
                f"archivio di {future} fermo a {vecchiaia}: il CRT si cercherebbe "
                f"su candele vecchie e l'ordine partirebbe al prezzo di adesso")

        conto = self.conto(cfd)
        if conto is None:
            raise FotografiaImpossibile(
                f"MT5 non ha dato conto e prezzo per {cfd}: terminale chiuso, "
                f"non connesso, oppure simbolo assente (controlla "
                f"MT5_SUFFISSO_SIMBOLI)")

        adesso = datetime.now(timezone.utc)
        eventi, eta, motivo = _calendario(adesso)
        if eventi is None:
            # WARNING e non ERROR: con `PA-55 = opera` questa non e' piu'
            # un'avaria ma una condizione dichiarata, e un ERROR ripetuto a
            # ogni valutazione insegna a ignorare gli ERROR.
            log.warning("calendario news non utilizzabile: %s", motivo)

        # Le fasi del gap sono sorveglianza (DEF-43, DEF-45) e dipendono dai
        # prezzi scambiati fra una chiusura e l'altra. Con soli alert a
        # chiusura di candela restano a zero, e SETUP-09 blocca gli ingressi
        # da gap: prudente, e dichiarato.
        # SETUP-19 e RISK-05 — la bias del DXY. L'archivio del DXY viene
        # aggiornato a ogni giro da `mercato.py` e fin qui non lo leggeva
        # nessuno: `bias_dxy` restava al suo valore di partenza NESSUNA e il
        # motore non lo guardava affatto, quindi si operava sulla sola bias
        # propria dello strumento su cinque coppie su sei.
        #
        # Se l'archivio del DXY e' assente o troppo corto la bias torna
        # NESSUNA, e SETUP-19 dice che allora non si opera su alcuna coppia.
        # E' astensione, non guasto: il motivo compare nella decisione.
        bias_dxy = bias_comando_dxy(self.storico(DXY_FUTURE), adesso)

        foto = costruisci_fotografia(
            istante=adesso,
            strumento=cfd,
            storico=self.storico(future),
            conto=conto,
            bias_dxy=bias_dxy,
            # CRT-12 — senza gli storici delle compagne la divergenza SMT non
            # si puo' valutare, e una conferma che non si valuta e' una
            # conferma morta: e' la classe di DEF-33.
            storici_compagni={
                c: self.storico(UNIVERSO[c].future if c in UNIVERSO else c)
                for c in COMPAGNE_SMT.get(cfd, ())
            },
            eventi_news=eventi or (),
            eta_calendario_ore=eta,
        )
        return foto, tf_trigger


def _calendario(adesso: datetime):
    """Il calendario news dal file configurato (PA-54)."""
    from core import calendario
    from core.parametri import PERCORSO_CALENDARIO_NEWS

    return calendario.carica(PERCORSO_CALENDARIO_NEWS, adesso)


def collega(suffisso_broker: str = "") -> FornitoreTradingView:
    """Registra il fornitore nella strategia."""
    from core import strategy

    fornitore = FornitoreTradingView(suffisso_broker=suffisso_broker)
    strategy.registra_fornitore(fornitore.costruisci)
    log.info("fornitore TradingView collegato: analisi sul future, esecuzione su CFD")
    return fornitore
