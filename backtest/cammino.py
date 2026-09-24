"""Come sarebbe finita l'operazione GESTITA, non solo aperta.

## Perche' serve un secondo simulatore

`etichette.py` misura una cosa semplice: entra, e finisce a TP1 o allo stop.
E' la domanda giusta per il modello centrale -- "questo CRT vince?" -- e
sarebbe la domanda sbagliata per la sentinella, che entra in scena **dopo**.

Il bot vero fa due tempi (`GEST-04`, `SETUP-14`, `REV-49`):

    1. ingresso -> TP1 (il 50% del range). Li' chiude un quarto.
    2. il 75% residuo prosegue verso il key level, con lo stop spostato.

La sentinella non decide se entrare. Decide **dove mettere lo stop nel secondo
tempo**, ed e' l'unica cosa che decide. E' il suo ambito.

## Il numero che impara

Lo stop del residuo sta a `ingresso +/- k x rischio`:

    k = 0.00   pareggio secco — la regola di oggi
    k = 0.50   a meta' strada fra ingresso e stop originale
    k = 1.00   non si muove niente, resta lo stop iniziale

`k = 0` e' il manuale del neolaureato. Se i cammini dicono che conviene
diversamente, la sentinella se lo guadagna -- passando il cancello di
`core/apprendimento.py`, non perche' il numero e' piu' bello.

E' esattamente la lamentela ricorrente: posizioni che aprono e chiudono in
pochi secondi. Uno stop portato a pareggio troppo presto uccide le operazioni
che sarebbero andate.

## La prudenza, e dov'e' messa

Due punti dove non si sa in che ordine il prezzo sia passato, e in entrambi si
sceglie la lettura peggiore -- la stessa che la sentinella applica dal vivo in
`livello_toccato`:

1. la barra tocca stop e TP1: vince lo stop, e l'operazione muore intera;
2. nel secondo tempo, una barra tocca stop del residuo e bersaglio: vince lo
   stop.

**E un punto dove la prudenza sarebbe stata un errore.** La prima versione
riesaminava anche la barra di TP1 contro lo stop del residuo. Sembra prudente
e non lo e': prima di TP1 quello stop non esisteva ancora, valeva l'originale,
e la barra e' gia' passata dal primo tempo senza toccarlo. In piu' quella
barra ha quasi sempre l'estremo avverso sull'ingresso -- l'ingresso e' la
chiusura della barra precedente -- quindi con `k = 0` il residuo moriva quasi
sempre, per meccanica e non per mercato. Avrebbe fatto sembrare il pareggio
secco un disastro senza che il prezzo c'entrasse. I test l'hanno bocciata al
primo giro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from core.definizioni import Bias, Candela

# Quanto si chiude a TP1. `GEST-04`: un quarto, e il 75% prosegue.
FRAZIONE_PARZIALE: float = 0.25

# Il `k` di oggi: pareggio secco. E' il predefinito della competenza, cioe'
# cio' che il bot fa adesso e cio' a cui si torna se l'appreso non passa.
K_DI_OGGI: float = 0.0


@dataclass(frozen=True)
class EsitoGestito:
    """Com'e' finita l'operazione con la gestione a due tempi."""

    # "stop", "parziale+stop", "parziale+target", "parziale+scaduto", "scaduto"
    come: str
    # R complessivo, al netto dei costi, pesato per le frazioni.
    erre: float
    # Quante barre sono servite in tutto.
    barre: int
    # Il parziale e' stato incassato?
    tp1_preso: bool


def _toccato(barra: Candela, livello: float, verso: Bias, favorevole: bool) -> bool:
    """La barra ha raggiunto il livello?

    `favorevole` distingue i due versi: per una short il bersaglio sta sotto
    (serve il minimo) e lo stop sta sopra (serve il massimo).
    """
    if verso is Bias.SHORT:
        return barra.minimo <= livello if favorevole else barra.massimo >= livello
    return barra.massimo >= livello if favorevole else barra.minimo <= livello


def stop_del_residuo(ingresso: float, stop: float, k: float) -> float:
    """Dove sta lo stop nel secondo tempo.

    `k = 0` e' l'ingresso esatto (pareggio), `k = 1` e' lo stop di partenza.
    Si interpola fra i due, quindi il verso viene da solo: non c'e' un ramo
    per le long e uno per le short, e due rami e' il posto dove il segno si
    inverte senza che nessuno se ne accorga.
    """
    return ingresso + k * (stop - ingresso)


