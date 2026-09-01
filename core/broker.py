"""Adattatore MetaTrader 5: qui dentro sta tutto cio' che tocca il broker.

Due scelte importanti:

1. L'import di MetaTrader5 e' protetto da try/except. Il pacchetto esiste solo
   su Windows, quindi su qualunque altra macchina il progetto deve comunque
   avviarsi: in quel caso ogni funzione restituisce un errore pulito.
2. Gli ordini vengono inviati **senza** stop loss e take profit sul broker.
   I livelli restano in archivio e saranno sorvegliati dal server: e' una
   scelta di impianto, non una dimenticanza (vedi README).

Non c'e' nessuna regola di trading in questo file: volume, direzione e livelli
arrivano sempre dall'esterno.
"""

from typing import Any, Optional

from core.config import impostazioni
from core.models import OrderResult

try:  # pragma: no cover - dipende dalla macchina
    import MetaTrader5 as mt5  # type: ignore[import-not-found]

    MT5_DISPONIBILE: bool = True
    MOTIVO_INDISPONIBILE: str = ""
except ImportError as errore:  # su Linux/macOS, o se il pacchetto manca
    mt5 = None  # type: ignore[assignment]
    MT5_DISPONIBILE = False
    MOTIVO_INDISPONIBILE = (
        f"pacchetto MetaTrader5 non importabile ({errore}). "
        "Funziona solo su Windows con il terminale MT5 installato."
    )

# Stato della connessione al terminale, per non richiamare initialize ogni volta.
_connesso: bool = False


def disponibile() -> bool:
    """True se il pacchetto MetaTrader5 e' importabile su questa macchina."""
    return MT5_DISPONIBILE


def _errore_mt5() -> tuple[int, str]:
    """Ultimo errore del terminale, in forma (codice, descrizione)."""
    if mt5 is None:
        return -1, MOTIVO_INDISPONIBILE
    codice, descrizione = mt5.last_error()
    return int(codice), str(descrizione)


def connetti() -> tuple[bool, str]:
    """Avvia la connessione al terminale MT5.

    Se MT5_LOGIN e' 0 si assume che il terminale sia gia' loggato a mano sul
    conto FP Markets: initialize() si aggancia alla sessione esistente.
    """
    global _connesso
    if not MT5_DISPONIBILE or mt5 is None:
        return False, MOTIVO_INDISPONIBILE

    cfg = impostazioni()
    parametri: dict[str, Any] = {}
    if cfg.MT5_PATH.strip():
        parametri["path"] = cfg.MT5_PATH.strip()
    if cfg.MT5_LOGIN:
        parametri["login"] = cfg.MT5_LOGIN
        parametri["password"] = cfg.MT5_PASSWORD
        parametri["server"] = cfg.MT5_SERVER

    try:
        avviato = mt5.initialize(**parametri)
    except Exception as errore:  # il modulo nativo puo' sollevare di tutto
        _connesso = False
        return False, f"initialize() ha sollevato: {errore!r}"

    if not avviato:
        _connesso = False
        codice, descrizione = _errore_mt5()
        return False, f"initialize() fallita: [{codice}] {descrizione}"

    _connesso = True
    return True, "terminale MT5 connesso"


def disconnetti() -> None:
    """Chiude la connessione al terminale, se era aperta."""
    global _connesso
    if MT5_DISPONIBILE and mt5 is not None and _connesso:
        mt5.shutdown()
    _connesso = False


def _assicura_connessione() -> tuple[bool, str]:
    """Connette al terminale solo se non lo siamo gia'."""
    if _connesso:
        return True, "gia' connesso"
    return connetti()


