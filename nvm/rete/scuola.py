"""La scuola della rete (scuole 1 e 2) e l'esame sugli anni che non ha mai visto.

    python -m nvm.rete.scuola --minuti 30

- **Impara** sugli anni fino al 2019, **si controlla** sul 2020-2022, l'**esame** e' dal 2023 in poi: quegli anni la
  rete non li vede mai mentre impara.
- Scuola 1: a ogni passo si nasconde il 15% delle candele e la rete le deve indovinare.
- Scuola 2: le domande di `etichette.DOMANDE`, con le risposte degli agenti; le classi rare (i setup) pesano di piu'.
- Alla fine: per ogni domanda quante ne indovina all'esame, contro chi rispondesse sempre la risposta piu' comune, e
  per i CRT e i setup quante volte, quando la rete dice "c'e'", c'e' davvero. Pesi e resoconto in `dati/rete/`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from nvm.dati.ore import carica
from nvm.rete.etichette import DOMANDE, etichette
from nvm.rete.finestre import CARATTERISTICHE, LUNGHEZZA, TF_RETE, Storia, finestre
from nvm.rete.modello import Occhi
from nvm.tempo import utc

RADICE = Path(__file__).resolve().parents[2]
DATI = RADICE / "dati" / "grezzi"
USCITA = RADICE / "dati" / "rete"
INIZIO = utc(2009, 6, 1)          # servono 40 candele mensili prima: lo storico parte nel 2006
CONTROLLO = utc(2020, 1, 1)
ESAME = utc(2023, 1, 1)
NASCOSTE = 0.15


class Materiale:
    """Gli istanti di tutti gli strumenti, con le risposte degli agenti."""

    def __init__(self, strumenti: list[str], fine: int):
        self.storie, self.chi, self.t, self.y = [], [], [], {nome: [] for nome, _ in DOMANDE}
        for i, s in enumerate(strumenti):
            m, _ = carica(DATI, s, utc(2006, 1, 1), fine, solo_bid=True)
            st = Storia.da(m)
            t = st.istanti(INIZIO, fine)
            e = etichette(m, t)
            self.storie.append(st)
            self.chi.append(np.full(len(t), i))
            self.t.append(t)
            for nome, _ in DOMANDE:
                self.y[nome].append(e[nome])
        self.chi, self.t = np.concatenate(self.chi), np.concatenate(self.t)
        self.y = {k: np.concatenate(v) for k, v in self.y.items()}

    def parte(self, dal: int, al: int) -> np.ndarray:
        return np.flatnonzero((self.t >= dal) & (self.t < al))

    def lotto(self, indici: np.ndarray):
        """Finestre e risposte di un gruppo di istanti, come tensori."""
        x = np.zeros((len(indici), len(TF_RETE), LUNGHEZZA, CARATTERISTICHE), np.float32)
        v = np.ones((len(indici), len(TF_RETE), LUNGHEZZA), bool)
        for i in np.unique(self.chi[indici]):
            dove = np.flatnonzero(self.chi[indici] == i)
            xi, vi = finestre(self.storie[i], self.t[indici[dove]])
            x[dove], v[dove] = xi, vi
        y = [torch.from_numpy(self.y[nome][indici]) for nome, _ in DOMANDE]
        return torch.from_numpy(x), torch.from_numpy(v), y


def pesi_classi(y: np.ndarray) -> torch.Tensor:
    """Le classi rare pesano di piu' (l'inverso della frequenza): un setup ogni trenta istanti conta quanto gli altri
    ventinove insieme."""
    conti = np.bincount(y, minlength=3).astype(np.float64) + 1.0
    w = conti.sum() / (3 * conti)
    return torch.tensor(w / w.mean(), dtype=torch.float32)


def passo(rete: Occhi, x, v, y, pesi, generatore) -> tuple[torch.Tensor, float, float]:
    piene = ~v
    nascoste = (torch.rand(v.shape, generator=generatore) < NASCOSTE) & piene
    riassunto, candele = rete(x, v, nascoste)
    perdita1 = nn.functional.mse_loss(rete.ricostruisci(candele)[nascoste], x[..., :4][nascoste]) \
        if nascoste.any() else torch.zeros(())
    logit = rete.rispondi(riassunto, candele)
    perdita2 = sum(nn.functional.cross_entropy(l, t, weight=w) for l, t, w in zip(logit, y, pesi)) / len(logit)
    return perdita1 + perdita2, float(perdita1.detach()), float(perdita2.detach())


@torch.no_grad()
def giudica(rete: Occhi, mat: Materiale, indici: np.ndarray, lotto: int = 512) -> dict:
    """Quante ne indovina per domanda, con la risposta piu' comune per confronto."""
    rete.eval()
    previsti = {nome: [] for nome, _ in DOMANDE}
    for a in range(0, len(indici), lotto):
        x, v, _ = mat.lotto(indici[a:a + lotto])
        riassunto, candele = rete(x, v)
        for (nome, _), l in zip(DOMANDE, rete.rispondi(riassunto, candele)):
            previsti[nome].append(l.argmax(-1).numpy())
    rete.train()
    fuori = {}
    for nome, _ in DOMANDE:
        p, y = np.concatenate(previsti[nome]), mat.y[nome][indici]
        comune = np.bincount(y, minlength=3).argmax()
        richiamo = [float((p[y == c] == c).mean()) if (y == c).any() else None for c in range(3)]
        precisione = [float((y[p == c] == c).mean()) if (p == c).any() else None for c in range(3)]
        fuori[nome] = {"giuste": float((p == y).mean()), "comune": float((y == comune).mean()),
                       "media dei richiami": float(np.mean([r for r in richiamo if r is not None])),
                       "richiamo": richiamo, "precisione": precisione, "casi": int(len(y))}
    return fuori


