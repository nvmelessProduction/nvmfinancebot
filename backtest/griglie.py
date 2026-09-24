"""Cosa ogni agente prova a fare meglio, e su quale griglia.

## Tutti assunti lo stesso giorno

Ogni agente e' un neolaureato che parte dal manuale. Il manuale e' il valore
che il bot usa **adesso**, e sta nella griglia come uno dei candidati -- di
solito il primo. Se nessun altro candidato lo batte, il manuale resta, e
l'agente resta neolaureato.

Questo e' il motivo per cui si possono accendere tutti insieme senza rischio:
un agente che non impara niente non fa niente di nuovo.

## Ognuno nel suo ambito, e nessuno ottimizza per gli altri

Ogni agente muove **il suo** numero, con quelli degli altri fermi al
predefinito. Non si cerca la combinazione migliore di tutti i numeri insieme,
e non e' pigrizia:

- una ricerca congiunta su quattro griglie da cinque valori prova 625
  combinazioni, e su 16.463 casi la migliore di 625 sembra ottima **per
  caso**. E' il modo piu' rapido di fabbricare il sesto falso positivo;
- e non e' quello che si e' chiesto. L'economista migliora il suo lavoro, non
  la strategia dell'azienda.

Quando un agente avra' fatto carriera, il suo numero nuovo diventa il
predefinito degli altri, e al giro dopo ognuno rimisura nel mondo cambiato.
Si cresce a turni, non tutti insieme sullo stesso campione.

## Cosa NON c'e' qui

Non c'e' il modello centrale. Quello impara di chi fidarsi fra i pareri, ed e'
un'altra domanda -- sta in `core/pesi.py` e in `backtest/addestra.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cammino import (                                          # noqa: E402
    FRAZIONE_PARZIALE, K_DI_OGGI, EsitoGestito, esito_gestito,
)

from core.apprendimento import Competenza, dichiara            # noqa: E402
from core.definizioni import Bias, Candela                     # noqa: E402


# ===========================================================================
# Le competenze dichiarate
# ===========================================================================
#
# Ognuna dichiara: chi impara, cosa, su cosa si misura, da dove vengono i dati,
# qual e' il manuale, e quanto deve guadagnare per meritare la promozione.

PAREGGIO = dichiara(Competenza(
    agente="sentinella.pareggio",
    domanda="dove mettere lo stop del 75% residuo dopo il parziale",
    bersaglio="R medio dell'operazione gestita",
    fonte="i cammini del campo di prova, uno per CRT che arriva a TP1",
    predefinito=K_DI_OGGI,
    campioni_minimi=300,
    guadagno_minimo=0.05,
))

PARZIALE = dichiara(Competenza(
    agente="sentinella.parziale",
    domanda="quanta posizione chiudere a TP1",
    bersaglio="R medio dell'operazione gestita",
    fonte="gli stessi cammini",
    predefinito=FRAZIONE_PARZIALE,
    campioni_minimi=300,
    guadagno_minimo=0.05,
))

STOP = dichiara(Competenza(
    agente="livelli.stop",
    domanda="quanto lasciare lo stop oltre l'estremo di N2",
    bersaglio="R medio dell'operazione gestita",
    fonte="gli stessi cammini, con il rischio ricalcolato",
    predefinito=1.0,
    campioni_minimi=300,
    guadagno_minimo=0.05,
))

BERSAGLIO = dichiara(Competenza(
    agente="livelli.tp1",
    domanda="a che frazione del range mettere TP1",
    bersaglio="R medio dell'operazione gestita",
    fonte="gli stessi cammini",
    predefinito=0.50,
    campioni_minimi=300,
    guadagno_minimo=0.05,
))


@dataclass(frozen=True)
class Griglia:
    """I candidati di un agente, e come si simula ciascuno."""

    competenza: Competenza
    valori: tuple[float, ...]
    # Il prefisso delle colonne nel campo di prova.
    colonna: str

    def nome_colonna(self, valore: float) -> str:
        return f"{self.colonna}{valore:.2f}"

    def tutte_le_colonne(self) -> tuple[str, ...]:
        return tuple(self.nome_colonna(v) for v in self.valori)


GRIGLIE: tuple[Griglia, ...] = (
    Griglia(PAREGGIO, (0.00, 0.25, 0.50, 0.75, 1.00), "pareggio_k"),
    Griglia(PARZIALE, (0.00, 0.25, 0.50, 0.75, 1.00), "parziale_f"),
    Griglia(STOP, (1.00, 1.25, 1.50, 2.00), "stop_m"),
    Griglia(BERSAGLIO, (0.25, 0.50, 0.75), "tp1_f"),
)


def colonne_delle_griglie() -> tuple[str, ...]:
    """Tutte le colonne che le griglie aggiungono al campo di prova."""
    fuori: list[str] = []
    for g in GRIGLIE:
        fuori.extend(g.tutte_le_colonne())
    return tuple(fuori)


# ===========================================================================
# Come si sposta ciascun numero
# ===========================================================================


def stop_scalato(ingresso: float, stop: float, moltiplicatore: float) -> float:
    """Lo stop allontanato di un fattore dall'ingresso.

    `1.0` e' l'estremo di N2, cioe' `GEST-02` come sta scritta. Valori piu'
    alti lasciano piu' spazio al rumore e costano di piu' quando si sbaglia:
    e' un baratto, e per questo va misurato e non scelto.

    Stessa forma di `cammino.stop_del_residuo`: si interpola dall'ingresso,
    quindi il verso viene da solo e non c'e' un ramo per le long e uno per le
    short dove il segno puo' invertirsi di nascosto.
    """
    return ingresso + moltiplicatore * (stop - ingresso)


def tp1_alla_frazione(n1: Candela, verso: Bias, frazione: float) -> float:
    """TP1 a una frazione del range di N1, invece che al 50%.

    `0.50` e' `CRT-16` e `GEST-07` come stanno scritte. La frazione si conta
    dal lato da cui il prezzo viene: per una long dal minimo verso l'alto,
    per una short dal massimo verso il basso. A `0.50` le due coincidono,
    come devono.
    """
    ampiezza = n1.massimo - n1.minimo
    if verso is Bias.SHORT:
        return n1.massimo - frazione * ampiezza
    return n1.minimo + frazione * ampiezza


def simula(
    griglia: Griglia,
    valore: float,
    n1: Candela,
    ingresso: float,
    stop: float,
    tp1: float,
    target_finale: float,
    verso: Bias,
    successive: Sequence[Candela],
    barre_massime: int,
    costo_per_lato: float,
) -> Optional[EsitoGestito]:
    """Come sarebbe finita con QUESTO valore, e gli altri al predefinito.

    Il costo resta quello misurato: cambiare la gestione non cambia lo spread
    ne' la commissione, e fingere che lo faccia sarebbe il modo piu' comodo
    per far sembrare buona una griglia.
    """
    nome = griglia.competenza.agente
    k = K_DI_OGGI
    frazione = FRAZIONE_PARZIALE

    if nome == PAREGGIO.agente:
        k = valore
    elif nome == PARZIALE.agente:
        frazione = valore
    elif nome == STOP.agente:
        stop = stop_scalato(ingresso, stop, valore)
    elif nome == BERSAGLIO.agente:
        tp1 = tp1_alla_frazione(n1, verso, valore)
    else:
        raise ValueError(f"griglia senza simulazione: {nome}")

    return esito_gestito(
        ingresso=ingresso, stop=stop, tp1=tp1, target_finale=target_finale,
        verso=verso, successive=successive, barre_massime=barre_massime,
        costo_per_lato=costo_per_lato, k=k, frazione=frazione)


def tutte_le_simulazioni(
    n1: Candela, ingresso: float, stop: float, tp1: float,
    target_finale: float, verso: Bias, successive: Sequence[Candela],
    barre_massime: int, costo_per_lato: float,
) -> dict[str, Optional[float]]:
    """Gli R di ogni candidato di ogni agente, per un CRT solo.

    `None` dove la simulazione non e' misurabile: un TP1 al 25% del range puo'
    cadere dietro l'ingresso, e li' non c'e' un'operazione da misurare. Si
    lascia vuoto invece di mettere zero -- uno zero sarebbe un pareggio, e un
    pareggio non e' "non misurabile".
    """
    fuori: dict[str, Optional[float]] = {}
    for griglia in GRIGLIE:
        for valore in griglia.valori:
            esito = simula(griglia, valore, n1, ingresso, stop, tp1,
                           target_finale, verso, successive, barre_massime,
                           costo_per_lato)
            fuori[griglia.nome_colonna(valore)] = (
                None if esito is None else esito.erre)
    return fuori
