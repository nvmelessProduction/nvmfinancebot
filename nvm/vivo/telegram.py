"""I due canali: operativo (avvio, aperture col perche', chiusure, allarmi) ed
equipe (gli agenti che si parlano, e la riunione del fine settimana).

Senza token i messaggi finiscono solo sullo schermo. Un messaggio che non
parte non ferma mai il bot: si riprova qualche volta, poi si va avanti.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from nvm.vivo.ambiente import Impostazioni

URL = "https://api.telegram.org/bot{token}/sendMessage"
AGGIORNAMENTI = "https://api.telegram.org/bot{token}/getUpdates"


def contesto() -> ssl.SSLContext:
    """Il controllo dei certificati, sempre acceso, con l'elenco di Windows piu'
    quello di `certifi`: su una VPS appena installata a Windows puo' mancare il
    certificato radice di Telegram (e' successo il 24/09/2026)."""
    c = ssl.create_default_context()
    try:
        import certifi
        c.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return c
LUNGHEZZA = 4000  # Telegram ne accetta 4096


def _pezzi(testo: str) -> list[str]:
    pezzi, corrente = [], ""
    for riga in testo.split("\n"):
        if len(corrente) + len(riga) + 1 > LUNGHEZZA and corrente:
            pezzi.append(corrente)
            corrente = ""
        corrente = f"{corrente}\n{riga}" if corrente else riga
    return pezzi + [corrente] if corrente else pezzi


@dataclass
class Ricevuto:
    """Un messaggio arrivato al bot da uno dei suoi canali."""

    numero: int      # l'update_id di Telegram: il prossimo da chiedere e' numero + 1
    chat: str
    testo: str
    quando: int      # UTC
    # Il testo del messaggio a cui questo risponde, se risponde a qualcosa (per /errore sulla scheda).
    risposta: str = ""


class Telegram:
    def __init__(
        self, imp: Impostazioni,
        invia: Optional[Callable[[str, str], None]] = None,
        stampa: Callable[[str], None] = print, tentativi: int = 3,
        prendi: Optional[Callable[[int], list[dict]]] = None,
    ):
        self._imp = imp
        self._invia = invia or self._http
        self._prendi = prendi or self._aggiornamenti
        self._stampa = stampa
        self._tentativi = tentativi

    def ricevi(self, dal: int) -> tuple[list[Ricevuto], int]:
        """I messaggi arrivati dal numero `dal` in poi, solo dai canali del bot,
        e il numero da cui ripartire. Chiunque altro scriva al bot non conta.
        Se Telegram non risponde, lo dice l'errore: chi chiama decide."""
        if not self._imp.token:
            return [], dal
        miei = set(self._imp.chat_operativo) | set(self._imp.chat_equipe)
        arrivati, prossimo = [], dal
        for u in self._prendi(dal):
            prossimo = max(prossimo, int(u["update_id"]) + 1)
            m = u.get("message") or u.get("channel_post") or {}
            chat, testo = str(m.get("chat", {}).get("id", "")), m.get("text", "")
            if chat in miei and testo:
                risposta = (m.get("reply_to_message") or {}).get("text", "")
                arrivati.append(Ricevuto(int(u["update_id"]), chat, testo, int(m.get("date", 0)), risposta))
        return arrivati, prossimo

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

    def _aggiornamenti(self, dal: int) -> list[dict]:
        dati = json.dumps({"offset": dal, "timeout": 0, "allowed_updates": ["message", "channel_post"]}).encode()
        richiesta = urllib.request.Request(
            AGGIORNAMENTI.format(token=self._imp.token), data=dati, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(richiesta, timeout=20, context=contesto()) as r:
                risposta = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as errore:
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None
        return risposta.get("result", [])

    def _http(self, chat: str, testo: str) -> None:
        dati = json.dumps({"chat_id": chat, "text": testo, "disable_web_page_preview": True}).encode()
        richiesta = urllib.request.Request(
            URL.format(token=self._imp.token), data=dati, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(richiesta, timeout=20, context=contesto()) as r:
                r.read()
        except urllib.error.HTTPError as errore:
            # Il messaggio d'errore di urllib contiene l'indirizzo, e l'indirizzo il token.
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None
