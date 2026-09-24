"""Gli agenti si confrontano: dopo ogni decisione, quando finisce, e alla riunione.

- **Dopo ogni decisione** ognuno dice se spinge a entrare o frena, e quanto:
  e' di quanto il suo parere sposta la stima del Capo (`Capo.spinte`).
- **Quando finisce** (presa o solo sulla carta) si guarda chi aveva ragione,
  e la pagella di ognuno si aggiorna.
- **Alla riunione** i consigli: le coppie di pareri che insieme vanno meglio
  (o peggio) che da soli. Il Capo le prova subito nel riaddestramento.
"""

from __future__ import annotations

from typing import Optional

from itertools import combinations

import numpy as np

from nvm.agenti.capo import COLONNE, Capo
from nvm.vivo.messaggi import erre, quando

# Quali colonne del Capo vengono da quale agente.
AGENTI: dict[str, tuple[int, ...]] = {
    "Cacciatore": (16, 17, 21, 24),
    "Grilletto": (14, 15),
    "Livelli": (18, 19, 20),
    "Key level": (0, 1, 2, 3, 4),
    "Orario": (5, 6, 7, 8, 9, 22, 23),
    "Bias": (10, 11, 12, 13, 25),
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
    "ora di Londra di Romeo": ("Orario", COLONNE.index("ora di Romeo: Londra")),
    "ora di New York di Romeo": ("Orario", COLONNE.index("ora di Romeo: New York")),
    "dentro un CRT più grande": ("Cacciatore", COLONNE.index("dentro un CRT più grande")),
    "a sconto sulla settimana": ("Bias", COLONNE.index("a sconto sulla settimana")),
}


def spinte(capo: Capo, x: np.ndarray) -> dict[str, float]:
    """La spinta di ogni agente su questa decisione. Le combinazioni contano meta' per ciascuno."""
    x = np.asarray(x, float)
    x = np.r_[x, np.zeros(len(COLONNE) - len(x))]
    s = capo.spinte(x)
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


# --- Le presentazioni all'avvio ---

LAVORO: dict[str, str] = {
    "Cacciatore": "Guardo se c'è un CRT: una candela fa da range e quella dopo ne spazza un lato. "
                  "Coppie: mensile → giornaliero, settimanale → 4 ore, giornaliero → 1 ora, 4 ore → 15 minuti. "
                  "E dico se il CRT sta dentro uno più grande, come vuole Romeo.",
    "Grilletto": "Aspetto il Model#1 di Romeo: la candela del turtle soup e la chiusura oltre la sua apertura. "
                 "Dopo uno stop posso sparare ancora, fino a tre colpi sullo stesso CRT.",
    "Livelli": "Metto lo stop oltre l'estremo della manipolazione, il primo target al 50% del range, il secondo al lato opposto.",
    "Key level": "Guardo se la manipolazione è arrivata su una zona del timeframe sopra: un massimo, un rejection block, un FVG.",
    "Orario": "Guardo a che ora di New York scatta l'ingresso. Le ore di Romeo: 1–5 (Londra) e 8–11 (New York); "
              "la sua golden candle è 9–13.",
    "Bias": "Leggo il bias dalle chiusure: la candela del range e il timeframe sopra, a favore o contro il CRT. "
            "E guardo se compriamo a sconto e vendiamo a premio sulla settimana.",
    "Rischio": "Scelgo quanto puntare: il criterio di Kelly sulle stime del Capo, e la parte che ho imparato dagli errori.",
    "Capo": "Ascolto tutti, peso i pareri e decido: entro solo se il guadagno atteso è sopra zero "
            "e se l'operazione somiglia a una che prenderebbe Romeo. Imparo dalle sue entrate e, ogni sabato, "
            "dagli errori della settimana.",
}


def _pagella(pagelle: dict, nome: str) -> str:
    giuste, totali = pagelle.get(nome, [0, 0])
    if not totali:
        return "pagella vuota: non ho ancora casi dal vivo"
    return f"pagella {giuste} su {totali} ({giuste / totali:.0%})"


def fiducia_per_agente(capo: Capo) -> dict[str, float]:
    """Quanto il Capo ascolta ogni agente: la somma dei pesi (in valore assoluto) delle sue colonne."""
    pesi = np.abs(capo.primo.pesi[1:])
    per = {nome: float(pesi[[c for c in col if c < len(pesi)]].sum()) for nome, col in AGENTI.items()}
    for k, (i, j) in enumerate(capo.interazioni):
        for nome, col in AGENTI.items():
            per[nome] += float(pesi[len(COLONNE) + k]) * ((i in col) + (j in col)) / 2
    return per


def presentazioni(pagelle: dict, capo: Capo, parte: float) -> list[str]:
    testi = []
    for nome, lavoro in LAVORO.items():
        g, t = pagelle.get(nome, [0, 0])
        righe = [f"👋 Sono il {nome}." if nome not in ("Key level", "Orario", "Bias", "Rischio") else f"👋 Sono l'agente {nome}.",
                 lavoro, f"Stato: {grado(g, t)}, {_pagella(pagelle, nome)}."]
        if nome == "Rischio":
            righe.append(f"Oggi uso {parte:.2f} del Kelly: l'ho imparato su 16 anni di puntate del Capo.".replace(".", ",", 1))
        if nome == "Capo":
            f = fiducia_per_agente(capo)
            ordine = sorted(f.items(), key=lambda a: -a[1])
            righe.append("Oggi ascolto soprattutto: " + ", ".join(n for n, _ in ordine[:3])
                         + "; meno: " + ", ".join(n for n, _ in ordine[-2:]) + ".")
            if capo.romeo is not None:
                pesi = sorted(capo.fiducia_romeo(), key=lambda a: -a[1])
                righe.append("Da Romeo ho imparato che le sue entrate hanno soprattutto: "
                             + ", ".join(n for n, w in pesi[:3] if w > 0) + ". "
                             + f"Entro solo sopra il {capo.soglia_romeo:.0%} di somiglianza.")
        righe.append(f"— {nome}")
        testi.append("\n".join(righe))
    return testi


