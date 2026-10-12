"""Il passo 2 su Kaggle: il cervello impara dai risultati quanti R porta ogni setup, e l'esame lo confronta col bot.

- Gli occhi della notte prima (`occhi.pt`, scuole 1 e 2) guardano il grafico all'apertura della candela 3; la
  "scheda" del setup (`esperienza.SCHEDA`) dice cosa il bot sapeva all'ingresso. Una testa piccola stima il
  risultato in R e la probabilita' di chiudere in guadagno.
- Per confronto, lo stesso cervello **senza occhi** (solo la scheda): se gli occhi non battono la scheda, il grafico
  non sta aggiungendo niente.
- Anni come sempre: impara fino al 2019, sceglie la soglia sul 2020-2022, esame dal 2023 (mai visto).
- All'esame: il bot (A+), il bot di adesso (A+ e almeno 1:1,5), la rete su tutti i CRT, la rete sopra il bot (vota
  solo i setup che il bot di adesso prenderebbe). Per ognuno: quanti a settimana, R medio, R totale, anni in guadagno.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from kaggle_rete.esperienza import SCHEDA, STOP_MINIMO
from kaggle_rete.histdata import pezzi_buoni
from nvm.agenti.foto import RR_MINIMO, TF_CRT
from nvm.dati.ore import carica
from nvm.rete.finestre import TF_RETE, Storia, finestre
from nvm.rete.modello import Occhi
from nvm.tempo import TF, utc

CONTROLLO = utc(2020, 1, 1)
ESAME = utc(2023, 1, 1)
SETTIMANA = 7 * 86400
# Il timeframe della rete che guarda ogni timeframe del bot (le 6 ore stanno fra le 4 ore).
_DOVE = {TF.H1: TF.H1, TF.H4: TF.H4, TF.H6: TF.H4, TF.D1: TF.D1, TF.W1: TF.W1, TF.MN: TF.MN}
_LOG = [SCHEDA.index(n) for n in ("stop", "tp1", "target", "rr tp1", "rr target", "inside bar")]
A_PIU, RR = SCHEDA.index("A+"), SCHEDA.index("rr target")


def prepara_scheda(scheda: np.ndarray) -> np.ndarray:
    x = scheda.astype(np.float32).copy()
    x[:, _LOG] = np.log1p(np.maximum(x[:, _LOG], 0))
    return x


def tf_rete(scheda: np.ndarray) -> np.ndarray:
    quale = np.argmax(scheda[:, :len(TF_CRT)], axis=1)
    return np.array([TF_RETE.index(_DOVE[TF_CRT[k]]) for k in quale], np.int64)


class Trader(nn.Module):
    def __init__(self, occhi: Occhi | None, n_scheda: int, d: int = 128, abbandono: float = 0.1):
        super().__init__()
        self.occhi = occhi
        self.scheda = nn.Sequential(nn.Linear(n_scheda, d), nn.GELU(), nn.Linear(d, d))
        entra = d if occhi is None else d + 2 * occhi.fine.normalized_shape[0]
        self.testa = nn.Sequential(nn.LayerNorm(entra), nn.Linear(entra, d), nn.GELU(), nn.Dropout(abbandono),
                                   nn.Linear(d, 2))

    def forward(self, x, v, scheda, quale):
        h = [self.scheda(scheda)]
        if self.occhi is not None:
            r, c = self.occhi(x, v)
            h = [r, c[torch.arange(len(quale), device=c.device), quale, -1]] + h
        out = self.testa(torch.cat(h, dim=-1))
        return out[:, 0], out[:, 1]      # R stimato, logit di chiudere in guadagno


class Casi:
    """I casi preparati (`prepara_casi`), con le finestre del grafico all'apertura della candela 3."""

    def __init__(self, radice: Path, file_casi: Path, scrivi=print):
        f = np.load(file_casi)
        studio = f["scheda"][:, SCHEDA.index("stop")] > STOP_MINIMO
        strumenti, t_tutti = f["strumento"], f["t"]
        tenere = np.zeros(len(t_tutti), bool)
        scrivi(f"casi preparati {len(t_tutti)}, con lo stop troppo piccolo (tolti) {int((~studio).sum())}")
        xs = np.zeros((len(t_tutti), len(TF_RETE), 40, 7), np.float16)
        vs = np.ones((len(t_tutti), len(TF_RETE), 40), bool)
        for s in np.unique(strumenti):
            inizio = time.time()
            m, _ = carica(radice, str(s), utc(1999, 1, 1), utc(2100, 1, 1), solo_bid=True)
            pezzi, _ = pezzi_buoni(m)
            dove = np.flatnonzero((strumenti == s) & studio)
            for p in pezzi:
                dentro = dove[(t_tutti[dove] >= p.t[0]) & (t_tutti[dove] <= p.t[-1])]
                if not len(dentro):
                    continue
                st = Storia.da(p)
                for a in range(0, len(dentro), 8192):
                    k = dentro[a:a + 8192]
                    x, v = finestre(st, t_tutti[k])
                    xs[k], vs[k] = x.astype(np.float16), v
                tenere[dentro] = True
            scrivi(f"{s}: {int(tenere[dove].sum())} casi su {len(dove)} col grafico ({time.time() - inizio:.0f} s)")
        k = np.flatnonzero(tenere)
        self.strumento, self.t = strumenti[k], t_tutti[k]
        self.scheda_grezza = f["scheda"][k]
        self.scheda = prepara_scheda(self.scheda_grezza)
        self.quale = tf_rete(self.scheda_grezza)
        self.erre = f["erre"][k].astype(np.float32)
        self.x, self.v = xs[k], vs[k]

    def parte(self, dal: int, al: int) -> np.ndarray:
        return np.flatnonzero((self.t >= dal) & (self.t < al))


