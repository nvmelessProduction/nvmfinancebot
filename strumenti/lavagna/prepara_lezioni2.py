"""Le lezioni della lavagna, versione 2: per ogni istante lo strumento principale e i suoi grafici di confronto (SMT),
con tutti i timeframe fino a quell'istante (l'ultima candela e' quella in formazione), niente futuro.

    python prepara2.py CARTELLA_HD CARTELLA_M1 indice_segreto.json USCITA

Per ogni simbolo e timeframe: `t` il tempo da mostrare (ora italiana per l'intraday, data del giorno di borsa da 1D in
su), `u` l'inizio vero della candela in UTC (serve ai disegni per restare al loro posto cambiando timeframe), `p` i
prezzi in punti. Il DXY e' quello del bot (`foto.dxy`, dalle 5 coppie): HistData prima del 2019 ha un'altra serie.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepara_lezioni as P  # noqa: E402
from nvm.agenti import foto  # noqa: E402
from nvm.dati.candele import costruisci  # noqa: E402
from nvm.dati.minuti import PUNTO, Minuti  # noqa: E402
from nvm.dati.ore import carica  # noqa: E402
from nvm.tempo import TF, utc  # noqa: E402

SIMBOLI = {"EURUSD": ("DXY", "GBPUSD")}
COPPIE_DXY = tuple(foto.PESI_DXY)
CIFRE = {"DXY": 3}


def _m(strumento, t, punti) -> Minuti:
    z = np.zeros(len(t), np.float32)
    return Minuti(strumento, np.asarray(t, np.int64), punti, punti.copy(), z, z.copy(), 60)


def minuti(m1: Path, s: str, anni) -> Minuti:
    """I minuti di piu' anni, in ordine e senza doppioni (HistData ne ripete qualcuno al cambio d'anno o d'ora)."""
    tt, pp = [], []
    for a in anni:
        t, p = P.minuti_da_zip(m1 / f"{s}-{a}.zip")
        tt.append(t); pp.append(p)
    t, p = np.concatenate(tt), np.concatenate(pp)
    o = np.argsort(t, kind="stable")
    t, p = t[o], p[o]
    _, primi = np.unique(t, return_index=True)
    return _m(s, t[primi], np.rint(p[primi] / PUNTO[s]).astype(np.int64))


def serie(base_min: Minuti, base_ore: Minuti, T: int, cifre: int) -> dict:
    """Tutti i timeframe di un simbolo fino a T."""
    punto = 10.0 ** -cifre
    fuori = {}
    k = np.searchsorted(base_min.t, T)
    a = np.searchsorted(base_min.t, T - 2700 * P.QUANTE * 3)
    m = base_min.fra(int(base_min.t[a]) if a < len(base_min) else T, T)
    h = base_ore.fra(0, T)
    mt, mp = m.t, m.bid * m.punto
    mt_w, mp_w = P._senza_weekend(mt, mp)
    a = np.searchsorted(h.t, T - 10800 * P.QUANTE * 3)
    ht_w, hp_w = P._senza_weekend(h.t[a:], h.bid[a:] * h.punto)
    bot = {"1m": (m, TF.M1), "5m": (m, TF.M5), "15m": (m, TF.M15),
           "1h": (h, TF.H1), "4h": (h, TF.H4), "6h": (h, TF.H6), "12h": (h, TF.H12)}
    nostri = {"3m": (mt_w, mp_w), "30m": (mt_w, mp_w), "45m": (mt_w, mp_w), "2h": (ht_w, hp_w), "3h": (ht_w, hp_w)}

    def scrivi(nome, inizi, ohlc, giorni=False):
        inizi, ohlc = inizi[-P.QUANTE:] if not giorni else inizi, ohlc[-P.QUANTE:] if not giorni else ohlc
        fuori[nome] = {"t": P.giorno_di_borsa(inizi) if giorni else P.ora_italiana(inizi),
                       "u": [int(x) for x in inizi],
                       "p": np.rint(np.asarray(ohlc) / punto).astype(np.int64).ravel().tolist()}

    for nome in P.INTRA:
        if nome in bot:
            base, tf = bot[nome]
            c = costruisci(base, tf) if len(base) else None
            if c is None or not len(c):
                continue
            scrivi(nome, c.inizio, c.bid)
        else:
            if not len(nostri[nome][0]):
                continue
            ti, o = P.blocchi(*nostri[nome], P.INTRA[nome])
            scrivi(nome, ti, o)
    for nome, tf in P.LUNGHI.items():
        c = costruisci(h, tf)
        scrivi(nome, c.inizio, c.bid, giorni=True)
    return fuori


def main(hd: Path, m1: Path, segreto: Path, uscita: Path) -> None:
    indice = json.loads(segreto.read_text())
    anni = range(2014, 2020)
    tutti = ("EURUSD",) + tuple(x for v in SIMBOLI.values() for x in v if x != "DXY")
    ore = {s: carica(hd, s, utc(2002, 1, 1), utc(2020, 1, 1), solo_bid=True)[0] for s in set(tutti) | set(COPPIE_DXY)}
    mins = {s: minuti(m1, s, anni) for s in set(tutti) | set(COPPIE_DXY)}
    ore["DXY"] = foto.dxy({s: ore[s] for s in COPPIE_DXY})
    mins["DXY"] = foto.dxy({s: mins[s] for s in COPPIE_DXY})
    uscita.mkdir(parents=True, exist_ok=True)
    for x in indice:
        n, T = x["n"], x["T"]
        principale = "EURUSD"
        dati = {"n": n, "T": T, "principale": principale, "simboli": {}}
        for s in (principale,) + SIMBOLI[principale]:
            cifre = CIFRE.get(s, 5 if PUNTO[s] < 1e-4 else 3)
            dati["simboli"][s] = {"cifre": cifre, "tf": serie(mins[s], ore[s], T, cifre)}
        (uscita / f"{n:02d}.json").write_text(json.dumps(dati, separators=(",", ":")))
        print(n, {s: len(v["tf"]) for s, v in dati["simboli"].items()}, flush=True)


if __name__ == "__main__":
    main(*(Path(x) for x in sys.argv[1:5]))
