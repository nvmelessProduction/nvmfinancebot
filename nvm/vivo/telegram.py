"""I due canali: operativo (avvio, aperture col perche', chiusure, allarmi) ed
equipe (gli agenti che si parlano, e la riunione del fine settimana).

Senza token i messaggi finiscono solo sullo schermo. Un messaggio che non
parte non ferma mai il bot: si riprova qualche volta, poi si va avanti.
"""

from __future__ import annotations

import atexit
import json
import queue
import ssl
import threading
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


SEPARATORE = "\n\n〰〰〰\n\n"


def raggruppa(testi: list[str], massimo: int = LUNGHEZZA) -> list[str]:
    """Piu' messaggi in pochi: si mettono insieme finche' stanno in un messaggio di Telegram,
    senza mai spezzarne uno a meta' (se uno da solo e' troppo lungo, lo spezza `_pezzi`)."""
    gruppi, corrente = [], ""
    for t in testi:
        if corrente and len(corrente) + len(SEPARATORE) + len(t) > massimo:
            gruppi.append(corrente)
            corrente = ""
        corrente = f"{corrente}{SEPARATORE}{t}" if corrente else t
    return gruppi + [corrente] if corrente else gruppi


@dataclass
class Ricevuto:
    """Un messaggio arrivato al bot da uno dei suoi canali."""

    numero: int      # l'update_id di Telegram: il prossimo da chiedere e' numero + 1
    chat: str
    testo: str
    quando: int      # UTC


class TroppiMessaggi(RuntimeError):
    """Telegram chiede di aspettare (risposta 429): `dopo` secondi."""

    def __init__(self, dopo: float):
        super().__init__(f"Telegram chiede di aspettare {dopo:g} secondi")
        self.dopo = dopo


# Telegram accetta circa 20 messaggi al minuto nello stesso gruppo: uno ogni tre secondi abbondanti.
INTERVALLO = 3.1


class Telegram:
    """Con Telegram vero i messaggi partono da una coda, su un filo a parte e al ritmo che
    Telegram accetta: il bot non aspetta mai Telegram per decidere o per aprire ordini.
    Con un `invia` dato (le prove, il bot finto) partono subito, uno dopo l'altro."""

    def __init__(
        self, imp: Impostazioni,
        invia: Optional[Callable[[str, str], None]] = None,
        stampa: Callable[[str], None] = print, tentativi: int = 3,
        prendi: Optional[Callable[[int], list[dict]]] = None,
        intervallo: float = INTERVALLO, in_coda: Optional[bool] = None,
    ):
        self._imp = imp
        self._invia = invia or self._http
        self._prendi = prendi or self._aggiornamenti
        self._stampa = stampa
        self._tentativi = tentativi
        self._in_coda = (invia is None and bool(imp.token)) if in_coda is None else in_coda and bool(imp.token)
        self._intervallo = intervallo if self._in_coda else 0.0
        self._ultimo: dict[str, float] = {}
        self._coda: queue.Queue = queue.Queue()
        if self._in_coda:
            threading.Thread(target=self._lavora, name="telegram", daemon=True).start()
            # Prima di uscire (anche per l'aggiornamento) si prova a spedire quello che resta.
            atexit.register(self.svuota)

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
                arrivati.append(Ricevuto(int(u["update_id"]), chat, testo, int(m.get("date", 0))))
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
                if self._in_coda:
                    self._coda.put((canale, c, pezzo))
                else:
                    self._spedisci(canale, c, pezzo)

    def _spedisci(self, canale: str, chat: str, pezzo: str) -> None:
        attesa = self._ultimo.get(chat, -1e9) + self._intervallo - time.monotonic()
        if attesa > 0:
            time.sleep(attesa)
        for n in range(self._tentativi):
            try:
                self._invia(chat, pezzo)
                break
            except TroppiMessaggi as errore:
                if n == self._tentativi - 1:
                    self._stampa(f"[{canale}] messaggio non partito: {errore}")
                else:
                    time.sleep(errore.dopo)
            except Exception as errore:  # la rete non deve mai fermare il bot
                if n == self._tentativi - 1:
                    self._stampa(f"[{canale}] messaggio non partito: {errore}")
                else:
                    time.sleep(2 ** n)
        self._ultimo[chat] = time.monotonic()

    def _lavora(self) -> None:
        while True:
            canale, chat, pezzo = self._coda.get()
            try:
                self._spedisci(canale, chat, pezzo)
            except Exception:
                pass
            finally:
                self._coda.task_done()

    def svuota(self, massimo: float = 60.0) -> bool:
        """Aspetta che la coda sia spedita, al massimo `massimo` secondi. Vero se e' vuota."""
        fine = time.monotonic() + massimo
        while self._coda.unfinished_tasks and time.monotonic() < fine:
            time.sleep(0.1)
        return not self._coda.unfinished_tasks

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
            if errore.code == 429:
                try:
                    dopo = float(json.loads(errore.read().decode("utf-8"))["parameters"]["retry_after"])
                except Exception:
                    dopo = 30.0
                raise TroppiMessaggi(dopo) from None
            # Il messaggio d'errore di urllib contiene l'indirizzo, e l'indirizzo il token.
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None
