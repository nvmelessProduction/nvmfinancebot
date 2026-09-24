"""Fase 2: i pesi, e il protocollo che decide se valgono qualcosa.

## Cosa fa, in ordine

1. Legge il campo di prova e ci attacca i blocchi del campione efficace.
2. **Walk-forward**: allena su tutto cio' che precede un anno, decide su
   quell'anno, e passa al successivo. Nessuna riga viene mai giudicata da un
   modello che l'ha vista.
3. Applica la regola d'ingresso `p x RR - (1 - p) - costi > 0` e raccoglie gli
   R delle operazioni prese fuori campione.
4. Li confronta con le due linee -- `B0`, prendere tutti i CRT, e `B1`, il
   filtro in AND che il bot usa oggi -- con l'intervallo al 95% a blocchi.
5. Dice se i criteri del protocollo sono soddisfatti. **Tutti**, non la
   maggioranza.

## I criteri, e perche' sono cosi' severi

    battere B0 di almeno 0,10 R
    intervallo al 95% sulla differenza che ESCLUDE lo zero
    almeno 7 anni su 10 in positivo
    almeno 300 operazioni fuori campione
    segno del peso stabile in almeno l'80% delle finestre

Non sono severi per prudenza generica: sono severi perche' questo progetto ha
gia' prodotto cinque falsi positivi, e tutti e cinque avevano lo stesso
aspetto -- un numero troppo bello su un campione che sembrava grande.

Il criterio del **segno stabile** e' quello che nessun altro copre. Un peso
che cambia segno fra le finestre non sta misurando una proprieta' del mercato:
sta inseguendo il rumore di quella finestra, e fuori campione fara' la meta'
delle volte il contrario di quello che ci si aspetta.

## L'holdout

Non si tocca. Il walk-forward gira su 2006-2023 e basta. Il 2024-2026 si apre
una volta sola, alla fine, quando c'e' un candidato da confermare -- e se lo
si guarda due volte non e' piu' un holdout, e' un secondo insieme di prova su
cui si e' scelto.

## Uso

    python backtest/addestra.py
    python backtest/addestra.py --lambda 1.0 --primo-anno 2010
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bootstrap                                               # noqa: E402
from campione_efficace import blocchi as etichette_blocco      # noqa: E402
from regressione import (                                      # noqa: E402
    LAMBDA, adatta, brier, brier_di_riferimento, previsione,
)

from core.parametri import CONFERME_CHE_BLOCCANO_DA_SOLE       # noqa: E402
from core.pesi import (                                        # noqa: E402
    LE_OTTO, Pesi, caratteristiche_numeriche, nomi_delle_colonne, salva,
)

# I criteri del protocollo. Stanno qui in cima e in chiaro perche' un criterio
# che si puo' cambiare mentre si guarda il risultato non e' un criterio.
GUADAGNO_MINIMO: float = 0.10          # R sopra B0
ANNI_POSITIVI_MINIMI: float = 0.70     # 7 su 10
OPERAZIONI_MINIME: int = 300           # fuori campione
STABILITA_MINIMA: float = 0.80         # segno del peso

# Il primo anno su cui si decide. Prima si allena soltanto: con due anni di
# storia il modello non ha visto abbastanza per essere giudicato.
PRIMO_ANNO: int = 2010
ULTIMO_ANNO: int = 2023                # l'holdout comincia nel 2024


@dataclass
class Finestra:
    """Un anno deciso fuori campione."""

    anno: int
    allenata_su: int
    candidate: int
    prese: int
    erre_prese: list[float]
    blocchi_presi: list[str]
    erre_tutte: list[float]
    blocchi_tutte: list[str]
    brier_modello: float
    brier_base: float
    pesi: dict[str, float]


def leggi(percorso: Path) -> list[dict]:
    with percorso.open(encoding="utf-8", newline="") as f:
        righe = list(csv.DictReader(f))
    if righe and "costo_erre" not in righe[0]:
        raise SystemExit(
            "il campo di prova non ha la colonna `costo_erre`: rigeneralo "
            "con `python backtest/campo_prova.py`")
    return righe


def _responso(riga: dict) -> dict:
    """Dal CSV al responso, con `None` che resta `None`."""
    fuori: dict[str, Optional[bool]] = {}
    for regola in LE_OTTO:
        valore = riga[regola]
        fuori[regola] = None if valore == "" else (valore == "1")
    return fuori


def matrice(righe: Sequence[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Le caratteristiche e le etichette, con la codifica di `core/pesi.py`.

    La codifica viene da li' e non da qui: e' il punto in cui due copie della
    stessa regola divergerebbero, e i pesi sarebbero giusti per un mondo e
    applicati a un altro.
    """
    X, y = [], []
    for r in righe:
        allineati = None if r["allineati"] == "" else int(r["allineati"])
        X.append(caratteristiche_numeriche(
            _responso(r), allineati, float(r["rapporto"])))
        y.append(1.0 if r["esito"] == "target" else 0.0)
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


