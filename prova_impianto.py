"""Collaudo dell'impianto: prova i tre collegamenti uno per uno.

Uso (con il server gia' avviato in un'altra finestra):

    python main.py            <- finestra 1
    python prova_impianto.py  <- finestra 2

Ogni prova stampa OK oppure ERRORE con il dettaglio, cosi' e' evidente quale
pezzo non funziona. Il codice di uscita e' 0 solo se passano tutte e tre.

Nota: la prova del webhook manda un alert finto al server, che quindi finira'
in archivio con nota "COLLAUDO IMPIANTO". La strategia e' uno stub, quindi
non verra' aperto nulla in nessun caso.
"""

import sys
from typing import Callable

import httpx

from core import broker, notifier, storage
from core.config import impostazioni
from core.log import configura as configura_log

# Segnaposto usati nella stampa.
VERDE_OK = "OK     "
ROSSO_KO = "ERRORE "


def indirizzo_base() -> str:
    """URL del server locale da interrogare.

    Se il server ascolta su 0.0.0.0 non possiamo chiamarlo cosi': usiamo
    l'indirizzo di loopback.
    """
    cfg = impostazioni()
    host = "127.0.0.1" if cfg.HOST in ("0.0.0.0", "") else cfg.HOST
    return f"http://{host}:{cfg.PORT}"


# --------------------------------------------------------------------------
# 1. MetaTrader 5
# --------------------------------------------------------------------------
def prova_mt5() -> tuple[bool, str]:
    """Verifica che il terminale MT5 sia raggiungibile e il conto leggibile."""
    if not broker.disponibile():
        return False, broker.MOTIVO_INDISPONIBILE

    connesso, messaggio = broker.connetti()
    if not connesso:
        return False, (
            f"{messaggio}\n"
            "         Controlla che il terminale MT5 sia aperto e loggato sul conto "
            "FP Markets, e che MT5_PATH nel .env punti al terminale giusto."
        )

    ok_conto, conto, messaggio_conto = broker.info_conto()
    if not ok_conto or conto is None:
        return False, messaggio_conto

    ok_posizioni, posizioni, messaggio_posizioni = broker.posizioni_broker()
    numero = len(posizioni) if ok_posizioni else "?"

    riga = (
        f"conto {conto['login']} su {conto['server']} | "
        f"equity {conto['equity']} {conto['valuta']} | "
        f"posizioni aperte: {numero}"
    )
    if not ok_posizioni:
        riga += f" ({messaggio_posizioni})"

    # Connettersi non basta: se "Algo Trading" e' spento gli ordini vengono
    # rifiutati senza spiegazioni. Meglio scoprirlo adesso.
    permesso, messaggio_permesso = broker.trading_permesso()
    if not permesso:
        return False, (
            f"{riga}\n"
            f"         connesso, ma NON si puo' operare: {messaggio_permesso}"
        )

    return True, f"{riga} | trading da programma permesso"


# --------------------------------------------------------------------------
# 2. Telegram
# --------------------------------------------------------------------------
def prova_telegram() -> tuple[bool, str]:
    """Verifica il token e manda davvero un messaggio di prova."""
    valido, dettaglio = notifier.verifica_credenziali()
    if not valido:
        return False, (
            f"{dettaglio}\n"
            "         Metti TELEGRAM_TOKEN (da @BotFather) e TELEGRAM_CHAT_ID nel .env. "
            "Ricorda di scrivere almeno una volta al bot, altrimenti non puo' risponderti."
        )

    inviato, dettaglio_invio = notifier.invia(
        "Collaudo impianto nvmfinancebot: se leggi questo messaggio, Telegram funziona."
    )
    if not inviato:
        return False, dettaglio_invio
    return True, f"{dettaglio} | messaggio di prova consegnato"


# --------------------------------------------------------------------------
# 3. Webhook
# --------------------------------------------------------------------------
def prova_webhook() -> tuple[bool, str]:
    """Verifica che il server risponda, rifiuti i segreti sbagliati e accetti i buoni."""
    cfg = impostazioni()
    base = indirizzo_base()

    if not cfg.webhook_configurato:
        return False, (
            "WEBHOOK_SECRET non impostato nel .env: il server rifiuta tutto per sicurezza."
        )

    # 3a. Il server e' vivo?
    try:
        risposta_salute = httpx.get(f"{base}/salute", timeout=cfg.TIMEOUT_HTTP)
    except httpx.HTTPError as errore:
        return False, (
            f"il server non risponde su {base} ({errore!r})\n"
            "         Avvia prima il server con: python main.py"
        )
    if risposta_salute.status_code != 200:
        return False, f"/salute ha risposto {risposta_salute.status_code}: {risposta_salute.text[:200]}"

    alert_finto = {
        "secret": cfg.WEBHOOK_SECRET,
        "symbol": "EURUSD",
        "tf": "15",
        "candle_close_time_utc": "2026-01-01T00:00:00Z",
        "open": 1.10000,
        "high": 1.10500,
        "low": 1.09500,
        "close": 1.10250,
        "rsi": 50.0,
        "note": "COLLAUDO IMPIANTO",
    }

    # 3b. Un segreto sbagliato deve essere respinto con 401.
    try:
        respinto = httpx.post(
            f"{base}/webhook",
            json={**alert_finto, "secret": alert_finto["secret"] + "-sbagliato"},
            timeout=cfg.TIMEOUT_HTTP,
        )
    except httpx.HTTPError as errore:
        return False, f"errore contattando /webhook: {errore!r}"
    if respinto.status_code != 401:
        return False, (
            f"un segreto sbagliato ha ricevuto {respinto.status_code} invece di 401. "
            "Il controllo di sicurezza NON sta funzionando."
        )

    # 3c. Il segreto giusto deve passare.
    try:
        accettato = httpx.post(f"{base}/webhook", json=alert_finto, timeout=cfg.TIMEOUT_HTTP)
    except httpx.HTTPError as errore:
        return False, f"errore contattando /webhook: {errore!r}"
    if accettato.status_code != 200:
        return False, f"/webhook ha risposto {accettato.status_code}: {accettato.text[:300]}"

    corpo = accettato.json()
    stato = risposta_salute.json()

    righe = [
        f"server vivo in modalita' {stato.get('modalita')} | "
        f"segreto sbagliato respinto con 401 | "
        f"alert accettato (id {corpo.get('alert_id')}), "
        f"azione {corpo.get('azione')}, esito {corpo.get('esito')}"
    ]

    # Stato reale della sorveglianza, non quello sperato.
    sentinella = stato.get("sentinella", {})
    if sentinella.get("attiva"):
        righe.append(f"         sentinella in funzione ({sentinella.get('giri', 0)} giri finora)")
    elif stato.get("posizioni_aperte_archivio"):
        righe.append("         ATTENZIONE: ci sono posizioni aperte e la sentinella NON gira")
    else:
        righe.append("         sentinella ferma (niente da sorvegliare al momento)")

    if stato.get("posizioni_scoperte"):
        righe.append("         ALLARME: posizioni aperte senza nessuno che guardi stop e target")

    return True, "\n".join(righe)


