"""La scuola delle zone di Nameless (fase 2), su Kaggle con la scheda grafica.

    from kaggle_rete.zone import scuola
    scuola(ore=3)

Input del notebook: il codice, i dati (fase 0) e l'output della scuola degli occhi (fase 1, `occhi_nameless.pt`): la
rete parte dagli occhi gia' allenati (se non ci sono, parte da zero e lo dice).

1. **Le materie** (`nvm/nameless/materie.py`): le risposte delle regole delle foto su tutti i pezzi di mercato, col
   processore, tutti i processori insieme (una decina di minuti). Si salvano nell'output (`materie/`): serviranno al
   Capo (fase 3).
2. **La scuola**: impara fino al 2019, si controlla sul 2020-2022. Meta' degli esempi all'ultima ora della candela 2 di
   un timeframe dei CRT (le domande sui CRT), meta' a ore qualunque (le domande sulle candele). Le risposte rare pesano
   di piu'.
3. **L'esame** dal 2023 (anni mai visti): per ogni materia e timeframe la media dei richiami (per ogni risposta delle
   regole, quante volte la rete dice la stessa: cosi' rispondere sempre "niente" non basta) almeno il 98%, dove ci sono
   almeno `MINIMO_ESAME` casi; e la rete rifa' le 24 foto del proprietario (`materie.FOTO`).

Nell'output: `zone_nameless.pt` (la rete), `esame_zone.json`, `materie/`.
"""

from __future__ import annotations

import glob
import json
import math
import os
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import torch
from torch import nn

from kaggle_rete.dati import CRYPTO
from kaggle_rete.histdata import NOMI
from kaggle_rete.occhi import CONTROLLO, ESAME, carica_sensi, trova_dati
from nvm.nameless import materie as M
from nvm.nameless.lettore_mappa import LettoreMappa
from nvm.nameless.mappa import tavole
from nvm.nameless.occhi import Lettore, Occhi
from nvm.nameless.sensi import TF_NAMELESS, Sensi
from nvm.nameless.zone import USCITE_CANDELA, USCITE_CRT, Zone, parte

SOGLIA = 0.98
MINIMO_ESAME = 200
DOMANDE_CRT = ("crt", "key level", "entra", "direzione", "target")
DOMANDE_CANDELA = ("direzione", "accetta")
# La direzione CRT e' binaria; quella delle candele ha tre classi (ribassista, neutra, rialzista).
CLASSI_CRT = {"crt": 3, "key level": 3, "entra": 3, "direzione": 2, "target": 3}
CLASSI_CANDELA = {"direzione": 3, "accetta": 3}


def _materie_pezzo(argomenti):
    nome, ore, con_mappa = argomenti if len(argomenti) == 3 else (*argomenti, False)
    inizio = time.time()
    return nome, M.Materie.da(ore), (tavole(ore) if con_mappa else None), time.time() - inizio


def calcola_materie(pezzi: list, processi: int | None = None, scrivi=print, con_mappa: bool = False):
    """Le materie di ogni pezzo, in parallelo sui processori (prima di accendere la scheda grafica). Con `con_mappa`
    anche le tavole della mappa (fase 2b): (materie, tavole)."""
    fuori, mappe = {}, {}
    with Pool(processi or os.cpu_count() or 1) as pool:
        for nome, m, t, secondi in pool.imap_unordered(_materie_pezzo, [(n, o, con_mappa) for n, o in pezzi]):
            fuori[nome] = m
            if t is not None:
                mappe[nome] = t
            conti = ", ".join(f"{tf.value} {int(m.crt[tf]['entra'].sum())}" for tf in M.TF_CRT)
            scrivi(f"materie {nome}: si entra {conti} ({secondi:.0f} s)")
    return (fuori, mappe) if con_mappa else fuori


