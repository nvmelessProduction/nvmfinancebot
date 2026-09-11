"""Server dell'impianto: riceve gli alert di TradingView e li fa girare.

Due soli endpoint:
    POST /webhook   riceve l'alert, lo archivia, chiede una decisione
    GET  /salute    dice in che stato siamo

La catena e' sempre la stessa:

    segreto -> archivio -> strategia -> salvaguardie -> azione -> archivio

La decisione oggi e' sempre "NONE" perche' la strategia e' ancora uno stub
(core/strategy.py). Tutto il resto della catena e' vero e funzionante: quando
la strategia arrivera', non ci sara' altro da costruire.
"""

import hmac
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException

from core import broker, notifier, storage
from core.config import impostazioni
from core.log import configura as configura_log
from core.log import diario
from core.models import AlertIn, Decision, Esito
from core.mercato import mercato
from core.sentinella import sentinella
from core.simboli import simbolo_esecuzione
from core.strategy import valuta

log = diario("server")

# Una decisione per volta. Due alert simultanei che passano insieme il
# controllo "quante posizioni ho aperte" aprirebbero una posizione di troppo.
_lucchetto_decisione = threading.Lock()


@asynccontextmanager
async def ciclo_di_vita(app: FastAPI) -> AsyncIterator[None]:
    """Prepara l'impianto all'avvio e lo smonta con ordine alla chiusura."""
    configura_log()
    cfg = impostazioni()
    storage.inizializza()

    log.info("=" * 60)
    log.info("avvio impianto | modalita' %s | archivio %s", cfg.MODE, cfg.DB_PATH)

    if not cfg.webhook_configurato and cfg.FORNITORE_DATI != "mercato":
        log.error("WEBHOOK_SECRET non impostato: /webhook rifiutera' ogni richiesta")
    if not cfg.telegram_configurato:
        log.warning("Telegram non configurato: le notifiche finiranno solo nel log")
    if cfg.bloccato:
        log.warning("freno a mano tirato: esiste il file %s, non partiranno ordini", cfg.FILE_BLOCCO)

    # In dry_run non tocchiamo il broker nemmeno per connetterci.
    if cfg.MODE != "dry_run":
        connesso, messaggio = broker.connetti()
        log.info("MT5: %s - %s", "ok" if connesso else "KO", messaggio)
    else:
        log.info("MT5 non contattato (modalita' dry_run)")

    # --- Fornitore dei dati di analisi ------------------------------------
    if cfg.FORNITORE_DATI in ("tradingview", "mercato"):
        from core.fornitore_tradingview import collega

        collega(suffisso_broker=cfg.MT5_SUFFISSO_SIMBOLI)
        log.info("analisi sul future, esecuzione su CFD via MT5")
        for riga in storage.copertura_candele():
            log.info("  archivio: %s %s, %d candele dal %s",
                     riga["strumento"], riga["tf"], riga["quante"], riga["dalla"][:10])
    else:
        log.info("nessun fornitore dati: il motore si asterra' dichiarandolo")

    # --- Il bot si prende i dati da solo ----------------------------------
    if cfg.FORNITORE_DATI == "mercato":
        mercato.intervallo_sec = cfg.MERCATO_INTERVALLO_SEC
        mercato.su_candela = processa_alert
        mercato.avvia()
        log.info("nessun alert da configurare: le candele le cerca il bot")

    # La sentinella serve se c'e' qualcosa da sorvegliare, adesso o fra poco.
    aperte = storage.posizioni_aperte()
    if aperte and cfg.MODE == "dry_run":
        log.warning(
            "ci sono %d posizioni aperte in archivio ma la modalita' e' dry_run: "
            "le sorveglio comunque",
            len(aperte),
        )
    if cfg.MODE != "dry_run" or aperte:
        sentinella.avvia()

    yield

    mercato.ferma()
    sentinella.ferma()
    broker.disconnetti()
    log.info("impianto fermato")
    log.info("=" * 60)


app = FastAPI(
    title="nvmfinancebot - impianto",
    description="Infrastruttura del bot. La strategia non e' ancora implementata.",
    version="0.2.0",
    lifespan=ciclo_di_vita,
)


