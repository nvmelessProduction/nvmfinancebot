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

from bisect import bisect_right
from collections.abc import Sequence as _SequenzaAstratta
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

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
    COSTO_SPREAD_MASSIMO_IN_R,
    RAPPORTO_MINIMO,
    MAX_POSIZIONI_PER_STRUMENTO,
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

    ## Perche' e' scritta cosi' e non in una riga

    Questa funzione e' il punto piu' caldo di tutto il bot. Misurato il
    2026-09-23 con `cProfile` su una valutazione sola: **190 chiamate, 2,7
    secondi**, dei quali 5,5 dentro `sorted` su 9,4 milioni di confronti.
    Riordinava l'intero archivio -- 285.000 candele per `EURUSD` -- ad ogni
    chiamata, e le candele arrivano gia' ordinate dall'archivio.

    Con quel costo un giro completo sui sei strumenti durava novanta secondi,
    e l'alert arrivava al motore gia' vecchio: le tre operazioni decise il
    2026-09-23 sono state tutte bloccate da "alert vecchio di 22-55s".

    Due mosse, e nessuna delle due rinuncia alla barriera:

    - **ricerca binaria** invece del filtro lineare, che vale perche' la
      serie e' ordinata. Se non lo fosse si ricade sul percorso vecchio.
    - **una memoria cortissima** sull'ultimo istante: dentro una valutazione
      l'istante non cambia e le stesse serie vengono richieste decine di
      volte. La memoria tiene un riferimento alla serie, quindi `id()` resta
      valido finche' la voce e' in cache.
    """
    if not candele:
        return ()

    chiave = (id(candele), istante)
    memoria = _MEMORIA_VISIBILI
    if memoria.get("istante") is not istante:
        memoria.clear()
        memoria["istante"] = istante
    trovato = memoria.get(chiave)
    if trovato is not None:
        return trovato[1]

    if candele[0].orario <= candele[-1].orario and _ordinata(candele):
        taglio = bisect_right(_OrariDi(candele), istante)
        fuori = tuple(candele[:taglio])
    else:
        fuori = tuple(sorted((c for c in candele if c.orario <= istante),
                             key=lambda c: c.orario))
    # Il riferimento alla serie va tenuto: senza, l'oggetto potrebbe essere
    # liberato e un altro riusare lo stesso `id()`.
    memoria[chiave] = (candele, fuori)
    return fuori


# L'ultimo istante valutato e i suoi tagli. Si svuota da sola al cambio di
# istante, quindi non cresce e non tiene in vita serie vecchie.
_MEMORIA_VISIBILI: dict = {}


class _OrariDi(_SequenzaAstratta):
    """Gli orari di una serie, senza costruirne la lista.

    `bisect` vuole una sequenza indicizzabile: costruire la lista degli orari
    costerebbe la scansione che si sta cercando di evitare.
    """

    __slots__ = ("_candele",)

    def __init__(self, candele: Sequence[Candela]) -> None:
        self._candele = candele

    def __len__(self) -> int:
        return len(self._candele)

    def __getitem__(self, i):
        return self._candele[i].orario


def _ordinata(candele: Sequence[Candela]) -> bool:
    """La serie e' gia' in ordine di chiusura?

    Il controllo costa una scansione, ma senza confronti di chiave e senza
    allocare: su 285.000 candele sono millisecondi contro i secondi di
    `sorted`. Serve perche' la barriera non puo' dipendere da una promessa:
    se un giorno arrivasse una serie disordinata, il percorso vecchio la
    gestisce comunque.
    """
    precedente = None
    for c in candele:
        if precedente is not None and c.orario < precedente:
            return False
        precedente = c.orario
    return True


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
    # Quanto costa un giro completo su un lotto, gia' convertito in distanza
    # di prezzo. Su un conto RAW e' quasi tutto il costo e lo spread e' zero;
    # su un conto standard e' zero e il costo sta nello spread. Lo riempie
    # chi costruisce la Fotografia, che sa su che conto sta girando.
    costo_commissione: float = 0.0
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
    # COSA HA VISTO, in numeri: il range letto, l'estremo superato, il
    # rientro, il livello preso e su quale coppia di timeframe. Senza questi
    # il messaggio diceva "aperto, stop qui, target la'" e chi legge non
    # poteva risalire a quale disegno fosse stato riconosciuto -- ne'
    # verificarlo sul grafico, che e' l'unico modo per capire dove sbaglia.
    lettura_crt: Optional[Mapping[str, Any]] = None

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


def _range_della_coppia(tf_esecuzione: TF) -> Optional[TF]:
    """Di quale coppia di CRT-04 questo timeframe e' il lato di ESECUZIONE.

    `COPPIE_CRT` mappa range -> esecuzione; qui serve il verso opposto,
    perche' il CRT si forma quando chiude una candela BASSA e il range va
    cercato in alto.
    """
    for alto, basso in COPPIE_CRT.items():
        if basso is tf_esecuzione:
            return alto
    return None


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
    # Il raffinamento si cerca UN GRADINO PIU' SOTTO del timeframe su cui il
    # CRT si e' appena formato, non su quello stesso.
    #
    # Prima era `COPPIE_CRT.get(crt.tf)`, cioe' il lato di esecuzione della
    # coppia del range -- ed e' esattamente il timeframe su cui il CRT e'
    # appena nato. Si armava per aspettare un ritorno sulle stesse barre che
    # avevano appena prodotto il rientro: un doppione.
    #
    # Adesso che SETUP-02 forma il CRT alla chiusura della barra bassa che
    # rientra, quel momento E' l'ingresso -- "a volte si entra sulla seconda
    # candela e non sulla terza". Il ritorno nell'FVG resta un raffinamento
    # possibile, ma su un timeframe ancora piu' fine.
    tf_ing = COPPIE_CRT.get(tf_trigger)
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


def chiedi_la_size(foto: "Fotografia", crt, livelli):
    """RISK-01, RISK-02, RISK-03, DEF-47 — quanti lotti.

    Il calcolo lavora sulla scala del FUTURE, dove la distanza e' gia'
    adimensionale: convertirla sarebbe un giro a vuoto con un arrotondamento
    in piu'. `_coppia_per_la_size` sceglie la coppia ancora/stop coerente con
    l'archivio da cui i livelli vengono, perche' quando le candele sono del
    CFD anche l'ancora deve esserlo.

    `doppio_ingresso` dimezza la size (RISK-04): due ingressi sulla stessa
    idea non possono rischiare come due idee diverse.
    """
    ancora, stop_scala = _coppia_per_la_size(
        foto, crt.n2.chiusura, livelli.stop_future, livelli.stop)
    return risk.calcola_size(
        equity=foto.equity,
        strumento=foto.strumento,
        chiusura_n2_future=ancora,
        stop_future=stop_scala,
        prezzo_cfd=foto.prezzo_cfd,
        valore_punto=foto.valore_punto,
        passo_broker=foto.passo_broker,
        posizioni_aperte_per_strumento=foto.posizioni_aperte_per_strumento,
        doppio_ingresso=livelli.da_gap,
    )


@dataclass(frozen=True)
class Preludio:
    """Cosa si sa prima ancora di cercare un CRT."""

    contesto: Any = None
    comando: Any = None
    tf_comando: Any = None
    # L'astensione gia' costruita, quando uno dei cancelli chiude. Chi chiama
    # la restituisce e basta: qui non c'e' orchestrazione da fare, il cancello
    # E' la decisione.
    astensione: Optional[Decisione] = None


def preludio(foto: "Fotografia", tf_trigger: TF) -> Preludio:
    """ESCL-05, PA-55, SETUP-06 — i tre cancelli che precedono il CRT.

    1. **Lo strumento e' nell'universo** (ESCL-05, PRIN-08). Fuori da quei sei
       non si opera, e non c'e' niente da valutare.
    2. **Il calendario news e' utilizzabile** (PA-55). Assente o troppo
       vecchio: astensione dichiarata, non silenziosa.
    3. **C'e' una bias di comando** (SETUP-06). Senza, non esiste la direzione
       rispetto a cui un CRT sarebbe a favore o contro.

    Porta con se' anche i divieti di contesto, che vanno calcolati comunque:
    altrimenti la statistica "quante volte ciascun filtro ha impedito
    un'operazione" vedrebbe sempre e solo il primo blocco, e non direbbe mai
    se un filtro non scatta.

    Sui primi due cancelli i divieti di contesto non sono ancora calcolati, e
    l'astensione non li nomina: dichiararli sarebbe dire che sono stati
    valutati quando non lo sono stati.
    """
    if foto.strumento not in UNIVERSO:
        return Preludio(astensione=_non_operare(
            foto.strumento, ["ESCL-05"], "strumento fuori da PRIN-08"))

    if ctx.calendario_impone_astensione(foto.eventi_news, foto.eta_calendario_ore):
        return Preludio(astensione=_non_operare(
            foto.strumento, ["PRIN-99"],
            "calendario news assente o troppo vecchio: PA-55 impone astensione"))

    contesto = blocchi_indipendenti(foto, tf_trigger)
    comando, tf_comando = stp.bias_comando(
        foto.bias_per_tf, foto.target_raggiunto_per_tf)
    if comando is Bias.NESSUNA:
        return Preludio(contesto=contesto, astensione=_non_operare(
            foto.strumento, ["SETUP-06"] + contesto.blocchi,
            "nessuna bias di comando", ["SETUP-06"]))
    return Preludio(contesto=contesto, comando=comando, tf_comando=tf_comando)


def arma_il_setup(foto: "Fotografia", crt, tf_ingresso: Optional[TF]) -> bool:
    """CRT-13 — mette il setup in attesa del ritorno nell'FVG. Armato?

    Romeo non entra alla chiusura della candela di range: entra sul timeframe
    basso, sul ritorno nell'FVG dopo il CISD. Sono due momenti separati nel
    tempo, e il secondo puo' non arrivare mai. L'ordine partira' da
    `ingresso_ltf.controlla` alla chiusura di una candela del timeframe di
    ingresso, se e quando il prezzo torna nel vuoto.

    Misurato su `4h -> 15m`: winrate da 30,8% a 62,4%, da -0,0782 a +0,3613 R.
    Non e' una regolazione, e' un'altra operazione.

    **Si arma solo se i dati del timeframe di ingresso ci sono davvero**:
    senza quelli il ritorno nell'FVG non si puo' vedere, e un setup armato che
    nessuno potra' mai far scattare e' peggio di un ingresso mediocre.
    """
    if not INGRESSO_ROMEO or tf_ingresso is None:
        return False
    if not foto.candele_per_tf.get(tf_ingresso):
        return False

    from core import ingresso_ltf

    corta = crt.direzione is Bias.SHORT
    ingresso_ltf.arma(
        strumento=foto.strumento,
        direzione=crt.direzione,
        tf_crt=crt.tf,
        tf_ingresso=tf_ingresso,
        estremo_sweep=crt.n2.massimo if corta else crt.n2.minimo,
        eq_range=(crt.n1.massimo + crt.n1.minimo) / 2,
        lato_opposto=crt.n1.minimo if corta else crt.n1.massimo,
    )
    return True


def componi_ordine(
    foto: "Fotografia", crt, tf_trigger: TF, verso_cfd, livelli, obiettivo_1,
    esito_size, applicate: list, responso_romeo: dict,
    rapporto_kl_gap: Optional[float],
) -> Decisione:
    """SETUP-03, SETUP-04, DEF-33 — l'ordine, quando tutto ha retto.

    `verso_cfd` e' gia' convertito (DEF-33): `direzione` resta quella letta
    sulle candele del future, perche' e' con quel segno che il CRT e' stato
    riconosciuto e con quel segno vanno interpretate le regole di setup. Al
    broker parte `azione`.

    `regole_applicate` passa da `dict.fromkeys` e non da `set`: l'ordine in
    cui le regole sono state valutate e' informazione, e un insieme lo
    butterebbe via.
    """
    return Decisione(
        azione="SELL" if verso_cfd is Bias.SHORT else "BUY",
        strumento=foto.strumento,
        direzione=crt.direzione,
        volume=esito_size.lotti,
        livello_stop=livelli.stop,
        tp1=obiettivo_1,
        # Esteso poi da GEST-08 alla chiusura dei timeframe superiori.
        target_finale=livelli.bersaglio,
        tf_crt=crt.tf,
        doppio_ingresso=livelli.da_gap,
        spread=foto.spread,
        rischio=esito_size.rischio_percentuale,
        regole_applicate=tuple(dict.fromkeys(applicate)),
        motivo="tutte le condizioni soddisfatte",
        rapporto_su_tp1=livelli.rapporto,
        rapporto_giud01=rapporto_kl_gap,
        responso_romeo=responso_romeo,
        lettura_crt=_lettura_del_crt(crt, tf_trigger),
    )


@dataclass(frozen=True)
class RespondoConferme:
    """Cosa hanno detto le otto conferme, e se fermano."""

    responso: dict
    blocchi: tuple = ()
    motivo: Optional[str] = None


def interroga_conferme(
    foto: "Fotografia", crt, basse: list, diagnostico: bool,
) -> RespondoConferme:
    """CRT-06/10/11/12/15/17/18/20 — le otto conferme di Romeo.

    Si valutano sulle barre di ESECUZIONE: dopo la riscrittura secondo
    SETUP-02 il Power of Three si svolge dentro la candela di riferimento
    successiva, e li' si legge. Sul timeframe del range non c'e' ancora nulla
    da vedere.

    Il responso esiste SEMPRE, anche quando qualcuna ferma: e' cio' che il
    trader discrezionale legge, ed e' il dato su cui si potra' pesare ciascuna
    conferma (CRT-14). Col modo `diagnostico` nessuna ferma, ma il responso si
    calcola lo stesso -- altrimenti si perderebbe proprio il dato che quel
    modo esiste per raccogliere.
    """
    ok, blocchi, responso = stp.conferme_di_romeo(
        n1=crt.n1,
        n2=crt.n2,
        candele_ingresso=basse[-12:],
        direzione=crt.direzione,
        istante=foto.istante,
        tf_crt=crt.tf,
        candele_compagne=foto.candele_compagne,
        candele_strumento=basse,
        strumento=foto.strumento,
        crt_per_tf=foto.crt_per_tf,
        # Le barre VERE della fase di manipolazione: CRT-10 e CRT-18 leggono
        # la forma delle candele, e la sintetica ne rappresenta una sola.
        barre_fase=getattr(crt, "barre_fase", ()),
    )
    if ok or diagnostico:
        return RespondoConferme(responso=responso)
    return RespondoConferme(
        responso=responso, blocchi=tuple(blocchi),
        motivo=("conferme di Romeo non soddisfatte: "
                + ", ".join(SPIEGAZIONE_CRT.get(x, x) for x in blocchi)),
    )


@dataclass(frozen=True)
class RicercaCrt:
    """Il CRT trovato, oppure la regola per cui non c'e'."""

    crt: Any = None
    barre: tuple = ()
    regola: Optional[str] = None
    motivo: Optional[str] = None


def trova_crt(foto: "Fotografia", tf_trigger: TF) -> RicercaCrt:
    """SETUP-00, SETUP-02, CRT-04 — cerca il CRT su questa coppia.

    `tf_trigger` e' il timeframe di ESECUZIONE: la candela appena chiusa su
    cui si cerca il rientro. Il RANGE e' la candela di riferimento del
    timeframe alto della coppia, e le barre in cui cercare manipolazione e
    rientro sono quelle di `tf_trigger` chiuse DOPO di essa -- cioe' dentro la
    candela di riferimento successiva.

    Restituisce anche `barre`, che servono a valle: e' su quelle che si legge
    il CISD e si misura la divergenza SMT.

    **Perche' il range non e' `tf_trigger` stesso.** `CRT-04` dice che il CRT
    e' una COPPIA -- range sull'alto, sweep e ingresso sul basso -- e le sue
    coppie piu' piccole sono `15m -> 1m` e `5m -> 15s`. Un range da un minuto
    non esiste in nessuna di esse. Prima qui si prendevano le ultime due
    candele di `tf_trigger` qualunque fosse: con un alert su `M1` il range era
    un minuto e l'ingresso lo stesso minuto, cioe' tre candele dello stesso
    timeframe -- l'errore che `REV-50` ha corretto in `SETUP-01`, *"che e'
    un'altra strategia"*.

    Non e' teoria, e' tutto cio' che il bot ha fatto. Misurato il 2026-09-22
    su 458 ordini: **317 da `M1min` e 141 da `M5`, zero da un timeframe di
    range valido**. Il motivo e' meccanico: su un timeframe di range
    `INGRESSO_ROMEO` fa ARMARE il setup e l'ordine parte dopo, dal ritorno
    nell'FVG; su `M1` e `M5` non esiste una coppia in cui fare da range,
    quindi non si poteva armare e si cadeva dritti sull'ordine a mercato. La
    strada diretta sparava solo dove non doveva.

    Quegli alert servono comunque, e li usa `valuta_ingresso_armato`: sono il
    secondo tempo di CRT-13, dove un setup gia' armato trova il suo ingresso.
    Li' non c'e' un CRT nuovo da cercare.
    """
    tf_range = _range_della_coppia(tf_trigger)
    if tf_range is None:
        return RicercaCrt(regola="CRT-04", motivo=(
            f"{tf_trigger.value} non e' il timeframe di esecuzione di nessuna "
            "coppia di CRT-04: non c'e' un range di cui essere la coppia"))

    alte = candele_visibili(foto.candele_per_tf.get(tf_range, ()), foto.istante)
    if not alte:
        return RicercaCrt(regola="DEF-26", motivo=(
            f"storia insufficiente su {tf_range.value}: manca la candela di "
            "riferimento che definisce il range"))

    c_rif = alte[-1]
    basse = candele_visibili(foto.candele_per_tf.get(tf_trigger, ()), foto.istante)
    barre = tuple(c for c in basse if c.orario > c_rif.orario)

    crt = stp.cerca_crt(c_rif, list(barre), tf_range, foto.key_level_presi)
    if crt is None:
        return RicercaCrt(barre=tuple(basse), regola="SETUP-00", motivo=(
            "nessun CRT valido: serve la presa di un key level di timeframe "
            "superiore"))
    return RicercaCrt(crt=crt, barre=tuple(basse))


@dataclass(frozen=True)
class Livelli:
    """I tre livelli di un CRT, gia' sulla scala su cui partira' l'ordine."""

    da_gap: bool
    prezzo_ingresso: float
    stop: float
    obiettivo_1: float
    bersaglio: Optional[float]
    # Sulla scala del FUTURE: `calcola_size` lavora li', dove la distanza e'
    # gia' adimensionale, e `_rapporto_giud01` ci misura l'ATR.
    stop_future: float
    bersaglio_future: Optional[float]
    rapporto: Optional[float]