class Etichette:
    """Le risposte delle regole messe in fila con le ore dei sensi.

    - `crt[d]` [ore, len(TF_CRT)] per ogni domanda di `DOMANDE_CRT` (-1 dove non si chiede: non e' l'ultima ora di una
      candela del timeframe, o il CRT non ha il key level per direzione e target) e `rr` (nan dove non c'e');
    - `confini[i]`: le ore in cui chiude una candela del timeframe `TF_CRT[i]` (le domande sui CRT);
    - per le candele, una fila per timeframe di `TF_CANDELA` nell'ordine delle candele dei sensi (`candela`)."""

    def __init__(self, sensi: Sensi, materie: dict, scrivi=print):
        n = sensi.ore()
        k_crt = [TF_NAMELESS.index(tf) for tf in M.TF_CRT]
        self.crt = {d: np.full((n, len(k_crt)), -1, np.int8) for d in DOMANDE_CRT}
        self.rr = np.full((n, len(k_crt)), np.nan, np.float32)
        confine = np.zeros((n, len(k_crt)), bool)
        self.scarti = {"crt": 0, "candele": 0}
        fine_pezzo = np.r_[sensi.primo[1:, 0], n]
        for p, nome in enumerate(sensi.nomi):
            a, b = int(sensi.primo[p, 0]), int(fine_pezzo[p])
            for i, k in enumerate(k_crt):
                e = sensi.entro[k][a:b]
                confine[a + 1:b, i] = (e[1:] > e[:-1]) & (e[1:] >= sensi.primo[p, k])
            m = materie.get(nome)
            if m is None:
                continue
            for i, (tf, k) in enumerate(zip(M.TF_CRT, k_crt)):
                r = m.crt[tf]
                j = a + r["ora"]
                dentro = (r["ora"] >= 0) & (j < b)
                j_ok = np.where(dentro, j, a)
                ok = dentro & confine[j_ok, i] & (sensi.entro[k][j_ok] == sensi.primo[p, k] + r["k2"])
                self.scarti["crt"] += int((~ok).sum())
                j, r = j[ok], {c: v[ok] for c, v in r.items()}
                verso = r["verso"].astype(np.int8)
                self.crt["crt"][j, i] = verso
                self.crt["key level"][j, i] = np.where(r["kl"], verso, 0)
                self.crt["entra"][j, i] = np.where(r["entra"], verso, 0)
                self.crt["direzione"][j, i] = r["direzione"]
                self.crt["target"][j, i] = r["tipo"]
                self.rr[j, i] = r["rr"]
        for d in ("crt", "key level", "entra"):
            self.crt[d][confine & (self.crt[d] < 0)] = 0
        self.confini = [np.flatnonzero(confine[:, i]) for i in range(len(k_crt))]
        # Le candele: direzione, accettazione e l'ora (dei sensi) in cui il suo estremo e' preso.
        self.candela = {}
        for tf in M.TF_CANDELA:
            k = TF_NAMELESS.index(tf)
            quante = len(sensi.fine[k])
            dirc, acc, preso = np.ones(quante, np.int8), np.zeros(quante, np.int8), np.full(quante, M.MAI, np.int64)
            buone = np.zeros(quante, bool)
            for p, nome in enumerate(sensi.nomi):
                m = materie.get(nome)
                if m is None:
                    continue
                c = m.candele[tf]
                a = int(sensi.primo[p, k])
                lung = min(len(c["fine"]), (int(sensi.primo[p + 1, k]) if p + 1 < len(sensi.nomi) else quante) - a)
                uguali = c["fine"][:lung] == sensi.fine[k][a:a + lung]
                self.scarti["candele"] += int((~uguali).sum())
                idx = a + np.flatnonzero(uguali)
                sel = np.flatnonzero(uguali)
                dirc[idx], acc[idx] = c["direzione"][sel], c["accetta"][sel]
                preso[idx] = np.where(c["preso"][sel] == M.MAI, M.MAI, c["preso"][sel] + int(sensi.primo[p, 0]))
                buone[idx] = True
            self.candela[tf] = (dirc, acc, preso, buone)
        scrivi(f"etichette: {sum(len(c) for c in self.confini)} ore con una domanda sui CRT; scartati "
               f"{self.scarti['crt']} CRT e {self.scarti['candele']} candele che non tornano coi sensi")

    def candele(self, sensi: Sensi, j: np.ndarray) -> dict[str, np.ndarray]:
        """Le risposte sulle candele alle ore `j` [B]: {domanda: [B, len(TF_CANDELA)]}, -1 dove non c'e' la candela."""
        d = np.full((len(j), len(M.TF_CANDELA)), -1, np.int8)
        a = np.full((len(j), len(M.TF_CANDELA)), -1, np.int8)
        for i, tf in enumerate(M.TF_CANDELA):
            dirc, acc, preso, buone = self.candela[tf]
            k = TF_NAMELESS.index(tf)
            c = sensi.entro[k][j]
            ok = (c >= sensi.primo[sensi.chi[j], k]) & buone[np.maximum(c, 0)]
            cc = np.maximum(c, 0)
            d[:, i] = np.where(ok, dirc[cc], -1)
            a[:, i] = np.where(ok, np.where(preso[cc] > j, acc[cc], 0), -1)
        return {"direzione": d, "accetta": a}


