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
from typing import Optional

import numpy as np

from nvm.agenti import portafoglio
from nvm.agenti.capo import pesi_per_eta
from nvm.agenti.portafoglio import Operazioni
from nvm.cervello.genoma import come_dati as genomi_come_dati, modifiche
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


def allena(t, fino_a: int, confronto: bool = True, genomi: Optional[dict] = None) -> Squadra:
    """La squadra a scuola sulle operazioni chiuse prima di `fino_a`, in ordine di tempo, con le
    piu' recenti che pesano di piu'. `genomi`: com'e' fatto il cervello di ognuno."""
    tr = np.flatnonzero(t.chiusa < fino_a)
    tr = tr[np.argsort(t.quando[tr], kind="stable")]
    y, w = obiettivo(t.erre[tr])
    return Squadra.allena({a: t.viste[a][tr] for a in AGENTI}, y, w * pesi_per_eta(t.chiusa[tr], fino_a), confronto,
                          genomi=genomi)


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


def fiducia_anno_per_anno(t, genomi: Optional[dict] = None) -> np.ndarray:
    """La fiducia della squadra su ogni operazione dal 2010, allenata ogni anno sugli anni prima."""
    anni = t.anno
    p = np.full(len(t), np.nan)
    for a in range(PRIMO_ESAME - 2, ULTIMO_ESAME + 1):
        oggi = np.flatnonzero(anni == a)
        if len(oggi):
            p[oggi] = allena(t, _istante(a), genomi=genomi).giudica({k: t.viste[k][oggi] for k in AGENTI})[2]
    return p


# --- I cervelli si modificano da soli (`genoma.py`) -------------------------------------------

# Una modifica resta se la squadra va meglio nel complesso, in almeno questa parte degli anni,
# e con un miglioramento almeno pari alla sua incertezza anno per anno.
ANNI_MEGLIO = 0.6


def resa(t, p: np.ndarray) -> tuple[float, dict]:
    """Quanto rende quello su cui la squadra scommetterebbe: il R medio pesato per la sua fiducia
    (2p - 1, solo sopra la soglia), nel complesso e anno per anno."""
    w = np.clip(2 * np.nan_to_num(p) - 1, 0, None)
    anni = t.anno
    per_anno = {}
    for a in range(PRIMO_ESAME - 2, ULTIMO_ESAME + 1):
        m = (anni == a) & (w > 0)
        per_anno[a] = float((w[m] * t.erre[m]).sum() / w[m].sum()) if w[m].sum() > 0 else 0.0
    return (float((w * t.erre).sum() / w.sum()) if w.sum() > 0 else 0.0), per_anno


def _passa(nuova: tuple, vecchia: tuple) -> tuple[bool, float, int, int]:
    d = np.array([nuova[1][a] - vecchia[1][a] for a in vecchia[1]])
    meglio = int((d > 0).sum())
    incertezza = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.inf
    passa = nuova[0] > vecchia[0] and meglio >= ANNI_MEGLIO * len(d) and d.mean() >= incertezza
    return bool(passa), float(nuova[0] - vecchia[0]), meglio, len(d)


def evolvi(t, genomi: dict, provate: list, settimana: str, dire=print) -> tuple[dict, list, str, np.ndarray]:
    """Ogni agente prova su se stesso una modifica mai provata; la squadra rifa' l'esame anno per
    anno; restano le modifiche che la migliorano (insieme, se insieme vanno ancora meglio).
    Restituisce i genomi nuovi, le prove (per la memoria), il racconto e la fiducia della
    squadra finale anno per anno (per l'esame sul conto)."""
    t0 = time.time()
    rng = np.random.default_rng(int.from_bytes(settimana.encode(), "little") % (2 ** 32))
    gia = {(x["agente"], x["da"], x["modifica"]) for x in provate}
    p_oggi = fiducia_anno_per_anno(t, genomi)
    oggi = resa(t, p_oggi)
    prove, righe, buone = [], [], []
    for a in AGENTI:
        nuove = [(testo, g) for testo, g in modifiche(a, genomi[a]) if (a, genomi[a].chiave(), testo) not in gia]
        if not nuove:
            continue
        testo, g = nuove[int(rng.integers(len(nuove)))]
        prova = dict(genomi)
        prova[a] = g
        p = fiducia_anno_per_anno(t, prova)
        passa, di_quanto, meglio, anni = _passa(resa(t, p), oggi)
        prove.append({"settimana": settimana, "agente": a, "da": genomi[a].chiave(), "modifica": testo,
                      "esito": "tenuta" if passa else "scartata", "di_quanto": di_quanto, "anni_meglio": meglio})
        righe.append((a, testo, passa, di_quanto, meglio, anni))
        if passa:
            buone.append((di_quanto, a, g, p))
        dire(f"  {a}: {testo} → {'tenuta' if passa else 'scartata'} ({di_quanto:+.4f} R, meglio in {meglio}/{anni} anni)")
    nuovi, p_finale = dict(genomi), p_oggi
    if buone:
        buone.sort(key=lambda x: -x[0])
        insieme = dict(genomi)
        for _, a, g, _ in buone:
            insieme[a] = g
        if len(buone) > 1:
            p_insieme = fiducia_anno_per_anno(t, insieme)
            if _passa(resa(t, p_insieme), oggi)[0]:
                nuovi, p_finale = insieme, p_insieme
            else:
                _, a, g, p_finale = buone[0]
                nuovi[a] = g
                righe = [(x[0], x[1], x[2] and x[0] == a, *x[3:]) for x in righe]
        else:
            _, a, g, p_finale = buone[0]
            nuovi[a] = g
    racconto = [f"🧬 I cervelli si sono messi alla prova (settimana {settimana.split('-S')[-1]})",
                "Ognuno ha provato a cambiare se stesso; resta solo quello che migliora la squadra nella maggior "
                "parte degli anni."]

    def r(x):
        return f"{x:+.3f}".replace(".", ",").replace("-", "−")
    for a, testo, passa, di_quanto, meglio, anni in righe:
        racconto.append(f"• {a} {testo}: " + (f"la squadra va meglio ({r(di_quanto)} volte il rischio a scommessa, "
                                              f"meglio in {meglio} anni su {anni}). La tiene."
                                              if passa else f"non migliora ({r(di_quanto)}, meglio in {meglio} anni su "
                                                            f"{anni}). Torna com'era."))
    if not righe:
        racconto.append("• Nessuno aveva modifiche nuove da provare.")
    dire(f"Evoluzione dei cervelli: {round(time.time() - t0)} s")
    return nuovi, prove, "\n".join(racconto), p_finale


