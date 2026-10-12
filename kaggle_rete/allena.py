"""La scuola della rete (scuole 1 e 2) sulla scheda grafica di Kaggle, con lo storico di HistData.

Le stesse regole di `nvm/rete/scuola.py`: impara fino al 2019, si controlla sul 2020-2022, esame dal 2023 (anni che
non vede mai mentre impara). In piu':
- tutti gli strumenti e tutti gli anni che HistData ha (ogni strumento parte quando ha 40 mesi di storia);
- le finestre si preparano una volta sola e stanno sulla scheda grafica: ogni passo costa solo la rete;
- la rete e' piu' grande (piu' esempi lo permettono), il ritmo d'apprendimento scende col tempo;
- ogni tanto salva la rete migliore, cosi' se Kaggle si ferma il lavoro non si perde.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from kaggle_rete.histdata import pezzi_buoni
from nvm.dati.ore import carica
from nvm.rete.etichette import DOMANDE, etichette
from nvm.rete.finestre import Storia, finestre
from nvm.rete.modello import Occhi
from nvm.rete.scuola import NASCOSTE, pesi_classi
from nvm.tempo import utc

CONTROLLO = utc(2020, 1, 1)
ESAME = utc(2023, 1, 1)
MESI_PRIMA = 41          # la rete guarda 40 candele mensili: si parte quando ci sono


class Archivio:
    """Tutti gli istanti di tutti gli strumenti: finestre, risposte degli agenti, quando e di chi."""

    def __init__(self, radice: Path, strumenti: list[str], fine: int, scrivi=print):
        xs, vs, chi, tt = [], [], [], []
        ys = {nome: [] for nome, _ in DOMANDE}
        self.strumenti, self.conti = [], {}
        for s in strumenti:
            inizio = time.time()
            m, _ = carica(radice, s, utc(1999, 1, 1), fine, solo_bid=True)
            pezzi, nota = pezzi_buoni(m)
            if nota:
                scrivi(f"{s}: {nota}")
            if not pezzi:
                scrivi(f"{s}: troppo poco storico ({len(m)} ore), salto")
                continue
            for m in pezzi:
                st = Storia.da(m)
                primo = np.datetime64(int(m.t[0]), "s").astype("datetime64[M]") + MESI_PRIMA
                t = st.istanti(int(primo.astype("datetime64[s]").astype(np.int64)), fine)
                if not len(t):
                    continue
                e = etichette(m, t)
                for a in range(0, len(t), 8192):
                    x, v = finestre(st, t[a:a + 8192])
                    xs.append(x.astype(np.float16))
                    vs.append(v)
                nome = s if len(pezzi) == 1 else f"{s} dal {str(np.datetime64(int(m.t[0]), 's'))[:10]}"
                chi.append(np.full(len(t), len(self.strumenti), np.int16))
                self.strumenti.append(nome)
                tt.append(t)
                for k, _ in DOMANDE:
                    ys[k].append(e[k].astype(np.int64))
                self.conti[nome] = {"istanti": int(len(t)), "dal": str(np.datetime64(int(t[0]), "s"))[:10],
                                    "al": str(np.datetime64(int(t[-1]), "s"))[:10]}
                scrivi(f"{nome}: {len(t)} istanti dal {self.conti[nome]['dal']} al {self.conti[nome]['al']} "
                       f"({time.time() - inizio:.0f} s)")
        self.x = np.concatenate(xs)
        self.v = np.concatenate(vs)
        self.chi = np.concatenate(chi)
        self.t = np.concatenate(tt)
        self.y = {k: np.concatenate(v) for k, v in ys.items()}

    def parte(self, dal: int, al: int) -> np.ndarray:
        return np.flatnonzero((self.t >= dal) & (self.t < al))


@torch.no_grad()
def giudica(rete: Occhi, x, v, y: dict, indici: np.ndarray, lotto: int = 2048) -> dict:
    """Quante ne indovina per domanda, con la risposta piu' comune per confronto (come `scuola.giudica`)."""
    rete.eval()
    previsti = {nome: [] for nome, _ in DOMANDE}
    for a in range(0, len(indici), lotto):
        i = torch.as_tensor(indici[a:a + lotto], device=x.device)
        with torch.autocast(x.device.type, enabled=x.device.type == "cuda"):
            r, c = rete(x[i].float(), v[i])
            uscite = rete.rispondi(r, c)
        for (nome, _), l in zip(DOMANDE, uscite):
            previsti[nome].append(l.argmax(-1).cpu().numpy())
    rete.train()
    fuori = {}
    for nome, _ in DOMANDE:
        p, yy = np.concatenate(previsti[nome]), y[nome][indici]
        comune = np.bincount(yy, minlength=3).argmax()
        richiamo = [float((p[yy == c] == c).mean()) if (yy == c).any() else None for c in range(3)]
        precisione = [float((yy[p == c] == c).mean()) if (p == c).any() else None for c in range(3)]
        fuori[nome] = {"giuste": float((p == yy).mean()), "comune": float((yy == comune).mean()),
                       "media dei richiami": float(np.mean([r for r in richiamo if r is not None])),
                       "richiamo": richiamo, "precisione": precisione, "casi": int(len(yy))}
    return fuori


