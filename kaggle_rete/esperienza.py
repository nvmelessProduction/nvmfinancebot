"""La scuola dell'esperienza (passo 2): ogni setup che il bot avrebbe visto negli anni, col suo trade simulato.

Per ogni CRT delle foto (`foto.trova` su tutti i timeframe del bot, `giro.setup_buono`), come fa il bot dal vivo
(`giro.occasioni_foto`): una sola occasione per apertura e verso, quella del timeframe piu' grande; il quadro tagliato
all'apertura della candela 3 (niente futuro); il target finale delle foto (`foto.obiettivo_finale`); il 25% al TP1
col pareggio e il resto al target finale, o tutto al TP1 se un target finale non c'e'. L'esito si simula ora per ora
con `campo.simula` (lo stop vince se una candela tocca tutti e due, commissioni tolte in R) fino alla scadenza del bot
(`giro.TETTO_FOTO`).

Ogni caso tiene anche quello che il bot sapeva all'ingresso (timeframe, verso, distanze di stop e target in unita' del
range giornaliero medio, rendimento al TP1 e al target, key level, direzione, tipo di target): e' la "scheda" che la
rete legge insieme al grafico.

Lo spread: HistData da' solo il bid. L'ask si fa col bid piu' uno spread fisso per strumento (`SPREAD`), un po' sopra
quelli tipici di un conto raw: e' una stima prudente, dichiarata.

I setup che il bot prende dal DXY (`foto.dal_dxy`) qui non ci sono: nello storico il grafico del DXY del broker
non c'e'.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from nvm.agenti import foto
from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import MASSIMO, MINIMO, PUNTO, Minuti
from nvm.prova.campo import Operazione, simula
from nvm.tempo import ORDINE, TF
from nvm.vivo.giro import TETTO_FOTO, setup_buono

# Lo spread (in prezzo) che si aggiunge al bid di HistData per fare l'ask.
_PIP = 0.0001
SPREAD = {**{c: 0.3 * _PIP for c in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF")},
          "USDJPY": 0.003,
          **{c: 0.8 * _PIP for c in ("EURGBP", "EURAUD", "EURCAD", "EURCHF", "AUDNZD", "AUDCAD", "AUDCHF", "NZDCAD",
                                     "NZDCHF", "CADCHF", "GBPCHF", "GBPCAD")},
          **{c: 1.2 * _PIP for c in ("EURNZD", "GBPAUD", "GBPNZD")},
          **{c: 0.010 for c in ("EURJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY")},
          "GBPJPY": 0.015,
          "XAUUSD": 0.20, "XAGUSD": 0.025, "USOIL": 0.03, "UKOIL": 0.03,
          "SPX500": 0.5, "NAS100": 1.2, "US30": 2.0, "GER40": 1.2, "UK100": 1.0, "JPN225": 8.0, "DXY": 0.03}

# Le colonne della scheda di ogni caso, nell'ordine.
SCHEDA = ([f"tf {tf.value}" for tf in foto.TF_CRT] +
          ["vendita", "stop", "tp1", "target", "rr tp1", "rr target", "key level", "direzione", "A+",
           "target gap", "target key level", "inside bar"])
GIORNI_SCALA = 14
# Lo stop piu' piccolo che si studia, in range giornalieri medi: sotto (il 3,6% dei casi, su EURUSD meno di 3-4 pip)
# spread e commissioni si mangiano quasi tutto e un salto d'apertura fa perdere decine di volte il rischio.
STOP_MINIMO = 0.05


def con_spread(m: Minuti, spread: float | None = None) -> Minuti:
    """Le stesse ore con l'ask = bid + spread (HistData ha solo il bid)."""
    sp = SPREAD.get(m.strumento, 0.0) if spread is None else spread
    punti = int(round(sp / PUNTO[m.strumento]))
    return Minuti(m.strumento, m.t, m.bid, m.bid + punti, m.volume_bid, m.volume_ask, m.passo)


