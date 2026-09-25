"""Le manopole degli agenti: quello che ognuno puo' cambiare di se' da solo.

Ogni specialista ha un mansionario: le sue manopole, e per ognuna i valori
ammessi, dentro i limiti scritti dalle fonti di Romeo. Fuori da li' non va,
anche se i numeri lo tentassero: uno stop "infinito", per esempio, non perde
quasi mai e non guadagna mai (`registro/tentativi.md`, 25/09/2026).

I valori in uso stanno in `nvm/vivo/agenti.json`, scritto dall'allenamento
settimanale (`nvm/prova/allenamento.py`); li applicano il bot dal vivo e gli
script di misura (`applica`). Senza file valgono quelli scritti nel codice.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE = Path(__file__).resolve().parent.parent / "vivo" / "agenti.json"


@dataclass(frozen=True)
class Manopola:
    agente: str
    nome: str
    modulo: str
    attributo: str
    # I valori ammessi, in ordine: l'allenamento prova i vicini di quello in uso.
    valori: tuple
    # Da dove vengono i limiti, e cosa vuol dire la manopola, in parole.
    perche: str

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

    def vicini(self, valore: Any) -> list:
        """I valori ammessi accanto a quello in uso: si cresce un passo alla volta."""
        v = list(self.valori)
        corrente = list(valore) if isinstance(valore, tuple) else valore
        if corrente not in v:
            return v
        i = v.index(corrente)
        return [v[j] for j in (i - 1, i + 1) if 0 <= j < len(v)]


MANOPOLE: tuple[Manopola, ...] = (
    Manopola("Cacciatore", "variante", "nvm.agenti.cacciatore", "VARIANTE", ("manuale", "chiusura dentro"),
             "come si arma un CRT: alla presa del lato (manuale) o quando la candela 2 richiude dentro"),
    Manopola("Grilletto", "colpi", "nvm.prova.base", "COLPI_PER_CRT", (1, 2, 3),
             "quante volte riprova sullo stesso CRT dopo uno stop; Romeo: 'third tap+ is the highest probability'"),
    Manopola("Grilletto", "lato della liquidità", "nvm.agenti.conferme", "LATO_LIQUIDITA", (1, 2, 3),
             "quante candele per lato fanno un massimo di swing da prendere prima della manipolazione"),
    Manopola("Livelli", "secondo obiettivo oltre il lato", "nvm.agenti.livelli", "OLTRE", (0.0, 0.25, 0.5, 0.75, 1.0),
             "quanto oltre il lato opposto del CRT, in ampiezze del CRT; Romeo: 'CRTH/L', ma i suoi target arrivano a 1,8 volte il range"),
    Manopola("Livelli", "stop minimo", "nvm.agenti.livelli", "STOP_MINIMO", (0.15, 0.2, 0.25, 0.33, 0.5),
             "lo stop mai piu' vicino di questa frazione del range; Romeo: 25%. Al massimo meta' range: oltre, le operazioni non si fermano piu' e scadono"),
    Manopola("Key level", "candele guardate", "nvm.agenti.conferme", "QUANTE", (12, 24, 48),
             "quante candele del timeframe sopra guarda per trovare i livelli"),
    Manopola("Key level", "vicinanza", "nvm.agenti.conferme", "TOLLERANZA", (0.05, 0.1, 0.2),
             "entro quale frazione del range la manipolazione 'arriva' a un livello (msg 6718)"),
    Manopola("Key level", "lato dello swing", "nvm.agenti.conferme", "LATO_SWING", (1, 2, 3),
             "quante candele per lato fanno un massimo di swing sul timeframe sopra"),
    Manopola("Orario", "ora di Londra", "nvm.agenti.conferme", "LONDRA", ([0, 4], [1, 4], [1, 5], [2, 5], [2, 6]),
             "le ore di New York che contano come 'Londra' di Romeo (msg 772: 3-5am)"),
    Manopola("Orario", "ora di New York", "nvm.agenti.conferme", "NEW_YORK", ([7, 10], [8, 11], [8, 12], [9, 12], [9, 13]),
             "le ore di New York che contano come 'New York' di Romeo (msg 772: 930; GCT 9-13, msg 6110)"),
    Manopola("Bias", "sconto", "nvm.agenti.conferme", "SCONTO", (0.3, 0.4, 0.5),
             "sotto quale frazione della settimana prima un acquisto e' 'a sconto'; Romeo: 50% = equilibrio"),
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
    """Mette in uso i valori; ignora quelli fuori dal mansionario o di manopole che non esistono piu'."""
    for agente, per in valori.items():
        for nome, v in per.items():
            try:
                m = trova(agente, nome)
            except StopIteration:
                continue
            if v in list(m.valori):
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