def allena(radice: Path, strumenti: list[str], uscita: Path, ore: float = 6.0, lotto: int = 512,
           d: int = 128, strati: int = 4, teste: int = 8, lr: float = 3e-4, seme: int = 1, scrivi=print) -> dict:
    torch.manual_seed(seme)
    rng = np.random.default_rng(seme)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scrivi(f"scheda: {torch.cuda.get_device_name(0) if dev.type == 'cuda' else 'NESSUNA (processore)'}")
    inizio = time.time()
    fine_dati = int(time.time()) // 3600 * 3600
    arch = Archivio(radice, strumenti, fine_dati, scrivi)
    impara, controlla, esame = arch.parte(0, CONTROLLO), arch.parte(CONTROLLO, ESAME), arch.parte(ESAME, 2 ** 62)
    scrivi(f"materiale pronto in {time.time() - inizio:.0f} s: impara {len(impara)}, controlla {len(controlla)}, "
           f"esame {len(esame)}")
    x = torch.from_numpy(arch.x).to(dev)
    v = torch.from_numpy(arch.v).to(dev)
    y = [torch.from_numpy(arch.y[nome]).to(dev) for nome, _ in DOMANDE]
    rete = Occhi(d=d, strati=strati, teste=teste).to(dev)
    scrivi(f"pesi della rete: {sum(p.numel() for p in rete.parameters())}")
    ottimo = torch.optim.AdamW(rete.parameters(), lr=lr, weight_decay=0.05)
    scala = torch.amp.GradScaler(dev.type, enabled=dev.type == "cuda")
    pesi = [pesi_classi(arch.y[nome][impara]).to(dev) for nome, _ in DOMANDE]
    campione = rng.choice(controlla, size=min(30000, len(controlla)), replace=False)
    impara_t = torch.from_numpy(impara).to(dev)
    g = torch.Generator(device=dev).manual_seed(seme)
    uscita.mkdir(parents=True, exist_ok=True)
    durata = 3600 * ore
    partenza = time.time()
    passi, migliore, storia, ultimo_controllo = 0, None, [], partenza
    while (trascorso := time.time() - partenza) < durata:
        f = trascorso / durata                       # ritmo: sale nei primi 3% poi scende a coseno
        for gr in ottimo.param_groups:
            gr["lr"] = lr * min(1.0, f / 0.03) * 0.5 * (1 + math.cos(math.pi * f))
        i = impara_t[torch.randint(len(impara_t), (lotto,), device=dev, generator=g)]
        xb, vb = x[i].float(), v[i]
        piene = ~vb
        nascoste = (torch.rand(vb.shape, device=dev, generator=g) < NASCOSTE) & piene
        with torch.autocast(dev.type, enabled=dev.type == "cuda"):
            r, c = rete(xb, vb, nascoste)
            ric = rete.ricostruisci(c)
            logit = rete.rispondi(r, c)
        p1 = nn.functional.mse_loss(ric.float()[nascoste], xb[..., :4][nascoste])
        p2 = sum(nn.functional.cross_entropy(l.float(), t[i], weight=w) for l, t, w in zip(logit, y, pesi)) / len(logit)
        ottimo.zero_grad(set_to_none=True)
        scala.scale(p1 + p2).backward()
        scala.unscale_(ottimo)
        nn.utils.clip_grad_norm_(rete.parameters(), 1.0)
        scala.step(ottimo)
        scala.update()
        passi += 1
        if time.time() - ultimo_controllo > 600 or passi == 200:
            ultimo_controllo = time.time()
            cc = giudica(rete, x, v, arch.y, campione)
            media = float(np.mean([q["media dei richiami"] for q in cc.values()]))
            storia.append({"passo": passi, "minuti": round((time.time() - partenza) / 60, 1),
                           "scuola 1": p1.item(), "scuola 2": p2.item(), "controllo": media})
            scrivi(f"{storia[-1]['minuti']:6.1f} min, passo {passi}: scuola 1 {p1.item():.3f}, "
                   f"scuola 2 {p2.item():.3f}, controllo {media:.3f}")
            if migliore is None or media > migliore[0]:
                migliore = (media, {k: t.detach().clone() for k, t in rete.state_dict().items()})
                torch.save({"pesi": migliore[1], "forma": {"d": d, "strati": strati, "teste": teste}},
                           uscita / "occhi.pt")
    if migliore is not None:
        rete.load_state_dict(migliore[1])
    torch.save({"pesi": rete.state_dict(), "forma": {"d": d, "strati": strati, "teste": teste}}, uscita / "occhi.pt")
    resoconto = {"strumenti": arch.conti, "passi": passi, "ore": ore, "lotto": lotto,
                 "forma": {"d": d, "strati": strati, "teste": teste}, "storia": storia,
                 "controllo": giudica(rete, x, v, arch.y, controlla), "esame": giudica(rete, x, v, arch.y, esame)}
    (uscita / "resoconto.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False), encoding="utf-8")
    return resoconto


def stampa(resoconto: dict, scrivi=print) -> None:
    scrivi(f"\nESAME (dal 2023, anni mai visti), {resoconto['passi']} passi:")
    for nome, r in resoconto["esame"].items():
        prec = ", ".join("—" if p is None else f"{p:.0%}" for p in r["precisione"][1:])
        scrivi(f"  {nome:14s} giuste {r['giuste']:.1%} (sempre la risposta piu' comune {r['comune']:.1%}), "
               f"media richiami {r['media dei richiami']:.1%}, precisione classi 1/2: {prec}")