def _segreto_valido(segreto_ricevuto: str) -> bool:
    """Confronta il segreto in modo resistente ai timing attack.

    Se WEBHOOK_SECRET non e' impostato rifiutiamo sempre: senza segreto
    chiunque conosca l'URL potrebbe far operare il bot.
    """
    cfg = impostazioni()
    if not cfg.webhook_configurato:
        return False
    return hmac.compare_digest(segreto_ricevuto.encode("utf-8"), cfg.WEBHOOK_SECRET.encode("utf-8"))


def salvaguardia_violata(alert: AlertIn, decisione: Decision) -> Optional[str]:
    """Controlla le salvaguardie prima di operare davvero.

    Restituisce il motivo del blocco, o None se si puo' procedere. Nessuna di
    queste regole decide di aprire qualcosa: possono solo dire di no.
    """
    cfg = impostazioni()

    # 1. Freno a mano: un file, per fermare tutto senza toccare la config.
    if cfg.bloccato:
        return f"freno a mano tirato (esiste il file {cfg.FILE_BLOCCO})"

    # 2. Alert vecchio: descrive un prezzo che non c'e' piu'.
    if cfg.MAX_RITARDO_ALERT_SEC > 0:
        ritardo = alert.ritardo_secondi()
        # None = orario non interpretabile: non blocchiamo per un formato
        # strano, sarebbe il modo peggiore di perdere segnali buoni.
        if ritardo is not None and ritardo > cfg.MAX_RITARDO_ALERT_SEC:
            return (
                f"alert vecchio di {ritardo:.0f}s "
                f"(massimo {cfg.MAX_RITARDO_ALERT_SEC}s): prezzo non piu' attuale"
            )

    # 3. Tetto anti-errore sul volume. Non calcola la size: rifiuta e basta.
    if cfg.VOLUME_MASSIMO > 0 and decisione.volume is not None:
        if decisione.volume > cfg.VOLUME_MASSIMO:
            return (
                f"volume richiesto {decisione.volume} oltre il tetto "
                f"VOLUME_MASSIMO={cfg.VOLUME_MASSIMO}"
            )

    # 4. Capienza dell'impianto: quante posizioni riusciamo a sorvegliare.
    if cfg.MAX_POSIZIONI_APERTE > 0 and decisione.azione in ("BUY", "SELL"):
        try:
            aperte = len(storage.posizioni_aperte())
        except Exception as errore:
            # Se non sappiamo quante ne abbiamo, non ne apriamo altre.
            return f"impossibile contare le posizioni aperte: {errore!r}"
        if aperte >= cfg.MAX_POSIZIONI_APERTE:
            return (
                f"gia' {aperte} posizioni aperte, tetto "
                f"MAX_POSIZIONI_APERTE={cfg.MAX_POSIZIONI_APERTE}"
            )

    # 5. La sentinella deve essere in piedi prima di aprire qualcosa: senza,
    #    stop e target non li guarderebbe nessuno.
    if decisione.azione in ("BUY", "SELL") and (decisione.sl is not None or decisione.tp is not None):
        if not sentinella.attiva():
            return "la sentinella non e' in funzione: stop e target non sarebbero sorvegliati"

    return None


def simbolo_da_eseguire(alert: AlertIn, decisione: Decision) -> Optional[str]:
    """Il simbolo da mandare al broker, con il suffisso del conto.

    La decisione nomina il CFD (`XAUUSD`); il broker puo' chiamarlo
    `XAUUSD.a`. Il suffisso e' un fatto del conto, non della strategia, ed e'
    qui che si aggiunge.

    None quando non si puo' sapere su cosa operare. Ripiegare sul simbolo
    dell'alert sarebbe il peggiore dei mondi: quello e' lo strumento di
    ANALISI, e mandarlo al broker significa chiedergli un future che non ha.
    """
    if not decisione.simbolo:
        return None
    return simbolo_esecuzione(decisione.simbolo, impostazioni().MT5_SUFFISSO_SIMBOLI)