def filtri_e_esclusioni(
    foto: "Fotografia", crt, tf_trigger: TF, comando, contesto,
    rapporto: Optional[float], da_gap: bool, diagnostico: bool,
) -> tuple[list[str], str]:
    """REV-17, PREC-04, SETUP-09 — i filtri uniti e cosa hanno detto.

    Restituisce `(blocchi, motivo)`. Vuoto il primo, si opera.

    **L'unione di tre elenchi, e nessuno dei tre e' normativo da solo.** Per
    REV-17 le esclusioni sono l'unione di `SETUP-15` e `CTX-01`, che NON
    coincidono: `contesto.filtri_attivi` porta la sua meta', `setup.
    esclusioni_setup` l'altra. A queste si aggiunge `SETUP-09` quando
    l'ingresso e' da gap, e i divieti di contesto che valgono comunque.

    Il `motivo` nomina solo i filtri di `CTX-01`, perche' sono quelli che
    portano con se' una spiegazione leggibile; le altre due famiglie parlano
    per codice di regola, e il codice basta a ritrovarle nei documenti.

    Col modo `diagnostico` cadono le obiezioni SOPPESABILI, piu' `GEST-01`:
    il rapporto su TP1 e' un giudizio sul valore dell'operazione, non una
    salvaguardia del conto. Cadono dai blocchi E dai filtri, perche' se
    restassero nei filtri il motivo nominerebbe una regola che non sta
    fermando niente.
    """
    allineato = stp.allineamento_soddisfatto(
        crt.tf, foto.sbilanciamenti, crt.direzione)
    limite = bool(contesto.limiti)

    filtri = ctx.filtri_attivi(
        adesso=foto.istante,
        strumento=foto.strumento,
        key_level_preso=True,
        comando=comando,
        direzione_crt=crt.direzione,
        allineamento_ok=allineato,
        rapporto_su_tp1=rapporto,
        posizioni_aperte_strumento=contesto.posizioni_qui,
        limite_rischio_raggiunto=limite,
        eventi_news=foto.eventi_news,
        mitigazione_non_determinata=(
            da_gap and foto.mitigazione is Mitigazione.NON_DETERMINATA),
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
        posizioni_aperte_strumento=contesto.posizioni_qui,
        limite_rischio_raggiunto=limite,
        dentro_finestra_news=contesto.evento_news is not None,
        dati_coerenti=foto.dati_coerenti,
        da_gap=da_gap,
        mitigazione=foto.mitigazione,
    )
    # SETUP-09: un ingresso da gap vuole la terza fase, non una qualsiasi.
    blocchi_gap: tuple[str, ...] = ()
    if da_gap:
        _, blocchi_gap = stp.ingresso_da_gap_ammesso(foto.gap_fase, foto.mitigazione)

    blocchi = ([f.regola for f in filtri] + list(esclusi)
               + list(blocchi_gap) + list(contesto.blocchi))

    if diagnostico:
        morbide = OBIEZIONI_SOPPESABILI | {"GEST-01"}
        filtri = tuple(f for f in filtri if f.regola not in morbide)
        blocchi = [b for b in blocchi if b not in morbide]

    motivo = ("; ".join(f"{f.regola}: {f.motivo}" for f in filtri)
              or "condizioni non soddisfatte")
    return blocchi, motivo


