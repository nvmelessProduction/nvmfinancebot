"""Quello che il bot ricorda fra un riavvio e l'altro, in `dati/vivo/`.

- `stato.json`: l'ultimo giro fatto, l'ora del server, le operazioni aperte,
  le decisioni seguite sulla carta;
- `registro.jsonl`: ogni decisione, apertura e chiusura, una riga per
  evento. Non si cancella mai: e' da qui che l'equipe impara, anche dalle
  operazioni non aperte;
- `capo.json`: il Capo in uso, riaddestrato ogni fine settimana.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from nvm.vivo.esecutore import Viva


@dataclass
class Seguita:
    """Una decisione seguita sulla carta fino alla fine, presa o no."""

    chiave: str
    strumento: str
    alto: str
    basso: str
    verso: str
    quando: int
    ingresso: float
    stop: float
    tp1: float
    tp2: float
    scadenza: int
    entrata: bool
    x: list[float]
    rr1: float
    rr2: float
    costi: float
    p1: float
    q: float
    atteso: float
    # Riempiti quando finisce: uscita, R, primo target preso, secondo preso, quando.
    esito: Optional[dict] = None
    # Quanto ogni agente spingeva a entrare (sopra zero) o frenava, quando si e' deciso.
    spinte: dict = field(default_factory=dict)
    # Come la si chiama nei messaggi: "EURUSD SHORT, giornaliero → 1 ora, 09/09 03:00 NY".
    leggibile: str = ""
    # Quanto somigliava a un'entrata di Romeo, per il Capo (`spec/capo.md`).
    romeo: float = 1.0


@dataclass
class Stato:
    ultimo_giro: Optional[int] = None
    scarto: Optional[int] = None
    vive: list[Viva] = field(default_factory=list)
    seguite: list[Seguita] = field(default_factory=list)
    ultima_riunione: str = ""
    # Per agente: [volte che aveva ragione, volte che si era schierato].
    pagelle: dict = field(default_factory=dict)
    # Per agente e per segnale dato: [vinte, totali] dal vivo. Serve a capire dove migliorare.
    diario: dict = field(default_factory=dict)
    # L'ultimo quarto d'ora guardato per la coppia 4 ore -> 15 minuti.
    ultimo_quarto: Optional[int] = None

    @classmethod
    def carica(cls, cartella: Path) -> "Stato":
        p = cartella / "stato.json"
        if not p.exists():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            ultimo_giro=d.get("ultimo_giro"), scarto=d.get("scarto"),
            vive=[Viva(**v) for v in d.get("vive", [])],
            seguite=[Seguita(**s) for s in d.get("seguite", [])],
            ultima_riunione=d.get("ultima_riunione", ""),
            pagelle=d.get("pagelle", {}), diario=d.get("diario", {}), ultimo_quarto=d.get("ultimo_quarto"),
        )

    def salva(self, cartella: Path) -> None:
        cartella.mkdir(parents=True, exist_ok=True)
        tmp = cartella / "stato.json.tmp"
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(cartella / "stato.json")


def registra(cartella: Path, evento: str, **dati) -> None:
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "registro.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"evento": evento, **dati}, ensure_ascii=False, default=float) + "\n")