def _esegui_decisione(
    alert: AlertIn,
    decisione: Decision,
    id_alert: int,
) -> tuple[Esito, str, Optional[int], Optional[float]]:
    """Applica la decisione secondo la modalita' operativa.

    Restituisce (esito, dettaglio, ticket, prezzo). Non decide nulla di suo:
    si limita a fare cio' che la decisione dice, o a fermarsi.
    """
    cfg = impostazioni()
    testo = notifier.messaggio_decisione(alert, decisione, cfg.MODE)

    # Nessuna azione richiesta: e' il caso normale finche' la strategia e' uno stub.
    if decisione.azione == "NONE":
        log.info("nessuna azione | %s %s", alert.simbolo, alert.tf)
        return "ignorato", "azione NONE: nessuna operazione", None, None

    blocco = salvaguardia_violata(alert, decisione)

    if cfg.MODE == "dry_run":
        # In simulazione diciamo anche cosa *avrebbe* fermato l'ordine: e' il
        # momento giusto per accorgersi che una salvaguardia e' troppo stretta.
        nota = f" (in auto sarebbe stato bloccato: {blocco})" if blocco else ""
        log.info("simulazione | %s", testo.replace("\n", " | "))
        return "simulato", f"dry_run: nessun ordine inviato al broker{nota}", None, None

    if blocco is not None:
        log.warning("operazione bloccata: %s", blocco)
        notifier.invia(f"{testo}\n\nBLOCCATO: {blocco}")
        return "bloccato", blocco, None, None

    if cfg.MODE == "semi":
        inviato, dettaglio_telegram = notifier.invia(
            f"{testo}\n\nModalita' semi: serve la tua conferma manuale."
        )
        dettaglio = (
            "semi: in attesa di conferma manuale (notifica inviata)"
            if inviato
            else f"semi: in attesa di conferma manuale (NOTIFICA NON CONSEGNATA: {dettaglio_telegram})"
        )
        return "in_attesa_conferma", dettaglio, None, None

    # --- modalita' auto: si opera davvero ---------------------------------
    if decisione.azione == "CLOSE":
        # La chiusura mirata richiede un ticket, che la strategia dovra'
        # indicare quando esistera'. Per ora non abbiamo dove prenderlo.
        dettaglio = "auto: CLOSE non gestibile senza un ticket indicato dalla strategia"
        notifier.invia(f"{testo}\n\n{dettaglio}")
        return "errore", dettaglio, None, None

    if decisione.volume is None or decisione.volume <= 0:
        # Il volume lo decide la strategia, non l'impianto: senza, non si opera.
        dettaglio = "auto: volume non indicato dalla decisione, ordine non inviato"
        notifier.invia(f"{testo}\n\n{dettaglio}")
        return "errore", dettaglio, None, None

    # Si analizza sul future e si opera sul CFD (DEF-33): il simbolo da
    # mandare al broker e' quello della decisione, non quello dell'alert.
    # Mandare `alert.simbolo` significherebbe chiedere a MT5 un contratto
    # future che il broker non quota.
    simbolo_ordine = simbolo_da_eseguire(alert, decisione)
    if simbolo_ordine is None:
        dettaglio = (
            "auto: la decisione non indica su quale strumento operare, "
            "e il simbolo dell'alert e' quello di analisi: ordine non inviato"
        )
        log.error(dettaglio)
        notifier.invia(f"{testo}\n\n{dettaglio}")
        return "errore", dettaglio, None, None

    esito_ordine = broker.invia_ordine(
        simbolo=simbolo_ordine,
        direzione=decisione.azione,
        volume=decisione.volume,
        commento=f"alert {id_alert}",
    )
    notifier.invia(f"{testo}\n\nesecuzione: {esito_ordine.messaggio}")

    if not esito_ordine.ok:
        return "errore", f"auto: {esito_ordine.messaggio}", None, None

    return "eseguito", f"auto: {esito_ordine.messaggio}", esito_ordine.ticket, esito_ordine.prezzo


class ArchiviazioneFallita(RuntimeError):
    """L'alert non e' finito in archivio: non si prosegue.

    Archiviare prima di tutto il resto e' una regola dell'impianto: senza
    traccia dell'alert, una decisione presa non sarebbe ricostruibile.
    """