def info_conto() -> tuple[bool, Optional[dict[str, Any]], str]:
    """Legge i dati del conto: valuta, saldo, equity, margine libero."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, None, messaggio

    conto = mt5.account_info()
    if conto is None:
        codice, descrizione = _errore_mt5()
        return False, None, f"account_info() vuota: [{codice}] {descrizione}"

    return (
        True,
        {
            "login": conto.login,
            "server": conto.server,
            "valuta": conto.currency,
            "saldo": conto.balance,
            "equity": conto.equity,
            "margine_libero": conto.margin_free,
            "leva": conto.leverage,
        },
        "dati conto letti",
    )


def posizioni_broker(simbolo: Optional[str] = None) -> tuple[bool, list[dict[str, Any]], str]:
    """Elenca le posizioni realmente aperte sul conto MT5."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, [], messaggio

    posizioni = mt5.positions_get(symbol=simbolo) if simbolo else mt5.positions_get()
    if posizioni is None:
        codice, descrizione = _errore_mt5()
        # positions_get() restituisce None anche su errore vero: lo segnaliamo.
        return False, [], f"positions_get() fallita: [{codice}] {descrizione}"

    elenco = [
        {
            "ticket": p.ticket,
            "simbolo": p.symbol,
            "direzione": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": p.volume,
            "prezzo_apertura": p.price_open,
            "prezzo_corrente": p.price_current,
            "profitto": p.profit,
            "magic": p.magic,
        }
        for p in posizioni
    ]
    return True, elenco, f"{len(elenco)} posizioni aperte"