def divieti_permanenti(
    foto: "Fotografia", crt, comando, tf_comando, stop: float,
    prezzo_ingresso: float, posizioni_qui: int, diagnostico: bool,
) -> tuple:
    """PREC-05 — l'ultima riga di difesa, prima che l'ordine parta.

    Restituisce i divieti violati, vuoto se non ce n'e'. Non decide: chi
    chiama dichiara l'astensione.

    `indicatori_usati=()` non e' cosmetica. ESCL-15 controlla che ogni
    indicatore dichiarato sia fra quelli ammessi; qui si dichiarava `("RSI",)`
    per un indicatore che nessuno calcola -- `definizioni.rsi` e
    `divergenza_rsi` hanno zero chiamanti in produzione, e PA-39 ha deciso che
    l'RSI resta statistica. Una dichiarazione falsa renderebbe silenzioso un
    uso vero e non ammesso, perche' ESCL-15 validerebbe un elenco scritto a
    mano invece di quello reale. Il motore non usa alcun indicatore: lo dice.

    Nel modo diagnostico cadono i DIVIETI DI STRATEGIA, non quelli che
    proteggono il conto. `ESCL-01` e' `SETUP-07` riscritto come muro -- ordine
    contro `bias_comando` -- ed `ESCL-03` e' `SETUP-08`: sono le stesse due
    regole che quel modo ha gia' spento fra i filtri, e lasciarle qui
    significherebbe spegnerle a meta'. Tutto il resto resta: ESCL-02 (nessun
    key level preso) ed ESCL-04 (timeframe non ammesso) sono strutturali --
    senza di essi non c'e' un CRT di cui parlare -- ed ESCL-11 e' il tetto di
    posizioni.
    """
    proposta = esc.OrdineProposto(
        strumento=foto.strumento,
        direzione=crt.direzione,
        bias_comando=comando,
        tf_crt=crt.tf,
        key_level_preso=True,
        livello_stop=stop,
        prezzo_ingresso=prezzo_ingresso,
        posizioni_aperte_strumento=posizioni_qui,
        target_comando_raggiunto=foto.target_raggiunto_per_tf.get(
            tf_comando or TF.M12, False),
        indicatori_usati=(),
    )
    divieti = esc.verifica_divieti(proposta)
    if diagnostico:
        di_strategia = {"ESCL-01", "ESCL-03"}
        divieti = tuple(d for d in divieti if d.regola not in di_strategia)
    return divieti