def pesi_classi(y: np.ndarray, classi: int) -> torch.Tensor:
    """Le risposte rare pesano quanto le comuni (l'inverso della frequenza, al massimo 50 volte): l'esame e' la media
    dei richiami, e un "no" che capita il 3% delle volte deve contare quanto i "si'". Nella fase 2 erano smussate (la
    radice) e la rete diceva quasi sempre "si'" sulla direzione."""
    conti = np.bincount(y[y >= 0].astype(np.int64), minlength=classi).astype(np.float64) + 1.0
    w = np.minimum(conti.sum() / (classi * conti), 50.0)
    return torch.tensor(w / w.mean(), dtype=torch.float32)


def _campione_stratificato(candidati: np.ndarray, etichette: dict[str, np.ndarray], quanti: int,
                           rng: np.random.Generator) -> np.ndarray:
    """Seleziona esempi per ogni classe di ogni risposta, distribuendo quanti esempi circa tra gli strati."""
    gruppi = []
    for valori in etichette.values():
        valori = np.asarray(valori)
        if valori.ndim == 1:
            valori = valori[:, None]
        for i in range(valori.shape[1]):
            for classe in np.unique(valori[:, i]):
                if classe < 0:
                    continue
                indici = np.flatnonzero(valori[:, i] == classe)
                if len(indici):
                    gruppi.append(indici)
    if not gruppi:
        return np.sort(rng.choice(candidati, size=min(quanti, len(candidati)), replace=False))
    quota = max(1, math.ceil(quanti / len(gruppi)))
    scelti = [rng.choice(i, size=quota, replace=False) if len(i) > quota else i for i in gruppi]
    return np.sort(np.unique(candidati[np.concatenate(scelti)]))


def metriche(previsti: np.ndarray, veri: np.ndarray, classi: int, disponibili: np.ndarray | None = None) -> dict:
    """Quante ne indovina; il richiamo è calcolato sul campione stratificato per materia e classe."""
    ok = veri >= 0
    p, y = previsti[ok], veri[ok]
    richiamo = [float((p[y == c] == c).mean()) if (y == c).sum() >= 10 else None for c in range(classi)]
    precisione = [float((y[p == c] == c).mean()) if (p == c).sum() >= 10 else None for c in range(classi)]
    usati = [r for r in richiamo if r is not None]
    risultato = {"casi": int(len(y)), "giuste": float((p == y).mean()) if len(y) else None,
                 "media dei richiami": float(np.mean(usati)) if usati else None, "richiamo": richiamo,
                 "precisione": precisione, "per classe": np.bincount(y.astype(np.int64), minlength=classi).tolist(),
                 "campionamento": "stratificato per materia e classe"}
    if disponibili is not None:
        disponibili = disponibili[disponibili >= 0].astype(np.int64)
        risultato["casi disponibili per classe"] = np.bincount(disponibili, minlength=classi).tolist()
    return risultato


