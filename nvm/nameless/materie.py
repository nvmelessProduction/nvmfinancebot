"""Le materie di Nameless (fase 2): le risposte giuste, date dalle regole delle foto (`nvm/agenti/foto.py`).

Il proprietario, 13/10/2026: *"tutto quello che sta scritto là è quello che deve fare la rete neurale. Su ogni fottuto
pair"*. Le regole delle foto tornano 24 su 24 (`strumenti/foto.py`): sono il maestro. Per ogni pezzo di mercato, con
gli orari di TradingView (`candele.SESSIONI`), si scrivono:

- **per ogni CRT** di 1, 4, 6 ore, giorno, settimana e mese (`foto.trova`): il verso; se la candela 2 ha preso un key
  level (a 1 ora: il key level giornaliero e il massimo o minimo a 4 ore, `giro.setup_buono`); e per quelli col key
  level la direzione (`foto.direzione`), il target finale (`foto.obiettivo_finale`: gap, key level, l'altro lato del
  range) con quanti R vale, e se il bot entra: CRT, key level, direzione e un piano da almeno 1 R (`giro.piani_foto`,
  `metodo.valuta_foto`). La domanda si fa all'ultima ora della candela 2 (`ora`), quando la candela 3 sta per aprire;
- **per ogni candela** di giorno, settimana, 1, 3 e 12 mesi: come ha chiuso rispetto a quella prima
  (`foto.bias_candela`) e se ha accettato un lato il cui estremo il prezzo non ha ancora preso (`foto.accettazione`):
  per ogni ora, la candela che conta e' l'ultima chiusa (`sensi.Sensi.entro`).

Solo numpy e le regole: niente rete qui. Il calcolo e' lungo (le regole guardano gap e livelli di anni), si fa una
volta su Kaggle col processore (`kaggle_rete/materie.py`) e la rete lo impara sulla scheda grafica.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from nvm.agenti import foto
from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import MASSIMO, MINIMO, Minuti
from nvm.tempo import TF

TF_CRT = foto.TF_CRT
TF_CANDELA = (TF.D1, TF.W1, TF.MN, TF.Q3, TF.Y1)
TIPI = ("gap", "key level", "range")
LUNGO, CORTO = 1, 2          # le classi del verso: 0 niente
MAI = np.iinfo(np.int64).max

# I campi di ogni CRT, nell'ordine in cui si salvano.
CAMPI_CRT = ("ora", "k2", "n3", "verso", "kl", "direzione", "tipo", "rr", "entra", "ingresso", "stop", "tp1",
             "obiettivo", "alto", "basso")
CAMPI_CANDELA = ("direzione", "accetta", "preso", "fine")


@contextmanager
def _gap_in_memoria():
    """Le regole chiedono gli stessi gap tante volte per lo stesso istante (direzione, target, muro, liquidazione):
    si calcolano una volta. Solo dentro questo calcolo: il bot dal vivo non lo vede."""
    originale = foto.gap_di
    memoria: dict = {}

    def gap_di(q, tf, t):
        chiave = (id(q), tf, int(t))
        if chiave not in memoria:
            if len(memoria) > 50000:
                memoria.clear()
            memoria[chiave] = originale(q, tf, t)
        return memoria[chiave]
    foto.gap_di = gap_di
    try:
        yield
    finally:
        foto.gap_di = originale


def setup_buono(s) -> bool:
    """Come `giro.setup_buono`: il CRT a 1 ora vale solo col key level giornaliero e il massimo (minimo) a 4 ore."""
    if s.tf is not TF.H1:
        return True
    return s.h4_preso is not None and any(l.tf is TF.D1 and not l.oggi for l in s.presi)


def key_level(s) -> bool:
    """La domanda "key level" di `metodo.valuta_foto`: a 1 ora come `setup_buono`, sopra basta un key level preso."""
    return setup_buono(s) if s.tf is TF.H1 else bool(s.presi)


def piano(s, ob) -> bool:
    """C'e' un piano da almeno `foto.RR_MINIMO` R (`giro.piani_foto`): il 25% al TP1 e il resto al target finale, o
    tutto al TP1."""
    rischio = abs(s.ingresso - s.stop)
    segno = -1 if s.short else 1
    # Le condizioni di `prova.campo.Operazione`: lo stop dietro, il TP1 davanti, il secondo target non prima del primo.
    if not rischio or segno * (s.ingresso - s.stop) <= 0 or segno * (s.tp1 - s.ingresso) <= 0:
        return False
    abbastanza = lambda tp: abs(tp - s.ingresso) >= foto.RR_MINIMO * rischio - 1e-12
    al_finale = ob.prezzo != s.tp1 and segno * (ob.prezzo - s.tp1) >= 0 and abbastanza(ob.prezzo)
    return al_finale or abbastanza(s.tp1)


def crt_di(q: foto.Quadro, tf: TF, dal: int = 0, al: int = 2 ** 62) -> dict[str, np.ndarray]:
    """Tutti i CRT di `tf` con la candela 3 che apre in [dal, al], con le risposte delle regole (`CAMPI_CRT`)."""
    righe = []
    ore = q.ore
    c = q.candele[tf]
    with _gap_in_memoria():
        for s in foto.trova(q, tf, dal, al):
            k2 = int(np.searchsorted(c.inizio, s.n2_inizio))
            fine2 = int(c.fine[k2])
            ora = int(np.searchsorted(ore.inizio, fine2, side="left")) - 1
            kl = key_level(s)
            direzione, tipo, rr, entra, obiettivo = -1, -1, np.nan, False, np.nan
            if kl:
                dz = foto.direzione(q, s)
                ob = foto.obiettivo_finale(q, s)
                direzione = int(dz.ok)
                tipo = TIPI.index(ob.tipo) if ob.tipo in TIPI else TIPI.index("key level")
                rr = abs(ob.prezzo - s.ingresso) / max(abs(s.ingresso - s.stop), 1e-12)
                obiettivo = ob.prezzo
                entra = dz.ok and piano(s, ob)
            righe.append((ora, k2, s.n3_inizio, CORTO if s.short else LUNGO, kl, direzione, tipo, rr, entra,
                          s.ingresso, s.stop, s.tp1, obiettivo, s.range_alto, s.range_basso))
    tipi = (np.int64, np.int64, np.int64, np.int8, bool, np.int8, np.int8, np.float32, bool, np.float64, np.float64,
            np.float64, np.float64, np.float64, np.float64)
    if not righe:
        return {n: np.zeros(0, t) for n, t in zip(CAMPI_CRT, tipi)}
    colonne = list(zip(*righe))
    return {n: np.array(v, t) for n, v, t in zip(CAMPI_CRT, colonne, tipi)}


def candele_di(q: foto.Quadro, tf: TF) -> dict[str, np.ndarray]:
    """Per ogni candela di `tf`, quando e' l'ultima chiusa: la sua direzione (0 giu', 1 nessuna, 2 su:
    `foto.bias_candela`) e l'accettazione (`foto.accettazione`): 0 nessuna, 1 su, 2 giu', con l'ora in cui il prezzo
    ne prende l'estremo (`preso`, indice delle ore; da li' in poi non conta piu'); `fine` per allinearle ai sensi."""
    c = q.candele[tf]
    ore = q.ore
    n = len(c)
    direzione = np.ones(n, np.int8)
    accetta = np.zeros(n, np.int8)
    preso = np.full(n, MAI, np.int64)
    for k in range(n):
        direzione[k] = foto.bias_candela(c, k)[0] + 1
        j, dentro, verso, livello = k, 0, 0, 0.0
        while j >= 1 and dentro <= 3:
            p, x = c.bid[j - 1], c.bid[j]
            if x[3] > p[MASSIMO]:
                verso, livello = 1, float(x[MASSIMO])
                break
            if x[3] < p[MINIMO]:
                verso, livello = -1, float(x[MINIMO])
                break
            if not (x[MASSIMO] <= p[MASSIMO] and x[MINIMO] >= p[MINIMO]):
                break
            j, dentro = j - 1, dentro + 1
        if not verso:
            continue
        accetta[k] = 1 if verso > 0 else 2
        a = int(np.searchsorted(ore.inizio, int(c.fine[j])))
        oltre = ore.bid[a:, MASSIMO] > livello if verso > 0 else ore.bid[a:, MINIMO] < livello
        if oltre.any():
            preso[k] = a + int(np.argmax(oltre))
    return {"direzione": direzione, "accetta": accetta, "preso": preso, "fine": c.fine.astype(np.int64)}


