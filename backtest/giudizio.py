"""Mette ME davanti ai setup, alla cieca, come farebbe un discrezionale.

## Perche' serve un protocollo e non basta "guardare i grafici"

Se decido conoscendo l'esito non misuro il giudizio, misuro il senno di poi. E
non e' un rischio teorico: i dati sono gia' passati sotto i miei occhi in
questa stessa sessione.

Quindi il programma fa due cose separate, e in quest'ordine:

```
prepara   scrive i dossier, SENZA esito, e li salva
rivela    legge le mie decisioni e solo allora calcola come e' andata
```

Fra i due passi le decisioni finiscono in un file. Una volta scritte non si
toccano: e' l'unica garanzia che il confronto significhi qualcosa.

## Cosa contiene un dossier

Tutto quello che un trader avrebbe davanti al momento della decisione, e nulla
di piu': la candela di riferimento, come e' stato spazzata, i livelli, il
contesto delle ultime barre, l'orario. Nessuna barra successiva all'ingresso.
"""
from __future__ import annotations

import json
import random
from bisect import bisect_right
from pathlib import Path
from typing import Sequence

from core.definizioni import Bias, Candela

DOSSIER = Path("dossier.json")
DECISIONI = Path("decisioni.json")
ESITI = Path("esiti_veri.json")


def descrivi(candela: Candela, etichetta: str) -> dict:
    corpo = abs(candela.chiusura - candela.apertura)
    ampiezza = candela.massimo - candela.minimo
    return {
        "etichetta": etichetta,
        "apertura": round(candela.apertura, 5),
        "massimo": round(candela.massimo, 5),
        "minimo": round(candela.minimo, 5),
        "chiusura": round(candela.chiusura, 5),
        "direzione": "su" if candela.chiusura > candela.apertura else "giu",
        "corpo_su_range": round(corpo / ampiezza, 2) if ampiezza else None,
    }


def dossier(setup, strumento: str, htf: Sequence[Candela], ltf: Sequence[Candela],
            tempi_h: Sequence, indice_ltf_ingresso: int) -> dict:
    """Il fascicolo di un setup, con solo cio' che si sa al momento di decidere."""
    i_h = bisect_right(tempi_h, setup.orario) - 1
    rif = htf[i_h - 1]
    corto = setup.direzione is Bias.SHORT
    ampiezza = rif.massimo - rif.minimo
    livello = rif.massimo if corto else rif.minimo
    eq = (rif.massimo + rif.minimo) / 2

    precedenti = [descrivi(htf[i_h - 1 - k], f"riferimento-{k}") for k in range(0, 4)
                  if i_h - 1 - k >= 0]
    # Le barre LTF dall'inizio della finestra fino all'ingresso, compresa.
    inizio = max(0, indice_ltf_ingresso - 12)
    recenti = [descrivi(ltf[j], f"esecuzione-{indice_ltf_ingresso-j}")
               for j in range(inizio, indice_ltf_ingresso)]

    return {
        "strumento": strumento,
        "quando": setup.orario.strftime("%Y-%m-%d %H:%M UTC"),
        "giorno_settimana": setup.orario.strftime("%A"),
        "ora_utc": setup.orario.hour,
        "direzione": "SHORT" if corto else "LONG",
        "candela_di_riferimento": descrivi(rif, "il range da operare"),
        "riferimento_precedenti": precedenti[1:],
        "livello_spazzato": round(livello, 5),
        "equilibrio_del_range": round(eq, 5),
        "estremo_dello_sweep": round(setup.stop, 5),
        "sforamento_su_range": round(abs(setup.stop - livello) / ampiezza, 3) if ampiezza else None,
        "ingresso": round(setup.ingresso, 5),
        "ingresso_vs_equilibrio": "premium" if setup.ingresso > eq else "discount",
        "stop": round(setup.stop, 5),
        "bersaglio": round(setup.bersaglio, 5),
        "rapporto": round(setup.rapporto, 2),
        "barre_esecuzione_recenti": recenti,
    }
