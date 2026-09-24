"""Il campo di prova: ogni CRT con i suoi punteggi e com'e' finito.

## Cosa produce

Una riga per CRT: quando, dove, gli otto punteggi delle conferme, i livelli, e
l'esito in R al netto dei costi. E' il dataset che la Fase 2 dovra' pesare.

## La regola che non si viola, e come e' garantita

**Le caratteristiche usano SOLO candele chiuse prima dell'ingresso.** L'esito,
e solo l'esito, guarda avanti -- e' l'etichetta, ed e' corretto che sia cosi'.

La garanzia non e' una buona intenzione: e' strutturale. `caratteristiche()`
riceve una serie GIA' TRONCATA all'istante del CRT e non ha modo di vedere
oltre; `etichetta()` riceve le barre successive e non vede i punteggi. Sono
due funzioni che non si parlano, e `verifica_niente_sbirciate` lo prova
ricalcolando le caratteristiche sull'archivio intero e sull'archivio troncato
e pretendendo che coincidano.

Serve perche' sbirciare anche di una barra fa sembrare perfetto ogni CRT. Il
progetto ci e' gia' cascato: `CRT-17` dava 85,7% di winrate e +15,3 sigma
filtrando con le candele SUCCESSIVE a N2, e guardando solo cio' che si vede
davvero al momento dell'ingresso spariva del tutto. Era il quinto falso
positivo, e tutti e cinque avevano lo stesso aspetto: un numero troppo bello.

## Cosa NON fa

Non applica filtri, esclusioni, bias o rischio. Qui si raccoglie ogni CRT che
ESISTE, con quello che le conferme dicevano. Quali valga la pena prendere e'
la domanda della Fase 2, e rispondervi qui vorrebbe dire rispondere prima di
misurare.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from etichette import Esito, esito_del_crt                     # noqa: E402

from core import gestione as gest                              # noqa: E402
from core import setup as stp                                  # noqa: E402
from core import stato                                         # noqa: E402
from core.definizioni import Bias, Candela                     # noqa: E402
from core.parametri import TF                                  # noqa: E402

LE_OTTO = ("CRT-06", "CRT-10", "CRT-11", "CRT-12",
           "CRT-15", "CRT-17", "CRT-18", "CRT-20")


@dataclass(frozen=True)
class Riga:
    """Un CRT, come si vedeva e come e' finito."""

    strumento: str
    coppia: str
    quando: str
    verso: str
    # I tre livelli, sulla scala su cui l'esito e' misurato.
    ingresso: float
    stop: float
    target: float
    rapporto: float
    # Il costo del giro completo, in multipli del rischio. E' gia' dentro
    # `erre`, e sta anche qui da solo perche' la regola d'ingresso della
    # Fase 2 -- `p x RR - (1 - p) - costi > 0` -- lo vuole separato. Chi lo
    # ricalcolasse a valle scriverebbe la seconda copia della stessa regola.
    costo_erre: float
    # Gli otto punteggi: True / False / None, come il motore li calcola.
    conferme: dict
    # Quanti altri timeframe erano allineati (CRT-06 porta un conteggio, non
    # un si'/no: vedi il suo docstring).
    allineati: Optional[int]
    # L'etichetta.
    esito: str
    erre: float
    barre: int
    # Il bersaglio del 75% residuo (SETUP-14). `None` quando non esiste un key
    # level nella direzione: dal vivo quella e' un'astensione (PRIN-99).
    target_finale: Optional[float] = None
    # Gli R della gestione a due tempi, un candidato per agente: e' cio' su
    # cui gli agenti fanno carriera. Vuoto quando manca il bersaglio.
    cammini: dict = field(default_factory=dict)