def tp1_alle_spalle(
    obiettivo_1: Optional[float],
    prezzo_ingresso: float,
    verso_ordine: Bias,
) -> bool:
    """GEST-04, GEST-07 — il parziale sta gia' dietro il prezzo?

    `obiettivo_1` nasce come 50% di `N1` (GEST-07): un livello del RANGE, che
    col prezzo di ingresso non lo confronta nessuno. Quando il prezzo l'ha
    gia' superato, TP1 sta dalla parte dello stop e `gestione.raggiunge_tp1`
    lo trova centrato al primo giro di sentinella: chiude il parziale e porta
    il resto a break even, cioe' a due spread dall'ingresso, dove il tick dopo
    lo prende.

    Misurato il 2026-09-21 sulle 17 posizioni aperte in prova: **12 avevano
    TP1 dal lato sbagliato, vissute in media sei secondi** -- aperte e chiuse
    prima che si potessero vedere.

    Non e' un filtro soppesabile. In esercizio GEST-01 le ferma prima, perche'
    il rapporto vale None e CTX blocca; col modo diagnostico GEST-01 e' spento
    e il livello incoerente arriva al broker. Ma un parziale alle spalle del
    prezzo non e' un'operazione sfortunata: e' un parziale che non esiste. Si
    toglie, e la posizione vive sul suo stop e sul bersaglio finale -- che e'
    esattamente cio' che GEST-04 prevede quando TP1 non c'e'.

    `verso_ordine` e' il verso sul CFD e mai `crt.direzione`. `obiettivo_1` e
    `prezzo_ingresso` sono prezzi del CFD, mentre il CRT e' letto sul future:
    su `6S` e `6J`, che quotano il reciproco, i due sono opposti. Col verso
    sbagliato questa guardia sopprimeva i TP1 BUONI e teneva quelli alle
    spalle -- cioe' faceva l'opposto del suo scopo. Visto in esercizio il
    2026-09-22: "USDCHF: TP1 0.82018 gia' superato dal prezzo 0.82059" su uno
    SHORT, dove 0,82018 sta sotto il prezzo e il parziale era dalla parte
    giusta.
    """
    if obiettivo_1 is None:
        return False
    if verso_ordine is Bias.LONG:
        return obiettivo_1 <= prezzo_ingresso
    return obiettivo_1 >= prezzo_ingresso


@dataclass(frozen=True)
class ContestoIndipendente:
    """Cosa dice il contesto, a prescindere dal CRT."""

    blocchi: list[str]
    limiti: tuple
    evento_news: Any
    posizioni_qui: int


def blocchi_indipendenti(foto: "Fotografia", tf_trigger: TF) -> ContestoIndipendente:
    """I divieti che non dipendono dal CRT: contesto e rischio.

    Vanno valutati anche quando il CRT non c'e', altrimenti la statistica
    "quante volte ciascun filtro ha impedito un'operazione" vedrebbe sempre e
    solo il primo blocco, e non direbbe se un filtro non scatta mai.

    Sono sei, e li usano ENTRAMBE le strade -- l'ordine diretto e l'ingresso
    armato di CRT-13. Prima erano due elenchi scritti a mano in due punti, e
    NON coincidevano: alla strada armata mancavano `PRIN-13` (domenica) e
    `CTX-04` (festivita'). Un setup armato poteva quindi scattare di domenica
    o in un giorno di festivita', mentre lo stesso setto per via diretta no --
    e il commento di quella strada dice l'opposto, che "un setup armato non e'
    un lasciapassare" perche' PREC-01 mette il rischio sopra il setup.

    Due copie della stessa regola divergono sempre, e divergono nel punto che
    muove i soldi. Qui ce n'e' una sola.
    """
    evento_news = ctx.dentro_finestra_news(
        foto.istante, foto.strumento, foto.eventi_news)
    posizioni_qui = foto.posizioni_aperte_per_strumento.get(foto.strumento, 0)
    limiti = risk.limiti_raggiunti(
        foto.pnl_giornaliero, foto.equity_inizio_giornata,
        foto.pnl_settimanale, foto.equity_inizio_settimana,
        foto.pnl_mensile, foto.equity_inizio_mese,
        equity_corrente=foto.equity,
    )

    blocchi: list[str] = []
    if not ctx.operativita_domenicale_ammessa(foto.istante, tf_trigger):
        blocchi.append("PRIN-13")             # domenica solo da TF_1W in su
    if evento_news is not None:
        blocchi.append("CTX-02")
    if ctx.giorno_di_festivita(foto.istante.date()) is not None:
        blocchi.append("CTX-04")
    if posizioni_qui >= MAX_POSIZIONI_PER_STRUMENTO:
        blocchi.append("RISK-06")
    if not foto.dati_coerenti:
        blocchi.append("PRIN-99")
    blocchi.extend(l.regola for l in limiti)                  # PREC-01
    return ContestoIndipendente(blocchi, tuple(limiti), evento_news, posizioni_qui)


