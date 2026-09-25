"""Le entrate di Romeo dal vivo (`spec/romeo-dal-vivo.md`).

L'utente le manda al bot quando le vede sul canale di Romeo:

    /romeo EURUSD compra 1.0765 stop 1.0760 target 1.0800

Il bot dice subito, sul canale equipe, se fra le sue decisioni delle ultime
24 ore c'era la stessa entrata e quanto vicina; il sabato la somiglianza a
Romeo impara anche da queste. Non diventano mai operazioni: Romeo e' il
metro e un esempio, non un ordine (decisione dell'utente, 24/09/2026:
addestrare non vuol dire obbligare).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np

from nvm.dati.minuti import PUNTO
from nvm.dati.strumenti import STRUMENTI

if TYPE_CHECKING:
    from nvm.vivo.stato import Seguita

# Romeo pubblica dopo essere entrato, e l'utente la manda quando la vede: si
# guardano le decisioni del bot fino a 24 ore prima, e fino a un'ora dopo.
PRIMA = 24 * 3600
DOPO = 3600
# Ritrovata: ingresso entro meta' del rischio di Romeo, la soglia del PIANO.md.
META_RISCHIO = 0.5
PIP = {n: s.pip for n, s in STRUMENTI.items()}
NOMI = {"ORO": "XAUUSD", "GOLD": "XAUUSD"}
COMPRA = {"compra", "compro", "acquisto", "buy", "long"}
VENDE = {"vende", "vendo", "vendita", "sell", "short"}
PAROLE = {"stop": "stop", "sl": "stop", "target": "target", "tp": "target", "obiettivo": "target",
          "ingresso": "ingresso", "entry": "ingresso", "prezzo": "ingresso"}
RIEMPITIVI = {"a", "@", "at", "da", "e"}
FORMATO = "/romeo EURUSD compra 1.0765 stop 1.0760 (target facoltativo: target 1.0800)"


@dataclass
class EntrataDiRomeo:
    strumento: str
    verso: str          # "long" o "short", come nelle decisioni
    ingresso: float
    stop: Optional[float]
    target: Optional[float]
    quando: int         # quando e' arrivata al bot, UTC
    # La decisione del bot piu' vicina, se c'era, e quanto: in rischi di Romeo, o in pip se manca lo stop.
    vista: Optional[str] = None
    distanza: Optional[float] = None
    pip: Optional[float] = None
    presa: bool = False

    @property
    def rischio(self) -> Optional[float]:
        return None if self.stop is None else abs(self.ingresso - self.stop)

    @property
    def ritrovata(self) -> bool:
        return self.distanza is not None and self.distanza <= META_RISCHIO


def _numero(testo: str) -> Optional[float]:
    try:
        return float(testo.replace(",", "."))
    except ValueError:
        return None


def leggi_comando(testo: str, quando: int) -> EntrataDiRomeo | str:
    """L'entrata scritta nel comando, o il perche' non si legge."""
    parole = testo.split()
    if not parole or not re.fullmatch(r"/romeo(@\w+)?", parole[0], re.IGNORECASE):
        return "non è un comando /romeo"
    parole = parole[1:]
    strumento = verso = chiave = None
    numeri: dict[str, float] = {}
    for p in parole:
        pm, pl = p.upper(), p.lower().rstrip(":")
        if pm in PUNTO or pm in NOMI:
            strumento = NOMI.get(pm, pm)
        elif pl in COMPRA:
            verso = "long"
        elif pl in VENDE:
            verso = "short"
        elif pl in PAROLE:
            chiave = PAROLE[pl]
        elif pl in RIEMPITIVI:
            continue
        elif (n := _numero(p)) is not None:
            k = chiave or ("ingresso" if "ingresso" not in numeri else None)
            if k is None or k in numeri:
                return f"c'è un numero di troppo ({p}). Scrivi così: {FORMATO}"
            numeri[k] = n
            chiave = None
        else:
            return f"non capisco «{p}». Scrivi così: {FORMATO}"
    if strumento is None:
        return f"manca lo strumento ({', '.join(PUNTO)}). Scrivi così: {FORMATO}"
    if verso is None:
        return f"manca se compra o vende. Scrivi così: {FORMATO}"
    if "ingresso" not in numeri:
        return f"manca il prezzo di ingresso. Scrivi così: {FORMATO}"
    ingresso, stop, target = numeri["ingresso"], numeri.get("stop"), numeri.get("target")
    segno = 1 if verso == "long" else -1
    if stop is not None and segno * (ingresso - stop) <= 0:
        return "lo stop sta dalla parte sbagliata: per un acquisto va sotto l'ingresso, per una vendita sopra"
    if target is not None and segno * (target - ingresso) <= 0:
        return "il target sta dalla parte sbagliata: per un acquisto va sopra l'ingresso, per una vendita sotto"
    return EntrataDiRomeo(strumento, verso, ingresso, stop, target, quando)


def candidate(e: EntrataDiRomeo, seguite: list[Seguita]) -> list[Seguita]:
    """Le decisioni del bot sullo stesso strumento, nello stesso verso, nella finestra dell'entrata."""
    return [s for s in seguite if s.strumento == e.strumento and s.verso == e.verso
            and e.quando - PRIMA <= s.quando <= e.quando + DOPO]


def confronta(e: EntrataDiRomeo, seguite: list[Seguita]) -> Optional[Seguita]:
    """La decisione del bot piu' vicina al prezzo di Romeo; riempie `vista`, `distanza`, `pip` e `presa`."""
    c = candidate(e, seguite)
    if not c:
        e.vista = e.distanza = e.pip = None
        e.presa = False
        return None
    s = min(c, key=lambda s: abs(s.ingresso - e.ingresso))
    e.vista = s.chiave
    e.pip = abs(s.ingresso - e.ingresso) / PIP[e.strumento]
    e.distanza = abs(s.ingresso - e.ingresso) / e.rischio if e.rischio else None
    e.presa = s.entrata
    return s


def etichette(entrate: list[EntrataDiRomeo], seguite: list[Seguita]) -> tuple[list[Seguita], np.ndarray]:
    """Le decisioni dal vivo da quando l'utente manda le entrate di Romeo, e quali sono le sue scelte.

    Come per il 2023 (`nvm/prova/romeo.etichette`): per ogni sua entrata, la
    decisione piu' vicina al suo prezzo vale 1, tutte le altre 0.
    """
    if not entrate:
        return [], np.zeros(0, bool)
    inizio = min(e.quando for e in entrate) - PRIMA
    casi = [s for s in seguite if s.quando >= inizio]
    posto = {s.chiave: i for i, s in enumerate(casi)}
    y = np.zeros(len(casi), bool)
    for e in entrate:
        c = candidate(e, casi)
        if c:
            y[posto[min(c, key=lambda s: abs(s.ingresso - e.ingresso)).chiave]] = True
    return casi, y


def presa_vicina(e: EntrataDiRomeo, seguite: list[Seguita]) -> Optional[float]:
    """Quanto era vicina, in rischi di Romeo, l'operazione piu' vicina che il bot ha davvero preso."""
    prese = [s for s in candidate(e, seguite) if s.entrata]
    if not prese or not e.rischio:
        return None
    return min(abs(s.ingresso - e.ingresso) for s in prese) / e.rischio