@dataclass
class Casi:
    """I casi di uno strumento, in colonne: quando, la scheda, e com'e' finita."""

    strumento: str
    t: np.ndarray          # apertura della candela 3 (l'istante in cui la rete guarda)
    scheda: np.ndarray     # [N, len(SCHEDA)] float32
    erre: np.ndarray       # il risultato in R, costi tolti
    uscita: np.ndarray     # come e' finita (stop, target, pareggio, scaduta)

    def __len__(self) -> int:
        return len(self.t)


def _scala(giorni, t: int) -> float:
    k = int(np.searchsorted(giorni.fine, t, side="right")) - 1
    if k < 0:
        return float("nan")
    a = max(0, k - GIORNI_SCALA + 1)
    r = giorni.bid[a:k + 1, MASSIMO] - giorni.bid[a:k + 1, MINIMO]
    return float(np.mean(r)) if len(r) else float("nan")


def _kl_ok(s) -> bool:
    """Il key level come lo chiede il bot (`metodo.valuta_foto`)."""
    if s.tf is TF.H1:
        return bool(s.h4_preso is not None and any(l.tf is TF.D1 and not l.oggi for l in s.presi))
    return bool(s.presi)


def casi(m: Minuti, dal: int, al: int, scrivi=print) -> Casi:
    """Tutti i casi con la candela 3 che apre in [dal, al): `m` sono le ore (bid e ask) fino a dove si vuole simulare."""
    inizio = time.time()
    q = foto.Quadro.da(m, int(m.t[-1]) + 3600)
    basse = q.candele[TF.H1]
    giorni = q.candele[TF.D1]
    trovati = [s for tf in foto.TF_CRT for s in foto.trova(q, tf, dal, al - 1) if setup_buono(s)]
    gruppi: dict = {}
    for s in trovati:
        gruppi.setdefault((s.n3_inizio, s.verso), []).append(s)
    t, schede, erre, uscite = [], [], [], []
    for (n3, _), gruppo in sorted(gruppi.items(), key=lambda g: g[0][0]):
        s = max(gruppo, key=lambda x: ORDINE.index(x.tf))
        try:
            qq = q.taglia(n3)
            ob = foto.obiettivo_finale(qq, s)
            dz = foto.direzione(qq, s)
            tutto_al_tp1 = ob.prezzo == s.tp1
            op = Operazione(s.strumento, s.verso, n3, s.ingresso, s.stop, s.tp1, ob.prezzo,
                            parziale=1.0 if tutto_al_tp1 else foto.PARZIALE, pareggio=not tutto_al_tp1)
            e = simula(op, basse, n3 + TETTO_FOTO.get(s.tf, 30 * 86400))
        except (ValueError, IndexError, KeyError):
            continue
        sc = _scala(giorni, n3)
        if not np.isfinite(sc) or sc <= 0:
            continue
        rischio = op.rischio
        kl, ok = _kl_ok(s), bool(dz.ok)
        riga = [float(s.tf is tf) for tf in foto.TF_CRT] + [
            float(s.verso is Verso.SHORT), rischio / sc, abs(s.tp1 - op.ingresso) / sc, abs(ob.prezzo - op.ingresso) / sc,
            abs(s.tp1 - op.ingresso) / rischio, abs(ob.prezzo - op.ingresso) / rischio, float(kl), float(ok),
            float(kl and ok), float(ob.tipo == "gap"), float(ob.tipo == "key level"), float(getattr(s, "dentro", 0))]
        t.append(n3)
        schede.append(riga)
        erre.append(e.erre)
        uscite.append(e.uscita.value)
    fuori = Casi(m.strumento, np.array(t, np.int64), np.array(schede, np.float32).reshape(-1, len(SCHEDA)),
                 np.array(erre, np.float32), np.array(uscite))
    scrivi(f"{m.strumento}: {len(fuori)} casi ({time.time() - inizio:.0f} s)")
    return fuori