# --------------------------------------------------------------------------
# Esecuzione
# --------------------------------------------------------------------------
def esegui(nome: str, prova: Callable[[], tuple[bool, str]]) -> bool:
    """Lancia una prova, la stampa e restituisce se e' passata."""
    try:
        ok, dettaglio = prova()
    except Exception as errore:  # una prova non deve mai bloccare le altre
        ok, dettaglio = False, f"eccezione imprevista: {errore!r}"
    print(f"{VERDE_OK if ok else ROSSO_KO} {nome}")
    print(f"         {dettaglio}")
    print()
    return ok


def quadro_operativo() -> None:
    """Stampa lo stato delle salvaguardie: non e' una prova, e' un promemoria.

    Sono le impostazioni che decidono se il bot puo' farti male. Vanno viste
    ogni volta, non solo quando qualcosa si rompe.
    """
    cfg = impostazioni()
    print("QUADRO OPERATIVO")

    freno = "TIRATO (nessun ordine partira')" if cfg.bloccato else "libero"
    print(f"         freno a mano (file {cfg.FILE_BLOCCO}): {freno}")
    print(f"         alert piu' vecchi di {cfg.MAX_RITARDO_ALERT_SEC}s: non eseguiti"
          if cfg.MAX_RITARDO_ALERT_SEC else "         controllo sul ritardo alert: DISATTIVATO")
    print(f"         tetto volume per ordine: {cfg.VOLUME_MASSIMO}"
          if cfg.VOLUME_MASSIMO else "         tetto sul volume: DISATTIVATO")
    print(f"         massimo posizioni aperte: {cfg.MAX_POSIZIONI_APERTE}"
          if cfg.MAX_POSIZIONI_APERTE else "         tetto sulle posizioni aperte: DISATTIVATO")

    # Attenzione: qui si legge la configurazione, non lo stato reale del
    # server. Lo stato vero lo riporta la prova 3, che interroga /salute.
    if cfg.SENTINELLA_ATTIVA:
        print(f"         sentinella stop/target: prevista ogni {cfg.SENTINELLA_INTERVALLO_SEC}s")
    else:
        print("         sentinella stop/target: DISATTIVATA in configurazione - "
              "stop e target non sarebbero sorvegliati da nessuno")

    try:
        aperte = storage.posizioni_aperte()
        if aperte:
            print(f"         posizioni attualmente in archivio: {len(aperte)}")
    except Exception as errore:
        print(f"         archivio non leggibile: {errore!r}")

    if cfg.MODE == "auto":
        print()
        print("         >>> MODALITA' AUTO: il bot puo' operare da solo. <<<")
    print()


def main() -> int:
    """Esegue le tre prove e riassume il risultato."""
    configura_log()
    cfg = impostazioni()
    print("=" * 72)
    print("COLLAUDO IMPIANTO nvmfinancebot")
    print(f"modalita': {cfg.MODE}   archivio: {cfg.DB_PATH}   server: {indirizzo_base()}")
    print("=" * 72)
    print()

    quadro_operativo()

    risultati = {
        "1. MetaTrader 5 (broker)": esegui("1. MetaTrader 5 (broker)", prova_mt5),
        "2. Telegram (notifiche)": esegui("2. Telegram (notifiche)", prova_telegram),
        "3. Webhook (server + sicurezza)": esegui("3. Webhook (server + sicurezza)", prova_webhook),
    }

    broker.disconnetti()

    print("=" * 72)
    for nome, ok in risultati.items():
        print(f"  {'OK    ' if ok else 'ERRORE'}  {nome}")
    passate = sum(1 for ok in risultati.values() if ok)
    print(f"\n  {passate} collegamenti su {len(risultati)} funzionanti.")

    if passate == len(risultati):
        print("\n  Impianto in piedi. La strategia resta da scrivere:")
        print("  finche' core/strategy.py restituisce NONE, non verra' aperto nulla.")
    else:
        print("\n  Sistema quello che e' in ERRORE prima di andare avanti.")
    print("=" * 72)

    return 0 if passate == len(risultati) else 1


if __name__ == "__main__":
    sys.exit(main())
