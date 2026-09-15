"""Una memoria per i gap, valida solo dentro il backtest.

`gap_del_timeframe` scorre tutte le terne e per ognuna controlla se una
candela successiva l'ha invalidata: e' quadratico, e su 1.300 giornaliere fa
circa 1,7 milioni di confronti. Il motore lo paga una volta per chiusura di
candela e non se ne accorge; il backtest lo paga 26.000 volte.

I gap si calcolano **solo** sui timeframe di `TF_BIAS` (`ordine_scansione_gap`
con la lettura adottata per REV-15), quindi fra una chiusura giornaliera e la
successiva non possono cambiare. La memoria tiene un risultato solo, quello
dell'ultima chiave vista: la scansione va in avanti nel tempo e non torna
indietro.

Non cambia nessun risultato — e' la stessa funzione, chiamata meno volte.
"""
from __future__ import annotations

import core.stato as stato


def memoizza_gap(chiave_di) -> None:
    """Sostituisce `stato.gap_per_timeframe` con una versione che ricorda.

    `chiave_di(istante)` deve restituire qualcosa che cambia esattamente
    quando cambia lo stato dei timeframe di contesto.
    """
    vero = stato.gap_per_timeframe
    ultima: dict = {}

    def veloce(storico, istante):
        chiave = chiave_di(istante)
        if ultima.get("chiave") != chiave:
            ultima["chiave"] = chiave
            ultima["valore"] = vero(storico, istante)
        return ultima["valore"]

    stato.gap_per_timeframe = veloce
