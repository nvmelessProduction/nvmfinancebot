"""Traduzione fra i nomi di TradingView, i future di analisi e i CFD operativi.

Tre mondi con tre nomi diversi per la stessa cosa, e `ESCL-12` vieta di
confonderli:

```
TradingView   il ticker del grafico future:  GC1!, 6E1!, CME_MINI:...
analisi       il codice di PRIN-08:          GC, 6E, 6B, 6A, 6S, 6J
esecuzione    il simbolo CFD su FP Markets:  XAUUSD, EURUSD, ... (+ suffisso)
```

Il bot **analizza sul future e opera sul CFD** (`DEF-32`, `DEF-33`, `DEF-34`).
Questo file e' l'unico posto in cui i tre nomi si incontrano, e non converte
mai un **prezzo**: solo un nome.
"""

from __future__ import annotations

import re
from typing import Optional

from core.parametri import TF, UNIVERSO

# Il ticker che TradingView mette in `{{ticker}}` puo' portare il prefisso
# dell'exchange e il suffisso del contratto continuo.
#   COMEX:GC1!  ->  GC        CME:6E1!  ->  6E        6J2!  ->  6J
_PULIZIA = re.compile(r"^(?:[A-Z_]+:)?([A-Z0-9]+?)(?:\d*!)?$")

# Future di analisi -> CFD di esecuzione (PRIN-08, DEF-33).
FUTURE_A_CFD: dict[str, str] = {
    dati.future: dati.cfd for dati in UNIVERSO.values()
}

# Lo strumento di sola analisi: il DXY non si opera mai (PRIN-08).
DXY_FUTURE: str = "ICEUS"
SOLO_ANALISI: frozenset[str] = frozenset({DXY_FUTURE, "DXY", "DX"})

# Intervallo dell'alert TradingView -> timeframe di DEF-01.
# `{{interval}}` restituisce i minuti per gli intraday, e D/W/M per gli altri.
INTERVALLO_A_TF: dict[str, TF] = {
    "60": TF.H1, "1H": TF.H1, "H1": TF.H1,
    "240": TF.H4, "4H": TF.H4, "H4": TF.H4,
    "360": TF.H6, "6H": TF.H6, "H6": TF.H6,
    "720": TF.H12, "12H": TF.H12, "H12": TF.H12,
    "1D": TF.D1, "D": TF.D1, "1440": TF.D1,
    "1W": TF.W1, "W": TF.W1,
    "1M": TF.M1, "M": TF.M1,
    "3M": TF.M3, "6M": TF.M6, "12M": TF.M12,
}


def future_da_ticker(ticker: str) -> Optional[str]:
    """Il codice di PRIN-08 a partire dal ticker di TradingView.

    None se il ticker non corrisponde a nessuno strumento noto: un alert su
    uno strumento fuori da PRIN-08 va ignorato, non interpretato (ESCL-05).
    """
    corrispondenza = _PULIZIA.match(ticker.strip().upper())
    if corrispondenza is None:
        return None
    nudo = corrispondenza.group(1)
    if nudo in FUTURE_A_CFD or nudo in SOLO_ANALISI:
        return nudo
    return None


def e_solo_analisi(future: str) -> bool:
    """True per il DXY, che si analizza e non si opera mai (PRIN-08)."""
    return future in SOLO_ANALISI


def cfd_di(future: str) -> Optional[str]:
    """Il CFD su cui si opera, dato il future su cui si e' analizzato."""
    return FUTURE_A_CFD.get(future)


def future_di(cfd: str) -> Optional[str]:
    """Il future su cui si analizza, dato il CFD."""
    dati = UNIVERSO.get(cfd)
    return dati.future if dati else None


def timeframe_da_intervallo(intervallo: str) -> Optional[TF]:
    """Il timeframe di DEF-01 a partire da `{{interval}}` di TradingView.

    None se l'intervallo non e' fra i dieci ammessi: `DEF-01` dice che nessun
    altro timeframe puo' essere citato da nessuna regola, quindi un alert a
    cinque minuti non innesca e non archivia nulla.
    """
    return INTERVALLO_A_TF.get(intervallo.strip().upper())


def simbolo_esecuzione(cfd: str, suffisso: str = "") -> str:
    """Il nome con cui il broker conosce il CFD.

    Alcuni broker aggiungono un suffisso (`EURUSD.a`, `XAUUSD.pro`). Si
    scopre con `python prova_esecuzione.py` e si mette in `MT5_SUFFISSO_SIMBOLI`.
    """
    return f"{cfd}{suffisso}" if suffisso else cfd


def cfd_da_simbolo_esecuzione(simbolo: str, suffisso: str = "") -> Optional[str]:
    """L'inversa di `simbolo_esecuzione`: dal nome del broker al CFD di PRIN-08.

    Serve a rileggere cio' che torna dal broker. MT5 restituisce le posizioni
    col nome **suffissato** (`EURUSD.a`), mentre RISK-02, RISK-06 ed ESCL-11
    contano posizioni per strumento dell'`UNIVERSO`, che e' scritto coi nomi
    nudi. Senza questa conversione, con un suffisso configurato:

    - `posizioni_aperte_per_strumento[strumento]` e' sempre 0, quindi il tetto
      di RISK-06 e il divieto ESCL-11 non scattano mai;
    - `n` dentro il gruppo di correlazione e' sempre 1, quindi RISK-02 applica
      sempre l'1,00% pieno e la scala 0,75/0,45 non entra mai in funzione.

    Nessuna delle due cose lascia traccia nei log: il conteggio e' semplicemente
    vuoto, e il motore lo legge come "nessuna posizione aperta".

    None se il nome non corrisponde ad alcuno strumento dell'`UNIVERSO`: puo'
    succedere legittimamente, se sul conto c'e' una posizione aperta a mano su
    uno strumento che il bot non tratta. Chi chiama la scarta.
    """
    nudo = simbolo
    if suffisso and simbolo.endswith(suffisso):
        nudo = simbolo[: -len(suffisso)]
    return nudo if nudo in UNIVERSO else None
