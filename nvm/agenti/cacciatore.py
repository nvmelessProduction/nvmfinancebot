"""Il Cacciatore: su questa coppia di timeframe c'e' un CRT armato?

Regole in `spec/cacciatore.md`, dove ogni punto dice da quale fonte viene.
In breve:

- ogni candela chiusa del timeframe alto e' un range (`CRT high`, `CRT low`);
- fa da range per le due candele alte successive, la 2 e la 3;
- il CRT si arma alla prima candela bassa che esce dal range: sopra `CRT
  high` e' uno short, sotto `CRT low` un long;
- decade alla prima di: rottura (la candela 2 chiude fuori dal range),
  lato opposto (una candela bassa tocca l'altro estremo), scadenza (finisce
  la candela 3).

La variante dichiarata `CHIUSURA_DENTRO` arma il CRT solo quando la candela
2 chiude dentro il range dopo averlo spazzato, e lo lascia valere solo nella
candela 3.

Il Cacciatore non decide se entrare (Grilletto), non mette stop e target
(Livelli) e non giudica la qualita' del CRT (Conferme, Contesto).

Tutto si calcola in un passaggio solo, ma ogni evento usa soltanto candele
gia' chiuse al suo istante: `CRT.stato_a` e' la risposta che il Cacciatore
avrebbe dato in quel momento, e `tests/test_cacciatore.py` lo prova
confrontandola con quella calcolata sui soli dati di allora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import TF, fine_candela, inizio_candela

# Le coppie di Romeo, dal post del 06/01/2025: range -> ingresso.
COPPIE: tuple[tuple[TF, TF], ...] = (
    (TF.MN, TF.D1),
    (TF.W1, TF.H4),
    (TF.D1, TF.H1),
    (TF.H4, TF.M15),
)


class Variante(str, Enum):
    MANUALE = "manuale"
    CHIUSURA_DENTRO = "chiusura dentro"


# La variante in uso quando chi chiama non ne sceglie una: la manopola del
# Cacciatore (`nvm/agenti/manopole.py`).
VARIANTE = Variante.MANUALE


class Verso(str, Enum):
    SHORT = "short"
    LONG = "long"


class Stato(str, Enum):
    NESSUNO = "nessuno"
    ARMATO = "armato"
    DECADUTO = "decaduto"


class Motivo(str, Enum):
    ROTTURA = "rottura"
    LATO_OPPOSTO = "lato opposto"
    SCADENZA = "scadenza"


@dataclass
class CRT:
    """Un CRT trovato, con la sua storia."""

    strumento: str
    alto_tf: TF
    basso_tf: TF
    verso: Verso
    range_inizio: int
    crt_high: float
    crt_low: float
    armato_quando: int
    decaduto_quando: int
    motivo: Motivo
    manipolazione_inizio: int
    # La fine della candela 3: la vita naturale del CRT. MAI se la candela 3
    # non e' ancora iniziata.
    fine_candela_3: int
    # La storia dell'estremo della manipolazione: a ogni istante (chiusura di
    # una candela bassa) il punto piu' lontano toccato fino a li'.
    estremo_istanti: np.ndarray = field(repr=False)
    estremo_valori: np.ndarray = field(repr=False)

    @property
    def crt_50(self) -> float:
        return (self.crt_high + self.crt_low) / 2

    def stato_a(self, istante: int) -> Stato:
        if istante < self.armato_quando:
            return Stato.NESSUNO
        if istante >= self.decaduto_quando:
            return Stato.DECADUTO
        return Stato.ARMATO

    def estremo_a(self, istante: int) -> Optional[float]:
        """L'estremo della manipolazione noto a quell'istante."""
        i = int(np.searchsorted(self.estremo_istanti, istante, side="right")) - 1
        return None if i < 0 else float(self.estremo_valori[i])


# Istante "non ancora noto": la decadenza che cadra' in un futuro non ancora visto.
MAI = np.iinfo(np.int64).max // 2


def caccia(alte: Candele, basse: Candele, variante: Optional[Variante] = None) -> list[CRT]:
    """Tutti i CRT di una coppia, dal primo all'ultimo, sui prezzi BID.

    `alte` e `basse` devono contenere solo candele gia' chiuse (vedi
    `Candele.chiuse_entro`): e' cosi' che il Cacciatore lavora dal vivo, dove
    la candela 2 o la 3 possono essere ancora aperte o non ancora iniziate.
    """
    if alte.strumento != basse.strumento:
        raise ValueError("le candele alte e basse devono essere dello stesso strumento")
    variante = VARIANTE if variante is None else variante
    # A quale candela alta appartiene ogni candela bassa: la candela 2 e la 3
    # si riconoscono dalle basse, senza aspettare che quelle alte chiudano.
    gruppo = inizio_candela(basse.inizio, alte.tf) if len(basse) else np.empty(0, np.int64)
    inizi_alti = np.unique(gruppo)
    trovati: list[CRT] = []
    for k in range(len(alte)):
        for verso in Verso:
            crt = _un_range(alte, basse, gruppo, inizi_alti, k, verso, variante)
            if crt is not None:
                trovati.append(crt)
    trovati.sort(key=lambda c: (c.armato_quando, c.range_inizio, c.verso.value))
    return trovati


def armati_a(crt: list[CRT], istante: int) -> list[CRT]:
    """I CRT armati a quell'istante: la risposta del Cacciatore in quel momento."""
    return [c for c in crt if c.stato_a(istante) is Stato.ARMATO]


