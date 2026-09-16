"""Legge i file gia' in cache e costruisce i timeframe. Nessun download."""
import lzma, pickle, struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from core.definizioni import Candela

DEP = Path("dukascopy"); CACHE = Path("duka_serie.pickle")
SCALA = {"USDJPY": 1e3, "XAUUSD": 1e3}
SIMBOLI = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD"]

def _orarie(sim, lato):
    s = SCALA.get(sim, 1e5); fuori = []
    for f in sorted(DEP.glob(f"{sim}_*_{lato}_candles_hour_1.bi5")):
        p = f.name.split("_"); anno, mm = int(p[1]), int(p[2])
        if not f.stat().st_size: continue
        try: d = lzma.LZMADecompressor().decompress(f.read_bytes())
        except lzma.LZMAError: continue
        ini = datetime(anno, mm + 1, 1, tzinfo=timezone.utc)
        for i in range(0, len(d) - 23, 24):
            sec, o, c, l, h, v = struct.unpack(">I4If", d[i:i+24])
            if v <= 0 and o == c == l == h: continue
            o, c, l, h = o/s, c/s, l/s, h/s
            if not (l <= min(o, c) and h >= max(o, c)): continue
            fuori.append(Candela(ini + timedelta(seconds=sec) + timedelta(hours=1), o, h, l, c))
    fuori.sort(key=lambda x: x.orario)
    return tuple(fuori)

def _giorno(m):
    c = m.replace(hour=22, minute=0, second=0, microsecond=0)
    return c + timedelta(days=1) if m > c else c

def _gruppi(candele, chiave):
    g = {}
    for c in candele: g.setdefault(chiave(c), []).append(c)
    return tuple(Candela(v[-1].orario, v[0].apertura, max(x.massimo for x in v),
                         min(x.minimo for x in v), v[-1].chiusura)
                 for k, v in sorted(g.items())[:-1])

def costruisci(orarie):
    d1 = _gruppi(orarie, lambda c: _giorno(c.orario))
    return {
        "H1": orarie,
        "H4": _gruppi(orarie, lambda c: ((c.orario-timedelta(microseconds=1)).date(),
                                         (c.orario-timedelta(microseconds=1)).hour // 4)),
        "D1": d1,
        "W1": _gruppi(d1, lambda c: (c.orario-timedelta(microseconds=1)).isocalendar()[:2]),
        "M1": _gruppi(d1, lambda c: ((c.orario-timedelta(microseconds=1)).year,
                                     (c.orario-timedelta(microseconds=1)).month)),
    }

def tutto():
    if CACHE.exists(): return pickle.loads(CACHE.read_bytes())
    fuori = {}
    for s in SIMBOLI:
        b, a = _orarie(s, "BID"), _orarie(s, "ASK")
        fuori[s] = {"BID": costruisci(b), "ASK": costruisci(a)}
        print(f"  {s:8s} BID {len(b):7,} orarie  ASK {len(a):7,}  "
              f"D1 {len(fuori[s]['BID']['D1']):6,}  W1 {len(fuori[s]['BID']['W1']):5,}", flush=True)
    CACHE.write_bytes(pickle.dumps(fuori))
    return fuori

if __name__ == "__main__":
    tutto()
