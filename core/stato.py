"""Costruzione della `Fotografia`: da uno storico di candele allo stato del motore.

E' il pezzo che mancava fra i dati e le regole. `motore.valuta()` riceve una
fotografia gia' pronta e non va a cercarsi niente; qualcuno pero' deve
costruirla, e quel qualcuno e' questo file.

Tutto qui dentro e' **puro**: riceve candele, restituisce stato. Non legge da
disco, non chiama il broker, non guarda l'orologio. L'istante di valutazione
arriva come parametro, ed e' l'unica nozione di "adesso" che esiste.

**Il divieto di lookahead vale qui piu' che altrove.** Ogni funzione filtra lo
storico con `candele_visibili()` prima di toccarlo. E' ridondante rispetto al
motore, che rifiltra a sua volta, e va bene cosi': in un backtest o in un
forward test il lookahead non fa rumore, produce solo risultati troppo belli.

**La bias e' una piega, non una fotografia.** `DEF-24` fa ereditare la bias
lungo una catena di inside bar, quindi non si puo' calcolare guardando le
ultime due candele: bisogna ripercorrere lo storico dall'inizio. E' il motivo
per cui `serie_bias` esiste e `bias_corrente` la usa invece di prendere una
scorciatoia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence

from core.definizioni import (
    Bias,
    Candela,
    Gap,
    KeyLevel,
    LivelloStrutturale,
    Polarita,
    Presa,
    assorbi_key_level,
    bias_timeframe,
    gap_attivo,
    gap_invalidato,
    gap_rialzista,
    gap_ribassista,
    key_levels,
    livelli_strutturali,
    presa_key_level,
    timeframe_utilizzabile,
)
from core.motore import candele_visibili
from core.parametri import (
    LOOKBACK_ANNI,
    ORDINE_SCANSIONE_TARGET,
    TF,
    TF_BIAS,
    TF_KEY_LEVEL,
    ordine_scansione_gap,
)

# Uno storico e' una mappa timeframe -> candele chiuse, in ordine qualsiasi.
Storico = Mapping[TF, Sequence[Candela]]


# ===========================================================================
# Bias
# ===========================================================================


def serie_bias(candele: Sequence[Candela]) -> tuple[Bias, ...]:
    """DEF-16, DEF-23, DEF-24 — La bias a ogni chiusura, dalla piu' vecchia.

    Va ripercorsa dall'inizio perche' DEF-24 e' ricorsiva: una serie di inside
    bar senza gap mantiene l'ultima bias determinata da una candela non
    inside, e quella puo' stare molte candele indietro.

    Le prime due posizioni sono NESSUNA: servono `C1` per il confronto e `C2`
    per il gap di DEF-23, e prima non esistono.
    """
    ordinate = sorted(candele, key=lambda c: c.orario)
    serie: list[Bias] = []
    precedente = Bias.NESSUNA

    for indice, c0 in enumerate(ordinate):
        if indice == 0:
            serie.append(Bias.NESSUNA)
            continue
        c1 = ordinate[indice - 1]
        c2 = ordinate[indice - 2] if indice >= 2 else None
        precedente = bias_timeframe(c0, c1, c2, bias_precedente=precedente)
        serie.append(precedente)

    return tuple(serie)


def bias_corrente(candele: Sequence[Candela], istante: datetime) -> Bias:
    """DEF-16 — La bias del timeframe all'istante indicato."""
    visibili = candele_visibili(candele, istante)
    if not timeframe_utilizzabile(len(visibili)):
        return Bias.NESSUNA                       # DEF-26
    serie = serie_bias(visibili)
    return serie[-1] if serie else Bias.NESSUNA


def bias_per_timeframe(storico: Storico, istante: datetime) -> dict[TF, Bias]:
    """DEF-16 e DEF-31 — La bias di ogni timeframe che ne ha una.

    `TF_H12` e `TF_H6` non compaiono: su quei due si rilevano solo gap, e
    nessuna bias da accettazione o rifiuto (DEF-31).
    """
    return {
        tf: bias_corrente(storico.get(tf, ()), istante)
        for tf in TF_BIAS
        if tf in storico
    }


# ===========================================================================
# Key level
# ===========================================================================


