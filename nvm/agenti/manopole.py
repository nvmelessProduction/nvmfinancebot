"""Le manopole degli agenti: quello che ognuno puo' cambiare di se' da solo.

Ogni specialista ha le sue manopole: i numeri e le scelte che prima erano
scritti a mano (dove va lo stop, quali ore contano, quante candele si
guardano). Nessun recinto: l'utente, 25/09/2026, *"non dobbiamo limitarli
ne' dargli regole fisse, vanno addestrati"*. Ogni settimana l'allenamento
(`nvm/prova/allenamento.py`) prova a spostarle di un passo, in su o in giu',
e tiene quello che migliora le prestazioni. I soli confini sono quelli che
vengono dalla definizione (un'ora del giorno sta fra 0 e 24, una frazione
fra 0 e 1, un numero di candele e' almeno 1).

I valori in uso stanno in `nvm/vivo/agenti.json`, scritto dall'allenamento
settimanale; li applicano il bot dal vivo e gli script di misura (`applica`).
Senza file valgono quelli scritti nel codice.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

FILE = Path(__file__).resolve().parent.parent / "vivo" / "agenti.json"


@dataclass(frozen=True)
class Manopola:
    agente: str
    nome: str
    modulo: str
    attributo: str
    # "passo": un numero che si sposta di `passo`; "intero": di uno; "finestra": un intervallo
    # di ore [inizio, fine) che si allarga, si stringe o si sposta di un'ora; "scelta": una fra `scelte`.
    tipo: str
    perche: str
    passo: float = 0.0
    minimo: Optional[float] = None
    massimo: Optional[float] = None
    scelte: tuple = ()

    def leggi(self) -> Any:
        v = getattr(importlib.import_module(self.modulo), self.attributo)
        return v.value if hasattr(v, "value") else (list(v) if isinstance(v, tuple) else v)

    def scrivi(self, valore: Any) -> None:
        m = importlib.import_module(self.modulo)
        vecchio = getattr(m, self.attributo)
        if hasattr(vecchio, "value"):              # un Enum: si scrive col suo valore
            valore = type(vecchio)(valore)
        elif isinstance(vecchio, tuple):
            valore = tuple(valore)
        setattr(m, self.attributo, valore)

    def ammesso(self, v: Any) -> bool:
        """Solo i confini della definizione, nessun recinto."""
        if self.tipo == "scelta":
            return v in self.scelte
        if self.tipo == "finestra":
            return isinstance(v, (list, tuple)) and len(v) == 2 and 0 <= v[0] < v[1] <= 24
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return False
        if self.tipo == "intero" and int(v) != v:
            return False
        return (self.minimo is None or v >= self.minimo) and (self.massimo is None or v <= self.massimo)

    def vicini(self, valore: Any) -> list:
        """Un passo in ogni direzione da quello in uso: si cresce piano, ma senza recinto."""
        if self.tipo == "scelta":
            prossimi = [c for c in self.scelte if c != valore]
        elif self.tipo == "finestra":
            a, b = valore
            prossimi = [[a - 1, b], [a + 1, b], [a, b - 1], [a, b + 1]]
        elif self.tipo == "intero":
            prossimi = [valore - 1, valore + 1]
        else:
            prossimi = [round(valore - self.passo, 4), round(valore + self.passo, 4)]
        return [v for v in prossimi if self.ammesso(v)]


MANOPOLE: tuple[Manopola, ...] = (
    Manopola("Cacciatore", "variante", "nvm.agenti.cacciatore", "VARIANTE", "scelta",
             "come si arma un CRT: alla presa del lato (manuale) o quando la candela 2 richiude dentro",
             scelte=("manuale", "chiusura dentro")),
    Manopola("Grilletto", "colpi", "nvm.prova.base", "COLPI_PER_CRT", "intero",
             "quante volte riprova sullo stesso CRT dopo uno stop; Romeo: 'third tap+ is the highest probability'",
             minimo=1),
    Manopola("Grilletto", "lato della liquidità", "nvm.agenti.conferme", "LATO_LIQUIDITA", "intero",
             "quante candele per lato fanno un massimo di swing da prendere prima della manipolazione", minimo=1),
    Manopola("Grilletto", "invalidazione", "nvm.agenti.livelli", "INVALIDAZIONE", "intero",
             "dopo quante candele basse di fila chiuse oltre il livello del Model#1, dalla parte sbagliata, "
             "l'idea non vale piu' e si esce (0 = mai); Romeo: 'turtle soup high has to be the ceiling'", minimo=0),
    Manopola("Livelli", "tempo", "nvm.agenti.livelli", "TEMPO", "passo",
             "entro quante candele basse deve arrivare il primo obiettivo, se no si esce (0 = mai); "
             "Romeo: 'when you're right, trade will be over very quick'", passo=8, minimo=0),
    Manopola("Livelli", "secondo obiettivo oltre il lato", "nvm.agenti.livelli", "OLTRE", "passo",
             "quanto oltre il lato opposto del CRT, in ampiezze del CRT; Romeo: 'CRTH/L', ma i suoi target arrivano a 1,8 volte il range",
             passo=0.25, minimo=0.0),
    Manopola("Livelli", "pareggio", "nvm.agenti.livelli", "PAREGGIO", "passo",
             "a che punto del cammino verso il primo obiettivo lo stop va a pareggio: 1 = al primo obiettivo",
             passo=0.25, minimo=0.25),
    Manopola("Livelli", "stop minimo", "nvm.agenti.livelli", "STOP_MINIMO", "passo",
             "lo stop mai piu' vicino all'ingresso di questa frazione del range; Romeo: 25%", passo=0.05, minimo=0.0),
    Manopola("Key level", "candele guardate", "nvm.agenti.conferme", "QUANTE", "passo",
             "quante candele del timeframe sopra guarda per trovare i livelli", passo=6, minimo=6),
    Manopola("Key level", "vicinanza", "nvm.agenti.conferme", "TOLLERANZA", "passo",
             "entro quale frazione del range la manipolazione 'arriva' a un livello (msg 6718)", passo=0.05, minimo=0.0),
    Manopola("Key level", "lato dello swing", "nvm.agenti.conferme", "LATO_SWING", "intero",
             "quante candele per lato fanno un massimo di swing sul timeframe sopra", minimo=1),
    Manopola("Orario", "ora di Londra", "nvm.agenti.conferme", "LONDRA", "finestra",
             "le ore di New York che contano come 'Londra' di Romeo (msg 772: 3-5am)"),
    Manopola("Orario", "ora di New York", "nvm.agenti.conferme", "NEW_YORK", "finestra",
             "le ore di New York che contano come 'New York' di Romeo (msg 772: 930; GCT 9-13, msg 6110)"),
    Manopola("Bias", "sconto", "nvm.agenti.conferme", "SCONTO", "passo",
             "sotto quale frazione della settimana prima un acquisto e' 'a sconto'; Romeo: 50% = equilibrio",
             passo=0.1, minimo=0.1, massimo=0.9),
)

AGENTI = tuple(dict.fromkeys(m.agente for m in MANOPOLE))


def di(agente: str) -> list[Manopola]:
    return [m for m in MANOPOLE if m.agente == agente]


def trova(agente: str, nome: str) -> Manopola:
    return next(m for m in MANOPOLE if m.agente == agente and m.nome == nome)


def attuali() -> dict[str, dict[str, Any]]:
    """I valori in uso adesso, per agente."""
    return {a: {m.nome: m.leggi() for m in di(a)} for a in AGENTI}


def applica(valori: dict[str, dict[str, Any]]) -> None:
    """Mette in uso i valori; ignora quelli che non hanno senso o di manopole che non esistono piu'."""
    for agente, per in valori.items():
        for nome, v in per.items():
            try:
                m = trova(agente, nome)
            except StopIteration:
                continue
            if m.ammesso(v):
                m.scrivi(v)


def leggi(percorso: Path = FILE) -> dict[str, dict[str, Any]]:
    if not percorso.exists():
        return {}
    return json.loads(percorso.read_text(encoding="utf-8")).get("manopole", {})


def salva(valori: dict[str, dict[str, Any]], percorso: Path = FILE) -> None:
    percorso.write_text(json.dumps({"manopole": valori}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def carica_e_applica(percorso: Path = FILE) -> dict[str, dict[str, Any]]:
    """Quello che fanno il bot e gli script all'avvio: le manopole scelte dall'allenamento."""
    applica(leggi(percorso))
    return attuali()


def impronta(valori: dict[str, dict[str, Any]] | None = None) -> str:
    """Un nome corto per un insieme di valori: le tabelle salvate lo portano nel nome."""
    import hashlib
    testo = json.dumps(attuali() if valori is None else valori, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(testo.encode("utf-8")).hexdigest()[:8]