def filtro_dxy(foto: "Fotografia", crt) -> Optional[str]:
    """SETUP-19 + RISK-05 — la bias del dollaro abilita questa operazione?

    `None` se passa, altrimenti il motivo per cui non passa. La REGOLA sta
    qui; l'inoltro al giudizio e l'eventuale astensione restano a chi chiama,
    perche' dipendono dal timeframe e dal modo diagnostico, non dalla bias.

    `SETUP-19` e' scritta in direzioni **CFD** mentre il CRT e' rilevato sul
    future: le due si confrontano solo dopo DEF-33, ed e' il motivo per cui
    qui si usa `_verso_sul_cfd` e mai `crt.direzione`.

    Due casi che sembrano guasti e non lo sono:

    - `XAUUSD` non deriva dal DXY (PRIN-09): `direzione_da_dxy` torna None e
      `strumento_eleggibile` lascia passare il setup proprio (PA-05);
    - con bias DXY `NESSUNA`, SETUP-19 dice "nessuna operazione su alcuna
      coppia", quindi si blocca -- ed e' voluto.
    """
    verso_del_setup = _verso_sul_cfd(foto, crt.direzione)                # passo 2
    verso_dal_dxy = stp.direzione_da_dxy(foto.bias_dxy, foto.strumento)  # passo 1
    if risk.strumento_eleggibile(                                        # passo 3
        strumento=foto.strumento,
        direzione_dal_dxy=verso_dal_dxy.value if verso_dal_dxy else None,
        ha_setup_proprio=True,
        direzione_del_setup=verso_del_setup.value,
    ):
        return None
    if verso_dal_dxy is None:
        return (f"bias DXY {foto.bias_dxy.value}: SETUP-19 non abilita alcuna "
                f"operazione su {foto.strumento}")
    return (f"bias DXY {foto.bias_dxy.value} vuole {verso_dal_dxy.value} su "
            f"{foto.strumento}, il CRT porta a {verso_del_setup.value}")


def calcola_livelli(
    foto: "Fotografia", crt
) -> tuple[Optional[Livelli], Optional[str]]:
    """GEST-02, GEST-07, SETUP-14, DEF-33, ESCL-12 — stop, TP1 e bersaglio.

    Restituisce `(livelli, None)` oppure `(None, motivo)` quando i livelli non
    si sanno leggere: in quel caso ci si astiene, perche' PRIN-99 vieta di
    mandare un ordine con numeri di cui non si risponde.

    I tre livelli nascono come prezzi del FUTURE -- estremi di N2, 50% di N1,
    key level -- e da qui in poi servono a tre cose che vivono tutte sul CFD:
    il rapporto di GEST-01 contro il prezzo di ingresso, i livelli che partono
    al broker, e il confronto della sentinella col prezzo corrente. Lasciarli
    sulla scala del future e' il confronto che ESCL-12 vieta, e su `6J` e `6S`
    produce numeri di due ordini di grandezza diversi.

    `bersaglio_future` esce non convertito perche' `_rapporto_giud01` lo vuole
    sulla scala su cui l'ATR e' misurato. La size, allo stesso modo, resta
    calcolata sui livelli future: li' la distanza e' gia' adimensionale e
    convertirla sarebbe un giro a vuoto con un arrotondamento in piu'.
    """
    # Un ingresso e' "da gap" solo se due cose sono vere insieme (REV-47):
    #
    #   1. la zona e' una zona di REAZIONE, non il gap target. DEF-15bis
    #      assegna al gap piu' alto il ruolo di bersaglio e vieta di usarlo
    #      con un ruolo diverso;
    #   2. il prezzo vi sta INTERAGENDO. E' la prima riga di SETUP-09 ("si
    #      applica quando il prezzo interagisce con una zona_gap") ed e'
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

    # Il prezzo di ingresso e' l'apertura di N3, che non esiste ancora: si usa
    # il prezzo corrente, che e' cio' che CTX-05 chiede di fare ("sui prezzi
    # effettivi al momento dell'ordine, non su quelli teorici").
    prezzo_ingresso = foto.prezzo_cfd

    ancora = crt.n2.chiusura
    try:
        stop = _sulla_scala_del_cfd(foto, stop_future, ancora)
        obiettivo_1 = _sulla_scala_del_cfd(foto, tp1_future, ancora)
        bersaglio = (
            None if bersaglio_future is None
            else _sulla_scala_del_cfd(foto, bersaglio_future, ancora)
        )
    except ValueError as errore:
        return None, f"livelli non convertibili sulla scala del CFD: {errore}"

    return Livelli(
        da_gap=da_gap,
        prezzo_ingresso=prezzo_ingresso,
        stop=stop,
        obiettivo_1=obiettivo_1,
        bersaglio=bersaglio,
        stop_future=stop_future,
        bersaglio_future=bersaglio_future,
        rapporto=ctx.rapporto_rischio_rendimento(prezzo_ingresso, stop, obiettivo_1),
    ), None


def guardie_sui_livelli(
    bersaglio: Optional[float],
    stop: float,
    prezzo_ingresso: float,
    verso_ordine: Bias,
    tf_crt: TF,
) -> Optional[tuple[list[str], str]]:
    """I quattro controlli sui livelli, prima che l'ordine parta.

    Restituisce `(regole_che_bloccano, motivo)` quando si deve rinunciare, e
    `None` quando i livelli reggono.

    E' un agente PURO: non conosce la `Fotografia`, non costruisce decisioni,
    non legge l'archivio. Prende quattro numeri e un verso, e risponde. Per
    questo si puo' provare da solo — cosa che, finche' queste righe stavano
    dentro le 686 di `valuta`, era impossibile: ed e' li' dentro che tutti e
    quattro i difetti qui sotto sono vissuti indisturbati.

    Il verso e' quello del CFD e mai quello del CRT: `6S` e `6J` quotano il
    reciproco, e un CRT LONG li' e' un ordine SHORT qui. Usare `crt.direzione`
    farebbe risultare sbagliati esattamente i livelli giusti su USDCHF e
    USDJPY — lo scambio che una volta ha gia' mandato gli ordini al contrario.

    I quattro, in ordine:

    1. **Un bersaglio deve esistere** (SETUP-14). Senza, il 75% residuo non ha
       dove andare.
    2. **Il bersaglio sta davanti al prezzo** (PRIN-99). Nasce da un key
       level, e col prezzo di ingresso non lo confrontava nessuno: il
       2026-09-22 un SELL su USDCHF a 0,81891 e' partito con target 0,82029,
       cioe' SOPRA. L'audit ne contava 48 su 201.
    3. **Lo stop sta dall'altra parte** (PRIN-99). Stesso difetto del punto 2,
       sull'altro livello, e nessuno gliel'aveva applicato. Il 2026-09-23:
       `USDJPY SELL ingresso 158.204 stop 158.196` — lo stop sotto l'ingresso
       su uno short, cioe' dalla parte del bersaglio: il prezzo lo tocca
       andando nella direzione GIUSTA. Vissuta 4 secondi.
    4. **Il gioco vale la candela** (SETUP-02C). Il documento non scrive una
       soglia ma descrive la costruzione: stop stretto perche' e' l'ombra
       dello sweep, bersaglio largo perche' e' il lato opposto di un range
       superiore, "rapporto misurato da 1,85 a 3,92 R". Sotto 1 quella
       costruzione non regge piu'. Il 2026-09-23 `AUDUSD BUY 0.70412 stop
       0.70257 target 0.70475`: 155 pip rischiati per farne 63, perdente
       anche vincendo sei volte su dieci.
    """
    lungo = verso_ordine is Bias.LONG
    nome_ordine = "BUY" if lungo else "SELL"

    if bersaglio is None:
        return (["PRIN-99"],
                f"SETUP-14: nessun key level su {tf_crt.value} o superiore a "
                "cui portare il 75% residuo")

    if (bersaglio <= prezzo_ingresso) if lungo else (bersaglio >= prezzo_ingresso):
        return (["PRIN-99"],
                f"bersaglio {bersaglio:.5f} dalla parte sbagliata rispetto "
                f"all'ingresso {prezzo_ingresso:.5f} per un ordine "
                f"{nome_ordine}: l'operazione non potrebbe vincere")

    if (stop >= prezzo_ingresso) if lungo else (stop <= prezzo_ingresso):
        return (["PRIN-99"],
                f"stop {stop:.5f} dalla parte sbagliata rispetto all'ingresso "
                f"{prezzo_ingresso:.5f} per un ordine {nome_ordine}: sarebbe "
                "gia' toccato, l'operazione morirebbe appena aperta")

    rischio_prezzo = abs(prezzo_ingresso - stop)
    if rischio_prezzo > 0:
        rapporto_vero = abs(bersaglio - prezzo_ingresso) / rischio_prezzo
        if rapporto_vero < RAPPORTO_MINIMO:
            return (["SETUP-02C"],
                    f"rapporto {rapporto_vero:.2f} a 1: si rischierebbe piu' "
                    f"di quanto si puo' guadagnare (minimo {RAPPORTO_MINIMO:g}). "
                    "Lo stop dell'ombra dello sweep non e' cosi' largo: "
                    "l'ingresso e' lontano dal CRT o il bersaglio e' gia' "
                    "quasi preso")

    return None


