"""Notifiche su Telegram via API HTTP (nessuna libreria dedicata).

Se token o chat_id non sono configurati il messaggio finisce a console:
l'impianto deve poter girare anche senza Telegram.
"""

import threading
import time
from typing import Optional

import httpx

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
        return True, f"messaggio inviato a {len(riusciti)} destinatari"
    if riusciti:
        return True, (f"inviato a {len(riusciti)} destinatari su {len(esiti)}; "
                      f"falliti: {'; '.join(falliti)}")
    return False, "; ".join(falliti)


def _invia_a(destinatario: str, testo: str) -> tuple[bool, str]:
    """Una consegna, con i suoi tentativi."""
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


def messaggio_decisione(
    alert: AlertIn,
    decisione: Decision,
    modalita: str,
    dettaglio: Optional[str] = None,
) -> str:
    """Testo leggibile che riassume alert e decisione, per Telegram/console."""
    righe = [
        f"[{modalita.upper()}] {alert.simbolo} {alert.tf}",
        f"candela chiusa: {alert.chiusura_candela_utc} UTC",
        f"O {alert.apertura} H {alert.massimo} L {alert.minimo} C {alert.chiusura}",
        f"azione: {decisione.azione}",
    ]
    if decisione.motivo:
        righe.append(f"motivo: {decisione.motivo}")
    if alert.rsi is not None:
        righe.append(f"rsi: {alert.rsi}")
    if alert.nota:
        righe.append(f"nota: {alert.nota}")
    if dettaglio:
        righe.append(dettaglio)
    return "\n".join(righe)
