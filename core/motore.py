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

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Mapping, Optional, Sequence

from core import contesto as ctx
from core import definizioni as dfn
from core import esclusioni as esc
from core import gestione as gest
from core import rischio as risk
from core import setup as stp
from core.definizioni import (
    Bias, Candela, Gap, KeyLevel, Mitigazione,
)
from core.config import impostazioni
from core.log import diario
from core.parametri import (
    CONFERME_ROMEO, COPPIE_CRT, INGRESSO_ROMEO,
    COSTO_SPREAD_MASSIMO_IN_R, MAX_POSIZIONI_PER_STRUMENTO,
    RISK_05_BLOCCA_DA_SOLA, TF, UNIVERSO,
)

log = diario("motore")

# Perche' ciascuna conferma di Romeo ha fermato l'operazione. Finisce nel
# motivo della decisione, quindi in archivio e su Telegram: senza, l'utente
# leggerebbe "CRT-17" e dovrebbe andarsi a cercare cosa vuol dire.
SPIEGAZIONE_CRT: dict[str, str] = {
    "CRT-06": "i CRT delle altre coppie puntano altrove",
    "CRT-10": "double purge col verso opposto",
    "CRT-11": "CISD assente sul timeframe di ingresso",
    "CRT-12": "nessuna divergenza SMT sulle compagne",
    "CRT-15": "fuori dalle finestre orarie di New York",
    "CRT-17": "la meta' del range non tiene in questa direzione",
    "CRT-18": "chiusura oltre la meta' dell'ombra dello sweep",
    "CRT-20": "ombre di N2 troppo strette",
}

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
    # Tutti i key level attivi, presi o no. Servono a SETUP-14 per il target
    # del 75% residuo: quello non richiede che il livello sia stato spazzato,
    # richiede che esista.
    key_level_correnti: Sequence[KeyLevel] = ()

    # CRT-12 — le candele degli strumenti correlati, sullo stesso timeframe
    # del CRT. Servono alla divergenza SMT e a nient'altro: senza di esse la
    # regola non si pronuncia, e non pronunciarsi non blocca.
    candele_compagne: Mapping[str, Sequence[Candela]] = field(default_factory=dict)
    # CRT-06 — i CRT trovati sulle ALTRE coppie di CRT-04, per l'allineamento.
    crt_per_tf: Mapping[TF, object] = field(default_factory=dict)

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
    # Le candele di `candele_per_tf` sono gia' prezzi del CFD?
    #
    # DEF-32 dice di analizzare sul future ed eseguire sul CFD, e quando i dati
    # arrivano da TradingView e' proprio cosi': l'archivio contiene `6J`, che
    # quota 0,0067, mentre l'ordine va su `USDJPY`, che quota 157. I livelli
    # vanno allora convertiti (`livello_cfd`, DEF-33/ESCL-12).
    #
    # Con Dukascopy o MT5 no: quei motori leggono il book del broker, cioe'
    # `USDJPY+`, e archiviano sotto `USDJPY`. I livelli NASCONO gia' in scala
    # CFD, e convertirli una seconda volta li sposta soltanto. Chi costruisce
    # la Fotografia sa da dove vengono le candele; il motore no, e infatti
    # convertiva sempre.
    analisi_in_scala_cfd: bool = False
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
    # Lo spread al momento della decisione. Non serve a decidere (CTX-03 dice
    # esplicitamente che non si filtra sullo spread): serve piu' tardi, come
    # buffer del break even di GEST-04, che PA-46 vuole multiplo dello spread
    # e non numero per strumento.
    spread: float = 0.0
    # La frazione di equity che questa posizione rischia (RISK-02). Serve
    # al ridimensionamento: senza sapere da quale rischio ciascuna
    # posizione e' partita non si sa di quanto ridurla.
    rischio: Optional[float] = None
    regole_applicate: tuple[str, ...] = ()
    regole_che_bloccano: tuple[str, ...] = ()
    motivo: str = ""
    # Registrati per le statistiche, mai per decidere (DEF-44, GIUD-01).
    rapporto_su_tp1: Optional[float] = None
    rapporto_giud01: Optional[float] = None
    # CRT-14 — cosa ha detto CIASCUNA conferma di Romeo, anche quelle spente.
    # Non serve a decidere: serve al trader discrezionale, che le pesa tutte
    # insieme invece di subirle come veti in AND. E' la regola che dice
    # "non si prende ogni istanza, il contesto decide quali istanze valgono".
    responso_romeo: Mapping[str, Optional[bool]] = field(default_factory=dict)

    def spiegazione(self) -> str:
        """Una riga leggibile, per il log e per Telegram."""
        if self.azione == "NONE":
            return f"{self.strumento}: nessuna operazione — {', '.join(self.regole_che_bloccano)}"
        return (
            f"{self.strumento}: {self.azione} {self.volume} "
            f"stop {self.livello_stop} tp1 {self.tp1} target {self.target_finale} "
            f"[{', '.join(self.regole_applicate)}]"
        )


