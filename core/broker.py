"""Adattatore MetaTrader 5: qui dentro sta tutto cio' che tocca il broker.

Scelte di impianto:

1. L'import di MetaTrader5 e' protetto da try/except. Il pacchetto esiste solo
   su Windows, quindi su qualunque altra macchina il progetto deve comunque
   avviarsi: in quel caso ogni funzione restituisce un errore pulito.
2. Gli ordini vengono inviati **senza** stop loss e take profit sul broker.
   I livelli restano in archivio e li sorveglia core/sentinella.py: e' una
   scelta di impianto, non una dimenticanza (vedi README).
3. Ogni chiamata al terminale passa da un lucchetto. La libreria MT5 e' un
   modulo nativo con stato globale: webhook e sentinella la userebbero da
   thread diversi, e in quel caso le risposte si mescolano.
4. La connessione viene verificata, non data per buona: un terminale chiuso
   a meta' giornata deve produrre una riconnessione, non ordini nel vuoto.

Non c'e' nessuna regola di trading in questo file: volume, direzione e livelli
arrivano sempre dall'esterno.
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import impostazioni
from core.gestione import chiusura_ha_soglia_di_tolleranza
from core.simboli import cfd_da_simbolo_esecuzione
from core.log import diario
from core.models import OrderResult

log = diario("broker")

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

# Il modulo MetaTrader5 ha stato globale: una sola chiamata per volta.
# RLock e non Lock perche' invia_ordine() richiama prezzo_corrente().
_lucchetto = threading.RLock()

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

    with _lucchetto:
        try:
            avviato = mt5.initialize(**parametri)
        except Exception as errore:  # il modulo nativo puo' sollevare di tutto
            _connesso = False
            log.error("initialize() ha sollevato: %r", errore)
            return False, f"initialize() ha sollevato: {errore!r}"

        if not avviato:
            _connesso = False
            codice, descrizione = _errore_mt5()
            log.error("initialize() fallita: [%s] %s", codice, descrizione)
            return False, f"initialize() fallita: [{codice}] {descrizione}"

        _connesso = True
        # Il trading da programma puo' essere disattivato lato terminale o
        # lato conto: meglio scoprirlo adesso che al primo ordine.
        terminale = mt5.terminal_info()
        if terminale is not None and not terminale.trade_allowed:
            log.warning(
                "il terminale MT5 e' connesso ma NON abilitato al trading da "
                "programma: attiva il pulsante 'Algo Trading'"
            )
        log.info("terminale MT5 connesso")
        return True, "terminale MT5 connesso"


def disconnetti() -> None:
    """Chiude la connessione al terminale, se era aperta."""
    global _connesso
    with _lucchetto:
        if MT5_DISPONIBILE and mt5 is not None and _connesso:
            mt5.shutdown()
            log.info("terminale MT5 disconnesso")
        _connesso = False


def _assicura_connessione() -> tuple[bool, str]:
    """Connette al terminale, e verifica che la connessione sia ancora viva.

    Non basta ricordarsi di aver chiamato initialize(): se l'utente chiude MT5
    a meta' giornata il nostro `_connesso` resterebbe True per sempre. Chiediamo
    al terminale se c'e'.
    """
    global _connesso
    if not MT5_DISPONIBILE or mt5 is None:
        return False, MOTIVO_INDISPONIBILE

    with _lucchetto:
        if _connesso and mt5.terminal_info() is not None:
            return True, "gia' connesso"
        if _connesso:
            log.warning("il terminale MT5 non risponde piu': riconnessione")
            _connesso = False
        return connetti()


def trading_permesso() -> tuple[bool, str]:
    """Dice se il terminale accetta ordini da programma.

    Il pulsante "Algo Trading" spento e' il motivo numero uno per cui un
    ordine viene rifiutato senza spiegazioni.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, messaggio
    with _lucchetto:
        terminale = mt5.terminal_info()
        if terminale is None:
            return False, "terminal_info() vuota"
        if not terminale.trade_allowed:
            return False, "trading da programma disattivato: attiva 'Algo Trading' su MT5"
        conto = mt5.account_info()
        if conto is not None and not conto.trade_allowed:
            return False, "il conto non permette di operare (controlla col broker)"
    return True, "trading permesso"


def info_conto() -> tuple[bool, Optional[dict[str, Any]], str]:
    """Legge i dati del conto: valuta, saldo, equity, margine libero."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, None, messaggio

    with _lucchetto:
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
                "trading_permesso": bool(conto.trade_allowed),
            },
            "dati conto letti",
        )


def posizioni_broker(simbolo: Optional[str] = None) -> tuple[bool, list[dict[str, Any]], str]:
    """Elenca le posizioni realmente aperte sul conto MT5."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, [], messaggio

    with _lucchetto:
        posizioni = mt5.positions_get(symbol=simbolo) if simbolo else mt5.positions_get()
        if posizioni is None:
            codice, descrizione = _errore_mt5()
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


# Quanti tentativi fare prima di dire che una quotazione non c'e', e quanto
# aspettare fra uno e l'altro. Un simbolo appena selezionato ci mette qualche
# decimo di secondo a ricevere il primo prezzo dal server.
_TENTATIVI_TICK = 6
_ATTESA_TICK = 0.25