def b1_il_filtro_di_oggi(riga: dict) -> bool:
    """`B1` — quello che il bot lascerebbe passare oggi.

    Le conferme accese in `CONFERME_CHE_BLOCCANO_DA_SOLE` fermano
    l'operazione quando rispondono `False`. `None` non blocca mai:
    trasformare "non lo so" in "no" spegnerebbe il bot senza dirlo, ed e'
    esattamente la regola che il motore applica.

    La tabella si legge dal bot, non si ricopia: se domani si accende o si
    spegne una conferma, questa linea si muove da sola.
    """
    for regola, blocca in CONFERME_CHE_BLOCCANO_DA_SOLE.items():
        if blocca and riga[regola] == "0":
            return False
    return True


def cammina(
    righe: list[dict], blocchi: list[str], penalita: float,
    primo_anno: int, ultimo_anno: int, margine: float,
) -> list[Finestra]:
    """Il walk-forward: si allena sul passato, si decide sul futuro."""
    per_anno: dict[int, list[int]] = defaultdict(list)
    for indice, r in enumerate(righe):
        per_anno[datetime.fromisoformat(r["quando"]).year].append(indice)

    finestre: list[Finestra] = []
    nomi = nomi_delle_colonne()
    for anno in range(primo_anno, ultimo_anno + 1):
        prima = [i for a, ind in per_anno.items() if a < anno for i in ind]
        adesso = per_anno.get(anno, [])
        if len(prima) < 200 or not adesso:
            continue

        X_tr, y_tr = matrice([righe[i] for i in prima])
        stima = adatta(X_tr, y_tr, penalita=penalita)

        X_te, y_te = matrice([righe[i] for i in adesso])
        p = previsione(stima, X_te)

        prese_erre, prese_blocchi = [], []
        tutte_erre, tutte_blocchi = [], []
        for posto, indice in enumerate(adesso):
            r = righe[indice]
            erre = float(r["erre"])
            tutte_erre.append(erre)
            tutte_blocchi.append(blocchi[indice])
            rr = float(r["rapporto"])
            costo = float(r["costo_erre"])
            atteso = p[posto] * rr - (1.0 - p[posto]) - costo
            if atteso > margine:
                prese_erre.append(erre)
                prese_blocchi.append(blocchi[indice])

        finestre.append(Finestra(
            anno=anno, allenata_su=len(prima), candidate=len(adesso),
            prese=len(prese_erre), erre_prese=prese_erre,
            blocchi_presi=prese_blocchi, erre_tutte=tutte_erre,
            blocchi_tutte=tutte_blocchi,
            brier_modello=brier(p, y_te), brier_base=brier_di_riferimento(y_te),
            pesi=dict(zip(nomi, stima.pesi))))
    return finestre


