"""Il rischio di `docs/05_rischio.md`: size, limiti, esposizione.

E' il file che decide quanto si mette a mercato. Per `PREC-01` batte
`03_setup.md`: se un limite e' raggiunto, nessun setup valido viene eseguito,
su nessuno strumento.

**La distanza di stop si misura interamente sul future** (DEF-47 come corretta
da PA-62). Il CFD entra solo con `valore_punto`, che e' un moltiplicatore
monetario e non un prezzo: cosi' `ESCL-12` resta rispettata. Il fattore `k`
costante che DEF-47 prevedeva non puo' esistere per `6J` e `6S`, che quotano il
reciproco del rispettivo CFD — vedi `docs/DECISIONI-2026-09-03.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from core.parametri import (
    LIMITE_GIORNALIERO,
    LIMITE_MENSILE,
    LIMITE_SETTIMANALE,
    MAX_POSIZIONI_PER_STRUMENTO,
    UNIVERSO,
    distanza_relativa_stop,
    gruppo_di,
    posizioni_ridimensionate,
    richiedi,
    rischio_per_posizione,
)


@dataclass(frozen=True)
class EsitoSize:
    """Il risultato del calcolo della size, sempre spiegato.

    `lotti` a None significa che non si opera, e `motivo` dice perche'.
    """

    lotti: Optional[float]
    rischio_percentuale: float
    distanza_relativa: Optional[float]
    motivo: str


# ===========================================================================
# RISK-01, RISK-02, RISK-06 — rischio per posizione
# ===========================================================================


def posizioni_nel_gruppo(
    strumento: str,
    posizioni_aperte_per_strumento: Mapping[str, int],
) -> int:
    """RISK-02 — Quante posizioni conta `n`, per REV-03.

    `n` si conta **dentro il gruppo di correlazione**: le cinque coppie forex
    formano un gruppo unico perche' derivano tutte dal DXY; `XAUUSD` un gruppo
    proprio, perche' quattro posizioni sullo stesso strumento sono correlate
    in modo totale — sono lo stesso strumento.
    """
    gruppo = gruppo_di(strumento)
    return sum(
        quante
        for altro, quante in posizioni_aperte_per_strumento.items()
        if altro in UNIVERSO and gruppo_di(altro) == gruppo
    )


def rischio_del_prossimo_ordine(
    strumento: str,
    posizioni_aperte_per_strumento: Mapping[str, int],
) -> float:
    """RISK-02 — Rischio percentuale della posizione che si sta per aprire.

    `n` conta le posizioni gia' aperte nel gruppo **piu' quella in
    valutazione**, come dice RISK-02.
    """
    n = posizioni_nel_gruppo(strumento, posizioni_aperte_per_strumento) + 1
    return rischio_per_posizione(n, strumento)


def esposizione_del_gruppo(
    strumento: str,
    posizioni_aperte_per_strumento: Mapping[str, int],
    inclusa_la_nuova: bool = True,
) -> float:
    """RISK-02 e RISK-06 — Rischio aggregato del gruppo di correlazione.

    Con il ridimensionamento attivo (REV-42) tutte le posizioni del gruppo
    rischiano la stessa percentuale, quindi l'esposizione e' `n x rischio(n)`.
    Senza, sarebbe la somma di quanto ciascuna rischiava al proprio ingresso,
    che e' un numero piu' alto: e' la differenza fra 1,80% e 2,65% su quattro
    posizioni.
    """
    n = posizioni_nel_gruppo(strumento, posizioni_aperte_per_strumento)
    if inclusa_la_nuova:
        n += 1
    if n == 0:
        return 0.0
    if posizioni_ridimensionate():
        return n * rischio_per_posizione(n, strumento)
    # Lettura alternativa: ciascuna conserva il rischio del proprio ingresso.
    return sum(rischio_per_posizione(i, strumento) for i in range(1, n + 1))


def tetto_posizioni_raggiunto(posizioni_sullo_strumento: int) -> bool:
    """RISK-06 ed ESCL-11 — Massimo quattro posizioni per singolo strumento."""
    return posizioni_sullo_strumento >= MAX_POSIZIONI_PER_STRUMENTO


# ===========================================================================
# RISK-03, RISK-04, DEF-47 — la size
# ===========================================================================


def _arrotonda_per_difetto(lotti: float, passo: float) -> float:
    """RISK-03 — Arrotondamento per difetto al passo minimo del broker.

    Sempre per difetto: se produce zero, l'operazione non viene eseguita.
    Arrotondare per eccesso significherebbe rischiare piu' del dichiarato.
    """
    if passo <= 0:
        raise ValueError(f"passo del broker non valido: {passo}")
    decimali = max(0, len(f"{passo:.10f}".rstrip("0").split(".")[-1]))
    return round(math.floor(lotti / passo) * passo, decimali)


def calcola_size(
    equity: float,
    strumento: str,
    chiusura_n2_future: float,
    stop_future: float,
    prezzo_cfd: float,
    valore_punto: float,
    passo_broker: float,
    posizioni_aperte_per_strumento: Mapping[str, int],
    doppio_ingresso: bool = False,
) -> EsitoSize:
    """RISK-03 e DEF-47 — Size in lotti, con la distanza misurata sul future.

    I tre passi, nell'ordine:

    1. distanza di stop **adimensionale** sul future: `r = |N2 - stop| / N2`;
    2. distanza in punti sul CFD: `r x prezzo_cfd`;
    3. lotti = (equity x rischio) / (distanza_cfd x valore_punto), arrotondati
       per difetto al passo del broker.

    Nessun prezzo future viene confrontato con un prezzo CFD: `r` e' un numero
    puro. Su `6J` e `6S`, che quotano il reciproco del CFD, una variazione
    relativa sul future e' una variazione relativa uguale sul CFD al primo
    ordine, con il segno che gestisce gia' DEF-33.

    `doppio_ingresso` dimezza il rischio, non lo raddoppia (RISK-04): due
    ingressi da meta' rischio, non due a rischio pieno.
    """
    if equity <= 0:
        return EsitoSize(None, 0.0, None, "PRIN-99: equity non positiva")
    if prezzo_cfd <= 0 or valore_punto <= 0:
        return EsitoSize(None, 0.0, None, "PRIN-99: prezzo CFD o valore punto non validi")

    try:
        relativa = distanza_relativa_stop(chiusura_n2_future, stop_future)
    except ValueError as errore:
        # RISK-03: distanza nulla o prezzo non valido e' dato incoerente.
        return EsitoSize(None, 0.0, None, f"PRIN-99: {errore}")

    rischio = rischio_del_prossimo_ordine(strumento, posizioni_aperte_per_strumento)
    if doppio_ingresso:
        rischio /= 2                                        # RISK-04

    distanza_cfd = relativa * prezzo_cfd
    lotti_esatti = (equity * rischio) / (distanza_cfd * valore_punto)
    lotti = _arrotonda_per_difetto(lotti_esatti, passo_broker)

    if lotti <= 0:
        return EsitoSize(
            None,
            rischio,
            relativa,
            f"RISK-03: {lotti_esatti:.6f} lotti arrotondati per difetto danno zero",
        )
    return EsitoSize(lotti, rischio, relativa, "size calcolata")


def ridimensionamento_eseguibile(
    lotti_bersaglio: float,
    passo_broker: float,
) -> bool:
    """PA-63 — Il ridimensionamento e' eseguibile sul broker?

    Se adeguare una posizione esistente produrrebbe un volume sotto il passo
    minimo, non lo e'. In quel caso **la nuova posizione non si apre**: aprirla
    comunque produrrebbe un'esposizione fuori scala e non dichiarata, e
    PRIN-99 dice di astenersi.
    """
    if richiedi("PA-63") != "non_aprire_la_nuova":
        raise ValueError(f"PA-63: lettura non riconosciuta: {richiedi('PA-63')!r}")
    return _arrotonda_per_difetto(lotti_bersaglio, passo_broker) > 0


# ===========================================================================
# RISK-05 — selezione degli strumenti forex
# ===========================================================================


def strumento_eleggibile(
    strumento: str,
    direzione_dal_dxy: Optional[str],
    ha_setup_proprio: bool,
    direzione_del_setup: Optional[str],
) -> bool:
    """RISK-05 — La bias del DXY abilita, non obbliga.

    *"Non si apre una posizione su uno strumento solo perche' il DXY ha dato
    una bias. Si apre esclusivamente sugli strumenti che presentano un setup
    proprio nella direzione inversa al DXY."*

    Per `XAUUSD` non c'e' nulla da confrontare: ha bias propria (PRIN-09,
    PA-05), quindi basta il setup proprio.
    """
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")
    if not ha_setup_proprio:
        return False
    if not UNIVERSO[strumento].deriva_direzione_dal_dxy:
        return True
    if direzione_dal_dxy is None or direzione_del_setup is None:
        return False
    return direzione_dal_dxy == direzione_del_setup


# ===========================================================================
# RISK-07, RISK-08, RISK-09, RISK-10 — limiti di perdita
# ===========================================================================


@dataclass(frozen=True)
class LimiteRaggiunto:
    """Un limite di perdita raggiunto, con la regola che lo impone."""

    regola: str
    soglia: float
    perdita: float


def limiti_raggiunti(
    pnl_giornaliero: float,
    equity_inizio_giornata: float,
    pnl_settimanale: float,
    equity_inizio_settimana: float,
    pnl_mensile: float,
    equity_inizio_mese: float,
) -> tuple[LimiteRaggiunto, ...]:
    """RISK-07, RISK-08, RISK-09 — I tre limiti, calcolati sul P&L chiuso.

    I limiti bloccano l'**apertura** di nuove posizioni, non la gestione di
    quelle esistenti (RISK-10): una posizione aperta non viene chiusa dal
    raggiungimento di un limite.

    Conseguenza dichiarata da RISK-10 e non risolta (PA-34): il limite
    giornaliero puo' essere superato dalle posizioni gia' aperte senza che il
    sistema intervenga.
    """
    raggiunti: list[LimiteRaggiunto] = []
    controlli = (
        ("RISK-07", LIMITE_GIORNALIERO, pnl_giornaliero, equity_inizio_giornata),
        ("RISK-08", LIMITE_SETTIMANALE, pnl_settimanale, equity_inizio_settimana),
        ("RISK-09", LIMITE_MENSILE, pnl_mensile, equity_inizio_mese),
    )
    for regola, soglia, pnl, equity_iniziale in controlli:
        if equity_iniziale <= 0:
            continue
        perdita = -pnl / equity_iniziale
        if pnl <= 0 and perdita >= soglia:
            raggiunti.append(LimiteRaggiunto(regola, soglia, perdita))
    return tuple(raggiunti)


def stop_obbligatorio(livello_stop: Optional[float]) -> bool:
    """RISK-11 ed ESCL-10 — Nessuna posizione puo' esistere senza stop loss."""
    return livello_stop is not None
