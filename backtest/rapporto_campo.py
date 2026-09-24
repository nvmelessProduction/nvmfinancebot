"""Cosa dice il campo di prova, prima che qualcuno provi a pesarlo.

## A che serve, e perche' viene PRIMA della Fase 2

Il protocollo fissa la linea da battere: `B0`, prendere **tutti** i CRT. Se
`B0` fosse gia' positivo il lavoro sui pesi sarebbe un'altra cosa; se e'
negativo, ogni conferma va misurata come *quanto sposta rispetto a B0*, non
come "quanto vince".

E c'e' una cosa da guardare prima ancora: **una conferma che risponde sempre
allo stesso modo non e' una conferma.** Il progetto ci e' gia' cascato due
volte -- `CRT-18` rispondeva `True` 226 volte su 226, `CRT-10` rispondeva
`None` 226 volte su 226 -- e in entrambi i casi il difetto era invisibile
finche' nessuno contava le risposte.

Quello che questo modulo stampa non decide niente: descrive. Le decisioni
hanno il loro protocollo, e comincia dopo.

## Uso

    python backtest/rapporto_campo.py
    python backtest/rapporto_campo.py --dati dati/campo_prova.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estrazione import LE_OTTO                                  # noqa: E402


def leggi(percorso: Path) -> list[dict]:
    with percorso.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def erre(righe) -> list[float]:
    return [float(r["erre"]) for r in righe]


def _riga_di_misura(nome: str, valori: list[float], quante: int) -> str:
    if not valori:
        return f"  {nome:26} {quante:>7,}        --"
    medio = statistics.mean(valori)
    scarto = statistics.pstdev(valori) if len(valori) > 1 else 0.0
    errore = scarto / (len(valori) ** 0.5) if valori else 0.0
    return (f"  {nome:26} {quante:>7,}  {medio:>+8.4f} R"
            f"  +/- {errore:.4f}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dati", default="dati/campo_prova.csv")
    a = p.parse_args()

    percorso = Path(a.dati)
    if not percorso.exists():
        print(f"manca {percorso}: gira prima backtest/campo_prova.py")
        return 2
    righe = leggi(percorso)
    if not righe:
        print("il campo di prova e' vuoto")
        return 1

    tutti = erre(righe)
    esiti = Counter(r["esito"] for r in righe)
    print(f"{len(righe):,} CRT, {min(r['quando'] for r in righe)[:10]} "
          f"-> {max(r['quando'] for r in righe)[:10]}")
    print()
    print("=== B0: prendere TUTTI i CRT (la linea da battere) ===")
    print(_riga_di_misura("B0", tutti, len(tutti)))
    for come in ("target", "stop", "scaduto"):
        print(f"  {come:26} {esiti[come]:>7,}  "
              f"{100 * esiti[come] / len(righe):>6.1f}%")
    print()

    print("=== per coppia ===")
    per_coppia = defaultdict(list)
    for r in righe:
        per_coppia[r["coppia"]].append(r)
    for coppia in sorted(per_coppia):
        print(_riga_di_misura(coppia, erre(per_coppia[coppia]),
                              len(per_coppia[coppia])))
    print()

    print("=== per strumento ===")
    per_strumento = defaultdict(list)
    for r in righe:
        per_strumento[r["strumento"]].append(r)
    for nome in sorted(per_strumento):
        print(_riga_di_misura(nome, erre(per_strumento[nome]),
                              len(per_strumento[nome])))
    print()

    print("=== le otto conferme: quanto spostano rispetto a B0 ===")
    print("  (una conferma che risponde sempre allo stesso modo non e' una")
    print("   conferma: e' una costante travestita, e va vista qui)")
    print()
    base = statistics.mean(tutti)
    for regola in LE_OTTO:
        risposte = Counter(r[regola] for r in righe)
        forma = ", ".join(
            f"{_nome(v)} {n:,} ({100 * n / len(righe):.0f}%)"
            for v, n in sorted(risposte.items()))
        print(f"  {regola}   {forma}")
        if len(risposte) == 1:
            solo = _nome(next(iter(risposte)))
            print(f"     COSTANTE: {solo} su tutte le {len(righe):,} righe. "
                  f"Non porta informazione.")
            continue
        for valore in ("1", "0", ""):
            quante = [float(r["erre"]) for r in righe if r[regola] == valore]
            if not quante:
                continue
            delta = statistics.mean(quante) - base
            print(f"     {_nome(valore):12} {len(quante):>7,}  "
                  f"{statistics.mean(quante):>+8.4f} R   "
                  f"({delta:+.4f} rispetto a B0)")
    print()

    print("=== CRT-06 come conteggio, non come si'/no ===")
    per_allineati = defaultdict(list)
    for r in righe:
        per_allineati[r["allineati"]].append(float(r["erre"]))
    for chiave in sorted(per_allineati, key=lambda k: (k == "", k)):
        valori = per_allineati[chiave]
        nome = "non lo so" if chiave == "" else f"{chiave} allineati"
        print(_riga_di_misura(nome, valori, len(valori)))
    print()

    print("=== il rapporto misurato ===")
    rapporti = [float(r["rapporto"]) for r in righe]
    rapporti.sort()
    for frazione in (0.10, 0.25, 0.50, 0.75, 0.90):
        posto = int(frazione * (len(rapporti) - 1))
        print(f"  {frazione:>4.0%}  {rapporti[posto]:.2f} R")
    print("  Le fonti dichiarano 'da 1,85 a 3,92 R' (SETUP-02C). Il rapporto")
    print("  qui e' misurato su TP1 (50% del range), che e' il bersaglio")
    print("  dell'esito, non il key level di SETUP-14.")
    return 0


def _nome(valore: str) -> str:
    return {"1": "si'", "0": "no", "": "non lo so"}.get(valore, valore)


if __name__ == "__main__":
    sys.exit(main())
