"""La rete: gli "occhi" che leggono le candele di tutti i timeframe insieme, e le teste che rispondono.

Ogni candela diventa un vettore (`entrata`), con il suo posto nel timeframe; un transformer (la famiglia delle AI
moderne, qui allenato solo sui grafici) fa parlare tutte le candele di tutti i timeframe fra loro, e un segnaposto in
testa (`riassunto`) raccoglie il quadro intero. Le teste:

- `ricostruisci`: scuola 1, indovina le candele nascoste (impara a leggere i grafici da sola);
- una testa per ogni domanda della scuola 2 (`etichette.DOMANDE`), che guarda il riassunto e l'ultima candela del
  timeframe della domanda.

Piccola di proposito (circa 150 mila pesi): con gli esempi che abbiamo una rete grande imparerebbe a memoria.
"""

from __future__ import annotations

import torch
from torch import nn

from nvm.rete.etichette import DOMANDE
from nvm.rete.finestre import CARATTERISTICHE, LUNGHEZZA, TF_RETE


class Occhi(nn.Module):
    def __init__(self, d: int = 64, strati: int = 3, teste: int = 4, abbandono: float = 0.1):
        super().__init__()
        n_tf = len(TF_RETE)
        self.entrata = nn.Linear(CARATTERISTICHE, d)
        self.posto = nn.Parameter(torch.randn(n_tf, LUNGHEZZA, d) * 0.02)
        self.riassunto = nn.Parameter(torch.randn(1, 1, d) * 0.02)
        self.nascosta = nn.Parameter(torch.zeros(d))
        strato = nn.TransformerEncoderLayer(d, teste, 4 * d, dropout=abbandono, batch_first=True, norm_first=True)
        self.lettore = nn.TransformerEncoder(strato, strati, enable_nested_tensor=False)
        self.fine = nn.LayerNorm(d)
        self.ricostruisci = nn.Linear(d, 4)
        self.risposte = nn.ModuleList([nn.Linear(2 * d, 3) for _ in DOMANDE])
        self._tf = [TF_RETE.index(tf) for _, tf in DOMANDE]

    def forward(self, x: torch.Tensor, vuote: torch.Tensor, nascoste: torch.Tensor | None = None):
        """x [B, n_tf, L, C], vuote [B, n_tf, L]: (riassunto [B, d], candele [B, n_tf, L, d])."""
        b, n_tf, lung, _ = x.shape
        h = self.entrata(x)
        if nascoste is not None:
            h = torch.where(nascoste[..., None], self.nascosta.expand_as(h), h)
        h = (h + self.posto).reshape(b, n_tf * lung, -1)
        h = torch.cat([self.riassunto.expand(b, -1, -1), h], dim=1)
        maschera = torch.cat([torch.zeros(b, 1, dtype=torch.bool, device=x.device), vuote.reshape(b, -1)], dim=1)
        h = self.fine(self.lettore(h, src_key_padding_mask=maschera))
        return h[:, 0], h[:, 1:].reshape(b, n_tf, lung, -1)

    def rispondi(self, riassunto: torch.Tensor, candele: torch.Tensor) -> list[torch.Tensor]:
        """I logit (3 classi) di ogni domanda della scuola 2."""
        return [testa(torch.cat([riassunto, candele[:, i, -1]], dim=-1)) for testa, i in zip(self.risposte, self._tf)]
