"""Gli agenti si confrontano: dopo ogni decisione, quando finisce, e alla riunione.

- **Dopo ogni decisione** ognuno dice se spinge a entrare o frena, e quanto:
  e' di quanto il suo parere sposta la stima del Capo (`Capo.spinte`).
- **Quando finisce** (presa o solo sulla carta) si guarda chi aveva ragione,
  e la pagella di ognuno si aggiorna.
- **Alla riunione** i consigli: le coppie di pareri che insieme vanno meglio
  (o peggio) che da soli. Il Capo le prova subito nel riaddestramento.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from typing import Optional

import numpy as np

from nvm.agenti.capo import COLONNE, COLONNE_BASE, INVENTATE, Capo
from nvm.vivo.messaggi import erre, quando

# Quali colonne del Capo vengono da quale agente.
AGENTI: dict[str, tuple[int, ...]] = {
    "Cacciatore": (16, 17, 21, 24),
    "Grilletto": (14, 15, 26, 27),
    "Livelli": (18, 19, 20),
    "Key level": (0, 1, 2, 3, 4),
    "Orario": (5, 6, 7, 8, 9, 22, 23),
    "Bias": (10, 11, 12, 13, 25),
}
# Le domande che gli agenti hanno inventato sono loro: il Capo le conta nella loro voce.
for _i, _d in enumerate(INVENTATE):
    AGENTI[_d.agente] = AGENTI.get(_d.agente, ()) + (len(COLONNE_BASE) + _i,)
# Sotto questa spinta un agente non si schiera.
NEUTRO = 0.015

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
    "liquidità presa prima": ("Grilletto", COLONNE.index("liquidità presa prima")),
    "liquidità ripresa fuori dal CRT": ("Grilletto", COLONNE.index("liquidità presa sopra il CRT")),
}


def spinte_su_casi(capo: Capo, x: np.ndarray) -> dict[str, np.ndarray]:
    """Di quanto il parere di ogni agente sposta la qualita' attesa, su cui il Capo decide,
    caso per caso: la qualita' attesa vera meno quella che il Capo avrebbe stimato se
    l'agente avesse dato le risposte di un caso medio. Per Romeo: meno quella che avrebbe
    stimato senza ascoltarlo."""
    x = np.atleast_2d(np.asarray(x, float))
    if x.shape[1] < len(COLONNE):
        x = np.c_[x, np.zeros((len(x), len(COLONNE) - x.shape[1]))]
    zero = np.zeros(len(x))
    rr1, rr2 = COLONNE.index("RR1"), COLONNE.index("RR2")
    tutto = capo.qualita(x, x[:, rr1], x[:, rr2], zero)
    media = capo.media[:len(COLONNE)]
    per = {}
    for nome, col in AGENTI.items():
        medio = x.copy()
        medio[:, list(col)] = media[list(col)]
        per[nome] = tutto - capo.qualita(medio, medio[:, rr1], medio[:, rr2], zero)
    if capo.romeo is not None and capo.fiducia_in_romeo != 0:
        senza = replace(capo, fiducia_in_romeo=0.0)
        per["Romeo"] = tutto - senza.qualita(x, x[:, rr1], x[:, rr2], zero)
    return per


def spinte(capo: Capo, x: np.ndarray) -> dict[str, float]:
    """La spinta di ogni agente su questa decisione, sulla qualita' attesa."""
    return {nome: float(v[0]) for nome, v in spinte_su_casi(capo, x).items()}


def ascolto(capo: Capo, casi: np.ndarray) -> dict[str, float]:
    """Quanto il Capo ascolta ognuno: di quanto, in media, il suo parere sposta la qualita' attesa."""
    return {nome: float(np.abs(v).mean()) for nome, v in spinte_su_casi(capo, casi).items()}


def _schieramento(per: dict[str, float]) -> tuple[list[str], list[str]]:
    favore = [f"{n} ({v:+.2f})".replace(".", ",") for n, v in sorted(per.items(), key=lambda a: -a[1]) if v >= NEUTRO]
    contro = [f"{n} ({v:+.2f})".replace(".", ",") for n, v in sorted(per.items(), key=lambda a: a[1]) if v <= -NEUTRO]
    return favore, contro


def chi_aveva_ragione(per: dict[str, float], vinta: bool) -> tuple[list[str], list[str]]:
    ragione = [n for n, v in per.items() if abs(v) >= NEUTRO and (v > 0) == vinta]
    torto = [n for n, v in per.items() if abs(v) >= NEUTRO and (v > 0) != vinta]
    return ragione, torto


