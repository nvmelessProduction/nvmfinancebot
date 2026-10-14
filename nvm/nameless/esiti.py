"""Come sarebbe finito ogni setup che il bot prende (fase 3 di Nameless): il risultato in R, coi costi.

Il Capo impara dai risultati veri (`documenti/PROGETTO-NAMELESS.md`, fase 3): per ogni CRT per cui le regole delle foto
dicono "si entra" (`materie.crt`, `entra`), l'operazione come la fa il bot dal vivo (`giro._decisione_foto`):

- entrata all'apertura della candela 3, stop oltre l'estremo della candela 2;
- il 25% al TP1 col pareggio e il resto al target finale; se il target finale non vale almeno 1 R, tutto al TP1
  (`giro.piani_foto`);
- scadenza dopo `giro.TETTO_FOTO` (10 giorni per il CRT a 1 ora, 30 a 4 ore, ...): si chiude alla chiusura;
- l'esito candela per candela sulle ore, con le regole del campo di prova (`prova.campo.simula`): stop e target nella
  stessa ora conta lo stop, un'apertura oltre lo stop esce all'apertura.

I costi. HistData da' solo il bid: lo spread si stima, ed e' dichiarato. `SPREAD_RANGE` volte il range medio giornaliero
delle 14 giornate prima (circa 0,7 pip su EURUSD, 40 centesimi sull'oro, mezzo punto sull'S&P 500): piu' largo di un
conto raw, apposta. Piu' la commissione del conto (`strumenti.Strumento.commissione`: 0,7 pip sul forex). Sul demo il
prezzo d'entrata e' quello voluto (fase 0): niente slittamento in piu'. La prova coi costi doppi (`erre_doppi`) dice se
il risultato regge se lo spread e' il doppio.
"""

from __future__ import annotations

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import MASSIMO, MINIMO, Minuti
from nvm.nameless.materie import CORTO, TF_CRT, Materie
from nvm.prova.campo import COMMISSIONE, Operazione, Uscita, simula
from nvm.tempo import TF

SPREAD_RANGE = 0.01
GIORNI = 14
PARZIALE = 0.25
# Come `giro.TETTO_FOTO`: quanto resta aperta al massimo un'operazione, per timeframe del CRT.
TETTO = {TF.H1: 10 * 86400, TF.H4: 30 * 86400, TF.H6: 40 * 86400, TF.D1: 90 * 86400, TF.W1: 300 * 86400,
         TF.MN: 800 * 86400}
USCITE = tuple(u.value for u in Uscita)
CAMPI = ("tf", "riga", "erre", "erre_doppi", "uscita", "chiusa", "tp1_preso", "rischio", "spread", "finita")


def spread_a(ore: Minuti) -> tuple[np.ndarray, np.ndarray]:
    """(fine delle giornate, spread stimato da quel momento): `SPREAD_RANGE` volte il range medio delle `GIORNI`
    giornate chiuse."""
    g = costruisci(ore, TF.D1)
    r = g.bid[:, MASSIMO] - g.bid[:, MINIMO]
    medio = np.convolve(r, np.ones(GIORNI) / GIORNI, mode="full")[:len(r)]
    quante = np.minimum(np.arange(1, len(r) + 1), GIORNI)
    medio = medio * GIORNI / quante
    return g.fine.astype(np.int64), SPREAD_RANGE * medio


def esito(op: Operazione, ore: Candele, spread: float, scadenza: int):
    """L'esito con l'ask = bid + spread sulle ore che servono."""
    a = int(np.searchsorted(ore.inizio, op.quando))
    b = int(np.searchsorted(ore.inizio, scadenza))
    pezzo = Candele(ore.strumento, TF.H1, ore.inizio[a:b], ore.fine[a:b], ore.bid[a:b], ore.bid[a:b] + spread,
                    ore.volume[a:b])
    return simula(op, pezzo, scadenza)


def esiti(ore: Minuti, m: Materie) -> dict[str, np.ndarray]:
    """I risultati di tutti i setup in cui si entra, uno per riga (`CAMPI`): `tf` l'indice in `TF_CRT`, `riga` la
    riga in `m.crt[tf]`; `finita` e' falso per le operazioni ancora aperte quando finiscono i dati (il risultato non
    e' quello vero: non contano)."""
    COMMISSIONE.setdefault(ore.strumento, 0.0)
    h1 = costruisci(ore, TF.H1)
    fine_dati = int(h1.fine[-1]) if len(h1) else 0
    fine_g, spread_g = spread_a(ore)
    righe = []
    for i, tf in enumerate(TF_CRT):
        r = m.crt[tf]
        for k in np.flatnonzero(r["entra"]):
            n3 = int(r["n3"][k])
            g = int(np.searchsorted(fine_g, n3, side="right")) - 1
            if g < 0:
                continue
            corto = int(r["verso"][k]) == CORTO
            verso = Verso.SHORT if corto else Verso.LONG
            s = float(spread_g[g])
            ingresso, stop, tp1, ob = (float(r[c][k]) for c in ("ingresso", "stop", "tp1", "obiettivo"))
            rischio = abs(ingresso - stop)
            segno = -1 if corto else 1
            al_finale = ob != tp1 and segno * (ob - tp1) >= 0 and abs(ob - ingresso) >= rischio - 1e-12
            risultati = []
            for costo in (s, 2 * s):
                try:
                    op = Operazione(ore.strumento, verso, n3, ingresso + (0.0 if corto else costo), stop, tp1,
                                    ob if al_finale else tp1, parziale=PARZIALE if al_finale else 1.0,
                                    pareggio=al_finale)
                except ValueError:
                    risultati = []
                    break
                risultati.append(esito(op, h1, costo, n3 + TETTO[tf]))
            if not risultati:
                continue
            e, e2 = risultati
            finita = e.uscita is not Uscita.SCADUTA or n3 + TETTO[tf] <= fine_dati
            righe.append((i, k, e.erre, e2.erre, USCITE.index(e.uscita.value), e.quando, e.tp1_preso, rischio, s,
                          finita))
    tipi = (np.int8, np.int64, np.float32, np.float32, np.int8, np.int64, bool, np.float64, np.float64, bool)
    if not righe:
        return {c: np.zeros(0, t) for c, t in zip(CAMPI, tipi)}
    return {c: np.array(v, t) for c, v, t in zip(CAMPI, zip(*righe), tipi)}
