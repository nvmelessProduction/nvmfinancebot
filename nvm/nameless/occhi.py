"""Gli occhi di Nameless (fase 1): la rete che legge le candele di tutti i timeframe insieme.

La scuola delle candele (`documenti/PROGETTO-NAMELESS.md`): si nascondono delle candele e la rete le deve indovinare.
Cosi' impara a leggere un grafico da sola, prima di sapere i nomi delle cose (CRT, key level, gap: fase 2). Due modi
di nascondere:

- **a caso**: il 15% delle candele di ogni timeframe; la rete le ricostruisce da quelle intorno e dagli altri
  timeframe (leggere);
- **il futuro**: si torna indietro da 1 a 24 ore (il "taglio") e si nasconde tutto quello che e' chiuso dopo, in ogni
  timeframe; la rete deve dire cosa e' successo dopo il taglio vedendo solo il prima (prevedere).

Ogni candela e' un gettone: il contenuto (apertura, massimo, minimo, chiusura rispetto all'ultima chiusura a 1 ora
prima del taglio, in unita' del range medio di 14 giorni, compressi con l'arcoseno iperbolico; se e' salita), il
tempo (l'ora di New York e il giorno, `sensi.tempo_di`), il timeframe e il posto nella fila. Una candela nascosta
tiene il tempo e il posto, il contenuto diventa un segnaposto. Un transformer fa parlare tutti i gettoni fra loro;
un gettone in testa (`riassunto`) raccoglie il quadro intero, per le materie della fase 2.

L'esame (`copia`): indovinare meglio di chi copia l'ultima candela vista dello stesso timeframe. La rete parte proprio
da li' e impara la correzione (`Occhi.indovina`).
"""

from __future__ import annotations

import torch
from torch import nn

from nvm.nameless.sensi import D1, TF_NAMELESS, Sensi

LUNGHEZZA = 40          # candele per timeframe
CONTENUTO = 5           # apertura, massimo, minimo, chiusura (in scala), se e' salita
VICINATO = 10           # la candela vista prima e quella vista dopo, con se ci sono (`vicinato`)
TEMPO = 4               # ora di New York e giorno della settimana, seno e coseno
GIORNI_SCALA = 14
NASCOSTE = 0.15
ORE_FUTURO = 24


class Lettore:
    """I sensi sulla scheda grafica: fa le finestre di un gruppo di ore, al momento."""

    def __init__(self, sensi: Sensi, dove: str | torch.device = "cpu"):
        t = lambda a: torch.as_tensor(a, device=dove)
        self.prezzi = [t(p) for p in sensi.prezzi]
        self.tempo = [t(x) for x in sensi.tempo]
        self.entro = [t(e) for e in sensi.entro]
        self.primo = t(sensi.primo)
        self.chi = t(sensi.chi).long()
        self.dove = dove
        self.passi = torch.arange(-LUNGHEZZA + 1, 1, device=dove)

    def guarda(self, j: torch.Tensor, taglio: torch.Tensor):
        """Le finestre alle ore `j` [B], con tutto quello che chiude dopo l'ora `taglio` [B] (<= j, stesso pezzo)
        segnato in `dopo`. Prezzi rispetto alla chiusura dell'ora del taglio, in unita' del range medio delle ultime
        14 giornate chiuse al taglio: niente di quello che e' dopo il taglio entra nei numeri.

        (contenuto [B, K, L, 5], tempo [B, K, L, 4], vuote [B, K, L], dopo [B, K, L])."""
        p = self.chi[j]
        rif = self.prezzi[0][taglio, 3]
        kd = self.entro[D1][taglio][:, None] + torch.arange(-GIORNI_SCALA + 1, 1, device=self.dove)
        buone = kd >= self.primo[p, D1][:, None]
        g = self.prezzi[D1][kd.clamp(min=0)]
        rng = torch.where(buone, g[..., 1] - g[..., 2], torch.zeros((), device=self.dove))
        scala = (rng.sum(1) / buone.sum(1).clamp(min=1)).clamp(min=1e-12)
        contenuto, tempo, vuote, dopo = [], [], [], []
        for k in range(len(TF_NAMELESS)):
            idx = self.entro[k][j][:, None] + self.passi
            v = idx < self.primo[p, k][:, None]
            i = idx.clamp(min=0)
            c = self.prezzi[k][i]
            rel = torch.asinh((c - rif[:, None, None]) / scala[:, None, None])
            su = (c[..., 3] > c[..., 0]).to(rel.dtype)[..., None]
            contenuto.append(torch.cat([rel, su], -1).masked_fill(v[..., None], 0.0))
            tempo.append(self.tempo[k][i].masked_fill(v[..., None], 0.0))
            vuote.append(v)
            dopo.append((idx > self.entro[k][taglio][:, None]) & ~v)
        return torch.stack(contenuto, 1), torch.stack(tempo, 1), torch.stack(vuote, 1), torch.stack(dopo, 1)


def nascondi(vuote: torch.Tensor, dopo: torch.Tensor, futuro: torch.Tensor, generatore=None) -> torch.Tensor:
    """Le candele da indovinare: quelle dopo il taglio per gli esempi del futuro, il 15% a caso per gli altri."""
    caso = torch.rand(vuote.shape, generator=generatore, device=vuote.device) < NASCOSTE
    return torch.where(futuro[:, None, None], dopo, caso) & ~vuote


