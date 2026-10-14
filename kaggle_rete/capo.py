"""La scuola del Capo di Nameless (fase 3), su Kaggle con la scheda grafica.

    from kaggle_rete.capo import scuola
    scuola()

Input del notebook: il codice, i dati (fase 0) e l'output della scuola delle zone (fase 2: `zone_nameless.pt` e
`materie/`). Se le materie non ci sono si ricalcolano; se mancano le zone il Capo guarda solo gli occhi (lo dice).

1. **Gli esiti** (`nvm/nameless/esiti.py`): ogni setup in cui il bot entra, come lo gestisce il bot, coi costi (e coi
   costi doppi), su tutti i mercati, col processore.
2. **La vista**: occhi e zone a ogni setup, all'ultima ora della candela 2 (scheda grafica, pochi minuti).
3. **La scuola**: impara sugli anni fino al 2019 (solo operazioni gia' chiuse prima del 2020), si sceglie sul
   2020-2022 (chiuse prima del 2023). Il Capo mette i setup in classifica (quanti R si aspetta); per ogni seme si tiene
   l'epoca che sul controllo avrebbe guadagnato di piu', e sul controllo si sceglie anche quanti prenderne in cima
   alla classifica (`migliore_soglia`). Il voto finale e' la media dei semi (`Capo.insieme`). L'esame non si guarda
   mai per scegliere.
4. **L'esame** dal 2023 (anni mai visti), coi costi: i setup scelti guadagnano piu' di zero con sicurezza (la media
   resta sopra zero nel 97,5% delle ricampionature per settimane: le operazioni della stessa settimana si muovono
   insieme) e piu' di prenderli tutti. Si dice anche coi costi doppi, per timeframe e per famiglia.

Nell'output: `capo_nameless.pt`, `esame_capo.json`, `operazioni.npz` (ogni setup con il suo esito e il voto).
"""

from __future__ import annotations

import glob
import json
import os
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import torch
from torch import nn

from kaggle_rete.dati import CRYPTO
from kaggle_rete.histdata import NOMI
from kaggle_rete.occhi import CONTROLLO, ESAME, carica_sensi, famiglia, trova_dati
from kaggle_rete.zone import calcola_materie
from nvm.nameless import capo as C
from nvm.nameless import esiti as E
from nvm.nameless import materie as M
from nvm.nameless.lettore_mappa import LettoreMappa
from nvm.nameless.mappa import tavole
from nvm.nameless.occhi import Lettore, Occhi
from nvm.nameless.sensi import TF_NAMELESS
from nvm.nameless.zone import Zone

SEMI = 5
SETTIMANA = 7 * 86400
RICAMPIONATURE = 2000


def carica_materie(pezzi: list, processi: int | None, scrivi) -> dict:
    """Le materie della fase 2 (output del notebook delle zone); quelle che mancano si calcolano."""
    trovate = {Path(p).stem.replace("_", " "): p for p in glob.glob("/kaggle/input/**/materie/*.npz", recursive=True)}
    materie, mancano = {}, []
    for nome, ore in pezzi:
        if nome in trovate:
            materie[nome] = M.Materie.carica(trovate[nome], ore.strumento)
        else:
            mancano.append((nome, ore))
    scrivi(f"materie della fase 2: {len(materie)} pezzi; da calcolare: {len(mancano)}")
    if mancano:
        materie.update(calcola_materie(mancano, processi, scrivi))
    return materie


def _tavole_pezzo(argomenti):
    nome, ore = argomenti
    return nome, tavole(ore)


def calcola_mappe(pezzi: list, processi: int | None, scrivi) -> dict:
    """Le tavole della mappa (fase 2b), per le zone che la ricevono."""
    with Pool(processi or os.cpu_count() or 1) as pool:
        mappe = dict(pool.imap_unordered(_tavole_pezzo, pezzi))
    scrivi(f"mappe: {len(mappe)} pezzi")
    return mappe


def _esiti_pezzo(argomenti):
    nome, ore, m = argomenti
    return nome, E.esiti(ore, m)