def caratteristiche(
    crt, tf_range: TF, barre_fino_a_ora: Sequence[Candela],
    istante: datetime,
    strumento: str = "",
    compagne: Optional[dict] = None,
    crt_per_tf: Optional[dict] = None,
) -> tuple[dict, Optional[int]]:
    """Gli otto punteggi, come si vedevano all'istante del CRT.

    **Non riceve lo storico.** Riceve solo dati GIA' troncati: le barre di
    esecuzione chiuse entro l'istante del rientro, le serie delle compagne
    gia' tagliate, i CRT degli altri timeframe gia' calcolati a quell'istante.

    E' la garanzia strutturale contro la sbirciata: senza lo storico intero in
    mano, questa funzione non ha modo di guardare oltre nemmeno volendo. Dare
    qui lo storico e fidarsi che venga troncato dentro sarebbe la stessa
    fiducia che ha gia' prodotto cinque falsi positivi.
    """
    _, _, responso = stp.conferme_di_romeo(
        n1=crt.n1,
        n2=crt.n2,
        candele_ingresso=list(barre_fino_a_ora[-12:]),
        direzione=crt.direzione,
        istante=istante,
        tf_crt=tf_range,
        candele_compagne=compagne,
        candele_strumento=list(barre_fino_a_ora),
        strumento=strumento,
        crt_per_tf=crt_per_tf,
        barre_fase=getattr(crt, "barre_fase", ()),
    )
    allineati = stp.quanti_modelli_allineati(crt_per_tf, tf_range, crt.direzione)
    return responso, allineati


def etichetta(
    crt, successive: Sequence[Candela], barre_massime: int,
    costo_per_lato: float,
) -> tuple[Optional[Esito], float, float, float]:
    """L'esito, e i tre livelli su cui e' misurato.

    Lo stop e' l'estremo di N2 (GEST-02, SETUP-02C); il bersaglio e' il 50%
    del range di N1 (GEST-07, CRT-16). Qui NON si usa il key level di
    SETUP-14: quello e' il target del 75% residuo dopo il parziale, e
    misurarci sopra l'esito intero confonderebbe due momenti diversi.
    """
    ingresso = crt.n2.chiusura
    stop = gest.stop_aggressivo(crt.n2, crt.direzione)
    target = gest.tp1(crt.n1)
    esito = esito_del_crt(ingresso, stop, target, crt.direzione,
                          successive, barre_massime, costo_per_lato)
    return esito, ingresso, stop, target


def punteggi_dallo_storico(
    crt, storico: dict, tf_range: TF, tf_esecuzione: TF, istante: datetime,
    strumento: str = "", compagne: Optional[dict] = None,
    crt_per_tf: Optional[dict] = None,
) -> tuple[dict, Optional[int]]:
    """I punteggi partendo dall'archivio, troncando QUI.

    E' l'unico punto in cui l'archivio intero e l'istante si incontrano, ed e'
    una riga sola: `c.orario <= istante`. Tutto cio' che sta a valle riceve
    dati gia' tagliati e non puo' sbagliarsi.
    """
    tutte = storico.get(tf_esecuzione, ())
    fino_a_ora = [c for c in tutte if c.orario <= istante]
    return caratteristiche(crt, tf_range, fino_a_ora, istante,
                           strumento, compagne, crt_per_tf)


def verifica_niente_sbirciate(
    crt, storico: dict, tf_range: TF, tf_esecuzione: TF,
    istante: datetime,
) -> Optional[str]:
    """Dare l'archivio INTERO deve dare lo stesso risultato di darlo tagliato.

    E' il controllo del protocollo. Se l'estrattore tronca davvero
    all'istante, le due letture coincidono; se da qualche parte legge oltre,
    divergono -- e ogni misura che ne discende e' senza valore.

    Non e' un controllo teorico. Il progetto ci e' gia' cascato: `CRT-17` dava
    85,7% di winrate e +15,3 sigma filtrando con le candele SUCCESSIVE a `N2`,
    e guardando solo cio' che si vede al momento dell'ingresso spariva del
    tutto. Era il quinto falso positivo, e tutti e cinque avevano lo stesso
    aspetto: un numero troppo bello.

    Restituisce il motivo della divergenza, oppure `None` se tutto regge.
    """
    tutte = storico.get(tf_esecuzione, ())
    troncato = dict(storico)
    troncato[tf_esecuzione] = tuple(c for c in tutte if c.orario <= istante)
    if len(troncato[tf_esecuzione]) == len(tutte):
        return None                     # niente futuro da cui sbirciare

    con_futuro, _ = punteggi_dallo_storico(
        crt, storico, tf_range, tf_esecuzione, istante)
    senza, _ = punteggi_dallo_storico(
        crt, troncato, tf_range, tf_esecuzione, istante)
    if con_futuro != senza:
        diverse = [k for k in LE_OTTO if con_futuro.get(k) != senza.get(k)]
        return ("l'archivio intero da' punteggi diversi da quello troncato: "
                + ", ".join(diverse))
    return None