def _vicine(vuote: torch.Tensor, nascoste: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Per ogni posto, la candela vista prima e quella vista dopo nello stesso timeframe (-1 e `LUNGHEZZA` se non
    c'e')."""
    viste = ~vuote & ~nascoste
    posto = torch.arange(LUNGHEZZA, device=vuote.device).expand_as(viste)
    ultima = torch.cummax(torch.where(viste, posto, torch.full_like(posto, -1)), dim=-1).values
    prima = torch.cat([torch.full_like(ultima[..., :1], -1), ultima[..., :-1]], -1)
    fuori = torch.full_like(posto, LUNGHEZZA)
    seguente = torch.cummin(torch.where(viste, posto, fuori).flip(-1), dim=-1).values.flip(-1)
    dopo = torch.cat([seguente[..., 1:], torch.full_like(seguente[..., :1], LUNGHEZZA)], -1)
    return prima, dopo


def _prendi(contenuto: torch.Tensor, dove: torch.Tensor) -> torch.Tensor:
    return torch.gather(contenuto[..., :4], 2, dove.clamp(0, LUNGHEZZA - 1)[..., None].expand(*dove.shape, 4))


def copia(contenuto: torch.Tensor, vuote: torch.Tensor, nascoste: torch.Tensor):
    """Chi copia l'ultima candela vista: per ogni candela nascosta, la candela visibile prima di lei nello stesso
    timeframe. (previsione [B, K, L, 4], dove si puo' confrontare [B, K, L]: nascosta e con una visibile prima)."""
    prima, _ = _vicine(vuote, nascoste)
    return _prendi(contenuto, prima), nascoste & (prima >= 0)


def vicinato(contenuto: torch.Tensor, vuote: torch.Tensor, nascoste: torch.Tensor) -> torch.Tensor:
    """Accanto a ogni candela, la candela vista prima e quella vista dopo (apertura, massimo, minimo, chiusura e se
    c'e'): quello che un occhio guarda per primo [B, K, L, 10]. Solo candele viste: niente di nascosto entra."""
    prima, dopo = _vicine(vuote, nascoste)
    c_prima, c_dopo = prima >= 0, dopo < LUNGHEZZA
    return torch.cat([_prendi(contenuto, prima) * c_prima[..., None], c_prima[..., None].to(contenuto.dtype),
                      _prendi(contenuto, dopo) * c_dopo[..., None], c_dopo[..., None].to(contenuto.dtype)], -1)


class Occhi(nn.Module):
    def __init__(self, d: int = 128, strati: int = 4, teste: int = 4, abbandono: float = 0.1):
        super().__init__()
        n_tf = len(TF_NAMELESS)
        self.contenuto = nn.Linear(CONTENUTO + VICINATO, d)
        self.tempo = nn.Linear(TEMPO, d)
        self.posto = nn.Parameter(torch.randn(n_tf, LUNGHEZZA, d) * 0.02)
        self.riassunto = nn.Parameter(torch.randn(1, 1, d) * 0.02)
        self.nascosta = nn.Parameter(torch.zeros(d))
        strato = nn.TransformerEncoderLayer(d, teste, 4 * d, dropout=abbandono, batch_first=True, norm_first=True)
        self.lettore = nn.TransformerEncoder(strato, strati, enable_nested_tensor=False)
        self.fine = nn.LayerNorm(d)
        self.ricostruisci = nn.Linear(d, 4)
        nn.init.zeros_(self.ricostruisci.weight)
        nn.init.zeros_(self.ricostruisci.bias)
        self.misura = {"d": d, "strati": strati, "teste": teste}

    def forward(self, contenuto, tempo, vuote, nascoste=None):
        """(riassunto [B, d], candele [B, K, L, d]). Le candele `nascoste` non mostrano il contenuto."""
        b, n_tf, lung, _ = contenuto.shape
        if nascoste is None:
            nascoste = torch.zeros_like(vuote)
        proprio = contenuto.masked_fill(nascoste[..., None], 0.0)
        h = self.contenuto(torch.cat([proprio, vicinato(contenuto, vuote, nascoste)], -1))
        h = h + nascoste[..., None].to(h.dtype) * self.nascosta.to(h.dtype)
        h = (h + self.tempo(tempo) + self.posto).reshape(b, n_tf * lung, -1)
        h = torch.cat([self.riassunto.expand(b, -1, -1).to(h.dtype), h], dim=1)
        maschera = torch.cat([torch.zeros(b, 1, dtype=torch.bool, device=h.device), vuote.reshape(b, -1)], dim=1)
        h = self.fine(self.lettore(h, src_key_padding_mask=maschera))
        return h[:, 0], h[:, 1:].reshape(b, n_tf, lung, -1)

    def indovina(self, contenuto, tempo, vuote, nascoste) -> torch.Tensor:
        """Apertura, massimo, minimo, chiusura (in scala) di ogni candela [B, K, L, 4]: la rete parte da chi copia
        l'ultima candela vista (`copia`) e impara quanto correggerla. Appena nata (correzione zero) sbaglia quanto
        lui: tutto quello che fa meglio l'ha imparato."""
        base, _ = copia(contenuto, vuote, nascoste)
        return base + self.ricostruisci(self(contenuto, tempo, vuote, nascoste)[1]).to(base.dtype)