@torch.no_grad()
def stima(rete: Trader, cs: Casi, dev, indici: np.ndarray, lotto: int = 2048) -> np.ndarray:
    rete.eval()
    fuori = []
    for a in range(0, len(indici), lotto):
        i = indici[a:a + lotto]
        x = torch.from_numpy(cs.x[i]).to(dev).float()
        v = torch.from_numpy(cs.v[i]).to(dev)
        sc = torch.from_numpy(cs.scheda[i]).to(dev)
        q = torch.from_numpy(cs.quale[i]).to(dev)
        with torch.autocast(dev.type, enabled=dev.type == "cuda"):
            r, _ = rete(x, v, sc, q)
        fuori.append(r.float().cpu().numpy())
    rete.train()
    return np.concatenate(fuori) if fuori else np.zeros(0, np.float32)


def _meglio_del_10(previsto: np.ndarray, erre: np.ndarray) -> float:
    """Il controllo durante la scuola: l'R medio del 10% dei casi che la rete stima migliori."""
    if len(previsto) < 50:
        return float("nan")
    k = np.argsort(-previsto)[:max(len(previsto) // 10, 1)]
    return float(erre[k].mean())


def allena(cs: Casi, occhi: Occhi | None, minuti: float, dev, lotto: int = 512, lr: float = 1e-3,
           lr_occhi: float = 5e-5, seme: int = 1, scrivi=print):
    torch.manual_seed(seme)
    rng = np.random.default_rng(seme)
    rete = Trader(occhi, cs.scheda.shape[1]).to(dev)
    nuovi = [p for n, p in rete.named_parameters() if not n.startswith("occhi.")]
    gruppi = [{"params": nuovi, "lr": lr}]
    if occhi is not None:
        gruppi.append({"params": list(rete.occhi.parameters()), "lr": lr_occhi})
    ottimo = torch.optim.AdamW(gruppi, weight_decay=0.01)
    basi = [g["lr"] for g in ottimo.param_groups]
    scala = torch.amp.GradScaler(dev.type, enabled=dev.type == "cuda")
    impara, controlla = cs.parte(0, CONTROLLO), cs.parte(CONTROLLO, ESAME)
    erre_t = torch.from_numpy(np.clip(cs.erre, -2.0, 10.0))
    durata, partenza, ultimo, passi = 60 * minuti, time.time(), time.time(), 0
    migliore, storia = None, []
    while (f := (time.time() - partenza) / durata) < 1:
        for g, b in zip(ottimo.param_groups, basi):
            g["lr"] = b * min(1.0, f / 0.05) * 0.5 * (1 + math.cos(math.pi * f))
        i = rng.choice(impara, size=lotto)
        x = torch.from_numpy(cs.x[i]).to(dev).float()
        v = torch.from_numpy(cs.v[i]).to(dev)
        sc = torch.from_numpy(cs.scheda[i]).to(dev)
        q = torch.from_numpy(cs.quale[i]).to(dev)
        y = erre_t[i].to(dev)
        with torch.autocast(dev.type, enabled=dev.type == "cuda"):
            r, logit = rete(x, v, sc, q)
        perdita = nn.functional.smooth_l1_loss(r.float(), y) + \
            0.5 * nn.functional.binary_cross_entropy_with_logits(logit.float(), (y > 0).float())
        ottimo.zero_grad(set_to_none=True)
        scala.scale(perdita).backward()
        scala.unscale_(ottimo)
        nn.utils.clip_grad_norm_(rete.parameters(), 1.0)
        scala.step(ottimo)
        scala.update()
        passi += 1
        if time.time() - ultimo > 300 or passi == 100:
            ultimo = time.time()
            c = _meglio_del_10(stima(rete, cs, dev, controlla), cs.erre[controlla])
            storia.append({"passo": passi, "minuti": round((time.time() - partenza) / 60, 1),
                           "perdita": perdita.item(), "controllo": c})
            scrivi(f"{storia[-1]['minuti']:6.1f} min, passo {passi}: perdita {perdita.item():.3f}, "
                   f"R medio del 10% migliore al controllo {c:+.3f}")
            if migliore is None or c > migliore[0]:
                migliore = (c, {k: t.detach().clone() for k, t in rete.state_dict().items()})
    if migliore is not None:
        rete.load_state_dict(migliore[1])
    return rete, storia


def _riga(cs: Casi, sel: np.ndarray, dal: int, al: int) -> dict:
    e = cs.erre[sel]
    anni = cs.t[sel].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    per_anno = {int(a): float(e[anni == a].sum()) for a in np.unique(anni)}
    return {"casi": int(len(e)), "a settimana": len(e) / max((al - dal) / SETTIMANA, 1e-9),
            "R medio": float(e.mean()) if len(e) else float("nan"), "R totale": float(e.sum()),
            "vinti": float((e > 0).mean()) if len(e) else float("nan"),
            "anni in guadagno": f"{sum(v > 0 for v in per_anno.values())}/{len(per_anno)}", "per anno": per_anno}


def soglia(previsto: np.ndarray, erre: np.ndarray, minimo: int = 200) -> tuple[float, str]:
    """La soglia sul controllo: fra il 5, 10, 20, 30 e 50% migliore, quella con l'R medio piu' alto (almeno
    `minimo` casi)."""
    meglio = (-np.inf, np.inf, "")
    for quota in (0.05, 0.10, 0.20, 0.30, 0.50):
        n = int(len(previsto) * quota)
        if n < minimo:
            continue
        s = float(np.sort(previsto)[::-1][n - 1])
        r = float(erre[previsto >= s].mean())
        if r > meglio[0]:
            meglio = (r, s, f"il {quota:.0%} migliore")
    return meglio[1], meglio[2]


def esame(cs: Casi, previsto: np.ndarray, nome: str) -> dict:
    """Soglie scelte sul controllo, poi l'esame dal 2023 guardato una volta."""
    controlla, esame_ = cs.parte(CONTROLLO, ESAME), cs.parte(ESAME, 2 ** 62)
    a_piu = cs.scheda_grezza[:, A_PIU] > 0
    bot = a_piu & (cs.scheda_grezza[:, RR] >= RR_MINIMO - 1e-9)
    s_tutti, q_tutti = soglia(previsto[controlla], cs.erre[controlla])
    cb = controlla[bot[controlla]]
    s_bot, q_bot = soglia(previsto[cb], cs.erre[cb])
    fine = int(cs.t.max()) + 1
    fuori = {"soglie": {"rete su tutti i CRT": [s_tutti, q_tutti], "rete sopra il bot": [s_bot, q_bot]}}
    for parte, idx, dal, al in (("controllo", controlla, CONTROLLO, ESAME), ("esame", esame_, ESAME, fine)):
        fuori[parte] = {
            "tutti i CRT": _riga(cs, idx, dal, al),
            "il bot (A+)": _riga(cs, idx[a_piu[idx]], dal, al),
            "il bot di adesso (A+ e 1:1,5)": _riga(cs, idx[bot[idx]], dal, al),
            f"{nome} su tutti i CRT": _riga(cs, idx[previsto[idx] >= s_tutti], dal, al),
            f"{nome} sopra il bot": _riga(cs, idx[bot[idx] & (previsto[idx] >= s_bot)], dal, al),
        }
    return fuori


def stampa(r: dict, scrivi=print) -> None:
    for parte in ("controllo", "esame"):
        scrivi(f"\n{parte.upper()} ({'2020-2022' if parte == 'controllo' else 'dal 2023, mai visto'}):")
        for nome, x in r[parte].items():
            scrivi(f"  {nome:34s} {x['a settimana']:6.1f}/sett, R medio {x['R medio']:+.3f}, totale "
                   f"{x['R totale']:+8.1f} R, vinti {x['vinti']:.0%}, anni in guadagno {x['anni in guadagno']}")


def tutto(radice: Path, file_casi: Path, file_occhi: Path, uscita: Path, minuti: float = 90,
          minuti_scheda: float = 20, scrivi=print) -> dict:
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scrivi(f"scheda grafica: {torch.cuda.get_device_name(0) if dev.type == 'cuda' else 'NESSUNA'}")
    cs = Casi(radice, file_casi, scrivi)
    scrivi(f"casi: impara {len(cs.parte(0, CONTROLLO))}, controllo {len(cs.parte(CONTROLLO, ESAME))}, "
           f"esame {len(cs.parte(ESAME, 2 ** 62))}")
    resoconto = {}
    for nome, con_occhi, quanto in (("rete con gli occhi", True, minuti), ("rete senza occhi", False, minuti_scheda)):
        occhi = None
        if con_occhi:
            salvato = torch.load(file_occhi, map_location="cpu", weights_only=True)
            occhi = Occhi(**salvato["forma"])
            occhi.load_state_dict(salvato["pesi"])
        scrivi(f"\n--- {nome}: {quanto:g} minuti ---")
        rete, storia = allena(cs, occhi, quanto, dev, scrivi=scrivi)
        previsto = stima(rete, cs, dev, np.arange(len(cs.t)))
        r = esame(cs, previsto, nome)
        r["storia"] = storia
        stampa(r, scrivi)
        resoconto[nome] = r
        uscita.mkdir(parents=True, exist_ok=True)
        torch.save(rete.state_dict(), uscita / f"trader {nome}.pt")
        (uscita / "resoconto passo 2.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False),
                                                      encoding="utf-8")
    return resoconto
