"""Gli strumenti che il bot conosce, in una tabella sola: le altre si ricavano da qui.

I sei di partenza sono quelli di Romeo e del bot dal vivo (`BASE`). Dal
25/09/2026 (l'utente: *"utilizzando tutti i grafici/pair che ci danno"*) il
bot conosce anche le altre coppie fra le otto valute principali: 28 coppie
forex e l'oro. Servono per imparare da piu' mercati; dal vivo si opera su
quelle scelte in `vivo.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Strumento:
    nome: str
    punto: float        # il divisore dei prezzi di Dukascopy
    pip: float
    cifre: int          # i decimali con cui si scrive un prezzo
    commissione: float  # un giro (apertura e chiusura), in prezzo per unita': circa 7 dollari a lotto


def _coppia(base: str, quota: str) -> Strumento:
    yen = quota == "JPY"
    pip = 0.01 if yen else 0.0001
    return Strumento(base + quota, 1e-3 if yen else 1e-5, pip, 3 if yen else 5, round(0.7 * pip, 8))


# Le otto valute nell'ordine con cui il mercato scrive le coppie (EURUSD, non USDEUR).
VALUTE = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")
ORO = Strumento("XAUUSD", 1e-3, 1.0, 2, 0.07)
BASE = ("EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD")

_TUTTE = {s.nome: s for s in [_coppia(a, b) for i, a in enumerate(VALUTE) for b in VALUTE[i + 1:]] + [ORO]}
# Prima i sei di partenza, nel loro ordine; poi le altre.
STRUMENTI: dict[str, Strumento] = {n: _TUTTE[n] for n in BASE} | {n: s for n, s in _TUTTE.items() if n not in BASE}
NUOVI = tuple(n for n in STRUMENTI if n not in BASE)
