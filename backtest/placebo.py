"""Il CRT batte una monetina? Confronto contro entrate a caso.

E' la domanda che viene prima di ogni ottimizzazione, e quasi nessuno se la
fa. Una strategia con stop stretto e bersaglio vicino ha un tasso di successo
alto **per geometria**, non per bravura: se il bersaglio sta a 2 R, il prezzo
ci arriva prima dello stop circa una volta su tre anche entrando a caso.

Quindi il 32% misurato non dice niente da solo. Dice qualcosa solo se
confrontato con il 32% (o 28%, o 36%) che si ottiene **con la stessa
geometria, nello stesso strumento, nello stesso periodo, entrando a caso**.

## Come e' costruito il confronto

Per ogni segnale vero si prendono:

  - lo stesso strumento e lo stesso periodo;
  - la stessa distanza **relativa** di stop e di bersaglio (`r` e `t`), cosi'
    la geometria e' identica e non si confrontano mele con pere;
  - la stessa direzione;
  - `CAMPIONI` barre di partenza estratte a caso.

Poi si cammina in avanti con le stesse identiche regole del simulatore vero,
tie-break compreso: a parita' dentro una barra vince lo stop.

Se i due tassi coincidono, il CRT non aggiunge informazione: tutto quello che
si misura e' la forma del bersaglio. Se il CRT e' sopra in modo stabile, un
segnale c'e' e vale la pena cercarne il modo migliore di usarlo.
"""
from __future__ import annotations

import random
import statistics
from bisect import bisect_right

from core.definizioni import Bias
from core.parametri import TF

CAMPIONI = 20            # entrate a caso per ogni segnale vero
ORIZZONTE_GIORNI = 60


def _risolve(serie, partenza, direzione, ingresso, stop, bersaglio, massimo_barre):
    """Cammina in avanti. Restituisce True se arriva al bersaglio, False allo
    stop, None se scade. Stesse regole del simulatore vero."""
    for barra in serie[partenza:partenza + massimo_barre]:
        if direzione is Bias.SHORT:
            preso_stop = barra.massimo >= stop
            preso_target = barra.minimo <= bersaglio
        else:
            preso_stop = barra.minimo <= stop
            preso_target = barra.massimo >= bersaglio
        if preso_stop:
            return False          # a parita' vince lo stop
        if preso_target:
            return True
    return None


def confronta(segnali, storico, tempi, seme: int = 20260915) -> dict:
    """Tasso di successo dei segnali veri contro quello delle entrate a caso."""
    caso = random.Random(seme)
    orarie = storico[TF.H1]
    prima_oraria = orarie[0].orario if orarie else None

    veri: list[bool] = []
    finti: list[bool] = []

    for segnale in segnali:
        marcia = TF.H1 if (prima_oraria and segnale.istante >= prima_oraria) else TF.D1
        serie = storico[marcia]
        per_giorno = 24 if marcia is TF.H1 else 1
        massimo = ORIZZONTE_GIORNI * per_giorno

        r = abs(segnale.ingresso - segnale.stop) / segnale.ingresso
        t = abs(segnale.ingresso - segnale.tp1) / segnale.ingresso
        if r == 0 or t == 0:
            continue

        partenza = bisect_right(tempi[marcia], segnale.istante)
        esito = _risolve(serie, partenza, segnale.direzione, segnale.ingresso,
                         segnale.stop, segnale.tp1, massimo)
        if esito is None:
            continue
        veri.append(esito)

        # Le stesse proporzioni, applicate a barre estratte a caso.
        for _ in range(CAMPIONI):
            indice = caso.randrange(0, max(1, len(serie) - massimo - 1))
            apertura = serie[indice].chiusura
            if segnale.direzione is Bias.SHORT:
                finto_stop, finto_target = apertura * (1 + r), apertura * (1 - t)
            else:
                finto_stop, finto_target = apertura * (1 - r), apertura * (1 + t)
            fuori = _risolve(serie, indice + 1, segnale.direzione, apertura,
                             finto_stop, finto_target, massimo)
            if fuori is not None:
                finti.append(fuori)

    return {"veri": veri, "finti": finti}


def riassumi(veri, finti) -> str:
    """Le due percentuali, la differenza e quante sigma vale."""
    if not veri or not finti:
        return "campione vuoto"
    pv = statistics.fmean(veri)
    pf = statistics.fmean(finti)
    # Errore standard della differenza fra due proporzioni indipendenti.
    ev = (pv * (1 - pv) / len(veri)) ** 0.5
    ef = (pf * (1 - pf) / len(finti)) ** 0.5
    diff = pv - pf
    errore = (ev ** 2 + ef ** 2) ** 0.5
    return (f"CRT {100*pv:5.1f}% su {len(veri):5d}   "
            f"a caso {100*pf:5.1f}% su {len(finti):6d}   "
            f"differenza {100*diff:+5.1f} punti  ({diff/errore:+.2f} sigma)")
