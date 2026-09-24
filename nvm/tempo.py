"""I timeframe e i loro confini: la giornata chiude alle 17:00 di New York.

Regola in `spec/dati.md`. Ogni candela sopra il minuto si costruisce da qui,
con un solo modo di tagliare il tempo:

    giornaliero   apre alle 17:00 di New York del giorno prima
    4 ore         apre alle 17, 21, 1, 5, 9, 13 di New York
    1h, 15m, 5m   allo scoccare dell'ora o del quarto
    settimanale   da domenica 17:00 a venerdi' 17:00 di New York
    mensile       la prima giornata di trading del mese

Il trucco e' una sola linea del tempo "di sessione": l'ora di New York
spostata avanti di 7 ore. Li' le 17:00 di New York diventano mezzanotte, e
giorni, settimane e mesi di trading si tagliano come quelli del calendario.
L'ora legale la segue `zoneinfo`: i cambi cadono la domenica alle 2 di
notte, a mercato chiuso, quindi nessuna candela di trading ne attraversa
uno.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

NEW_YORK = ZoneInfo("America/New_York")
SPOSTAMENTO = 7 * 3600  # 17:00 di New York -> mezzanotte di sessione


class TF(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN = "MN"


# Timeframe che si tagliano a passo fisso sulla linea di sessione.
PASSO = {
    TF.M1: 60,
    TF.M5: 300,
    TF.M15: 900,
    TF.H1: 3600,
    TF.H4: 4 * 3600,
    TF.D1: 86400,
}


@lru_cache(maxsize=None)
def _scarto_ny(ora_utc: int) -> int:
    """Secondi da aggiungere all'UTC per avere l'ora di New York, per un'ora UTC."""
    istante = datetime.fromtimestamp(ora_utc * 3600, tz=timezone.utc)
    return int(istante.astimezone(NEW_YORK).utcoffset().total_seconds())


def scarti_ny(t_utc: np.ndarray) -> np.ndarray:
    """Lo scarto di New York (secondi) per ogni istante UTC, in blocco.

    Gli scarti cambiano solo allo scoccare di un'ora, quindi basta calcolarli
    una volta per ogni ora distinta.
    """
    ore = t_utc // 3600
    uniche, indici = np.unique(ore, return_inverse=True)
    scarti = np.fromiter((_scarto_ny(int(o)) for o in uniche), dtype=np.int64, count=len(uniche))
    return scarti[indici]


def _utc_da_sessione(sessione: int) -> int:
    """Da un istante sulla linea di sessione all'istante UTC corrispondente."""
    locale = datetime(1970, 1, 1) + timedelta(seconds=sessione - SPOSTAMENTO)
    return int(locale.replace(tzinfo=NEW_YORK).timestamp())


def inizio_candela(t_utc: np.ndarray, tf: TF) -> np.ndarray:
    """L'istante UTC in cui apre la candela `tf` che contiene ogni istante."""
    t_utc = np.asarray(t_utc, dtype=np.int64)
    if tf in (TF.M1, TF.M5, TF.M15, TF.H1):
        # Gli scarti di New York sono ore intere: questi confini coincidono
        # con quelli UTC.
        passo = PASSO[tf]
        return t_utc - t_utc % passo

    sessione = t_utc + scarti_ny(t_utc) + SPOSTAMENTO
    if tf in (TF.H4, TF.D1):
        passo = PASSO[tf]
        inizio = sessione - sessione % passo
    elif tf is TF.W1:
        giorno = sessione // 86400
        # Il 1/1/1970 era giovedi': (giorno + 3) % 7 e' 0 di lunedi'.
        inizio = (giorno - (giorno + 3) % 7) * 86400
    elif tf is TF.MN:
        giorni = (sessione // 86400).astype("datetime64[D]")
        inizio = giorni.astype("datetime64[M]").astype("datetime64[D]").astype(np.int64) * 86400
    else:  # pragma: no cover - enum chiuso
        raise ValueError(tf)

    uniche, indici = np.unique(inizio, return_inverse=True)
    utc = np.fromiter((_utc_da_sessione(int(s)) for s in uniche), dtype=np.int64, count=len(uniche))
    return utc[indici]


def fine_candela(inizio_utc: int, tf: TF) -> int:
    """L'istante UTC in cui chiude la candela `tf` che apre a `inizio_utc`."""
    if tf in (TF.M1, TF.M5, TF.M15, TF.H1):
        return inizio_utc + PASSO[tf]
    sessione = inizio_utc + _scarto_ny(inizio_utc // 3600) + SPOSTAMENTO
    if tf in (TF.H4, TF.D1):
        return _utc_da_sessione(sessione + PASSO[tf])
    if tf is TF.W1:
        # La settimana di trading finisce venerdi' alle 17:00 di New York,
        # cioe' 5 giorni di sessione dopo l'apertura di domenica sera.
        return _utc_da_sessione(sessione + 5 * 86400)
    giorno = np.datetime64(sessione // 86400, "D")
    mese_dopo = (giorno.astype("datetime64[M]") + 1).astype("datetime64[D]")
    return _utc_da_sessione(int(mese_dopo.astype(np.int64)) * 86400)


def come_testo(t_utc: int) -> str:
    """Un istante UTC scritto per chi legge: '2026-09-10 05:00 NY'."""
    ny = datetime.fromtimestamp(int(t_utc), tz=timezone.utc).astimezone(NEW_YORK)
    return ny.strftime("%Y-%m-%d %H:%M NY")


def utc(anno: int, mese: int, giorno: int, ora: int = 0, minuto: int = 0) -> int:
    """Un istante UTC in secondi. Comodo nei test."""
    return int(datetime(anno, mese, giorno, ora, minuto, tzinfo=timezone.utc).timestamp())


def ny(anno: int, mese: int, giorno: int, ora: int = 0, minuto: int = 0) -> int:
    """Un'ora di New York, restituita in secondi UTC. Comodo nei test."""
    return int(datetime(anno, mese, giorno, ora, minuto, tzinfo=NEW_YORK).timestamp())
