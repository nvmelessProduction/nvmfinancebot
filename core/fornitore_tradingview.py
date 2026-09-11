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
from core.parametri import LOOKBACK_ANNI, TF, UNIVERSO
from core.simboli import (
    cfd_di,
    e_solo_analisi,
    future_da_ticker,
    simbolo_esecuzione,
    timeframe_da_intervallo,
)
from core.stato import Conto, costruisci_fotografia

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


@dataclass
class FornitoreTradingView:
    """Costruisce la Fotografia dai prezzi archiviati e dal conto MT5."""

    suffisso_broker: str = ""

    # -- storico ----------------------------------------------------------
    def storico(self, future: str) -> dict[TF, tuple[Candela, ...]]:
        """Lo storico del future, dai prezzi che TradingView ha mandato."""
        storico: dict[TF, tuple[Candela, ...]] = {}
        for tf in TF_DA_ALERT:
            righe = storage.candele_archiviate(future, tf.value)
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
                    "(importa lo storico da TradingView)",
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

    # -- fotografia --------------------------------------------------------
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

        conto = self.conto(cfd)
        if conto is None:
            raise FotografiaImpossibile(
                f"MT5 non ha dato conto e prezzo per {cfd}: terminale chiuso, "
                f"non connesso, oppure simbolo assente (controlla "
                f"MT5_SUFFISSO_SIMBOLI)")

        adesso = datetime.now(timezone.utc)
        eventi, eta, motivo = _calendario(adesso)
        if eventi is None:
            log.error("calendario news non utilizzabile: %s", motivo)

        # Le fasi del gap sono sorveglianza (DEF-43, DEF-45) e dipendono dai
        # prezzi scambiati fra una chiusura e l'altra. Con soli alert a
        # chiusura di candela restano a zero, e SETUP-09 blocca gli ingressi
        # da gap: prudente, e dichiarato.
        foto = costruisci_fotografia(
            istante=adesso,
            strumento=cfd,
            storico=self.storico(future),
            conto=conto,
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