def _lettura_del_crt(crt, tf_esecuzione: Optional[TF]) -> dict[str, Any]:
    """I numeri del disegno riconosciuto, per chi legge il messaggio.

    Non serve a decidere: serve a poter RIFARE la lettura sul grafico. Finche'
    il messaggio diceva solo "aperto, stop qui, target la'", l'unica cosa che
    chi guarda poteva fare era crederci — e per capire dove il bot sbaglia
    bisogna invece poterlo smentire.

    `n1` e' la candela di riferimento, cioe' il range (SETUP-02A). `n2` e' la
    fase di manipolazione impacchettata: il suo estremo e' il punto piu'
    lontano raggiunto oltre il range, la sua chiusura e' il rientro.
    """
    corta = crt.direzione is Bias.SHORT
    return {
        "tf_range": getattr(crt.tf, "value", crt.tf),
        "tf_esecuzione": getattr(tf_esecuzione, "value", tf_esecuzione),
        "verso": "SHORT" if corta else "LONG",
        # Il bordo del range che e' stato violato.
        "livello_range": crt.n1.massimo if corta else crt.n1.minimo,
        # Fin dove si e' spinto oltre quel bordo, e dove e' rientrato.
        "estremo_superato": crt.n2.massimo if corta else crt.n2.minimo,
        "rientro": crt.n2.chiusura,
        "key_level": getattr(crt.key_level, "valore", None),
        "tipo_key_level": getattr(
            getattr(crt.key_level, "tipo", None), "value", None),
        "tf_key_level": getattr(
            getattr(crt.key_level, "tf", None), "value", None),
    }


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


def _costo_del_giro(spread: float, costo_commissione: float) -> float:
    """Quanto costa aprire e chiudere, espresso in DISTANZA DI PREZZO.

    Due voci, e su conti diversi pesano in modo opposto:

    - lo **spread**, che si paga passando da bid ad ask;
    - la **commissione**, che su un conto RAW e' quasi tutto il costo e non
      compare nello spread. Li' `bid == ask` e' normale, e leggere uno spread
      a zero come "gratis" e' l'errore che questa funzione esiste per evitare.

    `costo_commissione` arriva gia' in distanza di prezzo: e' la commissione
    per lotto divisa per `valore_punto`, cioe' di quanto deve muoversi il
    prezzo perche' un lotto la ripaghi. E' indipendente dalla size, che e' il
    motivo per cui si puo' confrontare con una distanza di stop.
    """
    return max(spread, 0.0) + max(costo_commissione, 0.0)


def _spread_troppo_caro(spread: float, prezzo: float, stop: float,
                        costo_commissione: float = 0.0) -> Optional[str]:
    """RISK-03 — lo stop sta dentro il costo? Se si', perche'.

    Uno stop piu' vicino di dieci volte il costo del giro non e' uno stop
    stretto: e' uno stop dentro cio' che l'operazione paga per esistere, e
    basta l'oscillazione normale a chiuderlo. Vedi `COSTO_SPREAD_MASSIMO_IN_R`.

    Il costo e' spread **piu' commissione**: guardare il solo spread su un
    conto RAW significa leggere zero e lasciar passare tutto.

    Sta in una funzione sola perche' i due ingressi -- quello armato di
    CRT-13 e quello diretto -- devono applicarla uguale. Quando stava scritta
    solo nel primo, il secondo apriva lo stesso: misurato il 2026-09-22 sulle
    53 posizioni dopo il riavvio, **36 avevano ancora lo stop dentro i dieci
    spread**, tutte passate dalla strada che il controllo non aveva.
    """
    costo_giro = _costo_del_giro(spread, costo_commissione)
    if costo_giro <= 0:
        return None                      # niente da misurare
    rischio = abs(prezzo - stop)
    if rischio <= 0:
        return None                      # RISK-03 lo ferma altrove, come PRIN-99
    costo = costo_giro / rischio
    if costo <= COSTO_SPREAD_MASSIMO_IN_R:
        return None
    return (f"il giro costerebbe {costo:.2f} R: lo stop dista "
            f"{rischio / costo_giro:.1f} volte il costo, il minimo e' "
            f"{1 / COSTO_SPREAD_MASSIMO_IN_R:.0f}")


def _livelli_dell_ingresso_armato(
    foto: "Fotografia", ingresso
) -> tuple[Optional[tuple[float, float, float]], Optional[str]]:
    """I tre livelli di un ingresso armato, sulla scala del CFD (REV-52).

    Nascono sul FUTURE e devono passare di scala come per l'ingresso
    ordinario. Restituisce `((stop, bersaglio, finale), None)` oppure
    `(None, motivo)`: PRIN-99 vieta di mandare un ordine con livelli che non
    si sanno leggere.
    """
    ancora = ingresso.prezzo
    try:
        return (
            (_sulla_scala_del_cfd(foto, ingresso.stop, ancora),
             _sulla_scala_del_cfd(foto, ingresso.bersaglio_1, ancora),
             _sulla_scala_del_cfd(foto, ingresso.bersaglio_2, ancora)),
            None,
        )
    except ValueError as errore:
        return None, f"livelli non convertibili: {errore}"


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
    troppo_caro = _spread_troppo_caro(foto.spread, ingresso.prezzo, ingresso.stop,
                                       foto.costo_commissione)
    if troppo_caro:
        return _non_operare(
            foto.strumento, ["RISK-03"], troppo_caro,
            applicate, direzione=ingresso.direzione, tf_crt=tf_trigger,
            livello_stop=ingresso.stop, tp1=ingresso.bersaglio_1,
        )

    # --- I controlli di rischio, rifatti adesso ---------------------------
    #
    # PREC-01: il rischio batte il setup, e un setup armato non e' un
    # lasciapassare. Fra l'armamento e adesso possono essere passate ore --
    # un limite di perdita puo' essere scattato, una finestra news puo'
    # essersi aperta, il tetto di posizioni puo' essersi riempito.
    #
    # Stessa funzione della strada diretta: quando erano due elenchi separati,
    # a questo mancavano PRIN-13 e CTX-04.
    blocchi = blocchi_indipendenti(foto, tf_trigger).blocchi
    if blocchi:
        return _non_operare(
            foto.strumento, blocchi,
            "ingresso trovato ma il rischio non lo consente (PREC-01)",
            applicate, direzione=ingresso.direzione, tf_crt=tf_trigger,
        )

    # I livelli nascono sul FUTURE e devono passare sulla scala del CFD
    # (REV-52), come per l'ingresso ordinario -- a meno che non ci siano gia'.
    tre, errore = _livelli_dell_ingresso_armato(foto, ingresso)
    if tre is None:
        return _non_operare(
            foto.strumento, ["PRIN-99", "ESCL-12"], errore or "", applicate,
            direzione=ingresso.direzione, tf_crt=tf_trigger)
    stop, bersaglio, finale = tre

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

    # Solo ADESSO il setup si puo' chiudere: l'ordine ha superato tutte le
    # regole di rischio e sta per partire. `valuta_armati` lo lasciava aperto
    # apposta -- chiuderlo prima bruciava l'occasione anche quando una regola
    # fermava l'ordine, e al setup restavano barre a disposizione.
    ingresso_ltf.conferma_esecuzione(
        ingresso.id_setup, "CRT-13: ingresso sul ritorno nell'FVG dopo il CISD")

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
        # Qui il CRT non e' piu' in mano: `Ingresso` porta i livelli calcolati,
        # non le candele da cui nascono. Si dice quello che si sa davvero --
        # la coppia di timeframe e il verso -- e non si inventa il resto.
        lettura_crt={
            "tf_range": ingresso.tf_crt,
            "tf_esecuzione": getattr(tf_trigger, "value", tf_trigger),
            "verso": "SHORT" if ingresso.direzione is Bias.SHORT else "LONG",
            "via": "ritorno nell'FVG dopo il cambio di carattere",
        },
    )


