"""Le zone di Nameless (fase 2): sopra gli occhi della fase 1, una testa per ogni materia della strategia.

Come le aree specializzate del cervello (`documenti/PROGETTO-NAMELESS.md`): gli occhi leggono tutti i timeframe
insieme, le zone rispondono alle domande delle regole delle foto (`nvm/nameless/materie.py`). Ogni testa guarda il
quadro intero (il riassunto degli occhi) e le ultime due candele del suo timeframe.

- **CRT**, una testa per timeframe di `materie.TF_CRT`, all'ultima ora della candela 2: c'e' un CRT? ha preso un key
  level? si entra? (0 niente, 1 acquisto, 2 vendita); e, per i CRT col key level, la direzione e' dalla nostra parte?
  (0 no, 1 si'), il target finale (gap, key level, l'altro lato del range: `materie.TIPI`) e quanti R vale.
- **Candela**, una testa per timeframe di `materie.TF_CANDELA`, a ogni ora: com'e' l'ultima candela chiusa rispetto a
  quella prima (0 giu', 1 nessuna, 2 su) e se ha accettato un lato il cui estremo non e' ancora preso (0 nessuna,
  1 su, 2 giu').
"""

from __future__ import annotations

import torch
from torch import nn

from nvm.nameless.materie import TF_CANDELA, TF_CRT
from nvm.nameless.occhi import Occhi
from nvm.nameless.sensi import TF_NAMELESS

# Le uscite di ogni testa: nome -> (inizio, quante). "rr" e' una sola uscita: log(1 + R del target finale).
USCITE_CRT = {"crt": (0, 3), "key level": (3, 3), "entra": (6, 3), "direzione": (9, 2), "target": (11, 3),
              "rr": (14, 1)}
USCITE_CANDELA = {"direzione": (0, 3), "accetta": (3, 3)}


def _testa(entrate: int, d: int, uscite: int) -> nn.Module:
    return nn.Sequential(nn.Linear(entrate, d), nn.GELU(), nn.Linear(d, uscite))


class Zone(nn.Module):
    def __init__(self, occhi: Occhi):
        super().__init__()
        self.occhi = occhi
        d = occhi.misura["d"]
        self.i_crt = [TF_NAMELESS.index(tf) for tf in TF_CRT]
        self.i_candela = [TF_NAMELESS.index(tf) for tf in TF_CANDELA]
        self.teste_crt = nn.ModuleList([_testa(3 * d, d, 15) for _ in TF_CRT])
        self.teste_candela = nn.ModuleList([_testa(3 * d, d, 6) for _ in TF_CANDELA])

    def forward(self, contenuto, tempo, vuote, tutto: bool = False):
        """(crt [B, len(TF_CRT), 15], candela [B, len(TF_CANDELA), 6]): i logit di ogni testa (`USCITE_CRT`,
        `USCITE_CANDELA`). Con `tutto` anche quello che vedono gli occhi (riassunto [B, d], candele [B, K, L, d]): il
        Capo (fase 3) guarda tutto."""
        riassunto, candele = self.occhi(contenuto, tempo, vuote)
        ingresso = lambda i: torch.cat([riassunto, candele[:, i, -1], candele[:, i, -2]], -1)
        crt = torch.stack([t(ingresso(i)) for t, i in zip(self.teste_crt, self.i_crt)], 1)
        candela = torch.stack([t(ingresso(i)) for t, i in zip(self.teste_candela, self.i_candela)], 1)
        return (crt, candela, riassunto, candele) if tutto else (crt, candela)


def parte(uscite: torch.Tensor, nome: str, quali: dict) -> torch.Tensor:
    a, n = quali[nome]
    return uscite[..., a:a + n]