def processa_alert(alert: AlertIn) -> dict[str, Any]:
    """Il percorso completo di un alert, da qualunque parte arrivi.

    Lo chiamano in due: il webhook di TradingView, e il ciclo di mercato che
    va a prendersi le candele da solo. Tutto cio' che conta — archiviazione,
    riconoscimento dei duplicati, decisione, salvaguardie, esecuzione,
    notifica, registrazione della posizione — sta qui, una volta sola, perche'
    due copie di questo percorso finirebbero per divergere proprio nel punto
    che muove i soldi.

    La verifica del segreto NON sta qui: riguarda solo cio' che arriva da
    internet, ed e' compito di `/webhook`.
    """
    # 2. La candela del future entra in archivio: e' il dato su cui il motore
    #    ragionera' adesso e nelle valutazioni future (DEF-32).
    if impostazioni().FORNITORE_DATI == "tradingview":
        from core.fornitore_tradingview import archivia_candela

        try:
            archiviata, motivo = archivia_candela(alert)
            log.info("candela: %s", motivo)
        except Exception:
            log.exception("archiviazione della candela fallita")

    # 3. Archiviazione dell'alert, prima di tutto il resto.
    try:
        id_alert, gia_visto = storage.salva_alert(alert)
    except Exception as errore:
        log.exception("impossibile salvare l'alert")
        raise ArchiviazioneFallita("archiviazione dell'alert fallita") from errore

    # 3. Consegna doppia (TradingView o il tunnel che ritentano): l'alert e'
    #    gia' stato valutato, rivalutarlo significherebbe raddoppiare l'ordine.
    if gia_visto:
        log.info("alert duplicato ignorato (id %s, %s %s)", id_alert, alert.simbolo, alert.tf)
        return {
            "ricevuto": True,
            "alert_id": id_alert,
            "decisione_id": None,
            "azione": "NONE",
            "esito": "duplicato",
            "dettaglio": "alert gia' ricevuto in precedenza, non rivalutato",
            "modalita": impostazioni().MODE,
        }

    # 4. Decisione ed esecuzione, una per volta.
    decisione = valuta(alert)
    with _lucchetto_decisione:
        try:
            esito, dettaglio, ticket, prezzo = _esegui_decisione(alert, decisione, id_alert)
        except Exception as errore:
            # Qualunque imprevisto: la decisione va comunque registrata.
            esito, dettaglio, ticket, prezzo = (
                "errore",
                f"eccezione durante l'esecuzione: {errore!r}",
                None,
                None,
            )
            log.exception("esecuzione fallita")

        # 5. Registrazione della decisione con il suo esito.
        try:
            id_decisione: Optional[int] = storage.salva_decisione(
                id_alert, decisione, esito, dettaglio, ticket
            )
        except Exception:
            log.exception("impossibile salvare la decisione")
            id_decisione = None

        # 6. Se abbiamo davvero aperto qualcosa lo annotiamo subito: da questo
        #    momento la sentinella se ne fa carico. Se questa scrittura fallisce
        #    la posizione resta sul broker senza sorveglianza: va gridato.
        if esito == "eseguito":
            try:
                storage.registra_posizione(
                    # Quello davvero aperto sul broker: la sentinella dovra'
                    # chiederne il prezzo, e il prezzo del future non
                    # chiuderebbe una posizione sul CFD.
                    simbolo=simbolo_da_eseguire(alert, decisione) or alert.simbolo,
                    direzione=decisione.azione,
                    volume=float(decisione.volume or 0.0),
                    ticket=ticket,
                    decisione_id=id_decisione,
                    prezzo_ingresso=prezzo,
                    sl=decisione.sl,
                    tp=decisione.tp,
                )
            except Exception as errore:
                log.exception("posizione aperta ma NON registrata in archivio")
                notifier.invia(
                    f"ATTENZIONE: ordine eseguito (ticket {ticket}) ma non registrato "
                    f"in archivio: {errore!r}\n"
                    "Stop e target NON sono sorvegliati. Intervieni a mano su MT5."
                )

    return {
        "ricevuto": True,
        "alert_id": id_alert,
        "decisione_id": id_decisione,
        "azione": decisione.azione,
        "esito": esito,
        "dettaglio": dettaglio,
        "modalita": impostazioni().MODE,
    }