def prezzo_corrente(simbolo: str) -> tuple[bool, Optional[dict[str, float]], str]:
    """Legge bid e ask correnti di un simbolo."""
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, None, messaggio

    with _lucchetto:
        if not mt5.symbol_select(simbolo, True):
            codice, descrizione = _errore_mt5()
            return False, None, f"simbolo {simbolo} non selezionabile: [{codice}] {descrizione}"

        # Un simbolo appena aggiunto all'Osservazione del mercato non ha
        # ancora una quotazione: il terminale deve prima riceverla dal server.
        # Il primo `symbol_info_tick` torna quindi con bid e ask a zero, che
        # somiglia a "mercato chiuso" ma e' solo "non ancora arrivata".
        # Succede su tutti i simboli che non stavano gia' in Osservazione, e
        # sono la maggioranza al primo avvio.
        tick = None
        for tentativo in range(_TENTATIVI_TICK):
            tick = mt5.symbol_info_tick(simbolo)
            if tick is not None and tick.bid and tick.ask:
                break
            if tentativo < _TENTATIVI_TICK - 1:
                time.sleep(_ATTESA_TICK)

        if tick is None:
            codice, descrizione = _errore_mt5()
            return False, None, f"nessun tick per {simbolo}: [{codice}] {descrizione}"

        if not tick.bid or not tick.ask:
            return False, None, (
                f"{simbolo}: nessuna quotazione dopo {_TENTATIVI_TICK} tentativi. "
                f"Mercato chiuso, oppure il simbolo non e' quotato su questo conto"
            )

        return True, {"bid": float(tick.bid), "ask": float(tick.ask)}, "tick letto"


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


def _volume_accettabile(simbolo: str, volume: float) -> tuple[bool, float, str]:
    """Controlla il volume contro i limiti del simbolo.

    Non calcola nulla: prende il volume che gli viene dato e dice se il broker
    lo accetterebbe. L'arrotondamento e' solo pulizia dei decimali (0.30000004
    diventa 0.3), non un aggiustamento della size.
    """
    if mt5 is None:
        return False, volume, MOTIVO_INDISPONIBILE

    info = mt5.symbol_info(simbolo)
    if info is None:
        codice, descrizione = _errore_mt5()
        return False, volume, f"symbol_info({simbolo}) vuota: [{codice}] {descrizione}"

    passo = float(getattr(info, "volume_step", 0.01)) or 0.01
    minimo = float(getattr(info, "volume_min", 0.0))
    massimo = float(getattr(info, "volume_max", 0.0))

    # Numero di decimali del passo, per togliere il rumore in virgola mobile.
    decimali = max(0, len(f"{passo:.8f}".rstrip("0").split(".")[-1]))
    pulito = round(round(volume / passo) * passo, decimali)

    if minimo and pulito < minimo:
        return False, pulito, f"volume {volume} sotto il minimo del simbolo ({minimo})"
    if massimo and pulito > massimo:
        return False, pulito, f"volume {volume} sopra il massimo del simbolo ({massimo})"
    if pulito <= 0:
        return False, pulito, f"volume {volume} non rappresentabile col passo {passo}"

    return True, pulito, "volume accettabile"


def _cifre_simbolo(simbolo: str, difetto: int = 5) -> int:
    """Quanti decimali accetta il broker su questo simbolo.

    Chi chiama e' gia' dentro `_lucchetto` e gia' connesso: qui si legge e
    basta. Il ripiego a cinque cifre non e' una scelta di comodo -- e' il
    valore piu' fine fra i sei strumenti, quindi arrotondare li' non rende
    mai un livello piu' grossolano di quanto il broker accetti.
    """
    if mt5 is None:
        return difetto
    info = mt5.symbol_info(simbolo)
    if info is None:
        return difetto
    return int(getattr(info, "digits", difetto) or difetto)


def _livello_troppo_vicino(
    simbolo: str, prezzo: float, richiesta: dict[str, Any]
) -> Optional[str]:
    """Stop o target sotto la distanza minima che il broker accetta?

    MT5 rifiuta con `retcode 10016 (Invalid stops)` sia quando un livello sta
    dalla parte sbagliata, sia quando sta troppo VICINO al prezzo: ogni
    simbolo ha un `trade_stops_level` in punti, e sotto quella soglia il
    livello non e' piazzabile. Il motore non puo' saperlo -- ragiona su
    livelli di struttura, non sulle condizioni di questo broker.

    Restituisce il motivo del rifiuto, oppure None se va tutto bene. Con
    specifiche illeggibili restituisce None: non e' questo il posto dove
    fermare un'operazione che tutte le regole hanno approvato, e il broker
    resta comunque l'ultima rete.
    """
    ok, spec, _ = specifiche_simbolo(simbolo)
    if not ok or not spec:
        return None
    punto = float(spec.get("punto") or 0.0)
    livelli_punti = int(spec.get("stops_level_punti") or 0)
    if punto <= 0 or livelli_punti <= 0:
        return None
    minima = livelli_punti * punto

    for campo, nome in (("sl", "stop"), ("tp", "target")):
        livello = richiesta.get(campo)
        if livello is None:
            continue
        distanza = abs(float(livello) - prezzo)
        if distanza < minima:
            return (
                f"{nome} {livello} a {distanza:.5f} dal prezzo {prezzo:.5f}: "
                f"{simbolo} ne vuole almeno {minima:.5f} "
                f"({livelli_punti} punti). L'ordine non parte: spostare il "
                f"livello vorrebbe dire aprire un'altra operazione"
            )
    return None