def key_level_correnti(storico: Storico, istante: datetime) -> list[KeyLevel]:
    """DEF-36 e DEF-37 — I key level attivi, con l'assorbimento applicato.

    Calcolati su `C1` di ciascun timeframe. Quando due timeframe diversi
    producono lo stesso identico valore resta solo quello piu' alto: non e'
    un caso raro, il minimo di una mensile e' per costruzione identico a
    quello di una delle sue settimanali.

    I timeframe sono quelli di `TF_KEY_LEVEL`, cioe' i sei di DEF-36 piu'
    `TF_H4` (REV-48): senza key level su `TF_H4` la riga `TF_H1` di SETUP-05
    non e' soddisfabile e `TF_H1` non puo' essere il timeframe di trigger che
    PRIN-10 dice che e'.
    """
    grezzi: list[KeyLevel] = []
    for tf in TF_KEY_LEVEL:
        visibili = candele_visibili(storico.get(tf, ()), istante)
        if len(visibili) < 2:
            continue                              # serve C1
        grezzi.extend(key_levels(visibili[-2], tf))
    return assorbi_key_level(grezzi)


def key_level_presi(storico: Storico, istante: datetime) -> list[KeyLevel]:
    """DEF-38 — I key level presi dall'ultima candela chiusa del loro timeframe.

    La presa si conferma a candela chiusa, mai sul prezzo scambiato (DEF-45):
    uno sfioramento intraday rientrato prima della chiusura non abilita alcun
    setup.
    """
    presi: list[KeyLevel] = []
    for livello in key_level_correnti(storico, istante):
        visibili = candele_visibili(storico.get(livello.tf, ()), istante)
        if not visibili:
            continue
        if presa_key_level(visibili[-1], livello) is not Presa.NESSUNA:
            presi.append(livello)
    return presi


def sbilanciamenti_per_timeframe(storico: Storico, istante: datetime) -> dict[TF, Bias]:
    """SETUP-05 — In che direzione ciascun timeframe ha sbilanciato un key level.

    E' il dato su cui gira la regola dei due timeframe immediatamente
    superiori. Un timeframe che ha preso sia un massimo sia un minimo non
    sbilancia in alcuna direzione: la candela ha spazzato entrambi i lati e
    non dice nulla, come in DEF-16 passo 1.
    """
    direzioni: dict[TF, set[Bias]] = {}
    for livello in key_level_presi(storico, istante):
        visibili = candele_visibili(storico.get(livello.tf, ()), istante)
        presa = presa_key_level(visibili[-1], livello)
        if presa is Presa.RIALZO:
            direzioni.setdefault(livello.tf, set()).add(Bias.LONG)
        elif presa is Presa.RIBASSO:
            direzioni.setdefault(livello.tf, set()).add(Bias.SHORT)

    return {
        tf: next(iter(insieme))
        for tf, insieme in direzioni.items()
        if len(insieme) == 1
    }


# ===========================================================================
# Gap
# ===========================================================================


def gap_del_timeframe(candele: Sequence[Candela], tf: TF) -> list[Gap]:
    """DEF-10, DEF-11, DEF-14 — I gap non invalidati di un timeframe.

    Si scorrono tutte le terne consecutive. Un gap invalidato non torna mai
    valido (ESCL-16), quindi viene scartato una volta per tutte.
    """
    ordinate = sorted(candele, key=lambda c: c.orario)
    validi: list[Gap] = []

    for indice in range(2, len(ordinate)):
        p1, p2, p3 = ordinate[indice - 2], ordinate[indice - 1], ordinate[indice]
        for gap in (gap_rialzista(p1, p2, p3, tf), gap_ribassista(p1, p2, p3, tf)):
            if gap is None:
                continue
            # L'invalidazione si verifica sullo stesso timeframe, sulle sole
            # candele successive alla formazione.
            if not gap_invalidato(gap, ordinate[indice + 1:]):
                validi.append(gap)

    return validi


def gap_per_timeframe(storico: Storico, istante: datetime) -> dict[TF, list[Gap]]:
    """DEF-13 e DEF-31 — I gap validi di ogni timeframe della scansione."""
    return {
        tf: gap_del_timeframe(candele_visibili(storico.get(tf, ()), istante), tf)
        for tf in ordine_scansione_gap()
        if tf in storico
    }


