"""I timeframe e i loro confini: le candele aprono come quelle dei future, alle 18:00 di New York.

Il proprietario, 06/10/2026: *"devono partire come sul futures"*. Sui future (CME) la giornata apre alle
18:00 di New York, cioe' a mezzanotte italiana; fino al 06/10/2026 le nostre candele aprivano alle 17:00
come quelle di MT5, e tre esempi suoi sull'oro a 4 ore erano CRT solo con le candele del future
(`casi/ESEMPI-PROPRIETARIO.md`). Ogni candela sopra il minuto si costruisce da qui:

    giornaliero   apre alle 18:00 di New York del giorno prima
    12 ore        alle 18 e alle 6 di New York
    6 ore         alle 18, 0, 6, 12 di New York
    4 ore         alle 18, 22, 2, 6, 10, 14 di New York
    1h, 15m, 5m   allo scoccare dell'ora o del quarto
    settimanale   da domenica 18:00 a venerdi' di New York
    mensile       la prima giornata di trading del mese
    3, 6, 12 mesi i trimestri (gennaio, aprile, luglio, ottobre), i semestri e l'anno

Il trucco e' una sola linea del tempo "di sessione": l'ora di New York spostata avanti di 6 ore. Li' le
18:00 di New York diventano mezzanotte, e giorni, settimane e mesi di trading si tagliano come quelli del
calendario. L'ora legale la segue `zoneinfo`: i cambi cadono la domenica alle 2 di notte, a mercato chiuso.

Il forex riapre la domenica alle 17:00 di New York, un'ora prima dei future: quell'ora va nella prima
candela della settimana (sabato e domenica di sessione si spostano al lunedi'), cosi' non nasce una
candela di un'ora sola.

Le crypto (`weekend=True`) hanno i loro orari, quelli dei grafici crypto: il proprietario, 08/10/2026,
*"la candela giornaliera delle crypto apre alle 2 e non a 00, quindi la prima candela h4 apre alle
2,6,10,14 e cosi via la prima candela h6 apre alle 2,8 e cosi via e stessa cosa vale per h12 che apre alle
2"*. Le 2 italiane d'estate sono la mezzanotte UTC (d'inverno l'1): per le crypto ogni candela si taglia
sul calendario UTC, sabato e domenica compresi.

    giornaliero   a mezzanotte UTC
    12 ore        a mezzanotte e a mezzogiorno UTC
    6 ore         alle 0, 6, 12, 18 UTC
    4 ore         alle 0, 4, 8, 12, 16, 20 UTC
    settimanale   da lunedi' a mezzanotte UTC, sette giorni
    mensile       dal giorno 1 a mezzanotte UTC; 3, 6, 12 mesi come sopra
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

NEW_YORK = ZoneInfo("America/New_York")
SPOSTAMENTO = 6 * 3600  # 18:00 di New York -> mezzanotte di sessione
# La giornata del forex, per i controlli sui dati (`nvm/dati/controlli.py`): chiude alle 17:00 di New York.
SPOSTAMENTO_FOREX = 7 * 3600


class TF(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    H6 = "H6"
    H12 = "H12"
    D1 = "D1"
    W1 = "W1"
    MN = "MN"
    Q3 = "3M"
    S6 = "6M"
    Y1 = "12M"


# Timeframe che si tagliano a passo fisso sulla linea di sessione.
PASSO = {
    TF.M1: 60,
    TF.M5: 300,
    TF.M15: 900,
    TF.H1: 3600,
    TF.H4: 4 * 3600,
    TF.H6: 6 * 3600,
    TF.H12: 12 * 3600,
    TF.D1: 86400,
}
# Quanti mesi dura una candela dei timeframe del calendario.
MESI = {TF.MN: 1, TF.Q3: 3, TF.S6: 6, TF.Y1: 12}
# Dal piu' piccolo al piu' grande: per dire quale timeframe sta sopra a un altro.
ORDINE = (TF.M1, TF.M5, TF.M15, TF.H1, TF.H4, TF.H6, TF.H12, TF.D1, TF.W1, TF.MN, TF.Q3, TF.S6, TF.Y1)


def sopra_a(tf: TF) -> tuple[TF, ...]:
    """I timeframe piu' grandi di `tf`, dal piu' vicino."""
    return ORDINE[ORDINE.index(tf) + 1:]


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


def _al_lunedi(sessione: np.ndarray) -> np.ndarray:
    """Sabato e domenica di sessione vanno al lunedi' a mezzanotte di sessione (la domenica alle 18 di NY)."""
    giorno = sessione // 86400
    # Il 1/1/1970 era giovedi': (giorno + 3) % 7 e' 0 di lunedi'.
    dow = (giorno + 3) % 7
    return np.where(dow >= 5, (giorno + 7 - dow) * 86400, sessione)


