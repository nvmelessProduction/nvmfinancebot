"""Com'e' fatto il cervello di ogni agente, e come lo cambia da solo.

Il genoma di un agente e' la forma del suo cervello: quanti neuroni ha, quanto frena i suoi
pesi (piu' freno = impara regole piu' semplici), e quali parti della sua vista guarda (per
esempio il Grilletto puo' smettere di guardare le candele piccole e tenere solo le misure
della manipolazione, o viceversa).

Ogni settimana ogni agente prova una modifica di se stesso mai provata prima; la squadra
modificata rifa' l'esame anno per anno sui vent'anni, e la modifica resta solo se la squadra
va meglio nel complesso e nella maggior parte degli anni (`scuola.evolvi`). Le regole del
contesto restano: cambiano i cervelli, non il programma che li fa girare, e ogni modifica e'
scritta nel registro.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

import numpy as np

from nvm.cervello.viste import AGENTI

# Le parti della vista di ogni agente (colonne da..a), che il suo cervello puo' spegnere o riaccendere.
BLOCCHI: dict[str, dict[str, tuple[int, int]]] = {
    "Cacciatore": {"coppia di grafici": (0, 4), "misure del range": (4, 9), "candele grandi": (9, 29)},
    "Grilletto": {"tentativo": (0, 3), "manipolazione": (3, 5), "liquidità": (5, 7), "distanza dell'obiettivo": (7, 8),
                  "candele piccole": (8, 56)},
    "Livelli": {"obiettivi": (0, 2), "costi": (2, 4), "stop": (4, 6)},
    "Key level": {"livelli trovati": (0, 5), "distanze dai massimi": (5, 7), "distanza dell'obiettivo": (7, 8),
                  "candele del grafico sopra": (8, 48)},
    "Orario": {"ora": (0, 2), "giorno": (2, 7), "sessioni di Romeo": (7, 9), "distanza dell'obiettivo": (9, 10)},
    "Bias": {"grafico sopra": (0, 3), "settimane": (3, 6), "candela del range": (6, 7), "risposte": (7, 12),
             "distanza dell'obiettivo": (12, 13)},
}
NEURONI = (8, 16, 24, 32)
FRENI = (1e-5, 1e-4, 1e-3, 1e-2, 1e-1)


@dataclass(frozen=True)
class Genoma:
    neuroni: int = 16
    freno: float = 1e-3
    spenti: tuple = ()

    def colonne(self, agente: str) -> Optional[np.ndarray]:
        """Le colonne della vista che guarda; None se le guarda tutte."""
        if not self.spenti:
            return None
        return np.array([c for nome, (da, a) in BLOCCHI[agente].items() if nome not in self.spenti
                         for c in range(da, a)], int)

    def chiave(self) -> str:
        return json.dumps([self.neuroni, self.freno, sorted(self.spenti)])


def iniziali() -> dict[str, Genoma]:
    return {a: Genoma() for a in AGENTI}


def modifiche(agente: str, g: Genoma) -> list[tuple[str, Genoma]]:
    """Tutte le modifiche di un passo che l'agente puo' provare su se stesso, con la loro descrizione."""
    fuori = []
    i = NEURONI.index(g.neuroni) if g.neuroni in NEURONI else 1
    for j in (i - 1, i + 1):
        if 0 <= j < len(NEURONI):
            fuori.append((f"{'più' if j > i else 'meno'} neuroni ({g.neuroni} → {NEURONI[j]})",
                          replace(g, neuroni=NEURONI[j])))
    k = min(range(len(FRENI)), key=lambda x: abs(np.log(FRENI[x]) - np.log(g.freno)))
    for j in (k - 1, k + 1):
        if 0 <= j < len(FRENI):
            fuori.append((f"{'più' if j > k else 'meno'} freno sui pesi (regole {'più semplici' if j > k else 'più fini'})",
                          replace(g, freno=FRENI[j])))
    for nome in BLOCCHI[agente]:
        if nome in g.spenti:
            fuori.append((f"torna a guardare «{nome}»", replace(g, spenti=tuple(s for s in g.spenti if s != nome))))
        elif len(g.spenti) + 1 < len(BLOCCHI[agente]):
            fuori.append((f"smette di guardare «{nome}»", replace(g, spenti=tuple(sorted(g.spenti + (nome,))))))
    return fuori


def da_dati(d: Optional[dict]) -> dict[str, Genoma]:
    g = iniziali()
    for a, x in (d or {}).items():
        if a in g:
            g[a] = Genoma(int(x["neuroni"]), float(x["freno"]), tuple(x.get("spenti", ())))
    return g


def come_dati(genomi: dict[str, Genoma]) -> dict:
    return {a: {"neuroni": g.neuroni, "freno": g.freno, "spenti": list(g.spenti)} for a, g in genomi.items()}
