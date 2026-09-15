"""Dal segnale all'esito: stop, TP1, break even o target.

La scala degli esiti e' quella che il motore produrrebbe davvero, non una
inventata per il backtest:

  GEST-02   stop iniziale = estremo di N2
  GEST-07   TP1 = 50% del range di N1
  GEST-04   al TP1 si chiude il 25% e il resto va a break even
  GEST-05   dopo il break even lo stop non si muove piu'
  GEST-08   alla chiusura di ogni TF superiore che conferma il pattern, il
            target finale si sposta al key level di quel timeframe

Il pareggio esiste solo grazie a GEST-08: senza estensione il target finale
coincide con TP1 e la posizione si chiude tutta li'.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional, Sequence

from core.definizioni import Bias, Candela, key_levels
from core.gestione import Posizione, applica_tp1, estendi_target
from core.parametri import TF, gerarchia
from core.setup import cerca_crt

STOP, PAREGGIO, PRIMO, TARGET, APERTA = "stop", "be", "tp1", "target", "aperta"


@dataclass(frozen=True)
class Esito:
    segnale: object
    esito: str
    erre: float           # risultato in multipli del rischio iniziale
    barre: int
    tf_marcia: object = None   # su quale serie e' stata camminata


def _colpito(barra: Candela, direzione: Bias, stop: float, obiettivo: float) -> Optional[str]:
    """Quale livello ha toccato la barra. A parita' vince lo stop.

    E' la stessa scelta di `sentinella.livello_toccato`: dentro una barra non
    si sa in che ordine il prezzo sia passato, e fra due letture possibili si
    prende la peggiore.
    """
    if direzione is Bias.SHORT:
        se_stop = barra.massimo >= stop
        se_target = barra.minimo <= obiettivo
    else:
        se_stop = barra.minimo <= stop
        se_target = barra.massimo >= obiettivo
    if se_stop:
        return "stop"
    if se_target:
        return "target"
    return None


def _superiori(tf: TF) -> tuple[TF, ...]:
    ordine = gerarchia()
    return tuple(t for t in ordine if ordine.index(t) < ordine.index(tf))


def serie_di_marcia(segnale, storico, tempi) -> TF:
    """Su quale serie camminare in avanti dall'ingresso.

    Le orarie sono la grana piu' fine, ma coprono solo gli ultimi due anni:
    un segnale del 2013 camminato sulle orarie del 2024 non e' un backtest
    ottimista, e' un backtest su prezzi di un altro anno. Fuori dalla
    copertura oraria si cammina sulle giornaliere, che partono dal 2000.
    """
    orarie = storico.get(TF.H1, ())
    if orarie and segnale.istante >= orarie[0].orario:
        return TF.H1
    return TF.D1


def simula(
    segnale,
    storico: dict[TF, tuple[Candela, ...]],
    tempi: dict[TF, list],
    contesto,
    giorni_massimi: int = 60,
    estendi: bool = True,
) -> Esito:
    """Cammina in avanti dall'ingresso fino alla chiusura o allo scadere.

    `estendi=False` spegne GEST-08: il target finale resta TP1 e la posizione
    si chiude tutta li'. E' la misura conservativa dell'edge, quella che non
    dipende da quanto lontano un key level superiore porti il residuo.
    """
    direzione = segnale.direzione
    ingresso, stop, obiettivo_1 = segnale.ingresso, segnale.stop, segnale.tp1
    rischio = abs(ingresso - stop)
    if rischio == 0:
        return Esito(segnale, APERTA, 0.0, 0, None)

    erre_tp1 = abs(obiettivo_1 - ingresso) / rischio
    posizione = Posizione(
        strumento=segnale.strumento, direzione=direzione, prezzo_ingresso=ingresso,
        tf_crt=segnale.tf_trigger, livello_stop=stop, tp1=obiettivo_1,
        # SETUP-14: il bersaglio del 75% residuo lo dichiara la decisione, e
        # non coincide con TP1 (REV-49). `estendi=False` lo riporta a TP1 per
        # avere la misura conservativa.
        target_finale=(segnale.target if estendi else obiettivo_1),
    )

    marcia = serie_di_marcia(segnale, storico, tempi)
    barre_serie = storico[marcia]
    partenza = bisect_right(tempi[marcia], segnale.istante)
    per_giorno = 24 if marcia is TF.H1 else 1
    fino_a_barre = giorni_massimi * per_giorno
    superiori = _superiori(segnale.tf_trigger) if estendi else ()
    prossima: dict[TF, int] = {
        tf: bisect_right(tempi[tf], segnale.istante) for tf in superiori if tf in storico
    }

    for passo, barra in enumerate(barre_serie[partenza:partenza + fino_a_barre], start=1):
        # --- GEST-08: il target si estende alla chiusura dei TF superiori ---
        for tf in superiori:
            serie = storico.get(tf, ())
            indice = prossima.get(tf, len(serie))
            while indice < len(serie) and serie[indice].orario <= barra.orario:
                posizione = _estendi(posizione, serie, indice, tf, direzione, contesto)
                indice += 1
            prossima[tf] = indice

        colpito = _colpito(barra, direzione, posizione.livello_stop, posizione.target_finale)

        if not posizione.tp1_raggiunto:
            if colpito == "stop":
                return Esito(segnale, STOP, -1.0, passo, marcia)
            if colpito == "target":
                # Il TP1 e' stato toccato. Se il target finale non e' mai stato
                # esteso coincide con TP1 e la posizione si chiude tutta qui.
                if posizione.target_finale == posizione.tp1:
                    return Esito(segnale, PRIMO, erre_tp1, passo, marcia)
                posizione, _ = applica_tp1(posizione, spread=0.0)
                # Nella stessa barra il prezzo puo' essere tornato all'ingresso:
                # non sappiamo in che ordine, e si prende la lettura peggiore.
                if _tocca(barra, direzione, posizione.livello_stop):
                    return Esito(segnale, PAREGGIO, 0.25 * erre_tp1, passo, marcia)
            continue

        if colpito == "stop":
            return Esito(segnale, PAREGGIO, 0.25 * erre_tp1, passo, marcia)
        if colpito == "target":
            erre_finale = abs(posizione.target_finale - ingresso) / rischio
            return Esito(segnale, TARGET, 0.25 * erre_tp1 + 0.75 * erre_finale, passo, marcia)

    return Esito(segnale, APERTA, 0.0, fino_a_barre, marcia)


def _tocca(barra: Candela, direzione: Bias, livello: float) -> bool:
    if direzione is Bias.SHORT:
        return barra.massimo >= livello
    return barra.minimo <= livello


def _estendi(posizione, serie, indice, tf: TF, direzione: Bias, contesto):
    """GEST-08 — il TF superiore conferma il pattern: il target va al suo key level.

    "Conferma il pattern" significa un CRT nella stessa direzione su quel
    timeframe (REV-26). Il key level a cui si sposta il target e' quello di
    quel timeframe nel verso della bias (DEF-46, SETUP-14): `KL_max` per una
    long, `KL_min` per una short.
    """
    if indice < 2:
        return posizione
    n1, n2 = serie[indice - 1], serie[indice]
    istante = n2.orario
    crt = cerca_crt(n1, n2, tf, contesto(istante))
    massimo, minimo, _ = key_levels(serie[indice - 1], tf)
    bersaglio = massimo if direzione is Bias.LONG else minimo
    return estendi_target(
        posizione, tf, bersaglio,
        crt_formato_su_quel_tf=(crt is not None and crt.direzione is direzione),
    )