def esito_gestito(
    ingresso: float,
    stop: float,
    tp1: float,
    target_finale: float,
    verso: Bias,
    successive: Sequence[Candela],
    barre_massime: int,
    costo_per_lato: float = 0.0,
    k: float = K_DI_OGGI,
    frazione: float = FRAZIONE_PARZIALE,
) -> Optional[EsitoGestito]:
    """L'operazione dall'ingresso alla fine, coi due tempi di `GEST-04`.

    `None` quando i livelli non descrivono l'operazione che si dice di
    misurare: rischio nullo, TP1 o bersaglio dalla parte sbagliata. Un
    risultato inventato su livelli incoerenti e' peggio di un risultato
    assente.
    """
    rischio = abs(ingresso - stop)
    if rischio <= 0 or not successive:
        return None
    if not (0.0 <= frazione <= 1.0):
        raise ValueError(f"frazione fuori da [0,1]: {frazione}")

    corta = verso is Bias.SHORT
    # TP1 e bersaglio devono stare dalla parte del guadagno, lo stop dall'altra.
    if corta:
        if not (tp1 < ingresso and target_finale < ingresso and stop > ingresso):
            return None
    else:
        if not (tp1 > ingresso and target_finale > ingresso and stop < ingresso):
            return None

    # Il costo di un lato in multipli del rischio. L'ingresso si paga sul
    # 100%, ogni uscita sulla sua frazione: in totale due lati, come sempre.
    costo = costo_per_lato / rischio

    def guadagno(prezzo: float) -> float:
        """R lordo di un'uscita a questo prezzo."""
        return ((ingresso - prezzo) if corta else (prezzo - ingresso)) / rischio

    viste = list(successive[:barre_massime])

    # --- primo tempo: ingresso -> TP1 ------------------------------------
    indice_tp1 = None
    for numero, barra in enumerate(viste, start=1):
        if _toccato(barra, stop, verso, favorevole=False):
            # Muore intera. Un lato all'ingresso, uno all'uscita, sul 100%.
            return EsitoGestito("stop", -1.0 - 2.0 * costo, numero, False)
        if _toccato(barra, tp1, verso, favorevole=True):
            indice_tp1 = numero
            break

    if indice_tp1 is None:
        ultima = viste[-1].chiusura
        return EsitoGestito("scaduto", guadagno(ultima) - 2.0 * costo,
                            len(viste), False)

    # --- il parziale ------------------------------------------------------
    erre = frazione * (guadagno(tp1) - costo)      # uscita del quarto
    erre -= costo                                  # ingresso, sul 100%

    livello_residuo = stop_del_residuo(ingresso, stop, k)
    resto = 1.0 - frazione
    if resto <= 0:
        return EsitoGestito("parziale+target", erre, indice_tp1, True)

    # --- secondo tempo ----------------------------------------------------
    #
    # Si riparte dalla barra DOPO quella di TP1, e non e' una scelta
    # ottimistica: e' che prima di TP1 lo stop del residuo **non esisteva
    # ancora**. Fino a quel punto valeva quello originale, e la barra di TP1
    # e' gia' passata dal primo tempo senza toccarlo -- se l'avesse toccato
    # l'operazione sarebbe morta intera.
    #
    # La prima versione riesaminava anche la barra di TP1, e i test l'hanno
    # bocciata subito: la barra che tocca TP1 ha quasi sempre l'estremo
    # avverso sull'ingresso, perche' l'ingresso e' la chiusura di quella
    # precedente. Con `k = 0` il residuo moriva quasi sempre, e per un motivo
    # meccanico -- avrebbe fatto sembrare il pareggio secco un disastro senza
    # che il mercato c'entrasse niente.
    #
    # Resta un'ottimismo dichiarato e limitato a una barra: se dentro la barra
    # di TP1 il prezzo tornasse indietro oltre `livello_residuo`, qui non si
    # vede.
    for numero, barra in enumerate(viste[indice_tp1:], start=indice_tp1 + 1):
        if _toccato(barra, livello_residuo, verso, favorevole=False):
            erre += resto * (guadagno(livello_residuo) - costo)
            return EsitoGestito("parziale+stop", erre, numero, True)
        if _toccato(barra, target_finale, verso, favorevole=True):
            erre += resto * (guadagno(target_finale) - costo)
            return EsitoGestito("parziale+target", erre, numero, True)

    ultima = viste[-1].chiusura
    erre += resto * (guadagno(ultima) - costo)
    return EsitoGestito("parziale+scaduto", erre, len(viste), True)
