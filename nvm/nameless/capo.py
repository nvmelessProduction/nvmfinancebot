"""Il Capo di Nameless (fase 3): fra i setup che le regole delle foto prenderebbero, quali prendere davvero.

Il proprietario: *"il bot è intelligente, quindi dovrà sapere quanto rischiare, quando fermarsi"*; il piano
(`documenti/PROGETTO-NAMELESS.md`): il Capo impara dai risultati veri, coi costi, e si giudica sugli anni che non ha
mai visto. Prenderli tutti perde (sui 20 anni circa -0,08 R a operazione, `nvm/nameless/esiti.py`): il Capo deve
trovare quelli che guadagnano.

Cosa guarda, per ogni setup, all'ultima ora della candela 2 (prima di entrare):

- quello che vedono gli occhi (fase 1): il riassunto del quadro e le ultime due candele del timeframe del CRT;
- quello che dicono le zone (fase 2): tutte le loro risposte, su ogni timeframe;
- il setup: timeframe, verso, quanti R valgono il TP1 e il target finale, che target e', quanto e' grande lo stop e
  il range rispetto al range medio giornaliero, se il piano e' "25% al TP1 e il resto al target" o "tutto al TP1".

Occhi e zone restano come sono (non si riallenano sui risultati: imparerebbero a memoria il passato); il Capo e' una
rete piccola sopra, con un voto: quanti R si aspetta. Si prende il setup se si aspetta piu' di zero. Ne allena
alcune con semi diversi e fa la media (`Capo.insieme`): un Capo solo e' piu' ballerino.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from nvm.nameless.materie import CORTO, TF_CRT, TIPI
from nvm.nameless.sensi import TF_NAMELESS

# Le caratteristiche del setup, nell'ordine di `setup`.
SETUP = tuple([f"CRT {tf.value}" for tf in TF_CRT] + ["vendita", "R al TP1", "R al target", "tutto al TP1"] +
              [f"target {t}" for t in TIPI] + ["stop sul range giornaliero", "range sul range giornaliero"])


def setup(crt: dict, righe: np.ndarray, tf: int, spread: np.ndarray, spread_range: float) -> np.ndarray:
    """Le caratteristiche dei setup `righe` di `crt` (le materie di un timeframe, indice `tf` in `TF_CRT`):
    [N, len(SETUP)] float32. `spread` e' quello stimato per ognuno (`esiti.spread_a`): il range medio giornaliero e'
    `spread / spread_range`."""
    n = len(righe)
    x = np.zeros((n, len(SETUP)), np.float32)
    x[:, tf] = 1.0
    ingresso, stop, tp1, ob = (crt[c][righe].astype(np.float64) for c in ("ingresso", "stop", "tp1", "obiettivo"))
    corto = crt["verso"][righe] == CORTO
    rischio = np.maximum(np.abs(ingresso - stop), 1e-12)
    segno = np.where(corto, -1.0, 1.0)
    r_tp1 = np.abs(tp1 - ingresso) / rischio
    r_ob = np.abs(ob - ingresso) / rischio
    al_finale = (ob != tp1) & (segno * (ob - tp1) >= 0) & (r_ob >= 1 - 1e-12)
    giornaliero = np.maximum(spread / spread_range, 1e-12)
    x[:, len(TF_CRT)] = corto
    x[:, len(TF_CRT) + 1] = np.log1p(r_tp1)
    x[:, len(TF_CRT) + 2] = np.log1p(r_ob)
    x[:, len(TF_CRT) + 3] = ~al_finale
    tipo = crt["tipo"][righe]
    for t in range(len(TIPI)):
        x[:, len(TF_CRT) + 4 + t] = tipo == t
    x[:, -2] = np.log1p(rischio / giornaliero)
    x[:, -1] = np.log1p((crt["alto"][righe] - crt["basso"][righe]) / giornaliero)
    return x


@torch.no_grad()
def vista(zone, lettore, j: np.ndarray, tf: np.ndarray, lotto: int = 1024) -> np.ndarray:
    """Quello che occhi e zone vedono all'ora `j` di ogni setup (col timeframe del suo CRT, indice in `TF_CRT`):
    [N, 3d + 15 * len(TF_CRT) + 6 * len(TF_CANDELA)] float32."""
    zone.eval()
    pezzi = []
    dove = lettore.dove
    k_tf = torch.tensor([TF_NAMELESS.index(t) for t in TF_CRT], device=dove)
    for a in range(0, len(j), lotto):
        jj = torch.as_tensor(j[a:a + lotto], device=dove)
        contenuto, tempo, vuote, _ = lettore.guarda(jj, jj)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dove == "cuda"):
            crt, candela, riassunto, candele = zone(contenuto, tempo, vuote, tutto=True)
        righe = torch.arange(len(jj), device=dove)
        k = k_tf[torch.as_tensor(tf[a:a + lotto], device=dove).long()]
        ultima, prima = candele[righe, k, -1], candele[righe, k, -2]
        pezzi.append(torch.cat([riassunto, ultima, prima, crt.flatten(1), candela.flatten(1)], -1).float().cpu())
    return torch.cat(pezzi).numpy() if pezzi else np.zeros((0, 0), np.float32)


class Capo(nn.Module):
    """La rete piccola del Capo: dalla vista e dal setup, quanti R si aspetta."""

    def __init__(self, entrate: int, d: int = 128, abbandono: float = 0.3):
        super().__init__()
        self.rete = nn.Sequential(nn.LayerNorm(entrate), nn.Linear(entrate, d), nn.GELU(), nn.Dropout(abbandono),
                                  nn.Linear(d, d), nn.GELU(), nn.Dropout(abbandono), nn.Linear(d, 1))
        self.entrate = entrate

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.rete(x)[:, 0]

    @staticmethod
    @torch.no_grad()
    def insieme(capi: list, x: torch.Tensor) -> torch.Tensor:
        """La media dei voti di piu' Capi."""
        for c in capi:
            c.eval()
        return torch.stack([c(x) for c in capi]).mean(0)
