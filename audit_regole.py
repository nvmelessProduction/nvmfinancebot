"""Ogni regola dei documenti e' davvero COLLEGATA al percorso di produzione?

## Perche' guardare il codice non basta

`DEF-33` era implementata in `direzione_cfd`, aveva cinque test verdi, ed era
**morta**: nessuno la chiamava. Su `USDJPY` e `USDCHF` gli ordini sarebbero
partiti rovesciati, e 430 test non se ne accorgevano perche' collaudavano la
funzione **da sola**.

Una regola puo' quindi trovarsi in quattro stati, e solo l'ultimo conta:

```
1. citata nei documenti e basta          -> non implementata
2. implementata ma mai chiamata          -> MORTA  (il caso DEF-33)
3. chiamata solo dai test                -> MORTA
4. raggiungibile dal percorso di produzione -> viva
```

Questo programma li distingue costruendo il grafo delle chiamate a partire
dagli ingressi reali — il webhook, il ciclo di mercato, la sentinella — e
guardando quali funzioni sono raggiungibili davvero.

Non sostituisce il giudizio: una funzione raggiungibile puo' comunque fare la
cosa sbagliata. Ma dice dove NON serve nemmeno guardare, e trova la classe di
errore che i test non vedono per costruzione.
"""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

RADICE = Path(".")
CODICE = ["core", "."]
# Da dove parte davvero l'esecuzione. `main` e' interamente un ingresso: e' il
# server, ogni sua funzione e' raggiungibile da fuori. Gli altri sono i cicli
# che girano da soli e i punti in cui il fornitore entra nel motore.
#
# Indovinare questi nomi e' il punto debole dello strumento: la prima versione
# scriveva "fotografia" invece di "costruisci" e segnalava come morte meta'
# delle regole vive. Per questo c'e' una calibratura piu' sotto.
MODULI_INGRESSO = {"main"}
INGRESSI_ESPLICITI = ["giro", "valuta", "costruisci", "storico", "_ciclo",
                      "_giro_protetto", "_controlla", "_valuta_le_ultime",
                      "processa_alert", "avvia", "lifespan"]

# Se una di queste risulta morta, lo strumento e' rotto, non il codice.
CALIBRATURA = {
    "DEF-33": "conversione del verso per 6J e 6S, collegata in motore.valuta",
    "DEF-16": "bias, passa da costruisci_fotografia",
    "SETUP-02A": "il CRT short, cuore del motore",
    "GEST-02": "lo stop iniziale",
    "RISK-03": "il calcolo della size",
}
RE_REGOLA = re.compile(r"\b((?:DEF|SETUP|GEST|RISK|CTX|PRIN|ESCL|GIUD|PA|REV|PREC)-\d+[A-Z]?)\b")


def moduli() -> dict[str, Path]:
    fuori = {}
    for f in sorted(Path("core").glob("*.py")):
        if f.name != "__init__.py":
            fuori[f"core.{f.stem}"] = f
    for f in sorted(Path(".").glob("*.py")):
        if f.name not in ("audit_regole.py",) and not f.name.startswith("test"):
            fuori[f.stem] = f
    return fuori


def analizza(percorso: Path):
    """Funzioni definite, chi chiamano, e quali regole citano."""
    albero = ast.parse(percorso.read_text())
    definite, chiamate, regole = {}, defaultdict(set), defaultdict(set)

    class Visita(ast.NodeVisitor):
        def __init__(self): self.dove = None
        def visit_FunctionDef(self, nodo):
            precedente, self.dove = self.dove, nodo.name
            definite[nodo.name] = nodo.lineno
            testo = ast.get_docstring(nodo) or ""
            regole[nodo.name].update(RE_REGOLA.findall(testo))
            for pezzo in ast.walk(nodo):
                if isinstance(pezzo, ast.Constant) and isinstance(pezzo.value, str):
                    regole[nodo.name].update(RE_REGOLA.findall(pezzo.value))
            self.generic_visit(nodo)
            self.dove = precedente
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, nodo):
            self.generic_visit(nodo)
        def visit_Call(self, nodo):
            if self.dove:
                f = nodo.func
                nome = (f.id if isinstance(f, ast.Name)
                        else f.attr if isinstance(f, ast.Attribute) else None)
                if nome: chiamate[self.dove].add(nome)
            self.generic_visit(nodo)

    Visita().visit(albero)
    return definite, chiamate, regole