@dataclass
class Materie:
    """Le risposte delle regole per un pezzo di mercato: `crt[tf]` (i campi di `CAMPI_CRT`, uno per CRT) e
    `candele[tf]` (`candele_di`, una per candela, nello stesso ordine delle candele di `sensi.candele_di`)."""

    strumento: str
    ore: int
    crt: dict = field(default_factory=dict)
    candele: dict = field(default_factory=dict)

    @classmethod
    def da(cls, ore: Minuti, dal: int = 0, al: int = 2 ** 62) -> "Materie":
        """Gli orari di TradingView (`candele.SESSIONI`) vanno messi prima."""
        q = foto.Quadro.da(ore, int(ore.t[-1]) + 3600)
        m = cls(ore.strumento, len(q.ore))
        for tf in TF_CANDELA:
            m.candele[tf] = candele_di(q, tf)
        for tf in TF_CRT:
            m.crt[tf] = crt_di(q, tf, dal, al)
        return m

    def salva(self, percorso) -> None:
        dati = {"ore": np.array(self.ore)}
        for tf, d in self.crt.items():
            dati.update({f"crt {tf.value} {k}": v for k, v in d.items()})
        for tf, d in self.candele.items():
            dati.update({f"candele {tf.value} {k}": v for k, v in d.items()})
        np.savez_compressed(percorso, **dati)

    @classmethod
    def carica(cls, percorso, strumento: str = "") -> "Materie":
        z = np.load(percorso)
        m = cls(strumento, int(z["ore"]))
        for tf in TF_CRT:
            m.crt[tf] = {k: z[f"crt {tf.value} {k}"] for k in CAMPI_CRT}
        for tf in TF_CANDELA:
            m.candele[tf] = {k: z[f"candele {tf.value} {k}"] for k in CAMPI_CANDELA}
        return m