def calcola_esiti(pezzi: list, materie: dict, processi: int | None, scrivi) -> dict:
    fuori = {}
    lavori = [(nome, ore, materie[nome]) for nome, ore in pezzi if nome in materie]
    with Pool(processi or os.cpu_count() or 1) as pool:
        for nome, e in pool.imap_unordered(_esiti_pezzo, lavori):
            fuori[nome] = e
            r = e["erre"][e["finita"]]
            scrivi(f"esiti {nome}: {len(r)} operazioni, media {r.mean() if len(r) else 0:+.3f} R")
    return fuori


class Operazioni:
    """Tutti i setup in cui il bot entra, in fila: l'ora della domanda, il timeframe, l'esito, il setup."""

    def __init__(self, sensi, materie: dict, esiti: dict, conti: dict, scrivi=print):
        valide = np.zeros(sensi.ore(), bool)
        valide[sensi.istanti(0, 2 ** 62)] = True
        fine_pezzo = np.r_[sensi.primo[1:, 0], sensi.ore()]
        colonne = {c: [] for c in ("j", "tf", "erre", "erre_doppi", "n3", "chiusa", "finita", "pezzo", "uscita")}
        caratteristiche, scarti = [], 0
        for p, nome in enumerate(sensi.nomi):
            if nome not in esiti:
                continue
            e, m = esiti[nome], materie[nome]
            a, b = int(sensi.primo[p, 0]), int(fine_pezzo[p])
            for i, tf in enumerate(M.TF_CRT):
                sel = np.flatnonzero(e["tf"] == i)
                if not len(sel):
                    continue
                righe = e["riga"][sel]
                crt = m.crt[tf]
                j = a + crt["ora"][righe]
                k = TF_NAMELESS.index(tf)
                dentro = (j >= a) & (j < b)
                jj = np.where(dentro, j, a)
                ok = dentro & valide[jj] & (sensi.entro[k][jj] == sensi.primo[p, k] + crt["k2"][righe])
                scarti += int((~ok).sum())
                sel, righe, j = sel[ok], righe[ok], j[ok]
                colonne["j"].append(j)
                colonne["tf"].append(np.full(len(j), i, np.int8))
                for c in ("erre", "erre_doppi", "chiusa", "finita", "uscita"):
                    colonne[c].append(e[c][sel])
                colonne["n3"].append(crt["n3"][righe])
                colonne["pezzo"].append(np.full(len(j), p, np.int32))
                caratteristiche.append(C.setup(crt, righe, i, e["spread"][sel], E.SPREAD_RANGE))
        for c, v in colonne.items():
            setattr(self, c, np.concatenate(v) if v else np.zeros(0))
        self.setup = np.concatenate(caratteristiche) if caratteristiche else np.zeros((0, len(C.SETUP)), np.float32)
        self.famiglia = np.array([conti[sensi.nomi[p]]["famiglia"] for p in self.pezzo]) if len(self.pezzo) else \
            np.zeros(0, str)
        self.scarti = scarti
        scrivi(f"operazioni: {len(self.j)} (scartate {scarti} che non tornano coi sensi)")

    def parte(self, nome: str) -> np.ndarray:
        if nome == "impara":
            return np.flatnonzero((self.n3 < CONTROLLO) & (self.chiusa < CONTROLLO) & self.finita)
        if nome == "controllo":
            return np.flatnonzero((self.n3 >= CONTROLLO) & (self.n3 < ESAME) & (self.chiusa < ESAME) & self.finita)
        return np.flatnonzero((self.n3 >= ESAME) & self.finita)


