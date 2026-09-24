"""Gli agenti fanno carriera, tutti insieme, ognuno nel suo ambito.

## Come si passa di grado

Per ogni agente, per ogni candidato della sua griglia, lo stesso
walk-forward del modello centrale: si sceglie il candidato migliore **sul
passato**, lo si applica all'anno successivo, e si misura li'. Il numero che
conta e' quello degli anni in cui l'agente non aveva ancora visto niente.

Poi il cancello di `core/apprendimento.py`, tutto intero:

    casi fuori campione >= campioni_minimi
    guadagno >= guadagno_minimo, sul manuale
    intervallo al 95% a blocchi che esclude lo zero
    segno stabile in almeno l'80% delle finestre

Chi non passa resta neolaureato, e il bot si comporta come oggi.

## I sorvegliati speciali

Un agente con peso globale nullo puo' avere ragione **dentro una fetta** --
su uno strumento solo, su una coppia sola -- e una misura globale lo
seppellisce. E' un'obiezione giusta e questo modulo la prende sul serio: ogni
candidato viene misurato anche per strumento e per coppia, e chi e' forte da
qualche parte ma nullo in media finisce in un elenco a parte.

Quell'elenco **non promuove nessuno**. Serve a non dimenticarsene: un effetto
di fetta va poi cercato apposta, con i suoi dati e il suo cancello, non
accettato perche' e' saltato fuori guardando venti fette e scegliendo la
migliore -- che e' il modo classico di trovare qualcosa che non c'e'.

## Uso

    python backtest/impara_agenti.py
    python backtest/impara_agenti.py --salva dati/appresi.json
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bootstrap                                               # noqa: E402
import griglie                                                 # noqa: E402
from campione_efficace import blocchi as etichette_blocco      # noqa: E402

from core.apprendimento import (                               # noqa: E402
    Appreso, Competenza, salva, valore_da_usare,
)

# Il primo anno su cui si decide, e l'ultimo prima dell'holdout.
PRIMO_ANNO: int = 2010
ULTIMO_ANNO: int = 2023

# Quanti casi servono in un anno perche' quell'anno conti come una finestra.
CASI_MINIMI_PER_ANNO: int = 50

# Quanto deve valere un effetto di fetta per finire fra i sorvegliati.
EFFETTO_DI_FETTA: float = 0.10
CASI_MINIMI_PER_FETTA: int = 200


def leggi(percorso: Path) -> list[dict]:
    with percorso.open(encoding="utf-8", newline="") as f:
        righe = list(csv.DictReader(f))
    if righe and griglie.GRIGLIE[0].tutte_le_colonne()[0] not in righe[0]:
        raise SystemExit(
            "il campo di prova non ha le colonne dei cammini: rigeneralo con "
            "`python backtest/campo_prova.py`")
    return righe


def _valori(righe: Sequence[dict], colonna: str) -> tuple[list[float], list[int]]:
    """Gli R di una colonna, e a quali righe appartengono.

    Le celle vuote si saltano: "non misurabile" non e' un pareggio, e
    trattarlo come zero gonfierebbe proprio le griglie con piu' casi
    incoerenti.
    """
    valori, indici = [], []
    for i, r in enumerate(righe):
        cella = r.get(colonna, "")
        if cella != "":
            valori.append(float(cella))
            indici.append(i)
    return valori, indici


def _confronto_appaiato(
    righe: Sequence[dict], blocchi: Sequence[str],
    colonna: str, riferimento: str,
) -> tuple[list[float], list[str]]:
    """La differenza riga per riga fra un candidato e il manuale.

    **Appaiata**, cioe' sulle righe dove entrambi sono misurabili: confrontare
    due medie calcolate su insiemi diversi direbbe soprattutto quali CRT sono
    capitati a chi. Su una domanda dove la differenza vale centesimi di R,
    quello basta a inventare un vincitore.
    """
    differenze, gruppi = [], []
    for i, r in enumerate(righe):
        a, b = r.get(colonna, ""), r.get(riferimento, "")
        if a != "" and b != "":
            differenze.append(float(a) - float(b))
            gruppi.append(blocchi[i])
    return differenze, gruppi


def scegli_sul_passato(
    righe: Sequence[dict], griglia: griglie.Griglia, indici: Sequence[int],
) -> float:
    """Il candidato migliore su queste righe. E' l'unica cosa che guarda il
    passato, ed e' anche l'unica che puo' scegliere."""
    migliore, punteggio = griglia.competenza.predefinito, None
    sotto = [righe[i] for i in indici]
    for valore in griglia.valori:
        v, _ = _valori(sotto, griglia.nome_colonna(valore))
        if len(v) < CASI_MINIMI_PER_ANNO:
            continue
        medio = float(np.mean(v))
        if punteggio is None or medio > punteggio:
            migliore, punteggio = valore, medio
    return migliore