def puntate_anno_per_anno(t, p: np.ndarray) -> np.ndarray:
    """Quanto punterebbe il cervello del Rischio su ogni operazione (`rischio_cervello.py`), allenato
    ogni anno sugli anni prima con la fiducia dei cervelli di quegli anni. Prima del primo anno
    d'esame, quando non ha ancora anni da cui imparare, vale la formula di prima (2p - 1)."""
    from nvm.cervello.rischio_cervello import CervelloRischio, vista_del_rischio
    f = np.clip(2 * np.nan_to_num(p) - 1, 0, None)
    valide = np.isfinite(p)
    x = vista_del_rischio(np.nan_to_num(p, nan=0.5), t.viste["Livelli"])
    for a in range(PRIMO_ESAME, ULTIMO_ESAME + 1):
        tr = np.flatnonzero(valide & (t.chiusa < _istante(a)))
        oggi = np.flatnonzero(valide & (t.anno == a))
        if len(tr) < 500 or not len(oggi):
            continue
        tr = tr[np.argsort(t.quando[tr], kind="stable")]
        cervello = CervelloRischio.allena(x[tr], t.erre[tr], pesi_per_eta(t.chiusa[tr], _istante(a)))
        f[oggi] = cervello.quanto(x[oggi])
    return f


def cervello_del_rischio(t, p: np.ndarray):
    """Il cervello del Rischio allenato su tutto, per il bot dal vivo."""
    from nvm.cervello.rischio_cervello import CervelloRischio, vista_del_rischio
    tr = np.flatnonzero(np.isfinite(p))
    tr = tr[np.argsort(t.quando[tr], kind="stable")]
    return CervelloRischio.allena(vista_del_rischio(p[tr], t.viste["Livelli"][tr]), t.erre[tr],
                                  pesi_per_eta(t.chiusa[tr], int(t.chiusa.max()) + 1))


def esame(t, kelly_capo: np.ndarray, entra_capo: np.ndarray, p: np.ndarray, dire=print,
          f: Optional[np.ndarray] = None) -> dict:
    """I cervelli contro il Capo di oggi, sul conto intero fuori campione. `kelly_capo` e
    `entra_capo`: le puntate e le scelte del Capo anno per anno (allenato sugli anni prima);
    `p` la fiducia dei cervelli, anno per anno; `f` quanto punterebbe il cervello del Rischio,
    anno per anno (`puntate_anno_per_anno`)."""
    t0 = time.time()
    anni = t.anno
    dal = anni >= PRIMO_ESAME - 2
    formula = _conto(_operazioni(t, dal & (p > SOGLIA), np.clip(2 * p - 1, 0, None)), PRIMO_ESAME, ULTIMO_ESAME)
    col_rischio = (_conto(_operazioni(t, dal & (p > SOGLIA), f), PRIMO_ESAME, ULTIMO_ESAME)
                   if f is not None else None)
    capo = _conto(_operazioni(t, dal & entra_capo, kelly_capo), PRIMO_ESAME, ULTIMO_ESAME)
    rischio_cervello = col_rischio is not None and col_rischio["crescita"] >= formula["crescita"]
    cervelli = col_rischio if rischio_cervello else formula
    dire(f"Esame dei cervelli ({PRIMO_ESAME}-{ULTIMO_ESAME}, conto intero fuori campione): cervelli "
         f"{formula['crescita']:+.1%} l'anno (calo {formula['calo']:.0%}) con la puntata a formula"
         + (f", {col_rischio['crescita']:+.1%} (calo {col_rischio['calo']:.0%}) col cervello del Rischio"
            if col_rischio is not None else "")
         + f"; Capo di oggi {capo['crescita']:+.1%} (calo {capo['calo']:.0%}). {round(time.time() - t0)} s")
    return {"cervelli": cervelli, "formula": formula, "col_rischio": col_rischio, "rischio_cervello": rischio_cervello,
            "capo": capo, "decidono": cervelli["crescita"] > capo["crescita"]
            and (portafoglio.CALO_MASSIMO is None or cervelli["calo"] <= portafoglio.CALO_MASSIMO + 0.05)}


