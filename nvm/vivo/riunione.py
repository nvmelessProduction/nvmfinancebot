"""La riunione del fine settimana, sul canale equipe: piu' approfondita del
confronto che gli agenti fanno dopo ogni decisione.

1. com'e' andata la settimana, prese e scartate;
2. le pagelle: quante volte ognuno aveva ragione quando si e' schierato, e la carriera;
3. i consigli fra agenti: le coppie di pareri che insieme cambiano il risultato;
4. il Capo si riaddestra su storico + dal vivo, e prova subito i consigli.

La versione nuova entra in uso subito: gli agenti si addestrano, non si
bloccano (decisione dell'utente, 24/09/2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.capo import COLONNE, Capo, pesi_per_eta
from nvm.agenti.rischio import esiti, impara_parte, kelly
from nvm.vivo.dialogo import AGENTI, chi_aveva_ragione, consigli, fiducia_per_agente, grado
from nvm.vivo.messaggi import erre
from nvm.vivo.stato import Seguita


@dataclass
class Storico:
    x: np.ndarray
    tp1: np.ndarray
    tp2: np.ndarray
    erre: Optional[np.ndarray] = None
    quando: Optional[np.ndarray] = None
    # Le puntate di Kelly del cammino anno per anno e i loro risultati: il Rischio impara da qui.
    kelly_f: Optional[np.ndarray] = None
    kelly_r: Optional[np.ndarray] = None

    @classmethod
    def carica(cls, percorso) -> "Storico":
        with np.load(percorso) as f:
            c = lambda k: f[k] if k in f.files else None
            return cls(f["x"], f["tp1"].astype(bool), f["tp2"].astype(bool), c("erre"), c("quando"), c("kelly_f"), c("kelly_r"))


def _x(s: Seguita) -> list[float]:
    """Le colonne di una decisione, allungate se e' stata registrata prima di una colonna nuova."""
    return list(s.x) + [0.0] * (len(COLONNE) - len(s.x))


def _media(v: list[float]) -> str:
    return f"{len(v)} ({erre(float(np.mean(v)))})" if v else "0"


