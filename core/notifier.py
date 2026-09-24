"""Notifiche su Telegram via API HTTP (nessuna libreria dedicata).

Se token o chat_id non sono configurati il messaggio finisce a console:
l'impianto deve poter girare anche senza Telegram.
"""

import threading
import time
from typing import Optional

import httpx

# L'interruttore delle prove sta in `core/ambiente`: e' lo stesso per Telegram
# e per l'API di Claude, e due copie divergerebbero.
from core.ambiente import VARIABILE_SILENZIO, in_prova  # noqa: F401
from core.config import impostazioni
from core.log import diario
from core.models import AlertIn, Decision

log = diario("telegram")

URL_BASE: str = "https://api.telegram.org/bot{token}/{metodo}"


def _url(metodo: str) -> str:
    """Compone l'URL dell'API Telegram per il metodo richiesto."""
    return URL_BASE.format(token=impostazioni().TELEGRAM_TOKEN, metodo=metodo)


def invia(testo: str) -> tuple[bool, str]:
    """Invia un messaggio a Telegram, a tutti i destinatari configurati.

    `TELEGRAM_CHAT_ID` puo' contenere piu' di una chat, separate da virgola:
    serve a chi vuole le notifiche sul telefono e su un gruppo. Scriverne due
    e vederle sparire tutte e due, perche' la stringa intera viene passata a
    Telegram come se fosse un numero solo, e' il tipo di errore che non si
    scopre finche' non serve davvero una notifica.

    Restituisce (riuscito, dettaglio): riuscito se **almeno una** consegna e'
    andata a buon fine. Se Telegram non e' configurato stampa a log e
    restituisce (False, ...): non e' un errore fatale, e' una funzionalita'
    spenta.

    Non solleva mai: una notifica persa non deve far cadere un ordine.
    """
    if in_prova():
        log.info("[prova, non inviato] %s", testo.replace("\n", " | ")[:160])
        return False, "siamo in una prova: nessun messaggio e' uscito"

    cfg = impostazioni()
    if not cfg.telegram_configurato:
        log.info("[telegram spento] %s", testo.replace("\n", " | "))
        return False, "telegram non configurato (manca TELEGRAM_TOKEN o TELEGRAM_CHAT_ID)"

    esiti: list[tuple[bool, str]] = [
        _invia_a(destinatario, testo) for destinatario in cfg.destinatari_telegram
    ]
    riusciti = [d for ok, d in esiti if ok]
    falliti = [d for ok, d in esiti if not ok]

    if not falliti:
        # A voce, anche quando va bene. Senza questa riga il diario e' identico
        # che Telegram funzioni o no, e l'unica prova che un messaggio sia
        # partito e' il telefono di chi lo riceve: quando l'utente dice "non mi
        # arriva niente" non c'e' modo di sapere se il bot non l'ha mandato o
        # se Telegram non l'ha consegnato.
        log.info("inviato a %d destinatari: %s",
                 len(riusciti), testo.split("\n", 1)[0][:80])
        return True, f"messaggio inviato a {len(riusciti)} destinatari"
    if riusciti:
        # Consegna parziale. Restituisce comunque True -- il messaggio e'
        # arrivato a qualcuno -- ma va detto forte: con piu' destinatari
        # configurati, uno che rifiuta mentre l'altro accetta sparisce del
        # tutto, e chi non riceve piu' niente non ha nessun indizio.
        dettaglio = (f"inviato a {len(riusciti)} destinatari su {len(esiti)}; "
                     f"falliti: {'; '.join(falliti)}")
        log.warning("consegna parziale: %s", dettaglio)
        return True, dettaglio
    return False, "; ".join(falliti)


