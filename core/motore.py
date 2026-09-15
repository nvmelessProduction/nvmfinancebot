"""Orchestrazione: mette insieme gli altri moduli e produce una decisione.

**Ogni decisione e' tracciabile.** `Decisione` porta azione, direzione, size,
stop, target e l'elenco degli ID delle regole che l'hanno prodotta. Quando il
motore decide di non operare dice **quale regola** gliel'ha impedito, non "non
c'erano le condizioni". E' il requisito piu' importante di questo file: una
decisione che non sa spiegarsi non e' verificabile contro `07_casi.md`.

**Nessun lookahead.** All'istante `t` il motore vede solo candele **chiuse**
entro `t`. Il punto in cui questo si perde e' l'allineamento multi-timeframe:
la candela settimanale in corso non esiste finche' non chiude, e usarla
significherebbe leggere il futuro. Tutto passa da `candele_visibili()`, che e'
l'unica porta d'ingresso dei dati e ha un test dedicato.

**Ordine delle precedenze.** Si applicano in quest'ordine, che e' quello
dichiarato dai documenti:

```
PREC-05  ESCLUSIONI batte tutto        -> ultimo controllo, prima dell'ordine
PREC-01  RISK batte SETUP              -> i limiti fermano tutto
PREC-04  CONTESTO batte SETUP          -> i filtri fermano ogni setup
PREC-02  il timeframe piu' alto comanda
PREC-03  il future comanda sulla fonte dati
```

Le esclusioni girano **due volte**: la loro parte dichiarativa entra nei filtri,
e `verifica_divieti()` ricontrolla l'ordine gia' costruito. Non e' ridondanza:
e' l'unico controllo che non si fida degli altri.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from core import contesto as ctx
from core import esclusioni as esc
from core import gestione as gest
from core import rischio as risk
from core import setup as stp
from core.definizioni import Bias, Candela, Gap, KeyLevel, Mitigazione
from core.parametri import MAX_POSIZIONI_PER_STRUMENTO, TF, UNIVERSO

# ===========================================================================
# Ingresso dei dati: l'unica porta, e quella che vieta il lookahead
# ===========================================================================


def candele_visibili(candele: Sequence[Candela], istante: datetime) -> tuple[Candela, ...]:
    """Le sole candele **chiuse entro `istante`**.

    E' la barriera contro il lookahead, e l'unico posto da cui i dati entrano
    nel motore. `Candela.orario` e' l'istante di **chiusura** del periodo
    (DEF-02), quindi il confronto e' `orario <= istante`: una candela che
    chiude esattamente adesso e' visibile, una che chiudera' fra un secondo no.

    Il caso che rompe i backtest multi-timeframe: alle 14:00 di mercoledi' la
    candela settimanale in corso non e' chiusa, quindi non esiste. Chi la
    usasse per l'allineamento leggerebbe il futuro, e il backtest sembrerebbe
    ottimo.
    """
    return tuple(sorted((c for c in candele if c.orario <= istante), key=lambda c: c.orario))


@dataclass(frozen=True)
class Fotografia:
    """Tutto cio' che il motore puo' vedere in un istante, e nulla di piu'.

    Costruirla e' compito di chi ha i dati — il live o il forward test su
    demo. Il motore non va a cercarsi niente: se un dato non e' qui, per
    `ESCL-14` la regola che lo richiede non e' eseguibile.
    """

    istante: datetime
    strumento: str

    # Candele per timeframe. Vanno gia' filtrate da `candele_visibili`, e il
    # motore lo rifa' comunque: fidarsi qui costerebbe un lookahead silenzioso.
    candele_per_tf: Mapping[TF, Sequence[Candela]]

    # Contesto direzionale
    bias_per_tf: Mapping[TF, Bias] = field(default_factory=dict)
    target_raggiunto_per_tf: Mapping[TF, bool] = field(default_factory=dict)
    bias_dxy: Bias = Bias.NESSUNA

    # Key level presi e sbilanciamenti, per timeframe
    key_level_presi: Sequence[KeyLevel] = ()
    sbilanciamenti: Mapping[TF, Bias] = field(default_factory=dict)

    # Gap. Sono due ruoli diversi e DEF-15bis vieta di confonderli: il gap
    # attivo sul timeframe piu' alto (DEF-13) e' un TARGET, le zone di
    # ingresso sono i gap sui timeframe inferiori al suo (REV-47).
    gap_attivo: Optional[Gap] = None
    gap_reazione: Optional[Gap] = None
    gap_fase: int = 0
    mitigazione: Mitigazione = Mitigazione.NON_ATTESA

    # Conto e mercato
    equity: float = 0.0
    prezzo_cfd: float = 0.0
    valore_punto: float = 0.0
    passo_broker: float = 0.01
    spread: float = 0.0
    posizioni_aperte_per_strumento: Mapping[str, int] = field(default_factory=dict)

    # Limiti
    pnl_giornaliero: float = 0.0
    equity_inizio_giornata: float = 0.0
    pnl_settimanale: float = 0.0
    equity_inizio_settimana: float = 0.0
    pnl_mensile: float = 0.0
    equity_inizio_mese: float = 0.0

    # Calendario
    eventi_news: Sequence[ctx.EventoNews] = ()
    eta_calendario_ore: Optional[float] = None

    dati_coerenti: bool = True


# ===========================================================================
# La decisione
# ===========================================================================


@dataclass(frozen=True)
class Decisione:
    """Cosa fare, e per quali regole.

    `azione` e' NONE quando non si opera, e in quel caso `regole_che_bloccano`
    non e' mai vuoto: se lo fosse sarebbe un errore del motore, perche'
    significherebbe che non si opera senza una regola che lo imponga.
    """

    azione: str                       # "NONE", "BUY", "SELL"
    strumento: str
    direzione: Optional[Bias] = None
    volume: Optional[float] = None
    livello_stop: Optional[float] = None
    tp1: Optional[float] = None
    target_finale: Optional[float] = None
    tf_crt: Optional[TF] = None
    doppio_ingresso: bool = False
    regole_applicate: tuple[str, ...] = ()
    regole_che_bloccano: tuple[str, ...] = ()
    motivo: str = ""
    # Registrati per le statistiche, mai per decidere (DEF-44, GIUD-01).
    rapporto_su_tp1: Optional[float] = None
    rapporto_giud01: Optional[float] = None

    def spiegazione(self) -> str:
        """Una riga leggibile, per il log e per Telegram."""
        if self.azione == "NONE":
            return f"{self.strumento}: nessuna operazione — {', '.join(self.regole_che_bloccano)}"
        return (
            f"{self.strumento}: {self.azione} {self.volume} "
            f"stop {self.livello_stop} tp1 {self.tp1} target {self.target_finale} "
            f"[{', '.join(self.regole_applicate)}]"
        )


def _non_operare(
    strumento: str,
    blocchi: Sequence[str],
    motivo: str,
    applicate: Sequence[str] = (),
    **extra: object,
) -> Decisione:
    """Costruisce una decisione di astensione, sempre con almeno una regola."""
    if not blocchi:
        raise ValueError("astensione senza regola: sarebbe PRIN-99 non dichiarato")
    return Decisione(
        azione="NONE",
        strumento=strumento,
        regole_applicate=tuple(applicate),
        regole_che_bloccano=tuple(dict.fromkeys(blocchi)),
        motivo=motivo,
        **extra,  # type: ignore[arg-type]
    )


# ===========================================================================
# Valutazione
# ===========================================================================


def valuta(foto: Fotografia, tf_trigger: TF) -> Decisione:
    """Valuta un possibile ingresso su `tf_trigger` e restituisce la decisione.

    L'ordine dei controlli segue le precedenze dichiarate. I filtri di
    contesto e le esclusioni di setup si applicano **uniti** (REV-17), perche'
    i due elenchi non coincidono e nessuno dei due e' normativo da solo.
    """
    applicate: list[str] = []

    # --- 0. Lo strumento e' nell'universo? (ESCL-05, PRIN-08) -------------
    if foto.strumento not in UNIVERSO:
        return _non_operare(foto.strumento, ["ESCL-05"], "strumento fuori da PRIN-08")

    # --- 1. Il calendario news e' utilizzabile? (PA-55) -------------------
    if not ctx.calendario_utilizzabile(foto.eventi_news, foto.eta_calendario_ore):
        return _non_operare(
            foto.strumento, ["PRIN-99"],
            "calendario news assente o troppo vecchio: PA-55 impone astensione",
        )

    # --- 2. Filtri che non dipendono dal CRT ------------------------------
    # Vanno valutati anche quando il CRT non c'e', altrimenti la statistica
    # "quante volte ciascun filtro ha impedito un'operazione" vedrebbe sempre
    # e solo il primo blocco, e non direbbe se un filtro non scatta mai.
    limiti = risk.limiti_raggiunti(
        foto.pnl_giornaliero, foto.equity_inizio_giornata,
        foto.pnl_settimanale, foto.equity_inizio_settimana,
        foto.pnl_mensile, foto.equity_inizio_mese,
    )
    posizioni_qui = foto.posizioni_aperte_per_strumento.get(foto.strumento, 0)
    evento_news = ctx.dentro_finestra_news(foto.istante, foto.strumento, foto.eventi_news)
    festivita = ctx.giorno_di_festivita(foto.istante.date())

    indipendenti: list[str] = []
    if not ctx.operativita_domenicale_ammessa(foto.istante, tf_trigger):
        indipendenti.append("PRIN-13")        # domenica solo da TF_1W in su
    if evento_news is not None:
        indipendenti.append("CTX-02")
    if festivita is not None:
        indipendenti.append("CTX-04")
    if posizioni_qui >= MAX_POSIZIONI_PER_STRUMENTO:
        indipendenti.append("RISK-06")
    if not foto.dati_coerenti:
        indipendenti.append("PRIN-99")
    indipendenti.extend(l.regola for l in limiti)        # PREC-01

    # --- 3. Bias di comando (SETUP-06) ------------------------------------
    comando, tf_comando = stp.bias_comando(foto.bias_per_tf, foto.target_raggiunto_per_tf)
    applicate.append("SETUP-06")
    if comando is Bias.NESSUNA:
        return _non_operare(
            foto.strumento, ["SETUP-06"] + indipendenti, "nessuna bias di comando", applicate
        )

    # --- 4. Il CRT (SETUP-00, SETUP-02) -----------------------------------
    candele = candele_visibili(foto.candele_per_tf.get(tf_trigger, ()), foto.istante)
    if len(candele) < 2:
        return _non_operare(
            foto.strumento, ["DEF-26"] + indipendenti,
            f"storia insufficiente su {tf_trigger.value}: servono almeno N1 e N2",
            applicate,
        )
    n1, n2 = candele[-2], candele[-1]

    crt = stp.cerca_crt(n1, n2, tf_trigger, foto.key_level_presi)
    applicate.append("SETUP-00")
    if crt is None:
        return _non_operare(
            foto.strumento, ["SETUP-00"] + indipendenti,
            "nessun CRT valido: serve la presa di un key level di timeframe superiore",
            applicate,
        )
    applicate.append("SETUP-02A" if crt.direzione is Bias.SHORT else "SETUP-02B")

    # --- 4. Livelli: stop, TP1, target (GEST-02, GEST-07, GEST-08) --------
    # Un ingresso e' "da gap" solo se due cose sono vere insieme (REV-47):
    #
    #   1. la zona e' una zona di REAZIONE, non il gap target. DEF-15bis
    #      assegna al gap piu' alto il ruolo di bersaglio e vieta di usarlo
    #      con un ruolo diverso;
    #   2. il prezzo vi sta INTERAGENDO. E' la prima riga di SETUP-09
    #      ("si applica quando il prezzo interagisce con una zona_gap") ed e'
    #      quello che dice `gap_fase > 0`: la fase 0 significa che il prezzo
    #      quella zona non l'ha mai toccata.
    #
    # `doppio_ingresso` da solo confronta timeframe, e un CRT su TF_H1 non e'
    # mai piu' alto di un gap su TF_1D: senza le due condizioni sopra ogni CRT
    # risultava "a supporto di un gap" e SETUP-09 lo bloccava per sempre.
    da_gap = (
        foto.gap_reazione is not None
        and foto.gap_fase > 0
        and stp.doppio_ingresso(crt, foto.gap_reazione)
    )
    stop = gest.stop_aggressivo(crt.n2, crt.direzione)
    obiettivo_1 = gest.tp1(crt.n1)
    applicate.extend(["GEST-02", "GEST-07"])

    # Il prezzo di ingresso e' l'apertura di N3, che non esiste ancora: si usa
    # il prezzo corrente, che e' cio' che CTX-05 chiede di fare ("sui prezzi
    # effettivi al momento dell'ordine, non su quelli teorici").
    prezzo_ingresso = foto.prezzo_cfd

    rapporto = ctx.rapporto_rischio_rendimento(prezzo_ingresso, stop, obiettivo_1)

    # --- 5. Filtri uniti: CTX-01 + SETUP-15 (REV-17, PREC-04) -------------
    allineato = stp.allineamento_soddisfatto(crt.tf, foto.sbilanciamenti, crt.direzione)

    filtri = ctx.filtri_attivi(
        adesso=foto.istante,
        strumento=foto.strumento,
        key_level_preso=True,
        comando=comando,
        direzione_crt=crt.direzione,
        allineamento_ok=allineato,
        rapporto_su_tp1=rapporto,
        posizioni_aperte_strumento=posizioni_qui,
        limite_rischio_raggiunto=bool(limiti),
        eventi_news=foto.eventi_news,
        mitigazione_non_determinata=(da_gap and foto.mitigazione is Mitigazione.NON_DETERMINATA),
        dati_coerenti=foto.dati_coerenti,
    )
    esclusi = stp.esclusioni_setup(
        crt=crt,
        comando=comando,
        key_level_preso=True,
        sbilanciamenti=foto.sbilanciamenti,
        posizioni_aperte_strumento=posizioni_qui,
        limite_rischio_raggiunto=bool(limiti),
        dentro_finestra_news=evento_news is not None,
        dati_coerenti=foto.dati_coerenti,
        da_gap=da_gap,
        mitigazione=foto.mitigazione,
    )

    # --- 5bis. Ingresso da gap: la fase deve essere la terza (SETUP-09) ---
    blocchi_gap: tuple[str, ...] = ()
    if da_gap:
        _, blocchi_gap = stp.ingresso_da_gap_ammesso(foto.gap_fase, foto.mitigazione)

    blocchi = [f.regola for f in filtri] + list(esclusi) + list(blocchi_gap) + indipendenti

    if blocchi:
        return _non_operare(
            foto.strumento, blocchi,
            "; ".join(f"{f.regola}: {f.motivo}" for f in filtri) or "condizioni non soddisfatte",
            applicate,
            direzione=crt.direzione,
            tf_crt=crt.tf,
            livello_stop=stop,
            tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )

    # --- 6. Size (RISK-01, RISK-02, RISK-03, DEF-47) ----------------------
    n2_future = crt.n2.chiusura
    esito_size = risk.calcola_size(
        equity=foto.equity,
        strumento=foto.strumento,
        chiusura_n2_future=n2_future,
        stop_future=stop,
        prezzo_cfd=foto.prezzo_cfd,
        valore_punto=foto.valore_punto,
        passo_broker=foto.passo_broker,
        posizioni_aperte_per_strumento=foto.posizioni_aperte_per_strumento,
        doppio_ingresso=da_gap,
    )
    applicate.extend(["RISK-01", "RISK-02", "RISK-03", "DEF-47"])
    if esito_size.lotti is None:
        return _non_operare(
            foto.strumento, ["RISK-03"], esito_size.motivo, applicate,
            direzione=crt.direzione, tf_crt=crt.tf, livello_stop=stop, tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )

    # --- 7. Ultima riga di difesa: i divieti permanenti (PREC-05) ---------
    proposta = esc.OrdineProposto(
        strumento=foto.strumento,
        direzione=crt.direzione,
        bias_comando=comando,
        tf_crt=crt.tf,
        key_level_preso=True,
        livello_stop=stop,
        prezzo_ingresso=prezzo_ingresso,
        posizioni_aperte_strumento=posizioni_qui,
        target_comando_raggiunto=foto.target_raggiunto_per_tf.get(tf_comando or TF.M12, False),
        indicatori_usati=("RSI",),
    )
    divieti = esc.verifica_divieti(proposta)
    if divieti:
        return _non_operare(
            foto.strumento, [d.regola for d in divieti],
            "; ".join(f"{d.regola}: {d.motivo}" for d in divieti), applicate,
            direzione=crt.direzione, tf_crt=crt.tf, livello_stop=stop, tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )
    applicate.append("PREC-05")

    # --- 8. Ordine ---------------------------------------------------------
    applicate.extend(["SETUP-03", "SETUP-04"])
    return Decisione(
        azione="SELL" if crt.direzione is Bias.SHORT else "BUY",
        strumento=foto.strumento,
        direzione=crt.direzione,
        volume=esito_size.lotti,
        livello_stop=stop,
        tp1=obiettivo_1,
        target_finale=obiettivo_1,   # esteso poi da GEST-08 alla chiusura dei TF superiori
        tf_crt=crt.tf,
        doppio_ingresso=da_gap,
        regole_applicate=tuple(dict.fromkeys(applicate)),
        motivo="tutte le condizioni soddisfatte",
        rapporto_su_tp1=rapporto,
    )