def gap_attivi(storico: Storico, istante: datetime) -> tuple[Optional[Gap], Optional[Gap]]:
    """DEF-13 — Il gap attivo rialzista e quello ribassista, uno per direzione."""
    per_tf = gap_per_timeframe(storico, istante)
    return (
        gap_attivo(per_tf, Polarita.RIALZISTA),
        gap_attivo(per_tf, Polarita.RIBASSISTA),
    )


def gap_target(storico: Storico, istante: datetime) -> Optional[Gap]:
    """DEF-13, DEF-15bis, PREC-02 — Il gap che fa da target.

    Con un gap attivo per direzione su timeframe diversi vince quello piu'
    alto (REV-27): e' il criterio che DEF-13 usa gia' per la selezione e che
    PREC-02 stabilisce in generale.
    """
    lungo, corto = gap_attivi(storico, istante)
    candidati = [g for g in (lungo, corto) if g is not None]
    if not candidati:
        return None
    ordine = ordine_scansione_gap()
    return min(candidati, key=lambda g: ordine.index(g.tf))


def gap_di_reazione(storico: Storico, istante: datetime, bias: Bias) -> Optional[Gap]:
    """DEF-15bis — La zona in cui cercare l'ingresso, che non e' il target.

    DEF-15bis assegna al gap **due ruoli distinti** e chiude dicendo che
    *«nessuna regola puo' usare un gap con un ruolo diverso da quello qui
    assegnato»*:

    - il gap attivo sul timeframe **piu' alto** (DEF-13) e' un **target**;
    - i gap sui timeframe **inferiori a quello del gap target** sono le zone
      in cui cercare l'ingresso, e li' la polarita' conta: la zona si usa solo
      se concorda con la bias operativa in corso.

    `SETUP-09` lo ripete nella sua prima riga: *«si applica quando il prezzo
    interagisce con una zona_gap di timeframe inferiore a quello del gap
    target»*. E' questa la zona che il modello a fasi di DEF-43 sorveglia, e
    quella a cui `SETUP-10` riferisce il doppio ingresso.

    Restituisce `None` quando non c'e' nessuna zona utilizzabile: e' il caso
    ordinario, e significa ingresso unico a rischio pieno, non astensione.
    """
    bersaglio = gap_target(storico, istante)
    ordine = ordine_scansione_gap()
    limite = ordine.index(bersaglio.tf) if bersaglio is not None else -1
    sotto = {
        tf: gap
        for tf, gap in gap_per_timeframe(storico, istante).items()
        if ordine.index(tf) > limite
    }
    if bias is Bias.LONG:
        return gap_attivo(sotto, Polarita.RIALZISTA)
    if bias is Bias.SHORT:
        return gap_attivo(sotto, Polarita.RIBASSISTA)
    return None


# ===========================================================================
# Livelli strutturali e target
# ===========================================================================


def livelli_disponibili(
    storico: Storico,
    istante: datetime,
) -> dict[TF, list[LivelloStrutturale]]:
    """DEF-25, DEF-26, DEF-27 — I livelli strutturali ancora disponibili.

    Solo quelli formatisi dentro il `lookback` di cinque anni (DEF-26), e solo
    quelli non ancora consumati (DEF-27).

    **Sul consumo.** DEF-27 dice "al tocco, sul prezzo scambiato". Qui il
    prezzo scambiato e' rappresentato dagli estremi delle candele successive
    alla formazione: e' l'informazione piu' fine che uno storico a candele
    contenga. Con i tick il risultato non cambierebbe, perche' il massimo di
    una candela e' il massimo dei suoi tick.
    """
    inizio_lookback = istante - timedelta(days=365 * LOOKBACK_ANNI)
    risultato: dict[TF, list[LivelloStrutturale]] = {}

    for tf in ORDINE_SCANSIONE_TARGET:
        visibili = candele_visibili(storico.get(tf, ()), istante)
        dentro = [c for c in visibili if c.orario >= inizio_lookback]
        if not timeframe_utilizzabile(len(dentro)):
            continue                                        # DEF-26

        disponibili: list[LivelloStrutturale] = []
        for indice, candela in enumerate(dentro):
            successive = dentro[indice + 1:]
            if not successive:
                continue                    # nessun prezzo dopo: non consumabile
            massimo_dopo = max(c.massimo for c in successive)
            minimo_dopo = min(c.minimo for c in successive)
            for livello in livelli_strutturali([candela], tf):
                consumato = (
                    massimo_dopo >= livello.valore
                    if livello.rialzista
                    else minimo_dopo <= livello.valore
                )
                if not consumato:
                    disponibili.append(livello)

        if disponibili:
            risultato[tf] = disponibili

    return risultato