def prezzo_corrente(simbolo: str) -> tuple[bool, Optional[dict[str, float]], str]:
    """Legge bid e ask correnti di un simbolo."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, None, messaggio

    if not mt5.symbol_select(simbolo, True):
        codice, descrizione = _errore_mt5()
        return False, None, f"simbolo {simbolo} non selezionabile: [{codice}] {descrizione}"

    tick = mt5.symbol_info_tick(simbolo)
    if tick is None:
        codice, descrizione = _errore_mt5()
        return False, None, f"nessun tick per {simbolo}: [{codice}] {descrizione}"

    return True, {"bid": tick.bid, "ask": tick.ask}, "tick letto"


def _modalita_riempimento(simbolo: str) -> int:
    """Sceglie il filling mode accettato dal simbolo (FOK, IOC o Return).

    E' plumbing del broker, non una scelta di strategia: server diversi
    accettano modalita' diverse e un ordine con quella sbagliata viene
    rifiutato con "Unsupported filling mode".
    """
    if mt5 is None:
        return 0
    info = mt5.symbol_info(simbolo)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    maschera = int(getattr(info, "filling_mode", 0))
    if maschera & 1:  # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    if maschera & 2:  # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def invia_ordine(
    simbolo: str,
    direzione: str,
    volume: float,
    commento: str = "",
    deviazione: int = 20,
) -> OrderResult:
    """Invia un ordine a mercato.

    `direzione` deve essere "BUY" o "SELL"; `volume` arriva da chi chiama,
    qui non viene calcolato nulla. Stop e target non vengono passati al
    broker di proposito (li sorveglia il server).
    """
    direzione = direzione.upper()
    if direzione not in ("BUY", "SELL"):
        return OrderResult(ok=False, messaggio=f"direzione non valida: {direzione}")
    if volume <= 0:
        return OrderResult(ok=False, messaggio=f"volume non valido: {volume}")

    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return OrderResult(ok=False, messaggio=messaggio)

    ok_prezzo, tick, messaggio_prezzo = prezzo_corrente(simbolo)
    if not ok_prezzo or tick is None:
        return OrderResult(ok=False, messaggio=messaggio_prezzo)

    tipo = mt5.ORDER_TYPE_BUY if direzione == "BUY" else mt5.ORDER_TYPE_SELL
    prezzo = tick["ask"] if direzione == "BUY" else tick["bid"]

    richiesta: dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": simbolo,
        "volume": float(volume),
        "type": tipo,
        "price": prezzo,
        "deviation": deviazione,
        "magic": impostazioni().MT5_MAGIC,
        "comment": commento[:31],  # MT5 tronca i commenti lunghi
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _modalita_riempimento(simbolo),
    }

    try:
        risultato = mt5.order_send(richiesta)
    except Exception as errore:
        return OrderResult(ok=False, messaggio=f"order_send() ha sollevato: {errore!r}")

    if risultato is None:
        codice, descrizione = _errore_mt5()
        return OrderResult(
            ok=False,
            messaggio=f"order_send() senza risposta: [{codice}] {descrizione}",
            codice_errore=codice,
        )

    if risultato.retcode != mt5.TRADE_RETCODE_DONE:
        return OrderResult(
            ok=False,
            messaggio=f"ordine rifiutato: retcode {risultato.retcode} ({risultato.comment})",
            codice_errore=int(risultato.retcode),
        )

    return OrderResult(
        ok=True,
        messaggio=f"{direzione} {volume} {simbolo} eseguito",
        ticket=int(risultato.order),
        prezzo=float(risultato.price),
    )


def chiudi_posizione(ticket: int, deviazione: int = 20) -> OrderResult:
    """Chiude a mercato la posizione con il ticket indicato."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return OrderResult(ok=False, messaggio=messaggio)

    posizioni = mt5.positions_get(ticket=ticket)
    if not posizioni:
        codice, descrizione = _errore_mt5()
        return OrderResult(
            ok=False,
            messaggio=f"posizione {ticket} non trovata: [{codice}] {descrizione}",
            codice_errore=codice,
        )

    posizione = posizioni[0]
    ok_prezzo, tick, messaggio_prezzo = prezzo_corrente(posizione.symbol)
    if not ok_prezzo or tick is None:
        return OrderResult(ok=False, messaggio=messaggio_prezzo)

    # Per chiudere si manda l'ordine opposto sullo stesso ticket.
    in_acquisto = posizione.type == mt5.POSITION_TYPE_BUY
    tipo = mt5.ORDER_TYPE_SELL if in_acquisto else mt5.ORDER_TYPE_BUY
    prezzo = tick["bid"] if in_acquisto else tick["ask"]

    richiesta: dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": posizione.symbol,
        "volume": posizione.volume,
        "type": tipo,
        "position": posizione.ticket,
        "price": prezzo,
        "deviation": deviazione,
        "magic": impostazioni().MT5_MAGIC,
        "comment": "chiusura bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _modalita_riempimento(posizione.symbol),
    }

    try:
        risultato = mt5.order_send(richiesta)
    except Exception as errore:
        return OrderResult(ok=False, messaggio=f"order_send() ha sollevato: {errore!r}")

    if risultato is None:
        codice, descrizione = _errore_mt5()
        return OrderResult(
            ok=False,
            messaggio=f"order_send() senza risposta: [{codice}] {descrizione}",
            codice_errore=codice,
        )

    if risultato.retcode != mt5.TRADE_RETCODE_DONE:
        return OrderResult(
            ok=False,
            messaggio=f"chiusura rifiutata: retcode {risultato.retcode} ({risultato.comment})",
            codice_errore=int(risultato.retcode),
        )

    return OrderResult(
        ok=True,
        messaggio=f"posizione {ticket} chiusa",
        ticket=int(ticket),
        prezzo=float(risultato.price),
    )


def stato() -> dict[str, Any]:
    """Riassunto dello stato del broker, usato da /salute e dal collaudo."""
    if not MT5_DISPONIBILE:
        return {
            "mt5_disponibile": False,
            "connesso": False,
            "dettaglio": MOTIVO_INDISPONIBILE,
            "conto": None,
            "posizioni_aperte": None,
        }

    ok_conto, conto, messaggio_conto = info_conto()
    ok_posizioni, posizioni, _ = posizioni_broker()
    return {
        "mt5_disponibile": True,
        "connesso": _connesso,
        "dettaglio": messaggio_conto,
        "conto": conto if ok_conto else None,
        "posizioni_aperte": len(posizioni) if ok_posizioni else None,
    }
