"""Quante operazioni INDIPENDENTI contiene davvero il campo di prova.

## Il problema, in una riga

Due CRT dello stesso strumento le cui finestre di esito si sovrappongono non
sono due prove: sono una prova guardata due volte. Vivono lo stesso movimento
di prezzo, vincono insieme e perdono insieme.

Contarli come due gonfia il campione, e un campione gonfiato restringe
l'intervallo di confidenza: si finisce per dichiarare significativo un
risultato che non lo e'. E' il modo piu' comune di prendersi in giro con un
backtest, ed e' il motivo per cui il protocollo chiede il **campione
efficace** e il bootstrap **a blocchi**.

## Come si contano

Per ogni **gruppo di correlazione**, le finestre
`[quando, quando + barre x durata]` si uniscono quando si toccano: ogni gruppo
di finestre incatenate e' **un blocco**, cioe' una prova sola. Il campione
efficace e' il numero di blocchi.

## Il gruppo di correlazione, e perche' non lo strumento

La prima versione separava per **strumento**, con un test che diceva "lo
stesso istante su due strumenti resta due prove". E' sbagliato, e il campione
efficace che ne usciva -- il 90,2% delle righe -- era gonfiato.

Se `EURUSD` e `GBPUSD` prendono un CRT long nella stessa ora, quella e' **una
scommessa sul dollaro fatta due volte**: i due strumenti salgono e scendono
insieme, quindi vincono e perdono insieme. Contarle come due prove e' lo
stesso errore che il bootstrap a blocchi esiste per evitare, commesso lungo
l'altro asse.

I gruppi sono quelli di `RISK-02` (`GRUPPI_CORRELAZIONE`), letti dal bot e non
ricopiati: e' la stessa tabella con cui il rischio decide quante posizioni
correlate tollerare, ed e' gia' la sua dichiarazione di cosa si muove insieme.

Conta anche per una decisione piu' grande: aggiungere trenta cambi contro
dollaro moltiplica le righe e quasi non tocca il campione efficace. Il budget
di dati cresce coi **fattori indipendenti**, non con gli strumenti -- e questo
numero e' l'unico modo di verificarlo invece di sperarlo.

Il blocco e' anche l'unita' che il bootstrap della Fase 2 dovra' ricampionare:
ricampionare le righe una per una assumerebbe l'indipendenza che qui si sta
misurando non esserci.

## Cosa NON fa

Non butta via niente. Le righe restano tutte -- servono a stimare i pesi -- e
il blocco e' un'etichetta in piu': dice solo di quante prove distinte si
dispone quando si tratta di dichiarare un intervallo di confidenza.

## Uso

    python backtest/campione_efficace.py
    python backtest/campione_efficace.py --dati dati/campo_prova.csv --scrivi
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mercato_duka import DURATA                           # noqa: E402
from core.parametri import GRUPPI_CORRELAZIONE, TF             # noqa: E402


def gruppo_di(strumento: str) -> str:
    """A quale gruppo di correlazione appartiene uno strumento.

    Si legge da `GRUPPI_CORRELAZIONE`, la stessa tabella con cui `RISK-02`
    decide quante posizioni correlate tollerare. Una seconda tabella qui
    finirebbe per divergere da quella, e divergerebbe proprio nel punto in cui
    si dichiara cosa si muove insieme.

    Uno strumento fuori da ogni gruppo fa gruppo per se': non lo si accorpa a
    caso, perche' accorpare male **restringe** il campione efficace e quindi
    allarga l'intervallo -- dalla parte prudente, ma per un motivo inventato.
    """
    for nome, membri in GRUPPI_CORRELAZIONE.items():
        if strumento in membri:
            return nome
    return f"solo:{strumento}"


def durata_esecuzione(coppia: str) -> timedelta:
    """Quanto dura una barra della coppia, es. `TF_1W->TF_H4` -> 4 ore.

    Si legge da `DURATA`, la stessa tabella con cui il bot decide se una
    candela nuova puo' esistere: una seconda tabella qui sarebbe la solita
    coppia di copie che divergono.
    """
    _, _, esecuzione = coppia.partition("->")
    return DURATA[TF(esecuzione)]


def finestre(righe: Iterable[dict]) -> dict[str, list[tuple]]:
    """Per ogni gruppo di correlazione, le finestre di esito, in ordine."""
    per_gruppo: dict[str, list[tuple]] = defaultdict(list)
    for indice, r in enumerate(righe):
        inizio = datetime.fromisoformat(r["quando"])
        fine = inizio + int(r["barre"]) * durata_esecuzione(r["coppia"])
        per_gruppo[gruppo_di(r["strumento"])].append((inizio, fine, indice))
    for serie in per_gruppo.values():
        serie.sort()
    return per_gruppo


def blocchi(righe: list[dict]) -> list[str]:
    """L'etichetta di blocco di ogni riga, nell'ordine in cui e' arrivata.

    Due finestre che si toccano finiscono nello stesso blocco, e per
    transitivita' una catena di sovrapposizioni e' un blocco solo. E' voluto:
    se A si sovrappone a B e B a C, A e C condividono comunque il movimento
    che li attraversa.
    """
    etichette: list[Optional[str]] = [None] * len(righe)
    for gruppo, serie in finestre(righe).items():
        numero = 0
        fine_corrente = None
        for inizio, fine, indice in serie:
            if fine_corrente is None or inizio >= fine_corrente:
                numero += 1
                fine_corrente = fine
            else:
                fine_corrente = max(fine_corrente, fine)
            etichette[indice] = f"{gruppo}#{numero:05d}"
    return [e or "?" for e in etichette]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dati", default="dati/campo_prova.csv")
    p.add_argument("--scrivi", action="store_true",
                   help="riscrive il file con la colonna `blocco` in piu'")
    a = p.parse_args()

    percorso = Path(a.dati)
    if not percorso.exists():
        print(f"manca {percorso}: gira prima backtest/campo_prova.py")
        return 2
    with percorso.open(encoding="utf-8", newline="") as f:
        righe = list(csv.DictReader(f))
    if not righe:
        print("il campo di prova e' vuoto")
        return 1

    etichette = blocchi(righe)
    distinti = len(set(etichette))
    print(f"righe            : {len(righe):>7,}")
    print(f"blocchi distinti : {distinti:>7,}")
    print(f"campione efficace: {100 * distinti / len(righe):>6.1f}% delle righe")
    print()

    per_coppia: dict[str, set] = defaultdict(set)
    conta_coppia: dict[str, int] = defaultdict(int)
    for r, e in zip(righe, etichette):
        per_coppia[r["coppia"]].add(e)
        conta_coppia[r["coppia"]] += 1
    print(f"  {'coppia':22} {'righe':>8} {'blocchi':>8}")
    for coppia in sorted(conta_coppia):
        print(f"  {coppia:22} {conta_coppia[coppia]:>8,} "
              f"{len(per_coppia[coppia]):>8,}")
    print()

    soglia = 300
    if distinti < soglia:
        print(f"SOTTO le {soglia} prove indipendenti che il protocollo chiede "
              f"fuori campione: il numero non reggera' un intervallo di "
              f"confidenza.")
    else:
        print(f"sopra le {soglia} prove indipendenti del protocollo.")

    if a.scrivi:
        campi = list(righe[0].keys()) + ["blocco"]
        with percorso.open("w", encoding="utf-8", newline="") as f:
            scrittore = csv.DictWriter(f, fieldnames=campi)
            scrittore.writeheader()
            for r, e in zip(righe, etichette):
                r["blocco"] = e
                scrittore.writerow(r)
        print(f"\nscritta la colonna `blocco` in {percorso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
