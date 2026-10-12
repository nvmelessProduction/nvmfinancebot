"""Prepara le lezioni della pagina di disegno: per ogni istante scelto, le candele di tutti i timeframe fino a quell'istante
(l'ultima e' quella in formazione, come su MT5 e TradingView in quel momento), niente futuro.

    python prepara.py CARTELLA_HD CARTELLA_M1 casi.npz USCITA

- giorno, settimana, mese, 3, 6, 12 mesi: `costruisci` del bot sulle ore (giorno dalle 17 di New York);
- dal minuto alle 12 ore: blocchi dalle 17 di New York (come MT5 di FP), dai minuti fino a 45 minuti, dalle ore sopra.
I tempi delle candele intraday sono in ora italiana; quelli dal giorno in su sono la data del giorno di borsa.
"""

import io
import json
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nvm.dati.candele import costruisci  # noqa: E402
from nvm.dati.minuti import MASSIMO, MINIMO, Minuti  # noqa: E402
from nvm.dati.ore import carica  # noqa: E402
from nvm.tempo import TF, scarti_ny, utc  # noqa: E402
from kaggle_rete.histdata import _ultima_domenica  # noqa: E402

ROMA = ZoneInfo("Europe/Rome")
NY = ZoneInfo("America/New_York")
INTRA = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "45m": 2700,
         "1h": 3600, "2h": 7200, "3h": 10800, "4h": 14400, "6h": 21600, "12h": 43200}
LUNGHI = {"1D": TF.D1, "1W": TF.W1, "1M": TF.MN, "3M": TF.Q3, "6M": TF.S6, "12M": TF.Y1}
QUANTE = 600          # candele intraday per timeframe
PUNTO = 1e-5