class Scuola:
    def __init__(self, sensi: Sensi, et: Etichette, dove: str, mappe: dict | None = None):
        self.sensi, self.et, self.dove = sensi, et, dove
        self.lettore = Lettore(sensi, dove)
        self.mappa = LettoreMappa(sensi, mappe, self.lettore) if mappe else None
        tutte = np.zeros(sensi.ore(), bool)
        tutte[sensi.istanti(0, 2 ** 62)] = True
        self.valide = tutte
        f = sensi.fine[0]
        self.parti = {"impara": (0, CONTROLLO), "controllo": (CONTROLLO, ESAME), "esame": (ESAME, 2 ** 62)}
        self.confini = {n: [c[tutte[c] & (f[c] >= a) & (f[c] < b)] for c in et.confini]
                        for n, (a, b) in self.parti.items()}
        self.ore = {n: np.flatnonzero(tutte & (f >= a) & (f < b)) for n, (a, b) in self.parti.items()}
        # Le ore dei CRT col key level: le sole con la direzione e il target.
        self.con_kl = {n: [c[et.crt["direzione"][c, i] >= 0] for i, c in enumerate(cc)]
                       for n, cc in self.confini.items()}

    def lotto(self, j: np.ndarray):
        """(gli ingressi della rete, come argomenti; le risposte dei CRT; gli R; le risposte delle candele)."""
        jt = torch.as_tensor(j, device=self.dove)
        contenuto, tempo, vuote, _ = self.lettore.guarda(jt, jt)
        ingressi = {"contenuto": contenuto, "tempo": tempo, "vuote": vuote}
        if self.mappa is not None:
            rif, scala = self.lettore.scala(jt)
            ingressi["mappa"] = self.mappa.leggi(jt, rif, scala)
        y_crt = {d: self.et.crt[d][j] for d in DOMANDE_CRT}
        y_can = self.et.candele(self.sensi, j)
        return ingressi, y_crt, self.et.rr[j], y_can

    def esempi(self, rng: np.random.Generator, parte: str, quanti: int) -> np.ndarray:
        """Il 40% all'ultima ora della candela 2 di un timeframe dei CRT (a caso fra i timeframe), il 25% su CRT col
        key level (le domande sulla direzione e sul target), il resto a ore qualunque (le candele)."""
        def da(liste, n):
            tf = rng.integers(len(liste), size=n)
            return [liste[i][rng.integers(len(liste[i]))] if len(liste[i]) else
                    self.ore[parte][rng.integers(len(self.ore[parte]))] for i in tf]
        a, b = int(quanti * 0.4), int(quanti * 0.25)
        return np.r_[np.array(da(self.confini[parte], a) + da(self.con_kl[parte], b), np.int64),
                     self.ore[parte][rng.integers(len(self.ore[parte]), size=quanti - a - b)]]


def perdita(crt, candela, y_crt, rr, y_can, pesi, dove) -> torch.Tensor:
    totale, quante = 0.0, 0
    for d in DOMANDE_CRT:
        y = torch.as_tensor(y_crt[d], device=dove).long()
        for i in range(y.shape[1]):
            ok = y[:, i] >= 0
            if ok.any():
                totale = totale + nn.functional.cross_entropy(parte(crt[:, i], d, USCITE_CRT)[ok].float(), y[ok, i],
                                                              weight=pesi["crt"][d][i])
                quante += 1
    r = torch.as_tensor(rr, device=dove)
    ok = torch.isfinite(r)
    if ok.any():
        totale = totale + nn.functional.smooth_l1_loss(parte(crt, "rr", USCITE_CRT)[..., 0][ok].float(),
                                                       torch.log1p(r[ok].clamp(min=0)))
        quante += 1
    for d in DOMANDE_CANDELA:
        y = torch.as_tensor(y_can[d], device=dove).long()
        for i in range(y.shape[1]):
            ok = y[:, i] >= 0
            if ok.any():
                totale = totale + nn.functional.cross_entropy(parte(candela[:, i], d, USCITE_CANDELA)[ok].float(),
                                                              y[ok, i], weight=pesi["candela"][d][i])
                quante += 1
    return totale / max(quante, 1)


