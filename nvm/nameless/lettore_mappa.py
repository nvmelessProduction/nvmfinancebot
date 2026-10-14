"""La mappa sulla scheda grafica (fase 2b): dalle tavole di ogni pezzo (`mappa.tavole`) i gettoni di un gruppo di ore.

Come gli occhi con le candele (`occhi.Lettore`): le tavole di tutti i pezzi stanno in fila sulla scheda grafica e a
ogni gruppo di ore si legge quello che vale in quel momento. I prezzi sono in scala come le candele (stesso
riferimento e stessa scala, `Lettore.scala`). Per ogni elemento (`mappa.ELEMENTI`) sei numeri (`mappa.CAMPI`):

- key level: il livello, da quanto e' preso (log delle ore, /8), se e' preso, 0, 0, se c'e';
- accettazione: il livello, da quanto e' preso, se ha accettato su, se giu', se e' preso, se c'e';
- gap intatto (muro o target): il bordo che il prezzo incontra, l'altro bordo, 0, 0, 0, se c'e';
- gap toccato e non riempito: il bordo, l'estremo dell'aggressione (dalla reazione automatica), se e' nella reazione
  automatica o oltre, se e' nella liquidazione, 0, se c'e'.
"""

from __future__ import annotations

import numpy as np
import torch

from nvm.nameless.mappa import CAMPI, ELEMENTI, MAI, TF_ACCETTA, TF_GAP, TF_KL
from nvm.nameless.occhi import Lettore
from nvm.nameless.sensi import TF_NAMELESS, Sensi
from nvm.agenti.foto import GAP_INDIETRO


def _allinea(sensi: Sensi, tavole: dict, chiave: str, tf, campi: dict) -> dict[str, np.ndarray]:
    """Le colonne per candela di tutti i pezzi, nell'ordine delle candele dei sensi (`campi`: nome -> (valore se
    manca, se e' un'ora da spostare))."""
    k = TF_NAMELESS.index(tf)
    quante = len(sensi.fine[k])
    fuori = {n: np.full(quante, v, np.float64 if isinstance(v, float) else np.int64) for n, (v, _) in campi.items()}
    for p, nome in enumerate(sensi.nomi):
        t = tavole.get(nome)
        if t is None:
            continue
        t = t[chiave]
        a = int(sensi.primo[p, k])
        b = int(sensi.primo[p + 1, k]) if p + 1 < len(sensi.nomi) else quante
        lung = min(len(t["fine"]), b - a)
        uguali = np.flatnonzero(t["fine"][:lung] == sensi.fine[k][a:a + lung])
        for n, (_, ora) in campi.items():
            v = t[n][uguali]
            if ora:
                v = np.where(v == MAI, MAI, v + int(sensi.primo[p, 0]))
            fuori[n][a + uguali] = v
    return fuori


