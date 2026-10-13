"""I sensi di Nameless: le candele di ogni timeframe, con gli orari di TradingView, in fila per gli occhi.

I timeframe sono quelli del proprietario (13/10/2026): *"1h 4h 6h 12h 1d 1w 1m 3m 12m"*, con gli orari dei suoi
grafici di TradingView (`candele.SESSIONI`: le 18 di New York, cioe' 0, 4, 8, 12, 16, 20 italiane; l'UTC per le
crypto). Le candele sopra l'ora si fanno dalle ore con quel calendario (`candele.costruisci`), 3 e 12 mesi dai mesi
(`candele.raggruppa`), come dal vivo.

Le candele di tutti i mercati stanno in fila in pochi array (`Sensi`), cosi' le finestre si fanno sulla scheda grafica
al momento, senza prepararle prima (`nvm/nameless/occhi.py`). Per ogni ora `j` e ogni timeframe, `entro[k][j]` e'
l'ultima candela di quel timeframe gia' chiusa quando arriva l'ora dopo (`prossimo[j]`): il venerdi' sera la candela 2
di un CRT che apre la domenica e' gia' finita, anche se sulla carta chiude alla riapertura, perche' in mezzo non
arriva nessun prezzo. Una candela che chiude dopo non entra mai nella finestra. Ogni mercato (o pezzo di mercato, se
il controllo di qualita' l'ha tagliato) ha le sue candele: una finestra non passa mai da un mercato all'altro
(`primo`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nvm.dati.candele import Candele, costruisci, raggruppa
from nvm.dati.minuti import Minuti
from nvm.tempo import TF, scarti_ny

TF_NAMELESS = (TF.H1, TF.H4, TF.H6, TF.H12, TF.D1, TF.W1, TF.MN, TF.Q3, TF.Y1)
D1 = TF_NAMELESS.index(TF.D1)


def candele_di(ore: Minuti) -> dict[TF, Candele]:
    """Le candele di tutti i timeframe di Nameless da quelle a 1 ora, sul calendario dello strumento."""
    c = {tf: costruisci(ore, tf) for tf in TF_NAMELESS if tf not in (TF.Q3, TF.Y1)}
    c[TF.Q3] = raggruppa(c[TF.MN], TF.Q3)
    c[TF.Y1] = raggruppa(c[TF.MN], TF.Y1)
    return c


def tempo_di(inizio: np.ndarray) -> np.ndarray:
    """Quando apre ogni candela, come lo vede chi guarda il grafico: l'ora di New York e il giorno della settimana,
    ognuno come seno e coseno ([n, 4] float32)."""
    if not len(inizio):
        return np.zeros((0, 4), np.float32)
    ny = inizio + scarti_ny(inizio)
    ora = (ny % 86400) / 3600.0
    giorno = (ny // 86400 + 3) % 7          # il primo gennaio 1970 era un giovedi': lunedi' = 0
    a, b = 2 * np.pi * ora / 24, 2 * np.pi * giorno / 7
    return np.stack([np.sin(a), np.cos(a), np.sin(b), np.cos(b)], axis=1).astype(np.float32)


@dataclass
class Sensi:
    """Le candele di tutti i pezzi di mercato, una fila per timeframe (l'ordine di `TF_NAMELESS`).

    - `prezzi[k]` [n, 4] apertura, massimo, minimo, chiusura; `tempo[k]` [n, 4] (`tempo_di`); `fine[k]` [n] UTC;
    - `prossimo` [ore]: quando apre l'ora dopo (la fine dell'ora, se e' l'ultima del pezzo);
    - `entro[k]` [ore]: per ogni ora, l'ultima candela del timeframe chiusa a `prossimo` (`primo - 1` se nessuna);
    - `primo` [pezzi, timeframe]: la prima candela di ogni pezzo; `chi` [ore]: il pezzo di ogni ora.
    """

    nomi: list
    prezzi: list
    tempo: list
    fine: list
    entro: list
    primo: np.ndarray
    chi: np.ndarray
    prossimo: np.ndarray

    @classmethod
    def da(cls, pezzi: list[tuple[str, Minuti]]) -> "Sensi":
        """`pezzi`: (nome, ore) per ogni pezzo di mercato. Gli orari (`candele.SESSIONI`) vanno messi prima."""
        n_tf = len(TF_NAMELESS)
        prezzi, tempo, fine, entro = ([[] for _ in range(n_tf)] for _ in range(4))
        primo, chi, nomi, conti, prossimi = [], [], [], [0] * n_tf, []
        for p, (nome, ore) in enumerate(pezzi):
            c = candele_di(ore)
            fine_ore = c[TF.H1].fine
            prossimo = np.maximum(np.r_[c[TF.H1].inizio[1:], fine_ore[-1:]], fine_ore)
            primo.append(list(conti))
            for k, tf in enumerate(TF_NAMELESS):
                prezzi[k].append(c[tf].bid.astype(np.float32))
                tempo[k].append(tempo_di(c[tf].inizio))
                fine[k].append(c[tf].fine.astype(np.int64))
                entro[k].append(np.searchsorted(c[tf].fine, prossimo, side="right") - 1 + conti[k])
                conti[k] += len(c[tf])
            chi.append(np.full(len(fine_ore), p, np.int32))
            prossimi.append(prossimo.astype(np.int64))
            nomi.append(nome)
        unisci = lambda xs, forma: np.concatenate(xs) if xs else np.zeros(forma)
        return cls(nomi, [unisci(x, (0, 4)).astype(np.float32) for x in prezzi],
                   [unisci(x, (0, 4)).astype(np.float32) for x in tempo],
                   [unisci(x, (0,)).astype(np.int64) for x in fine],
                   [unisci(x, (0,)).astype(np.int64) for x in entro],
                   np.array(primo, np.int64).reshape(-1, n_tf), unisci(chi, (0,)).astype(np.int32),
                   unisci(prossimi, (0,)).astype(np.int64))

    def ore(self) -> int:
        return len(self.chi)

    def istanti(self, dal: int, al: int, giorni: int = 15, ore_prima: int = 24) -> np.ndarray:
        """Le ore (indici) che chiudono in [dal, al) e hanno abbastanza storia dietro: almeno `giorni` candele
        giornaliere chiuse (la scala dei prezzi) e `ore_prima` ore dello stesso pezzo (il taglio del futuro)."""
        f = self.fine[0]
        j = np.flatnonzero((f >= dal) & (f < al))
        p = self.chi[j]
        ok = (self.entro[D1][j] - self.primo[p, D1] >= giorni - 1) & (j - self.primo[p, 0] >= ore_prima)
        return j[ok]
