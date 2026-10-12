"""Nameless, il trader che usa la strategia del proprietario (il metodo delle foto, con tutte le correzioni).

Non inventa operazioni: i candidati sono i setup che la strategia trova (`esperienza.casi`: CRT su 1, 4, 6 ore,
giorno, settimana e mese, key level, direzione, TP1 all'altro lato del range col 25% e il pareggio, target finale
sul gap o sul key level). Fa quello che fa un trader esperto con quella strategia:
- **sceglie** quali setup prendere guardando tutto il quadro del momento (`QUADRO`): le coppie di timeframe (CRT
  appena formati su 4 ore, giorno, settimana), dove sta il prezzo rispetto ai massimi e minimi di giorno, settimana e
  mese prima (presi o no), come hanno chiuso le ultime candele (accettato, rifiutato, inside), il momentum, la
  volatilita', l'ora e il giorno, quanto costa il trade rispetto allo stop;
- **decide quanto rischiare** in base a quanto e' sicuro.

Come si allena (ricerca del 13/10/2026, `documenti/spec/rete.md`): meta-labeling (la rete giudica i segnali di una
strategia), alberi LightGBM sulla scheda (i piu' forti sui dati a tabella), anni separati con un margine fra impara e
controllo (i trade durano fino a 30 giorni: niente sbirciate), l'esame si guarda una volta sola.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import TF, scarti_ny, utc

GIORNI_SCALA = 14
STORIA_GIORNI = 260
MARGINE = 31 * 86400   # fra gli anni per imparare e quelli per controllare: i trade durano fino a 30 giorni

_CLASSI = {
    "major": ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"),
    "metalli": ("XAUUSD", "XAGUSD"),
    "indici": ("SPX500", "NAS100", "US30", "GER40", "UK100", "JPN225", "DXY"),
    "energia": ("USOIL", "UKOIL"),
}
QUADRO = (
    [f"rendimento {g}g" for g in (1, 5, 20, 60, 250)] +
    [f"posizione {g}g" for g in (5, 20, 60, 250)] +
    ["volatilita' 14/60", "range su prezzo"] +
    [f"distanza {n}" for n in ("PDH", "PDL", "PWH", "PWL", "PMH", "PML")] +
    [f"preso {n}" for n in ("PDH", "PDL", "PWH", "PWL", "PMH", "PML")] +
    [f"chiusura {tf}" for tf in ("D1", "W1", "MN")] +
    [f"CRT {tf} {v}" for tf in ("H4", "D1", "W1") for v in ("long", "short")] +
    [f"candela H1 -{k} {c}" for k in (1, 2, 3) for c in ("corpo", "ombra su", "ombra giu")] +
    [f"candela H4 -{k} {c}" for k in (1, 2) for c in ("corpo", "ombra su", "ombra giu")] +
    ["ora sin", "ora cos", "giorno sin", "giorno cos", "costo su range"] +
    [f"classe {c}" for c in ("major", "cross", "metalli", "indici", "energia")])
# Le colonne che cambiano senso fra long e short: si aggiunge la loro versione "dalla nostra parte".
_SEGNO = [c for c in QUADRO if c.startswith(("rendimento", "chiusura", "candela")) and "ombra" not in c]


def classe(strumento: str) -> str:
    for c, nomi in _CLASSI.items():
        if strumento in nomi:
            return c
    return "cross"


def _ultime(c: Candele, t: np.ndarray) -> np.ndarray:
    return np.searchsorted(c.fine, t, side="right") - 1


def _bias(c: Candele, k: np.ndarray) -> np.ndarray:
    """Come ha chiuso l'ultima candela chiusa rispetto alla precedente (`foto.bias_candela`): +1 accetta sopra,
    -1 accetta sotto, -0,5 prende il massimo e chiude dentro, +0,5 prende il minimo e chiude dentro, 0 inside."""
    ok = k >= 1
    j, p = np.maximum(k, 1), np.maximum(k - 1, 0)
    al, ba, ch = c.bid[j, MASSIMO], c.bid[j, MINIMO], c.bid[j, CHIUSURA]
    pal, pba = c.bid[p, MASSIMO], c.bid[p, MINIMO]
    fuori = np.where(ch > pal, 1.0, np.where(ch < pba, -1.0, 0.0))
    preso_su, preso_giu, dentro = al > pal, ba < pba, (ch <= pal) & (ch >= pba)
    fuori = np.where(dentro & preso_su & ~preso_giu, -0.5, fuori)
    fuori = np.where(dentro & preso_giu & ~preso_su, 0.5, fuori)
    return np.where(ok, fuori, 0.0).astype(np.float32)


def _crt(c: Candele, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """L'ultima candela chiusa ha fatto la candela 2 di un CRT: preso il minimo (massimo) della precedente, chiusa
    dentro, l'altro lato non toccato."""
    ok = k >= 1
    j, p = np.maximum(k, 1), np.maximum(k - 1, 0)
    al, ba, ch = c.bid[j, MASSIMO], c.bid[j, MINIMO], c.bid[j, CHIUSURA]
    pal, pba = c.bid[p, MASSIMO], c.bid[p, MINIMO]
    dentro = (ch <= pal) & (ch >= pba)
    return (ok & dentro & (ba < pba) & (al <= pal)).astype(np.float32), \
        (ok & dentro & (al > pal) & (ba >= pba)).astype(np.float32)