def _sulla_scala_del_cfd(foto: "Fotografia", livello: float, ancora: float) -> float:
    """Un livello di analisi, portato sulla scala su cui partira' l'ordine.

    Quando le candele analizzate sono quelle del future, il livello va
    convertito: `6J` quota 0,0067 e `USDJPY` 157, e mandare al broker uno stop
    a 0,0067 fa chiudere la posizione al primo passaggio della sentinella.

    Quando invece arrivano da Dukascopy o da MT5 sono gia' prezzi del CFD, e
    la conversione non aggiunge niente: toglie. `livello_cfd` ancora il
    livello alla chiusura di `N2` e lo riappoggia sul prezzo di **adesso**,
    cosi' che ogni livello finisce spostato di quanto il mercato si e' mosso
    da quando `N2` ha chiuso. Misurato su XAUUSD il 2026-09-21: un livello
    strutturale a 4354,88 diventava 4356,14, cioe' +1,26, che e' esattamente
    `prezzo di adesso - chiusura di N2` (4352,94 - 4351,68). Lo stop e il
    bersaglio non stanno piu' dove la struttura li mette.

    Su `USDCHF` e `USDJPY` va peggio. Portano `segno_invertito`, giusto per i
    future `6S` e `6J` che quotano il reciproco del CFD; applicato a candele
    che sono gia' del CFD, divide invece di moltiplicare e ribalta il verso
    dello scarto. Un livello sopra la chiusura di `N2` finisce **sotto** il
    prezzo, quindi stop e bersaglio cadono dalla stessa parte dell'ingresso:
    `rapporto_rischio_rendimento` lo riconosce come dato incoerente e
    restituisce None, e GEST-01 blocca. Erano 242 blocchi su 382 in archivio
    con rapporto None, concentrati proprio li': due strumenti su sei non
    potevano aprire nulla, qualunque cosa facesse il mercato.
    """
    return dfn.livello_di_esecuzione(
        livello, ancora, foto.prezzo_cfd, foto.strumento,
        foto.analisi_in_scala_cfd)


# Le obiezioni che un trader discrezionale puo' soppesare. Tutto il resto e'
# un muro: i limiti di perdita, le esclusioni, i dati incoerenti, il tetto di
# posizioni, il freno a mano e PRIN-13 restano invalicabili anche per il
# giudizio, e questo elenco e' scritto per inclusione proprio per questo --
# una regola nuova non diventa scavalcabile per distrazione.
OBIEZIONI_SOPPESABILI: frozenset[str] = frozenset({
    "RISK-05",   # bias del DXY contraria alla direzione del CRT
    "SETUP-05",  # meno di due timeframe superiori allineati
    "SETUP-06",  # bias di comando NESSUNA
    "SETUP-07",  # direzione del CRT opposta alla bias di comando
    "SETUP-19",  # il DXY non abilita operazioni su questo strumento
    "GEST-01",   # rapporto rischio/rendimento sotto il minimo
    # Le otto conferme di Romeo: sono il quadro su cui si decide, non filtri.
    "CRT-06", "CRT-10", "CRT-11", "CRT-12",
    "CRT-15", "CRT-17", "CRT-18", "CRT-20",
})


def _apri_ogni_crt() -> bool:
    """Siamo nel modo diagnostico che apre su ogni CRT?

    Vedi `APRI_OGNI_CRT` in core/config: non e' una strategia, e' una prova
    per vedere che la catena arriva fino all'ordine. Si legge ad ogni
    chiamata e non si mette in cache, cosi' spegnerla non richiede altro.
    """
    return bool(getattr(impostazioni(), "APRI_OGNI_CRT", False))


def _obiezione_da_giudicare(blocchi: Sequence[str]) -> Optional[str]:
    """L'unica obiezione che vale la pena sottoporre al giudizio, se c'e'.

    Una sola, e soppesabile. Un CRT bocciato da tre regole insieme non e' un
    caso limite: e' un setup che nessun trader guarderebbe, e interpellare il
    giudizio su quello significa pagare una chiamata per sentirsi dire di no.
    Misurato il 2026-09-21: su 179 CRT rifiutati in sei ore, 104 erano
    bocciature triple e 44 avevano un'obiezione sola.
    """
    distinte = {b for b in blocchi if b}
    if len(distinte) != 1:
        return None
    unica = next(iter(distinte))
    return unica if unica in OBIEZIONI_SOPPESABILI else None


def _giudizio_lascia_cadere(
    foto: "Fotografia", crt, tf_trigger: TF, blocchi: Sequence[str], motivo: str,
) -> bool:
    """Il trader discrezionale scavalca questa singola obiezione?

    False in ogni caso che non sia un ACCETTA esplicito: giudizio spento,
    obiezione non soppesabile, budget esaurito, rete giu', risposta
    malformata. E' `PRIN-99` -- se non si sa, non si opera -- e qui vale
    doppio, perche' l'esito di "non so" e' aprire una posizione contro una
    regola.

    Lo stesso CRT non si giudica due volte: vive finche' vive la sua candela
    di range e il motore lo ritrova identico a ogni chiusura del timeframe
    basso. Senza questo, due CRT su USDCHF e USDJPY avrebbero prodotto
    undici chiamate ciascuno in sei ore, con lo stesso dossier e lo stesso
    verdetto.
    """
    cfg = impostazioni()
    if not getattr(cfg, "GIUDIZIO_SULLE_OBIEZIONI", False):
        return False
    obiezione = _obiezione_da_giudicare(blocchi)
    if obiezione is None:
        return False

    from core import budget_giudizio as budget

    estremo = crt.n2.massimo if crt.direzione is Bias.SHORT else crt.n2.minimo
    impronta = budget.impronta_crt(
        foto.strumento, crt.direzione.value, crt.tf.value, estremo, obiezione)

    gia = budget.gia_giudicato(impronta)
    if gia is not None:
        verdetto, perche = gia
        log.info("giudizio gia' dato su %s %s (%s): %s",
                 foto.strumento, crt.tf.value, obiezione, verdetto)
        return verdetto == "ACCETTA"

    ok, dettaglio = budget.c_e_budget()
    if not ok:
        log.warning("giudizio non interpellato su %s (%s): %s",
                    foto.strumento, obiezione, dettaglio)
        return False

    from core.dossier import costruisci
    from core.giudizio_claude import giudica_obiezione

    try:
        finta = _non_operare(foto.strumento, list(blocchi), motivo, [],
                             direzione=crt.direzione, tf_crt=crt.tf)
        verdetto = giudica_obiezione(
            costruisci(foto, finta, tf_trigger), obiezione, motivo)
    except Exception:
        log.exception("giudizio sull'obiezione fallito, la sostengo")
        return False

    budget.ricorda(impronta, foto.strumento, obiezione,
                   "ACCETTA" if verdetto.accetta else "RIFIUTA", verdetto.motivo)
    log.info("giudizio su %s %s (%s): %s",
             foto.strumento, crt.tf.value, obiezione, verdetto.registrabile)
    return verdetto.accetta