# --- Le prove che ognuno porta, dallo storico ---

BINARIE: dict[str, tuple[int, ...]] = {
    "Cacciatore": (16, 17, 21, 24), "Grilletto": (14, 15), "Key level": (0, 1, 2, 3, 4),
    "Orario": (5, 6, 7, 8, 9, 22, 23), "Bias": (10, 11, 12, 13, 25),
}


def prove(x: np.ndarray, sx: np.ndarray, sr: np.ndarray) -> dict[str, str]:
    """Per ogni agente: com'è andata nello storico quando ha dato gli stessi segnali di adesso."""
    x = np.r_[np.asarray(x, float), np.zeros(len(COLONNE) - len(x))]
    testi = {}
    for nome, col in BINARIE.items():
        col = [c for c in col if c < sx.shape[1]]
        uguali = np.all(sx[:, col] == x[col], axis=1)
        if uguali.sum() >= 30:
            testi[nome] = f"nello storico, con gli stessi miei segnali: {erre(float(sr[uguali].mean()))} su {int(uguali.sum())} casi"
    rr1 = x[COLONNE.index("RR1")]
    vicini = np.abs(sx[:, COLONNE.index("RR1")] - rr1) <= 0.2 * max(rr1, 0.5)
    if vicini.sum() >= 30:
        testi["Livelli"] = f"con un primo target a {rr1:.1f} R, nello storico: {erre(float(sr[vicini].mean()))} su {int(vicini.sum())} casi".replace(".", ",", 1)
    return testi


def discussione_con_prove(per: dict[str, float], entra: bool, atteso: float, testi: dict[str, str],
                          romeo: Optional[float] = None, soglia: Optional[float] = None) -> str:
    righe = ["💬 Il confronto:"]
    for nome, v in sorted(per.items(), key=lambda a: -a[1]):
        posizione = "spingo a entrare" if v >= NEUTRO else ("freno" if v <= -NEUTRO else "resto neutro")
        righe.append(f"  {nome}: {posizione} ({v:+.2f})".replace(".", ",") + (f", {testi[nome]}." if nome in testi else "."))
    favore = sum(v >= NEUTRO for v in per.values())
    contro = sum(v <= -NEUTRO for v in per.values())
    capo = f"  Capo: {favore} a favore, {contro} contro; tutto pesato il guadagno atteso è {erre(atteso)}"
    if romeo is not None and soglia:
        capo += f", e somiglia a un'entrata di Romeo al {romeo:.0%} (mi serve almeno il {soglia:.0%})"
    if entra:
        capo += ": entro."
    elif atteso > 0:
        capo += ": non entro, Romeo questa non la prenderebbe."
    else:
        capo += ": non entro."
    righe.append(capo)
    return "\n".join(righe)


# --- Dopo il risultato: come migliorare ---

_FASCE = {5: "21–01 NY", 6: "01–05 NY", 7: "05–09 NY", 8: "09–13 NY", 9: "13–17 NY"}
_KEY = {0: "massimo preso", 1: "arriva al massimo", 2: "rejection block", 3: "FVG", 4: "non so"}
_BIAS = {10: "range a favore", 11: "range contro", 12: "sopra a favore", 13: "sopra contro"}


def firma(nome: str, x) -> str:
    """I segnali che un agente ha dato su una decisione, in parole: la chiave del suo diario."""
    x = list(x) + [0.0] * (len(COLONNE) - len(x))
    si = lambda c: x[c] == 1
    if nome == "Cacciatore":
        return ("4 ore → 15 minuti" if si(21) else "giornaliero → 1 ora" if si(17)
                else "settimanale → 4 ore" if si(16) else "mensile → giornaliero")
    if nome == "Grilletto":
        return "terzo colpo" if si(15) else ("secondo colpo" if si(14) else "primo colpo")
    if nome == "Key level":
        return ", ".join(v for c, v in _KEY.items() if si(c)) or "nessuna zona"
    if nome == "Orario":
        return next((v for c, v in _FASCE.items() if si(c)), "17–21 NY")
    if nome == "Bias":
        return ", ".join(v for c, v in _BIAS.items() if si(c)) or "bias neutro"
    rr1 = x[COLONNE.index("RR1")]
    return ("primo target sotto 1 R" if rr1 < 1 else "primo target fra 1 e 2 R" if rr1 < 2
            else "primo target fra 2 e 3 R" if rr1 < 3 else "primo target oltre 3 R")


def aggiorna_diario(diario: dict, x, vinta: bool) -> None:
    for nome in list(BINARIE) + ["Livelli"]:
        f = firma(nome, x)
        diario.setdefault(nome, {}).setdefault(f, [0, 0])
        diario[nome][f][0] += int(vinta)
        diario[nome][f][1] += 1


def come_migliorare(torto: list[str], diario: dict, x) -> str:
    righe = []
    for nome in torto:
        if nome not in BINARIE and nome != "Livelli":
            continue
        f = firma(nome, x)
        v, t = diario.get(nome, {}).get(f, [0, 0])
        righe.append(f"  {nome}: ho sbagliato. Dal vivo, con «{f}», {v} vinte su {t}"
                     + (": se continua così, sabato chiedo al Capo di ascoltarmi meno quando lo vedo." if t >= 3 and v / t < 0.4
                        else ": troppo presto per cambiare idea, lo segno."))
    return ("🛠 Come miglioriamo:\n" + "\n".join(righe)) if righe else ""