# ===========================================================================
# Costruzione della fotografia
# ===========================================================================


@dataclass(frozen=True)
class Conto:
    """I dati del conto che la fotografia richiede, tenuti insieme."""

    equity: float
    prezzo_cfd: float
    valore_punto: float
    passo_broker: float = 0.01
    spread: float = 0.0
    posizioni_aperte_per_strumento: Mapping[str, int] = None  # type: ignore[assignment]
    pnl_giornaliero: float = 0.0
    equity_inizio_giornata: float = 0.0
    pnl_settimanale: float = 0.0
    equity_inizio_settimana: float = 0.0
    pnl_mensile: float = 0.0
    equity_inizio_mese: float = 0.0

    def __post_init__(self) -> None:
        if self.posizioni_aperte_per_strumento is None:
            object.__setattr__(self, "posizioni_aperte_per_strumento", {})


def costruisci_fotografia(
    istante: datetime,
    strumento: str,
    storico: Storico,
    conto: Conto,
    bias_dxy: Bias = Bias.NESSUNA,
    gap_fase: int = 0,
    mitigazione=None,
    eventi_news: Sequence = (),
    eta_calendario_ore: Optional[float] = None,
    target_raggiunto_per_tf: Optional[Mapping[TF, bool]] = None,
    dati_coerenti: bool = True,
):
    """Assembla la `Fotografia` che `motore.valuta()` si aspetta.

    Tutto viene ricalcolato dallo storico a ogni chiamata: nessuno stato
    sopravvive fra una valutazione e l'altra. E' piu' lento di un aggiornamento
    incrementale, ed e' una scelta — uno stato che si trascina e' il posto in
    cui un lookahead si nasconde senza farsi notare, e questa strategia
    rivaluta al massimo una volta per chiusura di candela.

    `gap_fase` e `mitigazione` restano parametri perche' appartengono alla
    sorveglianza (DEF-43, DEF-45): dipendono dai prezzi scambiati fra una
    chiusura e l'altra, che uno storico di candele chiuse non contiene.
    """
    from core.definizioni import Mitigazione
    from core.motore import Fotografia
    from core.setup import bias_comando

    if mitigazione is None:
        mitigazione = Mitigazione.NON_ATTESA

    per_tf = bias_per_timeframe(storico, istante)
    comando, _ = bias_comando(per_tf, dict(target_raggiunto_per_tf or {}))

    return Fotografia(
        istante=istante,
        strumento=strumento,
        candele_per_tf={tf: tuple(candele) for tf, candele in storico.items()},
        bias_per_tf=per_tf,
        target_raggiunto_per_tf=dict(target_raggiunto_per_tf or {}),
        bias_dxy=bias_dxy,
        key_level_presi=key_level_presi(storico, istante),
        sbilanciamenti=sbilanciamenti_per_timeframe(storico, istante),
        gap_attivo=gap_target(storico, istante),
        gap_reazione=gap_di_reazione(storico, istante, comando),
        gap_fase=gap_fase,
        mitigazione=mitigazione,
        equity=conto.equity,
        prezzo_cfd=conto.prezzo_cfd,
        valore_punto=conto.valore_punto,
        passo_broker=conto.passo_broker,
        spread=conto.spread,
        posizioni_aperte_per_strumento=dict(conto.posizioni_aperte_per_strumento),
        pnl_giornaliero=conto.pnl_giornaliero,
        equity_inizio_giornata=conto.equity_inizio_giornata,
        pnl_settimanale=conto.pnl_settimanale,
        equity_inizio_settimana=conto.equity_inizio_settimana,
        pnl_mensile=conto.pnl_mensile,
        equity_inizio_mese=conto.equity_inizio_mese,
        eventi_news=tuple(eventi_news),
        eta_calendario_ore=eta_calendario_ore,
        dati_coerenti=dati_coerenti,
    )
