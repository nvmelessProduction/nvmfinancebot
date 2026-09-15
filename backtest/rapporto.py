"""Dal file dei segnali alla tabella degli esiti.

Due letture affiancate, perche' dicono cose diverse:

  senza GEST-08  il target finale resta TP1, la posizione si chiude tutta li'.
                 E' la misura conservativa: non dipende da quanto lontano un
                 key level superiore porti il residuo, e non produce mai un
                 pareggio, perche' il pareggio esiste solo se c'e' un residuo
                 da proteggere.
  con GEST-08    il target si estende alla chiusura di ogni TF superiore che
                 conferma il pattern. E' la regola vera, e produce code lunghe:
                 un residuo del 75% puo' correre per settimane.
"""
from __future__ import annotations

import pickle
import statistics
import sys
from bisect import bisect_right
from collections import Counter
from pathlib import Path

from archivio import carica, finestra, indice_temporale
from esiti import APERTA, PAREGGIO, PRIMO, STOP, TARGET, simula
from scansione import FINESTRA
from core.parametri import TF, UNIVERSO
from core.stato import key_level_presi

SOGLIE = [1.5, 1.2, 1.0, 0.8, 0.5]
SETTIMANE_ORARIE = 125.0        # i dati orari coprono circa 2,4 anni


def archivi():
    fuori = {}
    for strumento, dati in UNIVERSO.items():
        storico = carica(dati.future)
        fuori[strumento] = (storico, indice_temporale(storico))
    return fuori


def esegui(raccolto, archivi, soglia: float, estendi: bool):
    tutti = []
    for strumento, dati in raccolto.items():
        storico, tempi = archivi[strumento]

        def contesto(istante, storico=storico, tempi=tempi):
            ridotto = {t: finestra(storico[t], tempi[t], istante, FINESTRA[t])
                       for t in FINESTRA if t in storico}
            return key_level_presi(ridotto, istante)

        libera_da = None
        for segnale in dati["segnali"]:
            if segnale.rapporto is None or segnale.rapporto < soglia:
                continue
            if libera_da is not None and segnale.istante < libera_da:
                continue                   # RISK-06: una posizione alla volta
            esito = simula(segnale, storico, tempi, contesto, estendi=estendi)
            tutti.append(esito)
            serie = storico[esito.tf_marcia]
            indice = bisect_right(tempi[esito.tf_marcia], segnale.istante) + esito.barre
            libera_da = serie[indice].orario if indice < len(serie) else None
    return tutti


def riga(nome, esiti) -> str:
    conta = Counter(e.esito for e in esiti)
    chiuse = [e for e in esiti if e.esito != APERTA]
    vincenti = conta[PRIMO] + conta[TARGET]
    winrate = f"{100*vincenti/len(chiuse):.1f}%" if chiuse else "n/d"
    erre = [e.erre for e in chiuse]
    medio = f"{statistics.fmean(erre):+.2f}" if erre else "n/d"
    mediana = f"{statistics.median(erre):+.2f}" if erre else "n/d"
    return (f"{nome:10s} {len(esiti):5d} {conta[STOP]:5d} {conta[PAREGGIO]:4d} "
            f"{conta[PRIMO]:5d} {conta[TARGET]:5d} {conta[APERTA]:7d} {winrate:>8s} "
            f"{sum(erre):+9.2f} {medio:>8s} {mediana:>8s}")


INTESTAZIONE = (f"{'':10s} {'op.':>5s} {'stop':>5s} {'be':>4s} {'tp1':>5s} "
                f"{'targ':>5s} {'aperte':>7s} {'winrate':>8s} {'R tot':>9s} "
                f"{'R medio':>8s} {'R med.no':>8s}")


def main() -> int:
    raccolto = pickle.loads(Path("segnali.pickle").read_bytes())
    arc = archivi()

    print("=" * 86)
    print("IMBUTO — quante volte ciascuna regola ha impedito un'operazione")
    print("(scansione con GEST-01 disattivato: il suo effetto e' nella tabella soglie)")
    print("=" * 86)
    somma = Counter()
    for dati in raccolto.values():
        somma.update(dati["funnel"])
    for voce, quante in somma.most_common():
        print(f"{quante:8d}  {voce}")

    for estendi in (False, True):
        etichetta = "CON GEST-08 (target esteso)" if estendi else "SENZA GEST-08 (tutto a TP1)"
        print("\n" + "=" * 86)
        print(f"ESITI A RR_MINIMO = 1.5 — {etichetta}")
        print("=" * 86)
        print(INTESTAZIONE)
        print("-" * len(INTESTAZIONE))
        tutti = []
        for strumento in raccolto:
            soli = [e for e in esegui({strumento: raccolto[strumento]}, arc, 1.5, estendi)]
            print(riga(strumento, soli))
            tutti.extend(soli)
        print("-" * len(INTESTAZIONE))
        print(riga("TOTALE", tutti))

        if not estendi:
            print("\nElenco delle operazioni:")
            for esito in sorted(tutti, key=lambda e: e.segnale.istante):
                s = esito.segnale
                print(f"  {s.istante:%Y-%m-%d %H:%M} {s.strumento:7s} {s.tf_trigger.value:6s} "
                      f"{s.direzione.value:5s} R{s.rapporto:>5.2f} -> {esito.esito:6s} "
                      f"{esito.erre:+6.2f}  ({esito.barre} barre {esito.tf_marcia.value})")

    print("\n" + "=" * 86)
    print("SE SI ABBASSA RR_MINIMO — senza GEST-08, per confrontare mele con mele")
    print("=" * 86)
    print(f"{'RR min':>7s}" + INTESTAZIONE[10:] + f"{'op./sett.':>11s}")
    for soglia in SOGLIE:
        tutti = esegui(raccolto, arc, soglia, estendi=False)
        print(f"{soglia:7.1f}" + riga("", tutti)[10:] + f"{len(tutti)/SETTIMANE_ORARIE:>11.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