def allena(strumenti: list[str], minuti: float, lotto: int = 128, seme: int = 1) -> dict:
    torch.manual_seed(seme)
    g = torch.Generator().manual_seed(seme)
    rng = np.random.default_rng(seme)
    inizio = time.time()
    mat = Materiale(strumenti, utc(2026, 9, 1))
    impara, controlla, esame = mat.parte(INIZIO, CONTROLLO), mat.parte(CONTROLLO, ESAME), mat.parte(ESAME, 2 ** 62)
    print(f"materiale pronto in {time.time() - inizio:.0f} s: impara {len(impara)}, controlla {len(controlla)}, "
          f"esame {len(esame)}", flush=True)
    rete = Occhi()
    print(f"pesi della rete: {sum(p.numel() for p in rete.parameters())}", flush=True)
    ottimo = torch.optim.AdamW(rete.parameters(), lr=5e-4, weight_decay=0.01)
    pesi = [pesi_classi(mat.y[nome][impara]) for nome, _ in DOMANDE]
    campione = rng.choice(controlla, size=min(3000, len(controlla)), replace=False)
    fine, passi, migliore, storia = time.time() + 60 * minuti, 0, None, []
    while time.time() < fine:
        x, v, y = mat.lotto(rng.choice(impara, size=lotto))
        perdita, p1, p2 = passo(rete, x, v, y, pesi, g)
        ottimo.zero_grad()
        perdita.backward()
        nn.utils.clip_grad_norm_(rete.parameters(), 1.0)
        ottimo.step()
        passi += 1
        if passi % 300 == 0:
            c = giudica(rete, mat, campione)
            media = float(np.mean([r["media dei richiami"] for r in c.values()]))
            storia.append({"passo": passi, "scuola 1": p1, "scuola 2": p2, "controllo": media})
            print(f"passo {passi}: scuola 1 {p1:.3f}, scuola 2 {p2:.3f}, controllo {media:.3f}", flush=True)
            if migliore is None or media > migliore[0]:
                migliore = (media, {k: t.clone() for k, t in rete.state_dict().items()})
    if migliore is not None:
        rete.load_state_dict(migliore[1])
    resoconto = {"strumenti": strumenti, "passi": passi, "minuti": minuti, "storia": storia,
                 "controllo": giudica(rete, mat, controlla), "esame": giudica(rete, mat, esame)}
    USCITA.mkdir(parents=True, exist_ok=True)
    torch.save(rete.state_dict(), USCITA / "occhi.pt")
    (USCITA / "resoconto.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False), encoding="utf-8")
    return resoconto


def stampa(resoconto: dict) -> None:
    print(f"\nESAME (dal 2023, anni mai visti), {resoconto['passi']} passi:")
    for nome, r in resoconto["esame"].items():
        prec = ", ".join("—" if p is None else f"{p:.0%}" for p in r["precisione"][1:])
        print(f"  {nome:14s} giuste {r['giuste']:.1%} (sempre la risposta piu' comune {r['comune']:.1%}), "
              f"media richiami {r['media dei richiami']:.1%}, precisione classi 1/2: {prec}")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--minuti", type=float, default=30)
    a.add_argument("--strumenti", default="EURUSD,GBPUSD,AUDUSD,USDCHF,USDJPY,XAUUSD")
    args = a.parse_args()
    torch.set_num_threads(4)
    stampa(allena(args.strumenti.split(","), args.minuti))