def main() -> int:
    mods = moduli()
    tutte_definite, tutte_chiamate, tutte_regole = {}, defaultdict(set), defaultdict(set)
    dove_definita = {}
    for nome, percorso in mods.items():
        d, c, r = analizza(percorso)
        for f in d:
            dove_definita.setdefault(f, []).append(nome)
        tutte_definite.update({f: nome for f in d})
        for k, v in c.items(): tutte_chiamate[k] |= v
        for k, v in r.items(): tutte_regole[k] |= v

    # Raggiungibilita' per nome di funzione (approssimazione volutamente
    # generosa: se un nome e' chiamato da qualche parte di raggiungibile, la
    # funzione conta come viva. Meglio un falso "viva" che un falso allarme.)
    vivi = set()
    da_visitare = list(INGRESSI_ESPLICITI)
    da_visitare += [f for f, m in tutte_definite.items() if m in MODULI_INGRESSO]
    while da_visitare:
        f = da_visitare.pop()
        if f in vivi: continue
        vivi.add(f)
        da_visitare.extend(tutte_chiamate.get(f, ()))

    # Regole citate dai documenti
    nei_documenti = set()
    for f in Path("docs").glob("*.md"):
        nei_documenti.update(RE_REGOLA.findall(f.read_text()))

    # Dove vive ogni regola nel codice, e se quella funzione e' raggiungibile
    stato: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for funzione, regole in tutte_regole.items():
        for r in regole:
            stato[r].append((funzione, funzione in vivi))

    morte, mai, vive = [], [], []
    for r in sorted(nei_documenti):
        posti = stato.get(r, [])
        if not posti:
            mai.append(r)
        elif any(viva for _, viva in posti):
            vive.append(r)
        else:
            morte.append((r, [f for f, _ in posti]))

    # --- calibratura: se queste risultano morte, lo strumento e' rotto ------
    rotte = [r for r in CALIBRATURA if r in {x[0] for x in morte}]
    if rotte:
        print("!" * 78)
        print("STRUMENTO NON ATTENDIBILE: risultano morte regole che sono vive")
        for r in rotte:
            print(f"  {r}: {CALIBRATURA[r]}")
        print("Correggere gli ingressi prima di leggere il resto.")
        print("!" * 78 + "\n")
        return 1

    print("=" * 78)
    print("REGOLE IMPLEMENTATE MA MAI RAGGIUNTE DAL PERCORSO DI PRODUZIONE")
    print("(la classe di errore di DEF-33: codice giusto, mai chiamato)")
    print("=" * 78)
    if not morte:
        print("  nessuna")
    for r, funzioni in morte:
        print(f"  {r:10s} vive solo in: {', '.join(sorted(set(funzioni))[:4])}")

    print(f"\n{'=' * 78}")
    print("REGOLE DEI DOCUMENTI SENZA ALCUNA TRACCIA NEL CODICE")
    print("=" * 78)
    print(f"  {len(mai)} regole: {', '.join(mai)}")

    print(f"\n{'=' * 78}")
    print("FUNZIONI DEFINITE IN core/ E MAI CHIAMATE DA NESSUNO")
    print("=" * 78)
    chiamate_ovunque = set()
    for v in tutte_chiamate.values(): chiamate_ovunque |= v
    orfane = [f for f, m in tutte_definite.items()
              if m.startswith("core.") and f not in chiamate_ovunque
              and not f.startswith("_") and f not in INGRESSI_ESPLICITI]
    for f in sorted(orfane):
        r = sorted(tutte_regole.get(f, []))
        print(f"  {tutte_definite[f]:28s} {f:34s} {'regole: ' + ', '.join(r[:3]) if r else ''}")

    print(f"\nriepilogo: {len(vive)} regole vive, {len(morte)} morte, "
          f"{len(mai)} senza traccia, {len(orfane)} funzioni orfane")
    return 0


if __name__ == "__main__":
    sys.exit(main())