def invia_ordine(
    simbolo: str,
    direzione: str,
    volume: float,
    commento: str = "",
    deviazione: Optional[int] = None,
    stop: Optional[float] = None,
    target: Optional[float] = None,
) -> OrderResult:
    """Invia un ordine a mercato, con stop e target attaccati.

    `direzione` deve essere "BUY" o "SELL"; `volume` arriva da chi chiama,
    qui non viene calcolato nulla.

    ## Perche' `stop` e `target` vanno al broker

    Fino al 2026-09-22 l'ordine partiva nudo e i livelli vivevano solo in
    archivio, sorvegliati dalla sentinella. Funziona finche' il bot e' vivo,
    e infatti funzionava: 281 stop e 102 target eseguiti. Ma se il processo
    muore -- finestra chiusa, connessione caduta, corrente -- la posizione
    resta aperta **senza nessuno stop**, e su MT5 le colonne S/L e T/P erano
    vuote, quindi non si vedeva nemmeno.

    Adesso sono due reti e non una. Quella del broker scatta sul tick; la
    sentinella resta perche' GEST-04 -- parziale al 25% e resto a break even
    -- e' una sequenza condizionata che uno stop statico non sa esprimere.
    Chi arriva primo chiude, e la sentinella riconcilia gia' le posizioni
    sparite senza che sia stata lei a chiuderle.

    I livelli vengono arrotondati alla cifra del simbolo: MT5 rifiuta con
    `10016` uno stop non allineato al tick, e un ordine rifiutato per un
    decimale di troppo sarebbe un'operazione persa per niente.
    """
    # Una prova non manda ordini veri al broker.
    #
    # Il freno non e' teorico: chiamando questa funzione da uno script di
    # collaudo il 2026-09-21 l'ordine e' **partito**, e si e' fermato solo
    # perche' avevo passato `EURUSD` invece di `EURUSD+` e il broker ha
    # risposto "Trade disabled". Col nome giusto sarebbe stata una posizione
    # aperta sul conto. Era fortuna, non una porta chiusa -- e le altre due
    # porte che danno sul mondo, Telegram e l'API di Claude, si erano gia'
    # aperte cosi'.
    #
    # Chi vuole davvero provare il percorso dei soldi usa
    # `prova_esecuzione.py --ordine`, che non gira dentro una suite.
    from core.ambiente import broker_finto, in_prova

    if in_prova() and not broker_finto():
        log.warning("ordine NON inviato: siamo in una prova (%s %s %s)",
                    simbolo, direzione, volume)
        return OrderResult(
            ok=False, messaggio="siamo in una prova: nessun ordine e' partito")

    direzione = direzione.upper()
    if direzione not in ("BUY", "SELL"):
        return OrderResult(ok=False, messaggio=f"direzione non valida: {direzione}")
    if volume <= 0:
        return OrderResult(ok=False, messaggio=f"volume non valido: {volume}")

    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return OrderResult(ok=False, messaggio=messaggio)

    with _lucchetto:
        permesso, messaggio_permesso = trading_permesso()
        if not permesso:
            return OrderResult(ok=False, messaggio=messaggio_permesso)

        ok_prezzo, tick, messaggio_prezzo = prezzo_corrente(simbolo)
        if not ok_prezzo or tick is None:
            return OrderResult(ok=False, messaggio=messaggio_prezzo)

        ok_volume, volume_pulito, messaggio_volume = _volume_accettabile(simbolo, volume)
        if not ok_volume:
            return OrderResult(ok=False, messaggio=messaggio_volume)

        tipo = mt5.ORDER_TYPE_BUY if direzione == "BUY" else mt5.ORDER_TYPE_SELL
        prezzo = tick["ask"] if direzione == "BUY" else tick["bid"]

        richiesta: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": simbolo,
            "volume": volume_pulito,
            "type": tipo,
            "price": prezzo,
            "deviation": deviazione if deviazione is not None else impostazioni().MT5_DEVIAZIONE,
            "magic": impostazioni().MT5_MAGIC,
            "comment": commento[:31],  # MT5 tronca i commenti lunghi
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": _modalita_riempimento(simbolo),
        }

        # Lo stop e il target, arrotondati al tick del simbolo. Un livello a
        # zero per MT5 vuol dire "nessun livello", che e' esattamente cio' che
        # serve quando chi chiama non ne ha uno -- per esempio un TP1 tolto
        # perche' stava alle spalle del prezzo.
        cifre = _cifre_simbolo(simbolo)
        if stop is not None:
            richiesta["sl"] = round(float(stop), cifre)
        if target is not None:
            richiesta["tp"] = round(float(target), cifre)

        # E i livelli devono stare abbastanza LONTANI dal prezzo, o MT5
        # rifiuta con `retcode 10016 (Invalid stops)`. E' la seconda causa di
        # quel rifiuto, dopo lo stop dalla parte sbagliata, e si evita da qui:
        # il motore ragiona su livelli di struttura e non conosce la distanza
        # minima che questo broker impone su questo simbolo.
        #
        # Non si sposta il livello per farcelo entrare -- sarebbe uno stop
        # diverso da quello del setup, cioe' un'altra operazione. Si rifiuta
        # l'ordine e si dice perche'.
        troppo_vicino = _livello_troppo_vicino(simbolo, prezzo, richiesta)
        if troppo_vicino is not None:
            log.warning("ordine NON inviato: %s", troppo_vicino)
            return OrderResult(ok=False, messaggio=troppo_vicino)

        log.info("invio ordine %s %s %s (sl %s tp %s)", direzione,
                 volume_pulito, simbolo,
                 richiesta.get("sl", "-"), richiesta.get("tp", "-"))
        try:
            risultato = mt5.order_send(richiesta)
        except Exception as errore:
            log.exception("order_send() ha sollevato")
            return OrderResult(ok=False, messaggio=f"order_send() ha sollevato: {errore!r}")

    if risultato is None:
        codice, descrizione = _errore_mt5()
        log.error("order_send() senza risposta: [%s] %s", codice, descrizione)
        return OrderResult(
            ok=False,
            messaggio=f"order_send() senza risposta: [{codice}] {descrizione}",
            codice_errore=codice,
        )

    if risultato.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("ordine rifiutato: retcode %s (%s)", risultato.retcode, risultato.comment)
        return OrderResult(
            ok=False,
            messaggio=f"ordine rifiutato: retcode {risultato.retcode} ({risultato.comment})",
            codice_errore=int(risultato.retcode),
        )

    log.info("ordine eseguito: ticket %s a %s", risultato.order, risultato.price)
    return OrderResult(
        ok=True,
        messaggio=f"{direzione} {volume_pulito} {simbolo} eseguito a {risultato.price}",
        ticket=int(risultato.order),
        prezzo=float(risultato.price),
    )


