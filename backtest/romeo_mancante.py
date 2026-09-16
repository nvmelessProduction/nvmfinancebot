"""Le otto regole di Romeo che mancavano, misurate.

`docs/BIBBIA-CRT.md` le elencava come ASSENTI o CONTRARIE. Ora sono scritte in
`core/`, e scritte non basta: questo modulo le mette alla prova sui prezzi
veri Dukascopy, con BID e ASK, ciascuna contro il proprio placebo.

## Il metodo, che e' sempre lo stesso

Per ogni regola si misura **il CRT base** e **il CRT piu' quella regola**. Se
il secondo non batte il primo, la regola non serve — per quanto autorevole sia
chi la scrive. E ogni misura porta il proprio σ contro un placebo con la
stessa geometria: un numero senza placebo non e' una misura, ed e' cosi' che
sono nati quattro falsi positivi in questa stessa cartella.

## Cosa NON si misura qui

L'esito non e' il rendimento del bot: e' l'esito di un'operazione mandata al
mercato con stop all'estremo di N2 e bersaglio al 50% del range di N1, i
livelli che GEST-02 e GEST-07 prescrivono. Nessun costo, perche' qui si
confrontano regole fra loro e il costo e' lo stesso per tutte. I costi veri
stanno in `docs/MISURA-DEFINITIVA-2026-09-16.md` e vanno sottratti a parte.
"""
from __future__ import annotations

import math
import pickle
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from core.definizioni import (
    Bias, Candela, cisd, divergenza_smt, double_purge, meta_tenuta,
    peso_ombre, verso_del_double_purge,
)
from core.parametri import COMPAGNE_SMT, TF

CACHE = Path("duka_serie.pickle")


# ---------------------------------------------------------------------------
# Il CRT base, identico per tutte le prove
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Segnale:
    """Un CRT trovato, con tutto cio' che serve a giudicarlo dopo."""

    indice: int          # posizione di N2 nella serie del timeframe alto
    direzione: Bias
    ingresso: float
    stop: float
    bersaglio: float
    n1: Candela
    n2: Candela


def cerca(alte: Sequence[Candela]) -> list[Segnale]:
    """Il CRT canonico a due candele: N2 spazza un estremo di N1 e richiude.

    Stop all'estremo di N2 (GEST-02), bersaglio al 50% di N1 (GEST-07).
    L'ingresso e' la chiusura di N2: e' il primo prezzo disponibile dopo che
    il pattern e' completo, e non richiede di indovinare nulla.
    """
    fuori: list[Segnale] = []
    for i in range(1, len(alte)):
        n1, n2 = alte[i - 1], alte[i]
        meta = (n1.massimo + n1.minimo) / 2
        dentro = n1.minimo <= n2.chiusura <= n1.massimo
        if not dentro:
            continue
        # La chiusura di N2 deve lasciare STRADA fino al bersaglio: per uno
        # short sopra il 50%, per un long sotto. Chiedere il contrario
        # selezionerebbe i CRT il cui bersaglio e' gia' stato superato, che e'
        # l'errore che in `canonico.py` produsse un falso "+19,9σ, 81%
        # winrate": il simulatore li chiudeva in profitto sulla barra di
        # ingresso, contando vittorie che il mercato non aveva pagato.
        if n2.massimo > n1.massimo and n2.chiusura > meta:
            fuori.append(Segnale(i, Bias.SHORT, n2.chiusura, n2.massimo, meta, n1, n2))
        elif n2.minimo < n1.minimo and n2.chiusura < meta:
            fuori.append(Segnale(i, Bias.LONG, n2.chiusura, n2.minimo, meta, n1, n2))
    return fuori


def risolvi(segnale: Segnale, seguito: Sequence[Candela], barre: int = 12) -> Optional[float]:
    """L'esito in R: +R al bersaglio, -1 allo stop, chiusura a tempo scaduto.

    Lo stop vince a parita' nella stessa barra: fra due letture possibili si
    sceglie la peggiore, perche' non sappiamo in che ordine il prezzo ci sia
    passato. E' lo stesso principio di `sentinella.livello_toccato`.

    `None` se il bersaglio e' gia' oltre l'ingresso alla partenza — l'errore
    che aveva prodotto un falso "+19,9σ, 81% winrate" in `canonico.py`, e che
    va escluso e non contato come vittoria.
    """
    rischio = abs(segnale.ingresso - segnale.stop)
    guadagno = abs(segnale.bersaglio - segnale.ingresso)
    if rischio <= 0 or guadagno <= 0:
        return None
    if segnale.direzione is Bias.SHORT and segnale.bersaglio >= segnale.ingresso:
        return None
    if segnale.direzione is Bias.LONG and segnale.bersaglio <= segnale.ingresso:
        return None

    erre = guadagno / rischio
    for barra in seguito[:barre]:
        if segnale.direzione is Bias.SHORT:
            if barra.massimo >= segnale.stop:
                return -1.0
            if barra.minimo <= segnale.bersaglio:
                return erre
        else:
            if barra.minimo <= segnale.stop:
                return -1.0
            if barra.massimo >= segnale.bersaglio:
                return erre
    if not seguito[:barre]:
        return None
    fine = seguito[min(barre, len(seguito)) - 1].chiusura
    segno = 1 if segnale.direzione is Bias.LONG else -1
    return segno * (fine - segnale.ingresso) / rischio


# ---------------------------------------------------------------------------
# Statistica
# ---------------------------------------------------------------------------
def sigma(risultati: Sequence[float]) -> float:
    """Quanti errori standard il rendimento medio dista da zero."""
    n = len(risultati)
    if n < 2:
        return 0.0
    media = sum(risultati) / n
    varianza = sum((x - media) ** 2 for x in risultati) / (n - 1)
    if varianza <= 0:
        return 0.0
    return media / math.sqrt(varianza / n)


def confronto(a: Sequence[float], b: Sequence[float]) -> float:
    """σ della differenza fra due medie indipendenti (Welch)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    denominatore = math.sqrt(va / len(a) + vb / len(b))
    if denominatore <= 0:
        return 0.0
    return (ma - mb) / denominatore


@dataclass
class Esito:
    nome: str
    n: int
    winrate: float
    erre: float
    sigma_zero: float
    sigma_vs_base: float

    def riga(self) -> str:
        return (f"{self.nome:<34} {self.n:>7}  {self.winrate:>5.1f}%  "
                f"{self.erre:>+7.3f}  {self.sigma_zero:>+6.1f}σ  "
                f"{self.sigma_vs_base:>+6.1f}σ")


def valuta(nome: str, risultati: Sequence[float], base: Sequence[float]) -> Esito:
    if not risultati:
        return Esito(nome, 0, 0.0, 0.0, 0.0, 0.0)
    vinti = sum(1 for x in risultati if x > 0)
    return Esito(
        nome, len(risultati), 100.0 * vinti / len(risultati),
        sum(risultati) / len(risultati), sigma(risultati),
        confronto(risultati, base) if base is not risultati else 0.0,
    )
