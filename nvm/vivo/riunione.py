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
from nvm.vivo.dialogo import AGENTI, ascolto, chi_aveva_ragione, consigli, grado
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
    # I candidati del 2023 e le scelte di Romeo fra loro: il Capo impara da qui
    # quanto un'operazione somiglia a Romeo (`spec/capo.md`).
    romeo_x: Optional[np.ndarray] = None
    romeo_y: Optional[np.ndarray] = None
    romeo_tp1: Optional[np.ndarray] = None

    @classmethod
    def carica(cls, percorso) -> "Storico":
        with np.load(percorso) as f:
            c = lambda k: f[k] if k in f.files else None
            return cls(f["x"], f["tp1"].astype(bool), f["tp2"].astype(bool), c("erre"), c("quando"), c("kelly_f"), c("kelly_r"),
                       c("romeo_x"), None if c("romeo_y") is None else f["romeo_y"].astype(bool),
                       None if c("romeo_tp1") is None else f["romeo_tp1"].astype(bool))


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
        return "pochi casi dal vivo, continuo a raccogliere"
    migliore = max(voci, key=lambda a: a[1] / a[2])
    peggiore = min(voci, key=lambda a: a[1] / a[2])
    testo = f"meglio con «{migliore[0]}» ({migliore[1]}/{migliore[2]})"
    if peggiore[0] != migliore[0]:
        testo += f", peggio con «{peggiore[0]}» ({peggiore[1]}/{peggiore[2]}): pesatemi meno lì"
    return testo


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
        f"📋 Riunione del sabato · settimana {settimana}",
        "",
        "La settimana",
        f"• {len(nuove)} decisioni, {sum(s.entrata for s in nuove)} prese",
        f"• Finite: prese {_media(prese)}, sulla carta {_media(scartate)}",
    ]
    if finite:
        stimato = float(np.mean([s.p1 for s in finite]))
        vero = float(np.mean([s.esito["tp1"] for s in finite]))
        giudizio = ("ero ottimista" if stimato > vero + 0.05 else ("ero prudente" if vero > stimato + 0.05 else "ci ho preso"))
        righe.append(f"• Stimavo il primo obiettivo al {stimato:.0%}, dal vivo è arrivato nel {vero:.0%}: {giudizio}")

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
    romeo = storico.romeo_x is not None and storico.romeo_x.shape[1] == len(COLONNE) and storico.romeo_y.any()
    if romeo:
        nuovo = nuovo.impara_romeo(storico.romeo_x, storico.romeo_y)
        # La fiducia in Romeo: dai risultati dei candidati del 2023 e di tutte le decisioni dal vivo.
        casi_x, casi_tp1 = [], []
        if storico.romeo_tp1 is not None:
            casi_x.append(storico.romeo_x)
            casi_tp1.append(storico.romeo_tp1)
        if finite:
            casi_x.append(np.array([_x(s) for s in finite]))
            casi_tp1.append(np.array([bool(s.esito["tp1"]) for s in finite]))
        if casi_x:
            nuovo = nuovo.impara_fiducia(np.vstack(casi_x), np.concatenate(casi_tp1))
    # Quanto il Capo ascolta ognuno, prima e dopo, sugli stessi casi.
    casi = storico.romeo_x if storico.romeo_x is not None and storico.romeo_x.shape[1] == len(COLONNE) else sx[-3000:]
    prima, dopo = ascolto(capo, casi), ascolto(nuovo, casi)

    settimanali: dict[str, list[int]] = {}
    for s in di_questa:
        ragione, torto = chi_aveva_ragione(s.spinte, s.esito["erre"] > 0)
        for n in ragione:
            settimanali.setdefault(n, [0, 0])[0] += 1
            settimanali[n][1] += 1
        for n in torto:
            settimanali.setdefault(n, [0, 0])[1] += 1

    righe += ["", "Le pagelle"]
    for nome in list(AGENTI) + (["Romeo"] if "Romeo" in dopo else []):
        g, t = settimanali.get(nome, [0, 0])
        tot = (pagelle or {}).get(nome, [0, 0])
        verso = ("di più" if dopo.get(nome, 0) > prima.get(nome, 0) * 1.05 + 1e-4
                 else ("di meno" if dopo.get(nome, 0) < prima.get(nome, 0) * 0.95 - 1e-4 else "come prima"))
        riga = (f"• {nome} — questa settimana {g} giuste su {t}"
                + (f", in tutto {tot[0]} su {tot[1]} ({grado(*tot)})" if tot[1] else "")
                + f". Lo ascolto {verso}: {erre(prima.get(nome, 0))[1:]} → {erre(dopo.get(nome, 0))[1:]}.")
        if nome == "Romeo":
            riga += f" Fiducia {_peso(capo.fiducia_in_romeo)} → {_peso(nuovo.fiducia_in_romeo)}."
        righe.append(riga)
        if nome in AGENTI:
            righe.append(f"  ↳ {_risposta(nome, diario)}")

    righe += ["", "Consigli fra agenti (da oggi li provo)"]
    righe += [f"• {testo}" for testo, _ in scelti] or ["• nessuna coppia che cambi davvero il risultato"]

    # Il Rischio: quanta parte del Kelly, sulle puntate passate e su quelle dal vivo.
    dal_vivo = [s for s in finite if s.atteso > 0]
    f = np.r_[storico.kelly_f if storico.kelly_f is not None else [],
              [kelly(esiti(s.p1, s.q, s.rr1, s.rr2, s.costi)) for s in dal_vivo]]
    r = np.r_[storico.kelly_r if storico.kelly_r is not None else [], [s.esito["erre"] for s in dal_vivo]]
    nuova_parte = impara_parte(f, r) if len(f) else parte
    if romeo:
        pesi_romeo = sorted(nuovo.fiducia_romeo(), key=lambda a: -a[1])
        righe += ["", "Romeo",
                  f"• Ho ripassato le sue {int(storico.romeo_y.sum())} entrate del 2023: le sue scelte hanno soprattutto "
                  + ", ".join(n for n, w in pesi_romeo[:3] if w > 0)]
        prese_simili = [s.romeo for s in nuove if s.entrata]
        scartate_simili = [s.romeo for s in nuove if not s.entrata]
        if prese_simili and scartate_simili:
            righe.append(f"• Le mie prese gli somigliavano al {np.mean(prese_simili):.1%}, le scartate al "
                         f"{np.mean(scartate_simili):.1%}".replace(".", ","))
    righe += [
        "",
        f"Rischio: uso {_peso(nuova_parte)[1:]} del Kelly (era {_peso(parte)[1:]}), rifatto su {len(f)} puntate, "
        f"{len(dal_vivo)} dal vivo.",
        "",
        f"Capo: mi sono riaddestrato su {len(storico.x)} operazioni dello storico e {len(finite)} dal vivo. "
        "Da adesso lavoro così. Buon fine settimana.",
    ]
    return "\n".join(righe), nuovo, nuova_parte
