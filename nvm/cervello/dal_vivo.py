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

from nvm.cervello.piani import PIANI, nome
from nvm.cervello.rete import ReteValori
from nvm.cervello.scuola import vista_dei_piani
from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI

ESEMPI = "cervelli_esempi.jsonl"
# I risultati si imparano dentro questa misura, in R.
TETTO = (-3.0, 5.0)


def carica(file: Path, cartella: Path) -> tuple[Optional[Squadra], dict]:
    """La squadra di scuola, con tutte le operazioni vere gia' imparate. Senza file: nessuna.
    Nelle informazioni, sotto "piani", il cervello dei Livelli che sceglie stop e obiettivi."""
    if not file.exists():
        return None, {}
    dati = json.loads(file.read_text(encoding="utf-8"))
    squadra = Squadra.da_dati(dati["squadra"])
    info = {k: v for k, v in dati.items() if k not in ("squadra", "piani")}
    info["piani"] = ReteValori.da_dati(dati["piani"]) if dati.get("piani") else None
    esempi = cartella / ESEMPI
    if esempi.exists():
        for riga in esempi.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                e = json.loads(riga)
                v = squadra.adatta({a: np.array([e["viste"][a]]) for a in AGENTI})
                if np.isfinite(e["w"]):
                    squadra.aggiorna(v, e["y"], min(e["w"], -TETTO[0]) if e["y"] == 0 else min(e["w"], TETTO[1]))
                _impara_piano(info["piani"], v, e.get("piano"), e.get("erre"))
    return squadra, info


def _per_i_piani(rete: ReteValori, v: dict) -> Optional[np.ndarray]:
    """Quello che vede il cervello dei piani; None se e' nato con viste di un'altra misura (per
    esempio prima degli occhi nuovi): allora si segue il piano di sempre finche' non si riallena."""
    x = vista_dei_piani({a: np.atleast_2d(v[a]) for a in AGENTI})
    return x if x.shape[1] == len(rete.media) else None


def _impara_piano(rete: Optional[ReteValori], v: dict, piano: Optional[int], erre: Optional[float]) -> None:
    """Il cervello dei piani impara il valore vero del piano seguito (gli altri non si sanno)."""
    if rete is None or piano is None or erre is None:
        return
    if not np.isfinite(erre):
        return
    valori = np.full((1, len(PIANI)), np.nan)
    valori[0, piano] = float(np.clip(erre, *TETTO))
    x = _per_i_piani(rete, v)
    if x is None:
        return
    prima = rete.come_dati()
    rete.aggiorna(x, valori)
    if not np.all(np.isfinite(rete.valori(x))):
        tornata = ReteValori.da_dati(prima)
        rete.w1, rete.b1, rete.w2, rete.b2 = tornata.w1, tornata.b1, tornata.w2, tornata.b2


def scegli_piano(rete: Optional[ReteValori], viste: dict, fattibili: Optional[list]) -> Optional[tuple[int, list]]:
    """Il piano che il cervello dei Livelli stima migliore, fra quelli che si possono fare."""
    if rete is None or not fattibili:
        return None
    x = _per_i_piani(rete, viste)
    if x is None:
        return None
    valori = rete.valori(x)[0]
    possibili = [j for j, op in enumerate(fattibili) if op is not None]
    if not possibili:
        return None
    j = max(possibili, key=lambda k: valori[k])
    return j, [float(x) for x in valori]


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


def impara(squadra: Squadra, cartella: Path, giudizio: dict, erre: float, piani: Optional[ReteValori] = None) -> None:
    """Un risultato vero: ogni cervello impara, e l'esempio resta per le prossime volte."""
    if not np.isfinite(erre):
        return
    # Un risultato fuori misura (uno stop quasi nullo fa R enormi) non deve travolgere quello che sanno.
    erre = float(np.clip(erre, *TETTO))
    y, w = float(erre > 0), abs(erre)
    v = {a: np.array([giudizio["viste"][a]]) for a in AGENTI}
    prima = squadra.come_dati()
    squadra.aggiorna(v, y, w)
    if not np.all(np.isfinite(squadra.giudica(v)[2])):
        # Se un passo li rompe, si torna indietro: meglio non imparare che impazzire.
        ripristino = Squadra.da_dati(prima)
        squadra.primi, squadra.secondi, squadra.capo = ripristino.primi, ripristino.secondi, ripristino.capo
    piano = giudizio.get("piano")
    _impara_piano(piani, squadra.adatta(v), piano, erre)
    cartella.mkdir(parents=True, exist_ok=True)
    with (cartella / ESEMPI).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"viste": giudizio["viste"], "y": y, "w": w, "piano": piano, "erre": float(erre)}) + "\n")


def voce_livelli(piano: int, valori: list) -> str:
    """Livelli dice quale piano sceglie e perche': quanto vale, contro il piano di sempre."""
    solito = PIANI.index(("estremo", "meta"))

    def r(x):
        return f"{x:+.2f}".replace(".", ",").replace("-", "−")
    testo = f"Scelgo {nome(PIANI[piano])}: in casi così vale {r(valori[piano])} volte il rischio"
    if piano != solito:
        testo += f", il piano di sempre {r(valori[solito])}"
    return testo + "."


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


def la_migliore(seguite: list, dal: int, al: int, fiducia_minima: float) -> Optional[str]:
    """L'occasione di oggi in cui i cervelli hanno creduto di piu', e quanto serviva per metterci
    soldi: cosi' si vede perche' sono stati fermi (o perche' sono entrati)."""
    oggi = [s for s in seguite if s.cervelli and dal <= s.quando < al]
    if not oggi:
        return None
    s = max(oggi, key=lambda x: x.cervelli["fiducia"])
    ci_credono = round(100 * s.cervelli["fiducia"])
    serve = round(100 * (1 + fiducia_minima) / 2)
    verso = "acquisto" if s.verso == "long" else "vendita"
    esito = "abbastanza per metterci soldi" if ci_credono >= serve else "non abbastanza per metterci soldi"
    return (f"• L'occasione più convincente per i cervelli: {s.strumento} in {verso}, ci credevano {ci_credono} su "
            f"100; per rischiare ne serve almeno {serve}: {esito}")
