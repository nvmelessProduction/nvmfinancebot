"""I due canali: operativo (avvio, aperture col perche', chiusure, allarmi) ed
equipe (gli agenti che si parlano, e la riunione del fine settimana).

Senza token i messaggi finiscono solo sullo schermo. Un messaggio che non
parte non ferma mai il bot: si riprova qualche volta, poi si va avanti.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from nvm.vivo.ambiente import Impostazioni

URL = "https://api.telegram.org/bot{token}/sendMessage"
LUNGHEZZA = 4000  # Telegram ne accetta 4096


def _pezzi(testo: str) -> list[str]:
    pezzi, corrente = [], ""
    for riga in testo.split("\n"):
        if len(corrente) + len(riga) + 1 > LUNGHEZZA and corrente:
            pezzi.append(corrente)
            corrente = ""
        corrente = f"{corrente}\n{riga}" if corrente else riga
    return pezzi + [corrente] if corrente else pezzi


class Telegram:
    def __init__(
        self, imp: Impostazioni,
        invia: Optional[Callable[[str, str], None]] = None,
        stampa: Callable[[str], None] = print, tentativi: int = 3,
    ):
        self._imp = imp
        self._invia = invia or self._http
        self._stampa = stampa
        self._tentativi = tentativi

    def operativo(self, testo: str) -> None:
        self._manda("operativo", self._imp.chat_operativo, testo)

    def equipe(self, testo: str) -> None:
        self._manda("equipe", self._imp.chat_equipe, testo)

    def _manda(self, canale: str, chat: tuple[str, ...], testo: str) -> None:
        self._stampa(f"[{canale}] {testo}")
        if not self._imp.token:
            return
        for c in chat:
            for pezzo in _pezzi(testo):
                for n in range(self._tentativi):
                    try:
                        self._invia(c, pezzo)
                        break
                    except Exception as errore:  # la rete non deve mai fermare il bot
                        if n == self._tentativi - 1:
                            self._stampa(f"[{canale}] messaggio non partito: {errore}")
                        else:
                            time.sleep(2 ** n)

    def _http(self, chat: str, testo: str) -> None:
        dati = json.dumps({"chat_id": chat, "text": testo, "disable_web_page_preview": True}).encode()
        richiesta = urllib.request.Request(
            URL.format(token=self._imp.token), data=dati, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(richiesta, timeout=20) as r:
                r.read()
        except urllib.error.HTTPError as errore:
            # Il messaggio d'errore di urllib contiene l'indirizzo, e l'indirizzo il token.
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None