def _inizio_mese(giorni: np.ndarray, mesi_per_candela: int) -> np.ndarray:
    """Il primo giorno (in giorni dal 1/1/1970) del mese, trimestre, semestre o anno che contiene ogni giorno."""
    mesi = giorni.astype("datetime64[D]").astype("datetime64[M]").astype(np.int64)
    mesi = mesi - mesi % mesi_per_candela      # 1970-01 e' il mese 0: trimestri e semestri partono da gennaio
    return mesi.astype("datetime64[M]").astype("datetime64[D]").astype(np.int64)


def _inizio_crypto(t_utc: np.ndarray, tf: TF) -> np.ndarray:
    """Le candele delle crypto: il calendario UTC (vedi in cima)."""
    if tf in PASSO:
        return t_utc - t_utc % PASSO[tf]
    giorno = t_utc // 86400
    if tf is TF.W1:
        # Il 1/1/1970 era giovedi': (giorno + 3) % 7 e' 0 di lunedi'.
        return (giorno - (giorno + 3) % 7) * 86400
    return _inizio_mese(giorno, MESI[tf]) * 86400


def inizio_candela(t_utc: np.ndarray, tf: TF, weekend: bool = False) -> np.ndarray:
    """L'istante UTC in cui apre la candela `tf` che contiene ogni istante.

    `weekend`: lo strumento e' una crypto (scambia anche sabato e domenica, candele sul calendario UTC)."""
    t_utc = np.asarray(t_utc, dtype=np.int64)
    if tf in (TF.M1, TF.M5, TF.M15, TF.H1):
        # Gli scarti di New York sono ore intere: questi confini coincidono
        # con quelli UTC.
        passo = PASSO[tf]
        return t_utc - t_utc % passo
    if weekend:
        return _inizio_crypto(t_utc, tf)

    sessione = _al_lunedi(t_utc + scarti_ny(t_utc) + SPOSTAMENTO)
    if tf in (TF.H4, TF.H6, TF.H12, TF.D1):
        passo = PASSO[tf]
        inizio = sessione - sessione % passo
    elif tf is TF.W1:
        giorno = sessione // 86400
        inizio = (giorno - (giorno + 3) % 7) * 86400
    elif tf in MESI:
        inizio = _inizio_mese(sessione // 86400, MESI[tf]) * 86400
    else:  # pragma: no cover - enum chiuso
        raise ValueError(tf)

    uniche, indici = np.unique(inizio, return_inverse=True)
    utc = np.fromiter((_utc_da_sessione(int(s)) for s in uniche), dtype=np.int64, count=len(uniche))
    return utc[indici]


def fine_candela(inizio_utc: int, tf: TF, weekend: bool = False) -> int:
    """L'istante UTC in cui chiude la candela `tf` che apre a `inizio_utc`."""
    if tf in (TF.M1, TF.M5, TF.M15, TF.H1):
        return inizio_utc + PASSO[tf]
    if weekend:
        # Le crypto: il calendario UTC, sette giorni su sette.
        if tf in PASSO:
            return inizio_utc + PASSO[tf]
        if tf is TF.W1:
            return inizio_utc + 7 * 86400
        return int(_mese_dopo(inizio_utc // 86400, MESI[tf])) * 86400
    sessione = inizio_utc + _scarto_ny(inizio_utc // 3600) + SPOSTAMENTO
    if tf in PASSO:
        return _utc_da_sessione(sessione + PASSO[tf])
    if tf is TF.W1:
        # La settimana di trading finisce venerdi' sera (5 giorni di sessione dopo l'apertura di domenica).
        return _utc_da_sessione(sessione + 5 * 86400)
    return _utc_da_sessione(int(_mese_dopo(sessione // 86400, MESI[tf])) * 86400)


def _mese_dopo(giorno: int, mesi: int) -> int:
    """Il primo giorno (in giorni dal 1/1/1970) `mesi` mesi dopo il mese che contiene `giorno`."""
    g = np.datetime64(int(giorno), "D")
    return int((g.astype("datetime64[M]") + mesi).astype("datetime64[D]").astype(np.int64))


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