# GEST-11 — "Non esiste una deviazione massima oltre la quale rinunciare alla
# chiusura". `MT5_DEVIAZIONE` e' la tolleranza di slippage con cui si **apre**:
# li' rinunciare e' legittimo, perche' un ingresso a un prezzo peggiore e' un
# ingresso che non conviene piu'. In chiusura no. Una chiusura rifiutata per
# slippage lascia aperta una posizione il cui stop e' gia' stato superato, ed
# e' il caso peggiore possibile: la perdita continua a correre e nessuno la
# ferma. Questo valore e' abbastanza grande da non rifiutare mai in pratica.
DEVIAZIONE_CHIUSURA: int = 1_000_000


def modifica_livelli(
    ticket: int,
    stop: Optional[float] = None,
    target: Optional[float] = None,
) -> OrderResult:
    """Sposta stop e target di una posizione GIA' APERTA, sul broker.

    ## Perche' serve

    Da quando l'ordine parte con `sl` e `tp` attaccati ci sono due reti: il
    broker e la sentinella. Il guaio e' che i livelli cambiano dopo
    l'apertura -- `GEST-04` porta lo stop a pareggio dopo il parziale,
    `SETUP-17` lo porta a pareggio quando la bias si inverte, `GEST-08`
    allunga il target -- e fino al 2026-09-22 quei movimenti finivano solo
    in archivio.

    Due reti che dicono cose diverse sono peggio di una sola: quella del
    broker e' proprio quella che sopravvive alla morte del bot, ed e' quella
    che sarebbe rimasta allo stop vecchio. Misurato sul log: 58 parziali e 91
    spostamenti di `SETUP-17` in cui il broker non e' mai stato aggiornato.

    Un livello a `None` resta com'e'; per toglierlo si passa `0.0`, che e'
    come MT5 scrive "nessun livello".
    """
    from core.ambiente import broker_finto, in_prova

    if in_prova() and not broker_finto():
        log.warning("livelli NON modificati: siamo in una prova (%s)", ticket)
        return OrderResult(
            ok=False, messaggio="siamo in una prova: nessuna modifica e' partita")

    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return OrderResult(ok=False, messaggio=messaggio)

    if stop is None and target is None:
        return OrderResult(ok=True, messaggio="niente da modificare")

    with _lucchetto:
        posizioni = mt5.positions_get(ticket=ticket)
        if not posizioni:
            codice, descrizione = _errore_mt5()
            return OrderResult(
                ok=False,
                messaggio=f"posizione {ticket} non trovata sul broker: "
                          f"[{codice}] {descrizione}",
                codice_errore=codice,
            )
        posizione = posizioni[0]
        cifre = _cifre_simbolo(posizione.symbol)

        richiesta: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": posizione.symbol,
            "position": posizione.ticket,
            # Cio' che non si passa resta quello che c'e' gia': MT5 riscrive
            # entrambi i campi ad ogni SLTP, quindi ometterne uno lo azzera.
            "sl": round(float(stop), cifre) if stop is not None else posizione.sl,
            "tp": round(float(target), cifre) if target is not None else posizione.tp,
        }

        log.info("modifica livelli su %s: sl %s tp %s",
                 ticket, richiesta["sl"], richiesta["tp"])
        try:
            risultato = mt5.order_send(richiesta)
        except Exception as errore:
            log.exception("order_send() ha sollevato modificando i livelli")
            return OrderResult(
                ok=False, messaggio=f"order_send() ha sollevato: {errore!r}")

    if risultato is None:
        codice, descrizione = _errore_mt5()
        return OrderResult(
            ok=False,
            messaggio=f"order_send() senza risposta: [{codice}] {descrizione}",
            codice_errore=codice,
        )
    if risultato.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("modifica dei livelli rifiutata su %s: retcode %s (%s)",
                  ticket, risultato.retcode, risultato.comment)
        return OrderResult(
            ok=False,
            messaggio=f"modifica rifiutata: retcode {risultato.retcode} "
                      f"({risultato.comment})",
            codice_errore=risultato.retcode,
        )
    return OrderResult(ok=True, messaggio="livelli aggiornati sul broker")


