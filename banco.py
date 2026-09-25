"""Il banco di prova delle domande nuove per gli agenti.

    python banco.py liquidita       # un gruppo di `nvm/prova/domande.py`
    python banco.py orario cacciatore bias

Per ogni domanda, due misure:

1. **Romeo.** Fra i candidati del 2023 (le coppie del bot dal vivo, come in
   `romeo.py`), quanto spesso la risposta e' si' nelle scelte di Romeo e
   negli altri, e quanto la somiglianza a Romeo lo riconosce fuori campione
   con questa risposta in piu' (AUC, quattro gruppi casuali, 50 volte).
2. **Vent'anni.** Sulla tabella della configurazione 1 (2006-2023), il Capo
   allenato anno per anno con e senza la domanda: stima del primo target
   (log-loss) e R delle sue scelte, anno per anno.

Serve a decidere se una domanda entra negli agenti. Le domande gia' negli
agenti (per esempio la liquidita' presa) qui non cambiano niente: il Capo
di oggi le ha gia'. Ogni prova va nel registro (`registro/tentativi.md`),
anche quando va male.
"""

from __future__ import annotations

import argparse

import numpy as np

from capo import AL, COPPIE, DAL, RADICE, _istante, tabella
from nvm.agenti import capo as il_capo, manopole
from nvm.agenti.capo import COLONNE_ROMEO, Capo, Logistica
from nvm.dati.candele import costruisci
from nvm.dati.minuti import carica_periodo
from nvm.dati.strumenti import BASE
from nvm.dati.ore import carica as carica_ore
from nvm.prova.base import opera
from nvm.prova.cammino import _inizio_anno
from nvm.prova.domande import GRUPPI, Contesto
from nvm.prova.romeo import COPPIA_MINUTI, COPPIE_ORE, candidati, etichette, leggi
from nvm.tempo import TF

PENALITA = 10.0
RIPETIZIONI = 50


def contesto(base, fine: int) -> Contesto:
    return Contesto(*(costruisci(base, tf).chiuse_entro(fine) for tf in (TF.H1, TF.H4, TF.D1, TF.W1, TF.MN)))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    """L'area sotto la curva, con i pari merito al rango medio."""
    _, inverso, quanti = np.unique(p, return_inverse=True, return_counts=True)
    rango = (np.cumsum(quanti) - (quanti - 1) / 2)[inverso]
    n1 = int(y.sum())
    return float((rango[y].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1)))


def riconosce(a: np.ndarray, y: np.ndarray, seme: int = 0) -> float:
    rng = np.random.default_rng(seme)
    valori = []
    for _ in range(RIPETIZIONI):
        gruppo = rng.integers(0, 4, len(y))
        p = np.zeros(len(y))
        for g in range(4):
            prova = gruppo == g
            media, scala = a[~prova].mean(0), a[~prova].std(0)
            scala[scala == 0] = 1
            l = Logistica(PENALITA).allena((a[~prova] - media) / scala, y[~prova].astype(float))
            p[prova] = l.probabilita((a[prova] - media) / scala)
        valori.append(auc(p, y))
    return float(np.mean(valori))


def romeo(domande) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    radice = RADICE / "dati" / "grezzi"
    entrate = [e for e in leggi(RADICE / "casi" / "entrate-romeo.csv") if e.periodo == "studio" and e.strumento in BASE]
    xs, ys, ds, tp = [], [], [], []
    for s in sorted({e.strumento for e in entrate}):
        ore, _ = carica_ore(radice, s, _istante(2021), _istante(2024) + 60 * 86400)
        minuti = carica_periodo(radice / "minuti", s, _istante(2023), _istante(2024))
        fine = int(ore.t[-1]) + ore.passo
        c = contesto(ore, fine)
        ops, x = candidati(ore, minuti, _istante(2023), _istante(2024))
        basse = {coppia: costruisci(ore, coppia[1]).chiuse_entro(fine) for coppia in COPPIE_ORE}
        if len(minuti):
            basse[COPPIA_MINUTI] = costruisci(minuti, COPPIA_MINUTI[1]).chiuse_entro(int(minuti.t[-1]) + minuti.passo)
        ds += [domande(r, basse[(r.alto_tf, r.basso_tf)], c) for r in ops]
        tp += [r.tp1_preso for r in ops]
        xs.append(x)
        ys.append(etichette([e for e in entrate if e.strumento == s], ops))
    return np.vstack(xs), np.concatenate(ys), np.array(ds, float), np.array(tp, bool)