def _zone(dove: str, scrivi) -> Zone:
    trovati = sorted(glob.glob("/kaggle/input/**/zone_nameless.pt", recursive=True))
    if trovati:
        salvato = torch.load(trovati[0], map_location=dove, weights_only=False)
        zone = Zone(Occhi(**salvato["occhi"]))
        zone.load_state_dict(salvato["pesi"])
        scrivi(f"zone della fase 2 da {trovati[0]} ({salvato.get('passi', '?')} passi; esame passato: "
               f"{salvato.get('passa', '?')})")
        return zone
    occhi = sorted(glob.glob("/kaggle/input/**/occhi_nameless.pt", recursive=True))
    if not occhi:
        raise FileNotFoundError("mancano le zone (fase 2) e gli occhi (fase 1): aggiungi il notebook delle zone")
    salvato = torch.load(occhi[0], map_location=dove, weights_only=False)
    o = Occhi(**salvato["misura"])
    o.load_state_dict(salvato["pesi"])
    scrivi("ATTENZIONE: mancano le zone (fase 2): il Capo guarda solo gli occhi, le risposte delle zone sono a caso")
    return Zone(o)


def bilancio(erre: np.ndarray, settimane: np.ndarray, rng: np.random.Generator) -> dict:
    """Quante operazioni, la media in R, il totale, e la media nel 2,5% peggiore delle ricampionature per settimane."""
    if not len(erre):
        return {"operazioni": 0, "media": None, "totale": 0.0, "sicura": None}
    uniche, quale = np.unique(settimane, return_inverse=True)
    somma = np.bincount(quale, weights=erre, minlength=len(uniche))
    quante = np.bincount(quale, minlength=len(uniche)).astype(np.float64)
    medie = []
    for _ in range(RICAMPIONATURE):
        s = rng.integers(len(uniche), size=len(uniche))
        medie.append(somma[s].sum() / max(quante[s].sum(), 1))
    return {"operazioni": int(len(erre)), "media": float(erre.mean()), "totale": float(erre.sum()),
            "vinte": float((erre > 0).mean()), "sicura": float(np.quantile(medie, 0.025))}


QUOTE = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0)
MINIMO_PRESI = 50


def migliore_soglia(voto: np.ndarray, erre: np.ndarray) -> dict:
    """Quanti setup prendere in cima alla classifica del Capo: la quota (di `QUOTE`) che sul controllo avrebbe
    guadagnato di piu', con almeno `MINIMO_PRESI` operazioni. La soglia e' il voto da cui si prende (un numero: vale
    uguale sugli anni dell'esame, che non si guardano). Se nemmeno la migliore guadagna, non si prende niente."""
    migliore = {"quota": 0.0, "soglia": float("inf"), "totale": 0.0, "media": None, "presi": 0}
    for q in QUOTE:
        soglia = float(np.quantile(voto, 1 - q)) if q < 1 else -float("inf")
        presi = voto >= soglia
        if presi.sum() < MINIMO_PRESI:
            continue
        totale = float(erre[presi].sum())
        if totale > migliore["totale"]:
            migliore = {"quota": q, "soglia": soglia, "totale": totale, "media": float(erre[presi].mean()),
                        "presi": int(presi.sum())}
    return migliore


def _allena_un_capo(x, y, xc, yc, seme: int, dove: str, epoche: int, scrivi) -> tuple[C.Capo, dict]:
    torch.manual_seed(seme)
    capo = C.Capo(x.shape[1]).to(dove)
    ottimo = torch.optim.AdamW(capo.parameters(), lr=1e-3, weight_decay=1e-3)
    bersaglio = y.clamp(-3.0, 10.0)
    migliore, stato = None, None
    g = torch.Generator(device="cpu").manual_seed(seme)
    yc_np = yc.cpu().numpy()
    for epoca in range(epoche):
        capo.train()
        ordine = torch.randperm(len(x), generator=g)
        for a in range(0, len(x), 4096):
            i = ordine[a:a + 4096].to(dove)
            errore = nn.functional.huber_loss(capo(x[i]), bersaglio[i], delta=1.0)
            ottimo.zero_grad(set_to_none=True)
            errore.backward()
            ottimo.step()
        capo.eval()
        with torch.no_grad():
            voto = capo(xc).cpu().numpy()
        m = migliore_soglia(voto, yc_np)
        if migliore is None or m["totale"] > migliore["totale"]:
            migliore = {"epoca": epoca + 1, **m}
            stato = {k: v.detach().clone() for k, v in capo.state_dict().items()}
    capo.load_state_dict(stato)
    scrivi(f"capo {seme}: migliore all'epoca {migliore['epoca']}: al controllo, prendendo il "
           f"{migliore['quota']:.0%} piu' alto, {migliore['presi']} setup, {migliore['totale']:+.0f} R")
    return capo, migliore


