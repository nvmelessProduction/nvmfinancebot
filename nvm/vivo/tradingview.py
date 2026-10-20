"""TradingView come fonte dei grafici, tramite il suo server MCP ufficiale (https://www.tradingview.com/mcp/docs).

Il proprietario, 12/10/2026: *"io voglio che la rete neurale analizzi il mercato su TradingView, sui pair che dico io,
dei broker che dico io, e operi su MetaTrader 5"*. Le condizioni di TradingView (sezione 3) vietano il trading
automatico sui loro dati senza un permesso scritto: finche' non arriva, il bot propone e decide una persona
(i pulsanti Apri / Lascia su Telegram, `vivo.py`).

- L'accesso e' quello del vostro account TradingView (OAuth 2.1): il primo login si fa una volta sulla VPS con
  `tradingview_accesso.bat`, poi il bot lo rinnova da solo. Le chiavi stanno in `dati/vivo/tradingview.json`, fuori
  dal repository, e non si stampano mai.
- Le candele arrivano con `get_ohlcv` (al massimo 5.000 per richiesta) e diventano le stesse `Minuti` che il bot
  leggeva da MT5: il resto del bot non cambia. Niente spread: i prezzi sono quelli che si vedono sul grafico.
- Se TradingView non risponde, si dice: il bot non torna mai di nascosto ai prezzi di MT5.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from nvm.dati.candele import Candele, weekend, calendario
from nvm.dati.minuti import PUNTO, Minuti
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import TF, fine_candela, inizio_candela, scarti_ny

SERVER = "https://mcp.tradingview.com/mcp"
EMITTENTE = "https://www.tradingview.com"
AUTORIZZA = EMITTENTE + "/mcp/oauth/authorize"
TOKEN = EMITTENTE + "/mcp/oauth/token"
REGISTRA = EMITTENTE + "/mcp/oauth/register"
AMBITO = "mcp:read mcp:tools"
PORTA = 8765
FILE = "tradingview.json"
VERSIONE_MCP = "2025-06-18"
# get_ohlcv da' al massimo 5.000 candele per richiesta.
MASSIMO = 5000
INTERVALLI = {900: "15m", 3600: "1h", 86400: "1D"}
# I timeframe che il bot prende da TradingView cosi' come sono, col nome dell'intervallo (il proprietario, 13/10/2026:
# *"non deve costruire niente ma utilizzare i dati con gli orari che gli vengono forniti così come sono"*; *"1h 4h 6h 12h
# 1d 1w 1m 3m 12m"*). La documentazione di TradingView elenca 1h, 4h, 1D, 1W e M; gli altri si chiedono lo stesso, e se
# TradingView non li da' (`RispostaRifiutata`) si mettono insieme le sue candele (le ore, i mesi) sulla sua stessa griglia
# (`foto.Quadro.da`).
INTERVALLI_TF = {TF.H1: "1h", TF.H4: "4h", TF.H6: "6h", TF.H12: "12h", TF.D1: "1D", TF.W1: "1W", TF.MN: "M",
                 TF.Q3: "3M", TF.S6: "6M", TF.Y1: "12M"}
# I timeframe con l'orario esatto della candela (gli altri si mettono all'apertura della loro sessione: `candele_tv`).
INTRADAY = (TF.H1, TF.H4, TF.H6, TF.H12)
# Quanto prima della scadenza si rinnova l'accesso.
MARGINE = 120
# Fra una richiesta e l'altra: TradingView ne dichiara circa 100 al minuto, ma con 35 grafici a 0,7 secondi ha
# chiesto di rallentare (12/10/2026): una al secondo. Se chiede di rallentare, si aspetta e si riprova.
INTERVALLO = 1.0
ATTESE_RALLENTA = (20, 60)
# Il grafico del dollaro, in punti come quello del bot (`nvm/agenti/foto.py`).
PUNTO.setdefault("DXY", 1e-3)
PUNTO.setdefault("TOTAL", 1e6)


class ErroreTradingView(RuntimeError):
    pass


class RispostaRifiutata(ErroreTradingView):
    """TradingView ha risposto, ma senza candele (un intervallo o un grafico che non da'): non e' un errore di rete."""


class AccessoScaduto(ErroreTradingView):
    """L'accesso non si rinnova piu': va rifatto il login con `tradingview_accesso.bat`."""


class QuotaFinita(ErroreTradingView):
    """TradingView non accetta piu' richieste fino a `fino_a`: la quota giornaliera dell'account e' finita (*"do not
    retry"*). Fino ad allora il bot non manda richieste: riprovarle non serve."""

    def __init__(self, testo: str, fino_a: float):
        super().__init__(testo)
        self.fino_a = float(fino_a)


# Dopo l'ora in cui TradingView azzera la quota (mezzanotte UTC) si aspetta ancora qualche minuto.
MARGINE_QUOTA = 120


def fine_quota(testo: str, adesso: float) -> Optional[float]:
    """Se `testo` dice che la quota giornaliera e' finita, quando si puo' ripartire: alla prossima ora UTC che dice
    (*"It resets at 00:00 UTC"*; se non la dice, mezzanotte UTC), piu' `MARGINE_QUOTA`. None se non e' la quota."""
    alto = testo.upper()
    if "QUOTA_EXCEEDED" not in alto and "QUOTA EXCEEDED" not in alto:
        return None
    m = re.search(r"resets at (\d{1,2}):(\d{2}) UTC", testo, re.IGNORECASE)
    ore, minuti_ = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    quando = datetime.fromtimestamp(adesso, timezone.utc).replace(hour=ore % 24, minute=minuti_ % 60, second=0,
                                                                 microsecond=0)
    if quando.timestamp() <= adesso:
        quando += timedelta(days=1)
    return quando.timestamp() + MARGINE_QUOTA


def _contesto():
    from nvm.vivo.telegram import contesto
    return contesto()


def _richiesta(url: str, dati: bytes, intestazioni: dict, timeout: float = 30.0):
    """Una POST; restituisce (codice, intestazioni, corpo). Gli errori di rete diventano `ErroreTradingView`, senza
    mai il contenuto della richiesta (ci sono le chiavi)."""
    r = urllib.request.Request(url, data=dati, headers=intestazioni, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=_contesto()) as risposta:
            return risposta.status, dict(risposta.headers), risposta.read()
    except urllib.error.HTTPError as errore:
        try:
            corpo = errore.read()
        except Exception:
            corpo = b""
        return errore.code, dict(errore.headers or {}), corpo
    except urllib.error.URLError as errore:
        raise ErroreTradingView(f"TradingView non raggiungibile: {errore.reason}") from None
    except (TimeoutError, OSError) as errore:
        raise ErroreTradingView(f"TradingView non raggiungibile: {type(errore).__name__}") from None


def _modulo(valori: dict) -> bytes:
    return urllib.parse.urlencode(valori).encode()


# --- l'accesso --------------------------------------------------------------------------------------------

class Accesso:
    """Le chiavi dell'account TradingView, nel file `cartella/tradingview.json`."""

    def __init__(self, cartella: Path, posta: Callable = _richiesta, orologio: Callable[[], float] = time.time):
        self.percorso = Path(cartella) / FILE
        self._posta = posta
        self._orologio = orologio
        self._dati: dict = {}
        self._letto = 0.0
        self._lucchetto = threading.Lock()
        self._ricarica()

    def _ricarica(self) -> None:
        """Rilegge il file se e' cambiato: il login rifatto con il bot acceso vale subito, senza riavviarlo."""
        try:
            quando = self.percorso.stat().st_mtime
        except OSError:
            return
        if quando != self._letto:
            self._dati = json.loads(self.percorso.read_text(encoding="utf-8"))
            self._letto = quando

    def __repr__(self) -> str:  # le chiavi non si stampano mai
        return f"Accesso({self.percorso.name}, {'pronto' if self.pronto else 'da fare'})"

    @property
    def pronto(self) -> bool:
        self._ricarica()
        return bool(self._dati.get("client_id") and self._dati.get("refresh_token"))

    def salva(self, dati: dict) -> None:
        self._dati = dict(dati)
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        provvisorio = self.percorso.with_suffix(".tmp")
        provvisorio.write_text(json.dumps(self._dati), encoding="utf-8")
        provvisorio.replace(self.percorso)
        self._letto = self.percorso.stat().st_mtime

    def _dai_token(self, risposta: dict) -> None:
        dati = dict(self._dati)
        dati["access_token"] = risposta["access_token"]
        # TradingView puo' dare un refresh token nuovo a ogni rinnovo: si tiene sempre l'ultimo.
        if risposta.get("refresh_token"):
            dati["refresh_token"] = risposta["refresh_token"]
        dati["scade"] = self._orologio() + float(risposta.get("expires_in", 3600))
        self.salva(dati)

    def token(self) -> str:
        with self._lucchetto:
            if not self.pronto:
                raise AccessoScaduto("manca l'accesso a TradingView: fai doppio clic su tradingview_accesso.bat")
            if not self._dati.get("access_token") or self._orologio() > float(self._dati.get("scade", 0)) - MARGINE:
                self._rinnova()
            return self._dati["access_token"]

    def rinnova(self) -> None:
        with self._lucchetto:
            self._rinnova()

    def _rinnova(self) -> None:
        codice, _, corpo = self._posta(TOKEN, _modulo({
            "grant_type": "refresh_token", "refresh_token": self._dati["refresh_token"],
            "client_id": self._dati["client_id"], "resource": SERVER}),
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if codice in (400, 401):
            raise AccessoScaduto("l'accesso a TradingView è scaduto: rifai il login con tradingview_accesso.bat")
        if codice != 200:
            raise ErroreTradingView(f"TradingView non rinnova l'accesso (risposta {codice})")
        self._dai_token(json.loads(corpo.decode("utf-8")))

    # Il primo accesso, una volta sola, dalla VPS.
    def primo_accesso(self, apri: Callable[[str], object] = webbrowser.open, porta: int = PORTA,
                      attesa: float = 600.0, stampa: Callable[[str], None] = print) -> None:
        ritorno = f"http://127.0.0.1:{porta}/callback"
        codice, _, corpo = self._posta(REGISTRA, json.dumps({
            "client_name": "NVM bot", "redirect_uris": [ritorno], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": AMBITO}).encode(),
            {"Content-Type": "application/json", "Accept": "application/json"})
        if codice not in (200, 201):
            raise ErroreTradingView(f"TradingView non registra il programma (risposta {codice})")
        client_id = json.loads(corpo.decode("utf-8"))["client_id"]
        verificatore = secrets.token_urlsafe(48)
        sfida = base64.urlsafe_b64encode(hashlib.sha256(verificatore.encode()).digest()).rstrip(b"=").decode()
        stato = secrets.token_urlsafe(16)
        indirizzo = AUTORIZZA + "?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": client_id, "redirect_uri": ritorno, "scope": AMBITO,
            "state": stato, "code_challenge": sfida, "code_challenge_method": "S256", "resource": SERVER})
        arrivato: dict = {}

        class Risposta(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - nome di http.server
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if urllib.parse.urlparse(self.path).path == "/callback":
                    arrivato.update({k: v[0] for k, v in q.items()})
                ok = "code" in arrivato and arrivato.get("state") == stato
                testo = ("Fatto: il bot e' collegato a TradingView. Puoi chiudere questa pagina." if ok else
                         "Qualcosa non e' andato: chiudi questa pagina e rifai il doppio clic.")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(testo.encode("utf-8"))

            def log_message(self, *a):  # niente righe sullo schermo (nell'indirizzo c'e' il codice)
                pass

        server = http.server.HTTPServer(("127.0.0.1", porta), Risposta)
        server.timeout = 1.0
        stampa("Si apre il browser: entra con il vostro account TradingView e premi \"Allow\" / \"Consenti\".")
        stampa("Se il browser non si apre, copia questo indirizzo nel browser della VPS:")
        stampa(indirizzo)
        apri(indirizzo)
        fine = time.monotonic() + attesa
        try:
            while "code" not in arrivato and "error" not in arrivato and time.monotonic() < fine:
                server.handle_request()
        finally:
            server.server_close()
        if "error" in arrivato:
            raise ErroreTradingView(f"TradingView ha rifiutato l'accesso: {arrivato.get('error')}")
        if arrivato.get("state") != stato or "code" not in arrivato:
            raise ErroreTradingView("il login non è arrivato in tempo: rifai il doppio clic")
        codice, _, corpo = self._posta(TOKEN, _modulo({
            "grant_type": "authorization_code", "code": arrivato["code"], "redirect_uri": ritorno,
            "client_id": client_id, "code_verifier": verificatore, "resource": SERVER}),
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        if codice != 200:
            raise ErroreTradingView(f"TradingView non ha dato l'accesso (risposta {codice})")
        risposta = json.loads(corpo.decode("utf-8"))
        if not risposta.get("refresh_token"):
            raise ErroreTradingView("TradingView non ha dato la chiave per rinnovare l'accesso da solo")
        self._dati = {"client_id": client_id}
        self._dai_token(risposta)


# --- il server MCP ------------------------------------------------------------------------------------------

def _messaggi(intestazioni: dict, corpo: bytes) -> list[dict]:
    """La risposta del server MCP: JSON, oppure eventi (text/event-stream) con il JSON nelle righe `data:`."""
    tipo = next((v for k, v in intestazioni.items() if k.lower() == "content-type"), "")
    testo = corpo.decode("utf-8", "replace").strip()
    if not testo:
        return []
    if "text/event-stream" in tipo:
        fuori, dati = [], []
        for riga in testo.splitlines() + [""]:
            if riga.startswith("data:"):
                dati.append(riga[5:].strip())
            elif not riga.strip() and dati:
                try:
                    fuori.append(json.loads("\n".join(dati)))
                except ValueError:
                    pass
                dati = []
        return fuori
    x = json.loads(testo)
    return x if isinstance(x, list) else [x]


def _barre(x) -> Optional[list]:
    """Le candele dentro la risposta di get_ohlcv: la prima lista di oggetti con t, o, h, l, c."""
    if isinstance(x, list):
        if x and all(isinstance(b, dict) and {"t", "o", "h", "l", "c"} <= set(b) for b in x[:3]):
            return x
        for v in x:
            trovate = _barre(v)
            if trovate is not None:
                return trovate
    elif isinstance(x, dict):
        for k in ("bars", "data", "candles", "ohlcv", "result"):
            if k in x:
                trovate = _barre(x[k])
                if trovate is not None:
                    return trovate
        for v in x.values():
            trovate = _barre(v)
            if trovate is not None:
                return trovate
    return None


class TradingView:
    """Le chiamate al server MCP di TradingView. Una sessione MCP, riaperta da sola se scade."""

    def __init__(self, accesso: Accesso, posta: Callable = _richiesta, server: str = SERVER,
                 intervallo: float = INTERVALLO, attese: tuple = ATTESE_RALLENTA, dormi: Callable = time.sleep,
                 orologio: Callable[[], float] = time.time):
        self.accesso = accesso
        self._posta = posta
        self._server = server
        self._intervallo = intervallo
        self._attese = attese
        self._dormi = dormi
        self._ultima = 0.0
        self._sessione: Optional[str] = None
        self._numero = 0
        self._lucchetto = threading.Lock()
        self._orologio = orologio
        # Fino a quando la quota giornaliera e' finita (0: non lo e'), e quante richieste di dati oggi (UTC).
        self.ferma_fino = 0.0
        self.chiamate_oggi = 0
        self._giorno = -1

    @property
    def ferma(self) -> bool:
        """La quota giornaliera e' finita e non e' ancora ripartita."""
        return self._orologio() < self.ferma_fino

    def _conta(self) -> None:
        giorno = int(self._orologio() // 86400)
        if giorno != self._giorno:
            self._giorno, self.chiamate_oggi = giorno, 0
        self.chiamate_oggi += 1

    def _manda(self, messaggio: dict) -> tuple[int, dict, bytes]:
        attesa = self._ultima + self._intervallo - time.monotonic()
        if attesa > 0:
            time.sleep(attesa)
        self._ultima = time.monotonic()
        intestazioni = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer " + self.accesso.token(), "MCP-Protocol-Version": VERSIONE_MCP}
        if self._sessione:
            intestazioni["Mcp-Session-Id"] = self._sessione
        return self._posta(self._server, json.dumps(messaggio).encode(), intestazioni)

    def _apri_sessione(self) -> None:
        self._sessione = None
        self._numero += 1
        codice, intestazioni, corpo = self._manda({
            "jsonrpc": "2.0", "id": self._numero, "method": "initialize",
            "params": {"protocolVersion": VERSIONE_MCP, "capabilities": {},
                       "clientInfo": {"name": "nvm-bot", "version": "1"}}})
        if codice == 401:
            self.accesso.rinnova()
            codice, intestazioni, corpo = self._manda({
                "jsonrpc": "2.0", "id": self._numero, "method": "initialize",
                "params": {"protocolVersion": VERSIONE_MCP, "capabilities": {},
                           "clientInfo": {"name": "nvm-bot", "version": "1"}}})
        if codice != 200:
            raise ErroreTradingView(f"TradingView non apre la sessione (risposta {codice})")
        self._sessione = next((v for k, v in intestazioni.items() if k.lower() == "mcp-session-id"), None)
        self._manda({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def chiama(self, nome: str, argomenti: dict) -> object:
        """Uno strumento del server (tools/call): il risultato, gia' letto dal JSON se e' JSON."""
        with self._lucchetto:
            if self.ferma:
                raise QuotaFinita(f"{nome}: la quota giornaliera di TradingView è finita", self.ferma_fino)
            if self._numero == 0:
                self._apri_sessione()
            rallentato = 0
            for tentativo in range(3 + len(self._attese)):
                self._numero += 1
                self._conta()
                codice, intestazioni, corpo = self._manda({
                    "jsonrpc": "2.0", "id": self._numero, "method": "tools/call",
                    "params": {"name": nome, "arguments": argomenti}})
                if codice == 401 and tentativo < 2:
                    self.accesso.rinnova()
                    continue
                if codice in (400, 404) and self._sessione and tentativo < 2:
                    # La sessione MCP e' scaduta: se ne apre una nuova.
                    self._apri_sessione()
                    continue
                if codice == 429:
                    if rallentato < len(self._attese):
                        self._dormi(self._attese[rallentato])
                        rallentato += 1
                        continue
                    raise ErroreTradingView("TradingView chiede di rallentare (troppe richieste)")
                if codice != 200:
                    raise ErroreTradingView(f"TradingView ha risposto {codice} a {nome}")
                return self._risultato(nome, _messaggi(intestazioni, corpo))
            raise ErroreTradingView(f"TradingView non risponde a {nome}")

    def _risultato(self, nome: str, messaggi: list[dict]) -> object:
        m = next((x for x in messaggi if x.get("id") == self._numero), None) or \
            next((x for x in messaggi if "result" in x or "error" in x), None)
        if m is None:
            raise ErroreTradingView(f"TradingView non ha dato una risposta a {nome}")
        if "error" in m:
            testo = str(m["error"].get("message", m["error"]))
            self._quota(nome, testo)
            raise ErroreTradingView(f"{nome}: {testo[:200]}")
        r = m.get("result") or {}
        testi = [c.get("text", "") for c in r.get("content", []) if c.get("type") == "text"]
        if r.get("isError"):
            self._quota(nome, " ".join(testi))
            raise ErroreTradingView(f"{nome}: {' '.join(testi)[:200]}")
        if r.get("structuredContent") is not None:
            return r["structuredContent"]
        for t in testi:
            try:
                return json.loads(t)
            except ValueError:
                continue
        return " ".join(testi)

    def _quota(self, nome: str, testo: str) -> None:
        """Se la risposta dice che la quota giornaliera e' finita: niente piu' richieste fino a quando riparte."""
        fino = fine_quota(testo, self._orologio())
        if fino is not None:
            self.ferma_fino = fino
            raise QuotaFinita(f"{nome}: {testo[:200]}", fino)

    def candele(self, simbolo: str, passo, quante: int) -> list[dict]:
        """Le candele di `simbolo`: `passo` in secondi (`INTERVALLI`) o il nome dell'intervallo ("4h", "1W", "M")."""
        intervallo = passo if isinstance(passo, str) else INTERVALLI[passo]
        try:
            r = self.chiama("get_ohlcv", {"symbol": simbolo, "interval": intervallo, "count": int(min(quante, MASSIMO))})
        except QuotaFinita:
            raise
        except ErroreTradingView as errore:
            if str(errore).startswith("get_ohlcv:"):
                raise RispostaRifiutata(f"{simbolo} {intervallo}: {str(errore)[11:]}") from None
            raise
        barre = _barre(r)
        if barre is None:
            testo = r if isinstance(r, str) else json.dumps(r)[:300]
            raise RispostaRifiutata(f"{simbolo} {intervallo}: risposta senza candele ({testo[:300]})")
        return barre


def minuti(strumento: str, barre: list[dict], passo: int, adesso: float) -> Minuti:
    """Le candele di TradingView come `Minuti` del bot, solo quelle gia' chiuse, in punti. Le giornaliere si mettono
    all'apertura della loro giornata (le 17 di New York; le crypto a mezzanotte UTC), come quelle di MT5: se
    TradingView ne da' due per la stessa giornata (la domenica), diventano una."""
    if not barre:
        return Minuti.vuoti(strumento, passo)
    t = np.array([int(b["t"]) for b in barre], np.int64)
    t = np.where(t > 10**11, t // 1000, t)            # millisecondi, se mai arrivassero cosi'
    prezzi = np.array([[float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])] for b in barre])
    volume = np.array([float(b.get("v") or 0.0) for b in barre])
    if passo >= 86400:
        t = inizio_candela(t, TF.D1, calendario(strumento))
    else:
        t = t - t % passo
    ordine = np.argsort(t, kind="stable")
    t, prezzi, volume = t[ordine], prezzi[ordine], volume[ordine]
    nuove = np.flatnonzero(np.r_[True, t[1:] != t[:-1]])
    ultime = np.r_[nuove[1:] - 1, len(t) - 1]
    ohlc = np.c_[prezzi[nuove, 0], np.maximum.reduceat(prezzi[:, 1], nuove), np.minimum.reduceat(prezzi[:, 2], nuove),
                 prezzi[ultime, 3]]
    t, volume = t[nuove], np.add.reduceat(volume, nuove)
    chiuse = t + passo <= adesso
    punti = np.rint(ohlc[chiuse] / PUNTO[strumento]).astype(np.int64)
    v = volume[chiuse].astype(np.float32)
    return Minuti(strumento, t[chiuse], punti, punti.copy(), v, v.copy(), passo=passo)


def ora_di_sessione(inizi) -> object:
    """Il calendario di un grafico di TradingView, dalle sue candele a 4 ore: partono dall'apertura della sessione ogni
    4 ore, quindi l'ora di New York della partenza dice la sessione ("17" come MT5, "18" come i future, "19", "20").
    True se seguono l'UTC (0, 4, 8... UTC tutto l'anno), None se non si capisce. Basta il 98% delle candele: un
    giorno di festa con orari strani non cambia niente."""
    t = np.asarray(inizi, np.int64)
    if len(t) < 6 or np.mean(t % 3600 == 0) < 0.98:
        return None
    t = t[t % 3600 == 0]
    resti_ny = (((t + scarti_ny(t)) // 3600) % 24) % 4
    valori, quanti = np.unique(resti_ny, return_counts=True)
    if quanti.max() >= 0.98 * len(t):
        return {1: "17", 2: "18", 3: "19", 0: "20"}[int(valori[np.argmax(quanti)])]
    if np.mean((t // 3600) % 4 == 0) >= 0.98:
        return True
    return None


def candele_tv(strumento: str, tf: TF, barre: list[dict], adesso: float) -> Candele:
    """Le candele di TradingView di un timeframe come `Candele` del bot, cosi' come sono: i prezzi e gli orari di
    TradingView, solo quelle gia' chiuse. Per giorno, settimana e mese TradingView puo' segnare la candela con la data
    (la mezzanotte UTC) invece che con l'apertura della sessione: si mette all'apertura della sua sessione, per sapere
    di che giorno e'; i prezzi non si toccano. Se due candele cadono nella stessa (la domenica sera del giorno dopo),
    diventano una."""
    cal = calendario(strumento)
    if not barre:
        vuoto = np.empty(0, np.int64)
        return Candele(strumento, tf, vuoto, vuoto, np.empty((0, 4)), np.empty((0, 4)), np.empty(0))
    t = np.array([int(b["t"]) for b in barre], np.int64)
    t = np.where(t > 10**11, t // 1000, t)            # millisecondi, se mai arrivassero cosi'
    prezzi = np.array([[float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])] for b in barre])
    volume = np.array([float(b.get("v") or 0.0) for b in barre])
    if tf not in INTRADAY:
        t = inizio_candela(t, tf, cal)
    ordine = np.argsort(t, kind="stable")
    t, prezzi, volume = t[ordine], prezzi[ordine], volume[ordine]
    nuove = np.flatnonzero(np.r_[True, t[1:] != t[:-1]])
    ultime = np.r_[nuove[1:] - 1, len(t) - 1]
    ohlc = np.c_[prezzi[nuove, 0], np.maximum.reduceat(prezzi[:, 1], nuove), np.minimum.reduceat(prezzi[:, 2], nuove),
                 prezzi[ultime, 3]]
    t, volume = t[nuove], np.add.reduceat(volume, nuove)
    if tf is TF.H1:
        fine = t + 3600
    else:
        fine = np.fromiter((fine_candela(int(i), tf, cal) for i in t), np.int64, count=len(t))
    chiuse = fine <= adesso
    return Candele(strumento, tf, t[chiuse], fine[chiuse], ohlc[chiuse], ohlc[chiuse].copy(), volume[chiuse])


# --- i grafici scelti dal proprietario ----------------------------------------------------------------------

def leggi_simboli(testo: str) -> tuple[list[tuple[str, str]], list[str]]:
    """«OANDA:EURUSD, OANDA:US30USD=US30»: (simbolo di TradingView, strumento del bot), e quelli che non si
    capiscono. Lo strumento e' il nome dopo i due punti, se il bot lo conosce; se no va scritto dopo l'uguale."""
    fuori, sbagliati = [], []
    for pezzo in testo.replace(";", ",").replace(" ", ",").split(","):
        pezzo = pezzo.strip()
        if not pezzo:
            continue
        simbolo, _, nome = pezzo.partition("=")
        simbolo = simbolo.strip().upper()
        nome = (nome.strip() or simbolo.split(":")[-1]).upper()
        if ":" not in simbolo or nome not in STRUMENTI:
            sbagliati.append(pezzo)
            continue
        if any(n == nome for _, n in fuori):
            # Lo stesso strumento due volte farebbe due proposte per lo stesso setup: vale il primo.
            continue
        fuori.append((simbolo, nome))
    return fuori, sbagliati


class Fonte:
    """Le candele per il bot da TradingView, con gli stessi nomi del terminale MT5 (`orarie`, `barre`,
    `giornaliere`, `esiste`): il bot le chiede a lei invece che a MT5."""

    def __init__(self, tv: TradingView, simboli: list[tuple[str, str]], dxy: str = "", totale: str = "",
                 orologio: Callable[[], float] = time.time):
        self.tv = tv
        self.simboli = {nome: simbolo for simbolo, nome in simboli}
        if dxy:
            self.simboli["DXY"] = dxy.upper()
        if totale:
            self.simboli["TOTAL"] = totale.upper()
        self._orologio = orologio

    def simbolo(self, strumento: str) -> str:
        return self.simboli[strumento]

    def esiste(self, strumento: str) -> bool:
        return strumento in self.simboli

    def barre(self, strumento: str, quante: int, passo: int) -> Minuti:
        if strumento not in self.simboli:
            raise ErroreTradingView(f"{strumento} non è fra i grafici scelti su TradingView")
        # Una in piu': l'ultima e' quella in formazione e non si usa.
        b = self.tv.candele(self.simboli[strumento], passo, quante + 1)
        return minuti(strumento, b, passo, self._orologio())

    def orarie(self, strumento: str, quante: int) -> Minuti:
        return self.barre(strumento, quante, 3600)

    def giornaliere(self, strumento: str, quante: int) -> Minuti:
        return self.barre(strumento, quante, 86400)

    def grezze(self, strumento: str, tf: TF, quante: int) -> list[dict]:
        """Le candele di `tf` cosi' come le da' TradingView (una in piu': l'ultima e' quella in formazione)."""
        if strumento not in self.simboli:
            raise ErroreTradingView(f"{strumento} non è fra i grafici scelti su TradingView")
        return self.tv.candele(self.simboli[strumento], INTERVALLI_TF[tf], quante + 1)