def _un_range(
    alte: Candele, basse: Candele, gruppo: np.ndarray, inizi_alti: np.ndarray,
    k: int, verso: Verso, variante: Variante,
) -> Optional[CRT]:
    crt_high = float(alte.bid[k, MASSIMO])
    crt_low = float(alte.bid[k, MINIMO])
    # Una candela piatta (un giorno di festa con un'ora sola di dati) non e' un range.
    if crt_high <= crt_low:
        return None

    # La candela 2 e la 3: le prime due candele alte dopo il range.
    dopo = int(np.searchsorted(inizi_alti, alte.inizio[k], side="right"))
    if dopo >= len(inizi_alti):
        return None
    inizio_2 = int(inizi_alti[dopo])
    inizio_3 = int(inizi_alti[dopo + 1]) if dopo + 1 < len(inizi_alti) else None
    fine_2 = fine_candela(inizio_2, alte.tf)
    fine_3 = fine_candela(inizio_3, alte.tf) if inizio_3 is not None else MAI

    # La candela 2 chiusa, se c'e' gia'.
    k2 = int(np.searchsorted(alte.inizio, inizio_2))
    chiusa_2 = alte.bid[k2] if k2 < len(alte) and alte.inizio[k2] == inizio_2 else None

    if variante is Variante.MANUALE:
        finestra = (inizio_2, inizio_3 if inizio_3 is not None else inizio_2)
    else:
        # Il CRT esiste solo se la candela 2 ha spazzato il lato e ha chiuso
        # dentro il range, senza toccare l'altro lato.
        if chiusa_2 is None:
            return None
        alto_2, basso_2, chiusura_2 = (float(chiusa_2[x]) for x in (MASSIMO, MINIMO, CHIUSURA))
        if verso is Verso.SHORT:
            valido = alto_2 > crt_high and crt_low < chiusura_2 < crt_high and basso_2 > crt_low
        else:
            valido = basso_2 < crt_low and crt_low < chiusura_2 < crt_high and alto_2 < crt_high
        if not valido:
            return None
        finestra = (inizio_3, inizio_3) if inizio_3 is not None else None

    if finestra is None:
        i = j = 0
    else:
        i = int(np.searchsorted(gruppo, finestra[0], side="left"))
        j = int(np.searchsorted(gruppo, finestra[1], side="right"))
    fini = basse.fine[i:j]
    alti = basse.bid[i:j, MASSIMO]
    bassi = basse.bid[i:j, MINIMO]

    if verso is Verso.SHORT:
        oltre, estremi, opposto = alti > crt_high, alti, bassi <= crt_low
        accumula = np.maximum.accumulate
    else:
        oltre, estremi, opposto = bassi < crt_low, bassi, alti >= crt_high
        accumula = np.minimum.accumulate

    if variante is Variante.MANUALE:
        if not oltre.any():
            return None
        p = int(np.argmax(oltre))
        armato_quando = int(fini[p])
        manipolazione_inizio = int(basse.inizio[i + p])
        storia_fini = fini[p:]
        storia_estremi = accumula(estremi[p:])
    else:
        # Armato alla chiusura della candela 2, con il suo estremo.
        p = 0
        armato_quando = fine_2
        estremo_2 = float(chiusa_2[MASSIMO] if verso is Verso.SHORT else chiusa_2[MINIMO])
        m0 = int(np.searchsorted(gruppo, inizio_2, side="left"))
        m1 = int(np.searchsorted(gruppo, inizio_2, side="right"))
        dentro_2 = basse.bid[m0:m1, MASSIMO] > crt_high if verso is Verso.SHORT else basse.bid[m0:m1, MINIMO] < crt_low
        manipolazione_inizio = int(basse.inizio[m0 + int(np.argmax(dentro_2))]) if dentro_2.any() else inizio_2
        storia_fini = np.r_[armato_quando, fini].astype(np.int64)
        storia_estremi = accumula(np.r_[estremo_2, estremi])

    # Decadenza: la prima che succede fra quelle gia' note.
    candidati = [(fine_3, Motivo.SCADENZA)]
    tocchi = np.flatnonzero(opposto[p:])
    if tocchi.size:
        candidati.append((int(fini[p + tocchi[0]]), Motivo.LATO_OPPOSTO))
    if variante is Variante.MANUALE and chiusa_2 is not None:
        chiusura_2 = float(chiusa_2[CHIUSURA])
        rotta = chiusura_2 > crt_high if verso is Verso.SHORT else chiusura_2 < crt_low
        if rotta and armato_quando <= fine_2:
            candidati.append((fine_2, Motivo.ROTTURA))
    # A parita' di istante vince il lato opposto, poi la rottura: sono piu'
    # informativi della scadenza.
    ordine = {Motivo.LATO_OPPOSTO: 0, Motivo.ROTTURA: 1, Motivo.SCADENZA: 2}
    decaduto_quando, motivo = min(candidati, key=lambda c: (c[0], ordine[c[1]]))

    tenuti = storia_fini <= decaduto_quando
    return CRT(
        strumento=alte.strumento,
        alto_tf=alte.tf,
        basso_tf=basse.tf,
        verso=verso,
        range_inizio=int(alte.inizio[k]),
        crt_high=crt_high,
        crt_low=crt_low,
        armato_quando=armato_quando,
        decaduto_quando=decaduto_quando,
        motivo=motivo,
        manipolazione_inizio=manipolazione_inizio,
        fine_candela_3=fine_3,
        estremo_istanti=storia_fini[tenuti].astype(np.int64),
        estremo_valori=storia_estremi[tenuti].astype(np.float64),
    )
