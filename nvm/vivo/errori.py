"""Gli errori che l'utente segnala al bot (`spec/romeo-dal-vivo.md`, "Gli errori").

Su uno dei canali del bot, rispondendo alla scheda della decisione o scrivendo
lo strumento:

    /errore USDJPY comprato contro una spinta forte

Il bot ritrova la decisione (quella a cui si risponde, o la piu' recente su
quello strumento nelle ultime 48 ore), dice in equipe chi aveva spinto per
entrare, e la conserva. Il sabato il Capo, riaddestrandosi, da' a quella
decisione il doppio del peso: e' esperienza che vale di piu'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from nvm.dati.minuti import PUNTO

if TYPE_CHECKING:
    from nvm.vivo.stato import Seguita

FINESTRA = 48 * 3600
PESO = 2.0
COMPRA = {"compra", "compro", "comprato", "acquisto", "buy", "long"}
VENDE = {"vende", "vendo", "venduto", "vendita", "sell", "short"}
FORMATO = "/errore USDJPY comprato contro una spinta forte (oppure rispondi alla scheda della decisione con /errore e il perché)"


@dataclass
class Errore:
    quando: int
    chiave: str
    strumento: str
    nota: str
    entrata: bool
    leggibile: str = ""


def _pulisci(testo: str) -> str:
    return re.sub(r"[^\w:./→-]+", " ", testo).lower().split()


def trova(testo: str, quando: int, seguite: list[Seguita], risposta_a: str = "") -> Errore | str:
    """La decisione a cui si riferisce l'errore, o il perche' non si trova."""
    parole = testo.split()
    if not parole or not re.fullmatch(r"/errore(@\w+)?", parole[0], re.IGNORECASE):
        return "non è un comando /errore"
    parole = parole[1:]
    candidate = []
    if risposta_a:
        # Si risponde alla scheda: la prima riga dice strumento, verso, coppia e ora.
        testa = _pulisci(risposta_a.splitlines()[0]) if risposta_a.strip() else []
        candidate = [s for s in seguite if s.leggibile and set(_pulisci(s.leggibile)) <= set(testa)]
    strumento = next((p.upper() for p in parole if p.upper() in PUNTO), None)
    verso = next(("long" if p.lower() in COMPRA else "short" for p in parole if p.lower() in COMPRA | VENDE), None)
    if not candidate:
        if strumento is None:
            return f"non so a quale decisione ti riferisci: scrivi lo strumento. Esempio: {FORMATO}"
        candidate = [s for s in seguite if s.strumento == strumento and quando - FINESTRA <= s.quando <= quando
                     and (verso is None or s.verso == verso)]
    if not candidate:
        return f"nessuna mia decisione su {strumento} nelle ultime 48 ore"
    s = max(candidate, key=lambda x: x.quando)
    nota = " ".join(p for p in parole if p.upper() != s.strumento) or "senza spiegazione"
    return Errore(quando, s.chiave, s.strumento, nota, s.entrata, s.leggibile or s.chiave)


def pesi(seguite: list[Seguita], errori: list[Errore]) -> list[float]:
    """Il peso di ogni decisione nel riaddestramento: doppio per quelle segnalate come errore."""
    segnate = {e.chiave for e in errori}
    return [PESO if s.chiave in segnate else 1.0 for s in seguite]
