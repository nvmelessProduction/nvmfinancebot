"""Gli strumenti che il bot conosce, in una tabella sola: le altre si ricavano da qui.

I sei di partenza sono quelli di Romeo e del bot dal vivo (`BASE`). Dal
25/09/2026 (l'utente: *"utilizzando tutti i grafici/pair che ci danno"*;
*"aggiungi anche gli indici, le crypto come btcusd e ethusd, e anche
petrolio e argento"*) il bot conosce anche le altre 23 coppie fra le otto
valute principali, l'argento, il petrolio (WTI e Brent), sei indici e due
crypto. Servono per imparare da piu' mercati; dal vivo si opera su quelli
scelti in `vivo.py` che il broker ha.

Ogni broker chiama alcuni strumenti a modo suo (l'S&P 500 e' US500, SPX500,
US500.cash...): `mt5` elenca i nomi da provare, e il bot usa il primo che
il conto ha.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Strumento:
    nome: str
    punto: float        # il divisore dei prezzi di Dukascopy
    pip: float
    cifre: int          # i decimali con cui si scrive un prezzo
    commissione: float  # un giro (apertura e chiusura), in prezzo per unita': circa 7 dollari a lotto sul forex
    famiglia: str = "forex"
    dukascopy: str = ""  # il nome sul datafeed di Dukascopy, se diverso
    mt5: tuple = ()      # altri nomi con cui i broker lo chiamano su MetaTrader

    @property
    def codice(self) -> str:
        return self.dukascopy or self.nome


def _coppia(base: str, quota: str) -> Strumento:
    yen = quota == "JPY"
    pip = 0.01 if yen else 0.0001
    return Strumento(base + quota, 1e-3 if yen else 1e-5, pip, 3 if yen else 5, round(0.7 * pip, 8))


# Le otto valute nell'ordine con cui il mercato scrive le coppie (EURUSD, non USDEUR).
VALUTE = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")
BASE = ("EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD")

# Materie prime, indici e crypto: sui conti CFD di solito non c'e' commissione, solo lo spread
# (che il bot misura dai prezzi bid e ask). Il divisore di Dukascopy e' verificato il 25/09/2026 su
# un mese di ore di ognuno (per esempio marzo 2023: Dow 32.575, Nikkei 27.370, DAX 15.330, FTSE
# 7.858, Nasdaq 11.996, BTC 23.103, ETH 1.602; marzo 2012: argento 34,83, WTI 107,01, Brent 122,88,
# S&P 500 1.365,68). Su Dukascopy le crypto partono nel 2017, alcuni indici dopo il 2012.
ALTRI = (
    Strumento("XAUUSD", 1e-3, 1.0, 2, 0.07, "metalli", mt5=("GOLD",)),
    Strumento("XAGUSD", 1e-3, 0.01, 3, 0.0, "metalli", mt5=("SILVER",)),
    # Il platino, dal 20/10/2026 (il proprietario: *"aggiungiamo xptusd"*): come l'oro, quotato in dollari.
    Strumento("XPTUSD", 1e-3, 0.1, 2, 0.0, "metalli", mt5=("PLATINUM", "XPTUSD.")),
    Strumento("USOIL", 1e-3, 0.01, 3, 0.0, "petrolio", "LIGHTCMDUSD", ("XTIUSD", "WTI", "USOUSD", "WTIUSD", "CL-OIL")),
    Strumento("UKOIL", 1e-3, 0.01, 3, 0.0, "petrolio", "BRENTCMDUSD", ("XBRUSD", "BRENT", "UKOUSD", "BRENTUSD")),
    Strumento("SPX500", 1e-3, 1.0, 2, 0.0, "indici", "USA500IDXUSD", ("US500", "US500.cash", "SP500", "USA500", "US500Cash")),
    Strumento("NAS100", 1e-3, 1.0, 2, 0.0, "indici", "USATECHIDXUSD", ("US100", "USTEC", "NDX100", "US100.cash", "USTECH")),
    Strumento("US30", 1e-3, 1.0, 2, 0.0, "indici", "USA30IDXUSD", ("DJ30", "WS30", "US30.cash", "DOW30", "USA30")),
    Strumento("GER40", 1e-3, 1.0, 2, 0.0, "indici", "DEUIDXEUR", ("DE40", "GER30", "DAX40", "DE30", "GER40.cash")),
    Strumento("UK100", 1e-3, 1.0, 2, 0.0, "indici", "GBRIDXGBP", ("FTSE100", "UK100.cash")),
    Strumento("JPN225", 1e-3, 1.0, 2, 0.0, "indici", "JPNIDXJPY", ("JP225", "NIKKEI225", "JPN225.cash")),
    Strumento("BTCUSD", 1e-1, 1.0, 2, 0.0, "crypto", mt5=("BTCUSDT", "BITCOIN")),
    Strumento("ETHUSD", 1e-1, 1.0, 2, 0.0, "crypto", mt5=("ETHUSDT", "ETHEREUM")),
)

_TUTTE = {s.nome: s for s in [_coppia(a, b) for i, a in enumerate(VALUTE) for b in VALUTE[i + 1:]] + list(ALTRI)}
# Prima i sei di partenza, nel loro ordine; poi le altre coppie; poi il resto.
STRUMENTI: dict[str, Strumento] = {n: _TUTTE[n] for n in BASE} | {n: s for n, s in _TUTTE.items() if n not in BASE}
NUOVI = tuple(n for n in STRUMENTI if n not in BASE)
COPPIE_NUOVE = tuple(n for n in NUOVI if STRUMENTI[n].famiglia == "forex")
ALTRI_NUOVI = tuple(n for n in NUOVI if STRUMENTI[n].famiglia != "forex")
