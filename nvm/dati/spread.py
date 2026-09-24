"""Lo spread misurato, per i mesi di cui si ha il bid ma non ancora l'ask.

Non e' uno spread inventato: e' la mediana dello spread vero (ask - bid,
alla chiusura) dei mesi scaricati con entrambi i lati, per lo stesso
strumento, lo stesso anno e la stessa ora del giorno. Lo spread cambia
molto con l'ora (largo alla riapertura della domenica e al cambio di giorno,
stretto a Londra) e con gli anni (1,2 pip nel 2006, 0,3 oggi): una media
unica lo falserebbe.

E' comunque un'approssimazione, e si dichiara: dove c'e' l'ask vero si usa
quello, e la prova con lo spread x 1,5 (`PIANO.md` §3, Fase F) resta
obbligatoria.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA, Minuti


@dataclass
class ModelloSpread:
    strumento: str
    # (anno, ora UTC) -> spread mediano in punti
    tabella: dict[tuple[int, int], float]

    @classmethod
    def da(cls, esatti: list[Minuti]) -> "ModelloSpread":
        if not esatti:
            raise ValueError("serve almeno un mese con l'ask vero")
        strumento = esatti[0].strumento
        valori: dict[tuple[int, int], list[np.ndarray]] = {}
        for m in esatti:
            spread = (m.ask[:, CHIUSURA] - m.bid[:, CHIUSURA]).astype(np.float64)
            anni = m.t.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
            ore = (m.t // 3600) % 24
            for chiave in set(zip(anni.tolist(), ore.tolist())):
                dentro = (anni == chiave[0]) & (ore == chiave[1])
                valori.setdefault(chiave, []).append(spread[dentro])
        return cls(strumento, {k: float(np.median(np.concatenate(v))) for k, v in valori.items()})

    def spread(self, anno: int, ora: int) -> float:
        """Lo spread per un anno e un'ora; se quell'anno manca, l'anno piu' vicino."""
        if (anno, ora) in self.tabella:
            return self.tabella[(anno, ora)]
        stessa_ora = [(abs(a - anno), a) for a, o in self.tabella if o == ora]
        if stessa_ora:
            return self.tabella[(min(stessa_ora)[1], ora)]
        return float(np.median(list(self.tabella.values())))

    def applica(self, solo_bid: Minuti) -> Minuti:
        """L'ask stimato: il bid piu' lo spread del suo anno e della sua ora."""
        anni = solo_bid.t.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
        ore = (solo_bid.t // 3600) % 24
        cache: dict[tuple[int, int], int] = {}
        spread = np.empty(len(solo_bid), np.int32)
        for i, chiave in enumerate(zip(anni.tolist(), ore.tolist())):
            if chiave not in cache:
                cache[chiave] = int(round(self.spread(*chiave)))
            spread[i] = cache[chiave]
        return Minuti(
            solo_bid.strumento, solo_bid.t, solo_bid.bid, solo_bid.bid + spread[:, None],
            solo_bid.volume_bid, solo_bid.volume_ask, solo_bid.passo,
        )


def allarga(candele: Candele, fattore: float) -> Candele:
    """Le stesse candele con lo spread moltiplicato: l'ask si allontana dal bid.

    Serve alla prova di robustezza della Fase F (`PIANO.md` §3): una
    strategia che vive solo di spread stretto non regge dal vivo.
    """
    ask = candele.bid + fattore * (candele.ask - candele.bid)
    return Candele(candele.strumento, candele.tf, candele.inizio, candele.fine, candele.bid, ask, candele.volume)