def resoconto(chiave_leggibile: str, esito: dict, entrata: bool, per: dict[str, float], decisa: bool) -> tuple[str, list[str], list[str]]:
    """`decisa`: se il Capo aveva deciso di entrare (anche se poi l'ordine non e' partito)."""
    vinta = esito["erre"] > 0
    ragione, torto = chi_aveva_ragione(per, vinta)
    capo_ok = decisa == vinta
    uscita = str(esito["uscita"])
    testo = "\n".join([
        f"📊 Com'è finita: {chiave_leggibile}",
        f"{uscita[:1].upper() + uscita[1:]} · {erre(esito['erre'])} · " + ("presa" if entrata else "non presa, seguita sulla carta"),
        "Avevano visto giusto: " + (", ".join(ragione) if ragione else "nessuno"),
        "Avevano sbagliato: " + (", ".join(torto) if torto else "nessuno"),
        "Capo: " + ("decisione giusta." if capo_ok else "decisione sbagliata."),
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
            testo = (f"{a2} a {a1}: con «{n1}» e «{n2}» insieme va {erre(float(r[con].mean()))} "
                     f"({int(con.sum()):,} casi), con «{n1}» da solo {erre(float(r[senza].mean()))}. ".replace(",", ".")
                     + ("Insieme valiamo di più." if d > 0 else "Quando ci sono anch'io, fidati meno."))
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
    "Cacciatore": "Cerco i CRT: una candela fa da range, quella dopo ne prende un lato e rientra. "
                  "Guardo mensile → giornaliero, settimanale → 4 ore, giornaliero → 1 ora, 4 ore → 15 minuti, "
                  "e dico se il CRT sta dentro uno più grande.",
    "Grilletto": "Aspetto il Model#1 di Romeo: dopo il turtle soup, la chiusura oltre la sua apertura. "
                 "Se lo stop viene preso posso riprovare, fino a tre volte sullo stesso CRT. "
                 "E dico se la manipolazione ha preso la liquidità lasciata prima: la terza gamba del suo manuale.",
    "Livelli": "Metto lo stop oltre l'estremo, il primo obiettivo a metà del range, il secondo dall'altra parte.",
    "Key level": "Dico se il prezzo è arrivato su una zona del timeframe sopra: un massimo, un rejection block, un FVG.",
    "Orario": "Dico a che ora di New York scatta l'ingresso. Le ore di Romeo sono 1–5 (Londra) e 8–11 (New York).",
    "Bias": "Leggo la direzione dalle chiusure delle candele, e dico se compriamo a sconto o vendiamo a premio "
            "rispetto alla settimana prima.",
    "Romeo": "Sono la voce di Romeo: dalle sue entrate ho imparato quanto un'operazione gli somiglia. "
             "Il Capo mi ascolta quanto i risultati gli dicono di fare. Quando vedete una sua entrata nuova, "
             "mandatemela così: /romeo EURUSD compra 1.0765 stop 1.0760. Vi dico se l'avevamo vista, "
             "e il sabato imparo da lei.",
    "Rischio": "Scelgo quanto puntare: il criterio di Kelly sulle stime del Capo, nella misura che ho imparato.",
    "Capo": "Ascolto tutti e decido sulle prestazioni, non sul guadagno: entro se la qualità attesa "
            "(quanto rende l'operazione diviso per quanto può oscillare) supera la mia soglia, che alleno "
            "in palestra come gli altri le loro manopole. Ogni sabato imparo dai risultati quanto fidarmi di ognuno.",
}


def _pagella(pagelle: dict, nome: str) -> str:
    giuste, totali = pagelle.get(nome, [0, 0])
    if not totali:
        return "ancora vuota, nessun caso dal vivo"
    return f"{giuste} giuste su {totali} ({giuste / totali:.0%})"


def fiducia_per_agente(capo: Capo) -> dict[str, float]:
    """Quanto il Capo ascolta ogni agente: la somma dei pesi (in valore assoluto) delle sue colonne."""
    pesi = np.abs(capo.primo.pesi[1:])
    per = {nome: float(pesi[[c for c in col if c < len(pesi)]].sum()) for nome, col in AGENTI.items()}
    for k, (i, j) in enumerate(capo.interazioni):
        for nome, col in AGENTI.items():
            per[nome] += float(pesi[len(COLONNE) + k]) * ((i in col) + (j in col)) / 2
    if capo.romeo is not None:
        per["Romeo"] = abs(capo.fiducia_in_romeo)
    return per


def presentazioni(pagelle: dict, capo: Capo, parte: float, casi: Optional[np.ndarray] = None) -> list[str]:
    """Ogni membro dell'équipe si presenta: cosa fa, com'è andato finora."""
    quanto = ascolto(capo, casi) if casi is not None and len(casi) else {}
    testi = []
    for nome, lavoro in LAVORO.items():
        g, t = pagelle.get(nome, [0, 0])
        righe = [f"👋 {nome}", lavoro, f"Pagella: {_pagella(pagelle, nome)} · {grado(g, t)}"]
        if nome == "Romeo":
            righe.append("Il Capo non ha ancora imparato niente da me." if capo.romeo is None else
                         f"Il Capo mi dà una fiducia di {_virgola(capo.fiducia_in_romeo, segno=True)}, imparata dai risultati.")
        if nome == "Rischio":
            righe.append(f"Uso {_virgola(parte)} del Kelly: l'ho imparato su 16 anni di puntate del Capo.")
        if nome == "Capo" and quanto:
            ordine = sorted(quanto.items(), key=lambda a: -a[1])
            forti = [n for n, v in ordine if v >= NEUTRO]
            deboli = [n for n, v in ordine if v < NEUTRO]
            righe.append("Ascolto soprattutto: " + (", ".join(forti[:3]) or "nessuno in particolare") + ".")
            if deboli:
                righe.append(f"Per ora conta poco: {', '.join(deboli)}. Non sono esclusi: nei dati i loro segnali "
                             "hanno cambiato poco i risultati. Se dal vivo cambiano, il sabato li ascolto di più.")
        testi.append("\n".join(righe))
    return testi


def _virgola(x: float, segno: bool = False) -> str:
    return (f"{x:+.2f}" if segno else f"{x:.2f}").replace(".", ",")


# --- Il diario dal vivo ---

BINARIE: dict[str, tuple[int, ...]] = {
    "Cacciatore": (16, 17, 21, 24), "Grilletto": (14, 15, 26, 27), "Key level": (0, 1, 2, 3, 4),
    "Orario": (5, 6, 7, 8, 9, 22, 23), "Bias": (10, 11, 12, 13, 25),
}


# --- I segnali di ogni agente, in parole ---

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
        colpo = "terzo colpo" if si(15) else ("secondo colpo" if si(14) else "primo colpo")
        liquidita = ("liquidità ripresa fuori dal CRT" if si(27) else "liquidità presa prima" if si(26)
                     else "senza liquidità presa")
        return f"{colpo}, {liquidita}"
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
