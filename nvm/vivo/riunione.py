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

from nvm.agenti.capo import Capo, pesi_per_eta
from nvm.agenti.rischio import esiti, impara_parte, kelly
from nvm.vivo.dialogo import consigli, grado
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


def _media(v: list[float]) -> str:
    return f"{len(v)} ({erre(float(np.mean(v)))})" if v else "0"


def _peso(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


def riunione(
    seguite: list[Seguita], capo: Capo, storico: Storico, dal: int, settimana: str,
    pagelle: Optional[dict] = None, parte: float = 1.0,
) -> tuple[str, Capo, float]:
    finite = [s for s in seguite if s.esito is not None]
    di_questa = [s for s in finite if s.esito["quando"] >= dal]
    nuove = [s for s in seguite if s.quando >= dal]
    prese = [s.esito["erre"] for s in di_questa if s.entrata]
    scartate = [s.esito["erre"] for s in di_questa if not s.entrata]
    righe = [
        f"📋 Riunione del fine settimana ({settimana})",
        "",
        "1. La settimana",
        f"Decisioni nuove: {len(nuove)}, il Capo ne ha prese {sum(s.entrata for s in nuove)}.",
        f"Finite: prese {_media(prese)}, scartate {_media(scartate)} (sulla carta).",
    ]
    if finite:
        stimato = float(np.mean([s.p1 for s in finite]))
        vero = float(np.mean([s.esito["tp1"] for s in finite]))
        righe.append(f"Capo: stimavo il primo target al {stimato:.0%}, dal vivo è arrivato nel {vero:.0%} dei casi.")

    righe += ["", "2. Le pagelle (volte in cui aveva ragione quando si è schierato)"]
    if pagelle:
        for nome, (giuste, totali) in sorted(pagelle.items(), key=lambda a: -a[1][0] / max(a[1][1], 1)):
            righe.append(f"• {nome}: {giuste} su {totali} ({giuste / max(totali, 1):.0%}), {grado(giuste, totali)}")
    else:
        righe.append("• Nessuna decisione finita ancora: tutti neolaureati.")

    # 3. I consigli: sullo storico e sul vivo insieme.
    x = np.vstack([storico.x] + ([np.array([s.x for s in finite])] if finite else []))
    tp1 = np.r_[storico.tp1, [s.esito["tp1"] for s in finite]].astype(bool)
    tp2 = np.r_[storico.tp2, [s.esito["tp2"] for s in finite]].astype(bool)
    righe += ["", "3. I consigli fra agenti"]
    scelti = []
    if storico.erre is not None:
        r = np.r_[storico.erre, [s.esito["erre"] for s in finite]]
        scelti = consigli(x, r)
        righe += [f"• {testo}" for testo, _ in scelti] or ["• Nessuna coppia che cambi davvero il risultato."]
    else:
        righe.append("• Senza i risultati dello storico non si possono cercare.")

    # 4. Il riaddestramento, con i consigli come combinazioni da provare.
    # I casi recenti pesano di piu': gli errori dal vivo contano davvero.
    pesi = None
    if storico.quando is not None:
        quando = np.r_[storico.quando, [s.esito["quando"] for s in finite]]
        pesi = pesi_per_eta(quando, int(quando.max()))
    nuovo = Capo.allena(x, tp1, tp2, interazioni=tuple(c for _, c in scelti), pesi=pesi)
    prima = {n: a for n, a, _ in capo.fiducia()}
    dopo = [c for c in nuovo.fiducia() if c[0] in prima]
    cambi = sorted(dopo, key=lambda c: -abs(c[1] - prima[c[0]]))[:3]
    righe += [
        "",
        "4. Il Capo si riaddestra",
        f"Su {len(storico.x)} operazioni dello storico e {len(finite)} dal vivo.",
        "Dove ha cambiato idea di più (peso sul primo target): "
        + "; ".join(f"{n} {_peso(prima[n])} → {_peso(a)}" for n, a, _ in cambi) + ".",
    ]
    if scelti:
        pesi = {n: a for n, a, _ in nuovo.fiducia()}
        righe.append("Le combinazioni dei consigli, col peso che il Capo ha dato: "
                     + "; ".join(f"{n} {_peso(a)}" for n, a in pesi.items() if " × " in n) + ".")

    # 5. Il Rischio: quanta parte del Kelly, sulle puntate passate e su quelle dal vivo.
    dal_vivo = [s for s in finite if s.atteso > 0]
    f = np.r_[storico.kelly_f if storico.kelly_f is not None else [],
              [kelly(esiti(s.p1, s.q, s.rr1, s.rr2, s.costi)) for s in dal_vivo]]
    r = np.r_[storico.kelly_r if storico.kelly_r is not None else [], [s.esito["erre"] for s in dal_vivo]]
    nuova_parte = impara_parte(f, r) if len(f) else parte
    righe += [
        "",
        "5. Il Rischio si riaddestra",
        f"Su {len(f)} puntate ({len(dal_vivo)} dal vivo): la parte del Kelly che fa crescere di più il conto "
        f"è {nuova_parte:.2f} (era {parte:.2f}).",
    ]
    return "\n".join(righe), nuovo, nuova_parte
