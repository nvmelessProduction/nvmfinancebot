"""I cervelli nel mondo reale.

Il bot carica la squadra uscita da scuola (`nvm/vivo/cervelli.json`, rifatta ogni settimana in
palestra) e le rifa' imparare tutte le operazioni vere viste finora (`dati/vivo/
cervelli_esempi.jsonl`): cosi' quello che hanno imparato dal vivo non si perde quando tornano
a scuola. A ogni occasione giudicano e si confrontano; a ogni risultato imparano.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI

ESEMPI = "cervelli_esempi.jsonl"


def carica(file: Path, cartella: Path) -> tuple[Optional[Squadra], dict]:
    """La squadra di scuola, con tutte le operazioni vere gia' imparate. Senza file: nessuna."""
    if not file.exists():
        return None, {}
    dati = json.loads(file.read_text(encoding="utf-8"))
    squadra = Squadra.da_dati(dati["squadra"])
    esempi = cartella / ESEMPI
    if esempi.exists():
        for riga in esempi.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                e = json.loads(riga)
                squadra.aggiorna({a: np.array([e["viste"][a]]) for a in AGENTI}, e["y"], e["w"])
    return squadra, {k: v for k, v in dati.items() if k != "squadra"}


def _cento(logit: float) -> int:
    return int(round(100 / (1 + np.exp(-logit))))


def giudica(squadra: Squadra, viste: dict) -> dict:
    """Il primo giudizio di ognuno, quello dopo il confronto, chi ha convinto chi, e la fiducia
    della squadra (su 100: quanto credono che l'operazione guadagni)."""
    v = {a: np.atleast_2d(viste[a]) for a in AGENTI}
    primo, dopo, p = squadra.giudica(v)
    convinti = squadra.chi_ha_convinto(v)
    return {"primo": {a: _cento(float(primo[a][0])) for a in AGENTI},
            "dopo": {a: _cento(float(dopo[a][0])) for a in AGENTI},
            "convinti": {a: [b, float(e)] for a, (b, e) in convinti.items()},
            "fiducia": float(p[0]), "viste": {a: [round(float(x), 5) for x in viste[a]] for a in AGENTI}}


def impara(squadra: Squadra, cartella: Path, giudizio: dict, erre: float) -> None:
    """Un risultato vero: ogni cervello impara, e l'esempio resta per le prossime volte."""
    y, w = float(erre > 0), abs(float(erre))
    squadra.aggiorna({a: np.array([giudizio["viste"][a]]) for a in AGENTI}, y, w)
    cartella.mkdir(parents=True, exist_ok=True)
    with (cartella / ESEMPI).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"viste": giudizio["viste"], "y": y, "w": w}) + "\n")


# Da quanti punti su 100 un cambio d'idea si racconta.
CAMBIO = 3


def voce(g: dict, soglia: float, decidono: bool) -> str:
    """Il ragionamento dei cervelli su un'operazione, in un messaggio."""
    primi = ", ".join(f"{a} {g['primo'][a]}" for a in AGENTI)
    cambi = []
    for a in AGENTI:
        prima, dopo = g["primo"][a], g["dopo"][a]
        if abs(dopo - prima) >= CAMBIO:
            chi = g["convinti"].get(a, [None])[0]
            cambi.append(f"{a} da {prima} a {dopo}" + (f" (l'ha convinto {chi})" if chi else ""))
    fiducia = round(100 * g["fiducia"])
    entra = g["fiducia"] > soglia
    righe = [f"Quanto ci crediamo, su 100: {primi}."]
    righe.append("Dopo il confronto: " + ("; ".join(cambi) + "." if cambi else "nessuno ha cambiato idea."))
    if decidono:
        righe.append(f"Pesando i nostri giudizi (quanto ognuno ha avuto ragione a scuola): {fiducia} su 100: "
                     + ("entriamo." if entra else "non entriamo."))
    else:
        righe.append(f"Pesando i nostri giudizi (quanto ognuno ha avuto ragione a scuola): {fiducia} su 100, "
                     + ("entreremmo." if entra else "non entreremmo.")
                     + " Siamo in prova: decidiamo solo quando all'esame battiamo il Capo.")
    return "\n".join(righe)


def capo_quando_decidono(p1: float, capo_entrava: bool) -> str:
    """Il Capo quando decidono i cervelli: lo dice, e dice cosa avrebbe fatto lui."""
    return (f"Decidono i cervelli, scelta del proprietario. Io, col mio vecchio calcolo, "
            f"{'sarei entrato anch' + chr(39) + 'io' if capo_entrava else 'non sarei entrato'} "
            f"({round(100 * p1)} possibilità su 100 di arrivare al primo obiettivo).")


def gara(seguite: list, dal: int, al: int, soglia: float) -> Optional[str]:
    """La giornata, sulle occasioni finite: cosa avrebbero fatto i cervelli e cosa il Capo."""
    finite = [s for s in seguite if s.esito is not None and s.cervelli and dal <= s.esito["quando"] < al]
    if not finite:
        return None
    loro = [float(s.esito["erre"]) for s in finite if s.cervelli["fiducia"] > soglia]
    capo = [float(s.esito["erre"]) for s in finite if s.cervelli.get("capo", s.presa_dal_capo)]

    def v(x):
        return f"{sum(x):+.2f}".replace(".", ",").replace("-", "−") + " volte il rischio"
    return (f"• Cervelli contro Capo, sulle {len(finite)} occasioni finite oggi: i cervelli ne avrebbero prese "
            f"{len(loro)} ({v(loro)}), il Capo {len(capo)} ({v(capo)})")