def _ingresso_differito(foto: "Fotografia", crt, tf_trigger: TF) -> bool:
    """Questo CRT si armera' invece di ordinare subito?

    Se si', il prezzo d'ingresso non esiste ancora e tutto cio' che lo
    riguarda -- GEST-01 in testa -- va verificato dopo, quando l'ordine parte
    davvero. Le condizioni sono le stesse del punto 7bis, e stanno qui in una
    funzione sola perche' due copie finirebbero per divergere proprio sul
    caso che conta.
    """
    if not INGRESSO_ROMEO:
        return False
    tf_ing = COPPIE_CRT.get(crt.tf)
    return tf_ing is not None and bool(foto.candele_per_tf.get(tf_ing))


def _verso_sul_cfd(foto: "Fotografia", direzione) -> "Bias":
    """La direzione del CRT, portata sul verso in cui parte l'ordine.

    `6S` e `6J` quotano il reciproco del CFD -- franco e yen contro dollaro,
    mentre `USDCHF` e `USDJPY` quotano il dollaro contro quelle valute --
    quindi un CRT LONG sul future e' un ordine SHORT sul CFD. `direzione_cfd`
    ribalta per questo (DEF-33).

    Ma qui le candele analizzate sono gia' quelle del CFD: un CRT LONG su
    `USDCHF` dice che USDCHF sale, e l'ordine e' un BUY su USDCHF. Ribaltarlo
    manda l'ordine dalla parte sbagliata del mercato.

    Prima di arrivare all'ordine lo stesso ribaltamento falsava SETUP-19:
    `DIREZIONE_DA_BIAS_DXY` e' scritta in direzioni CFD e dice, giustamente,
    che con dollaro forte `USDCHF` e `USDJPY` vanno comprate mentre
    `EURUSD`, `GBPUSD` e `AUDUSD` vanno vendute. Confrontarla con una
    direzione del CRT ribaltata fa sembrare contrarie proprio le due coppie
    che dal dollaro forte sono trascinate su: misurato il 2026-09-21, su
    quattro CRT SHORT di `USDCHF` il motore ne usava quattro LONG, e RISK-05
    li bloccava tutti.
    """
    return dfn.direzione_di_esecuzione(
        direzione, foto.strumento, foto.analisi_in_scala_cfd)


def _coppia_per_la_size(
    foto: "Fotografia",
    ancora: float,
    stop_analisi: float,
    stop_cfd: float,
) -> tuple[float, float]:
    """L'ancora e lo stop con cui RISK-03 misura la distanza di rischio.

    `calcola_size` lavora su una distanza adimensionale, `|ancora - stop| /
    ancora`, e la riporta sul CFD moltiplicandola per `prezzo_cfd`. Con le
    candele del future e' giusto cosi': la distanza relativa e' la stessa
    grandezza sulle due scale.

    Con candele gia' in scala CFD quella distanza viene invece misurata dalla
    chiusura di `N2` invece che dall'ingresso. Ma RISK-03 vuole il rischio
    dell'ordine, e l'ordine parte al prezzo di adesso (CTX-05: "sui prezzi
    effettivi al momento dell'ordine"). Se nel frattempo il prezzo si e'
    avvicinato allo stop il rischio vero e' minore e la size esce piccola; se
    se ne e' allontanato, esce grande. In tutti e due i casi non e' l'1% che
    RISK-01 promette.

    Qui allora si misura dove parte l'ordine: `prezzo_cfd` contro lo stop gia'
    in scala CFD. La formula di `calcola_size` non cambia, cambiano i due
    numeri che riceve -- e siccome l'ancora diventa `prezzo_cfd`, la distanza
    relativa moltiplicata per `prezzo_cfd` torna esattamente
    `|prezzo_cfd - stop|`.
    """
    if foto.analisi_in_scala_cfd:
        return foto.prezzo_cfd, stop_cfd
    return ancora, stop_analisi


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


def _rapporto_giud01(
    foto: Fotografia, crt, bersaglio_future: Optional[float]
) -> Optional[float]:
    """07_casi.md §3.1 — `distanza_kl_gap / atr_tf`, da registrare e basta.

    None quando manca uno dei due ingredienti, ed e' il caso normale: senza
    gap attivo non c'e' distanza da misurare, e con meno di quindici candele
    non c'e' ATR. Un rapporto inventato inquinerebbe proprio i dati che devono
    chiudere PA-44.

    La distanza si misura dal bordo del gap **rivolto verso il key level**,
    che e' quello che il prezzo incontrerebbe per primo venendo dal target.
    Entrambi sono livelli del future, quindi la loro differenza e' una
    quantita' del future, e l'ATR che la normalizza pure: il rapporto e'
    adimensionale e non richiede la conversione di REV-52.
    """
    if bersaglio_future is None or foto.gap_attivo is None:
        return None

    misura = dfn.atr(candele_visibili(foto.candele_per_tf.get(crt.tf, ()), foto.istante))
    if misura is None:
        return None

    gap = foto.gap_attivo
    bordo = gap.zona_inf if bersaglio_future < gap.zona_inf else gap.zona_sup
    return stp.rapporto_giud01(abs(bersaglio_future - bordo), misura)


