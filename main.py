"""Server del bot: raccoglie le candele, decide, esegue, sorveglia.

Due endpoint:
    GET  /salute    stato di tutto: conto, archivio, mercato, sentinella
    POST /webhook   la vecchia porta per gli alert di TradingView, che resta
                    per chi la vuole ma non serve piu': con
                    FORNITORE_DATI=mercato le candele se le prende il bot

La catena e' sempre la stessa, da qualunque parte arrivi la candela:

    archivio -> strategia -> salvaguardie -> azione -> archivio

La strategia c'e' ed e' quella dei documenti in `docs/`: il motore sta in
`core/motore.py`, le regole nei moduli attorno. Ogni decisione porta con se'
gli identificativi delle regole che l'hanno prodotta — sia quelle applicate
sia quelle che hanno bloccato — e finiscono in archivio e su Telegram, perche'
un bot che non sa dire perche' ha fatto quello che ha fatto non e' verificabile.

Le salvaguardie, qui, possono solo dire di no: nessuna di loro apre niente.
"""

import hmac
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from datetime import datetime, timezone

from core import broker, notifier, storage
from core.config import impostazioni
from core.log import configura as configura_log
from core.log import diario
from core import pannello
from core.models import AlertIn, Decision, Esito
from core.mercato import mercato
from core.mercato_duka import mercato_duka
from core.mercato_mt5 import mercato_mt5
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

    if not cfg.webhook_configurato and cfg.FORNITORE_DATI not in ("mercato", "mt5"):
        log.error("WEBHOOK_SECRET non impostato: /webhook rifiutera' ogni richiesta")
    if not cfg.telegram_configurato:
        log.warning("Telegram non configurato: le notifiche finiranno solo nel log")
    if cfg.bloccato:
        log.warning("freno a mano tirato: esiste il file %s, non partiranno ordini", cfg.FILE_BLOCCO)

    # In dry_run non tocchiamo il broker nemmeno per connetterci.
    if cfg.MODE != "dry_run":
        connesso, messaggio = broker.connetti()
        log.info("MT5: %s - %s", "ok" if connesso else "KO", messaggio)
        if connesso:
            _annuncia_il_conto(cfg)
    else:
        log.info("MT5 non contattato (modalita' dry_run)")

    # --- Fornitore dei dati di analisi ------------------------------------
    if cfg.FORNITORE_DATI in ("tradingview", "mercato", "dukascopy", "mt5"):
        from core.fornitore_tradingview import collega

        collega(suffisso_broker=cfg.MT5_SUFFISSO_SIMBOLI)
        log.info("analisi sul future, esecuzione su CFD via MT5")
        for riga in storage.copertura_candele():
            log.info("  archivio: %s %s, %d candele dal %s",
                     riga["strumento"], riga["tf"], riga["quante"], riga["dalla"][:10])
    else:
        log.info("nessun fornitore dati: il motore si asterra' dichiarandolo")

    # --- Il calendario news, che senza non si opera -----------------------
    _prepara_calendario()

    # --- Il bot si prende i dati da solo ----------------------------------
    if cfg.FORNITORE_DATI == "mercato":
        mercato.intervallo_sec = cfg.MERCATO_INTERVALLO_SEC
        mercato.su_candela = processa_alert
        mercato.avvia()
        log.info("nessun alert da configurare: le candele le cerca il bot")
    elif cfg.FORNITORE_DATI == "dukascopy":
        # Gli stessi dati su cui ogni misura del progetto e' stata fatta:
        # estremi toccati e non campionati, BID e ASK separati. Su una
        # fonte aggregata il 37,7% degli esiti cambiava.
        mercato_duka.intervallo_sec = cfg.MERCATO_INTERVALLO_SEC
        mercato_duka.su_candela = processa_alert
        mercato_duka.segreto = cfg.WEBHOOK_SECRET or ""
        mercato_duka.avvia()
        log.info("candele da Dukascopy: prezzi scambiati, spread misurato")
    elif cfg.FORNITORE_DATI == "mt5":
        # Nessun limite di richieste, gia' connesso: risolve lo stallo di
        # ore che Dukascopy impone quando limita questo indirizzo. H4 e'
        # ricostruito dalle orarie sui confini di Dukascopy (vedi
        # mercato_mt5.TIMEFRAME_DAL_VIVO); D1/W1/M1 restano quelli
        # dell'archivio Dukascopy, meno freschi finche' non si risolve
        # anche per loro lo stesso disallineamento di confine.
        mercato_mt5.intervallo_sec = cfg.MERCATO_INTERVALLO_SEC
        mercato_mt5.su_candela = processa_alert
        mercato_mt5.segreto = cfg.WEBHOOK_SECRET or ""
        mercato_mt5.suffisso = cfg.MT5_SUFFISSO_SIMBOLI
        mercato_mt5.avvia()
        log.info("candele da MT5: nessun limite di richieste, H4 ricostruito dalle orarie")

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
    mercato_mt5.ferma()
    sentinella.ferma()
    broker.disconnetti()
    log.info("impianto fermato")
    log.info("=" * 60)