def chiudi_posizione(
    ticket: int,
    deviazione: Optional[int] = None,
    volume: Optional[float] = None,
) -> OrderResult:
    """Chiude a mercato la posizione con il ticket indicato.

    `volume` chiude solo una parte: serve al parziale del 25% di GEST-04, che
    il broker non sa fare da solo. MT5 esegue una chiusura parziale mandando
    l'ordine opposto con un volume inferiore a quello della posizione; il
    ticket resta lo stesso e il volume residuo si aggiorna. Con `volume`
    assente o pari al volume aperto si chiude tutto, come prima.

    Il volume richiesto viene limitato a quello realmente aperto: chiedere di
    piu' farebbe rifiutare l'ordine intero, e una chiusura rifiutata e' il
    caso che GEST-11 vieta.
    """
    # Come per l'invio: una prova non tocca il conto. Vedi `invia_ordine`.
    from core.ambiente import broker_finto, in_prova

    if in_prova() and not broker_finto():
        log.warning("chiusura NON inviata: siamo in una prova (ticket %s)", ticket)
        return OrderResult(
            ok=False, messaggio="siamo in una prova: nessuna chiusura e' partita")

    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return OrderResult(ok=False, messaggio=messaggio)

    with _lucchetto:
        posizioni = mt5.positions_get(ticket=ticket)
        if not posizioni:
            codice, descrizione = _errore_mt5()
            return OrderResult(
                ok=False,
                messaggio=f"posizione {ticket} non trovata sul broker: [{codice}] {descrizione}",
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

        da_chiudere = posizione.volume
        if volume is not None:
            da_chiudere = min(float(volume), posizione.volume)
            if da_chiudere <= 0:
                return OrderResult(
                    ok=False,
                    messaggio=f"volume di chiusura non valido: {volume}",
                )

        parziale = da_chiudere < posizione.volume
        richiesta: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": posizione.symbol,
            "volume": da_chiudere,
            "type": tipo,
            "position": posizione.ticket,
            "price": prezzo,
            # GEST-11: `chiusura_ha_soglia_di_tolleranza()` e' False, e da li'
            # discende il valore. Chiamarla invece di darlo per scontato fa
            # fallire rumorosamente il giorno in cui la regola cambiasse.
            "deviation": (
                deviazione if deviazione is not None
                else (impostazioni().MT5_DEVIAZIONE
                      if chiusura_ha_soglia_di_tolleranza()
                      else DEVIAZIONE_CHIUSURA)
            ),
            "magic": impostazioni().MT5_MAGIC,
            "comment": "parziale bot" if parziale else "chiusura bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": _modalita_riempimento(posizione.symbol),
        }

        log.info("chiusura posizione %s, volume %s", ticket, da_chiudere)
        try:
            risultato = mt5.order_send(richiesta)
        except Exception as errore:
            log.exception("order_send() ha sollevato in chiusura")
            return OrderResult(ok=False, messaggio=f"order_send() ha sollevato: {errore!r}")

    if risultato is None:
        codice, descrizione = _errore_mt5()
        return OrderResult(
            ok=False,
            messaggio=f"order_send() senza risposta: [{codice}] {descrizione}",
            codice_errore=codice,
        )

    if risultato.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("chiusura rifiutata: retcode %s (%s)", risultato.retcode, risultato.comment)
        return OrderResult(
            ok=False,
            messaggio=f"chiusura rifiutata: retcode {risultato.retcode} ({risultato.comment})",
            codice_errore=int(risultato.retcode),
        )

    log.info("posizione %s chiusa a %s", ticket, risultato.price)
    return OrderResult(
        ok=True,
        messaggio=f"posizione {ticket} chiusa a {risultato.price}",
        ticket=int(ticket),
        prezzo=float(risultato.price),
    )