@app.post("/webhook")
def webhook(alert: AlertIn) -> dict[str, Any]:
    """Punto di ingresso degli alert TradingView.

    Resta per chi vuole usare gli alert, ma non serve piu': con
    `FORNITORE_DATI=mercato` il bot si prende le candele da solo.
    """
    # Il segreto per primo: se non torna, non lasciamo traccia in archivio.
    if not _segreto_valido(alert.segreto):
        log.warning("richiesta con segreto non valido su %s", alert.simbolo)
        raise HTTPException(status_code=401, detail="segreto non valido")

    try:
        return processa_alert(alert)
    except ArchiviazioneFallita as errore:
        raise HTTPException(status_code=500, detail=str(errore)) from errore


@app.get("/salute")
def salute() -> dict[str, Any]:
    """Stato dell'impianto: modalita', broker, equity, posizioni, salvaguardie."""
    cfg = impostazioni()
    stato_broker = broker.stato()
    conto = stato_broker.get("conto")

    try:
        conteggi = storage.conteggi()
        aperte = storage.posizioni_aperte()
        ultime = storage.ultime_decisioni(5)
        archivio_ok = True
    except Exception:
        log.exception("archivio non leggibile")
        conteggi, aperte, ultime, archivio_ok = {}, [], [], False

    # Il campanello d'allarme: posizioni aperte che nessuno sta guardando.
    scoperte = bool(aperte) and not sentinella.attiva()

    from core import strategy

    fornitore = {
        "configurato": cfg.FORNITORE_DATI,
        "collegato": strategy.fornitore_collegato(),
    }
    if cfg.FORNITORE_DATI == "mercato":
        fornitore["mercato"] = {
            "in_funzione": mercato.in_funzione,
            "intervallo_sec": cfg.MERCATO_INTERVALLO_SEC,
            "giri": mercato.giri,
            "candele_raccolte": mercato.candele_nuove,
            "valutazioni": mercato.valutazioni,
            "ultimo_errore": mercato.ultimo_errore,
        }
    if cfg.FORNITORE_DATI in ("tradingview", "mercato"):
        # La copertura dell'archivio va guardata prima di fidarsi: senza
        # storia sufficiente DEF-26 fa tacere i timeframe, e il bot non opera
        # senza che sia evidente il perche'.
        try:
            fornitore["archivio"] = storage.copertura_candele()
        except Exception as errore:
            fornitore["archivio"] = f"non leggibile: {errore!r}"

    return {
        "modalita": cfg.MODE,
        "fornitore_dati": fornitore,
        "mt5_disponibile": stato_broker["mt5_disponibile"],
        "mt5_connesso": stato_broker["connesso"],
        "mt5_trading_permesso": stato_broker["trading_permesso"],
        "mt5_dettaglio": stato_broker["dettaglio"],
        "equity": conto["equity"] if conto else None,
        "saldo": conto["saldo"] if conto else None,
        "valuta": conto["valuta"] if conto else None,
        "posizioni_aperte_broker": stato_broker["posizioni_aperte"],
        "posizioni_aperte_archivio": len(aperte) if archivio_ok else None,
        "posizioni_scoperte": scoperte,
        "sentinella": sentinella.stato(),
        "salvaguardie": {
            "freno_a_mano": cfg.bloccato,
            "file_blocco": cfg.FILE_BLOCCO,
            "max_ritardo_alert_sec": cfg.MAX_RITARDO_ALERT_SEC,
            "volume_massimo": cfg.VOLUME_MASSIMO,
            "max_posizioni_aperte": cfg.MAX_POSIZIONI_APERTE,
        },
        "archivio_ok": archivio_ok,
        "conteggi": conteggi,
        "ultime_decisioni": ultime,
        "telegram_configurato": cfg.telegram_configurato,
        "webhook_configurato": cfg.webhook_configurato,
    }


if __name__ == "__main__":
    import uvicorn

    configura_log()
    cfg = impostazioni()
    uvicorn.run("main:app", host=cfg.HOST, port=cfg.PORT, reload=False, log_config=None)