def _peso(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


def _risposta(nome: str, diario: dict) -> str:
    """Cosa risponde un agente al Capo: il suo segnale migliore e il peggiore dal vivo."""
    voci = [(f, v, t) for f, (v, t) in (diario or {}).get(nome, {}).items() if t >= 2]
    if not voci:
        return f"{nome}: ho ancora troppo pochi casi dal vivo per dire qualcosa di serio. Continuo a raccogliere."
    migliore = max(voci, key=lambda a: a[1] / a[2])
    peggiore = min(voci, key=lambda a: a[1] / a[2])
    testo = f"{nome}: dal vivo il mio segnale migliore è «{migliore[0]}» ({migliore[1]} su {migliore[2]})"
    if peggiore[0] != migliore[0]:
        testo += f", il peggiore «{peggiore[0]}» ({peggiore[1]} su {peggiore[2]}). Propongo di pesare meno il secondo"
    return testo + "."


def riunione(
    seguite: list[Seguita], capo: Capo, storico: Storico, dal: int, settimana: str,
    pagelle: Optional[dict] = None, parte: float = 1.0, diario: Optional[dict] = None,
) -> tuple[str, Capo, float]:
    finite = [s for s in seguite if s.esito is not None]
    di_questa = [s for s in finite if s.esito["quando"] >= dal]
    nuove = [s for s in seguite if s.quando >= dal]
    prese = [s.esito["erre"] for s in di_questa if s.entrata]
    scartate = [s.esito["erre"] for s in di_questa if not s.entrata]
    righe = [
        f"📋 Riunione del sabato col Capo ({settimana})",
        "",
        "Capo: cominciamo. La settimana:",
        f"  decisioni nuove {len(nuove)}, ne ho prese {sum(s.entrata for s in nuove)};",
        f"  finite: prese {_media(prese)}, scartate {_media(scartate)} (sulla carta).",
    ]
    if finite:
        stimato = float(np.mean([s.p1 for s in finite]))
        vero = float(np.mean([s.esito["tp1"] for s in finite]))
        righe.append(f"  Io stimavo il primo target al {stimato:.0%}, dal vivo è arrivato nel {vero:.0%} dei casi"
                     + (": ero troppo ottimista." if stimato > vero + 0.05 else (": ero troppo prudente." if vero > stimato + 0.05 else ": ci ho preso.")))

    # Il riaddestramento, fatto subito: il Capo parla a ognuno sapendo gia' quanto lo ascoltera'.
    sx = storico.x if storico.x.shape[1] == len(COLONNE) else np.c_[storico.x, np.zeros((len(storico.x), len(COLONNE) - storico.x.shape[1]))]
    x = np.vstack([sx] + ([np.array([_x(s) for s in finite])] if finite else []))
    tp1 = np.r_[storico.tp1, [s.esito["tp1"] for s in finite]].astype(bool)
    tp2 = np.r_[storico.tp2, [s.esito["tp2"] for s in finite]].astype(bool)
    scelti = []
    if storico.erre is not None:
        scelti = consigli(x, np.r_[storico.erre, [s.esito["erre"] for s in finite]])
    pesi = None
    if storico.quando is not None:
        quando = np.r_[storico.quando, [s.esito["quando"] for s in finite]]
        pesi = pesi_per_eta(quando, int(quando.max()))
    nuovo = Capo.allena(x, tp1, tp2, interazioni=tuple(c for _, c in scelti), pesi=pesi)
    prima, dopo = fiducia_per_agente(capo), fiducia_per_agente(nuovo)

    settimanali: dict[str, list[int]] = {}
    for s in di_questa:
        ragione, torto = chi_aveva_ragione(s.spinte, s.esito["erre"] > 0)
        for n in ragione:
            settimanali.setdefault(n, [0, 0])[0] += 1
            settimanali[n][1] += 1
        for n in torto:
            settimanali.setdefault(n, [0, 0])[1] += 1

    righe += ["", "Capo, a ognuno:"]
    for nome in AGENTI:
        g, t = settimanali.get(nome, [0, 0])
        verso = "di più" if dopo[nome] > prima[nome] * 1.05 else ("di meno" if dopo[nome] < prima[nome] * 0.95 else "come prima")
        tot = (pagelle or {}).get(nome, [0, 0])
        righe.append(
            f"  → {nome}: questa settimana avevi ragione {g} volte su {t}"
            + (f" (in tutto {tot[0]} su {tot[1]}, {grado(*tot)})" if tot[1] else "")
            + f". Dopo il riaddestramento ti ascolto {verso} ({_peso(prima[nome])} → {_peso(dopo[nome])})."
        )
        righe.append(f"     {_risposta(nome, diario)}")

    righe += ["", "I consigli fra agenti (li provo da oggi come combinazioni):"]
    righe += [f"  • {testo}" for testo, _ in scelti] or ["  • nessuna coppia che cambi davvero il risultato."]
    if scelti:
        pesi_nuovi = {n: a for n, a, _ in nuovo.fiducia()}
        righe.append("  Capo: il peso che do a ognuna: " + "; ".join(f"{n} {_peso(a)}" for n, a in pesi_nuovi.items() if " × " in n) + ".")

    # Il Rischio: quanta parte del Kelly, sulle puntate passate e su quelle dal vivo.
    dal_vivo = [s for s in finite if s.atteso > 0]
    f = np.r_[storico.kelly_f if storico.kelly_f is not None else [],
              [kelly(esiti(s.p1, s.q, s.rr1, s.rr2, s.costi)) for s in dal_vivo]]
    r = np.r_[storico.kelly_r if storico.kelly_r is not None else [], [s.esito["erre"] for s in dal_vivo]]
    nuova_parte = impara_parte(f, r) if len(f) else parte
    righe += [
        "",
        f"Rischio: rifatti i conti su {len(f)} puntate ({len(dal_vivo)} dal vivo), la parte del Kelly che fa crescere "
        f"di più il conto è {_peso(nuova_parte)[1:]} (era {_peso(parte)[1:]}).",
        "",
        f"Capo: mi sono riaddestrato su {len(storico.x)} operazioni dello storico e {len(finite)} dal vivo, "
        "con più peso ai casi recenti. Da adesso lavoro così. Buon fine settimana.",
    ]
    return "\n".join(righe), nuovo, nuova_parte
