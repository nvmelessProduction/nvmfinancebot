"""Prezzi SPOT (quello che il CFD replica), invece del future continuo.

## L'ipotesi

Il future continuo e' incollato: quando il contratto rotola, la serie fa un
gradino che il mercato non ha mai scambiato. Quei gradini diventano massimi e
minimi finti, cioe' **key level finti e sweep finti**. Un modello che vive
sulla liquidita' vera li mangia come se fossero reali.

Lo spot non rotola. Se il CRT funziona meglio sullo spot, i rollover erano
rumore che abbiamo dato in pasto al motore per tutto il tempo.

`DEF-32` ed `ESCL-12` vietano di analizzare sul CFD, ed e' una regola scritta
dando per scontato che il future sia "il prezzo vero". Questa misura serve
proprio a verificare quel presupposto.
"""
from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

import httpx

from core.definizioni import Candela

TICKER = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X",
          "USDCHF": "USDCHF=X", "USDJPY": "USDJPY=X"}
RADICE = "https://query1.finance.yahoo.com/v8/finance/chart/"
CAPO = {"User-Agent": "nvmfinancebot/1.0 (ricerca, non commerciale)"}
CACHE = Path("spot.pickle")


def scarica(ticker: str, **parametri):
    r = httpx.get(RADICE + ticker, headers=CAPO, timeout=60, params=parametri)
    r.raise_for_status()
    d = r.json()["chart"]["result"][0]
    t, q = d["timestamp"], d["indicators"]["quote"][0]
    fuori, riparate, scartate = [], 0, 0
    for i in range(len(t) - 1):          # l'ultima non ha chiusura nota (DEF-02)
        if any(q[c][i] is None for c in ("open", "high", "low", "close")):
            scartate += 1
            continue
        apertura, chiusura = float(q["open"][i]), float(q["close"][i])
        alto, basso = float(q["high"][i]), float(q["low"][i])
        if alto < basso:
            scartate += 1               # barra che si contraddice: irrecuperabile
            continue
        # Stessa riparazione di `importa_storico.estremi_coerenti`: il massimo
        # non puo' stare sotto un prezzo scambiato nello stesso periodo. Non si
        # inventa un prezzo, si sceglie fra quelli che la fonte ha dichiarato.
        nuovo_alto, nuovo_basso = max(alto, apertura, chiusura), min(basso, apertura, chiusura)
        if (nuovo_alto, nuovo_basso) != (alto, basso):
            riparate += 1
        fuori.append(Candela(datetime.fromtimestamp(t[i + 1], timezone.utc),
                             apertura, nuovo_alto, nuovo_basso, chiusura))
    return tuple(fuori), riparate, scartate


def tutto() -> dict:
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    adesso = int(datetime.now(timezone.utc).timestamp())
    fuori = {}
    for nome, ticker in TICKER.items():
        serie, note = {}, []
        for etichetta, par in (("D1", dict(interval="1d", period1=0, period2=adesso)),
                               ("W1", dict(interval="1wk", period1=0, period2=adesso)),
                               ("H1", dict(interval="1h", range="730d"))):
            s, riparate, scartate = scarica(ticker, **par)
            serie[etichetta] = s
            note.append(f"{etichetta} {len(s):5d} (rip. {riparate:4d}, scart. {scartate:3d})")
        fuori[nome] = serie
        print(f"  {nome:8s} " + "  ".join(note), flush=True)
    CACHE.write_bytes(pickle.dumps(fuori))
    return fuori


if __name__ == "__main__":
    tutto()