class LettoreMappa:
    def __init__(self, sensi: Sensi, tavole: dict, lettore: Lettore):
        self.lettore = lettore
        dove = lettore.dove
        t = lambda a: torch.as_tensor(a, device=dove)
        self.kl = {}
        for tf in TF_KL:
            c = _allinea(sensi, tavole, f"kl {tf.value}", tf, {"preso alto": (MAI, True), "preso basso": (MAI, True)})
            self.kl[tf] = {n: t(v) for n, v in c.items()}
        self.acc = {}
        for tf in TF_ACCETTA:
            c = _allinea(sensi, tavole, f"accettazione {tf.value}", tf,
                         {"verso": (0, False), "livello": (0.0, False), "preso": (MAI, True)})
            self.acc[tf] = {"verso": t(c["verso"]), "livello": t(c["livello"].astype(np.float32)),
                            "preso": t(c["preso"])}
        self.gap = {}
        for tf in TF_GAP:
            colonne = {n: [] for n in ("nato", "scade", "tocco", "pieno", "reazione", "liquidazione", "pezzo",
                                       "rialzista", "accetta", "basso", "alto", "estremo")}
            for p, nome in enumerate(sensi.nomi):
                g = tavole.get(nome, {}).get(f"gap {tf.value}")
                if g is None or not len(g["nato"]):
                    continue
                buoni = g["nato"] != MAI
                off = int(sensi.primo[p, 0])
                for n in ("nato", "scade", "tocco", "pieno", "reazione", "liquidazione"):
                    v = g[n][buoni]
                    colonne[n].append(np.where(v == MAI, MAI, v + off))
                for n in ("rialzista", "accetta", "basso", "alto", "estremo"):
                    colonne[n].append(g[n][buoni])
                colonne["pezzo"].append(np.full(int(buoni.sum()), p, np.int64))
            unite = {n: (np.concatenate(v) if v else np.zeros(0)) for n, v in colonne.items()}
            self.gap[tf] = {n: t(v.astype(np.float32) if n in ("basso", "alto", "estremo") else v)
                            for n, v in unite.items()}

    def leggi(self, j: torch.Tensor, rif: torch.Tensor, scala: torch.Tensor) -> torch.Tensor:
        """La mappa alle ore `j` [B]: [B, len(ELEMENTI), CAMPI] float32."""
        let = self.lettore
        p = let.chi[j]
        rel = lambda x: torch.asinh((x - rif[:, None]) / scala[:, None]) if x.dim() == 2 else \
            torch.asinh((x - rif) / scala)
        eta = lambda preso: torch.where(preso <= j, torch.log1p((j - preso).clamp(min=0).float()) / 8,
                                        torch.zeros((), device=j.device))
        pezzi = []
        for tf in TF_KL:
            k = TF_NAMELESS.index(tf)
            c = let.entro[k][j]
            c_ok = c >= let.primo[p, k]
            cc = c.clamp(min=0)
            for lato, colonna, prezzo in (("alto", "preso alto", 1), ("basso", "preso basso", 2)):
                preso = self.kl[tf][colonna][cc]
                livello = let.prezzi[k][cc, prezzo]
                v = torch.stack([rel(livello), eta(preso), (preso <= j).float(), torch.zeros_like(livello),
                                 torch.zeros_like(livello), c_ok.float()], -1)
                pezzi.append(torch.where(c_ok[:, None], v, torch.zeros_like(v)))
        for tf in TF_ACCETTA:
            k = TF_NAMELESS.index(tf)
            c = let.entro[k][j]
            cc = c.clamp(min=0)
            a = self.acc[tf]
            verso = a["verso"][cc]
            c_ok = (c >= let.primo[p, k]) & (verso != 0)
            preso = a["preso"][cc]
            v = torch.stack([rel(a["livello"][cc]), eta(preso), (verso > 0).float(), (verso < 0).float(),
                             (preso <= j).float(), c_ok.float()], -1)
            pezzi.append(torch.where(c_ok[:, None], v, torch.zeros_like(v)))
        for tf in TF_GAP:
            g = self.gap[tf]
            w = GAP_INDIETRO.get(tf, 100)
            if not len(g["nato"]):
                pezzi.extend([torch.zeros(len(j), CAMPI, device=j.device)] * 6)
                continue
            hi = torch.searchsorted(g["nato"], j, right=True)
            idx = hi[:, None] - w + torch.arange(w, device=j.device)
            ii = idx.clamp(min=0)
            jj = j[:, None]
            dentro = (idx >= 0) & (g["pezzo"][ii] == p[:, None]) & (g["scade"][ii] > jj) & (g["nato"][ii] <= jj)
            rialz = g["rialzista"][ii]
            intatto = dentro & (g["tocco"][ii] > jj)
            toccato = dentro & (g["tocco"][ii] <= jj) & (g["pieno"][ii] > jj)
            accetta = g["accetta"][ii]
            basso, alto = g["basso"][ii], g["alto"][ii]
            bordo = torch.where(rialz, alto, basso)
            altro = torch.where(rialz, basso, alto)
            distanza = (bordo - rif[:, None]).abs()
            for maschera, tipo in ((intatto & rialz & accetta, "intatto"), (intatto & rialz & ~accetta, "intatto"),
                                   (intatto & ~rialz & accetta, "intatto"), (intatto & ~rialz & ~accetta, "intatto"),
                                   (toccato & rialz, "toccato"), (toccato & ~rialz, "toccato")):
                d = torch.where(maschera, distanza, torch.full_like(distanza, float("inf")))
                scelto = d.argmin(1)
                c_ok = maschera.any(1)
                r = torch.arange(len(j), device=j.device)
                b0 = rel(bordo[r, scelto])
                if tipo == "intatto":
                    zero = torch.zeros_like(b0)
                    v = torch.stack([b0, rel(altro[r, scelto]), zero, zero, zero, c_ok.float()], -1)
                else:
                    reaz = g["reazione"][ii][r, scelto] <= j
                    liq = g["liquidazione"][ii][r, scelto] <= j
                    estremo = torch.where(reaz, rel(g["estremo"][ii][r, scelto]), torch.zeros_like(b0))
                    v = torch.stack([b0, torch.nan_to_num(estremo), reaz.float(), liq.float(), torch.zeros_like(b0),
                                     c_ok.float()], -1)
                pezzi.append(torch.where(c_ok[:, None], v, torch.zeros_like(v)))
        return torch.stack(pezzi, 1)