def specifiche_simbolo(simbolo: str) -> tuple[bool, Optional[dict[str, Any]], str]:
    """Le specifiche di contratto di uno strumento, lette dal broker.

    Servono a due cose: dimensionare correttamente (RISK-03 vuole
    `valore_punto`, che e' `trade_tick_value / trade_tick_size`) e chiudere
    PA-62 con numeri misurati invece che stimati.

    Va letta una volta per ciascuno dei sei strumenti, sul conto su cui si
    opera: i valori dipendono dal broker e dalla valuta del conto, non sono
    proprieta' universali dello strumento.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, None, messaggio

    with _lucchetto:
        if not mt5.symbol_select(simbolo, True):
            codice, descrizione = _errore_mt5()
            return False, None, f"simbolo {simbolo} non selezionabile: [{codice}] {descrizione}"
        info = mt5.symbol_info(simbolo)
        if info is None:
            codice, descrizione = _errore_mt5()
            return False, None, f"symbol_info({simbolo}) vuota: [{codice}] {descrizione}"

        passo_tick = float(getattr(info, "trade_tick_size", 0.0) or 0.0)
        valore_tick = float(getattr(info, "trade_tick_value", 0.0) or 0.0)
        # valore_punto = quanto vale 1 unita' di prezzo per 1 lotto.
        valore_punto = (valore_tick / passo_tick) if passo_tick else 0.0

        return (
            True,
            {
                "simbolo": info.name,
                "descrizione": getattr(info, "description", ""),
                "cifre": int(info.digits),
                "volume_min": float(info.volume_min),
                "volume_max": float(info.volume_max),
                "volume_step": float(info.volume_step),
                "trade_tick_size": passo_tick,
                "trade_tick_value": valore_tick,
                "valore_punto": valore_punto,
                "spread_punti": int(getattr(info, "spread", 0)),
                "contract_size": float(getattr(info, "trade_contract_size", 0.0)),
                # La distanza minima fra prezzo e stop/target che il broker
                # accetta, in punti. Sotto questa soglia MT5 rifiuta con
                # `retcode 10016 (Invalid stops)` — la seconda causa di quel
                # rifiuto, dopo lo stop dalla parte sbagliata. Va convertita
                # in prezzo moltiplicandola per `point`.
                "stops_level_punti": int(getattr(info, "trade_stops_level", 0) or 0),
                "punto": float(getattr(info, "point", 0.0) or 0.0),
            },
            "specifiche lette",
        )


def conto_e_demo() -> tuple[bool, str]:
    """True solo se il conto collegato e' un DEMO.

    E' il controllo che precede qualsiasi invio di ordine di collaudo. Un
    ordine di prova su un conto reale non e' una prova: e' un'operazione.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, messaggio
    with _lucchetto:
        conto = mt5.account_info()
        if conto is None:
            return False, "account_info() vuota: impossibile stabilire il tipo di conto"
        modo = int(getattr(conto, "trade_mode", -1))
        demo = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        if modo == demo:
            return True, f"conto demo {conto.login} su {conto.server}"
        nomi = {0: "DEMO", 1: "CONTEST", 2: "REALE"}
        return False, f"conto {nomi.get(modo, modo)} {conto.login}: non e' un demo"


# Lo scarto fra l'orologio del server del broker e UTC. E' una proprieta' del
# SERVER, non del simbolo, quindi se ne tiene una sola misura per processo.
_scarto_server: Optional[timedelta] = None

# L'ultimo orario di tick visto per ciascun simbolo. Serve a distinguere un
# mercato vivo da uno fermo: e' l'unico segnale onesto che abbiamo.
_ultimo_tick: dict[str, int] = {}

# I valori plausibili per lo scarto di un broker, in ore. DEF-03 descrive
# questo server come UTC+2 d'inverno e UTC+3 d'estate; si lascia da 0 a +4 per
# non legarsi a un broker solo. E' l'ultima rete: a mercato fermo il candidato
# diventa NEGATIVO e cala di un'ora ogni ora.
SCARTO_PLAUSIBILE_ORE = range(0, 5)