def vent_anni(domande) -> np.ndarray:
    """Le risposte sulle operazioni della configurazione 1, nell'ordine della sua tabella."""
    radice = RADICE / "dati" / "grezzi"
    t = tabella(1, 1.0, radice)
    dal, al = _istante(DAL), _istante(AL + 1)
    risposte, quando = [], []
    for s in BASE:
        base, _ = carica_ore(radice, s, dal - 70 * 86400, al + 70 * 86400)
        fine = int(base.t[-1]) + base.passo
        c = contesto(base, fine)
        for alto, basso in COPPIE:
            alte, basse = costruisci(base, alto).chiuse_entro(fine), costruisci(base, basso).chiuse_entro(fine)
            for r in opera(alte, basse, dal, al):
                risposte.append(domande(r, basse, c))
                quando.append(r.quando)
    if not np.array_equal(np.array(quando), t.quando):
        raise RuntimeError("le operazioni non sono quelle della tabella: va ricostruita")
    return np.array(risposte, float)


def cammino(t, x: np.ndarray) -> tuple[float, int, float, list[float]]:
    anni = t.anno
    p1 = np.full(len(t), np.nan)
    qualita = np.full(len(t), np.nan)
    for a in range(2008, AL + 1):
        oggi = anni == a
        passato = t.chiusa < _inizio_anno(a)
        capo = Capo.allena(x[passato], t.tp1[passato], t.tp2[passato])
        p1[oggi] = capo.probabilita(x[oggi])[0]
        qualita[oggi] = capo.qualita(x[oggi], t.rr1[oggi], t.rr2[oggi], t.costi[oggi])
    giudicati = anni >= 2008
    y, p = t.tp1[giudicati], np.clip(p1[giudicati], 1e-6, 1 - 1e-6)
    scelte = giudicati & (qualita > il_capo.SOGLIA)
    per_anno = [float(t.erre[scelte & (anni == a)].mean()) for a in range(2008, AL + 1)]
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), int(scelte.sum()), float(t.erre[scelte].sum()), per_anno


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gruppi", nargs="+", choices=sorted(GRUPPI))
    a = parser.parse_args()
    manopole.carica_e_applica()
    t = tabella(1, 1.0, RADICE / "dati" / "grezzi")
    base = cammino(t, t.x)
    for nome in a.gruppi:
        nomi, domande = GRUPPI[nome]
        x, y, d, tp1 = romeo(domande)
        r = x[:, list(COLONNE_ROMEO)]
        print(f"== {nome}\n2023: {len(y)} candidati, {int(y.sum())} scelte di Romeo; "
              f"la somiglianza di oggi le riconosce a {riconosce(r, y):.3f}")
        print(f"  {'':36} {'Romeo':>6} {'altri':>6} {'1° target sì':>13} {'no':>6}  riconosce")
        for i, n in enumerate(nomi):
            si = d[:, i] != 0
            print(f"  {n:36} {d[y, i].mean():6.2f} {d[~y, i].mean():6.2f} {tp1[si].mean() if si.any() else np.nan:13.2f} "
                  f"{tp1[~si].mean():6.2f}  {riconosce(np.c_[r, d[:, i]], y):.3f}")
        v = vent_anni(domande)
        print(f"20 anni, il Capo di oggi: log-loss {base[0]:.5f}, scelte {base[1]}, R totale {base[2]:+.0f}")
        for i, n in enumerate(nomi):
            con = cammino(t, np.c_[t.x, v[:, i]])
            meglio = sum(x > y for x, y in zip(con[3], base[3]))
            si = v[:, i] != 0
            print(f"  + {n:34} {si.mean():4.0%} dei casi, 1° target {t.tp1[si].mean():.2f}/{t.tp1[~si].mean():.2f}  "
                  f"log-loss {con[0] - base[0]:+.5f}  R totale {con[2]:+.0f}  meglio in {meglio}/{len(con[3])} anni")


if __name__ == "__main__":
    main()
