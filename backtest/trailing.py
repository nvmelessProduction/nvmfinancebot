"""Uscita a trailing stop, senza take profit. E il suo placebo.

**Fuori dalla strategia scritta.** `GEST-05` ed `ESCL-09` vietano il trailing
in ogni forma: lo stop si muove una volta sola, a pareggio, e solo dopo TP1.
Questo file misura un'ipotesi alternativa, non implementa una regola.

## Perche' non e' una domanda gia' risposta

Il bersaglio fisso misura *«il prezzo arriva a 2 R prima di tornare a 1 R?»*.
Il trailing misura *«nei giorni dopo l'ingresso il prezzo deriva nella
direzione del segnale?»*. Sono due proprieta' diverse: un pattern puo' essere
inutile sulla prima e utile sulla seconda, perche' la prima e' quasi tutta
geometria mentre la seconda e' quasi tutta tendenza.

## Il metodo, dichiarato prima di guardare i risultati

Le distanze di trailing provate sono **tre**, fissate qui: 1, 2 e 3 volte il
rischio iniziale. Si riportano tutte e tre, comprese quelle che vanno male.
Provarne venti e raccontare la migliore sarebbe fabbricare un risultato: con
858 segnali il rumore vale ±0,027 R, e una variante su venti esce a +0,05 R
per puro caso.

Ogni variante viene confrontata con il **suo** placebo — entrate a caso,
stesso strumento, stesso periodo, stessa direzione, stessa distanza relativa
di stop, stesso trailing. L'unico numero che significa qualcosa e' la
differenza fra le due.

## Le convenzioni, tutte prudenti

- dentro una barra non si sa in che ordine il prezzo sia passato: lo stop si
  verifica **prima** di aggiornare il trailing, col livello gia' in vigore;
- a fine orizzonte si chiude al prezzo corrente, non si finge un'uscita
  migliore;
- il costo di un giro si sottrae al risultato, come in `costi.py`.
"""
from __future__ import annotations

import random
import statistics
from bisect import bisect_right

import costi
from core.definizioni import Bias
from core.parametri import TF

DISTANZE = (1.0, 2.0, 3.0)        # in multipli del rischio iniziale
ORIZZONTE_GIORNI = 60
CAMPIONI = 20


def percorri(serie, partenza, direzione, ingresso, stop, distanza, massimo_barre):
    """Cammina in avanti con lo stop che insegue. Restituisce il risultato in R.

    `distanza` e' il trailing, in multipli del rischio iniziale.
    """
    rischio = abs(ingresso - stop)
    if rischio == 0:
        return None
    scia = distanza * rischio
    livello = stop
    estremo = ingresso

    for barra in serie[partenza:partenza + massimo_barre]:
        # 1. Lo stop in vigore viene verificato per primo.
        if direzione is Bias.SHORT and barra.massimo >= livello:
            return (ingresso - livello) / rischio
        if direzione is Bias.LONG and barra.minimo <= livello:
            return (livello - ingresso) / rischio

        # 2. Poi il trailing si aggiorna sull'estremo favorevole della barra,
        #    e non torna mai indietro.
        if direzione is Bias.SHORT:
            estremo = min(estremo, barra.minimo)
            livello = min(livello, estremo + scia)
        else:
            estremo = max(estremo, barra.massimo)
            livello = max(livello, estremo - scia)

    # 3. Orizzonte scaduto: si chiude dove sta il prezzo.
    ultima = serie[min(partenza + massimo_barre, len(serie)) - 1]
    if direzione is Bias.SHORT:
        return (ingresso - ultima.chiusura) / rischio
    return (ultima.chiusura - ingresso) / rischio


def confronta(segnali, storico, tempi, distanza: float, seme: int = 20260915) -> dict:
    """Risultati in R dei segnali veri e delle entrate a caso appaiate."""
    caso = random.Random(seme)
    orarie = storico.get(TF.H1, ())
    prima = orarie[0].orario if orarie else None
    veri: list[float] = []
    finti: list[float] = []
    spese: list[float] = []

    for segnale in segnali:
        marcia = TF.H1 if (prima and segnale.istante >= prima) else TF.D1
        serie = storico[marcia]
        massimo = ORIZZONTE_GIORNI * (24 if marcia is TF.H1 else 1)
        r = abs(segnale.ingresso - segnale.stop) / segnale.ingresso
        if r == 0:
            continue

        esito = percorri(serie, bisect_right(tempi[marcia], segnale.istante),
                         segnale.direzione, segnale.ingresso, segnale.stop,
                         distanza, massimo)
        if esito is None:
            continue
        veri.append(esito)
        spese.append(costi.costo_in_erre(segnale.strumento, segnale.ingresso, segnale.stop))

        for _ in range(CAMPIONI):
            indice = caso.randrange(0, max(1, len(serie) - massimo - 1))
            apertura = serie[indice].chiusura
            finto_stop = (apertura * (1 + r) if segnale.direzione is Bias.SHORT
                          else apertura * (1 - r))
            fuori = percorri(serie, indice + 1, segnale.direzione, apertura,
                             finto_stop, distanza, massimo)
            if fuori is not None:
                finti.append(fuori)

    return {"veri": veri, "finti": finti, "spese": spese}


def riassumi(veri, finti, spese) -> str:
    if len(veri) < 2 or len(finti) < 2:
        return "campione troppo piccolo"
    mv, mf = statistics.fmean(veri), statistics.fmean(finti)
    ev = statistics.stdev(veri) / len(veri) ** 0.5
    ef = statistics.stdev(finti) / len(finti) ** 0.5
    diff = mv - mf
    errore = (ev ** 2 + ef ** 2) ** 0.5
    costo = statistics.fmean(spese)
    vincenti = 100 * sum(1 for v in veri if v > 0) / len(veri)
    return (f"CRT {mv:+.3f} R  a caso {mf:+.3f} R  "
            f"vantaggio {diff:+.3f} ±{errore:.3f} ({diff/errore:+5.2f}s)  "
            f"costo {costo:.3f}  netto {diff - costo:+.3f}  vinc. {vincenti:4.1f}%")