@torch.no_grad()
def previsioni(rete: Zone, scuola: Scuola, j: np.ndarray, lotto: int = 512) -> tuple[dict, dict, np.ndarray]:
    """Le risposte della rete alle ore `j`: ({domanda: [N, tf]} per i CRT, lo stesso per le candele, rr [N, tf])."""
    rete.eval()
    p_crt = {d: [] for d in DOMANDE_CRT}
    p_can = {d: [] for d in DOMANDE_CANDELA}
    p_rr = []
    for a in range(0, len(j), lotto):
        ingressi, *_ = scuola.lotto(j[a:a + lotto])
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=scuola.dove == "cuda"):
            crt, candela = rete(**ingressi)
        for d in DOMANDE_CRT:
            p_crt[d].append(parte(crt, d, USCITE_CRT).argmax(-1).cpu().numpy())
        for d in DOMANDE_CANDELA:
            p_can[d].append(parte(candela, d, USCITE_CANDELA).argmax(-1).cpu().numpy())
        p_rr.append(torch.expm1(parte(crt, "rr", USCITE_CRT)[..., 0].float()).cpu().numpy())
    rete.train()
    return ({d: np.concatenate(v) for d, v in p_crt.items()}, {d: np.concatenate(v) for d, v in p_can.items()},
            np.concatenate(p_rr))


def misura(rete: Zone, scuola: Scuola, parte_: str, quanti: int, seme: int = 7) -> dict:
    """Le materie su una parte degli anni: campione stratificato tra risposte e classi per dare supporto alle rare."""
    rng = np.random.default_rng(seme)
    fuori = {}
    campione_desc = "stratificato per materia e classe"
    for i, tf in enumerate(M.TF_CRT):
        c = scuola.confini[parte_][i]
        if not len(c):
            continue
        disponibili = {d: scuola.et.crt[d][c, i] for d in DOMANDE_CRT}
        j = _campione_stratificato(c, disponibili, quanti, rng)
        p_crt, _, p_rr = previsioni(rete, scuola, j)
        for d in DOMANDE_CRT:
            y_completi = disponibili[d]
            fuori[f"{d} {tf.value}"] = metriche(p_crt[d][:, i], scuola.et.crt[d][j, i],
                                                 CLASSI_CRT[d], y_completi)
        rr = scuola.et.rr[j, i]
        ok = np.isfinite(rr)
        if ok.any():
            fuori[f"rr {tf.value}"] = {"casi": int(ok.sum()),
                                       "errore mediano in R": float(np.median(np.abs(p_rr[ok, i] - rr[ok]))),
                                       "campionamento": campione_desc}
    ore = scuola.ore[parte_]
    y_tutte = scuola.et.candele(scuola.sensi, ore)
    supporti = {d: [y_tutte[d][:, i].copy() for i in range(len(M.TF_CANDELA))] for d in DOMANDE_CANDELA}
    j = _campione_stratificato(ore, y_tutte, quanti, rng)
    del y_tutte
    _, p_can, _ = previsioni(rete, scuola, j)
    y = scuola.et.candele(scuola.sensi, j)
    for i, tf in enumerate(M.TF_CANDELA):
        for d in DOMANDE_CANDELA:
            fuori[f"candela {d} {tf.value}"] = metriche(p_can[d][:, i], y[d][:, i],
                                                         CLASSI_CANDELA[d], supporti[d][i])
    return fuori


def voti(m: dict) -> tuple[float, float]:
    """(la media, la piu' bassa) delle medie dei richiami delle materie con abbastanza casi. L'esame richiede che
    passino tutte: durante la scuola si sceglie prima la peggiore, poi la media complessiva."""
    r = [x["media dei richiami"] for x in m.values() if x.get("media dei richiami") is not None and
         x["casi"] >= MINIMO_ESAME]
    return (float(np.mean(r)), float(min(r))) if r else (0.0, 0.0)