def scegli_sfidanti(genomi: dict, provate: list, seme: int = 0) -> list[tuple[str, str, dict]]:
    """Per ogni agente una versione diversa di se', mai provata, da mettere alla prova dal vivo
    contro quella di adesso (`dal_vivo.py`): (agente, modifica, genomi della squadra sfidante)."""
    rng = np.random.default_rng(seme)
    gia = {(x["agente"], x["da"], x["modifica"]) for x in provate}
    fuori = []
    for a in AGENTI:
        nuove = [(testo, g) for testo, g in modifiche(a, genomi[a]) if (a, genomi[a].chiave(), testo) not in gia]
        if nuove:
            testo, g = nuove[int(rng.integers(len(nuove)))]
            fuori.append((a, testo, {**genomi, a: g}))
    return fuori


def per_il_vivo(t, kelly_capo: np.ndarray, entra_capo: np.ndarray, dire=print, genomi: Optional[dict] = None,
                p: Optional[np.ndarray] = None, sfidanti: Optional[list] = None) -> dict:
    """La squadra allenata su tutto, con l'esito dell'esame, per il bot dal vivo (`cervelli.json`).
    `p`: la fiducia anno per anno gia' calcolata con questi genomi (per non rifarla). `sfidanti`:
    le versioni diverse di se' che gli agenti mettono alla prova dal vivo (`scegli_sfidanti`)."""
    p = fiducia_anno_per_anno(t, genomi) if p is None else p
    f = puntate_anno_per_anno(t, p)
    risultato = esame(t, kelly_capo, entra_capo, p, dire, f)
    squadra = allena(t, int(t.chiusa.max()) + 1, genomi=genomi)
    # Il Rischio per le scelte dei cervelli: quanto punta il cervello del Rischio (se all'esame fa
    # crescere il conto almeno quanto la formula 2p - 1), con la dose e la puntata minima imparate
    # sul conto intero.
    dal = t.anno >= PRIMO_ESAME - 2
    puntate = f if risultato["rischio_cervello"] else np.clip(2 * p - 1, 0, None)
    s = portafoglio.scegli(_operazioni(t, dal & (p > SOGLIA), puntate), None)
    rischio = {"parte": s.parte, "minimo": s.minimo}
    if risultato["rischio_cervello"]:
        rischio["cervello"] = cervello_del_rischio(t, p).come_dati()
    dati = {"quando": int(time.time()), "squadra": squadra.come_dati(), "esame": risultato,
            "decidono": bool(risultato["decidono"]), "soglia": SOGLIA, "rischio": rischio}
    if t.piani is not None:
        dati["piani"] = allena_piani(t, int(t.chiusa.max()) + 1).come_dati()
    if sfidanti:
        dati["sfidanti"] = [{"agente": a, "modifica": testo, "genomi": genomi_come_dati(g),
                             "squadra": allena(t, int(t.chiusa.max()) + 1, genomi=g).come_dati()}
                            for a, testo, g in sfidanti]
    return dati


def ricordi(t, quanti: int = 2000):
    """I ricordi di scuola che il bot porta con se' per ripassare mentre impara dal vivo
    (`esperienza.py`): casi dei vent'anni, piu' spesso i recenti e quelli che pesano."""
    from nvm.cervello.esperienza import ricordi_di_scuola
    fino_a = int(t.chiusa.max()) + 1
    y, w = obiettivo(t.erre)
    return ricordi_di_scuola(t.viste, y, w * pesi_per_eta(t.chiusa, fino_a), quanti)


def vista_dei_piani(viste: dict) -> np.ndarray:
    """Cosa guarda Livelli per scegliere stop e obiettivi: quello che vede lui e i colleghi."""
    return np.hstack([np.atleast_2d(viste[a]) for a in AGENTI])


def allena_piani(t, fino_a: int) -> ReteValori:
    """Il cervello dei Livelli che stima quanto vale ogni piano (`piani.py`) nella situazione."""
    tr = np.flatnonzero(t.chiusa < fino_a)
    tr = tr[np.argsort(t.quando[tr], kind="stable")]
    return ReteValori.allena(vista_dei_piani({a: t.viste[a][tr] for a in AGENTI}), t.piani[tr],
                             pesi_per_eta(t.chiusa[tr], fino_a))
