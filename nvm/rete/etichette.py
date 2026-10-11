"""Le risposte giuste della scuola 2: quello che gli agenti del metodo delle foto vedono a ogni istante.

La rete impara prima a leggere come il bot (le regole scritte del proprietario), poi dal proprietario stesso. Per
ogni istante (apertura di una candela a 4 ore, `finestre.Storia.istanti`):

- **direzione** di giorno, settimana e mese: com'e' la candela appena chiusa rispetto a quella prima
  (`foto.bias_candela`: accetta su, accetta giu', nessuna);
- **crt** a 4 ore e del giorno: la candela 3 di un CRT apre adesso? (`foto.trova`) e da che parte;
- **setup** a 4 ore e del giorno: il CRT e' anche un setup completo, col key level preso dalla candela 2 e la
  direzione dalla sua parte (`foto.direzione`), cioe' quello che il bot prenderebbe.

Classi: 0 niente (o ribassista per la direzione), 1 acquisto (rialzista), 2 vendita; la direzione usa 0 giu',
1 nessuna, 2 su.
"""

from __future__ import annotations

import numpy as np

from nvm.agenti import foto
from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import Minuti
from nvm.tempo import TF

TF_DIREZIONE = (TF.D1, TF.W1, TF.MN)
TF_SETUP = (TF.H4, TF.D1)
# Le domande della scuola 2, nell'ordine delle teste della rete, col timeframe a cui guardano.
DOMANDE = tuple([(f"direzione {tf.value}", tf) for tf in TF_DIREZIONE] +
                [(f"crt {tf.value}", tf) for tf in TF_SETUP] +
                [(f"setup {tf.value}", tf) for tf in TF_SETUP])


def etichette(ore: Minuti, t: np.ndarray, q=None) -> dict[str, np.ndarray]:
    """Le risposte degli agenti a ogni istante di `t` (ordinati), per nome di domanda."""
    t = np.asarray(t, np.int64)
    if q is None:
        q = foto.Quadro.da(ore, int(t[-1]) + 1)
    fuori = {}
    for tf in TF_DIREZIONE:
        c = q.candele[tf]
        k = np.searchsorted(c.fine, t, side="right") - 1
        fuori[f"direzione {tf.value}"] = np.array([foto.bias_candela(c, int(i))[0] + 1 for i in k], np.int64)
    posto = {int(x): i for i, x in enumerate(t)}
    for tf in TF_SETUP:
        crt = np.zeros(len(t), np.int64)
        setup = np.zeros(len(t), np.int64)
        for s in foto.trova(q, tf, int(t[0]), int(t[-1])):
            i = posto.get(int(s.n3_inizio))
            if i is None:
                continue
            classe = 2 if s.verso is Verso.SHORT else 1
            if crt[i] and crt[i] != classe:
                crt[i] = setup[i] = 0      # un CRT per lato nello stesso istante: non si sa, niente
                continue
            crt[i] = classe
            if s.presi and foto.direzione(q, s).ok:
                setup[i] = classe
        fuori[f"crt {tf.value}"] = crt
        fuori[f"setup {tf.value}"] = setup
    return fuori
