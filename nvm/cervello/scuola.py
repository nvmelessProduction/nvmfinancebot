"""La scuola dei cervelli e il loro esame (`spec/cervello.md`).

Ogni settimana, in palestra, la squadra dei cervelli torna a scuola sui vent'anni e fa
l'esame contro il Capo di oggi: stesse occasioni, stesso Rischio, conto intero, ogni anno
deciso solo con gli anni prima. Se i cervelli fanno crescere il conto di piu', da quel momento
decidono loro; altrimenti restano in prova: dal vivo giudicano ogni occasione, si confrontano
e imparano da ogni risultato, ma i soldi li muove il Capo.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np

from nvm.agenti import portafoglio
from nvm.agenti.capo import pesi_per_eta
from nvm.agenti.portafoglio import Operazioni
from nvm.cervello.rete import ReteValori
from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI

# Sopra questa fiducia la squadra dei cervelli entrerebbe: e' la probabilita' pesata che
# l'operazione guadagni, quindi 0,5 vuol dire guadagno atteso sopra zero.
SOGLIA = 0.5
PRIMO_ESAME, ULTIMO_ESAME = 2012, 2023


def _istante(anno: int) -> int:
    return int(datetime(anno, 1, 1, tzinfo=timezone.utc).timestamp())


def obiettivo(erre: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cosa imparano: se l'operazione ha guadagnato, pesata per quanto (una perdita grande
    insegna piu' di una piccola)."""
    erre = np.asarray(erre, float)
    return (erre > 0).astype(float), np.abs(erre)


def allena(t, fino_a: int, confronto: bool = True) -> Squadra:
    """La squadra a scuola sulle operazioni chiuse prima di `fino_a`, in ordine di tempo, con le
    piu' recenti che pesano di piu'."""
    tr = np.flatnonzero(t.chiusa < fino_a)
    tr = tr[np.argsort(t.quando[tr], kind="stable")]
    y, w = obiettivo(t.erre[tr])
    return Squadra.allena({a: t.viste[a][tr] for a in AGENTI}, y, w * pesi_per_eta(t.chiusa[tr], fino_a), confronto)


def _operazioni(t, scelte: np.ndarray, fiducia: np.ndarray) -> Operazioni:
    return Operazioni(t.quando[scelte], t.chiusa[scelte], t.strumento[scelte], t.verso[scelte], fiducia[scelte],
                      t.erre[scelte])


def _conto(op: Operazioni, primo: int, ultimo: int) -> dict:
    """Il conto intero fuori campione: ogni anno il Rischio sceglie sugli anni prima."""
    anni = np.array([datetime.fromtimestamp(int(q), tz=timezone.utc).year for q in op.entrata])
    totale, pezzi = 0.0, []
    for a in range(primo, ultimo + 1):
        s = portafoglio.scegli(op.fino_a(_istante(a)), None)
        m = anni == a
        c = portafoglio.simula(Operazioni(op.entrata[m], op.chiusa[m], op.strumento[m], op.verso[m], op.kelly[m],
                                          op.erre[m]), s.parte, None, s.minimo)
        pezzi.append(totale + np.concatenate([[0.0]] + [c.percorsi[k] for k in sorted(c.percorsi)]))
        totale += np.log(c.finale) if c.finale > 0 else -np.inf
    cammino = np.concatenate(pezzi)
    calo = 1 - np.exp((cammino - np.maximum.accumulate(cammino)).min())
    return {"crescita": float(np.expm1(totale / (ultimo - primo + 1))), "calo": float(calo)}


def fiducia_anno_per_anno(t) -> np.ndarray:
    """La fiducia della squadra su ogni operazione dal 2010, allenata ogni anno sugli anni prima."""
    anni = t.anno
    p = np.full(len(t), np.nan)
    for a in range(PRIMO_ESAME - 2, ULTIMO_ESAME + 1):
        oggi = np.flatnonzero(anni == a)
        if len(oggi):
            p[oggi] = allena(t, _istante(a)).giudica({k: t.viste[k][oggi] for k in AGENTI})[2]
    return p


def esame(t, kelly_capo: np.ndarray, entra_capo: np.ndarray, p: np.ndarray, dire=print) -> dict:
    """I cervelli contro il Capo di oggi, sul conto intero fuori campione. `kelly_capo` e
    `entra_capo`: le puntate e le scelte del Capo anno per anno (allenato sugli anni prima);
    `p` la fiducia dei cervelli, anno per anno."""
    t0 = time.time()
    anni = t.anno
    dal = anni >= PRIMO_ESAME - 2
    cervelli = _conto(_operazioni(t, dal & (p > SOGLIA), np.clip(2 * p - 1, 0, None)), PRIMO_ESAME, ULTIMO_ESAME)
    capo = _conto(_operazioni(t, dal & entra_capo, kelly_capo), PRIMO_ESAME, ULTIMO_ESAME)
    dire(f"Esame dei cervelli ({PRIMO_ESAME}-{ULTIMO_ESAME}, conto intero fuori campione): cervelli "
         f"{cervelli['crescita']:+.1%} l'anno (calo {cervelli['calo']:.0%}), Capo di oggi {capo['crescita']:+.1%} "
         f"(calo {capo['calo']:.0%}). {round(time.time() - t0)} s")
    return {"cervelli": cervelli, "capo": capo, "decidono": cervelli["crescita"] > capo["crescita"]
            and cervelli["calo"] <= portafoglio.CALO_MASSIMO + 0.05}


def per_il_vivo(t, kelly_capo: np.ndarray, entra_capo: np.ndarray, dire=print) -> dict:
    """La squadra allenata su tutto, con l'esito dell'esame, per il bot dal vivo (`cervelli.json`)."""
    p = fiducia_anno_per_anno(t)
    risultato = esame(t, kelly_capo, entra_capo, p, dire)
    squadra = allena(t, int(t.chiusa.max()) + 1)
    # Il Rischio per le scelte dei cervelli, se un giorno decideranno loro: la loro fiducia
    # (2p - 1) al posto del Kelly del Capo, con parte e fiducia minima imparate sul conto intero.
    dal = t.anno >= PRIMO_ESAME - 2
    s = portafoglio.scegli(_operazioni(t, dal & (p > SOGLIA), np.clip(2 * p - 1, 0, None)), None)
    dati = {"quando": int(time.time()), "squadra": squadra.come_dati(), "esame": risultato,
            "decidono": bool(risultato["decidono"]), "soglia": SOGLIA,
            "rischio": {"parte": s.parte, "minimo": s.minimo}}
    if t.piani is not None:
        dati["piani"] = allena_piani(t, int(t.chiusa.max()) + 1).come_dati()
    return dati


def vista_dei_piani(viste: dict) -> np.ndarray:
    """Cosa guarda Livelli per scegliere stop e obiettivi: quello che vede lui e i colleghi."""
    return np.hstack([np.atleast_2d(viste[a]) for a in AGENTI])


def allena_piani(t, fino_a: int) -> ReteValori:
    """Il cervello dei Livelli che stima quanto vale ogni piano (`piani.py`) nella situazione."""
    tr = np.flatnonzero(t.chiusa < fino_a)
    tr = tr[np.argsort(t.quando[tr], kind="stable")]
    return ReteValori.allena(vista_dei_piani({a: t.viste[a][tr] for a in AGENTI}), t.piani[tr],
                             pesi_per_eta(t.chiusa[tr], fino_a))