def stabilita_dei_segni(finestre: list[Finestra]) -> dict[str, float]:
    """Per ogni colonna, in che frazione di finestre il segno e' lo stesso.

    Un peso che cambia segno fra le finestre non sta misurando una proprieta'
    del mercato: sta inseguendo il rumore di quella finestra. E' il criterio
    che nessun altro copre, perche' un modello puo' essere ottimo in media e
    instabile in tutto.
    """
    fuori: dict[str, float] = {}
    for nome in nomi_delle_colonne():
        segni = [np.sign(f.pesi.get(nome, 0.0)) for f in finestre]
        segni = [s for s in segni if s != 0]
        if not segni:
            fuori[nome] = 0.0
            continue
        conta = Counter(segni)
        fuori[nome] = conta.most_common(1)[0][1] / len(finestre)
    return fuori


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dati", default="dati/campo_prova.csv")
    p.add_argument("--penalita", type=float, default=LAMBDA)
    p.add_argument("--primo-anno", type=int, default=PRIMO_ANNO)
    p.add_argument("--ultimo-anno", type=int, default=ULTIMO_ANNO)
    p.add_argument("--margine", type=float, default=0.0,
                   help="quanto valore atteso serve per prendere un CRT")
    p.add_argument("--giri", type=int, default=bootstrap.GIRI)
    p.add_argument("--salva", default=None,
                   help="dove scrivere i pesi finali (JSON)")
    a = p.parse_args()

    percorso = Path(a.dati)
    if not percorso.exists():
        print(f"manca {percorso}: gira prima backtest/campo_prova.py")
        return 2
    righe = leggi(percorso)
    blocchi = etichette_blocco(righe)
    print(f"{len(righe):,} CRT, {len(set(blocchi)):,} blocchi indipendenti")
    print(f"penalita' L2 = {a.penalita}, margine = {a.margine:+.3f} R")
    print()

    finestre = cammina(righe, blocchi, a.penalita, a.primo_anno,
                       a.ultimo_anno, a.margine)
    if not finestre:
        print("nessuna finestra: troppo pochi dati prima del primo anno")
        return 1

    print("=== walk-forward: si allena sul passato, si decide sul futuro ===")
    print(f"  {'anno':>5} {'allenata su':>12} {'candidate':>10} "
          f"{'prese':>7} {'R medio':>10} {'Brier':>8} {'base':>8}")
    for f in finestre:
        medio = np.mean(f.erre_prese) if f.erre_prese else float("nan")
        print(f"  {f.anno:>5} {f.allenata_su:>12,} {f.candidate:>10,} "
              f"{f.prese:>7,} {medio:>+10.4f} {f.brier_modello:>8.4f} "
              f"{f.brier_base:>8.4f}")
    print()

    prese = [e for f in finestre for e in f.erre_prese]
    prese_blocchi = [b for f in finestre for b in f.blocchi_presi]
    tutte = [e for f in finestre for e in f.erre_tutte]
    tutte_blocchi = [b for f in finestre for b in f.blocchi_tutte]

    # `B1` sugli stessi anni del walk-forward: confrontare una linea su
    # vent'anni con un modello su quattordici direbbe soprattutto quali anni
    # sono capitati a chi.
    anni = {f.anno for f in finestre}
    b1_erre, b1_blocchi = [], []
    for indice, r in enumerate(righe):
        if datetime.fromisoformat(r["quando"]).year not in anni:
            continue
        if b1_il_filtro_di_oggi(r):
            b1_erre.append(float(r["erre"]))
            b1_blocchi.append(blocchi[indice])

    print("=== le linee, sugli stessi anni ===")
    for nome, valori, gruppi in (
            ("B0  tutti i CRT", tutte, tutte_blocchi),
            ("B1  il filtro di oggi", b1_erre, b1_blocchi),
            ("modello", prese, prese_blocchi)):
        if not valori:
            print(f"  {nome:24} nessuna operazione")
            continue
        punto, basso, alto = bootstrap.intervallo(
            valori, gruppi, giri=a.giri)
        print(f"  {nome:24} {len(valori):>7,} op  {punto:>+8.4f} R  "
              f"[{basso:+.4f}, {alto:+.4f}]")
    print()

    if not prese:
        print("il modello non prende NIENTE: nessun CRT supera la regola "
              "d'ingresso. Non e' un errore, e' una risposta.")
        return 0

    print("=== i criteri del protocollo (tutti, non la maggioranza) ===")
    esiti: list[tuple[str, bool, str]] = []

    punto, basso, alto = bootstrap.differenza(
        prese, prese_blocchi, tutte, tutte_blocchi, giri=a.giri)
    esiti.append((
        f"batte B0 di >= {GUADAGNO_MINIMO:.2f} R",
        punto >= GUADAGNO_MINIMO,
        f"{punto:+.4f} R"))
    esiti.append((
        "l'intervallo al 95% esclude lo zero",
        bootstrap.esclude_lo_zero(basso, alto),
        f"[{basso:+.4f}, {alto:+.4f}]"))

    positivi = sum(1 for f in finestre
                   if f.erre_prese and np.mean(f.erre_prese) > 0)
    esiti.append((
        f"anni in positivo >= {ANNI_POSITIVI_MINIMI:.0%}",
        positivi >= ANNI_POSITIVI_MINIMI * len(finestre),
        f"{positivi} su {len(finestre)}"))

    esiti.append((
        f"operazioni fuori campione >= {OPERAZIONI_MINIME}",
        len(prese) >= OPERAZIONI_MINIME,
        f"{len(prese):,}"))

    stabilita = stabilita_dei_segni(finestre)
    # Solo le colonne che pesano davvero: il segno di un peso nullo non dice
    # niente, e pretenderne la stabilita' boccerebbe ogni modello.
    forti = [n for n in nomi_delle_colonne()
             if abs(np.mean([f.pesi.get(n, 0.0) for f in finestre])) > 0.01]
    instabili = [n for n in forti if stabilita[n] < STABILITA_MINIMA]
    esiti.append((
        f"segno stabile in >= {STABILITA_MINIMA:.0%} delle finestre",
        not instabili,
        "tutte stabili" if not instabili
        else f"instabili: {', '.join(instabili)}"))

    brier_medio = float(np.mean([f.brier_modello for f in finestre]))
    base_media = float(np.mean([f.brier_base for f in finestre]))
    esiti.append((
        "il Brier batte la frequenza di base",
        brier_medio < base_media,
        f"{brier_medio:.4f} contro {base_media:.4f}"))

    for nome, passa, dettaglio in esiti:
        print(f"  [{'x' if passa else ' '}] {nome:42} {dettaglio}")
    print()

    if all(passa for _, passa, _ in esiti):
        print("TUTTI i criteri passano. Il candidato puo' andare all'holdout, "
              "e l'holdout si guarda UNA volta sola.")
    else:
        mancano = [n for n, passa, _ in esiti if not passa]
        print(f"NON promuovibile: {len(mancano)} criteri su {len(esiti)} non "
              f"passano.")
        print("Non e' un guasto: e' il protocollo che fa il suo mestiere.")
    print()

    print("=== la stabilita' dei segni, colonna per colonna ===")
    for nome in nomi_delle_colonne():
        medio = float(np.mean([f.pesi.get(nome, 0.0) for f in finestre]))
        segnale = "" if abs(medio) > 0.01 else "   (peso trascurabile)"
        print(f"  {nome:18} peso medio {medio:+.4f}   "
              f"stabile {stabilita[nome]:.0%}{segnale}")

    if a.salva:
        X, y = matrice(righe)
        finale = adatta(X, y, penalita=a.penalita)
        pesi = Pesi(intercetta=finale.intercetta,
                    per_colonna=dict(zip(nomi_delle_colonne(), finale.pesi)),
                    addestrato_su=f"{a.primo_anno}-{a.ultimo_anno}",
                    righe=len(righe),
                    brier=brier(previsione(finale, X), y))
        salva(pesi, Path(a.salva))
        print()
        print(f"pesi scritti in {a.salva}")
        print(pesi.leggibile())
    return 0


if __name__ == "__main__":
    sys.exit(main())
