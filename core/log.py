"""Diario di bordo: un solo posto in cui si decide dove finiscono i messaggi.

Console e file, con rotazione. Il file serve per il dopo: quando un ordine
va storto alle 3 di notte, la console non c'e' piu' ma il file si'.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from core.config import impostazioni

_configurato: bool = False

FORMATO: str = "%(asctime)s %(levelname)-8s %(name)-16s %(message)s"


def configura() -> None:
    """Imposta i gestori di log. Chiamarla una volta sola, all'avvio."""
    global _configurato
    if _configurato:
        return

    cfg = impostazioni()
    livello = getattr(logging, cfg.LOG_LIVELLO.upper(), logging.INFO)

    radice = logging.getLogger()
    radice.setLevel(livello)

    formattatore = logging.Formatter(FORMATO)

    a_console = logging.StreamHandler(sys.stdout)
    a_console.setFormatter(formattatore)
    radice.addHandler(a_console)

    try:
        a_file = RotatingFileHandler(
            cfg.LOG_FILE,
            maxBytes=cfg.LOG_MAX_BYTE,
            backupCount=cfg.LOG_COPIE,
            encoding="utf-8",
        )
        a_file.setFormatter(formattatore)
        radice.addHandler(a_file)
    except OSError as errore:
        # Disco pieno o permessi: si continua con la sola console, ma lo diciamo.
        radice.warning("impossibile aprire il file di log %s: %r", cfg.LOG_FILE, errore)

    # Librerie chiacchierone: httpx registra ogni singola richiesta HTTP, e
    # ogni notifica Telegram diventerebbe due righe di log inutili.
    for rumorosa in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(rumorosa).setLevel(logging.WARNING)

    _configurato = True


def diario(nome: str) -> logging.Logger:
    """Restituisce il logger di un modulo."""
    return logging.getLogger(nome)
