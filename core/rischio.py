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
from typing import Any, Mapping, Optional, Sequence

from core.parametri import (
    LEVA_MASSIMA,
    LIMITE_GIORNALIERO,
    LIMITE_MENSILE,
    LIMITE_SETTIMANALE,
    LIMITI_PERDITA_SOPRA_EQUITY,
    RISCHIO_MASSIMO_LOTTO_MINIMO,
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

    ## La tolleranza, e perche' serve

    `0.29 / 0.01` in virgola mobile vale `28.999999999999996`, non 29:
    `floor` restituisce 28 e la size scende a 0,28 lotti. Non e' un caso
    raro — succede su 0.29, 0.58, 1.16 e altri — ed e' una perdita del 3,4%
    della size **su un valore che cadeva esattamente sul passo**.

    La tolleranza di un miliardesimo di passo corregge questo e nient'altro:
    un valore davvero sotto il passo successivo non ci arriva nemmeno vicino,
    quindi non si arrotonda mai per eccesso qualcosa che non lo meritava.
    """
    if passo <= 0:
        raise ValueError(f"passo del broker non valido: {passo}")
    decimali = max(0, len(f"{passo:.10f}".rstrip("0").split(".")[-1]))
    return round(math.floor(lotti / passo + 1e-9) * passo, decimali)


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
        # Il lotto minimo del broker, quando la size esatta sta sotto.
        #
        # `RISK-03` arrotonda per difetto, e su un conto piccolo quel
        # difetto e' quasi sempre zero: 0,005742 lotti diventano niente, e
        # l'operazione non parte. Non e' prudenza, e' il pezzo piu' piccolo
        # in vendita che e' piu' grosso della fetta che si voleva comprare.
        #
        # Sotto `LIMITI_PERDITA_SOPRA_EQUITY` si compra il minimo lo stesso:
        # e' li' che i limiti di perdita non ci sono e si sta guardando cosa
        # fa il bot, non proteggendo un capitale. Misurato su 100 EUR, col
        # lotto minimo e stop tipici il rischio va da 1,4% a 2,6% invece
        # dell'1% -- una volta e mezza o due, non un ordine di grandezza.
        #
        # Con un tetto pero': uno stop molto largo sul lotto minimo puo'
        # rischiare una fetta enorme, e senza limiti di perdita a fermarlo
        # basterebbero poche operazioni. Vedi `RISCHIO_MASSIMO_LOTTO_MINIMO`.
        sotto_soglia = (LIMITI_PERDITA_SOPRA_EQUITY > 0
                        and equity < LIMITI_PERDITA_SOPRA_EQUITY)
        if sotto_soglia and passo_broker > 0:
            rischio_vero = (passo_broker * distanza_cfd * valore_punto) / equity
            if rischio_vero <= RISCHIO_MASSIMO_LOTTO_MINIMO:
                return EsitoSize(
                    passo_broker, rischio_vero, relativa,
                    f"lotto minimo {passo_broker}: la size esatta era "
                    f"{lotti_esatti:.6f}, il rischio sale a "
                    f"{rischio_vero * 100:.2f}% (sotto i "
                    f"{LIMITI_PERDITA_SOPRA_EQUITY:.0f} EUR non ci sono "
                    f"limiti di perdita)",
                )
            return EsitoSize(
                None, rischio, relativa,
                f"RISK-03: col lotto minimo {passo_broker} si rischierebbe "
                f"il {rischio_vero * 100:.1f}%, oltre il tetto del "
                f"{RISCHIO_MASSIMO_LOTTO_MINIMO * 100:.0f}%",
            )
        return EsitoSize(
            None,
            rischio,
            relativa,
            f"RISK-03: {lotti_esatti:.6f} lotti arrotondati per difetto danno zero",
        )

    # --- Il tetto sulla LEVA, che e' cosa diversa dal rischio -------------
    #
    # `valore_punto` e' quanto vale un'unita' di prezzo per un lotto, quindi
    # `valore_punto x prezzo` e' il nozionale di un lotto. Con uno stop
    # vicino il rischio resta l'1% ma il nozionale esplode, e a quel punto
    # uno scivolamento sullo stop non costa piu' l'1%.
    nozionale = lotti * valore_punto * prezzo_cfd
    tetto = LEVA_MASSIMA * equity
    if nozionale > tetto:
        ridotti = _arrotonda_per_difetto(
            tetto / (valore_punto * prezzo_cfd), passo_broker)
        if ridotti <= 0:
            return EsitoSize(
                None, rischio, relativa,
                f"RISK-03: con la leva massima di {LEVA_MASSIMA:.0f}x il volume "
                f"scende sotto il passo del broker",
            )
        return EsitoSize(
            ridotti, rischio, relativa,
            f"size ridotta da {lotti} a {ridotti} lotti: il nozionale era "
            f"{nozionale / equity:.0f}x l'equity, il tetto e' {LEVA_MASSIMA:.0f}x",
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
    equity_corrente: Optional[float] = None,
) -> tuple[LimiteRaggiunto, ...]:
    """RISK-07, RISK-08, RISK-09 — I tre limiti, calcolati sul P&L chiuso.

    I limiti bloccano l'**apertura** di nuove posizioni, non la gestione di
    quelle esistenti (RISK-10): una posizione aperta non viene chiusa dal
    raggiungimento di un limite.

    Conseguenza dichiarata da RISK-10 e non risolta (PA-34): il limite
    giornaliero puo' essere superato dalle posizioni gia' aperte senza che il
    sistema intervenga.

    **Sotto `LIMITI_PERDITA_SOPRA_EQUITY` non si applica nessuno dei tre.**
    Sono percentuali, e `RISK-01` rischia l'1% per operazione: il giornaliero
    al 3% scatta sempre dopo tre operazioni perse, a qualunque cifra. Su un
    conto di prova piccolo quel freno impedisce di vedere una giornata intera
    senza proteggere niente che valga la pena proteggere. Vedi il parametro.
    """
    if equity_corrente is not None and LIMITI_PERDITA_SOPRA_EQUITY > 0:
        if equity_corrente < LIMITI_PERDITA_SOPRA_EQUITY:
            return ()

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


@dataclass(frozen=True)
class Ridimensionamento:
    """Cosa fare a una posizione gia' aperta quando `n` cambia."""

    id_posizione: int
    ticket: Optional[int]
    volume_attuale: float
    volume_bersaglio: float
    rischio_nuovo: float

    @property
    def da_chiudere(self) -> float:
        """Quanto va chiuso per portarla al volume bersaglio."""
        return round(self.volume_attuale - self.volume_bersaglio, 8)


def ridimensionamenti(
    strumento: str,
    aperte_nel_gruppo: Sequence[Mapping[str, Any]],
    passo_broker: float,
    equity: Optional[float] = None,
) -> tuple[tuple[Ridimensionamento, ...], Optional[str]]:
    """RISK-02 (REV-42) — Il ridimensionamento a ogni nuova apertura.

    *"A ogni nuova apertura tutte le posizioni gia' aperte vengono
    ridimensionate al nuovo `rischio_operazione`, cosi' che ciascuna rischi
    sempre la stessa percentuale."*

    Senza questo passo l'esposizione reale segue la curva alta — ciascuna
    posizione conserva il rischio del proprio ingresso — invece di quella
    dichiarata: 2,65% su quattro posizioni invece di 1,80%.

    `aperte_nel_gruppo` sono le righe di `storage.posizioni_aperte()` gia'
    filtrate sul gruppo di correlazione, con `volume` e `rischio_corrente`.

    Restituisce (ridimensionamenti, motivo_di_astensione). Il motivo non e'
    None quando PA-63 impone di **non aprire la nuova**: se adeguare una
    posizione esistente producesse un volume sotto il passo minimo del
    broker, aprire comunque darebbe un'esposizione fuori scala e non
    dichiarata, e PRIN-99 dice di astenersi.

    Il ridimensionamento va solo **verso il basso**: `n` cresce a ogni
    apertura e il rischio per posizione scende. Se una riga non ha
    `rischio_corrente` — posizione aperta prima che la colonna esistesse — la
    si lascia stare: non si sa da quale rischio partiva, e indovinarlo
    significherebbe cambiarle il volume su un numero inventato.

    **Sotto `LIMITI_PERDITA_SOPRA_EQUITY` non si ridimensiona nulla.** Li'
    `calcola_size` compra il lotto minimo del broker per decisione esplicita,
    quindi ogni posizione del gruppo e' gia' al pezzo piu' piccolo in vendita:
    non c'e' nessun budget di rischio da spartire in `n` parti, e ridurre
    0,01 lotti e' impossibile prima ancora che sconsigliabile. Senza questo
    controllo PA-63 vedeva un bersaglio di 0,0027 lotti, lo trovava non
    eseguibile e **rifiutava l'apertura nuova** -- bloccando proprio il regime
    in cui si e' scelto di operare senza limiti per vedere cosa fa il bot.
    """
    if equity is not None and LIMITI_PERDITA_SOPRA_EQUITY > 0:
        if equity < LIMITI_PERDITA_SOPRA_EQUITY:
            return (), None

    n = len(aperte_nel_gruppo) + 1                  # piu' quella in valutazione
    nuovo = rischio_per_posizione(n, strumento)

    esiti: list[Ridimensionamento] = []
    for riga in aperte_nel_gruppo:
        corrente = riga.get("rischio_corrente")
        if not corrente:
            continue
        volume = float(riga["volume"])
        if volume <= 0 or nuovo >= float(corrente):
            continue                                 # nulla da ridurre
        bersaglio = volume * (nuovo / float(corrente))
        if not ridimensionamento_eseguibile(bersaglio, passo_broker):
            return (), (
                f"PA-63: ridimensionare la posizione {riga.get('id')} a "
                f"{bersaglio:.4f} lotti darebbe zero al passo {passo_broker}; "
                "RISK-02 non e' applicabile e la nuova posizione non si apre"
            )
        # Al passo del broker, per difetto: meglio rischiare un filo meno.
        arrotondato = _arrotonda_per_difetto(bersaglio, passo_broker)
        if arrotondato >= volume:
            continue                                 # differenza sotto il passo
        esiti.append(Ridimensionamento(
            id_posizione=int(riga["id"]),
            ticket=riga.get("ticket"),
            volume_attuale=volume,
            volume_bersaglio=arrotondato,
            rischio_nuovo=nuovo,
        ))
    return tuple(esiti), None