def scuola(radice: Path | None = None, uscita: Path = Path("/kaggle/working"), solo: list[str] | None = None,
           epoche: int = 30, semi: int = SEMI, processi: int | None = None, zone: Zone | None = None,
           scrivi=None) -> dict:
    scrivi = scrivi or (lambda t: print(t, flush=True))
    inizio = time.time()
    rng = np.random.default_rng(7)
    radice = radice or trova_dati()
    nomi = [n for n in list(NOMI) + list(CRYPTO) if solo is None or n in solo]
    sensi, conti, pezzi = carica_sensi(radice, nomi, scrivi)
    materie = carica_materie(pezzi, processi, scrivi)
    esiti = calcola_esiti(pezzi, materie, processi, scrivi)
    # Le zone si caricano sul processore: le mappe si fanno coi processi paralleli prima di accendere la scheda.
    zone = zone if zone is not None else _zone("cpu", scrivi)
    mappe = calcola_mappe(pezzi, processi, scrivi) if hasattr(zone.occhi, "mappa_entrata") else None
    del pezzi
    dove = "cuda" if torch.cuda.is_available() else "cpu"
    zone = zone.to(dove)
    op = Operazioni(sensi, materie, esiti, conti, scrivi)
    lettore = Lettore(sensi, dove)
    mappa = LettoreMappa(sensi, mappe, lettore) if mappe else None
    t0 = time.time()
    x = np.concatenate([C.vista(zone, lettore, op.j, op.tf, mappa=mappa), op.setup], 1).astype(np.float32)
    scrivi(f"vista di {len(x)} setup in {time.time() - t0:.0f} s ({x.shape[1]} numeri per setup)")
    parti = {n: op.parte(n) for n in ("impara", "controllo", "esame")}
    scrivi("setup: " + ", ".join(f"{n} {len(v)}" for n, v in parti.items()))
    t = lambda a: torch.as_tensor(a, device=dove)
    xi, yi = t(x[parti["impara"]]), t(op.erre[parti["impara"]].astype(np.float32))
    xc, yc = t(x[parti["controllo"]]), t(op.erre[parti["controllo"]].astype(np.float32))
    capi, scelte = [], []
    for s in range(semi):
        c, info = _allena_un_capo(xi, yi, xc, yc, s, dove, epoche, scrivi)
        capi.append(c)
        scelte.append(info)
    voto = np.concatenate([C.Capo.insieme(capi, t(x[a:a + 65536])).cpu().numpy() for a in range(0, len(x), 65536)])
    soglia = migliore_soglia(voto[parti["controllo"]], op.erre[parti["controllo"]])
    scrivi(f"il Capo prende i setup col voto da {soglia['soglia']:+.3f} in su: al controllo il {soglia['quota']:.0%} "
           f"piu' alto, {soglia['presi']} setup, {soglia['totale']:+.0f} R")
    presi = voto >= soglia["soglia"]
    settimane = op.n3 // SETTIMANA
    esame = {}
    for nome, idx in parti.items():
        tutti = bilancio(op.erre[idx], settimane[idx], rng)
        scelti = bilancio(op.erre[idx][presi[idx]], settimane[idx][presi[idx]], rng)
        doppi = bilancio(op.erre_doppi[idx][presi[idx]], settimane[idx][presi[idx]], rng)
        esame[nome] = {"prenderli tutti": tutti, "scelti dal Capo": scelti, "scelti, costi doppi": doppi}
    e = parti["esame"]
    per_tf = {tf.value: {"tutti": bilancio(op.erre[e][op.tf[e] == i], settimane[e][op.tf[e] == i], rng),
                         "scelti": bilancio(op.erre[e][(op.tf[e] == i) & presi[e]],
                                            settimane[e][(op.tf[e] == i) & presi[e]], rng)}
              for i, tf in enumerate(M.TF_CRT)}
    per_famiglia = {f: {"tutti": bilancio(op.erre[e][op.famiglia[e] == f], settimane[e][op.famiglia[e] == f], rng),
                        "scelti": bilancio(op.erre[e][(op.famiglia[e] == f) & presi[e]],
                                           settimane[e][(op.famiglia[e] == f) & presi[e]], rng)}
                    for f in sorted(set(op.famiglia[e].tolist()))}
    s, tt = esame["esame"]["scelti dal Capo"], esame["esame"]["prenderli tutti"]
    passa = bool(s["operazioni"] and s["sicura"] is not None and s["sicura"] > 0 and s["media"] > (tt["media"] or 0))
    resoconto = {"passa": passa, "esame": esame, "per timeframe (dal 2023)": per_tf,
                 "per famiglia (dal 2023)": per_famiglia, "capi": scelte, "soglia": soglia, "costi": {
                     "spread": f"{E.SPREAD_RANGE:.0%} del range medio giornaliero", "commissione": "conto raw"},
                 "minuti": round((time.time() - inizio) / 60), "scarti": op.scarti}
    uscita.mkdir(parents=True, exist_ok=True)
    torch.save({"capi": [c.state_dict() for c in capi], "entrate": x.shape[1], "setup": list(C.SETUP),
                "passa": passa}, uscita / "capo_nameless.pt")
    np.savez_compressed(uscita / "operazioni.npz", j=op.j, tf=op.tf, erre=op.erre, erre_doppi=op.erre_doppi,
                        n3=op.n3, chiusa=op.chiusa, finita=op.finita, pezzo=op.pezzo, uscita=op.uscita, voto=voto,
                        nomi=np.array(sensi.nomi))
    (uscita / "esame_capo.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False), encoding="utf-8")
    stampa(resoconto, scrivi)
    return resoconto


def _riga(b: dict) -> str:
    if not b["operazioni"]:
        return "nessuna operazione"
    return (f"{b['operazioni']} operazioni, media {b['media']:+.3f} R (sicura {b['sicura']:+.3f}), "
            f"vinte {b['vinte']:.0%}, totale {b['totale']:+.0f} R")


def stampa(resoconto: dict, scrivi=print) -> None:
    scrivi(f"\nESAME DEL CAPO (dal 2023, anni mai visti, coi costi), {resoconto['minuti']} minuti")
    nomi = {"impara": "fino al 2019 (imparati)", "controllo": "2020-2022 (scelta del Capo)",
            "esame": "dal 2023 (esame)"}
    for parte, x in resoconto["esame"].items():
        scrivi(f"  {nomi[parte]}:")
        for chi, b in x.items():
            scrivi(f"    {chi}: {_riga(b)}")
    scrivi("  dal 2023 per timeframe (scelti / tutti):")
    for tf, x in resoconto["per timeframe (dal 2023)"].items():
        scrivi(f"    {tf:>3}: {_riga(x['scelti'])} | tutti: {_riga(x['tutti'])}")
    scrivi("  dal 2023 per famiglia (scelti / tutti):")
    for f, x in resoconto["per famiglia (dal 2023)"].items():
        scrivi(f"    {f}: {_riga(x['scelti'])} | tutti: {_riga(x['tutti'])}")
    scrivi("  'sicura': la media nel 2,5% peggiore delle ricampionature per settimane; deve stare sopra zero.")
    scrivi("PASSATO: i setup scelti dal Capo guadagnano dal 2023, con sicurezza, e piu' di prenderli tutti." if
           resoconto["passa"] else
           "NON PASSATO: dal 2023 i setup scelti dal Capo non guadagnano con sicurezza (o non piu' di prenderli "
           "tutti).")