def valuta(foto: Fotografia, tf_trigger: TF) -> Decisione:
    """Valuta un possibile ingresso su `tf_trigger` e restituisce la decisione.

    L'ordine dei controlli segue le precedenze dichiarate. I filtri di
    contesto e le esclusioni di setup si applicano **uniti** (REV-17), perche'
    i due elenchi non coincidono e nessuno dei due e' normativo da solo.
    """
    applicate: list[str] = []

    # --- 0-3. I cancelli che precedono il CRT (ESCL-05, PA-55, SETUP-06) --
    prima = preludio(foto, tf_trigger)
    if prima.astensione is not None:
        return prima.astensione
    contesto, comando, tf_comando = prima.contesto, prima.comando, prima.tf_comando
    indipendenti = contesto.blocchi
    applicate.append("SETUP-06")

    # --- 4. Il CRT (SETUP-00, SETUP-02, CRT-04) ---------------------------
    # La ricerca vive in `trova_crt`, che sa anche perche' un CRT non c'e'.
    ricerca = trova_crt(foto, tf_trigger)
    # `SETUP-00` si dichiara solo se la ricerca ci e' arrivata: con `CRT-04`
    # o `DEF-26` ci si ferma prima, e dichiararla direbbe che e' stata
    # valutata quando non lo e' stata. La statistica "quante volte ciascuna
    # regola ha deciso" si regge su questa distinzione.
    if ricerca.regola in (None, "SETUP-00"):
        applicate.append("SETUP-00")
    if ricerca.crt is None:
        return _non_operare(
            foto.strumento, [ricerca.regola] + indipendenti,
            ricerca.motivo or "", applicate,
        )
    crt = ricerca.crt
    basse = list(ricerca.barre)
    applicate.append("SETUP-02A" if crt.direzione is Bias.SHORT else "SETUP-02B")

    # --- 4ter. Le otto conferme di Romeo (CRT-06/10/11/12/15/17/18/20) ----
    #
    # Si valutano sul timeframe di ESECUZIONE, che dopo la riscrittura secondo
    # SETUP-02 e' `tf_trigger` stesso: il Power of Three si svolge dentro la
    # candela di riferimento successiva, e li' si legge -- sul timeframe del
    # range non c'e' ancora nulla da vedere.
    #
    # Erano legate a `tf_ingresso`, che e' un gradino PIU' SOTTO. Per `M5` e
    # `M1min` -- che non sono chiavi di `COPPIE_CRT`, perche' le chiavi sono i
    # range -- quella lettura dava `None`, e il blocco veniva saltato: **le
    # otto conferme non venivano valutate proprio sulle coppie su cui il bot
    # opera**, in silenzio, senza un errore. Si e' visto il 2026-09-23 solo
    # dopo aver iniziato a salvare il responso in archivio: zero decisioni con
    # le conferme registrate.
    #
    # `tf_ingresso` resta quello che era e serve ad altro: l'ARMAMENTO di
    # CRT-13, che aspetta il ritorno nell'FVG sul timeframe sotto.
    # `tf_ingresso` serve all'ARMAMENTO di CRT-13, che aspetta il ritorno
    # nell'FVG un gradino SOTTO l'esecuzione. Le conferme no: quelle si
    # leggono sull'esecuzione stessa. Legarle a questa variabile e' il guasto
    # del 2026-09-23, per cui su M5 e M1min non venivano valutate affatto.
    tf_ingresso = COPPIE_CRT.get(tf_trigger)

    # Lo stesso inoltro si ripete su piu' obiezioni: se il giudizio la fa
    # cadere, l'obiezione non ferma e GIUD-02 va DICHIARATA -- altrimenti la
    # decisione direbbe che e' passata senza dire chi l'ha lasciata passare.
    # `assoluta` e' l'obiezione che non si sottopone: il giudizio non la vede
    # nemmeno.
    def giudizio_salva(blocchi_qui, motivo_qui, assoluta: bool = False) -> bool:
        if assoluta:
            return False
        if _apri_ogni_crt() or _giudizio_lascia_cadere(
                foto, crt, tf_trigger, list(blocchi_qui), motivo_qui or ""):
            applicate.append("GIUD-02")
            return True
        return False

    applicate.extend(sorted(CONFERME_ROMEO))
    conferme = interroga_conferme(foto, crt, basse, _apri_ogni_crt())
    responso_romeo = conferme.responso
    if conferme.blocchi:
        blocchi_qui = list(conferme.blocchi) + indipendenti
        if not giudizio_salva(blocchi_qui, conferme.motivo):
            fermata = _non_operare(
                foto.strumento, blocchi_qui, conferme.motivo or "",
                applicate, direzione=crt.direzione, tf_crt=crt.tf)
            return replace(fermata, responso_romeo=responso_romeo)

    # --- 4. Livelli: stop, TP1, target (GEST-02, GEST-07, SETUP-14) -------
    #
    # La regola vive in `calcola_livelli`, che e' un agente suo e si prova da
    # solo. Qui restano la consegna e l'astensione.
    livelli, errore_livelli = calcola_livelli(foto, crt)
    if livelli is None:
        # Prezzo CFD assente o livello incoerente: PRIN-99, ci si astiene. Non
        # si manda un ordine con livelli che non si sanno leggere.
        return _non_operare(
            foto.strumento, ["PRIN-99", "ESCL-12"], errore_livelli or "",
            applicate, direzione=crt.direzione, tf_crt=crt.tf)
    applicate.extend(["GEST-02", "GEST-07", "SETUP-14"])
    # `obiettivo_1` e' l'unico che resta una variabile a se': viene
    # RIASSEGNATO a None quando il parziale sta alle spalle del prezzo. Gli
    # altri si leggono da `livelli`, cosi' non esistono due copie dello stesso
    # numero che possono divergere.
    obiettivo_1 = livelli.obiettivo_1


    # Da qui in poi ogni astensione dichiara gli stessi cinque campi: verso,
    # timeframe del CRT, stop, parziale e rapporto. Ripeterli a ogni uscita
    # era un invito a dimenticarne uno -- e un'astensione che non dice lo stop
    # e' un'astensione che il diario non puo' spiegare.
    def ferma(regole, motivo: str) -> Decisione:
        return _non_operare(
            foto.strumento, list(regole), motivo, applicate,
            direzione=crt.direzione, tf_crt=crt.tf, livello_stop=livelli.stop,
            tp1=obiettivo_1, rapporto_su_tp1=livelli.rapporto,
        )

    # --- 4bis-ter. Un parziale dietro le spalle non e' un parziale -------
    #
    # La regola vive in `tp1_alle_spalle`. Il `rapporto is None` resta qui
    # perche' e' la condizione in cui GEST-01 non ha gia' fermato tutto:
    # l'altra meta' di CRT-13 questo controllo ce l'ha gia', in
    # `ingresso_ltf.controlla`, dove il bersaglio superato scala al lato
    # opposto (CRT-16).
    if livelli.rapporto is None and tp1_alle_spalle(
            obiettivo_1, livelli.prezzo_ingresso, _verso_sul_cfd(foto, crt.direzione)):
        log.info("%s: TP1 %.5f gia' superato dal prezzo %.5f, nessun "
                 "parziale (GEST-04 non si applica)",
                 foto.strumento, obiettivo_1, livelli.prezzo_ingresso)
        obiettivo_1 = None

    # --- 4quater. Lo stop deve stare FUORI dal costo (RISK-03) -----------
    #
    # La stessa regola dell'ingresso armato, sulla strada diretta. Quando
    # stava scritta solo la', questa apriva lo stesso: e' da qui che passano
    # gli ordini senza CRT-13, cioe' la maggioranza.
    troppo_caro = _spread_troppo_caro(foto.spread, livelli.prezzo_ingresso, livelli.stop,
                                       foto.costo_commissione)
    if troppo_caro:
        return ferma(["RISK-03"], troppo_caro)

    # Il candidato e' pronto: CRT riconosciuto, conferme interrogate, livelli
    # calcolati e passati dalle guardie che non dipendono dal contesto. Da qui
    # in poi si decide SE e QUANTO operarci, ed e' un discorso diverso --
    # abbastanza da stare in una funzione sua.
    return _decidi_sul_candidato(
        foto, crt, tf_trigger, tf_ingresso, contesto, comando, tf_comando,
        livelli, obiettivo_1, responso_romeo, indipendenti, applicate,
        ferma, giudizio_salva,
    )


