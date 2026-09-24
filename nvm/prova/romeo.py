"""Le entrate di Romeo contro i prezzi veri e contro il bot.

Il metro del `PIANO.md` (il cambio del 24/09/2026): il bot deve fare le
entrate che farebbe Romeo. Il catalogo e' `casi/entrate-romeo.csv`, letto
dalle foto del suo canale: ogni riga dice lo strumento, il verso, la finestra
in cui Romeo e' entrato e i prezzi che si leggono (ingresso, stop, target),
quando si leggono. Gli orari sono quelli del suo server MT5, che segna New
York + 7 ore: lo si vede dal CPI del 12/12/2023, che sul suo grafico cade
alle 15:30.

Qui si fanno quattro cose:

1. `al_prezzo`: la lettura regge? Nella finestra il prezzo e' passato
   davvero dall'ingresso letto? Se no, la riga e' letta male.
2. `esito`: dopo l'ingresso e' arrivato prima il target o lo stop? Solo per
   il periodo di studio: il 2024-2026 resta chiuso fino alla Fase G.
3. `armati`: il Cacciatore vedeva un CRT armato nello stesso verso mentre
   Romeo entrava?
4. `ritrovata`: il bot ha fatto la stessa entrata? Stesso strumento, stesso
   verso, ingresso nella finestra di Romeo, e prezzo entro meta' del suo
   rischio (la soglia del `PIANO.md`).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import CRT, Verso, caccia
from nvm.agenti.capo import COLONNE, riga
from nvm.agenti.conferme import SOPRA, Grandi, tutti_i_pareri
from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import MASSIMO, MINIMO, Minuti
from nvm.prova.base import Risultato, opera
from nvm.tempo import NEW_YORK, TF

# L'ora del server di Romeo: New York + 7 ore, estate e inverno.
SCARTO_SERVER = timedelta(hours=7)
# Quanto possono differire i prezzi del broker di Romeo da quelli di
# Dukascopy: poco piu' di un pip sulle valute, mezzo dollaro sull'oro.
TOLLERANZA = {
    "EURUSD": 0.00015, "GBPUSD": 0.00015, "AUDUSD": 0.00015, "USDCHF": 0.00015,
    "USDJPY": 0.015, "XAUUSD": 0.6,
}
# L'esito si cerca al massimo per questo tempo dopo l'ingresso.
ORIZZONTE = 45 * 86400
# Il bot entra alla chiusura della candela che scatta: la sua entrata conta
# anche se cade fino a una candela bassa dopo la finestra di Romeo.
PASSO_BASSO = {TF.M15: 900, TF.H1: 3600, TF.H4: 4 * 3600, TF.D1: 86400}
# Meta' del rischio di Romeo: la soglia del PIANO.md.
META_RISCHIO = 0.5
# Le coppie del bot dal vivo: tre sulle ore, e il 4 ore -> 15 minuti dove ci sono i minuti.
COPPIE_ORE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
COPPIA_MINUTI = (TF.H4, TF.M15)


@dataclass
class Entrata:
    id: str
    periodo: str
    strumento: str
    verso: Verso
    tipo: str
    dal: int
    al: int
    ingresso: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    tf: str
    esito_romeo: str
    caso: str
    foto: str
    note: str

    @property
    def rischio(self) -> Optional[float]:
        if self.ingresso is None or self.stop is None:
            return None
        return abs(self.ingresso - self.stop)


def server_a_utc(testo: str) -> int:
    """'2024-03-29 16:30' sul server di Romeo -> istante UTC."""
    ny = datetime.strptime(testo, "%Y-%m-%d %H:%M") - SCARTO_SERVER
    return int(ny.replace(tzinfo=NEW_YORK).timestamp())


def _numero(testo: str) -> Optional[float]:
    return float(testo) if testo.strip() else None


def leggi(percorso: Path) -> list[Entrata]:
    with open(percorso, newline="", encoding="utf-8") as f:
        return [
            Entrata(
                r["id"], r["periodo"], r["strumento"], Verso(r["verso"].lower()), r["tipo"],
                server_a_utc(r["dal"]), server_a_utc(r["al"]) + 60,
                _numero(r["ingresso"]), _numero(r["stop"]), _numero(r["target"]),
                r["tf"], r["esito_romeo"], r["caso"], r["foto"], r["note"],
            )
            for r in csv.DictReader(f)
        ]


def _nella_finestra(e: Entrata, ore: Candele) -> slice:
    """Le candele che si sovrappongono alla finestra di Romeo."""
    i = int(np.searchsorted(ore.fine, e.dal, side="right"))
    j = int(np.searchsorted(ore.inizio, e.al, side="left"))
    return slice(i, j)


def al_prezzo(e: Entrata, ore: Candele) -> Optional[int]:
    """L'inizio della prima candela della finestra che passa dall'ingresso
    letto, o None se il prezzo non ci e' mai passato (la riga e' letta male)."""
    if e.ingresso is None:
        return None
    tol = TOLLERANZA[e.strumento]
    f = _nella_finestra(e, ore)
    basso = ore.bid[f, MINIMO] - tol
    alto = ore.ask[f, MASSIMO] + tol
    dentro = np.flatnonzero((basso <= e.ingresso) & (e.ingresso <= alto))
    return int(ore.inizio[f][dentro[0]]) if dentro.size else None


def esito(e: Entrata, ore: Candele, da: int) -> str:
    """'target', 'stop', 'incerto' o 'aperta' (nessuno dei due entro
    l'orizzonte), dalla candela che apre a `da`, quella dell'ingresso.

    'incerto' quando non si sa cosa e' venuto prima: stop e target nella
    stessa candela, o uno dei due gia' nella candela dell'ingresso, dove non
    si sa se il prezzo ci e' passato prima o dopo che Romeo entrasse. Con gli
    stop di 1-3 pip e le candele di un'ora succede spesso: li' serve il minuto.
    """
    if e.stop is None or e.target is None:
        return "senza prezzi"
    i = int(np.searchsorted(ore.inizio, da))
    j = int(np.searchsorted(ore.inizio, da + ORIZZONTE))
    long = e.verso is Verso.LONG
    # Lo stop di un long e il target di uno short si prendono in bid; gli
    # altri due in ask.
    for n in range(i, j):
        if long:
            preso_stop = ore.bid[n, MINIMO] <= e.stop
            preso_target = ore.bid[n, MASSIMO] >= e.target
        else:
            preso_stop = ore.ask[n, MASSIMO] >= e.stop
            preso_target = ore.ask[n, MINIMO] <= e.target
        if (preso_stop and preso_target) or (n == i and (preso_stop or preso_target)):
            return "incerto"
        if preso_stop:
            return "stop"
        if preso_target:
            return "target"
    return "aperta"


def armati(e: Entrata, crt: list[CRT]) -> list[CRT]:
    """I CRT nello stesso verso armati in qualche momento della finestra."""
    return [c for c in crt if c.verso is e.verso and c.armato_quando < e.al and c.decaduto_quando > e.dal]


@dataclass
class Confronto:
    operazione: Risultato
    # La distanza fra l'ingresso del bot e quello di Romeo, in rischi di
    # Romeo. None quando di Romeo non si legge lo stop.
    distanza: Optional[float]

    @property
    def ritrovata(self) -> bool:
        return self.distanza is not None and self.distanza <= META_RISCHIO


def confronta(e: Entrata, operazioni: list[Risultato]) -> list[Confronto]:
    """Le operazioni del bot nello stesso verso con ingresso nella finestra di
    Romeo, dalla piu' vicina al suo prezzo."""
    trovate = []
    for op in operazioni:
        if op.strumento != e.strumento or op.verso is not e.verso:
            continue
        if not (e.dal <= op.quando <= e.al + PASSO_BASSO[op.basso_tf]):
            continue
        r = e.rischio
        d = abs(op.ingresso - e.ingresso) / r if r else None
        trovate.append(Confronto(op, d))
    trovate.sort(key=lambda c: (c.distanza is None, c.distanza or 0.0))
    return trovate


def grandi(ore: Minuti, fine: int) -> Grandi:
    """I CRT delle coppie sulle ore, per la domanda "dentro un CRT piu' grande?"."""
    return Grandi.da([c for alto, basso in COPPIE_ORE
                      for c in caccia(costruisci(ore, alto).chiuse_entro(fine), costruisci(ore, basso).chiuse_entro(fine))])


def candidati(ore: Minuti, minuti: Minuti, dal: int, al: int) -> tuple[list[Risultato], np.ndarray]:
    """Le operazioni che il bot dal vivo avrebbe visto con ingresso in [dal, al),
    con le colonne del Capo. `minuti` puo' essere vuoto: allora niente 4 ore -> 15 minuti."""
    fine = int(ore.t[-1]) + ore.passo
    g = grandi(ore, fine)
    settimane = costruisci(ore, TF.W1).chiuse_entro(fine)
    coppie = [(alto, basso, ore) for alto, basso in COPPIE_ORE]
    if len(minuti):
        coppie.append((*COPPIA_MINUTI, minuti))
    ops, righe = [], []
    for alto, basso, dati in coppie:
        f = int(dati.t[-1]) + dati.passo
        alte, basse = costruisci(dati, alto).chiuse_entro(f), costruisci(dati, basso).chiuse_entro(f)
        sopra = costruisci(ore, SOPRA[alto]).chiuse_entro(fine)
        for r in opera(alte, basse, dal, al):
            ops.append(r)
            righe.append(riga(r, *tutti_i_pareri(r.scatto, alte, basse, sopra, settimane, g)))
    return ops, np.array(righe, dtype=float).reshape(len(ops), len(COLONNE))


def etichette(entrate: list[Entrata], operazioni: list[Risultato]) -> np.ndarray:
    """1 per il candidato che e' la scelta di Romeo (per ogni sua entrata, il piu'
    vicino al suo prezzo fra quelli nello stesso verso e nella sua finestra), 0 per gli altri."""
    y = np.zeros(len(operazioni), bool)
    posto = {id(o): i for i, o in enumerate(operazioni)}
    for e in entrate:
        c = confronta(e, operazioni)
        if c:
            y[posto[id(c[0].operazione)]] = True
    return y