# Le foto del proprietario (`strumenti/foto.py`, con gli orari di TradingView): id, strumento, timeframe, apertura della
# candela 3 (ora italiana), verso, se si entra, target finale (None: non si entra). Una prova controlla che siano le
# stesse di `strumenti.foto.FOTO`.
FOTO = (
    ("2/1", "EURUSD", TF.W1, "2026-02-16 00:00", "S", True, 1.1404),
    ("2/2", "EURUSD", TF.MN, "2026-05-01 00:00", "S", True, 1.1373),
    ("2/3", "EURUSD", TF.W1, "2026-06-01 00:00", "S", True, 1.1412),
    ("2/5", "DXY", TF.MN, "2025-02-03 00:00", "S", True, 99.235),
    ("2/6", "XAUUSD", TF.D1, "2026-08-26 00:00", "S", True, 4308.6),
    ("2/7", "XAUUSD", TF.H6, "2026-05-12 06:00", "S", True, 4101.0),
    ("2/8", "XAGUSD", TF.W1, "2026-05-18 00:00", "S", True, 61.28),
    ("3/1", "EURUSD", TF.MN, "2025-12-01 00:00", "L", True, 1.1779),
    ("3/2", "EURUSD", TF.W1, "2025-11-10 00:00", "L", True, 1.1798),
    ("3/3", "EURUSD", TF.D1, "2025-11-06 00:00", "L", True, 1.1803),
    ("3/4", "XAUUSD", TF.H4, "2026-09-03 20:00", "S", True, 4283.1),
    ("4/1", "EURUSD", TF.W1, "2026-09-14 00:00", "S", True, 1.1358),
    ("4/5", "XAUUSD", TF.H4, "2026-09-18 12:00", "S", True, 4257.1),
    ("4/6", "XAUUSD", TF.H1, "2026-09-10 09:00", "S", True, 4285.4),
    ("5/1", "GBPUSD", TF.MN, "2025-12-01 00:00", "L", True, 1.3793),
    ("5/2", "GBPUSD", TF.W1, "2025-11-10 00:00", "L", True, 1.3794),
    ("5/5", "XAUUSD", TF.H4, "2026-04-30 16:00", "S", True, 4100.5),
    ("5/6", "XAUUSD", TF.H4, "2026-05-01 20:00", "S", False, None),
    ("5/7", "XAUUSD", TF.H4, "2026-06-09 16:00", "S", True, 4100.5),
    ("5/8", "XAUUSD", TF.H4, "2026-09-02 08:00", "L", True, 4475.6),
    ("CASO-009", "XAUUSD", TF.H4, "2022-11-08 12:00", "L", True, 1683.7),
    ("franco-yen", "CHFJPY", TF.H1, "2026-10-07 11:00", "L", False, None),
    ("euro-yen", "EURJPY", TF.H1, "2026-10-07 11:00", "L", True, 178.336),
    ("euro-australiano", "EURAUD", TF.H1, "2026-10-07 11:00", "L", True, 1.61450),
)
ROMA = ZoneInfo("Europe/Rome")


def istante_foto(quando: str) -> int:
    return int(datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA).timestamp())


def crt_della_foto(crt: dict, tf: TF, quando: str, verso: str) -> int | None:
    """Quale CRT delle materie e' quello della foto (come `strumenti.foto.una`): il primo col verso della foto e col
    key level a 1 ora, con la candela 3 che apre vicino all'ora della foto (il mese e la settimana aprono la domenica
    sera o il primo del mese, la foto il primo giorno di borsa). None se le regole non vedono il CRT."""
    n3 = istante_foto(quando)
    prima = 4 * 86400 if tf in (TF.W1, TF.MN) else 3600
    v = CORTO if verso == "S" else LUNGO
    ok = (crt["n3"] >= n3 - prima) & (crt["n3"] <= n3 + 3600) & (crt["verso"] == v)
    if tf is TF.H1:
        ok &= crt["kl"]
    dove = np.flatnonzero(ok)
    return int(dove[0]) if len(dove) else None


def foto_giusta(crt: dict, i: int | None, deve: bool, target: float | None, entra: bool | None = None) -> bool:
    """La foto torna: si entra quando si deve (`entra`: la risposta da giudicare, quella delle regole se None) e il
    target finale e' quello della foto, entro mezzo range piu' lo 0,4% (le foto sono grafici dei future, i dati
    spot)."""
    if i is None:
        return not deve
    e = bool(crt["entra"][i]) if entra is None else entra
    if e != deve:
        return False
    if not e or target is None:
        return True
    return abs(crt["obiettivo"][i] - target) <= 0.5 * (crt["alto"][i] - crt["basso"][i]) + 0.004 * target
