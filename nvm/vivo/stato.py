"""Quello che il bot ricorda fra un riavvio e l'altro, in `dati/vivo/`.

- `stato.json`: l'ultimo giro fatto, l'ora del server, le operazioni aperte,
  le decisioni seguite sulla carta;
- `registro.jsonl`: ogni decisione, apertura e chiusura, una riga per
  evento. Non si cancella mai: e' da qui che l'equipe impara, anche dalle
  operazioni non aperte;
- `seguite_finite.jsonl`: le decisioni finite da piu' di due settimane, una per
  riga. Nello stato restano solo le recenti: con tanti strumenti lo stato, che
  si salva ogni minuto, diventerebbe troppo grande. La riunione le rilegge;
- `capo.json`: il Capo in uso, riaddestrato ogni fine settimana.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from nvm.vivo.esecutore import Viva
from nvm.vivo.romeo_vivo import EntrataDiRomeo


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
    # Le uscite con cui e' stata decisa (le manopole dei Livelli e del Grilletto in quel momento).
    pareggio_a: float = 1.0
    livello: Optional[float] = None
    invalida_candele: int = 0
    tempo_candele: int = 0
    # Per rifarla con altre scelte dei Livelli (`nvm/vivo/autoanalisi.py`): il CRT, l'estremo della
    # manipolazione, e lo stop minimo e il secondo obiettivo in uso quando si e' decisa.
    crt_alto: Optional[float] = None
    crt_basso: Optional[float] = None
    estremo: Optional[float] = None
    stop_minimo: Optional[float] = None
    oltre: Optional[float] = None
    # La qualita' attesa e la decisione del Capo (entrare o no), anche se poi l'ordine non e' partito.
    qualita: Optional[float] = None
    decisa: Optional[bool] = None
    # I cervelli degli agenti su questa occasione: cosa vedevano, il primo giudizio, quello dopo
    # il confronto, chi ha convinto chi, e la fiducia della squadra (`nvm/cervello/`).
    cervelli: Optional[dict] = None
    # Quanta parte al primo obiettivo (1 tutto, 0 niente: tutto al secondo) e se c'e' il pareggio.
    parziale: float = 0.5
    pareggio: bool = True

    @property
    def presa_dal_capo(self) -> bool:
        return self.decisa if self.decisa is not None else self.atteso > 0


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
    # Sotto "alternative": per agente e scelta vicina, come sarebbero finite le operazioni con quella.
    diario: dict = field(default_factory=dict)
    # L'ultimo quarto d'ora guardato per la coppia 4 ore -> 15 minuti.
    ultimo_quarto: Optional[int] = None
    # Le entrate di Romeo mandate dall'utente col comando /romeo (`nvm/vivo/romeo_vivo.py`).
    romeo: list[EntrataDiRomeo] = field(default_factory=list)
    # Il primo messaggio di Telegram ancora da leggere.
    telegram_dal: int = 0
    # L'ultimo allenamento degli agenti gia' raccontato in equipe (`nvm/vivo/allenamento.json`).
    ultimo_allenamento: str = ""
    # L'ultima volta che i cervelli si sono modificati da soli, gia' raccontata in equipe.
    ultima_evoluzione: str = ""
    # Il giorno (a New York) dell'ultimo riepilogo della sera, e le lezioni raccolte da allora:
    # "agente: «scelta»" -> quante volte avrebbe fatto meglio.
    ultimo_riepilogo: str = ""
    lezioni: dict = field(default_factory=dict)
    # Le operazioni che il Capo voleva ma non si sono aperte, dall'ultimo riepilogo: perche' -> quante.
    saltate: dict = field(default_factory=dict)
    # Le operazioni chiuse sul conto dall'ultimo riepilogo: [quando, R vero].
    chiuse: list = field(default_factory=list)
    # La settimana dell'ultima domenica di Romeo (V14) gia' fatta, e le previsioni di quella domenica.
    ultima_domenica: str = ""
    previsioni: dict = field(default_factory=dict)
    # Dall'ultimo riepilogo: quale regola di Romeo mancava alle occasioni guardate -> quante volte.
    mancanze: dict = field(default_factory=dict)

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
            romeo=[EntrataDiRomeo(**e) for e in d.get("romeo", [])], telegram_dal=d.get("telegram_dal", 0),
            ultimo_allenamento=d.get("ultimo_allenamento", ""), ultima_evoluzione=d.get("ultima_evoluzione", ""),
            ultimo_riepilogo=d.get("ultimo_riepilogo", ""), lezioni=d.get("lezioni", {}),
            saltate=d.get("saltate", {}), chiuse=d.get("chiuse", []),
            ultima_domenica=d.get("ultima_domenica", ""), previsioni=d.get("previsioni", {}),
            mancanze=d.get("mancanze", {}),
        )

    def salva(self, cartella: Path) -> None:
        cartella.mkdir(parents=True, exist_ok=True)
        tmp = cartella / "stato.json.tmp"
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(cartella / "stato.json")


ARCHIVIO = "seguite_finite.jsonl"


def archivia(cartella: Path, seguite: list[Seguita]) -> None:
    """Le decisioni finite escono dallo stato e vanno nell'archivio, una per riga."""
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / ARCHIVIO, "a", encoding="utf-8") as f:
        for s in seguite:
            f.write(json.dumps(asdict(s), ensure_ascii=False, separators=(",", ":")) + "\n")


def archiviate(cartella: Path, dal: int = 0) -> list[Seguita]:
    """Le decisioni dell'archivio finite da `dal` in poi."""
    p = cartella / ARCHIVIO
    if not p.exists():
        return []
    campi = set(Seguita.__dataclass_fields__)
    fuori = []
    for riga in p.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        d = json.loads(riga)
        if d.get("esito") and d["esito"]["quando"] >= dal:
            fuori.append(Seguita(**{k: v for k, v in d.items() if k in campi}))
    return fuori


def registra(cartella: Path, evento: str, **dati) -> None:
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "registro.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"evento": evento, **dati}, ensure_ascii=False, default=float) + "\n")