def _scarto_del_server(
    simbolo: str, tick: Any, adesso: datetime
) -> Optional[timedelta]:
    """Di quanto l'orologio del server e' avanti rispetto a UTC.

    MT5 marca ogni barra con l'orologio del server e la consegna come se
    fosse gia' UTC: senza correggerla ogni candela risulta spostata. Misurato
    il 2026-09-18 su questo conto: +3h (ora legale), confermato allineando le
    chiusure H1 contro l'archivio Dukascopy - 2,6 pip di scarto medio contro
    ~70 senza correzione.

    **Perche' non basta guardare il tick.** La prima versione ricalcolava lo
    scarto ad ogni chiamata da `symbol_info_tick`. Ma quel tick si CONGELA
    quando il mercato chiude: da li' in poi la differenza fra l'ora del tick e
    l'ora vera cresce di un'ora ogni ora, e le barre venivano timbrate sempre
    piu' avanti. Con orari nuovi `INSERT OR IGNORE` non le riconosceva come
    duplicati e le archiviava: il 2026-09-21 in `bot.db` c'erano **329 candele
    orarie su 387 scritte a mercato chiuso**, un fine settimana intero di
    prezzi mai scambiati, che poi alimentavano giornaliere del sabato.

    **Il segnale giusto e' il tick che avanza.** Un mercato fermo ha un tick
    fermo; un mercato vivo ne ha uno che cambia. Si misura solo quando e'
    avanzato, si tiene l'ultima misura buona quando non lo e'.

    Non basta "il tick e' vecchio piu' di N minuti": al cambio dell'ora legale
    il tick e' vivo ma lo scarto vero cambia di un'ora, e un controllo
    sull'eta' lo scambierebbe per un tick fermo, restando bloccato sul vecchio
    valore per sei mesi. Con l'avanzamento, invece, il nuovo valore si prende
    subito (provato in `tests/test_orario_server.py`).

    Senza nessuna misura attendibile restituisce `None`: chi chiama non
    archivia. Meglio nessuna candela che una con l'ora sbagliata.
    """
    global _scarto_server

    if tick is None or not getattr(tick, "time", 0):
        return _scarto_server

    ora_tick = int(tick.time)
    precedente = _ultimo_tick.get(simbolo)
    _ultimo_tick[simbolo] = ora_tick

    if precedente is None or ora_tick == precedente:
        # Primo avvistamento, oppure mercato fermo. In nessuno dei due casi
        # questo tick dice che ora sia sul server: al primo giro non si sa
        # ancora se stia avanzando, e fermo non avanza per definizione.
        return _scarto_server

    ora_server = datetime.fromtimestamp(ora_tick, tz=timezone.utc)
    ore = round((ora_server - adesso).total_seconds() / 3600)
    if ore not in SCARTO_PLAUSIBILE_ORE:
        log.warning(
            "%s: scarto del server implausibile (%+d ore), misura ignorata",
            simbolo, ore)
        return _scarto_server

    if _scarto_server != timedelta(hours=ore):
        log.info("scarto del server del broker: %+d ore rispetto a UTC", ore)
    _scarto_server = timedelta(hours=ore)
    return _scarto_server


def candele(simbolo: str, timeframe_mt5: int, quante: int) -> tuple[bool, list[dict[str, Any]], str]:
    """Legge le barre storiche di un simbolo.

    Restituisce dizionari con `apertura_utc`, `open`, `high`, `low`, `close`.
    **`apertura_utc` e' l'istante di APERTURA della barra**, che e' come MT5 le
    marca: convertirlo in chiusura e' compito di chi chiama, e sbagliarlo
    significa vedere ogni candela un periodo prima del dovuto.

    L'ultima barra restituita da MT5 e' quella **in formazione**. Viene
    consegnata cosi' com'e': scartarla e' parte della conversione.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, [], messaggio

    with _lucchetto:
        if not mt5.symbol_select(simbolo, True):
            codice, descrizione = _errore_mt5()
            return False, [], f"simbolo {simbolo} non selezionabile: [{codice}] {descrizione}"
        barre = mt5.copy_rates_from_pos(simbolo, timeframe_mt5, 0, quante)
        tick = mt5.symbol_info_tick(simbolo)

    if barre is None or len(barre) == 0:
        codice, descrizione = _errore_mt5()
        return False, [], f"nessuna barra per {simbolo}: [{codice}] {descrizione}"

    adesso = datetime.now(timezone.utc)
    scarto_server = _scarto_del_server(simbolo, tick, adesso)
    if scarto_server is None:
        return False, [], (
            f"{simbolo}: scarto del server non misurabile (nessun tick vivo e "
            f"nessuna misura precedente). Non si archivia: meglio nessuna "
            f"candela che una con l'orario sbagliato"
        )

    lette = []
    for barra in barre:
        apertura = datetime.fromtimestamp(int(barra["time"]), tz=timezone.utc) - scarto_server
        # Rete di sicurezza indipendente dalla misura: una barra che si apre
        # nel futuro non esiste. Se lo scarto fosse sbagliato in un modo non
        # previsto, qui si ferma invece di entrare in archivio.
        if apertura > adesso + timedelta(minutes=1):
            log.warning("%s: barra con apertura nel futuro (%s), scartata",
                        simbolo, apertura)
            continue
        lette.append({
            "apertura_utc": apertura,
            "open": float(barra["open"]),
            "high": float(barra["high"]),
            "low": float(barra["low"]),
            "close": float(barra["close"]),
        })
    if not lette:
        return False, [], f"{simbolo}: nessuna barra utilizzabile dopo i controlli"
    return True, lette, f"{len(lette)} barre"


def posizioni_per_strumento() -> tuple[bool, dict[str, int], str]:
    """Quante posizioni aperte per ciascuno strumento.

    E' il dato che RISK-06 usa per il tetto delle quattro posizioni e RISK-02
    per contare `n` dentro il gruppo di correlazione.
    """
    ok, posizioni, messaggio = posizioni_broker()
    if not ok:
        return False, {}, messaggio

    # MT5 restituisce il nome **suffissato** (`EURUSD.a`). Chi legge questo
    # dizionario — `motore.valuta` per ESCL-11 e `rischio.posizioni_nel_gruppo`
    # per RISK-02 — lo interroga coi nomi nudi dell'UNIVERSO. Con un suffisso
    # configurato e nessuna conversione il conteggio risultava sempre vuoto:
    # il tetto delle quattro posizioni non scattava mai e RISK-02 applicava
    # sempre l'1,00% pieno, senza che nulla comparisse nei log.
    suffisso = impostazioni().MT5_SUFFISSO_SIMBOLI
    conteggi: dict[str, int] = {}
    ignorate = 0
    for posizione in posizioni:
        strumento = cfd_da_simbolo_esecuzione(posizione["simbolo"], suffisso)
        if strumento is None:
            # Posizione aperta a mano su uno strumento fuori da PRIN-08: non
            # entra nei conteggi delle regole, che parlano dell'UNIVERSO.
            ignorate += 1
            continue
        conteggi[strumento] = conteggi.get(strumento, 0) + 1
    if ignorate:
        messaggio = f"{messaggio}, {ignorate} fuori dall'UNIVERSO"
    return True, conteggi, messaggio


def costi_posizione(ticket: int) -> tuple[bool, float, str]:
    """Quanto ha gia' incassato il broker su questa posizione, in valuta conto.

    Commissioni piu' swap, come li riporta MT5 sui deal di quel `position`.
    Il segno e' quello del broker: un costo e' NEGATIVO. Qui si restituisce
    il valore assoluto, perche' chi chiama vuole "quanto devo recuperare".

    ## Perche' serve

    `GEST-04` dice che il break even deve coprire **spread e commissioni**,
    ma PA-46 aveva risolto la commissione moltiplicando lo spread per due --
    e il documento di decisione lo ammette: *"il fattore 2 e' mio"*. Nel
    codice la commissione non entrava in nessun calcolo.

    Misurato il 2026-09-22 su 17 posizioni e 8,06 lotti: il saldo e' sceso di
    47,81 EUR mentre il movimento di prezzo ne spiegava 15,11. Gli altri
    32,70 erano costi, cioe' **4,06 EUR per lotto**. Su strumenti con spread
    largo rispetto alla commissione due spread bastano; su `USDJPY`, dove lo
    spread e' piccolo in proporzione, no -- e il pareggio chiudeva in perdita.

    Qui non si stima nulla: si chiede al broker quanto ha preso.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, 0.0, messaggio

    with _lucchetto:
        deal = mt5.history_deals_get(position=ticket)

    if deal is None:
        codice, descrizione = _errore_mt5()
        return False, 0.0, f"history_deals_get(position={ticket}) fallita: [{codice}] {descrizione}"

    totale = sum(
        float(getattr(d, "commission", 0.0) or 0.0)
        + float(getattr(d, "swap", 0.0) or 0.0)
        for d in deal
    )
    return True, abs(totale), f"{len(deal)} deal, costi {totale:.2f}"