def _invia_a(destinatario: str, testo: str) -> tuple[bool, str]:
    """Una consegna, con i suoi tentativi."""
    # Anche qui, e non solo in `invia`: questa e' la funzione che parla con
    # la rete, ed e' l'ultimo punto in cui si puo' fermare un messaggio.
    # Chiuderla solo a monte lascerebbe aperta la porta a chi la chiama
    # direttamente, cosa che e' gia' successa.
    if in_prova():
        log.info("[prova, non inviato] %s", testo.replace("\n", " | ")[:160])
        return False, "siamo in una prova: nessun messaggio e' uscito"

    cfg = impostazioni()
    tentativi = max(1, cfg.TELEGRAM_TENTATIVI)
    ultimo_dettaglio = ""

    for tentativo in range(1, tentativi + 1):
        try:
            risposta = httpx.post(
                _url("sendMessage"),
                json={
                    "chat_id": destinatario,
                    "text": testo,
                    # I messaggi usano <b>, <i> e <code>: senza questo
                    # Telegram li mostrerebbe come tag letterali.
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=cfg.TIMEOUT_HTTP,
            )
        except httpx.HTTPError as errore:
            ultimo_dettaglio = f"errore di rete verso Telegram: {errore!r}"
        else:
            if risposta.status_code == 200 and risposta.json().get("ok", False):
                return True, "messaggio inviato"
            if risposta.status_code == 429:
                # Troppi messaggi: Telegram dice lui quanto aspettare.
                attesa = int(risposta.json().get("parameters", {}).get("retry_after", 5))
                ultimo_dettaglio = f"limite di frequenza, attendo {attesa}s"
                log.warning(ultimo_dettaglio)
                time.sleep(min(attesa, 30))
                continue
            if 400 <= risposta.status_code < 500:
                # Token sbagliato o chat inesistente: ritentare non serve.
                dettaglio = f"Telegram ha rifiutato ({risposta.status_code}): {risposta.text[:300]}"
                log.error(dettaglio)
                return False, dettaglio
            ultimo_dettaglio = f"Telegram ha risposto {risposta.status_code}: {risposta.text[:200]}"

        if tentativo < tentativi:
            attesa = 2 ** (tentativo - 1)  # 1s, 2s, 4s...
            log.warning("%s (tentativo %d/%d, riprovo fra %ds)", ultimo_dettaglio, tentativo, tentativi, attesa)
            time.sleep(attesa)

    log.error("notifica non consegnata: %s", ultimo_dettaglio)
    return False, ultimo_dettaglio


def verifica_credenziali() -> tuple[bool, str]:
    """Chiama getMe per capire se il token e' valido. Usata dal collaudo."""
    cfg = impostazioni()
    if not cfg.telegram_configurato:
        return False, "telegram non configurato (manca TELEGRAM_TOKEN o TELEGRAM_CHAT_ID)"
    try:
        risposta = httpx.get(_url("getMe"), timeout=cfg.TIMEOUT_HTTP)
    except httpx.HTTPError as errore:
        return False, f"errore di rete verso Telegram: {errore!r}"
    if risposta.status_code != 200:
        return False, f"getMe ha risposto {risposta.status_code}: {risposta.text[:300]}"
    corpo = risposta.json()
    if not corpo.get("ok", False):
        return False, f"token rifiutato: {corpo}"
    nome = corpo.get("result", {}).get("username", "?")
    return True, f"token valido, bot @{nome}"


def invia_appena_possibile(testo: str) -> None:
    """Come `invia`, ma senza far aspettare chi chiama.

    `invia` puo' bloccare a lungo: `TELEGRAM_TENTATIVI` tentativi per ogni
    destinatario, con attese crescenti fra l'uno e l'altro piu' il timeout
    HTTP di ciascuno. Sono decine di secondi quando Telegram non risponde.

    Va bene per un avviso mandato da uno script, non per chi sta decidendo su
    una candela appena chiusa: `arma()` gira dentro `processa_alert`, quindi
    sul thread del mercato e sulla richiesta `/webhook`, e un CRT armato non
    puo' costare mezzo minuto di attesa perche' la rete e' lenta. Stessa cosa
    per il riepilogo periodico, che parte dal ciclo di mercato.

    Il messaggio parte su un thread suo e chi chiama torna subito. Se la
    consegna fallisce lo dice il diario: non c'e' nulla da decidere in base
    all'esito, quindi non serve aspettarlo.
    """
    def _manda() -> None:
        try:
            inviato, dettaglio = invia(testo)
            if not inviato:
                log.warning("notifica non consegnata: %s", dettaglio)
        except Exception:                              # pragma: no cover
            log.exception("notifica non inviata")

    threading.Thread(target=_manda, name="telegram", daemon=True).start()


def invia_all_equipe(testo: str) -> tuple[bool, str]:
    """I verbali degli agenti, sul loro canale.

    Canale separato da quello operativo, e separato apposta: li' ci vanno
    "aperta", "chiusa", "stop colpito", e basta. Un verbale da venti righe
    mescolato agli avvisi fa perdere l'avviso, che e' l'unica cosa che
    richiede di fare qualcosa.

    Se il canale non e' configurato non parte niente e **non si ripiega**
    sull'altro: un ripiego silenzioso riempirebbe di colpo proprio il canale
    che si voleva tenere pulito.
    """
    if in_prova():
        log.info("[prova, non inviato] equipe: %s",
                 testo.replace("\n", " | ")[:160])
        return False, "siamo in una prova: nessun messaggio e' uscito"

    cfg = impostazioni()
    if not cfg.equipe_configurata:
        log.info("[equipe spenta] %s", testo.replace("\n", " | ")[:200])
        return False, "canale equipe non configurato (manca TELEGRAM_CHAT_EQUIPE)"

    esiti = [_invia_a(d, testo) for d in cfg.destinatari_equipe()]
    riusciti = [d for ok, d in esiti if ok]
    falliti = [d for ok, d in esiti if not ok]
    if riusciti:
        return True, f"verbale inviato a {len(riusciti)} destinatari"
    return False, "; ".join(falliti)


def verbale_appena_possibile(testo: str) -> None:
    """Come `invia_appena_possibile`, ma sul canale dell'equipe.

    Su un thread suo per la stessa ragione dell'altro: un verbale non puo'
    costare mezzo minuto a chi sta decidendo su una candela appena chiusa.
    """
    def _manda() -> None:
        try:
            inviato, dettaglio = invia_all_equipe(testo)
            if not inviato:
                log.info("verbale non consegnato: %s", dettaglio)
        except Exception:                              # pragma: no cover
            log.exception("verbale non inviato")

    threading.Thread(target=_manda, name="equipe", daemon=True).start()


def messaggio_decisione(
    alert: AlertIn,
    decisione: Decision,
    modalita: str,
    dettaglio: Optional[str] = None,
) -> str:
    """Il messaggio di un'operazione, scritto per essere letto sul telefono.

    Prima era un dump: il ticker del FUTURE (`6E1!`, che non dice niente a
    nessuno), l'OHLC della candela, e la sfilza dei codici regola. Su un
    telefono, fra decine di notifiche, non si capiva ne' cosa fosse stato
    aperto ne' a che prezzo.

    Qui si scrive cio' che serve a chi guarda: lo strumento col nome vero,
    da che parte, quanto, e i tre livelli con il rapporto fra rischio e
    rendimento. I codici regola restano nel diario e in archivio, che e' il
    posto dove si va a cercarli quando servono davvero.
    """
    nome = decisione.simbolo or alert.simbolo
    verso = "LONG" if decisione.azione == "BUY" else "SHORT"
    segno = "🟢" if decisione.azione == "BUY" else "🔴"

    righe = [f"{segno} <b>{nome} {verso}</b>  ·  {_tempo(alert.tf)}"]

    if decisione.volume:
        righe.append(f"{decisione.volume} lotti")

    livelli = []
    if decisione.sl is not None:
        livelli.append(f"stop <code>{decisione.sl:g}</code>")
    if decisione.tp is not None:
        livelli.append(f"target <code>{decisione.tp:g}</code>")
    if livelli:
        righe.append("  ·  ".join(livelli))

    # Il rapporto e' il numero che dice se l'operazione vale la pena, e si
    # calcola sui livelli che partono davvero al broker.
    if decisione.sl is not None and decisione.tp is not None:
        rif = alert.chiusura
        rischio = abs(rif - decisione.sl)
        if rischio > 0:
            righe.append(f"rapporto <b>{abs(decisione.tp - rif) / rischio:.1f}</b> a 1")

    righe.extend(_analisi(decisione))

    if dettaglio:
        righe.append(f"<i>{dettaglio}</i>")
    return "\n".join(righe)


# Cosa dice ciascuna conferma, quando c'e' e quando manca, in italiano
# corrente. Niente sigle e niente gergo: chi legge sul telefono deve capire
# senza sapere cosa siano un CISD o una divergenza SMT. Il codice della
# regola resta in archivio e nel diario, che e' dove si va a cercarlo.
_IN_PAROLE: dict[str, tuple[str, str]] = {
    "CRT-06": ("gli altri tempi puntano dalla stessa parte",
               "gli altri tempi puntano altrove"),
    "CRT-10": ("il prezzo ha ripulito tutti e due i lati",
               "ripulendo i due lati, la spinta va dall'altra parte"),
    "CRT-11": ("la spinta ha cambiato verso",
               "la spinta non ha ancora cambiato verso"),
    "CRT-12": ("le coppie simili non l'hanno seguito: è un segno di inversione",
               "le coppie simili si muovono uguali: nessun segno di inversione"),
    "CRT-15": ("siamo in uno degli orari buoni della giornata",
               "siamo fuori dagli orari buoni della giornata"),
    "CRT-17": ("il prezzo si tiene dalla parte giusta del movimento",
               "il prezzo non si tiene dalla parte giusta del movimento"),
    "CRT-18": ("ha chiuso dalla parte giusta della coda",
               "ha chiuso dalla parte sbagliata della coda"),
    "CRT-20": ("la candela ha code lunghe: il prezzo è stato respinto",
               "la candela ha code corte: il prezzo non è stato respinto"),
}


def _analisi(decisione: Decision) -> list[str]:
    """Cosa ha visto il motore, conferma per conferma.

    Il responso c'e' **anche per le conferme che non bloccano**: quello e' il
    punto. Un ordine partito con cinque conferme su otto mancanti e uno
    partito con sette su otto sono due fatti molto diversi, e finche' il
    messaggio diceva solo "aperto" erano indistinguibili.

    E' il quadro da cui si decide quali conferme valga la pena riaccendere:
    se una manca su ogni operazione che poi perde, si e' trovata; se manca
    indifferentemente su vincenti e perdenti, non serve.
    """
    responso = decisione.responso_romeo or {}
    lettura = getattr(decisione, "lettura_crt", None) or {}
    if not responso and not lettura:
        return []

    def frasi(valore, indice):
        return [_IN_PAROLE.get(c, (c, c))[indice]
                for c, v in sorted(responso.items()) if v is valore]

    a_favore = frasi(True, 0)
    contro = frasi(False, 1)
    muti = sum(1 for v in responso.values() if v is None)

    righe = ["", "<b>L'analisi</b>"]

    # 1. Il disegno che ha fatto scattare tutto, raccontato.
    if decisione.direzione == "LONG":
        righe.append("Il prezzo è sceso sotto il minimo precedente e poi "
                     "è risalito: chi vendeva ha finito la forza proprio "
                     "dove sembrava averne di più.")
    elif decisione.direzione == "SHORT":
        righe.append("Il prezzo è salito sopra il massimo precedente e poi "
                     "è ricaduto: chi comprava ha finito la forza proprio "
                     "dove sembrava averne di più.")

    # 1bis. Gli stessi fatti IN NUMERI, per poterli ritrovare sul grafico.
    righe.extend(_numeri_del_disegno(lettura))

    # 2. Cosa lo sostiene e cosa no, in frasi legate invece che in elenco.
    if not responso:
        righe.append("<i>Le otto conferme non sono state valutate: il bot è "
                     "in prova e apre su ogni figura che riconosce.</i>")
        return righe
    if a_favore:
        righe.append("A favore: " + _elenco(a_favore) + ".")
    if contro:
        righe.append("Contro: " + _elenco(contro) + ".")
    if muti:
        righe.append(_su_altri(muti))

    righe.append(_quanto_pesa(len(a_favore), len(contro), len(responso)))
    return righe


_TEMPI_IN_PAROLE: dict[str, str] = {
    "TF_M1min": "1 minuto", "TF_M5": "5 minuti", "TF_M15": "15 minuti",
    "TF_H1": "1 ora", "TF_H4": "4 ore", "TF_H6": "6 ore", "TF_H12": "12 ore",
    "TF_D1": "giornaliero", "TF_W1": "settimanale", "TF_M1": "mensile",
    "TF_3M": "trimestrale", "TF_6M": "semestrale", "TF_12M": "annuale",
}


def _tempo(codice) -> str:
    """`TF_H1` non dice niente a nessuno; "1 ora" si'."""
    if codice is None:
        return ""
    return _TEMPI_IN_PAROLE.get(str(codice), str(codice))


def _numeri_del_disegno(lettura: dict) -> list[str]:
    """Su quale grafico, a quale prezzo: i fatti verificabili.

    Senza questi il messaggio chiedeva fiducia. Chi legge deve poter aprire
    il grafico, andare su quel timeframe e a quel prezzo, e vedere se il bot
    ha letto bene -- perche' e' l'unico modo per scoprire dove sbaglia.
    """
    if not lettura:
        return []
    righe: list[str] = []

    grande = _tempo(lettura.get("tf_range"))
    piccolo = _tempo(lettura.get("tf_esecuzione"))
    if grande and piccolo:
        righe.append(f"La figura è sul grafico da <b>{grande}</b>, "
                     f"l'ingresso è stato cercato su quello da <b>{piccolo}</b>.")
    elif grande:
        righe.append(f"La figura è sul grafico da <b>{grande}</b>.")

    livello = lettura.get("livello_range")
    estremo = lettura.get("estremo_superato")
    rientro = lettura.get("rientro")
    if livello is not None and estremo is not None and rientro is not None:
        oltre = "sopra" if lettura.get("verso") == "SHORT" else "sotto"
        indietro = "sotto" if lettura.get("verso") == "SHORT" else "sopra"
        righe.append(
            f"Il bordo da battere era <code>{livello:g}</code>: il prezzo è "
            f"andato {oltre} fino a <code>{estremo:g}</code> e poi è tornato "
            f"{indietro}, chiudendo a <code>{rientro:g}</code>.")

    kl = lettura.get("key_level")
    if kl is not None:
        tf_kl = _tempo(lettura.get("tf_key_level"))
        dove = f" del grafico da {tf_kl}" if tf_kl else ""
        righe.append(f"Il livello che ha fatto da calamita è "
                     f"<code>{kl:g}</code>{dove}.")

    via = lettura.get("via")
    if via:
        righe.append(f"L'ingresso è avvenuto sul {via}.")
    return righe


def _su_altri(quanti: int) -> str:
    """Gli aspetti su cui non c'erano dati, al singolare o al plurale."""
    if quanti == 1:
        return "Su un altro aspetto non c'erano abbastanza dati per dire qualcosa."
    return (f"Su altri {quanti} aspetti non c'erano abbastanza dati "
            "per dire qualcosa.")


def _elenco(voci: list) -> str:
    """Le voci unite come le scriverebbe una persona: virgole e una `e`."""
    if len(voci) == 1:
        return voci[0]
    return ", ".join(voci[:-1]) + " e " + voci[-1]


def _segnali(quanti: int) -> str:
    """Singolare o plurale: "1 segnali" non lo scrive nessuno."""
    return "segnale" if quanti == 1 else "segnali"


def _quanto_pesa(favore: int, contro: int, totale: int) -> str:
    """Quanto regge il quadro, detto a colpo d'occhio.

    Non e' una previsione: e' il rapporto fra cio' che sosteneva
    l'operazione e cio' che la contraddiceva. Serve a capire subito se
    il setup era solido o tirato per i capelli, ed e' il numero da
    incrociare con l'esito per sapere quali segnali contino davvero.
    """
    if contro == 0 and favore:
        return f"<i>Quadro pulito: {favore} {_segnali(favore)} a favore, nessuno contro.</i>"
    if favore > contro:
        return (f"<i>Quadro favorevole ma non pieno: {favore} a favore, "
                f"{contro} contro.</i>")
    if favore == contro:
        return f"<i>Quadro incerto: {favore} a favore e {contro} contro.</i>"
    return (f"<i>Quadro debole: solo {favore} {_segnali(favore)} a favore "
            f"su {totale}, {contro} contrari.</i>")


def messaggio_esito(simbolo: str, direzione: str, colpito: str,
                    livello: float, prezzo: float,
                    prezzo_ingresso: Optional[float] = None) -> str:
    """Come si e' chiusa un'operazione, in due righe.

    `colpito` e' "sl" o "tp". Il guadagno o la perdita si dice in parole,
    non solo col livello: e' la prima cosa che si vuole sapere.
    """
    vinta = colpito.lower() == "tp"
    segno = "✅" if vinta else "🛑"
    esito = "target" if vinta else "stop"
    # Il suffisso del broker (`EURUSD+`) e' un fatto del conto, non dello
    # strumento, e il verso si scrive come nel messaggio di apertura: LONG e
    # SHORT, non BUY e SELL, altrimenti la stessa operazione ha due nomi.
    nome = simbolo.rstrip("+")
    verso = "LONG" if direzione.upper() == "BUY" else "SHORT"
    righe = [f"{segno} <b>{nome} {verso}</b>  ·  {esito}",
             f"chiusa a <code>{prezzo:g}</code>"]
    if prezzo_ingresso:
        punti = (prezzo - prezzo_ingresso) * (1 if direzione.upper() == "BUY" else -1)
        righe[-1] += f"  ·  {punti:+g}"
    return "\n".join(righe)