def _spread_troppo_caro(spread: float, prezzo: float,
                        stop: float) -> Optional[str]:
    """RISK-03 — lo stop sta dentro il costo? Se si', perche'.

    Uno stop piu' vicino di dieci spread non e' uno stop stretto: e' uno stop
    dentro il rumore che lo spread stesso produce, e l'oscillazione fra bid e
    ask basta a chiuderlo. Vedi `COSTO_SPREAD_MASSIMO_IN_R` per i numeri.

    Sta in una funzione sola perche' i due ingressi -- quello armato di
    CRT-13 e quello diretto -- devono applicarla uguale. Quando stava scritta
    solo nel primo, il secondo apriva lo stesso: misurato il 2026-09-22 sulle
    53 posizioni dopo il riavvio, **36 avevano ancora lo stop dentro i dieci
    spread**, tutte passate dalla strada che il controllo non aveva.
    """
    if spread <= 0:
        return None
    rischio = abs(prezzo - stop)
    if rischio <= 0:
        return None                      # RISK-03 lo ferma altrove, come PRIN-99
    costo = spread / rischio
    if costo <= COSTO_SPREAD_MASSIMO_IN_R:
        return None
    return (f"lo spread costerebbe {costo:.2f} R: lo stop dista "
            f"{rischio / spread:.1f} spread dall'ingresso, il minimo e' "
            f"{1 / COSTO_SPREAD_MASSIMO_IN_R:.0f}")


