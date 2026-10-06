"""Il terminale MT5: le orarie del broker e gli ordini, solo su conto demo.

Due cose che il vecchio progetto ha pagato care e che qui si fanno subito
giuste:

- **MT5 marca le barre con l'orologio del server**, non con UTC, e le
  consegna come se fossero UTC. Lo scarto (da noi +2 d'inverno, +3 d'estate)
  si misura solo quando il tick **avanza**: a mercato chiuso il tick e'
  fermo, e la differenza con l'ora vera cresce di un'ora ogni ora.
- **Le 4 ore e le giornaliere di MT5 seguono il calendario del server**, non
  quello delle prove (New York alle 17). Si chiedono solo le orarie, e tutto
  il resto si ricostruisce con lo stesso codice delle prove sullo storico.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import PUNTO, Minuti
from nvm.dati.strumenti import STRUMENTI

# Lo scarto del server del broker rispetto a UTC, in ore: i valori credibili.
SCARTI_CREDIBILI = range(0, 5)


class ErroreMT5(RuntimeError):
    pass


@dataclass
class Conto:
    login: int
    server: str
    demo: bool
    saldo: float
    valuta: str
    trading_permesso: bool


@dataclass
class Esito:
    ok: bool
    messaggio: str
    ticket: int = 0
    prezzo: float = 0.0
    volume: float = 0.0


# Le risposte piu' comuni di MT5 a un ordine, in parole.
_SPIEGAZIONI = {
    10018: "mercato chiuso: si riprova alla prossima apertura",
    10027: "MT5 non permette al bot di operare: accendi il pulsante \"Algo Trading\" in alto nel terminale",
    10014: "volume non accettato dal broker",
    10016: "stop o target non accettati dal broker",
    10019: "margine non sufficiente",
    10030: "modo di esecuzione non accettato dal broker",
    10017: "trading disabilitato su questo simbolo",
}


class Terminale:
    def __init__(self, suffisso: str = "", mt5: Any = None, dormi=time.sleep, orologio=time.time):
        if mt5 is None:
            try:
                import MetaTrader5 as mt5  # esiste solo su Windows
            except ImportError as errore:
                raise ErroreMT5("manca MetaTrader5: il bot dal vivo gira solo su Windows, accanto al terminale") from errore
        self.mt5 = mt5
        self.suffisso = suffisso
        self.scarto: Optional[int] = None
        self._ultimo_tick: dict[str, int] = {}
        # Il nome che il broker usa per ogni strumento, trovato da `esiste`.
        self._nomi: dict[str, str] = {}
        self._dormi = dormi
        self._orologio = orologio

    # --- collegamento e conto -------------------------------------------------

    def connetti(self) -> None:
        if not self.mt5.initialize():
            raise ErroreMT5(f"MT5 non si collega: {self.mt5.last_error()}. Il terminale e' aperto e collegato al conto?")

    def conto(self) -> Conto:
        a, t = self.mt5.account_info(), self.mt5.terminal_info()
        if a is None or t is None:
            raise ErroreMT5(f"MT5 non da' le informazioni del conto: {self.mt5.last_error()}")
        return Conto(
            login=int(a.login), server=str(a.server),
            demo=a.trade_mode == self.mt5.ACCOUNT_TRADE_MODE_DEMO,
            saldo=float(a.balance), valuta=str(a.currency),
            trading_permesso=bool(t.trade_allowed) and bool(a.trade_allowed) and bool(getattr(a, "trade_expert", True)),
        )

    def simbolo(self, strumento: str) -> str:
        return self._nomi.get(strumento, strumento + self.suffisso)

    def esiste(self, strumento: str) -> bool:
        """Il broker ha questo strumento su questo conto? Si provano il nome del bot e gli altri
        nomi con cui i broker lo chiamano (`nvm/dati/strumenti.py`), col suffisso e senza; il
        primo che il conto ha diventa il suo nome."""
        s = STRUMENTI.get(strumento)
        nomi = [strumento] + list(s.mt5 if s is not None else ())
        for nome in dict.fromkeys([n + self.suffisso for n in nomi] + nomi):
            try:
                if self.mt5.symbol_select(nome, True) and self.mt5.symbol_info(nome) is not None:
                    self._nomi[strumento] = nome
                    return True
            except Exception:
                continue
        return False

    def tutti_i_simboli(self) -> list[tuple[str, str, str]]:
        """Tutti gli strumenti che il broker offre: (nome, cartella, descrizione), come nella finestra
        «Simboli» di MT5."""
        simboli = self.mt5.symbols_get() or ()
        fuori = []
        for s in simboli:
            fuori.append((str(getattr(s, "name", "")), str(getattr(s, "path", "") or ""),
                          str(getattr(s, "description", "") or "")))
        return sorted(fuori, key=lambda x: (x[1].lower(), x[0]))

    # --- l'ora del server -----------------------------------------------------

    def misura_scarto(self, strumento: str, attesa: float = 30.0) -> Optional[int]:
        """Guarda il tick finche' avanza (al massimo `attesa` secondi) e misura lo scarto."""
        simbolo = self.simbolo(strumento)
        self.mt5.symbol_select(simbolo, True)
        fine = self._orologio() + attesa
        while True:
            self._scarto_dal_tick(simbolo)
            if self.scarto is not None or self._orologio() >= fine:
                return self.scarto
            self._dormi(1.0)

    def _scarto_dal_tick(self, simbolo: str) -> None:
        tick = self.mt5.symbol_info_tick(simbolo)
        if tick is None or not getattr(tick, "time", 0):
            return
        ora = int(tick.time)
        prima = self._ultimo_tick.get(simbolo)
        self._ultimo_tick[simbolo] = ora
        if prima is None or ora == prima:
            return  # primo sguardo, o mercato fermo: il tick non dice che ore sono
        ore = round((ora - self._orologio()) / 3600)
        if ore in SCARTI_CREDIBILI:
            self.scarto = ore

    # --- le orarie ------------------------------------------------------------

    def orarie(self, strumento: str, quante: int) -> Minuti:
        return self.barre(strumento, quante, 3600)

    def barre(self, strumento: str, quante: int, passo: int) -> Minuti:
        """Le barre gia' chiuse (orarie o da 15 minuti), in UTC, con bid e ask in punti come nelle prove."""
        simbolo = self.simbolo(strumento)
        if not self.mt5.symbol_select(simbolo, True):
            raise ErroreMT5(f"il simbolo {simbolo} non c'e' su questo conto: {self.mt5.last_error()}")
        self._scarto_dal_tick(simbolo)
        if self.scarto is None:
            raise ErroreMT5("non so ancora l'ora del server: aspetto che il mercato si muova")
        tf = {3600: self.mt5.TIMEFRAME_H1, 900: self.mt5.TIMEFRAME_M15, 86400: self.mt5.TIMEFRAME_D1}[passo]
        barre = self.mt5.copy_rates_from_pos(simbolo, tf, 0, quante)
        if barre is None or len(barre) == 0:
            raise ErroreMT5(f"nessuna barra da {passo // 60} minuti per {simbolo}: {self.mt5.last_error()}")
        info = self.mt5.symbol_info(simbolo)
        t = np.asarray(barre["time"], np.int64) - self.scarto * 3600
        adesso = int(self._orologio())
        chiuse = t + passo <= adesso  # l'ultima e' ancora in formazione
        barre, t = barre[chiuse], t[chiuse]
        punto = PUNTO[strumento]
        bid = np.rint(np.c_[barre["open"], barre["high"], barre["low"], barre["close"]] / punto).astype(np.int64)
        spread = np.rint(np.asarray(barre["spread"], np.float64) * float(info.point) / punto).astype(np.int64)
        ask = bid + spread[:, None]
        volume = np.asarray(barre["tick_volume"], np.float32)
        return Minuti(strumento, t, bid, ask, volume, volume.copy(), passo=passo)

    def giornaliere(self, strumento: str, quante: int) -> Minuti:
        """Le candele giornaliere di tanti anni, per i 3, 6 e 12 mesi del metodo delle foto. Il broker le apre
        alle 17 di New York; le nostre candele aprono alle 18 (`nvm/tempo.py`): si spostano di un'ora, cosi'
        ogni giornata cade nel suo giorno di sessione."""
        m = self.barre(strumento, quante, 86400)
        return Minuti(strumento, m.t + 3600, m.bid, m.ask, m.volume_bid, m.volume_ask, passo=86400)

    # --- gli ordini -----------------------------------------------------------

    def prezzo(self, strumento: str) -> tuple[float, float]:
        tick = self.mt5.symbol_info_tick(self.simbolo(strumento))
        if tick is None:
            raise ErroreMT5(f"nessun prezzo per {strumento}: {self.mt5.last_error()}")
        return float(tick.bid), float(tick.ask)

    def perdita_per_lotto(self, strumento: str, verso: Verso, ingresso: float, stop: float) -> float:
        """Quanto costa lo stop con un lotto, nella valuta del conto."""
        simbolo = self.simbolo(strumento)
        tipo = self.mt5.ORDER_TYPE_SELL if verso is Verso.SHORT else self.mt5.ORDER_TYPE_BUY
        perdita = self.mt5.order_calc_profit(tipo, simbolo, 1.0, ingresso, stop)
        if perdita is None or perdita == 0:
            raise ErroreMT5(f"non riesco a calcolare il valore di un lotto su {simbolo}: {self.mt5.last_error()}")
        return abs(float(perdita))

    def lotti(self, strumento: str) -> tuple[float, float, float]:
        """Lotto minimo, passo e massimo."""
        info = self.mt5.symbol_info(self.simbolo(strumento))
        return float(info.volume_min), float(info.volume_step), float(info.volume_max)

    def distanza_minima(self, strumento: str) -> float:
        info = self.mt5.symbol_info(self.simbolo(strumento))
        return float(info.trade_stops_level) * float(info.point)

    def _riempimento(self, simbolo: str) -> int:
        maschera = int(getattr(self.mt5.symbol_info(simbolo), "filling_mode", 0))
        if maschera & 1:
            return self.mt5.ORDER_FILLING_FOK
        if maschera & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def apri(self, strumento: str, verso: Verso, volume: float, stop: float, target: float, magic: int, commento: str) -> Esito:
        simbolo = self.simbolo(strumento)
        cifre = int(self.mt5.symbol_info(simbolo).digits)
        bid, ask = self.prezzo(strumento)
        short = verso is Verso.SHORT
        richiesta = {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": simbolo, "volume": float(volume),
            "type": self.mt5.ORDER_TYPE_SELL if short else self.mt5.ORDER_TYPE_BUY,
            "price": bid if short else ask, "sl": round(stop, cifre), "tp": round(target, cifre),
            "deviation": 20, "magic": magic, "comment": commento[:31],
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self._riempimento(simbolo),
        }
        r = self.mt5.order_send(richiesta)
        if r is None:
            return Esito(False, f"ordine senza risposta: {self.mt5.last_error()}")
        if r.retcode != self.mt5.TRADE_RETCODE_DONE:
            return Esito(False, f"ordine rifiutato: codice {r.retcode} {getattr(r, 'comment', '')}")
        return Esito(True, "aperta", ticket=int(r.order), prezzo=float(r.price), volume=float(r.volume))

    def prova_ordine(self, strumento: str, magic: int) -> Esito:
        """Chiede a MT5 di controllare un ordine minimo, senza mandarlo: se il
        broker lo accetterebbe, il collegamento per aprire funziona."""
        simbolo = self.simbolo(strumento)
        if not self.mt5.symbol_select(simbolo, True):
            return Esito(False, f"il simbolo {simbolo} non c'è su questo conto")
        info = self.mt5.symbol_info(simbolo)
        tick = self.mt5.symbol_info_tick(simbolo)
        if info is None or tick is None:
            return Esito(False, f"MT5 non dà prezzi per {simbolo}: {self.mt5.last_error()}")
        cifre = int(info.digits)
        ask = float(tick.ask)
        # Stop e target larghi (1% e 2% del prezzo), ben oltre la distanza minima del broker.
        richiesta = {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": simbolo, "volume": float(info.volume_min),
            "type": self.mt5.ORDER_TYPE_BUY, "price": ask,
            "sl": round(ask * 0.99, cifre), "tp": round(ask * 1.02, cifre),
            "deviation": 20, "magic": magic, "comment": "nvm prova collegamento",
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self._riempimento(simbolo),
        }
        r = self.mt5.order_check(richiesta)
        if r is None:
            return Esito(False, f"MT5 non risponde al controllo: {self.mt5.last_error()}")
        if int(r.retcode) in (0, self.mt5.TRADE_RETCODE_DONE):
            return Esito(True, f"il broker accetterebbe {float(info.volume_min):g} lotti", volume=float(info.volume_min))
        return Esito(False, _SPIEGAZIONI.get(int(r.retcode), f"codice {r.retcode}") + f" ({getattr(r, 'comment', '')})")

    def sposta_stop(self, strumento: str, ticket: int, stop: float, target: float) -> Esito:
        simbolo = self.simbolo(strumento)
        cifre = int(self.mt5.symbol_info(simbolo).digits)
        r = self.mt5.order_send({
            "action": self.mt5.TRADE_ACTION_SLTP, "symbol": simbolo, "position": int(ticket),
            "sl": round(stop, cifre), "tp": round(target, cifre),
        })
        if r is None or r.retcode != self.mt5.TRADE_RETCODE_DONE:
            return Esito(False, f"stop non spostato: {getattr(r, 'retcode', None)} {self.mt5.last_error()}")
        return Esito(True, "stop spostato")

    def chiudi_posizione(self, strumento: str, ticket: int) -> Esito:
        """Chiude una posizione a mercato: le uscite prima dello stop che gli agenti hanno imparato."""
        posizioni = self.mt5.positions_get(ticket=int(ticket))
        if not posizioni:
            return Esito(True, "già chiusa")
        p = posizioni[0]
        simbolo = self.simbolo(strumento)
        bid, ask = self.prezzo(strumento)
        compra = int(p.type) == self.mt5.ORDER_TYPE_SELL
        r = self.mt5.order_send({
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": simbolo, "volume": float(p.volume),
            "type": self.mt5.ORDER_TYPE_BUY if compra else self.mt5.ORDER_TYPE_SELL, "position": int(ticket),
            "price": ask if compra else bid, "deviation": 20, "magic": int(p.magic), "comment": "nvm uscita",
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self._riempimento(simbolo),
        })
        if r is None or r.retcode != self.mt5.TRADE_RETCODE_DONE:
            return Esito(False, f"chiusura rifiutata: {getattr(r, 'retcode', None)} {self.mt5.last_error()}")
        return Esito(True, "chiusa", prezzo=float(r.price))

    def aperte(self, magic: int) -> set[int]:
        """I ticket delle posizioni del bot ancora aperte."""
        posizioni = self.mt5.positions_get()
        if posizioni is None:
            raise ErroreMT5(f"MT5 non da' le posizioni: {self.mt5.last_error()}")
        return {int(p.ticket) for p in posizioni if int(p.magic) == magic}

    def chiusura(self, ticket: int) -> tuple[float, float]:
        """Profitto netto (con commissioni e swap) e prezzo d'uscita di una posizione chiusa."""
        affari = self.mt5.history_deals_get(position=int(ticket))
        if not affari:
            raise ErroreMT5(f"nessuna chiusura trovata per la posizione {ticket}")
        netto = sum(float(d.profit) + float(d.commission) + float(d.swap) for d in affari)
        uscita = [d for d in affari if int(d.entry) == self.mt5.DEAL_ENTRY_OUT]
        return netto, (float(uscita[-1].price) if uscita else 0.0)
