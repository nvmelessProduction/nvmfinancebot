"""Server dell'impianto: riceve gli alert di TradingView e li fa girare.

Due soli endpoint:
    POST /webhook   riceve l'alert, lo archivia, chiede una decisione
    GET  /salute    dice in che stato siamo

La catena e' sempre la stessa: verifica del segreto -> salvataggio -> decisione
-> azione secondo la modalita'. La decisione oggi e' sempre "NONE" perche' la
strategia e' ancora uno stub: vedi core/strategy.py.
"""

import hmac
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException

from core import broker, notifier, storage
from core.config import impostazioni
from core.models import AlertIn, Decision, Esito
from core.strategy import valuta


@asynccontextmanager
async def ciclo_di_vita(app: FastAPI) -> AsyncIterator[None]:
    """Prepara l'archivio all'avvio e stacca il broker alla chiusura."""
    cfg = impostazioni()
    storage.inizializza()
    print(f"[AVVIO] modalita' = {cfg.MODE}, archivio = {cfg.DB_PATH}")

    if not cfg.webhook_configurato:
        print("[AVVIO] ATTENZIONE: WEBHOOK_SECRET non impostato, /webhook rifiutera' tutto.")
    if not cfg.telegram_configurato:
        print("[AVVIO] Telegram non configurato: le notifiche finiranno a console.")

    # In dry_run non tocchiamo il broker nemmeno per connetterci.
    if cfg.MODE != "dry_run":
        ok, messaggio = broker.connetti()
        print(f"[AVVIO] MT5: {'ok' if ok else 'KO'} - {messaggio}")
    else:
        print("[AVVIO] MT5 non contattato (modalita' dry_run).")

    yield

    broker.disconnetti()
    print("[ARRESTO] impianto fermato.")