def _periodo_finora(ore: Candele, c: Candele, k: np.ndarray, e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Massimo e minimo del periodo in corso (la candela k di `c`, non ancora chiusa) dalle ore chiuse prima di e."""
    al, ba = ore.bid[:, MASSIMO], ore.bid[:, MINIMO]
    alto, basso = np.full(len(e), np.nan), np.full(len(e), np.nan)
    dentro = k < len(c)
    inizio = np.searchsorted(ore.inizio, c.inizio[np.minimum(k, len(c) - 1)])
    for n in np.flatnonzero(dentro):
        a, b = int(inizio[n]), int(e[n])
        if b > a:
            alto[n], basso[n] = al[a:b].max(), ba[a:b].min()
    return alto, basso


def quadro(m: Minuti, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Il quadro a ogni istante di `t` (aperture di candele orarie), solo con le candele gia' chiuse: (quadro
    [N, len(QUADRO)], buoni [N] se c'era abbastanza storia)."""
    s = m.strumento
    ore = costruisci(m, TF.H1)
    h4, d1, w1, mn = (costruisci(m, tf) for tf in (TF.H4, TF.D1, TF.W1, TF.MN))
    t = np.asarray(t, np.int64)
    e = np.searchsorted(ore.inizio, t)
    kd = _ultime(d1, t)
    buoni = (e >= 4) & (e < len(ore)) & (kd >= STORIA_GIORNI)
    e, kd = np.where(buoni, e, 4), np.where(buoni, kd, STORIA_GIORNI)
    n = len(t)
    c0 = ore.bid[e - 1, CHIUSURA]
    dal_, dba, dch = d1.bid[:, MASSIMO], d1.bid[:, MINIMO], d1.bid[:, CHIUSURA]
    rng = dal_ - dba
    sc = rng[kd[:, None] - np.arange(GIORNI_SCALA)[None, :]].mean(axis=1)
    sc60 = rng[kd[:, None] - np.arange(60)[None, :]].mean(axis=1)
    sc = np.maximum(sc, 1e-12)
    q = np.zeros((n, len(QUADRO)), np.float32)
    col = {nome: i for i, nome in enumerate(QUADRO)}
    for g in (1, 5, 20, 60, 250):
        q[:, col[f"rendimento {g}g"]] = np.arcsinh((c0 - dch[kd - g]) / sc)
    for g in (5, 20, 60, 250):
        idx = kd[:, None] - np.arange(g)[None, :]
        alto, basso = dal_[idx].max(axis=1), dba[idx].min(axis=1)
        q[:, col[f"posizione {g}g"]] = (c0 - basso) / np.maximum(alto - basso, 1e-12)
    q[:, col["volatilita' 14/60"]] = np.log(sc / np.maximum(sc60, 1e-12))
    q[:, col["range su prezzo"]] = np.log(sc / np.abs(c0))
    for nome, c in (("D", d1), ("W", w1), ("M", mn)):
        k = _ultime(c, t)
        kk = np.maximum(k, 0)
        ph, pl = c.bid[kk, MASSIMO], c.bid[kk, MINIMO]
        q[:, col[f"distanza P{nome}H"]] = np.arcsinh((c0 - ph) / sc)
        q[:, col[f"distanza P{nome}L"]] = np.arcsinh((c0 - pl) / sc)
        alto, basso = _periodo_finora(ore, c, k + 1, e)
        with np.errstate(invalid="ignore"):
            q[:, col[f"preso P{nome}H"]] = (alto > ph).astype(np.float32)
            q[:, col[f"preso P{nome}L"]] = (basso < pl).astype(np.float32)
    for nome, c in (("D1", d1), ("W1", w1), ("MN", mn)):
        q[:, col[f"chiusura {nome}"]] = _bias(c, _ultime(c, t))
    for nome, c in (("H4", h4), ("D1", d1), ("W1", w1)):
        lo, sh = _crt(c, _ultime(c, t))
        q[:, col[f"CRT {nome} long"]], q[:, col[f"CRT {nome} short"]] = lo, sh
    for nome, c, quante in (("H1", ore, 3), ("H4", h4, 2)):
        kc = _ultime(c, t)
        for j in range(1, quante + 1):
            kk = np.maximum(kc - j + 1, 0)
            o, a, b, ch = (c.bid[kk, x] for x in (APERTURA, MASSIMO, MINIMO, CHIUSURA))
            q[:, col[f"candela {nome} -{j} corpo"]] = (ch - o) / sc
            q[:, col[f"candela {nome} -{j} ombra su"]] = (a - np.maximum(o, ch)) / sc
            q[:, col[f"candela {nome} -{j} ombra giu"]] = (np.minimum(o, ch) - b) / sc
    locale = t + scarti_ny(t)
    ora_ny = (locale % 86400) / 3600.0
    giorno = (locale // 86400 + 3) % 7  # 0 = lunedi'
    q[:, col["ora sin"]], q[:, col["ora cos"]] = np.sin(2 * np.pi * ora_ny / 24), np.cos(2 * np.pi * ora_ny / 24)
    q[:, col["giorno sin"]], q[:, col["giorno cos"]] = np.sin(2 * np.pi * giorno / 7), np.cos(2 * np.pi * giorno / 7)
    commissione = STRUMENTI[s].commissione if s in STRUMENTI else 0.0
    spread = np.maximum(ore.ask[e, APERTURA] - ore.bid[e, APERTURA], 0)
    q[:, col["costo su range"]] = (spread + commissione) / sc
    q[:, col[f"classe {classe(s)}"]] = 1.0
    return np.nan_to_num(q, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32), buoni


def dalla_nostra_parte(q: np.ndarray, vendita: np.ndarray) -> np.ndarray:
    """Le colonne con un verso, girate in modo che + voglia dire "a favore del trade"; i CRT a favore e contro; la
    posizione nel range contata dal lato giusto."""
    s = np.where(vendita > 0.5, -1.0, 1.0).astype(np.float32)[:, None]
    col = {nome: i for i, nome in enumerate(QUADRO)}
    parti = [q[:, [col[c] for c in _SEGNO]] * s]
    corto = vendita > 0.5
    for tf in ("H4", "D1", "W1"):
        lo, sh = q[:, col[f"CRT {tf} long"]], q[:, col[f"CRT {tf} short"]]
        parti.append(np.where(corto, sh, lo)[:, None])
        parti.append(np.where(corto, lo, sh)[:, None])
    for g in (5, 20, 60, 250):
        p = q[:, col[f"posizione {g}g"]]
        parti.append(np.where(corto, 1 - p, p)[:, None])
    return np.concatenate(parti, axis=1).astype(np.float32)


NOMI_DALLA_NOSTRA = ([f"{c} (a favore)" for c in _SEGNO] +
                     [f"CRT {tf} {x}" for tf in ("H4", "D1", "W1") for x in ("a favore", "contro")] +
                     [f"posizione {g}g (dal lato giusto)" for g in (5, 20, 60, 250)])


# --- preparazione: il quadro di ogni setup della strategia --------------------------------------------------------

def prepara(radice: Path, file_casi: Path, uscita: Path, con_spread=None, scrivi=print) -> None:
    """Per ogni setup di `file_casi` (`prepara_casi`) il quadro del momento, dallo storico di `radice`."""
    from kaggle_rete.histdata import pezzi_buoni
    from nvm.dati.ore import carica
    f = np.load(file_casi)
    strumenti, t_tutti = f["strumento"], f["t"]
    q_tutti = np.zeros((len(t_tutti), len(QUADRO)), np.float32)
    ok_tutti = np.zeros(len(t_tutti), bool)
    for s in np.unique(strumenti):
        inizio = time.time()
        if not (radice / "ore_bid" / str(s)).exists() and not (radice / "ore" / str(s)).exists():
            scrivi(f"{s}: manca lo storico")
            continue
        m, _ = carica(radice, str(s), utc(1999, 1, 1), utc(2100, 1, 1), solo_bid=True)
        pezzi, _ = pezzi_buoni(m)
        dove = np.flatnonzero(strumenti == s)
        for p in pezzi:
            if con_spread is not None:
                p = con_spread(p)
            dentro = dove[(t_tutti[dove] >= p.t[0]) & (t_tutti[dove] <= p.t[-1])]
            if len(dentro):
                q, buoni = quadro(p, t_tutti[dentro])
                q_tutti[dentro], ok_tutti[dentro] = q, buoni
        scrivi(f"{s}: {int(ok_tutti[dove].sum())} setup su {len(dove)} col quadro ({time.time() - inizio:.0f} s)")
    k = np.flatnonzero(ok_tutti)
    extra = {"fine": f["fine"][k]} if "fine" in f.files else {}
    np.savez_compressed(uscita, strumento=strumenti[k], t=t_tutti[k], scheda=f["scheda"][k], quadro=q_tutti[k],
                        erre=f["erre"][k], uscita=f["uscita"][k], **extra)
    scrivi(f"{len(k)} setup col quadro in {uscita}")


# --- la scuola e la prova ---------------------------------------------------------------------------------------

def tabella(f) -> tuple[np.ndarray, list[str]]:
    from kaggle_rete.esperienza import SCHEDA
    from kaggle_rete.trader import prepara_scheda
    sc = f["scheda"]
    vendita = sc[:, SCHEDA.index("vendita")]
    x = np.concatenate([prepara_scheda(sc), f["quadro"], dalla_nostra_parte(f["quadro"], vendita)], axis=1)
    return x, list(SCHEDA) + list(QUADRO) + NOMI_DALLA_NOSTRA


def scuola(x: np.ndarray, y: np.ndarray, impara: np.ndarray, controlla: np.ndarray, semi=(1, 2, 3), scrivi=print):
    """Una piccola squadra di LightGBM (semi diversi), regolati forte: con 20 anni di setup e poco segnale un
    modello libero impara a memoria."""
    import lightgbm as lgb
    yc = np.clip(y, -1.5, 4.0)
    squadra = []
    for seme in semi:
        regole = {"objective": "huber", "alpha": 1.0, "learning_rate": 0.02, "num_leaves": 15,
                  "min_data_in_leaf": 1000, "bagging_fraction": 0.6, "bagging_freq": 1, "feature_fraction": 0.6,
                  "lambda_l2": 10.0, "seed": seme, "verbose": -1}
        dentro = lgb.Dataset(x[impara], yc[impara])
        prova_ = lgb.Dataset(x[controlla], yc[controlla], reference=dentro)
        m = lgb.train(regole, dentro, num_boost_round=2000, valid_sets=[prova_],
                      callbacks=[lgb.early_stopping(100, verbose=False)])
        scrivi(f"  albero {seme}: {m.best_iteration} passi")
        squadra.append(m)
    return squadra


def stima(squadra, x: np.ndarray) -> np.ndarray:
    return np.mean([m.predict(x, num_iteration=m.best_iteration) for m in squadra], axis=0).astype(np.float32)


def soglia(stimato: np.ndarray, erre: np.ndarray, minimo: int = 300) -> tuple[float, str]:
    """Quanto essere esigenti, scelto sul controllo: fra il 2, 5, 10, 20, 30 e 50% migliore, quello con l'R medio piu'
    alto (almeno `minimo` setup)."""
    meglio = (-np.inf, np.inf, "")
    ordinati = np.sort(stimato)[::-1]
    for quota in (0.02, 0.05, 0.10, 0.20, 0.30, 0.50):
        n = int(len(stimato) * quota)
        if n < minimo:
            continue
        s = float(ordinati[n - 1])
        r = float(erre[stimato >= s].mean())
        if r > meglio[0]:
            meglio = (r, s, f"il {quota:.0%} migliore")
    return meglio[1], meglio[2]


def riga(erre: np.ndarray, t: np.ndarray, dal: int, al: int, peso: np.ndarray | None = None) -> dict:
    peso = np.ones(len(erre)) if peso is None else peso
    e = erre * peso
    anni = t.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    per_anno = {int(a): round(float(e[anni == a].sum()), 1) for a in np.unique(anni)}
    curva = np.cumsum(e[np.argsort(t)]) if len(e) else np.zeros(1)
    calo = float(np.max(np.maximum.accumulate(curva) - curva)) if len(e) else 0.0
    return {"setup": int(len(e)), "a settimana": round(len(e) / max((al - dal) / (7 * 86400), 1e-9), 1),
            "R medio": round(float(e.mean()), 3) if len(e) else None,
            "R totale": round(float(e.sum()), 1), "vinti": round(float((erre > 0).mean()), 3) if len(e) else None,
            "anni in guadagno": f"{sum(v > 0 for v in per_anno.values())}/{len(per_anno)}",
            "calo peggiore R": round(calo, 1), "per anno": per_anno}


def una_per_strumento(strumento: np.ndarray, t: np.ndarray, fine: np.ndarray, scelti: np.ndarray,
                      stimato: np.ndarray) -> np.ndarray:
    """La regola del proprietario: al massimo una posizione aperta per strumento. Fra i setup scelti, in ordine di
    tempo (a parita' di tempo prima il piu' convinto), si apre solo se lo strumento e' libero."""
    aperti = np.zeros(len(t), bool)
    for s in np.unique(strumento[scelti]):
        k = scelti[strumento[scelti] == s]
        k = k[np.lexsort((-stimato[k], t[k]))]
        libero = -1
        for i in k:
            if t[i] >= libero:
                aperti[i] = True
                libero = fine[i]
    return aperti


def prova(file: Path, impara_al: int, controllo_al: int, fuori_al: int, uscita: Path | None = None,
          scrivi=print) -> dict:
    """Impara fino a `impara_al` (meno il margine), sceglie la soglia sul controllo fino a `controllo_al`, poi
    misura una volta sul pezzo fuori fino a `fuori_al`: la strategia presa tutta, il bot (A+), Nameless, Nameless
    con la puntata secondo la fiducia."""
    from kaggle_rete.esperienza import SCHEDA
    f = np.load(file)
    x, nomi = tabella(f)
    y, t = f["erre"].astype(np.float32), f["t"]
    impara = np.flatnonzero(t < impara_al - MARGINE)
    controlla = np.flatnonzero((t >= impara_al) & (t < controllo_al - MARGINE))
    fuori = np.flatnonzero((t >= controllo_al) & (t < fuori_al))
    scrivi(f"setup: impara {len(impara)}, controllo {len(controlla)}, fuori {len(fuori)}")
    squadra = scuola(x, y, impara, controlla, scrivi=scrivi)
    stimato = stima(squadra, x)
    s, quale = soglia(stimato[controlla], y[controlla])
    a_piu = f["scheda"][:, SCHEDA.index("A+")] > 0.5
    # La puntata: 0,5 / 1 / 1,5 volte secondo il terzo della stima fra i setup presi al controllo.
    presi_c = stimato[controlla][stimato[controlla] >= s]
    t1, t2 = (np.quantile(presi_c, [1 / 3, 2 / 3]) if len(presi_c) >= 3 else (s, s))
    def peso(k):
        return np.where(stimato[k] >= t2, 1.5, np.where(stimato[k] >= t1, 1.0, 0.5))
    r = {"soglia": [float(s), quale]}
    for nome, idx, dal, al in (("controllo", controlla, impara_al, controllo_al), ("fuori", fuori, controllo_al, fuori_al)):
        presi = idx[stimato[idx] >= s]
        r[nome] = {"la strategia, tutti i setup": riga(y[idx], t[idx], dal, al),
                   "il bot (A+)": riga(y[idx[a_piu[idx]]], t[idx[a_piu[idx]]], dal, al),
                   "Nameless": riga(y[presi], t[presi], dal, al),
                   "Nameless con la puntata": riga(y[presi], t[presi], dal, al, peso(presi))}
        if "fine" in f.files:
            st = f["strumento"]
            bot1 = np.flatnonzero(una_per_strumento(st, t, f["fine"], idx[a_piu[idx]], stimato))
            nm1 = np.flatnonzero(una_per_strumento(st, t, f["fine"], presi, stimato))
            r[nome]["il bot (A+), uno per strumento"] = riga(y[bot1], t[bot1], dal, al)
            r[nome]["Nameless, uno per strumento"] = riga(y[nm1], t[nm1], dal, al)
            r[nome]["Nameless, uno per strumento, puntata"] = riga(y[nm1], t[nm1], dal, al, peso(nm1))
    imp = np.mean([m.feature_importance("gain") for m in squadra], axis=0)
    r["cosa guarda di piu'"] = [nomi[i] for i in np.argsort(-imp)[:15]]
    for nome in ("controllo", "fuori"):
        scrivi(f"\n{nome.upper()}:")
        for k, v in r[nome].items():
            scrivi(f"  {k:30s} {v['a settimana']:6.1f}/sett  R medio {v['R medio']}  totale {v['R totale']:+8.1f}  "
                   f"vinti {v['vinti']}  anni in guadagno {v['anni in guadagno']}  calo peggiore {v['calo peggiore R']}")
    scrivi("cosa guarda di piu': " + ", ".join(r["cosa guarda di piu'"]))
    if uscita is not None:
        uscita.write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
    return r
