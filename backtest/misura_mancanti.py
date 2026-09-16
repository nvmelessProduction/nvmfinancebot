"""Misura le otto regole mancanti sui prezzi veri Dukascopy."""
import pickle, sys
from pathlib import Path
sys.path.insert(0, "/home/user/nvmfinancebot")

from backtest.romeo_mancante import cerca, risolvi, valuta, Esito
from core.definizioni import (
    Bias, cisd, divergenza_smt, double_purge, meta_tenuta, peso_ombre,
    verso_del_double_purge, nuovo_estremo,
)
from core.contesto import dentro_finestra_crt
from core.parametri import COMPAGNE_SMT, TF

SCR = Path("/tmp/claude-0/-home-user-nvmfinancebot/524092c4-5c76-5af6-a985-c494bd565758/scratchpad/bt")
serie = pickle.load(open(SCR / "duka_serie.pickle", "rb"))

TF_NOME = {"H1": TF.H1, "H4": TF.H4, "D1": TF.D1, "W1": TF.W1, "M1": TF.M1}
COPPIE = [("W1", "H4"), ("D1", "H1"), ("M1", "D1")]

def barre(strumento, tf, lato="BID"):
    return serie[strumento][lato].get(tf, ())

print(f"{'':34} {'n':>7}  {'win':>6}  {'R medio':>7}  {'σ≠0':>7}  {'σ vs base':>7}")
print("=" * 82)

for alto, basso in COPPIE:
    print(f"\n### coppia {alto} → {basso}")
    base_tutti, per_regola = [], {}

    for strumento in ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY"]:
        alte = barre(strumento, alto)
        basse = barre(strumento, basso)
        if len(alte) < 30 or len(basse) < 30:
            continue
        # indice temporale sulle basse, per risolvere l'esito
        tempi = [c.orario for c in basse]
        import bisect
        segnali = cerca(alte)
        for s in segnali:
            j = bisect.bisect_right(tempi, s.n2.orario)
            esito = risolvi(s, basse[j:], barre=24)
            if esito is None:
                continue
            base_tutti.append(esito)

            # --- CRT-12 divergenza SMT -------------------------------------
            verso_sweep = Bias.LONG if s.direzione is Bias.SHORT else Bias.SHORT
            div = None
            for compagna in COMPAGNE_SMT.get(strumento, ()):
                alte_c = barre(compagna, alto)
                if not alte_c:
                    continue
                # allinea la compagna allo stesso istante
                tc = [c.orario for c in alte_c]
                k = bisect.bisect_right(tc, s.n2.orario)
                d = divergenza_smt(strumento, alte[:s.indice+1], alte_c[:k],
                                   compagna, verso_sweep)
                if d is not None:
                    div = d if div is None else (div or d)
            if div is True:
                per_regola.setdefault("CRT-12 con divergenza SMT", []).append(esito)
            elif div is False:
                per_regola.setdefault("CRT-12 senza divergenza", []).append(esito)

            # --- CRT-10 Double Purge ---------------------------------------
            if double_purge(s.n1, s.n2):
                v = verso_del_double_purge(s.n2)
                chiave = ("CRT-10 double purge concorde" if v is s.direzione
                          else "CRT-10 double purge discorde")
                per_regola.setdefault(chiave, []).append(esito)

            # --- CRT-19/20 ombre, NEI DUE VERSI ----------------------------
            peso = peso_ombre(s.n2)
            if peso is not None:
                if peso >= 0.60:
                    per_regola.setdefault("CRT-20 ombre GRANDI (>=0,60)", []).append(esito)
                elif peso <= 0.30:
                    per_regola.setdefault("CRT-19 ombre piccole (<=0,30)", []).append(esito)

            # --- CRT-11 CISD sul timeframe basso ---------------------------
            finestra = basse[max(0, j - 12):j]
            livello = cisd(finestra, s.direzione)
            if livello is not None:
                per_regola.setdefault("CRT-11 con CISD disponibile", []).append(esito)

            # --- CRT-15 finestre orarie di Romeo ---------------------------
            dentro = dentro_finestra_crt(s.n2.orario, TF_NOME[basso])
            if dentro is True:
                per_regola.setdefault("CRT-15 dentro finestra Romeo", []).append(esito)
            elif dentro is False:
                per_regola.setdefault("CRT-15 fuori finestra Romeo", []).append(esito)

            # --- CRT-17 tenuta della meta' ---------------------------------
            #
            # LOOKAHEAD CORRETTO. La prima versione passava `alte[i+1:i+3]`,
            # cioe' le due candele del timeframe ALTO successive a N2: su
            # D1→H1 sono i due giorni dopo, mentre l'esito si risolve entro 24
            # ore. Filtravo col futuro, e il risultato lo diceva: 85,7% di
            # winrate e +15,3σ, che e' il profilo di un lookahead e non di un
            # vantaggio.
            #
            # Al momento dell'ingresso si vede solo cio' che e' accaduto
            # DENTRO N2, sul timeframe basso, fino alla chiusura.
            inizio_n2 = bisect.bisect_right(tempi, s.n1.orario)
            dentro_n2 = basse[inizio_n2:j]
            t = meta_tenuta(s.n1, dentro_n2)
            if t is s.direzione:
                per_regola.setdefault("CRT-17 meta' tenuta (dentro N2)", []).append(esito)

    esiti = [valuta("CRT base (tutti)", base_tutti, base_tutti)]
    for nome in sorted(per_regola):
        esiti.append(valuta(nome, per_regola[nome], base_tutti))
    for e in esiti:
        if e.n >= 30:
            print(e.riga())