app = FastAPI(
    title="nvmfinancebot - impianto",
    description="Infrastruttura del bot. La strategia non e' ancora implementata.",
    version="0.1.0",
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


def _esegui_decisione(
    alert: AlertIn,
    decisione: Decision,
    id_alert: int,
) -> tuple[Esito, str, int | None]:
    """Applica la decisione secondo la modalita' operativa.

    Restituisce (esito, dettaglio, ticket). Non decide nulla di suo: si limita
    a fare cio' che la decisione dice, o a fermarsi.
    """
    cfg = impostazioni()
    testo = notifier.messaggio_decisione(alert, decisione, cfg.MODE)

    # Nessuna azione richiesta: e' il caso normale finche' la strategia e' uno stub.
    if decisione.azione == "NONE":
        print(f"[NESSUNA AZIONE] {testo}")
        return "ignorato", "azione NONE: nessuna operazione", None

    if cfg.MODE == "dry_run":
        print(f"[SIMULAZIONE] {testo}")
        return "simulato", "dry_run: nessun ordine inviato al broker", None

    if cfg.MODE == "semi":
        inviato, dettaglio_telegram = notifier.invia(
            f"{testo}\n\nModalita' semi: serve la tua conferma manuale."
        )
        return (
            "in_attesa_conferma",
            f"semi: in attesa di conferma manuale ({dettaglio_telegram})"
            if not inviato
            else "semi: in attesa di conferma manuale (notifica inviata)",
            None,
        )

    # --- modalita' auto: si opera davvero ---------------------------------
    if decisione.azione == "CLOSE":
        # La chiusura mirata richiede un ticket, che la strategia dovra'
        # indicare quando esistera'. Per ora non abbiamo dove prenderlo.
        dettaglio = "auto: CLOSE non gestibile senza un ticket indicato dalla strategia"
        notifier.invia(f"{testo}\n\n{dettaglio}")
        return "errore", dettaglio, None

    if decisione.volume is None or decisione.volume <= 0:
        # Il volume lo decide la strategia, non l'impianto: senza, non si opera.
        dettaglio = "auto: volume non indicato dalla decisione, ordine non inviato"
        notifier.invia(f"{testo}\n\n{dettaglio}")
        return "errore", dettaglio, None

    esito_ordine = broker.invia_ordine(
        simbolo=alert.simbolo,
        direzione=decisione.azione,
        volume=decisione.volume,
        commento=f"alert {id_alert}",
    )
    notifier.invia(f"{testo}\n\nesecuzione: {esito_ordine.messaggio}")

    if not esito_ordine.ok:
        return "errore", f"auto: {esito_ordine.messaggio}", None

    return "eseguito", f"auto: {esito_ordine.messaggio}", esito_ordine.ticket


@app.post("/webhook")
def webhook(alert: AlertIn) -> dict[str, Any]:
    """Punto di ingresso degli alert TradingView."""
    # 1. Il segreto per primo: se non torna, non lasciamo traccia in archivio.
    if not _segreto_valido(alert.segreto):
        raise HTTPException(status_code=401, detail="segreto non valido")

    # 2. Archiviazione prima di tutto il resto.
    try:
        id_alert = storage.salva_alert(alert)
    except Exception as errore:
        print(f"[ARCHIVIO KO] impossibile salvare l'alert: {errore!r}")
        raise HTTPException(status_code=500, detail="archiviazione dell'alert fallita") from errore

    # 3. Decisione (oggi sempre NONE) e sua esecuzione secondo la modalita'.
    decisione = valuta(alert)
    try:
        esito, dettaglio, ticket = _esegui_decisione(alert, decisione, id_alert)
    except Exception as errore:
        # Qualunque imprevisto: la decisione va comunque registrata.
        esito, dettaglio, ticket = "errore", f"eccezione durante l'esecuzione: {errore!r}", None
        print(f"[ESECUZIONE KO] {dettaglio}")

    # 4. Registrazione della decisione con il suo esito.
    try:
        id_decisione: int | None = storage.salva_decisione(
            id_alert, decisione, esito, dettaglio, ticket
        )
    except Exception as errore:
        print(f"[ARCHIVIO KO] impossibile salvare la decisione: {errore!r}")
        id_decisione = None

    # 5. Se in auto abbiamo davvero aperto qualcosa, lo annotiamo: i livelli
    #    di stop e target vivranno qui, non sul broker.
    if esito == "eseguito" and id_decisione is not None:
        try:
            storage.registra_posizione(
                simbolo=alert.simbolo,
                direzione=decisione.azione,
                volume=float(decisione.volume or 0.0),
                ticket=ticket,
                decisione_id=id_decisione,
                sl=decisione.sl,
                tp=decisione.tp,
            )
        except Exception as errore:
            print(f"[ARCHIVIO KO] impossibile registrare la posizione: {errore!r}")

    return {
        "ricevuto": True,
        "alert_id": id_alert,
        "decisione_id": id_decisione,
        "azione": decisione.azione,
        "esito": esito,
        "dettaglio": dettaglio,
        "modalita": impostazioni().MODE,
    }


@app.get("/salute")
def salute() -> dict[str, Any]:
    """Stato dell'impianto: modalita', broker, equity, posizioni aperte."""
    cfg = impostazioni()
    stato_broker = broker.stato()
    conto = stato_broker.get("conto")

    try:
        conteggi = storage.conteggi()
        aperte_archivio: int | None = len(storage.posizioni_aperte())
        archivio_ok = True
    except Exception as errore:
        print(f"[ARCHIVIO KO] {errore!r}")
        conteggi = {}
        aperte_archivio = None
        archivio_ok = False

    return {
        "modalita": cfg.MODE,
        "mt5_disponibile": stato_broker["mt5_disponibile"],
        "mt5_connesso": stato_broker["connesso"],
        "mt5_dettaglio": stato_broker["dettaglio"],
        "equity": conto["equity"] if conto else None,
        "valuta": conto["valuta"] if conto else None,
        "posizioni_aperte_broker": stato_broker["posizioni_aperte"],
        "posizioni_aperte_archivio": aperte_archivio,
        "archivio_ok": archivio_ok,
        "conteggi": conteggi,
        "telegram_configurato": cfg.telegram_configurato,
        "webhook_configurato": cfg.webhook_configurato,
    }


if __name__ == "__main__":
    import uvicorn

    cfg = impostazioni()
    uvicorn.run("main:app", host=cfg.HOST, port=cfg.PORT, reload=False)
