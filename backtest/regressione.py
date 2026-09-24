"""La regressione logistica con penalita' L2, scritta qui dentro.

## Perche' a mano

Perche' e' il pezzo che decide, e un pezzo che decide va capito. `sklearn` non
e' installato e non viene installato: la richiesta era **un algoritmo da
zero**, e questo e' il punto in cui "da zero" smette di essere una parola e
diventa cinquanta righe di algebra.

Non e' una rinuncia: la logistica ha una soluzione chiusa per ogni passo di
Newton, converge in una decina di iterazioni su questi numeri, e ogni
quantita' che produce ha un nome che si puo' controllare.

## Perche' logistica, e non qualcosa di piu' furbo

Perche' serve una **probabilita' calibrata**, non un punteggio. La regola
d'ingresso e' `p x RR - (1 - p) - costi > 0`: se `p` non e' una probabilita'
vera, quella moltiplicazione non significa niente. Un modello piu' espressivo
darebbe punteggi migliori e probabilita' peggiori, e qui la probabilita' e'
tutto cio' che serve.

E perche' i pesi si leggono. Con 16.463 righe, otto conferme e un holdout da
difendere, un modello che nessuno puo' guardare in faccia e' un modello che
nessuno puo' rifiutare.

## La penalita' L2, e perche' non e' opzionale

Due ragioni, e la seconda e' quella che conta qui.

La prima e' la solita: con poche righe per colonna i pesi scappano.

La seconda e' che nel campo di prova **ci sono colonne costanti**. `CRT-15`
risponde `None` su tutte e 16.463 le righe, quindi le sue due colonne sono
zero ovunque. Senza penalita' la matrice del passo di Newton e' singolare e
l'inversione fallisce o, peggio, restituisce numeri enormi. Con `lambda > 0`
la matrice torna definita positiva **per costruzione**, e il peso di una
colonna costante va a zero, che e' la risposta giusta: una costante non
informa.

## Cosa NON fa

Non sceglie le colonne, non guarda il tempo, non decide se il modello e'
buono. Prende una matrice e delle etichette e restituisce dei pesi. Il
walk-forward, il Brier e i criteri del protocollo stanno in `addestra.py`,
perche' sono domande diverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

# Quante iterazioni di Newton al massimo. Su questi dati ne servono meno di
# dieci; il tetto esiste perche' un ciclo che non converge non deve poter
# bloccare una misura.
ITERAZIONI_MASSIME: int = 50

# Sotto questo spostamento dei pesi si e' arrivati.
TOLLERANZA: float = 1e-8

# La penalita' predefinita. Non e' un numero sacro: `addestra.py` la sceglie
# per validazione, e questo e' solo il punto di partenza.
LAMBDA: float = 1.0


@dataclass(frozen=True)
class Stima:
    """Cosa e' uscito dall'adattamento."""

    intercetta: float
    pesi: np.ndarray
    iterazioni: int
    converge: bool
    # La log-verosimiglianza penalizzata all'ultimo passo: serve a confrontare
    # due adattamenti sugli STESSI dati, non su dati diversi.
    obiettivo: float


def _logistica(z: np.ndarray) -> np.ndarray:
    """La logistica in forma stabile.

    `exp` di un numero grande trabocca. Si separano i due rami: per `z >= 0`
    si usa `1/(1+e^-z)`, per `z < 0` si usa `e^z/(1+e^z)`. Sono la stessa
    funzione, ma nessuna delle due esponenzia un numero positivo grande.
    """
    fuori = np.empty_like(z, dtype=float)
    positivi = z >= 0
    fuori[positivi] = 1.0 / (1.0 + np.exp(-z[positivi]))
    e = np.exp(z[~positivi])
    fuori[~positivi] = e / (1.0 + e)
    return fuori


def adatta(
    X: np.ndarray,
    y: np.ndarray,
    penalita: float = LAMBDA,
    peso_riga: Optional[np.ndarray] = None,
) -> Stima:
    """I pesi che massimizzano la verosimiglianza penalizzata.

    `X` e' (righe x colonne) SENZA la colonna dell'intercetta: viene aggiunta
    qui, ed e' l'unica che la penalita' **non** tocca. Penalizzare
    l'intercetta vorrebbe dire spingere la probabilita' di base verso un mezzo
    anche quando i dati dicono un terzo -- e qui la base e' il 35,9%.

    `peso_riga` serve al ricampionamento a blocchi: ripesare una riga e'
    equivalente a ripeterla, e costa molto meno che ricostruire la matrice.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2:
        raise ValueError("X dev'essere una matrice righe x colonne")
    if len(X) != len(y):
        raise ValueError(f"X ha {len(X)} righe e y ne ha {len(y)}")
    if len(X) == 0:
        raise ValueError("non si stima niente su zero righe")

    n, k = X.shape
    # La colonna di uni in testa: l'intercetta e' un peso come gli altri,
    # tranne che per la penalita'.
    A = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)

    pesi_riga = (np.ones(n) if peso_riga is None
                 else np.asarray(peso_riga, dtype=float))

    # La penalita' non tocca l'intercetta: primo elemento a zero.
    diagonale = np.full(k + 1, float(penalita))
    diagonale[0] = 0.0
    penale = np.diag(diagonale)

    iterazioni = 0
    converge = False
    for iterazioni in range(1, ITERAZIONI_MASSIME + 1):
        p = _logistica(A @ w)
        # Gradiente della verosimiglianza penalizzata.
        g = A.T @ (pesi_riga * (y - p)) - penale @ w
        # Hessiana: A' W A + penalita'. `varianza` si azzera dove il modello
        # e' certissimo; il minimo la tiene lontana da zero, o la matrice
        # diventa singolare proprio quando l'adattamento sta riuscendo.
        varianza = np.clip(p * (1.0 - p), 1e-10, None) * pesi_riga
        H = (A * varianza[:, None]).T @ A + penale
        try:
            passo = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            # Con `penalita > 0` non dovrebbe succedere: se succede si
            # preferisce fermarsi che restituire numeri enormi.
            break
        w = w + passo
        if np.max(np.abs(passo)) < TOLLERANZA:
            converge = True
            break

    p = _logistica(A @ w)
    sicura = np.clip(p, 1e-12, 1 - 1e-12)
    verosimiglianza = float(np.sum(
        pesi_riga * (y * np.log(sicura) + (1 - y) * np.log(1 - sicura))))
    obiettivo = verosimiglianza - 0.5 * float(w @ penale @ w)
    return Stima(intercetta=float(w[0]), pesi=w[1:], iterazioni=iterazioni,
                 converge=converge, obiettivo=obiettivo)


def previsione(stima: Stima, X: np.ndarray) -> np.ndarray:
    """Le probabilita' su righe nuove."""
    X = np.asarray(X, dtype=float)
    return _logistica(stima.intercetta + X @ stima.pesi)


def brier(p: Sequence[float], y: Sequence[float]) -> float:
    """Lo scarto quadratico medio fra probabilita' ed esito.

    Il protocollo chiede il Brier e non l'accuratezza perche' l'accuratezza
    non sa distinguere un modello che dice 51% da uno che dice 99%, e qui la
    differenza fra i due e' tutta la decisione: `p` viene MOLTIPLICATA per il
    rapporto.

    Piu' basso e' meglio. Il riferimento non e' zero: e' il Brier di chi dice
    sempre la frequenza di base, che su questo campo vale 0,230.
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def brier_di_riferimento(y: Sequence[float]) -> float:
    """Il Brier di chi dice sempre la frequenza di base.

    E' la linea da battere: un modello che non la batte non ha imparato
    niente, per quanto bene si legga.
    """
    y = np.asarray(y, dtype=float)
    if len(y) == 0:
        return 0.0
    base = float(np.mean(y))
    return float(np.mean((base - y) ** 2))