def foto_rete(rete: Zone, scuola: Scuola, materie: dict) -> list[dict]:
    """Le 24 foto: le regole e la rete, alla stessa ora (l'ultima della candela 2)."""
    sensi = scuola.sensi
    fuori = []
    fine_pezzo = np.r_[sensi.primo[1:, 0], sensi.ore()]
    for nome, strumento, tf, quando, verso, deve, target in M.FOTO:
        n3 = M.istante_foto(quando)
        pezzo = next((p for p, x in enumerate(sensi.nomi) if x.split(" ")[0] == strumento and
                      sensi.prossimo[sensi.primo[p, 0]] <= n3 <= sensi.prossimo[fine_pezzo[p] - 1]), None)
        if pezzo is None:
            fuori.append({"foto": nome, "regole": False, "rete": False, "nota": f"mancano i dati di {strumento}"})
            continue
        a = int(sensi.primo[pezzo, 0])
        crt = materie[sensi.nomi[pezzo]].crt[tf]
        i = M.crt_della_foto(crt, tf, quando, verso)
        j = a + int(crt["ora"][i]) if i is not None else \
            a + int(np.searchsorted(sensi.prossimo[a:fine_pezzo[pezzo]], n3, side="left"))
        p_crt, _, _ = previsioni(rete, scuola, np.array([j]))
        v = M.CORTO if verso == "S" else M.LUNGO
        detto = int(p_crt["entra"][0, M.TF_CRT.index(tf)])
        rete_entra = detto == v
        regole = M.foto_giusta(crt, i, deve, target)
        fuori.append({"foto": nome, "regole": bool(regole), "rete": bool(rete_entra == deve),
                      "nota": f"{'entra' if rete_entra else 'lascia'} (le regole: {'entra' if deve else 'lascia'})"})
    return fuori


def _occhi_della_fase_1(dove: str, scrivi, con_mappa: bool = False) -> Occhi:
    trovati = sorted(glob.glob("/kaggle/input/**/occhi_nameless.pt", recursive=True))
    if not trovati:
        scrivi("ATTENZIONE: non trovo gli occhi della fase 1 (occhi_nameless.pt): la rete parte da zero")
        return Occhi(con_mappa=con_mappa)
    salvato = torch.load(trovati[0], map_location=dove, weights_only=False)
    misura = {k: v for k, v in salvato["misura"].items() if k != "con_mappa"}
    occhi = Occhi(**misura, con_mappa=con_mappa)
    occhi.load_state_dict(salvato["pesi"], strict=not con_mappa)
    scrivi(f"occhi della fase 1 da {trovati[0]} ({salvato.get('passi', '?')} passi; esame passato: "
           f"{salvato.get('passa', '?')})")
    return occhi


def _rete_di_partenza(dove: str, scrivi, con_mappa: bool) -> Zone:
    """Con la mappa (fase 2b) si parte dalle zone della fase 2, se ci sono fra gli input: si aggiungono solo i pesi
    della mappa. Se no dagli occhi della fase 1."""
    trovati = sorted(glob.glob("/kaggle/input/**/zone_nameless.pt", recursive=True)) if con_mappa else []
    if trovati:
        salvato = torch.load(trovati[0], map_location=dove, weights_only=False)
        misura = {k: v for k, v in salvato["occhi"].items() if k != "con_mappa"}
        rete = Zone(Occhi(**misura, con_mappa=True))
        mancano = rete.load_state_dict(salvato["pesi"], strict=False).missing_keys
        scrivi(f"zone della fase 2 da {trovati[0]} ({salvato.get('passi', '?')} passi); pesi nuovi per la mappa: "
               f"{', '.join(mancano) or 'nessuno'}")
        return rete
    return Zone(_occhi_della_fase_1(dove, scrivi, con_mappa))


