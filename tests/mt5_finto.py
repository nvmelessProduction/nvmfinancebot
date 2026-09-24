"""Un terminale MT5 finto, con le sole funzioni che il bot usa.

Le barre e i tick sono in ora del server (UTC + `scarto` ore), come nel
terminale vero. `chiudi` fa quello che farebbe il broker a stop o target.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np

BARRA = np.dtype([("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                  ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])


class MT5Finto:
    TIMEFRAME_H1, TIMEFRAME_M15 = 16385, 15
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_REAL = 0, 2
    TRADE_ACTION_DEAL, TRADE_ACTION_SLTP = 1, 6
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TRADE_RETCODE_DONE = 10009
    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1

    def __init__(self, scarto: int = 3, saldo: float = 1000.0, demo: bool = True):
        self.scarto = scarto
        self.saldo = saldo
        self.demo = demo
        self.barre: dict[str, np.ndarray] = {}
        self.tick: dict[str, NS] = {}
        self.posizioni: dict[int, NS] = {}
        self.affari: dict[int, list[NS]] = {}
        self.richieste: list[dict] = []
        self._ticket = 1000

    # --- quello che il bot chiama ---
    def initialize(self, **_):
        return True

    def last_error(self):
        return (1, "tutto bene")

    def account_info(self):
        return NS(login=123, server="Demo-Finto", trade_mode=0 if self.demo else 2, balance=self.saldo,
                  currency="EUR", trade_allowed=True, trade_expert=True)

    def terminal_info(self):
        return NS(trade_allowed=True)

    def symbol_select(self, simbolo, _):
        return simbolo in self.tick

    def symbol_info(self, simbolo):
        oro = simbolo.startswith("XAU")
        return NS(point=0.01 if oro else 1e-5, digits=2 if oro else 5, volume_min=0.01, volume_step=0.01,
                  volume_max=100.0, trade_stops_level=0, filling_mode=1)

    def symbol_info_tick(self, simbolo):
        return self.tick.get(simbolo)

    def copy_rates_from_pos(self, simbolo, tf, inizio, quante):
        b = self.barre.get(simbolo if tf == self.TIMEFRAME_H1 else (simbolo, tf))
        return None if b is None else b[max(0, len(b) - quante):]

    def order_calc_profit(self, tipo, simbolo, volume, apertura, chiusura):
        contratto = 100 if simbolo.startswith("XAU") else 100000
        return (chiusura - apertura) * contratto * volume * (1 if tipo == self.ORDER_TYPE_BUY else -1)

    def order_check(self, r):
        # Controlla soltanto: non apre niente.
        return NS(retcode=0, comment="Done")

    def order_send(self, r):
        self.richieste.append(dict(r))
        if r["action"] == self.TRADE_ACTION_DEAL:
            self._ticket += 1
            self.posizioni[self._ticket] = NS(ticket=self._ticket, magic=r["magic"], symbol=r["symbol"], type=r["type"],
                                              volume=r["volume"], price_open=r["price"], sl=r["sl"], tp=r["tp"])
            return NS(retcode=self.TRADE_RETCODE_DONE, order=self._ticket, price=r["price"], volume=r["volume"])
        p = self.posizioni[r["position"]]
        p.sl, p.tp = r["sl"], r["tp"]
        return NS(retcode=self.TRADE_RETCODE_DONE, order=0, price=0.0, volume=0.0)

    def positions_get(self):
        return list(self.posizioni.values())

    def history_deals_get(self, position):
        return self.affari.get(position, [])

    # --- per le prove ---
    def chiudi(self, ticket: int, prezzo: float) -> float:
        p = self.posizioni.pop(ticket)
        profitto = self.order_calc_profit(p.type, p.symbol, p.volume, p.price_open, prezzo)
        self.affari[ticket] = [
            NS(entry=self.DEAL_ENTRY_IN, price=p.price_open, profit=0.0, commission=0.0, swap=0.0),
            NS(entry=self.DEAL_ENTRY_OUT, price=prezzo, profit=profitto, commission=0.0, swap=0.0),
        ]
        self.saldo += profitto
        return profitto
