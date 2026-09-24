"""Gli agenti si confrontano: dopo ogni decisione, quando finisce, e alla riunione.

- **Dopo ogni decisione** ognuno dice se spinge a entrare o frena, e quanto:
  e' di quanto il suo parere sposta la stima del Capo (`Capo.spinte`).
- **Quando finisce** (presa o solo sulla carta) si guarda chi aveva ragione,
  e la pagella di ognuno si aggiorna.
- **Alla riunione** i consigli: le coppie di pareri che insieme vanno meglio
  (o peggio) che da soli. Il Capo le prova subito nel riaddestramento.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from nvm.agenti.capo import COLONNE, Capo
from nvm.vivo.messaggi import erre, quando

# Quali colonne del Capo vengono da quale agente.
AGENTI: dict[str, tuple[int, ...]] = {
    "Cacciatore": (16, 17),
    "Grilletto": (14, 15),
    "Livelli": (18, 19, 20),
    "Key level": (0, 1, 2, 3, 4),
    "Orario": (5, 6, 7, 8, 9),
    "Bias": (10, 11, 12, 13),
}
# Sotto questa spinta un agente non si schiera.
NEUTRO = 0.02

# I pareri si' o no che possono fare coppia in un consiglio.
SEGNALI: dict[str, tuple[str, int]] = {
    "massimo preso": ("Key level", COLONNE.index("key level: massimo preso")),
    "rejection block": ("Key level", COLONNE.index("key level: rejection block")),
    "FVG": ("Key level", COLONNE.index("key level: fvg")),
    "9–13 NY": ("Orario", COLONNE.index("ora 09-13")),
    "13–17 NY": ("Orario", COLONNE.index("ora 13-17")),
    "range a favore": ("Bias", COLONNE.index("bias range a favore")),
    "range contro": ("Bias", COLONNE.index("bias range contro")),
    "sopra a favore": ("Bias", COLONNE.index("bias sopra a favore")),
    "secondo colpo": ("Grilletto", COLONNE.index("secondo colpo")),
    "settimanale": ("Cacciatore", COLONNE.index("coppia W1-H4")),
    "giornaliero": ("Cacciatore", COLONNE.index("coppia D1-H1")),
}


def spinte(capo: Capo, x: np.ndarray) -> dict[str, float]:
    """La spinta di ogni agente su questa decisione. Le combinazioni contano meta' per ciascuno."""
    s = capo.spinte(np.asarray(x, float))
    per = {nome: float(s[list(c)].sum()) for nome, c in AGENTI.items()}
    for k, (i, j) in enumerate(capo.interazioni):
        for nome, c in AGENTI.items():
            per[nome] += float(s[len(COLONNE) + k]) * ((i in c) + (j in c)) / 2
    return per


def _schieramento(per: dict[str, float]) -> tuple[list[str], list[str]]:
    favore = [f"{n} ({v:+.2f})".replace(".", ",") for n, v in sorted(per.items(), key=lambda a: -a[1]) if v >= NEUTRO]
    contro = [f"{n} ({v:+.2f})".replace(".", ",") for n, v in sorted(per.items(), key=lambda a: a[1]) if v <= -NEUTRO]
    return favore, contro


def discussione(per: dict[str, float], entra: bool, atteso: float) -> str:
    favore, contro = _schieramento(per)
    return "\n".join([
        "💬 Il confronto:",
        "  spingono a entrare: " + (", ".join(favore) if favore else "nessuno"),
        "  frenano: " + (", ".join(contro) if contro else "nessuno"),
        f"  Capo: {len(favore)} a favore, {len(contro)} contro; tutto pesato il guadagno atteso è {erre(atteso)}: "
        + ("entro." if entra else "non entro."),
    ])


def chi_aveva_ragione(per: dict[str, float], vinta: bool) -> tuple[list[str], list[str]]:
    ragione = [n for n, v in per.items() if abs(v) >= NEUTRO and (v > 0) == vinta]
    torto = [n for n, v in per.items() if abs(v) >= NEUTRO and (v > 0) != vinta]
    return ragione, torto


def resoconto(chiave_leggibile: str, esito: dict, entrata: bool, per: dict[str, float], atteso: float) -> tuple[str, list[str], list[str]]:
    vinta = esito["erre"] > 0
    ragione, torto = chi_aveva_ragione(per, vinta)
    capo_ok = (atteso > 0) == vinta
    testo = "\n".join([
        f"🔎 Com'è finita: {chiave_leggibile} — {esito['uscita']}, {erre(esito['erre'])}"
        + (" (presa)" if entrata else " (non presa: sulla carta)"),
        "  Avevano ragione: " + (", ".join(ragione) if ragione else "nessuno"),
        "  Avevano torto: " + (", ".join(torto) if torto else "nessuno"),
        "  Capo: " + ("aveva ragione." if capo_ok else "aveva torto."),
    ])
    return testo, ragione + (["Capo"] if capo_ok else []), torto + ([] if capo_ok else ["Capo"])


def aggiorna_pagelle(pagelle: dict[str, list[int]], ragione: list[str], torto: list[str]) -> None:
    for n in ragione:
        pagelle.setdefault(n, [0, 0])
        pagelle[n][0] += 1
        pagelle[n][1] += 1
    for n in torto:
        pagelle.setdefault(n, [0, 0])
        pagelle[n][1] += 1


def grado(giuste: int, totali: int) -> str:
    if totali < 50:
        return "neolaureato"
    return "promosso" if giuste / totali >= 0.55 else "in prova"


def consigli(x: np.ndarray, r: np.ndarray, minimo: int = 200, quanti: int = 3) -> list[tuple[str, tuple[int, int]]]:
    """Le coppie di pareri di agenti diversi che insieme cambiano di piu' il risultato.

    Per ogni coppia (A, B): R medio quando dicono si' tutti e due, contro
    quando A dice si' e B no. Si tengono le piu' nette (differenza per la
    radice dei casi), con almeno `minimo` casi da tutte e due le parti.
    """
    trovati = []
    for (na, (aa, ia)), (nb, (ab, ib)) in combinations(SEGNALI.items(), 2):
        if aa == ab:
            continue
        for (n1, a1, i1), (n2, a2, i2) in (((na, aa, ia), (nb, ab, ib)), ((nb, ab, ib), (na, aa, ia))):
            con = (x[:, i1] == 1) & (x[:, i2] == 1)
            senza = (x[:, i1] == 1) & (x[:, i2] != 1)
            if con.sum() < minimo or senza.sum() < minimo:
                continue
            d = float(r[con].mean() - r[senza].mean())
            forza = abs(d) * np.sqrt(min(con.sum(), senza.sum()))
            testo = (f"{a2} → {a1}: quando tu dici «{n1}» e io «{n2}», va {erre(float(r[con].mean()))} "
                     f"({int(con.sum())} casi); senza di me {erre(float(r[senza].mean()))} ({int(senza.sum())}). "
                     + ("Ascoltami di più." if d > 0 else "Diffida quando ci sono anch'io."))
            trovati.append((forza, testo, (min(i1, i2), max(i1, i2))))
    trovati.sort(key=lambda t: -t[0])
    scelti, visti = [], set()
    for _, testo, coppia in trovati:
        if coppia in visti:
            continue
        visti.add(coppia)
        scelti.append((testo, coppia))
        if len(scelti) == quanti:
            break
    return scelti