def pnl_chiuso(da: datetime, a: Optional[datetime] = None) -> tuple[bool, float, str]:
    """P&L **chiuso** nel periodo, come lo vogliono RISK-07, RISK-08 e RISK-09.

    Somma profitto, commissioni e swap dei deal di uscita. Le posizioni ancora
    aperte non entrano: RISK-10 dice esplicitamente che i limiti si calcolano
    sul P&L chiuso, e che una posizione aperta non viene chiusa dal
    raggiungimento di un limite.
    """
    ok, messaggio = _assicura_connessione()
    if not ok or mt5 is None:
        return False, 0.0, messaggio

    fine = a or datetime.now(timezone.utc)
    with _lucchetto:
        deal = mt5.history_deals_get(da, fine)

    if deal is None:
        codice, descrizione = _errore_mt5()
        # Nessuno storico non e' un errore: puo' non esserci stata attivita'.
        if codice == 0:
            return True, 0.0, "nessun deal nel periodo"
        return False, 0.0, f"history_deals_get fallita: [{codice}] {descrizione}"

    uscita = int(getattr(mt5, "DEAL_ENTRY_OUT", 1))
    totale = sum(
        float(d.profit) + float(getattr(d, "commission", 0.0)) + float(getattr(d, "swap", 0.0))
        for d in deal
        if int(getattr(d, "entry", -1)) == uscita
    )
    return True, totale, f"{len(deal)} deal nel periodo"


def stato() -> dict[str, Any]:
    """Riassunto dello stato del broker, usato da /salute e dal collaudo."""
    if not MT5_DISPONIBILE:
        return {
            "mt5_disponibile": False,
            "connesso": False,
            "trading_permesso": False,
            "dettaglio": MOTIVO_INDISPONIBILE,
            "conto": None,
            "posizioni_aperte": None,
        }

    ok_conto, conto, messaggio_conto = info_conto()
    ok_posizioni, posizioni, _ = posizioni_broker()
    permesso, messaggio_permesso = trading_permesso()
    return {
        "mt5_disponibile": True,
        "connesso": _connesso,
        "trading_permesso": permesso,
        "dettaglio": messaggio_conto if ok_conto else f"{messaggio_conto} | {messaggio_permesso}",
        "conto": conto if ok_conto else None,
        "posizioni_aperte": len(posizioni) if ok_posizioni else None,
    }
