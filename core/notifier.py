"""Notifiche su Telegram via API HTTP (nessuna libreria dedicata).

Se token o chat_id non sono configurati il messaggio finisce a console:
l'impianto deve poter girare anche senza Telegram.
"""

from typing import Optional

import httpx

from core.config import impostazioni
from core.models import AlertIn, Decision

URL_BASE: str = "https://api.telegram.org/bot{token}/{metodo}"


def _url(metodo: str) -> str:
    """Compone l'URL dell'API Telegram per il metodo richiesto."""
    return URL_BASE.format(token=impostazioni().TELEGRAM_TOKEN, metodo=metodo)


def invia(testo: str) -> tuple[bool, str]:
    """Invia un messaggio a Telegram.

    Restituisce (riuscito, dettaglio). Se Telegram non e' configurato stampa
    a console e restituisce (False, "telegram non configurato"): non e' un
    errore fatale, e' una funzionalita' spenta.
    """
    cfg = impostazioni()
    if not cfg.telegram_configurato:
        print(f"[TELEGRAM NON CONFIGURATO] {testo}")
        return False, "telegram non configurato (manca TELEGRAM_TOKEN o TELEGRAM_CHAT_ID)"

    try:
        risposta = httpx.post(
            _url("sendMessage"),
            json={
                "chat_id": cfg.TELEGRAM_CHAT_ID,
                "text": testo,
                "disable_web_page_preview": True,
            },
            timeout=cfg.TIMEOUT_HTTP,
        )
    except httpx.HTTPError as errore:
        # Rete assente, DNS, timeout: lo diciamo, ma non facciamo cadere il bot.
        dettaglio = f"errore di rete verso Telegram: {errore!r}"
        print(f"[TELEGRAM KO] {dettaglio}")
        return False, dettaglio

    if risposta.status_code != 200:
        dettaglio = f"Telegram ha risposto {risposta.status_code}: {risposta.text[:300]}"
        print(f"[TELEGRAM KO] {dettaglio}")
        return False, dettaglio

    corpo = risposta.json()
    if not corpo.get("ok", False):
        dettaglio = f"Telegram ha rifiutato il messaggio: {corpo}"
        print(f"[TELEGRAM KO] {dettaglio}")
        return False, dettaglio

    return True, "messaggio inviato"


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
