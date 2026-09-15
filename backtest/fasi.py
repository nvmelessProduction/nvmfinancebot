"""Il modello a fasi di DEF-43, ricostruito dalle barre orarie.

DEF-43 e' **sorveglianza**: vuole i prezzi scambiati fra una chiusura e
l'altra, che un archivio di candele non contiene. Qui si approssima il
percorso di ogni barra con quattro prezzi — apertura, i due estremi
nell'ordine plausibile dato il verso della barra, chiusura — ed e' l'unica
approssimazione che permette a `SETUP-09` di essere valutata invece che
bloccare sempre.

Senza questo passo ogni CRT a supporto di un gap risulterebbe in fase 0, e
`ingresso_da_gap_ammesso` lo escluderebbe: non perche' il setup non ci sia,
ma perche' il dato non c'e'.
"""
from __future__ import annotations

from typing import Optional

from core.definizioni import (
    Bias,
    Candela,
    Gap,
    Mitigazione,
    Polarita,
    StatoFasi,
    avanza_fasi,
    direzione_verso_gap,
    fase_tre_raggiunta,
    mitigazione_attesa,
)
from core.parametri import TF


def percorso(barra: Candela) -> tuple[float, ...]:
    """I prezzi della barra, nell'ordine in cui il mercato li ha plausibilmente visti.

    Barra rialzista: prima il minimo, poi il massimo. Ribassista: il contrario.
    E' la convenzione usuale, e resta un'ipotesi: dentro l'ora l'ordine vero
    non e' ricostruibile da OHLC.
    """
    if barra.chiusura >= barra.apertura:
        return (barra.apertura, barra.minimo, barra.massimo, barra.chiusura)
    return (barra.apertura, barra.massimo, barra.minimo, barra.chiusura)


def identita(gap: Optional[Gap]) -> Optional[tuple]:
    """Due `Gap` con gli stessi estremi e lo stesso timeframe sono lo stesso gap."""
    if gap is None:
        return None
    return (gap.tf, gap.polarita, gap.zona_inf, gap.zona_sup, gap.orario_formazione)


class Sorveglianza:
    """Segue le fasi del gap attivo, barra per barra."""

    def __init__(self) -> None:
        self._gap: Optional[tuple] = None
        self._stato = StatoFasi()
        self._fase_tre = False

    def osserva(self, gap: Optional[Gap], barra: Candela) -> None:
        chiave = identita(gap)
        if chiave != self._gap:
            self._gap, self._stato, self._fase_tre = chiave, StatoFasi(), False
        if gap is None:
            return

        for prezzo in percorso(barra):
            verso = direzione_verso_gap(gap, prezzo)
            if verso is Bias.NESSUNA:
                continue
            if not self._fase_tre and fase_tre_raggiunta(self._stato, prezzo, verso):
                self._fase_tre = True
            self._stato = avanza_fasi(self._stato, gap, verso, prezzo)

    @property
    def fase(self) -> int:
        """La fase corrente. Tre e' definitiva: una volta sbilanciato l'estremo
        della fase 1, il setup e' abilitato finche' il gap resta valido."""
        return 3 if self._fase_tre else self._stato.fase


def mitigazione_del_gap(
    gap: Optional[Gap],
    storico: dict[TF, tuple[Candela, ...]],
) -> Mitigazione:
    """DEF-42 valutata su P3 del gap, che e' la C0 del momento in cui si e' formato."""
    if gap is None:
        return Mitigazione.NON_ATTESA
    serie = storico.get(gap.tf, ())
    for indice in range(len(serie) - 1, 0, -1):
        if serie[indice].orario == gap.orario_formazione:
            return mitigazione_attesa(serie[indice], serie[indice - 1], gap.polarita)
    return Mitigazione.NON_ATTESA