def valuta_ingresso_armato(foto: Fotografia, tf_trigger: TF) -> Optional[Decisione]:
    """CRT-13, secondo tempo: il ritorno nell'FVG fa partire l'ordine.

    Gira alla chiusura di una candela del timeframe di INGRESSO, non di
    quello di range. Restituisce una Decisione eseguibile oppure `None`, che
    e' il caso normale: la maggior parte delle chiusure non fa scattare
    niente.

    I controlli di rischio si rifanno **qui** e non si ereditano dal momento
    in cui il setup fu armato. Fra i due momenti possono essere passate ore:
    un limite di perdita puo' essere scattato, una finestra news puo' essersi
    aperta, il tetto di posizioni puo' essersi riempito. PREC-01 dice che il
    rischio batte il setup, e un setup armato non e' un lasciapassare.
    """
    from core import ingresso_ltf

    basse = candele_visibili(foto.candele_per_tf.get(tf_trigger, ()), foto.istante)
    if len(basse) < 3:
        return None
    ingressi = ingresso_ltf.valuta_armati(foto.strumento, tf_trigger, basse)
    if not ingressi:
        return None
    ingresso = ingressi[0]

    applicate = ["CRT-13", "SETUP-13", "GEST-02"]

    # --- Lo stop deve stare FUORI dal costo (RISK-03) ---------------------
    #
    # Sta qui e non all'armamento perche' qui il prezzo d'ingresso esiste:
    # e' lo stesso motivo per cui ci sta GEST-01. La regola sta in
    # `_spread_troppo_caro`, condivisa con la strada diretta.
    troppo_caro = _spread_troppo_caro(foto.spread, ingresso.prezzo, ingresso.stop)
    if troppo_caro:
        return _non_operare(
            foto.strumento, ["RISK-03"], troppo_caro,
            applicate, direzione=ingresso.direzione, tf_crt=tf_trigger,
            livello_stop=ingresso.stop, tp1=ingresso.bersaglio_1,
        )

    # --- I controlli di rischio, rifatti adesso ---------------------------
    limiti = risk.limiti_raggiunti(
        foto.pnl_giornaliero, foto.equity_inizio_giornata,
        foto.pnl_settimanale, foto.equity_inizio_settimana,
        foto.pnl_mensile, foto.equity_inizio_mese,
    )
    posizioni_qui = foto.posizioni_aperte_per_strumento.get(foto.strumento, 0)
    evento_news = ctx.dentro_finestra_news(foto.istante, foto.strumento, foto.eventi_news)
    blocchi: list[str] = [l.regola for l in limiti]
    if evento_news is not None:
        blocchi.append("CTX-02")
    if posizioni_qui >= MAX_POSIZIONI_PER_STRUMENTO:
        blocchi.append("RISK-06")
    if not foto.dati_coerenti:
        blocchi.append("PRIN-99")
    if blocchi:
        return _non_operare(
            foto.strumento, blocchi,
            "ingresso trovato ma il rischio non lo consente (PREC-01)",
            applicate, direzione=ingresso.direzione, tf_crt=tf_trigger,
        )

    # I livelli nascono sul FUTURE e devono passare sulla scala del CFD
    # (REV-52), come per l'ingresso ordinario -- a meno che non ci siano gia'.
    ancora_prezzo = ingresso.prezzo
    try:
        stop = _sulla_scala_del_cfd(foto, ingresso.stop, ancora_prezzo)
        bersaglio = _sulla_scala_del_cfd(foto, ingresso.bersaglio_1, ancora_prezzo)
        finale = _sulla_scala_del_cfd(foto, ingresso.bersaglio_2, ancora_prezzo)
    except ValueError as errore:
        return _non_operare(
            foto.strumento, ["PRIN-99", "ESCL-12"],
            f"livelli non convertibili: {errore}", applicate,
            direzione=ingresso.direzione, tf_crt=tf_trigger)

    ancora_size, stop_size = _coppia_per_la_size(foto, ingresso.prezzo, ingresso.stop, stop)
    esito_size = risk.calcola_size(
        equity=foto.equity, strumento=foto.strumento,
        chiusura_n2_future=ancora_size, stop_future=stop_size,
        prezzo_cfd=foto.prezzo_cfd, valore_punto=foto.valore_punto,
        passo_broker=foto.passo_broker,
        posizioni_aperte_per_strumento=foto.posizioni_aperte_per_strumento,
    )
    applicate.extend(["RISK-01", "RISK-02", "RISK-03"])
    if esito_size.lotti is None:
        return _non_operare(
            foto.strumento, ["RISK-03"], esito_size.motivo, applicate,
            direzione=ingresso.direzione, tf_crt=tf_trigger)

    verso_cfd = _verso_sul_cfd(foto, ingresso.direzione)
    return Decisione(
        azione="SELL" if verso_cfd is Bias.SHORT else "BUY",
        strumento=foto.strumento,
        direzione=ingresso.direzione,
        volume=esito_size.lotti,
        livello_stop=stop,
        tp1=bersaglio,
        target_finale=finale,
        tf_crt=tf_trigger,
        spread=foto.spread,
        rischio=esito_size.rischio_percentuale,
        regole_applicate=tuple(dict.fromkeys(applicate)),
        motivo="CRT-13: ingresso sul ritorno nell'FVG dopo il CISD",
    )


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
    if ctx.calendario_impone_astensione(foto.eventi_news, foto.eta_calendario_ore):
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

    # --- 4ter. Le due conferme di Romeo che reggono (CRT-11, CRT-20) -------
    #
    # Il CISD si cerca sul timeframe di INGRESSO della coppia di CRT-04: per
    # un CRT mensile e' il giornaliero, per uno giornaliero l'orario. E' li'
    # che il cambio di consegna si vede — sul timeframe del range non c'e'
    # ancora nulla da vedere.
    tf_ingresso = COPPIE_CRT.get(crt.tf)
    # Il responso deve esistere SEMPRE: e' cio' che il trader discrezionale
    # legge, e un dossier senza le conferme di Romeo e' un dossier su cui non
    # si puo' giudicare. Vuoto solo se il timeframe del CRT non ha una coppia
    # in CRT-04, nel qual caso non c'e' un timeframe di ingresso da guardare.
    responso_romeo: dict[str, Optional[bool]] = {}
    if tf_ingresso is not None:
        serie_ingresso = candele_visibili(
            foto.candele_per_tf.get(tf_ingresso, ()), foto.istante
        )
        applicate.extend(sorted(CONFERME_ROMEO))
        ok_romeo, blocchi_romeo, responso_romeo = stp.conferme_di_romeo(
            n1=crt.n1,
            n2=crt.n2,
            candele_ingresso=serie_ingresso[-12:],
            direzione=crt.direzione,
            istante=foto.istante,
            tf_crt=crt.tf,
            candele_compagne=foto.candele_compagne,
            candele_strumento=candele,
            strumento=foto.strumento,
            crt_per_tf=foto.crt_per_tf,
        )
        if not ok_romeo and _apri_ogni_crt():
            ok_romeo, blocchi_romeo = True, ()
        if not ok_romeo:
            motivo_romeo = ("conferme di Romeo non soddisfatte: "
                            + ", ".join(SPIEGAZIONE_CRT.get(x, x) for x in blocchi_romeo))
            blocchi_qui = list(blocchi_romeo) + indipendenti
            if not _giudizio_lascia_cadere(
                    foto, crt, tf_trigger, blocchi_qui, motivo_romeo):
                fermata = _non_operare(
                    foto.strumento, blocchi_qui, motivo_romeo,
                    applicate, direzione=crt.direzione, tf_crt=crt.tf,
                )
                return replace(fermata, responso_romeo=responso_romeo)
            applicate.append("GIUD-02")

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
    stop_future = gest.stop_aggressivo(crt.n2, crt.direzione)
    tp1_future = gest.tp1(crt.n1)
    bersaglio_future = stp.target_iniziale(crt, foto.key_level_correnti)
    applicate.extend(["GEST-02", "GEST-07", "SETUP-14"])

    # Il prezzo di ingresso e' l'apertura di N3, che non esiste ancora: si usa
    # il prezzo corrente, che e' cio' che CTX-05 chiede di fare ("sui prezzi
    # effettivi al momento dell'ordine, non su quelli teorici").
    prezzo_ingresso = foto.prezzo_cfd

    # --- 4bis. I tre livelli passano sulla scala del CFD (DEF-33, ESCL-12) --
    #
    # Nascono come prezzi del FUTURE — estremi di N2, 50% di N1, key level —
    # e da qui in poi servono a tre cose che vivono tutte sul CFD: il
    # rapporto di GEST-01 contro `prezzo_ingresso`, i livelli che partono al
    # broker, e il confronto della sentinella con `prezzo_corrente`. Lasciarli
    # sulla scala del future e' il confronto che ESCL-12 vieta, e su `6J` e
    # `6S` produce numeri di due ordini di grandezza diversi.
    #
    # La size resta calcolata sui livelli FUTURE (`calcola_size`, piu' sotto):
    # li' la distanza e' gia' adimensionale e la conversione sarebbe un giro a
    # vuoto con un arrotondamento in piu'.
    ancora = crt.n2.chiusura
    try:
        stop = _sulla_scala_del_cfd(foto, stop_future, ancora)
        obiettivo_1 = _sulla_scala_del_cfd(foto, tp1_future, ancora)
        bersaglio = (
            None if bersaglio_future is None
            else _sulla_scala_del_cfd(foto, bersaglio_future, ancora)
        )
    except ValueError as errore:
        # Prezzo CFD assente o livello incoerente: PRIN-99, ci si astiene. Non
        # si manda un ordine con livelli che non si sanno leggere.
        return _non_operare(
            foto.strumento, ["PRIN-99", "ESCL-12"],
            f"livelli non convertibili sulla scala del CFD: {errore}",
            applicate,
            direzione=crt.direzione,
            tf_crt=crt.tf,
        )

    rapporto = ctx.rapporto_rischio_rendimento(prezzo_ingresso, stop, obiettivo_1)

    # --- 4bis-ter. Un parziale dietro le spalle non e' un parziale -------
    #
    # `obiettivo_1` nasce come 50% di `N1` (GEST-07): un livello del RANGE,
    # che con il prezzo di ingresso non lo confronta nessuno. Quando il
    # prezzo l'ha gia' superato, TP1 sta dalla parte dello stop, e
    # `gestione.raggiunge_tp1` lo trova centrato al primo giro di sentinella:
    # chiude il parziale e porta il resto a break even, cioe' a due spread
    # dall'ingresso, dove il tick dopo lo prende.
    #
    # Misurato il 2026-09-21 sulle 17 posizioni aperte in prova: 12 avevano
    # TP1 dal lato sbagliato, e sono vissute in media sei secondi -- aperte e
    # chiuse prima che si potessero vedere.
    #
    # In esercizio GEST-01 le ferma prima, perche' `rapporto` qui vale None
    # e CTX le blocca. Col modo diagnostico GEST-01 e' spento, e allora il
    # livello incoerente arriva al broker. Ma GEST-01 e' un filtro che si
    # puo' soppesare, e questo non lo e': un parziale alle spalle del prezzo
    # non e' un'operazione sfortunata, e' un parziale che non esiste. Si
    # toglie, e la posizione vive sul suo stop e sul suo bersaglio finale --
    # che e' esattamente cio' che GEST-04 prevede quando TP1 non c'e'.
    #
    # L'altra meta' di CRT-13 questo controllo ce l'ha gia': in
    # `ingresso_ltf.controlla` il bersaglio superato scala al lato opposto
    # (CRT-16). Qui mancava perche' qui il primo bersaglio e' uno solo.
    if rapporto is None and obiettivo_1 is not None:
        dietro = (obiettivo_1 <= prezzo_ingresso if crt.direzione is Bias.LONG
                  else obiettivo_1 >= prezzo_ingresso)
        if dietro:
            log.info("%s: TP1 %.5f gia' superato dal prezzo %.5f, nessun "
                     "parziale (GEST-04 non si applica)",
                     foto.strumento, obiettivo_1, prezzo_ingresso)
            obiettivo_1 = None

    # --- 4quater. Lo stop deve stare FUORI dal costo (RISK-03) -----------
    #
    # La stessa regola dell'ingresso armato, sulla strada diretta. Quando
    # stava scritta solo la', questa apriva lo stesso: e' da qui che passano
    # gli ordini senza CRT-13, cioe' la maggioranza.
    troppo_caro = _spread_troppo_caro(foto.spread, prezzo_ingresso, stop)
    if troppo_caro:
        return _non_operare(
            foto.strumento, ["RISK-03"], troppo_caro, applicate,
            direzione=crt.direzione, tf_crt=crt.tf,
            livello_stop=stop, tp1=obiettivo_1, rapporto_su_tp1=rapporto,
        )

    # --- 4ter. Il filtro DXY, DOPO i livelli (SETUP-19, RISK-05) ---------
    #
    # Sta qui e non prima perche' sotto le quattro ore questa obiezione
    # passa al GIUDIZIO, e un giudizio su un'operazione di cui non si
    # conosce ne' lo stop ne' il bersaglio e' un giudizio su meta' dei
    # fatti. Prima il dossier arrivava con stop, tp1, size e rapporto a
    # null -- il 2026-09-21 il giudizio stesso l'ha fatto notare: "il
    # motore non ha nemmeno prodotto stop, tp1 o size, quindi non esiste
    # un ordine costruito da far partire".
    #
    # Spostarlo qui non cambia cosa blocca: cambia che, quando tocca al
    # giudizio, il dossier contiene anche la distanza di stop e quanto
    # dell'R se ne va in spread, che e' il numero che decide.
    #
    # SETUP-19 e' scritta in direzioni **CFD**, il CRT e' rilevato sul future:
    # le due si confrontano solo dopo DEF-33. La regola descrive tre passi e
    # qui ci sono tutti e tre.
    #
    # `XAUUSD` non deriva dal DXY (PRIN-09): `direzione_da_dxy` torna None e
    # `strumento_eleggibile` lascia passare il setup proprio (PA-05).
    #
    # Con bias DXY NESSUNA, SETUP-19 dice "nessuna operazione su alcuna
    # coppia": `direzione_da_dxy` torna None e `strumento_eleggibile` blocca.
    applicate.extend(["SETUP-19", "RISK-05"])
    verso_del_setup = _verso_sul_cfd(foto, crt.direzione)            # passo 2
    verso_dal_dxy = stp.direzione_da_dxy(foto.bias_dxy, foto.strumento)  # passo 1
    if not risk.strumento_eleggibile(                                # passo 3
        strumento=foto.strumento,
        direzione_dal_dxy=verso_dal_dxy.value if verso_dal_dxy else None,
        ha_setup_proprio=True,
        direzione_del_setup=verso_del_setup.value,
    ):
        motivo = (
            f"bias DXY {foto.bias_dxy.value}: SETUP-19 non abilita alcuna "
            f"operazione su {foto.strumento}"
            if verso_dal_dxy is None else
            f"bias DXY {foto.bias_dxy.value} vuole {verso_dal_dxy.value} su "
            f"{foto.strumento}, il CRT porta a {verso_del_setup.value}"
        )
        blocchi_dxy = ["RISK-05"] + indipendenti
        # Su un range alto la bias del dollaro e' il contesto che domina
        # l'operazione e ferma da sola; su uno scalp e' rumore, e la parola
        # passa al giudizio. Vedi `RISK_05_BLOCCA_DA_SOLA` in core/parametri.
        assoluta = (crt.tf.value in RISK_05_BLOCCA_DA_SOLA
                    and not _apri_ogni_crt())
        cade = _apri_ogni_crt() or (
            not assoluta
            and _giudizio_lascia_cadere(foto, crt, tf_trigger, blocchi_dxy, motivo))
        if not cade:
            return _non_operare(
                foto.strumento, blocchi_dxy, motivo, applicate,
                direzione=crt.direzione, tf_crt=crt.tf,
            )
        applicate.append("GIUD-02")


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
        # Con CRT-13 l'ordine parte al ritorno nell'FVG e il prezzo di
        # ingresso qui non esiste ancora: GEST-01 si verifica la', dove i
        # numeri sono quelli veri. Vedi `contesto.filtri_attivi`.
        rapporto_differito=_ingresso_differito(foto, crt, tf_trigger),
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

    if _apri_ogni_crt():
        # Restano solo i muri: tutto cio' che un trader potrebbe soppesare
        # cade, il resto no. L'elenco e' quello di `OBIEZIONI_SOPPESABILI`,
        # scritto per inclusione, piu' GEST-01.
        morbide = OBIEZIONI_SOPPESABILI | {"GEST-01"}
        filtri = tuple(f for f in filtri if f.regola not in morbide)
        blocchi = [b for b in blocchi if b not in morbide]

    motivo_filtri = ("; ".join(f"{f.regola}: {f.motivo}" for f in filtri)
                     or "condizioni non soddisfatte")
    if blocchi and _giudizio_lascia_cadere(
            foto, crt, tf_trigger, blocchi, motivo_filtri):
        applicate.append("GIUD-02")
        blocchi = []

    if blocchi:
        return _non_operare(
            foto.strumento, blocchi, motivo_filtri,
            applicate,
            direzione=crt.direzione,
            tf_crt=crt.tf,
            livello_stop=stop,
            tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )

    # --- 6. Size (RISK-01, RISK-02, RISK-03, DEF-47) ----------------------
    n2_future = crt.n2.chiusura
    ancora_size, stop_size = _coppia_per_la_size(foto, n2_future, stop_future, stop)
    esito_size = risk.calcola_size(
        equity=foto.equity,
        strumento=foto.strumento,
        chiusura_n2_future=ancora_size,
        stop_future=stop_size,
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
        # ESCL-15 controlla che ogni indicatore dichiarato sia fra quelli
        # ammessi. Qui si dichiarava `("RSI",)` per un indicatore che nessuno
        # calcola: `definizioni.rsi` e `definizioni.divergenza_rsi` hanno zero
        # chiamanti in produzione, e PA-39 ha deciso che l'RSI resta
        # statistica e non entra in nessuna decisione.
        #
        # Una dichiarazione falsa qui non e' cosmetica: e' la riga che
        # renderebbe silenzioso un uso vero e non ammesso, perche' ESCL-15
        # validerebbe un elenco scritto a mano invece di quello reale. Il
        # motore non usa alcun indicatore: lo dice.
        indicatori_usati=(),
    )
    divieti = esc.verifica_divieti(proposta)
    if _apri_ogni_crt():
        # Nel modo diagnostico cadono i DIVIETI DI STRATEGIA, non quelli che
        # proteggono il conto. `ESCL-01` e' `SETUP-07` riscritto come muro --
        # "ordine contro bias_comando" -- e `ESCL-03` e' `SETUP-08`: sono le
        # stesse due regole che il modo ha gia' spento fra i filtri, e
        # lasciarle qui significa spegnerle a meta'.
        #
        # Tutto il resto resta: ESCL-02 (nessun key level preso) e ESCL-04
        # (timeframe non ammesso) sono strutturali -- senza di essi non c'e'
        # un CRT di cui parlare -- ed ESCL-11 e' il tetto di posizioni.
        DIVIETI_DI_STRATEGIA = {"ESCL-01", "ESCL-03"}
        divieti = tuple(d for d in divieti if d.regola not in DIVIETI_DI_STRATEGIA)
    if divieti:
        return _non_operare(
            foto.strumento, [d.regola for d in divieti],
            "; ".join(f"{d.regola}: {d.motivo}" for d in divieti), applicate,
            direzione=crt.direzione, tf_crt=crt.tf, livello_stop=stop, tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )
    applicate.append("PREC-05")

    # --- 7bis. CRT-13 — si ARMA, non si ordina ----------------------------
    #
    # Romeo non entra alla chiusura della candela di range: entra sul
    # timeframe basso, sul ritorno nell'FVG dopo il CISD. Sono due momenti
    # separati nel tempo, e il secondo puo' non arrivare mai.
    #
    # Qui il CRT ha superato ogni controllo: si mette in attesa. L'ordine
    # partira' da `ingresso_ltf.controlla` alla chiusura di una candela del
    # timeframe di ingresso, se e quando il prezzo torna nel vuoto.
    #
    # Misurato su `4h -> 15m`: winrate da 30,8% a 62,4%, da -0,0782 a
    # +0,3613 R. Non e' una regolazione, e' un'altra operazione.
    # Si arma solo se i dati del timeframe di ingresso ci sono davvero:
    # senza quelli il ritorno nell'FVG non si puo' vedere, e un setup armato
    # che nessuno potra' mai far scattare e' peggio di un ingresso mediocre.
    ha_ltf = bool(foto.candele_per_tf.get(tf_ingresso)) if tf_ingresso else False
    if INGRESSO_ROMEO and tf_ingresso is not None and ha_ltf:
        from core import ingresso_ltf

        applicate.append("CRT-13")
        ingresso_ltf.arma(
            strumento=foto.strumento,
            direzione=crt.direzione,
            tf_crt=crt.tf,
            tf_ingresso=tf_ingresso,
            estremo_sweep=crt.n2.massimo if crt.direzione is Bias.SHORT else crt.n2.minimo,
            eq_range=(crt.n1.massimo + crt.n1.minimo) / 2,
            lato_opposto=crt.n1.minimo if crt.direzione is Bias.SHORT else crt.n1.massimo,
        )
        # CRT-13 e' la regola che impedisce l'ordine IMMEDIATO, e va
        # dichiarata: una decisione NONE senza regola che la imponga
        # sarebbe un errore del motore.
        armata = _non_operare(
            foto.strumento, ["CRT-13"],
            "CRT-13: setup armato, attendo il ritorno nell'FVG sul "
            f"{tf_ingresso.value}",
            applicate,
            direzione=crt.direzione, tf_crt=crt.tf,
            livello_stop=stop, tp1=obiettivo_1, rapporto_su_tp1=rapporto,
        )
        return replace(armata, responso_romeo=responso_romeo)

    # --- 7bis. Un bersaglio deve esistere (SETUP-14, PRIN-99) --------------
    # Sta DOPO i divieti e non prima: PREC-05 vuole le esclusioni come ultimo
    # controllo, e un'astensione che le scavalcasse nasconderebbe il motivo
    # vero per cui quell'ordine non andava mandato.
    if bersaglio is None:
        return _non_operare(
            foto.strumento, ["PRIN-99"],
            f"SETUP-14: nessun key level su {crt.tf.value} o superiore a cui "
            "portare il 75% residuo",
            applicate,
            direzione=crt.direzione, tf_crt=crt.tf, livello_stop=stop, tp1=obiettivo_1,
            rapporto_su_tp1=rapporto,
        )

    # --- 7ter. Il dato che deve chiudere PA-44 (GIUD-01, 07_casi.md §3.1) --
    #
    # Si REGISTRA, non si decide: `giud01_scelta_target` risponde sempre C —
    # "il target resta al key level" — perche' la soglia fra "vicini" e
    # "distanti" non esiste, e inventarla sarebbe la cosa peggiore, perche'
    # sembrerebbe funzionare.
    #
    # Il `rapporto` e' distanza key level/gap normalizzata sull'ATR. L'ATR e'
    # ammesso qui e solo qui (ESCL-15 b), come unita' di misura e mai come
    # generatore di segnali. Senza questo campo PA-44 non potrebbe chiudersi
    # coi numeri: resterebbe un punto aperto per sempre, che e' dove stava.
    rapporto_kl_gap = _rapporto_giud01(foto, crt, bersaglio_future)
    applicate.append("GIUD-01")

    # --- 8. Ordine ---------------------------------------------------------
    applicate.extend(["SETUP-03", "SETUP-04", "DEF-33"])

    # DEF-33 — quando il CRT e' rilevato sul FUTURE l'ordine va al CFD, e per
    # `6J` e `6S` i due hanno segno opposto: quei future quotano yen e franco
    # contro dollaro, i CFD quotano il dollaro contro quelle valute, quindi un
    # CRT short su `6J` e' un BUY su `USDJPY`.
    #
    # Quando invece si analizzano gia' le candele del CFD -- Dukascopy e MT5
    # leggono il book del broker -- non c'e' niente da ribaltare: un CRT short
    # su `USDJPY` e' un SELL su `USDJPY`. Decide `_verso_sul_cfd`, al punto
    # 4bis, in base a `foto.analisi_in_scala_cfd`.
    #
    # `direzione` resta comunque quella letta sulle candele, perche' e' con
    # quel segno che il CRT e' stato riconosciuto e con quel segno vanno
    # interpretate le regole di setup. Verso il broker parte `azione`, e i tre
    # livelli sono gia' passati dal punto 4bis.
    verso_cfd = verso_del_setup      # gia' convertito al punto 4bis
    return Decisione(
        azione="SELL" if verso_cfd is Bias.SHORT else "BUY",
        strumento=foto.strumento,
        direzione=crt.direzione,
        volume=esito_size.lotti,
        livello_stop=stop,
        tp1=obiettivo_1,
        target_finale=bersaglio,     # esteso poi da GEST-08 alla chiusura dei TF superiori
        tf_crt=crt.tf,
        doppio_ingresso=da_gap,
        spread=foto.spread,
        rischio=esito_size.rischio_percentuale,
        regole_applicate=tuple(dict.fromkeys(applicate)),
        motivo="tutte le condizioni soddisfatte",
        rapporto_su_tp1=rapporto,
        rapporto_giud01=rapporto_kl_gap,
        # Le conferme di Romeo viaggiano fino al giudice anche qui: senza,
        # meta' dei setup gli arriverebbe senza il quadro su cui decidere.
        responso_romeo=responso_romeo,
    )
