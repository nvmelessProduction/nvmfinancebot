"""Il CISD regge fuori campione, o e' l'ennesimo falso positivo?"""
import bisect, pickle, random, sys
from pathlib import Path
sys.path.insert(0, "/home/user/nvmfinancebot")
from backtest.romeo_mancante import cerca, risolvi, valuta, sigma, confronto
from core.definizioni import Bias, cisd

SCR = Path("/tmp/claude-0/-home-user-nvmfinancebot/524092c4-5c76-5af6-a985-c494bd565758/scratchpad/bt")
serie = pickle.load(open(SCR / "duka_serie.pickle", "rb"))
STRUMENTI = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY"]

def raccogli(alto, basso):
    """(anno, esito, ha_cisd, ha_cisd_placebo) per ogni segnale."""
    righe = []
    for strumento in STRUMENTI:
        alte, basse = serie[strumento]["BID"].get(alto, ()), serie[strumento]["BID"].get(basso, ())
        if len(alte) < 30 or len(basse) < 30:
            continue
        tempi = [c.orario for c in basse]
        for s in cerca(alte):
            j = bisect.bisect_right(tempi, s.n2.orario)
            esito = risolvi(s, basse[j:], barre=24)
            if esito is None:
                continue
            finestra = basse[max(0, j - 12):j]
            vero = cisd(finestra, s.direzione) is not None
            # PLACEBO: stessa condizione su una finestra presa a caso altrove,
            # cosi' la frazione di segnali selezionati resta la stessa ma il
            # legame col segnale sparisce.
            k = random.randrange(12, max(13, len(basse) - 1))
            finto = cisd(basse[k - 12:k], s.direzione) is not None
            righe.append((s.n2.orario.year, esito, vero, finto))
    return righe

random.seed(20260916)
for alto, basso in [("D1", "H1"), ("W1", "H4")]:
    righe = raccogli(alto, basso)
    print(f"\n### {alto} → {basso}   ({len(righe)} segnali)")
    print(f"{'epoca':<14} {'n con CISD':>10} {'R con':>8} {'R senza':>8} {'σ diff':>8}  {'placebo σ':>9}")
    print("-" * 68)
    for nome, da, a in [("2006-2012", 2006, 2012), ("2013-2019", 2013, 2019),
                        ("2020-2026", 2020, 2026), ("TUTTO", 2000, 2100)]:
        blocco = [r for r in righe if da <= r[0] <= a]
        con   = [r[1] for r in blocco if r[2]]
        senza = [r[1] for r in blocco if not r[2]]
        pcon  = [r[1] for r in blocco if r[3]]
        psenza= [r[1] for r in blocco if not r[3]]
        if len(con) < 30 or len(senza) < 30:
            continue
        print(f"{nome:<14} {len(con):>10} {sum(con)/len(con):>+8.3f} "
              f"{sum(senza)/len(senza):>+8.3f} {confronto(con, senza):>+7.1f}σ "
              f"{confronto(pcon, psenza):>+8.1f}σ")
