"""Ripercorre lo storico barra per barra e raccoglie le decisioni del motore.

Usa `core.motore.valuta` senza toccarlo: se il motore non opererebbe, qui non
si opera. L'unica liberta' presa e' sul calcolo, non sulle regole.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterator, Optional, Sequence

from core import motore
from core.definizioni import Bias, Candela
from core.parametri import TF, TF_BIAS, UNIVERSO
from core.stato import Conto, costruisci_fotografia

from archivio import finestra, indice_temporale
from fasi import Sorveglianza, mitigazione_del_gap

# Quante candele per timeframe restano visibili. Tagliate per coprire
# LOOKBACK_ANNI = 5 senza rendere quadratico il costo su ventisei anni.
FINESTRA = {
    TF.M12: 8, TF.M6: 12, TF.M3: 24, TF.M1: 70,
    TF.W1: 300, TF.D1: 1300, TF.H4: 40, TF.H1: 40,
}


@dataclass(frozen=True)
class Segnale:
    strumento: str
    tf_trigger: TF
    istante: datetime
    direzione: Bias
    ingresso: float
    stop: float
    tp1: float
    rapporto: float


def _chiave_contesto(tempi, istante: datetime) -> tuple:
    """Quante candele di ogni timeframe di contesto sono chiuse ora.

    Bias, key level, sbilanciamenti e gap si calcolano solo sui timeframe di
    `TF_BIAS`: fra una chiusura giornaliera e la successiva non possono
    cambiare. La chiave dice quando vale la pena ricalcolarli.
    """
    return tuple(bisect_right(tempi.get(tf, ()), istante) for tf in TF_BIAS)


def scansiona(
    strumento: str,
    storico: dict[TF, tuple[Candela, ...]],
    trigger: Sequence[TF],
    equity: float = 100_000.0,
) -> Iterator[Segnale]:
    """Ogni chiusura di candela dei timeframe trigger, in ordine di tempo."""
    tempi = indice_temporale(storico)
    istanti: list[tuple[datetime, TF]] = []
    for tf in trigger:
        istanti.extend((c.orario, tf) for c in storico.get(tf, ()))
    istanti.sort(key=lambda coppia: (coppia[0], coppia[1].value))

    cache_chiave: Optional[tuple] = None
    contesto: Optional[motore.Fotografia] = None
    sorveglianza = Sorveglianza()
    mitigazione = None
    ultima_oraria = -1
    orarie = storico.get(TF.H1, ())

    for istante, tf in istanti:
        chiave = _chiave_contesto(tempi, istante)
        if chiave != cache_chiave:
            ridotto = {
                t: finestra(storico[t], tempi[t], istante, FINESTRA[t])
                for t in FINESTRA
                if t in storico
            }
            contesto = costruisci_fotografia(
                istante=istante,
                strumento=strumento,
                storico=ridotto,
                conto=Conto(equity=equity, prezzo_cfd=1.0, valore_punto=1.0),
                eventi_news=(),
                eta_calendario_ore=0.0,
            )
            mitigazione = mitigazione_del_gap(contesto.gap_attivo, ridotto)
            cache_chiave = chiave

        assert contesto is not None

        # Le fasi del gap avanzano sulle barre orarie, che sono la grana piu'
        # fine disponibile: vanno consumate tutte, anche quando il trigger che
        # stiamo valutando e' giornaliero.
        fino_a = bisect_right(tempi[TF.H1], istante)
        while ultima_oraria + 1 < fino_a:
            ultima_oraria += 1
            sorveglianza.osserva(contesto.gap_attivo, orarie[ultima_oraria])
        recenti = finestra(storico[tf], tempi[tf], istante, 2)
        if len(recenti) < 2:
            continue

        foto = replace(
            contesto,
            istante=istante,
            candele_per_tf={tf: recenti},
            prezzo_cfd=recenti[-1].chiusura,   # ingresso = chiusura di N2
            gap_fase=sorveglianza.fase,
            mitigazione=mitigazione,
        )
        decisione = motore.valuta(foto, tf)
        if decisione.azione == "NONE":
            continue

        yield Segnale(
            strumento=strumento,
            tf_trigger=tf,
            istante=istante,
            direzione=decisione.direzione,      # type: ignore[arg-type]
            ingresso=foto.prezzo_cfd,
            stop=decisione.livello_stop,        # type: ignore[arg-type]
            tp1=decisione.tp1,                  # type: ignore[arg-type]
            rapporto=decisione.rapporto_su_tp1, # type: ignore[arg-type]
        )
