

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
FOTO = "https://api.telegram.org/bot{token}/sendPhoto"
AGGIORNAMENTI = "https://api.telegram.org/bot{token}/getUpdates"
RISPOSTA_TASTO = "https://api.telegram.org/bot{token}/answerCallbackQuery"
CAMBIA_TESTO = "https://api.telegram.org/bot{token}/editMessageText"


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
    # Un pulsante premuto sotto un messaggio del bot (Apri / Lascia): cosa dice il pulsante, il numero da dare a
    # Telegram per rispondere, il messaggio e il suo testo, e chi l'ha premuto.
    tasto: str = ""
    id_tasto: str = ""
    messaggio: int = 0
    originale: str = ""
    chi: str = ""
    # Un messaggio scritto in risposta a un messaggio del bot: il numero di quel messaggio.
    risposta_a: int = 0


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
        invia_come: Optional[Callable[[str, str, str], None]] = None,
        invia_foto: Optional[Callable[[str, bytes, str], None]] = None,
        posta: Optional[Callable[[str, dict], None]] = None,
    ):
        self._imp = imp
        self._invia = invia or self._http
        # Per le voci degli agenti col loro bot: (token, chat, testo).
        self._invia_come = invia_come or self._http_come
        self._invia_foto = invia_foto or self._http_foto
        # Le chiamate a Telegram che non sono messaggi (pulsanti, testi cambiati): (indirizzo, dati).
        self._posta = posta or self._http_posta
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

    def ricevi(self, dal: int, attesa: int = 0) -> tuple[list[Ricevuto], int]:
        """I messaggi arrivati dal numero `dal` in poi, solo dai canali del bot,
        e il numero da cui ripartire. Chiunque altro scriva al bot non conta.
        Se Telegram non risponde, lo dice l'errore: chi chiama decide."""
        if not self._imp.token:
            return [], dal
        miei = set(self._imp.chat_operativo) | set(self._imp.chat_equipe)
        arrivati, prossimo = [], dal
        # `attesa`: quanti secondi Telegram tiene aperta la richiesta se non c'e' niente (risposta appena arriva).
        for u in (self._prendi(dal, attesa) if attesa else self._prendi(dal)):
            prossimo = max(prossimo, int(u["update_id"]) + 1)
            q = u.get("callback_query")
            if q:
                m = q.get("message") or {}
                chat = str(m.get("chat", {}).get("id", ""))
                if chat in miei and q.get("data"):
                    chi = q.get("from", {})
                    arrivati.append(Ricevuto(int(u["update_id"]), chat, "", int(m.get("date", 0)), tasto=q["data"],
                                             id_tasto=str(q.get("id", "")), messaggio=int(m.get("message_id", 0)),
                                             originale=m.get("text", ""),
                                             chi=chi.get("first_name") or chi.get("username") or ""))
                continue
            m = u.get("message") or u.get("channel_post") or {}
            chat, testo = str(m.get("chat", {}).get("id", "")), m.get("text", "")
            if chat in miei and testo:
                chi = m.get("from", {})
                arrivati.append(Ricevuto(int(u["update_id"]), chat, testo, int(m.get("date", 0)),
                                         risposta_a=int((m.get("reply_to_message") or {}).get("message_id", 0)),
                                         chi=chi.get("first_name") or m.get("author_signature") or ""))
        return arrivati, prossimo

    def foto(self, canale: str, dati: bytes, didascalia: str = "") -> None:
        """Una foto (il grafico coi disegni) sul canale "operativo" o "equipe"."""
        chat = self._imp.chat_operativo if canale == "operativo" else self._imp.chat_equipe
        self._stampa(f"[{canale}] 📸 {didascalia}")
        if not self._imp.token:
            return
        for c in chat:
            if self._in_coda:
                self._coda.put((canale, c, (dati, didascalia[:1000]), None))
            else:
                self._spedisci(canale, c, (dati, didascalia[:1000]), None)

    def operativo(self, testo: str) -> None:
        self._manda("operativo", self._imp.chat_operativo, testo)

    def proposta(self, testo: str, tasti: list[tuple[str, str]], canale: str = "operativo") -> None:
        """Un messaggio sul canale `canale` con dei pulsanti sotto (testo del pulsante, cosa manda al bot)."""
        self._stampa(f"[{canale}] {testo}  " + "  ".join(f"[{t}]" for t, _ in tasti))
        if not self._imp.token:
            return
        pezzo = {"testo": testo[:LUNGHEZZA], "tasti": [[{"text": t, "callback_data": d} for t, d in tasti]]}
        chat = self._imp.chat_operativo if canale == "operativo" else self._imp.chat_equipe
        for c in chat:
            if self._in_coda:
                self._coda.put((canale, c, pezzo, None))
            else:
                self._spedisci(canale, c, pezzo, None)

    def subito(self, chat: str, testo: str, righe: Optional[list] = None, risposta_a: int = 0) -> int:
        """Un messaggio mandato subito, senza coda, con righe di pulsanti [[(testo, dato), ...], ...]; restituisce il
        suo numero (0 se non e' partito). Serve quando il bot deve sapere quale messaggio e' (Correggi)."""
        self._stampa(f"[{chat}] {testo}")
        if not self._imp.token:
            return 0
        dati = {"chat_id": chat, "text": testo[:LUNGHEZZA], "disable_web_page_preview": True}
        if righe:
            dati["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in righe]}
        if risposta_a:
            dati["reply_to_message_id"] = risposta_a
        try:
            r = self._posta(URL, dati)
        except Exception:
            return 0
        return int((r or {}).get("message_id", 0)) if isinstance(r, dict) else 0

    def rispondi_tasto(self, id_tasto: str, testo: str = "") -> None:
        """La risposta a un pulsante premuto (la scritta che compare un attimo sul telefono). Subito, senza coda."""
        if not self._imp.token or not id_tasto:
            return
        try:
            self._posta(RISPOSTA_TASTO, {"callback_query_id": id_tasto, "text": testo[:190]})
        except Exception:
            pass

    def chiudi_tasti(self, chat: str, messaggio: int, testo: str, righe: Optional[list] = None) -> None:
        """Cambia il testo di un messaggio gia' mandato e ne toglie i pulsanti (com'e' finita), o li rimette nuovi
        (`righe`, come in `subito`). Subito, senza coda."""
        self._stampa(f"[{chat}] (messaggio {messaggio}) {testo}")
        if not self._imp.token or not messaggio:
            return
        dati = {"chat_id": chat, "message_id": messaggio, "text": testo[:LUNGHEZZA], "disable_web_page_preview": True}
        if righe:
            dati["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in righe]}
        try:
            self._posta(CAMBIA_TESTO, dati)
        except Exception:
            pass

    def equipe(self, testo: str) -> None:
        self._manda("equipe", self._imp.chat_equipe, testo)

    def voci(self, voci: list, tema: str = "") -> None:
        """Gli agenti che parlano in equipe (`conversazione.Voce`). Chi ha il suo bot parla con
        quello, come un collega in una chat; senza bot propri, un messaggio solo con tutte le voci.
        `tema`: di quale operazione si parla (strumento e verso). Ogni messaggio comincia da li': con piu'
        operazioni insieme si sa sempre di che asset si parla (il proprietario, 07/10/2026: *"in NvmFinance bot
        equipe non si capisce mai di che asset parla"*)."""
        if not voci:
            return
        testa = f"📌 {tema}\n" if tema else ""
        if not any(v.chi in self._imp.voci for v in voci):
            self.equipe(testa + "\n".join(v.riga() for v in voci))
            return
        for v in voci:
            token = self._imp.voci.get(v.chi)
            self._manda("equipe", self._imp.chat_equipe, testa + (v.testo if token else v.riga()), token, v.chi)

    def _manda(self, canale: str, chat: tuple[str, ...], testo: str, token: Optional[str] = None,
               chi: str = "") -> None:
        self._stampa(f"[{canale}{' · ' + chi if token else ''}] {testo}")
        if not self._imp.token:
            return
        for c in chat:
            for pezzo in _pezzi(testo):
                if self._in_coda:
                    self._coda.put((canale, c, pezzo, token))
                else:
                    self._spedisci(canale, c, pezzo, token)

    def _spedisci(self, canale: str, chat: str, pezzo, token: Optional[str] = None) -> None:
        # Telegram conta i messaggi per bot e per gruppo: ogni bot ha il suo ritmo.
        chiave = (token or "", chat)
        attesa = self._ultimo.get(chiave, -1e9) + self._intervallo - time.monotonic()
        if attesa > 0:
            time.sleep(attesa)
        for n in range(self._tentativi):
            try:
                if isinstance(pezzo, tuple):
                    self._invia_foto(chat, *pezzo)
                elif isinstance(pezzo, dict):
                    self._posta(URL, {"chat_id": chat, "text": pezzo["testo"], "disable_web_page_preview": True,
                                      "reply_markup": {"inline_keyboard": pezzo["tasti"]}})
                elif token:
                    self._invia_come(token, chat, pezzo)
                else:
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
        self._ultimo[chiave] = time.monotonic()

    def _lavora(self) -> None:
        while True:
            canale, chat, pezzo, token = self._coda.get()
            try:
                self._spedisci(canale, chat, pezzo, token)
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

    def _aggiornamenti(self, dal: int, attesa: int = 0) -> list[dict]:
        dati = json.dumps({"offset": dal, "timeout": int(attesa),
                           "allowed_updates": ["message", "channel_post", "callback_query"]}).encode()
        richiesta = urllib.request.Request(
            AGGIORNAMENTI.format(token=self._imp.token), data=dati, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(richiesta, timeout=20 + attesa, context=contesto()) as r:
                risposta = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as errore:
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None
        return risposta.get("result", [])

    def _http_foto(self, chat: str, dati: bytes, didascalia: str) -> None:
        confine = "nvm" + str(int(time.time() * 1000))
        parti = []
        for nome, valore in (("chat_id", chat), ("caption", didascalia)):
            parti.append(f'--{confine}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valore}\r\n'.encode("utf-8"))
        parti.append(f'--{confine}\r\nContent-Disposition: form-data; name="photo"; filename="grafico.png"\r\n'
                     f'Content-Type: image/png\r\n\r\n'.encode("utf-8") + dati + b"\r\n")
        parti.append(f"--{confine}--\r\n".encode("utf-8"))
        richiesta = urllib.request.Request(FOTO.format(token=self._imp.token), data=b"".join(parti),
                                           headers={"Content-Type": f"multipart/form-data; boundary={confine}"})
        try:
            with urllib.request.urlopen(richiesta, timeout=60, context=contesto()) as r:
                r.read()
        except urllib.error.HTTPError as errore:
            if errore.code == 429:
                raise TroppiMessaggi(30.0) from None
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None

    def _http(self, chat: str, testo: str) -> None:
        self._http_come(self._imp.token, chat, testo)

    def _http_posta(self, indirizzo: str, dati: dict) -> Optional[dict]:
        richiesta = urllib.request.Request(indirizzo.format(token=self._imp.token), data=json.dumps(dati).encode(),
                                           headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(richiesta, timeout=20, context=contesto()) as r:
                risposta = json.loads(r.read().decode("utf-8") or "{}")
                return risposta.get("result") if isinstance(risposta.get("result"), dict) else None
        except urllib.error.HTTPError as errore:
            if errore.code == 429:
                raise TroppiMessaggi(30.0) from None
            # Il messaggio d'errore di urllib contiene l'indirizzo, e l'indirizzo il token.
            raise RuntimeError(f"Telegram ha risposto {errore.code}") from None
        except urllib.error.URLError as errore:
            raise RuntimeError(f"Telegram non raggiungibile: {errore.reason}") from None

    def _http_come(self, token: str, chat: str, testo: str) -> None:
        dati = json.dumps({"chat_id": chat, "text": testo, "disable_web_page_preview": True}).encode()
        richiesta = urllib.request.Request(
            URL.format(token=token), data=dati, headers={"Content-Type": "application/json"},
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