def cammina(
    righe: list[dict], blocchi: list[str], griglia: griglie.Griglia,
    primo_anno: int, ultimo_anno: int,
) -> tuple[list[float], list[str], list[float]]:
    """Il walk-forward di un agente.

    Torna `(differenze, blocchi, scelte)`: la differenza fuori campione fra il
    candidato scelto sul passato e il manuale, riga per riga, piu' l'elenco
    dei candidati scelti anno per anno -- che serve alla stabilita'.
    """
    per_anno: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(righe):
        per_anno[datetime.fromisoformat(r["quando"]).year].append(i)

    manuale = griglia.nome_colonna(griglia.competenza.predefinito)
    differenze: list[float] = []
    gruppi: list[str] = []
    scelte: list[float] = []
    for anno in range(primo_anno, ultimo_anno + 1):
        prima = [i for a, ind in per_anno.items() if a < anno for i in ind]
        adesso = per_anno.get(anno, [])
        if len(prima) < 500 or len(adesso) < CASI_MINIMI_PER_ANNO:
            continue
        scelto = scegli_sul_passato(righe, griglia, prima)
        scelte.append(scelto)
        d, g = _confronto_appaiato(
            [righe[i] for i in adesso], [blocchi[i] for i in adesso],
            griglia.nome_colonna(scelto), manuale)
        differenze.extend(d)
        gruppi.extend(g)
    return differenze, gruppi, scelte


def stabilita_della_scelta(scelte: Sequence[float], predefinito: float) -> float:
    """In che frazione di finestre si e' scelto lo STESSO candidato.

    E' la traduzione del "segno stabile" a una griglia: un agente che ogni
    anno sceglie un numero diverso non ha trovato una proprieta' del mercato,
    ha trovato il rumore di quell'anno. Se la scelta piu' frequente e' il
    manuale, la stabilita' e' zero: non c'e' nessuna carriera da promuovere.
    """
    if not scelte:
        return 0.0
    conta: dict[float, int] = defaultdict(int)
    for s in scelte:
        conta[s] += 1
    piu_scelto = max(conta, key=lambda v: conta[v])
    if piu_scelto == predefinito:
        return 0.0
    return conta[piu_scelto] / len(scelte)


def carriera(
    righe: list[dict], blocchi: list[str], griglia: griglie.Griglia,
    giri: int, primo_anno: int, ultimo_anno: int,
) -> Appreso:
    """Cosa questo agente ha imparato, e con che diritto."""
    differenze, gruppi, scelte = cammina(
        righe, blocchi, griglia, primo_anno, ultimo_anno)
    competenza = griglia.competenza
    if not differenze:
        return Appreso(competenza=competenza.agente,
                       valore=competenza.predefinito, campioni=0,
                       guadagno=0.0, intervallo=(0.0, 0.0), stabilita=0.0,
                       note="nessuna finestra utilizzabile")

    punto, basso, alto = bootstrap.intervallo(differenze, gruppi, giri=giri)
    conta: dict[float, int] = defaultdict(int)
    for s in scelte:
        conta[s] += 1
    scelto = max(conta, key=lambda v: conta[v])
    return Appreso(
        competenza=competenza.agente,
        valore=scelto,
        campioni=len(differenze),
        guadagno=punto,
        intervallo=(basso, alto),
        stabilita=stabilita_della_scelta(scelte, competenza.predefinito),
        quando=datetime.now().astimezone().isoformat(timespec="seconds"),
        note="scelte per anno: " + ", ".join(f"{s:g}" for s in scelte))


