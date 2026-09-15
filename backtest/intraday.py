"""Scarica le barre fini che servono alle coppie di Romeo non ancora provate.

La fonte gratuita copre 60 giorni a 15 e 5 minuti, 7 giorni a 1 minuto. E'
poco, e va detto: sessanta giorni sono **un solo regime di mercato**. Il
campione di operazioni e' grande, la varieta' di condizioni no.

`Candela.orario` e' la CHIUSURA (DEF-02) e la fonte marca l'APERTURA: la
chiusura della barra `i` e' l'apertura della barra `i+1`, e l'ultima si
scarta perche' non ha un successore e quindi non e' chiusa (ESCL-13).
"""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

import httpx

from core.definizioni import Candela

TICKER = {"XAUUSD": "GC=F", "EURUSD": "6E=F", "GBPUSD": "6B=F",
          "AUDUSD": "6A=F", "USDCHF": "6S=F", "USDJPY": "6J=F"}
RADICE = "https://query1.finance.yahoo.com/v8/finance/chart/"
INTESTAZIONE = {"User-Agent": "nvmfinancebot/1.0 (ricerca, non commerciale)"}
CACHE = Path("intraday.pickle")


def scarica(ticker: str, intervallo: str, finestra: str) -> tuple[Candela, ...]:
    risposta = httpx.get(RADICE + ticker, headers=INTESTAZIONE, timeout=60,
                         params={"interval": intervallo, "range": finestra})
    risposta.raise_for_status()
    dati = risposta.json()["chart"]["result"][0]
    tempi = dati["timestamp"]
    q = dati["indicators"]["quote"][0]

    fuori: list[Candela] = []
    for i in range(len(tempi) - 1):          # l'ultima non ha chiusura nota
        if any(q[c][i] is None for c in ("open", "high", "low", "close")):
            continue
        alto, basso = float(q["high"][i]), float(q["low"][i])
        if alto < basso:
            continue
        fuori.append(Candela(
            orario=datetime.fromtimestamp(tempi[i + 1], timezone.utc),
            apertura=float(q["open"][i]), massimo=alto, minimo=basso,
            chiusura=float(q["close"][i]),
        ))
    return tuple(fuori)


def tutto(intervalli=(("15m", "60d"), ("5m", "60d"))) -> dict:
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    fuori: dict = {}
    for strumento, ticker in TICKER.items():
        fuori[strumento] = {}
        for intervallo, finestra in intervalli:
            serie = scarica(ticker, intervallo, finestra)
            fuori[strumento][intervallo] = serie
            print(f"  {strumento:8s} {intervallo:4s} {len(serie):6d} barre", flush=True)
    CACHE.write_bytes(pickle.dumps(fuori))
    return fuori


if __name__ == "__main__":
    tutto()