app = FastAPI(
    title="nvmfinancebot",
    description=(
        "Bot di trading: si analizza sul future, si opera sul CFD via MT5.\n\n"
        "Il motore di strategia vive in `core/motore.py` e nei moduli attorno "
        "(`definizioni`, `setup`, `gestione`, `rischio`, `contesto`, "
        "`esclusioni`), con le regole tradotte dai documenti in `docs/`. Ogni "
        "decisione porta con se' gli identificativi delle regole che l'hanno "
        "prodotta, e finiscono in archivio e su Telegram.\n\n"
        "Le candele se le procura `core/mercato.py`: non serve configurare "
        "alert."
    ),
    version="1.0.0",
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
        # Il tetto si misura sulla CANDELA, non in assoluto: 180 secondi sono
        # tre candele da un minuto e lo 0,2% di una giornaliera. Vedi
        # `ritardo_massimo` in core/parametri.
        from core.parametri import ritardo_massimo
        from core.simboli import timeframe_da_intervallo

        tf_alert = timeframe_da_intervallo(alert.tf)
        tetto = (cfg.MAX_RITARDO_ALERT_SEC if tf_alert is None
                 else ritardo_massimo(tf_alert, cfg.MAX_RITARDO_ALERT_SEC))
        if ritardo is not None and ritardo > tetto:
            return (
                f"alert vecchio di {ritardo:.0f}s (su {alert.tf} il massimo e' "
                f"{tetto:.0f}s): il prezzo non e' piu' quello del segnale"
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

    # 5. Il conto e' quello che credi? In auto si inviano ordini veri, e
    #    dal log non si distingue un demo da un conto con i soldi dentro.
    #    Il consenso al reale si da' una volta, per iscritto, nel .env.
    if cfg.MODE == "auto" and decisione.azione in ("BUY", "SELL") and not cfg.CONSENTI_CONTO_REALE:
        demo, dettaglio = broker.conto_e_demo()
        if not demo:
            return (
                f"{dettaglio}. Per operare davvero su questo conto metti "
                f"CONSENTI_CONTO_REALE=true nel file .env"
            )

    # 6. La sentinella deve essere in piedi prima di aprire qualcosa: senza,
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
        notifier.invia(f"{testo}\n\n⛔ <i>{blocco}</i>")
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

    # RISK-02 — il ridimensionamento va deciso PRIMA di aprire, perche' PA-63
    # puo' imporre di non aprire affatto: se adeguare una posizione esistente
    # producesse un volume sotto il passo del broker, aprire comunque darebbe
    # un'esposizione fuori scala e non dichiarata.
    adeguamenti, blocco_risk02 = _ridimensionamenti_del_gruppo(
        decisione.simbolo or "", simbolo_ordine
    )
    if blocco_risk02 is not None:
        log.warning("apertura annullata: %s", blocco_risk02)
        notifier.invia(f"{testo}\n\n⛔ <i>{blocco_risk02}</i>")
        return "bloccato", blocco_risk02, None, None

    # Stop e target partono ATTACCATI all'ordine, non solo in archivio: se il
    # bot muore la posizione resta comunque protetta dal broker, e su MT5 le
    # colonne S/L e T/P smettono di essere vuote. La sentinella resta la rete
    # che gestisce GEST-04, che uno stop statico non sa esprimere.
    #
    # Al broker va il TARGET FINALE, non TP1: TP1 e' un parziale del 25% e il
    # broker chiuderebbe tutto. Il parziale resta mestiere della sentinella.
    esito_ordine = broker.invia_ordine(
        simbolo=simbolo_ordine,
        direzione=decisione.azione,
        volume=decisione.volume,
        commento=f"alert {id_alert}",
        stop=decisione.sl,
        target=decisione.tp,
    )
    notifier.invia(f"{testo}\n\n⏱ <i>{esito_ordine.messaggio}</i>")

    if not esito_ordine.ok:
        return "errore", f"auto: {esito_ordine.messaggio}", None, None

    # Aperta la nuova, `n` e' cambiato: le vecchie scendono al nuovo rischio.
    # Va dopo l'apertura e non prima, perche' un'apertura fallita non deve
    # lasciare il gruppo ridimensionato per una posizione che non esiste.
    _applica_ridimensionamenti(adeguamenti)

    return "eseguito", f"auto: {esito_ordine.messaggio}", esito_ordine.ticket, esito_ordine.prezzo


def _ridimensionamenti_del_gruppo(
    strumento: str, simbolo_broker: str
) -> tuple[tuple, Optional[str]]:
    """RISK-02 — Cosa va ridimensionato nel gruppo di correlazione, e se si apre.

    Non solleva: un guasto qui non deve impedire un'apertura che tutte le
    regole hanno gia' approvato. Si annota e si prosegue senza ridimensionare,
    che e' il comportamento che il bot aveva finora.
    """
    try:
        from core.parametri import UNIVERSO
        from core.rischio import gruppo_di, ridimensionamenti
        from core.simboli import cfd_da_simbolo_esecuzione

        if strumento not in UNIVERSO:
            return (), None

        ok_spec, specifiche, _ = broker.specifiche_simbolo(simbolo_broker)
        if not ok_spec or specifiche is None:
            return (), None

        suffisso = impostazioni().MT5_SUFFISSO_SIMBOLI
        gruppo = gruppo_di(strumento)
        nel_gruppo = []
        for riga in storage.posizioni_aperte():
            altro = cfd_da_simbolo_esecuzione(str(riga["simbolo"]), suffisso)
            if altro is not None and gruppo_di(altro) == gruppo:
                nel_gruppo.append(riga)

        return ridimensionamenti(
            strumento, nel_gruppo, float(specifiche["volume_step"])
        )
    except Exception:
        log.exception("calcolo del ridimensionamento RISK-02 fallito")
        return (), None


def _applica_ridimensionamenti(adeguamenti: tuple) -> None:
    """Riduce il volume delle posizioni gia' aperte, una per una.

    Una riduzione fallita non annulla le altre e non annulla l'apertura: la
    posizione resta al rischio vecchio, e lo si dice. Annullare a meta' un
    ridimensionamento parziale lascerebbe il gruppo in uno stato peggiore di
    quello di partenza.
    """
    for adeguamento in adeguamenti:
        if adeguamento.ticket is None:
            continue
        try:
            esito = broker.chiudi_posizione(
                int(adeguamento.ticket), volume=adeguamento.da_chiudere
            )
            if not esito.ok:
                log.error(
                    "RISK-02: ridimensionamento della posizione %s fallito: %s",
                    adeguamento.id_posizione, esito.messaggio,
                )
                notifier.invia(
                    f"ATTENZIONE: RISK-02 chiede di ridurre la posizione "
                    f"{adeguamento.ticket} a {adeguamento.volume_bersaglio} lotti "
                    f"ma la riduzione e' fallita: {esito.messaggio}"
                )
                continue
            storage.ridimensiona_posizione(
                adeguamento.id_posizione,
                adeguamento.volume_bersaglio,
                adeguamento.rischio_nuovo,
            )
            log.info(
                "RISK-02: posizione %s ridotta da %s a %s lotti (rischio %.2f%%)",
                adeguamento.id_posizione, adeguamento.volume_attuale,
                adeguamento.volume_bersaglio, adeguamento.rischio_nuovo * 100,
            )
        except Exception:
            log.exception(
                "ridimensionamento della posizione %s fallito", adeguamento.id_posizione
            )


def _annuncia_il_conto(cfg) -> None:
    """Dice a voce alta su che conto si sta per operare.

    In `auto` il bot invia ordini veri, e nel log degli ordini un conto demo
    e un conto con i soldi dentro sono identici. Chi accende deve poterlo
    leggere in chiaro, all'avvio, senza andarlo a cercare su MT5.
    """
    demo, dettaglio = broker.conto_e_demo()
    if cfg.MODE != "auto":
        log.info("conto: %s (modalita' %s: non si invia nulla)", dettaglio, cfg.MODE)
        return

    if demo:
        log.info("conto: %s - modalita' AUTO su conto demo", dettaglio)
        notifier.invia(f"nvmfinancebot avviato in AUTO su {dettaglio}.")
        return

    if cfg.CONSENTI_CONTO_REALE:
        log.warning("=" * 60)
        log.warning("MODALITA' AUTO SU CONTO REALE: %s", dettaglio)
        log.warning("CONSENTI_CONTO_REALE=true: gli ordini partiranno davvero.")
        log.warning("=" * 60)
        notifier.invia(f"ATTENZIONE: nvmfinancebot in AUTO su CONTO REALE.\n{dettaglio}")
        return

    log.warning("=" * 60)
    log.warning("Il conto collegato NON e' un demo: %s", dettaglio)
    log.warning("In auto gli ordini verranno RIFIUTATI dalla salvaguardia.")
    log.warning("Se e' voluto, metti CONSENTI_CONTO_REALE=true nel file .env.")
    log.warning("=" * 60)
    notifier.invia(
        f"nvmfinancebot e' in AUTO ma il conto non e' un demo ({dettaglio}).\n"
        "Gli ordini saranno rifiutati finche' non metti CONSENTI_CONTO_REALE=true."
    )


def _prepara_calendario() -> None:
    """Crea il calendario news se manca, e dice cosa comporta averlo vuoto.

    Cosa comporta dipende da `PA-55`, e il messaggio deve seguirlo. Quando la
    lettura era `astieniti` questa funzione annunciava "IL BOT NON OPERERA'"
    ed era vero; con `opera` la stessa riga sarebbe una bugia detta
    all'accensione, e chi la legge starebbe tranquillo per il motivo
    sbagliato.
    """
    from pathlib import Path

    from core import calendario
    from core.parametri import (
        ETA_MASSIMA_CALENDARIO_ORE,
        PERCORSO_CALENDARIO_NEWS,
        richiedi,
    )

    percorso = Path(PERCORSO_CALENDARIO_NEWS)
    if not percorso.exists():
        try:
            calendario.scrivi_modello(percorso)
            log.info("creato il calendario news vuoto: %s", percorso)
        except OSError:
            log.exception("impossibile creare il calendario news in %s", percorso)
            return

    eventi, eta, motivo = calendario.carica(percorso, datetime.now(timezone.utc))
    if eventi:
        log.info("calendario news: %s", motivo)
        if eta is not None and eta > ETA_MASSIMA_CALENDARIO_ORE:
            # Con PA-55 = opera un calendario vecchio non ferma nulla, ed e'
            # proprio per questo che va detto: gli eventi che contiene sono
            # passati, quindi CTX-02 non trovera' mai nulla contro cui
            # bloccare. Il filtro risulta acceso mentre e' spento.
            log.warning(
                "il calendario news ha %.0f ore: gli eventi dentro sono "
                "passati, quindi CTX-02 non blocchera' nulla. Aggiornalo.", eta)
        return

    if richiedi("PA-55") == "astieniti":
        log.warning("=" * 60)
        log.warning("IL BOT NON OPERERA' finche' il calendario news e' vuoto.")
        log.warning("Apri %s e aggiungi una riga per ogni notizia, in orario UTC:", percorso)
        log.warning("   data_ora_utc,valuta,stelle,descrizione")
        log.warning("   2026-09-11T12:30:00Z,USD,3,Non-Farm Payrolls")
        log.warning("Mettici anche gli eventi a una e due stelle: servono a")
        log.warning("distinguere una giornata tranquilla da un file mai compilato.")
        log.warning("=" * 60)
        notifier.invia(
            "nvmfinancebot avviato, ma NON operera': il calendario news e' vuoto.\n"
            f"Compila {percorso} e riavvia."
        )
        return

    log.warning("=" * 60)
    log.warning("Calendario news vuoto. Il bot OPERERA' lo stesso (PA-55).")
    log.warning("Quello che perdi e' CTX-02: il divieto di aprire da 30 minuti")
    log.warning("prima a 30 minuti dopo una notizia a tre stelle. Senza")
    log.warning("calendario non c'e' alcun evento contro cui confrontare")
    log.warning("l'orario, quindi quel divieto non esiste: il bot puo' aprire")
    log.warning("un minuto prima di un NFP o di un CPI.")
    log.warning("Per riaccenderlo basta compilare %s:", percorso)
    log.warning("   data_ora_utc,valuta,stelle,descrizione")
    log.warning("   2026-09-11T12:30:00Z,USD,3,Non-Farm Payrolls")
    log.warning("=" * 60)
    notifier.invia(
        "nvmfinancebot avviato. Il calendario news e' vuoto: il bot opera "
        "lo stesso (PA-55), ma il filtro news CTX-02 e' spento e puo' "
        "aprire a ridosso di un dato ad alto impatto."
    )


class ArchiviazioneFallita(RuntimeError):
    """L'alert non e' finito in archivio: non si prosegue.

    Archiviare prima di tutto il resto e' una regola dell'impianto: senza
    traccia dell'alert, una decisione presa non sarebbe ricostruibile.
    """


def _gestisci_posizioni_aperte(alert: AlertIn) -> int:
    """Applica al broker e all'archivio le azioni di GEST-08, GEST-10, SETUP-17.

    Restituisce quante ne ha applicate. Non solleva mai: una rivalutazione che
    fallisce non deve impedire la valutazione di un ingresso nuovo, e nemmeno
    la sorveglianza di stop e target, che vive per conto suo nella sentinella.

    L'ordine di scrittura conta. Per una chiusura si chiude **prima** sul
    broker e si scrive **dopo** in archivio: se si invertisse, un archivio che
    dice "chiusa" e un broker che dice "aperta" darebbero una posizione senza
    piu' nessuno che ne sorvegli lo stop. Al contrario, un broker chiuso e un
    archivio non aggiornato viene riconciliato dalla sentinella al giro dopo.
    """
    from core import strategy

    try:
        azioni = strategy.gestisci_aperte(alert)
    except Exception:
        log.exception("rivalutazione delle posizioni aperte fallita")
        return 0

    applicate = 0
    for azione in azioni:
        try:
            if azione.tipo == "chiudi":
                if azione.ticket is None:
                    continue
                esito = broker.chiudi_posizione(int(azione.ticket))
                if not esito.ok:
                    log.error("%s: chiusura fallita: %s", azione.regola, esito.messaggio)
                    notifier.invia(
                        f"ATTENZIONE: {azione.regola} chiede di chiudere la posizione "
                        f"{azione.ticket} ma la chiusura e' fallita: {esito.messaggio}"
                    )
                    continue
                storage.chiudi_posizione(
                    azione.id_posizione, esito.prezzo, f"{azione.regola}: {azione.motivo}"
                )
            elif azione.tipo == "break_even":
                # Lo stop si sposta in archivio E sul broker: da quando
                # l'ordine parte con `sl` attaccato sono due reti, e due reti
                # che dicono cose diverse sono peggio di una sola. Si marca
                # anche come gia' spostato, perche' GEST-05 vieta di rifarlo.
                nuovo = float(azione.valore or 0.0)
                storage.applica_parziale_tp1(
                    azione.id_posizione,
                    _volume_attuale(azione.id_posizione),
                    nuovo,
                )
                if azione.ticket is not None:
                    esito = broker.modifica_livelli(int(azione.ticket), stop=nuovo)
                    if not esito.ok:
                        log.warning("%s: stop spostato in archivio ma non sul "
                                    "broker per %s: %s",
                                    azione.regola, azione.ticket, esito.messaggio)
            elif azione.tipo == "estendi_target":
                nuovo = float(azione.valore or 0.0)
                storage.aggiorna_target(azione.id_posizione, nuovo)
                if azione.ticket is not None:
                    esito = broker.modifica_livelli(int(azione.ticket), target=nuovo)
                    if not esito.ok:
                        log.warning("%s: target esteso in archivio ma non sul "
                                    "broker per %s: %s",
                                    azione.regola, azione.ticket, esito.messaggio)
            else:
                log.warning("azione di gestione sconosciuta: %r", azione.tipo)
                continue
        except Exception:
            log.exception("azione %s su posizione %s fallita", azione.tipo, azione.id_posizione)
            continue

        applicate += 1
        log.info(
            "%s su posizione %s: %s (%s)",
            azione.regola, azione.id_posizione, azione.tipo, azione.motivo,
        )
        notifier.invia(f"{azione.regola} — {azione.motivo}")

    return applicate


def _volume_attuale(id_posizione: int) -> float:
    """Il volume che l'archivio registra per quella posizione.

    Serve a SETUP-17, che sposta lo stop senza toccare il volume: la stessa
    scrittura di GEST-04 lo richiede, e riscriverlo uguale e' piu' sicuro che
    avere due percorsi di scrittura diversi per la stessa colonna.
    """
    for riga in storage.posizioni_aperte():
        if int(riga["id"]) == id_posizione:
            return float(riga["volume"])
    return 0.0


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

    # 4. Prima di decidere un ingresso nuovo: cosa cambia per cio' che e'
    #    gia' aperto (GEST-08, GEST-10, SETUP-17). Va prima, perche' una
    #    posizione chiusa da GEST-10 libera un posto sotto il tetto di RISK-06
    #    e la valutazione successiva deve vederlo.
    gestite = _gestisci_posizioni_aperte(alert)

    # 5. Decisione ed esecuzione, una per volta.
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

        # 5bis. Registrazione della decisione con il suo esito.
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
                    # Lo stato di GEST-12. Senza questi tre la sentinella
                    # riceve una posizione che sa solo morire allo stop o al
                    # target: nessun parziale del 25%, nessun break even,
                    # nessuna estensione del bersaglio.
                    tp1=decisione.tp1,
                    tf_crt=decisione.tf_crt,
                    spread_ingresso=decisione.spread,
                    rischio_corrente=decisione.rischio,
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
        # Quante posizioni gia' aperte sono state toccate da GEST-08, GEST-10
        # o SETUP-17 a questa chiusura di candela.
        "posizioni_gestite": gestite,
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


@app.get("/", response_class=HTMLResponse)
def pannello_principale() -> str:
    """Il pannello: cosa il bot vede, cosa decide e perche'.

    Il log dice la verita' ma non si guarda; `/salute` e' JSON. Questa e' la
    pagina che si tiene aperta per capire se la strategia viene interpretata
    come la si intendeva.
    """
    try:
        decisioni = storage.ultime_decisioni(30)
    except Exception:
        log.exception("pannello: impossibile leggere le decisioni")
        decisioni = []
    return pannello.pagina_principale(salute(), decisioni)


@app.get("/decisione/{id_decisione}", response_class=HTMLResponse)
def pannello_decisione(id_decisione: int) -> str:
    """Una decisione sola, con il grafico delle candele che il motore aveva."""
    decisione = storage.decisione_completa(id_decisione)
    if decisione is None:
        raise HTTPException(status_code=404, detail="decisione inesistente")
    try:
        candele = pannello.candele_della_decisione(decisione)
    except Exception:
        log.exception("pannello: impossibile ricostruire le candele")
        candele = []
    return pannello.pagina_decisione(decisione, candele)


# ===========================================================================
# Il trader discrezionale via Cowork
# ===========================================================================


@app.get("/cowork/in-attesa")
def cowork_in_attesa() -> dict[str, Any]:
    """I setup che aspettano il giudizio. E' cio' che una sessione Cowork legge.

    Ogni voce porta il dossier completo — gli stessi numeri che riceve il
    giudizio automatico — e quanti secondi mancano alla scadenza. Oltre quella
    il setup decade e non si esegue (SETUP-04, SETUP-16).
    """
    from core import cowork

    cowork.scadi_i_vecchi()
    attesa = cowork.in_attesa()
    return {
        "quanti": len(attesa),
        "scadenza_minuti": cowork.SCADENZA_MINUTI,
        "setup": [s.come_json() for s in attesa],
    }


@app.post("/cowork/verdetto/{id_decisione}")
def cowork_verdetto(id_decisione: int, corpo: dict[str, Any]) -> dict[str, Any]:
    """Cowork risponde: `{"accetta": true|false, "motivo": "..."}`.

    Il verdetto si registra sempre, anche su un setup scaduto: serve a
    misurare, fra sei mesi, se il giudizio abbia aggiunto valore. Ma un
    setup scaduto non si esegue.

    Come per il giudizio automatico, Cowork puo' **solo rifiutare** cio' che
    le regole hanno approvato. Non arriva mai qui un setup che le regole
    abbiano gia' fermato.
    """
    from core import cowork

    accetta = bool(corpo.get("accetta"))
    motivo = str(corpo.get("motivo", ""))[:500]
    if not motivo:
        return {"ok": False, "dettaglio": "serve un motivo: un verdetto senza "
                "ragione non si puo' misurare"}

    eseguibile, spiegazione = cowork.registra_verdetto(id_decisione, accetta, motivo)
    log.info("Cowork su %s: %s — %s", id_decisione,
             "ACCETTA" if accetta else "RIFIUTA", motivo)
    return {"ok": True, "eseguibile": eseguibile, "dettaglio": spiegazione}


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
    if cfg.FORNITORE_DATI == "dukascopy":
        fornitore["dukascopy"] = {
            "in_funzione": mercato_duka.in_funzione,
            "intervallo_sec": cfg.MERCATO_INTERVALLO_SEC,
            "giri": mercato_duka.giri,
            "candele_raccolte": mercato_duka.candele_nuove,
            "valutazioni": mercato_duka.valutazioni,
            # Quante richieste sono andate a Dukascopy, e a che ritmo. Il
            # volume era invisibile, ed e' cosi' che un ciclo da 26.000
            # richieste al giorno e' rimasto in piedi finche' la fonte non ha
            # chiuso la porta: i log dicevano cosa falliva, mai quanto si
            # chiedeva. Sopra le diecimila al giorno, aspettarsi dei 503.
            "richieste": mercato_duka.richieste,
            "richieste_al_giorno": mercato_duka.richieste_al_giorno,
            "ultimo_errore": mercato_duka.ultimo_errore,
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
    if cfg.FORNITORE_DATI == "mt5":
        fornitore["mt5"] = {
            "in_funzione": mercato_mt5.in_funzione,
            "intervallo_sec": cfg.MERCATO_INTERVALLO_SEC,
            "giri": mercato_mt5.giri,
            "candele_raccolte": mercato_mt5.candele_nuove,
            "valutazioni": mercato_mt5.valutazioni,
            "ultimo_errore": mercato_mt5.ultimo_errore,
        }
    if cfg.FORNITORE_DATI in ("tradingview", "mercato", "mt5"):
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