def _decidi_sul_candidato(
    foto: Fotografia, crt, tf_trigger: TF, tf_ingresso, contesto, comando,
    tf_comando, livelli, obiettivo_1, responso_romeo: dict,
    indipendenti: list, applicate: list, ferma, giudizio_salva,
) -> Decisione:
    """La seconda meta' di `valuta`: si opera, e con quanto?

    Riceve un candidato gia' costruito -- CRT riconosciuto, conferme
    interrogate, livelli calcolati e passati dalle guardie che non dipendono
    dal contesto -- e decide se mandarlo al broker, armarlo per dopo, o
    lasciarlo cadere.

    `ferma` e `giudizio_salva` arrivano da chi chiama: sono i due modi di
    dichiarare un'astensione, e duplicarli qui vorrebbe dire due formulazioni
    della stessa uscita.
    """
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
    # La regola vive in `filtro_dxy`. Qui resta solo cosa farne, che dipende
    # dal timeframe e dal modo diagnostico e non dalla bias del dollaro.
    verso_del_setup = _verso_sul_cfd(foto, crt.direzione)
    motivo = filtro_dxy(foto, crt)
    if motivo is not None:
        blocchi_dxy = ["RISK-05"] + indipendenti
        # Su un range alto la bias del dollaro e' il contesto che domina
        # l'operazione e ferma da sola; su uno scalp e' rumore, e la parola
        # passa al giudizio. Vedi `RISK_05_BLOCCA_DA_SOLA` in core/parametri.
        assoluta = (crt.tf.value in RISK_05_BLOCCA_DA_SOLA
                    and not _apri_ogni_crt())
        if not giudizio_salva(blocchi_dxy, motivo, assoluta):
            return _non_operare(
                foto.strumento, blocchi_dxy, motivo, applicate,
                direzione=crt.direzione, tf_crt=crt.tf)

    # --- 5. Filtri uniti: CTX-01 + SETUP-15 + SETUP-09 (REV-17, PREC-04) --
    # La regola vive in `filtri_e_esclusioni`: l'unione dei tre elenchi, dove
    # nessuno dei tre e' normativo da solo.
    blocchi, motivo_filtri = filtri_e_esclusioni(
        foto, crt, tf_trigger, comando, contesto, livelli.rapporto, livelli.da_gap,
        _apri_ogni_crt())

    # Qui NON si passa da `giudizio_salva`: quell'aiutante fa cadere
    # l'obiezione anche col solo modo diagnostico, e a questo punto i blocchi
    # comprendono i MURI che `filtri_e_esclusioni` tiene apposta (ESCL-02,
    # RISK-06, i limiti di perdita). Il modo diagnostico ha gia' tolto li'
    # dentro cio' che era soppesabile; quello che resta lo puo' far cadere
    # solo il giudizio.
    if blocchi and _giudizio_lascia_cadere(
            foto, crt, tf_trigger, blocchi, motivo_filtri):
        applicate.append("GIUD-02")
        blocchi = []

    if blocchi:
        return ferma(blocchi, motivo_filtri)

    # --- 6. Size (RISK-01, RISK-02, RISK-03, DEF-47) ----------------------
    esito_size = chiedi_la_size(foto, crt, livelli)
    applicate.extend(["RISK-01", "RISK-02", "RISK-03", "DEF-47"])
    if esito_size.lotti is None:
        return ferma(["RISK-03"], esito_size.motivo)

    # --- 7. Ultima riga di difesa: i divieti permanenti (PREC-05) ---------
    divieti = divieti_permanenti(
        foto, crt, comando, tf_comando, livelli.stop, livelli.prezzo_ingresso,
        contesto.posizioni_qui, _apri_ogni_crt(),
    )
    if divieti:
        return ferma([d.regola for d in divieti],
                     "; ".join(f"{d.regola}: {d.motivo}" for d in divieti))
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
    if arma_il_setup(foto, crt, tf_ingresso):
        applicate.append("CRT-13")
        # CRT-13 e' la regola che impedisce l'ordine IMMEDIATO, e va
        # dichiarata: una decisione NONE senza regola che la imponga sarebbe
        # un'astensione muta.
        armata = _non_operare(
            foto.strumento, ["CRT-13"],
            "CRT-13: setup armato, attendo il ritorno nell'FVG sul "
            f"{tf_ingresso.value}",
            applicate,
            direzione=crt.direzione, tf_crt=crt.tf,
            livello_stop=livelli.stop, tp1=obiettivo_1,
            rapporto_su_tp1=livelli.rapporto,
        )
        return replace(armata, responso_romeo=responso_romeo)

    # --- 7bis. I quattro controlli sui livelli (SETUP-14, PRIN-99, SETUP-02C)
    #
    # Stanno DOPO i divieti e non prima: PREC-05 vuole le esclusioni come
    # ultimo controllo, e un'astensione che le scavalcasse nasconderebbe il
    # motivo vero per cui quell'ordine non andava mandato.
    #
    # La regola vive in `guardie_sui_livelli`, che e' un agente puro e si
    # prova da solo. Qui restano solo il verso e la consegna.
    verso_ordine = _verso_sul_cfd(foto, crt.direzione)
    guasto = guardie_sui_livelli(
        livelli.bersaglio, livelli.stop, livelli.prezzo_ingresso, verso_ordine, crt.tf)
    if guasto is not None:
        blocchi_livelli, motivo_livelli = guasto
        return ferma(blocchi_livelli, motivo_livelli)

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
    rapporto_kl_gap = _rapporto_giud01(foto, crt, livelli.bersaglio_future)
    applicate.append("GIUD-01")

    # --- 8. Ordine ---------------------------------------------------------
    applicate.extend(["SETUP-03", "SETUP-04", "DEF-33"])
    return componi_ordine(
        foto, crt, tf_trigger, verso_del_setup, livelli, obiettivo_1,
        esito_size, applicate, responso_romeo, rapporto_kl_gap,
    )
