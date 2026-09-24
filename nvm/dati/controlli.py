"""I controlli sui dati: niente si corregge in silenzio.

Ogni anomalia finisce nel rapporto con data e numero (`spec/dati.md`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import SPOSTAMENTO, come_testo, scarti_ny

# Salto massimo credibile fra due minuti consecutivi, in frazione del prezzo.
SALTO_MASSIMO = {"XAUUSD": 0.03}
SALTO_PREDEFINITO = 0.02
# Spread massimo credibile, in frazione del prezzo.
SPREAD_MASSIMO = 0.005
# Un buco a mercato aperto conta se supera questi minuti.
BUCO_MINUTI = 30
# Pause giornaliere note, in secondi dopo le 17:00 di New York.
PAUSA_GIORNALIERA = {"XAUUSD": 3600}


@dataclass
class Anomalia:
    tipo: str
    istante: int
    dettaglio: str

    def __str__(self) -> str:
        return f"{self.tipo:10} {come_testo(self.istante)}  {self.dettaglio}"


@dataclass
class Rapporto:
    strumento: str
    minuti: int
    anomalie: list[Anomalia] = field(default_factory=list)

    @property
    def conteggi(self) -> Counter:
        return Counter(a.tipo for a in self.anomalie)

    def pulito(self) -> bool:
        return not self.anomalie

    def testo(self, esempi: int = 5) -> str:
        righe = [f"{self.strumento}: {self.minuti} minuti, {len(self.anomalie)} anomalie"]
        for tipo, n in sorted(self.conteggi.items()):
            righe.append(f"  {tipo}: {n}")
            for a in [a for a in self.anomalie if a.tipo == tipo][:esempi]:
                righe.append(f"    {a}")
        return "\n".join(righe)


def _sessione(t: np.ndarray) -> np.ndarray:
    """L'ora di New York spostata di 7 ore: le 17:00 diventano mezzanotte (`nvm.tempo`)."""
    return t + scarti_ny(t) + SPOSTAMENTO


def controlla(minuti: Minuti) -> Rapporto:
    rapporto = Rapporto(minuti.strumento, len(minuti))
    if not len(minuti):
        return rapporto
    punto = minuti.punto
    aggiungi = rapporto.anomalie.append

    for lato, p in (("bid", minuti.bid), ("ask", minuti.ask)):
        storte = (p[:, MINIMO] > np.minimum(p[:, APERTURA], p[:, CHIUSURA])) | (
            p[:, MASSIMO] < np.maximum(p[:, APERTURA], p[:, CHIUSURA])
        )
        for i in np.flatnonzero(storte):
            aggiungi(Anomalia("candela", int(minuti.t[i]), f"{lato} O/H/L/C {tuple(p[i])} non coerente"))

    spread = (minuti.ask[:, CHIUSURA] - minuti.bid[:, CHIUSURA]) * punto
    prezzo = minuti.bid[:, CHIUSURA] * punto
    for i in np.flatnonzero(spread < 0):
        aggiungi(Anomalia("spread", int(minuti.t[i]), f"ask sotto bid di {-spread[i]:.5g}"))
    for i in np.flatnonzero(spread > SPREAD_MASSIMO * prezzo):
        aggiungi(Anomalia("spread", int(minuti.t[i]), f"spread {spread[i]:.5g} su prezzo {prezzo[i]:.5g}"))

    soglia = SALTO_MASSIMO.get(minuti.strumento, SALTO_PREDEFINITO)
    salti = np.abs(np.diff(prezzo)) / prezzo[:-1]
    for i in np.flatnonzero(salti > soglia):
        aggiungi(Anomalia("salto", int(minuti.t[i + 1]), f"{prezzo[i]:.5g} -> {prezzo[i + 1]:.5g}"))

    # Il buco si misura sulla linea di sessione, togliendo i fine settimana
    # che attraversa: da venerdi' 17:00 a domenica 17:00 di New York il
    # mercato e' chiuso, e li' i dati non devono esserci.
    sessione = _sessione(minuti.t)
    settimana = (sessione // 86400 + 3) // 7
    fine_settimana = np.diff(settimana)
    aperti = np.diff(sessione) - fine_settimana * 2 * 86400
    # L'oro si ferma ogni giorno dalle 17 alle 18 di New York, cioe' subito
    # dopo ogni mezzanotte di sessione (quella del lunedi' compresa).
    pausa = PAUSA_GIORNALIERA.get(minuti.strumento, 0)
    if pausa:
        mezzanotti = np.diff(sessione // 86400) - 2 * fine_settimana
        aperti = aperti - mezzanotti * pausa
    for i in np.flatnonzero(aperti > BUCO_MINUTI * 60):
        aggiungi(Anomalia("buco", int(minuti.t[i]), f"{aperti[i] // 60} minuti di mercato aperto senza dati"))

    rapporto.anomalie.sort(key=lambda a: a.istante)
    return rapporto