def minuti_da_zip(percorso: Path) -> tuple[np.ndarray, np.ndarray]:
    """I minuti di HistData (bid) con l'orario corretto (ora legale europea), in UTC."""
    z = zipfile.ZipFile(percorso)
    nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    testo = z.read(nome).decode("ascii", "replace")
    testo = re.sub(r"(\d{8}) (\d{6})", r"\1;\2", testo).replace(" ", "")
    a = np.loadtxt(io.StringIO(testo), delimiter=";", ndmin=2, usecols=range(6))
    d, hhmmss = a[:, 0].astype(np.int64), a[:, 1].astype(np.int64)
    mesi = (d // 10000 - 1970) * 12 + (d // 100) % 100 - 1
    giorno = mesi.astype("datetime64[M]").astype("datetime64[D]") + (d % 100 - 1)
    sec = giorno.astype("datetime64[s]").astype(np.int64) + hhmmss // 10000 * 3600 + (hhmmss // 100) % 100 * 60
    anni = giorno.astype("datetime64[Y]").astype(int) + 1970
    estate = np.zeros(len(d), bool)
    for y in np.unique(anni):
        sel = anni == y
        estate[sel] = (giorno[sel] >= np.datetime64(_ultima_domenica(int(y), 3))) & \
                      (giorno[sel] < np.datetime64(_ultima_domenica(int(y), 10)))
    t = sec + np.where(estate, 4, 5) * 3600
    o = np.argsort(t, kind="stable")
    return t[o], a[o, 2:6]


def blocchi(t: np.ndarray, p: np.ndarray, passo: int) -> tuple[np.ndarray, np.ndarray]:
    """Candele di `passo` secondi dalle 17 di New York (anche fra un'ora legale e l'altra)."""
    loc = t + scarti_ny(t)
    inizio_loc = (loc - 17 * 3600) // passo * passo + 17 * 3600
    inizio = inizio_loc - (loc - t)
    nuove = np.flatnonzero(np.r_[True, inizio[1:] != inizio[:-1]])
    ultime = np.r_[nuove[1:] - 1, len(t) - 1]
    ohlc = np.c_[p[nuove, 0], np.maximum.reduceat(p[:, 1], nuove), np.minimum.reduceat(p[:, 2], nuove), p[ultime, 3]]
    return inizio[nuove], ohlc


def ora_italiana(t: np.ndarray) -> list[int]:
    """Lightweight Charts mostra i tempi come UTC: si sposta ogni tempo dello scarto di Roma."""
    import datetime as dt
    return [int(x) + int(dt.datetime.fromtimestamp(int(x), ROMA).utcoffset().total_seconds()) for x in t]


def giorno_di_borsa(t: np.ndarray) -> list[str]:
    """La data del giorno di borsa: la candela che apre alle 17 di New York e' del giorno dopo."""
    import datetime as dt
    return [(dt.datetime.fromtimestamp(int(x), NY) + timedelta(hours=7)).strftime("%Y-%m-%d") for x in t]


def pacchetto(tempi, ohlc) -> dict:
    return {"t": tempi, "p": np.rint(np.asarray(ohlc) / PUNTO).astype(np.int64).ravel().tolist()}


def _minuti(t, p) -> Minuti:
    punti = np.rint(np.asarray(p) / PUNTO).astype(np.int64)
    z = np.zeros(len(t), np.float32)
    return Minuti("EURUSD", np.asarray(t, np.int64), punti, punti.copy(), z, z.copy(), 60)


def _senza_weekend(t, p):
    """Fuori le barre fra la chiusura del venerdi' e la riapertura della domenica (17 di New York): il bot le
    sposta sulla candela della domenica, qui (solo per i timeframe che il bot non ha) si lasciano fuori."""
    import datetime as dt
    loc = t + scarti_ny(t)
    g = ((loc // 86400) + 3) % 7          # 0 lunedi' ... 4 venerdi', 5 sabato, 6 domenica
    ora = loc % 86400
    fuori = ((g == 4) & (ora >= 17 * 3600)) | (g == 5) | ((g == 6) & (ora < 17 * 3600))
    return t[~fuori], p[~fuori]


def lezione(ore: Minuti, m1_t, m1_p, T: int) -> dict:
    fuori = {}
    k = np.searchsorted(m1_t, T)
    a = np.searchsorted(m1_t, T - 2700 * QUANTE * 3)
    mt, mp = m1_t[a:k], m1_p[a:k]
    m = _minuti(mt, mp)
    h = ore.fra(0, T)
    bot = {"1m": (m, TF.M1), "5m": (m, TF.M5), "15m": (m, TF.M15),
           "1h": (h, TF.H1), "4h": (h, TF.H4), "6h": (h, TF.H6), "12h": (h, TF.H12)}
    mt_w, mp_w = _senza_weekend(mt, mp)
    a = np.searchsorted(h.t, T - 10800 * QUANTE * 3)
    ht_w, hp_w = _senza_weekend(h.t[a:], h.bid[a:] * h.punto)
    nostri = {"3m": (mt_w, mp_w), "30m": (mt_w, mp_w), "45m": (mt_w, mp_w), "2h": (ht_w, hp_w), "3h": (ht_w, hp_w)}
    for nome in INTRA:
        if nome in bot:
            base, tf = bot[nome]
            c = costruisci(base, tf)
            ti, o = c.inizio, c.bid
        else:
            ti, o = blocchi(*nostri[nome], INTRA[nome])
        fuori[nome] = pacchetto(ora_italiana(ti[-QUANTE:]), o[-QUANTE:])
    for nome, tf in LUNGHI.items():
        c = costruisci(h, tf)
        fuori[nome] = pacchetto(giorno_di_borsa(c.inizio), c.bid)
    return fuori


def main(hd: Path, m1: Path, casi: Path, uscita: Path) -> None:
    rng = np.random.default_rng(12)
    ore, _ = carica(hd, "EURUSD", utc(2002, 1, 1), utc(2020, 1, 1), solo_bid=True)
    f = np.load(casi)
    from kaggle_rete.esperienza import SCHEDA
    sel = (f["strumento"] == "EURUSD") & (f["t"] >= utc(2014, 2, 1)) & (f["t"] < utc(2020, 1, 1)) & \
          (f["scheda"][:, SCHEDA.index("A+")] > 0) & (f["scheda"][:, SCHEDA.index("rr target")] >= 1.5)
    setup = rng.choice(f["t"][sel], size=12, replace=False)
    # Istanti a caso: aperture di ore da lunedi' a venerdi', 8-20 italiane.
    caso = []
    while len(caso) < 12:
        t = int(rng.integers(utc(2014, 2, 1), utc(2019, 12, 20))) // 3600 * 3600
        import datetime as dt
        r = dt.datetime.fromtimestamp(t, ROMA)
        if r.weekday() < 5 and 8 <= r.hour <= 20:
            caso.append(t)
    istanti = [int(x) for x in setup] + caso
    rng.shuffle(istanti)
    m1 = {a: minuti_da_zip(m1 / f"EURUSD-{a}.zip") for a in range(2014, 2020)}
    uscita.mkdir(parents=True, exist_ok=True)
    indice = []
    for i, T in enumerate(istanti, 1):
        import datetime as dt
        anno = dt.datetime.fromtimestamp(T, ROMA).year
        t1, p1 = m1[anno]
        if T - t1[0] < 60 * 86400 and anno - 1 in m1:
            t0, p0 = m1[anno - 1]
            t1, p1 = np.r_[t0, t1], np.r_[p0, p1]
        dati = lezione(ore, t1, p1, T)
        (uscita / f"{i:02d}.json").write_text(json.dumps({"n": i, "strumento": "EURUSD", "T": T, "cifre": 5,
                                                          "tf": dati}, separators=(",", ":")))
        indice.append({"n": i, "T": T, "setup del bot": bool(T in set(int(x) for x in setup))})
        print(i, dt.datetime.fromtimestamp(T, ROMA).strftime("%a %d/%m/%Y %H:%M"),
              {k: len(v["t"]) for k, v in dati.items()}, flush=True)
    # Quali sono setup del bot lo sa solo questo file, fuori dalla pagina: chi disegna non deve saperlo.
    (uscita.parent / "indice_segreto.json").write_text(json.dumps(indice))


if __name__ == "__main__":
    main(*(Path(x) for x in sys.argv[1:5]))
