"""L'intervallo di confidenza, ricampionando i BLOCCHI e non le righe.

## Perche' a blocchi

Il bootstrap ordinario ricampiona le righe una per una, e cosi' facendo
assume che siano indipendenti. Qui non lo sono: due CRT dello stesso
strumento le cui finestre di esito si sovrappongono vivono lo stesso
movimento, vincono insieme e perdono insieme.

Assumere un'indipendenza che non c'e' **restringe** l'intervallo. Non lo
allarga: lo restringe. Cioe' produce esattamente l'errore che fa piu' danno --
dichiarare significativo un vantaggio che non lo e', e mandarlo a operare.

`backtest/campione_efficace.py` ha gia' fatto il lavoro: ogni riga porta
l'etichetta del blocco a cui appartiene. Qui i blocchi si pescano interi.

## Cosa significa il numero che esce

`(basso, alto)` al 95%: se si rifacesse l'esperimento molte volte, il vero
valore starebbe li' dentro il 95% delle volte. Il protocollo chiede che
**l'intervallo escluda lo zero**, non che il centro sia positivo -- e sono
due cose molto diverse quando l'errore e' dello stesso ordine del segnale,
come lo e' qui: B0 vale -0,0509 con un errore di 0,0162.

## Il seme

Fisso e dichiarato. Un bootstrap che da' risposte diverse ad ogni giro non e'
una misura: e' un modo di continuare a tirare finche' esce il numero che
piace.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional, Sequence

import numpy as np

# Quante volte si ricampiona. Duemila basta per un intervallo al 95%: il
# tremolio sui percentili e' sotto il millesimo di R, cioe' sotto la
# precisione con cui il numero viene poi letto.
GIRI: int = 2000

SEME: int = 20260924


def indici_per_blocco(blocchi: Sequence[str]) -> dict[str, list[int]]:
    """Quali righe appartengono a ciascun blocco."""
    fuori: dict[str, list[int]] = defaultdict(list)
    for indice, blocco in enumerate(blocchi):
        fuori[blocco].append(indice)
    return dict(fuori)


def intervallo(
    valori: Sequence[float],
    blocchi: Sequence[str],
    giri: int = GIRI,
    confidenza: float = 0.95,
    seme: int = SEME,
    statistica: Optional[Callable[[np.ndarray], float]] = None,
) -> tuple[float, float, float]:
    """`(punto, basso, alto)` della media, ricampionando i blocchi interi.

    Si pescano **tanti blocchi quanti ce ne sono**, con ripetizione, e si
    prendono tutte le righe di ciascuno. Un giro puo' quindi avere piu' o meno
    righe dell'originale: e' voluto, ed e' il modo in cui la dipendenza dentro
    il blocco entra nella dispersione invece di sparire.
    """
    valori = np.asarray(valori, dtype=float)
    if len(valori) != len(blocchi):
        raise ValueError(
            f"{len(valori)} valori e {len(blocchi)} etichette di blocco")
    if len(valori) == 0:
        raise ValueError("non si ricampiona niente su zero righe")
    calcola = statistica or (lambda v: float(np.mean(v)))

    gruppi = indici_per_blocco(blocchi)
    nomi = list(gruppi)
    righe_di = [np.asarray(gruppi[n], dtype=int) for n in nomi]

    punto = calcola(valori)
    caso = np.random.default_rng(seme)
    risultati = np.empty(giri, dtype=float)
    for giro in range(giri):
        scelti = caso.integers(0, len(nomi), size=len(nomi))
        righe = np.concatenate([righe_di[i] for i in scelti])
        risultati[giro] = calcola(valori[righe])

    coda = (1.0 - confidenza) / 2.0
    basso = float(np.quantile(risultati, coda))
    alto = float(np.quantile(risultati, 1.0 - coda))
    return punto, basso, alto


def esclude_lo_zero(basso: float, alto: float) -> bool:
    """L'intervallo sta tutto da una parte dello zero?

    E' la domanda del protocollo, ed e' piu' severa di "il centro e'
    positivo". Con un errore dello stesso ordine del segnale -- qui lo e' --
    la differenza fra le due e' la differenza fra una misura e un'illusione.
    """
    return (basso > 0.0) or (alto < 0.0)


def differenza(
    valori_a: Sequence[float], blocchi_a: Sequence[str],
    valori_b: Sequence[float], blocchi_b: Sequence[str],
    giri: int = GIRI, confidenza: float = 0.95, seme: int = SEME,
) -> tuple[float, float, float]:
    """`(punto, basso, alto)` di `media(a) - media(b)`, a blocchi.

    E' la forma che il protocollo chiede davvero: non "quanto rende la
    strategia" ma **quanto rende in piu' di `B0`**, con l'intervallo sulla
    differenza. L'intervallo della differenza non si ottiene sottraendo due
    intervalli: va ricampionato, perche' le due misure condividono i blocchi.

    I blocchi si pescano dall'unione, e ogni giro usa le stesse pescate per
    entrambe le serie: cosi' cio' che cambia fra `a` e `b` e' la selezione,
    non il campione.
    """
    valori_a = np.asarray(valori_a, dtype=float)
    valori_b = np.asarray(valori_b, dtype=float)
    gruppi_a = indici_per_blocco(blocchi_a)
    gruppi_b = indici_per_blocco(blocchi_b)
    nomi = sorted(set(gruppi_a) | set(gruppi_b))
    if not nomi:
        raise ValueError("nessun blocco da ricampionare")

    vuoto = np.zeros(0, dtype=int)
    righe_a = [np.asarray(gruppi_a.get(n, ()), dtype=int) for n in nomi]
    righe_b = [np.asarray(gruppi_b.get(n, ()), dtype=int) for n in nomi]
    righe_a = [r if r.size else vuoto for r in righe_a]
    righe_b = [r if r.size else vuoto for r in righe_b]

    def media(v: np.ndarray) -> float:
        return float(np.mean(v)) if len(v) else float("nan")

    punto = media(valori_a) - media(valori_b)
    caso = np.random.default_rng(seme)
    risultati = []
    for _ in range(giri):
        scelti = caso.integers(0, len(nomi), size=len(nomi))
        ia = np.concatenate([righe_a[i] for i in scelti]) if len(scelti) else vuoto
        ib = np.concatenate([righe_b[i] for i in scelti]) if len(scelti) else vuoto
        if len(ia) == 0 or len(ib) == 0:
            continue                      # un giro senza righe non dice nulla
        risultati.append(media(valori_a[ia]) - media(valori_b[ib]))
    if not risultati:
        raise ValueError("nessun giro utilizzabile: troppe poche righe")

    coda = (1.0 - confidenza) / 2.0
    fuori = np.asarray(risultati, dtype=float)
    return punto, float(np.quantile(fuori, coda)), float(
        np.quantile(fuori, 1.0 - coda))