def scuola(ore: float = 3.0, radice: Path | None = None, uscita: Path = Path("/kaggle/working"),
           solo: list[str] | None = None, lotto: int = 256, seme: int = 1, campione: int = 20000,
           ogni_minuti: float = 15, processi: int | None = None, occhi: Occhi | None = None, mappa: bool = False,
           scrivi=None) -> dict:
    scrivi = scrivi or (lambda t: print(t, flush=True))
    inizio = time.time()
    rng = np.random.default_rng(seme)
    radice = radice or trova_dati()
    nomi = [n for n in list(NOMI) + list(CRYPTO) if solo is None or n in solo]
    scrivi(f"carico i dati di {len(nomi)} mercati e preparo le candele...")
    sensi, conti, pezzi = carica_sensi(radice, nomi, scrivi)
    if mappa:
        scrivi(f"preparo etichette e mappa per {len(pezzi)} pezzi di mercato...")
        materie, mappe = calcola_materie(pezzi, processi, scrivi, con_mappa=True)
    else:
        materie, mappe = calcola_materie(pezzi, processi, scrivi), None
    del pezzi
    (uscita / "materie").mkdir(parents=True, exist_ok=True)
    for nome, m in materie.items():
        m.salva(uscita / "materie" / f"{nome.replace(' ', '_')}.npz")
    et = Etichette(sensi, materie, scrivi)
    dove = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seme)
    sc = Scuola(sensi, et, dove, mappe)
    scrivi("domande sui CRT per imparare: " + ", ".join(f"{tf.value} {len(c)}" for tf, c in
                                                        zip(M.TF_CRT, sc.confini["impara"])))
    rete = (Zone(occhi) if occhi is not None else _rete_di_partenza(dove, scrivi, mappa)).to(dove)
    scrivi(f"pesi della rete: {sum(p.numel() for p in rete.parameters())} ({dove})")
    # I pesi delle risposte, dalle ore per imparare.
    pesi = {"crt": {d: [pesi_classi(et.crt[d][sc.confini['impara'][i], i], CLASSI_CRT[d]).to(dove)
                        for i in range(len(M.TF_CRT))] for d in DOMANDE_CRT}}
    campione_ore = sc.ore["impara"][rng.integers(len(sc.ore["impara"]), size=min(200000, len(sc.ore["impara"])))]
    y_can = et.candele(sensi, campione_ore)
    pesi["candela"] = {d: [pesi_classi(y_can[d][:, i], CLASSI_CANDELA[d]).to(dove) for i in range(len(M.TF_CANDELA))]
                       for d in DOMANDE_CANDELA}
    gruppi = [{"params": rete.occhi.parameters(), "lr": 1e-4},
              {"params": [p for n, p in rete.named_parameters() if not n.startswith("occhi.")], "lr": 1e-3}]
    ottimo = torch.optim.AdamW(gruppi, weight_decay=0.01)
    base = [g["lr"] for g in ottimo.param_groups]
    scala = torch.amp.GradScaler("cuda", enabled=dove == "cuda")
    fine = time.time() + 3600 * ore
    partenza, passi, migliore, storia, ultimo = time.time(), 0, None, [], time.time()
    while time.time() < fine:
        quota = (time.time() - partenza) / max(fine - partenza, 1e-9)
        for g, b in zip(ottimo.param_groups, base):
            g["lr"] = b * min(1.0, (passi + 1) / 300) * (0.05 + 0.475 * (1 + math.cos(math.pi * quota)))
        ingressi, y_crt, rr, y_c = sc.lotto(sc.esempi(rng, "impara", lotto))
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dove == "cuda"):
            crt, candela = rete(**ingressi)
        errore = perdita(crt, candela, y_crt, rr, y_c, pesi, dove)
        ottimo.zero_grad(set_to_none=True)
        scala.scale(errore).backward()
        scala.unscale_(ottimo)
        nn.utils.clip_grad_norm_(rete.parameters(), 1.0)
        scala.step(ottimo)
        scala.update()
        passi += 1
        if time.time() - ultimo > 60 * ogni_minuti or time.time() >= fine:
            ultimo = time.time()
            c = misura(rete, sc, "controllo", 3000)
            v, minimo = voti(c)
            peggiore = min((k for k, x in c.items() if x.get("media dei richiami") is not None and
                            x["casi"] >= MINIMO_ESAME), key=lambda k: c[k]["media dei richiami"], default="-")
            storia.append({"passo": passi, "minuti": round((time.time() - inizio) / 60),
                           "errore": float(errore.detach()), "controllo": v, "peggiore": peggiore,
                           "la peggiore": minimo})
            scrivi(f"passo {passi}: errore {float(errore.detach()):.3f}; al controllo le materie in media al {v:.1%}, "
                   f"la peggiore ({peggiore}) al {minimo:.1%}")
            if migliore is None or (minimo, v) > (migliore[0], migliore[1]):
                stato = {k: t.detach().clone() for k, t in rete.state_dict().items()}
                migliore = (minimo, v, passi, stato)
                torch.save({"pesi": stato, "occhi": rete.occhi.misura, "passi": passi,
                            "controllo": {"media": v, "peggiore": minimo}},
                           uscita / "zone_nameless.pt")
    if migliore is not None:
        rete.load_state_dict(migliore[3])
    esame = misura(rete, sc, "esame", campione)
    foto = foto_rete(rete, sc, materie)
    contano = {k: x for k, x in esame.items() if x.get("media dei richiami") is not None and x["casi"] >= MINIMO_ESAME}
    passa = all(x["media dei richiami"] >= SOGLIA for x in contano.values()) and all(f["rete"] for f in foto)
    passo_migliore = migliore[2] if migliore is not None else passi
    controllo_migliore = ({"media": migliore[1], "peggiore": migliore[0]} if migliore is not None else None)
    resoconto = {"passa": passa, "esame": esame, "foto": foto, "passi": passi, "miglior_passo": passo_migliore,
                 "controllo_migliore": controllo_migliore, "ore": ore,
                 "minuti": round((time.time() - inizio) / 60), "storia": storia, "scarti": et.scarti,
                 "mercati": conti}
    torch.save({"pesi": rete.state_dict(), "occhi": rete.occhi.misura, "passi": passo_migliore,
                "passi_totali": passi, "passa": passa, "esame": esame,
                "controllo": controllo_migliore}, uscita / "zone_nameless.pt")
    (uscita / "esame_zone.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False), encoding="utf-8")
    stampa(resoconto, scrivi)
    return resoconto


def stampa(resoconto: dict, scrivi=print) -> None:
    scrivi(f"\nESAME DELLE ZONE (dal 2023, anni mai visti), {resoconto['passi']} passi in {resoconto['minuti']} "
           "minuti")
    scrivi(f"  per ogni materia: la media dei richiami (deve essere almeno {SOGLIA:.0%})")
    for nome, x in resoconto["esame"].items():
        if "media dei richiami" not in x:
            scrivi(f"    {nome:>22}: sbaglia di {x['errore mediano in R']:.2f} R a meta' dei casi ({x['casi']} casi)")
            continue
        m = x["media dei richiami"]
        if m is None:
            continue
        segno = "ok" if m >= SOGLIA else "NO"
        nota = "" if x["casi"] >= MINIMO_ESAME else " (pochi casi, non conta)"
        scrivi(f"    {nome:>22}: {segno} {m:.1%} ({x['casi']} casi){nota}")
    giuste = sum(f["rete"] for f in resoconto["foto"])
    regole = sum(f["regole"] for f in resoconto["foto"])
    scrivi(f"  le foto: la rete ne rifa' {giuste} su {len(resoconto['foto'])} (le regole {regole})")
    for f in resoconto["foto"]:
        if not f["rete"]:
            scrivi(f"    {f['foto']}: {f['nota']}")
    scrivi("PASSATO: le zone rispondono come le regole delle foto." if resoconto["passa"] else
           "NON PASSATO: dove c'e' NO (o una foto sbagliata) la rete non risponde ancora come le regole.")