def sorvegliati_speciali(
    righe: list[dict], blocchi: list[str], griglia: griglie.Griglia,
) -> list[str]:
    """Dove un candidato e' forte pur essendo nullo in media.

    Non promuove nessuno: segnala. Un effetto trovato guardando venti fette e
    tenendo la migliore e' il modo classico di trovare qualcosa che non c'e',
    e la lista serve a decidere COSA cercare apposta la volta dopo -- con i
    suoi dati e il suo cancello.
    """
    manuale = griglia.nome_colonna(griglia.competenza.predefinito)
    trovati: list[str] = []
    for chiave in ("strumento", "coppia"):
        fette: dict[str, list[int]] = defaultdict(list)
        for i, r in enumerate(righe):
            fette[r[chiave]].append(i)
        for nome, indici in sorted(fette.items()):
            sotto = [righe[i] for i in indici]
            sotto_blocchi = [blocchi[i] for i in indici]
            for valore in griglia.valori:
                if valore == griglia.competenza.predefinito:
                    continue
                d, _ = _confronto_appaiato(
                    sotto, sotto_blocchi, griglia.nome_colonna(valore), manuale)
                if len(d) < CASI_MINIMI_PER_FETTA:
                    continue
                medio = float(np.mean(d))
                if abs(medio) >= EFFETTO_DI_FETTA:
                    trovati.append(
                        f"{nome}: {valore:g} vale {medio:+.4f} R "
                        f"su {len(d):,} casi")
    return trovati


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dati", default="dati/campo_prova.csv")
    p.add_argument("--giri", type=int, default=bootstrap.GIRI)
    p.add_argument("--primo-anno", type=int, default=PRIMO_ANNO)
    p.add_argument("--ultimo-anno", type=int, default=ULTIMO_ANNO)
    p.add_argument("--salva", default=None, help="dove scrivere gli appresi")
    a = p.parse_args()

    percorso = Path(a.dati)
    if not percorso.exists():
        print(f"manca {percorso}: gira prima backtest/campo_prova.py")
        return 2
    righe = leggi(percorso)
    blocchi = etichette_blocco(righe)
    print(f"{len(righe):,} CRT, {len(set(blocchi)):,} blocchi indipendenti")
    print(f"walk-forward {a.primo_anno}-{a.ultimo_anno}, holdout chiuso")
    print()

    appresi: dict[str, Appreso] = {}
    for griglia in griglie.GRIGLIE:
        competenza = griglia.competenza
        print(f"=== {competenza.agente} ===")
        print(f"    {competenza.domanda}")
        print(f"    manuale: {competenza.predefinito:g}")

        print(f"    {'candidato':>12} {'casi':>8} {'R medio':>10}"
              f"   {'contro il manuale':>18}")
        manuale = griglia.nome_colonna(competenza.predefinito)
        base, _ = _valori(righe, manuale)
        for valore in griglia.valori:
            v, _ = _valori(righe, griglia.nome_colonna(valore))
            if not v:
                print(f"    {valore:>12g} {0:>8} {'--':>10}")
                continue
            d, _ = _confronto_appaiato(
                righe, blocchi, griglia.nome_colonna(valore), manuale)
            delta = float(np.mean(d)) if d else 0.0
            segna = " (manuale)" if valore == competenza.predefinito else ""
            print(f"    {valore:>12g} {len(v):>8,} {np.mean(v):>+10.4f}"
                  f"   {delta:>+18.4f}{segna}")

        appreso = carriera(righe, blocchi, griglia, a.giri,
                           a.primo_anno, a.ultimo_anno)
        appresi[competenza.agente] = appreso
        valore, provenienza = valore_da_usare(competenza, appreso)
        print()
        print(f"    fuori campione: {appreso.campioni:,} casi, "
              f"{appreso.guadagno:+.4f} R "
              f"[{appreso.intervallo[0]:+.4f}, {appreso.intervallo[1]:+.4f}], "
              f"stabilita' {appreso.stabilita:.0%}")
        if appreso.note:
            print(f"    {appreso.note}")
        if appreso.promosso(competenza):
            print(f"    PROMOSSO: usa {valore:g}")
        else:
            print(f"    resta al manuale ({valore:g})")
            for motivo in appreso.perche_no(competenza):
                print(f"      - {motivo}")

        speciali = sorvegliati_speciali(righe, blocchi, griglia)
        if speciali:
            print("    sorvegliati speciali (NON promuovono, si ricordano):")
            for riga in speciali:
                print(f"      . {riga}")
        print()

    promossi = [n for n, imparato in appresi.items()
                if imparato.promosso(_competenza_di(n))]
    print(f"=== carriera: {len(promossi)} promossi su {len(appresi)} ===")
    for nome in sorted(appresi):
        competenza = _competenza_di(nome)
        valore, provenienza = valore_da_usare(competenza, appresi[nome])
        print(f"  {nome:24} usa {valore:>6g}   {provenienza}")

    if a.salva:
        salva(appresi, Path(a.salva))
        print()
        print(f"scritti in {a.salva}")
    return 0


def _competenza_di(nome: str) -> Competenza:
    for g in griglie.GRIGLIE:
        if g.competenza.agente == nome:
            return g.competenza
    raise KeyError(nome)


if __name__ == "__main__":
    sys.exit(main())
