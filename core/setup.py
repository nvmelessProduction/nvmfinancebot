"""Le condizioni di ingresso di `docs/03_setup.md`, come funzioni pure.

Il CRT e' lo strumento di ingresso. Non e' mai il motivo dell'ingresso: il
motivo lo danno la bias di comando, il key level preso e il gap
(`00_principi.md` §1). Questo modulo tiene le due cose separate, e ogni
funzione che nega un ingresso dice **quale regola** lo ha negato.

**Regole di 03_setup.md che non stanno qui, e dove stanno.**

| Regola | Dove vive | Perche' |
|---|---|---|
| SETUP-12 | `gestione.py` | Stop loss: e' gestione, e duplica GEST-02 |
| SETUP-13 | `gestione.py` | TP1 e parziale: duplica GEST-07 |
| SETUP-14 | `gestione.py` | Estensione del target: duplica GEST-08 |
| SETUP-18 | nessun codice | "Sono ammesse posizioni opposte su strumenti diversi": e' un permesso, non un vincolo. Ogni strumento e' gia' valutato per conto suo |

Scriverle in due posti significherebbe farle divergere.

**L'elenco di SETUP-15 non e' completo da solo.** Per REV-17 le esclusioni sono
l'**unione** di SETUP-15 e CTX-01, che non coincidono. Qui c'e' solo la parte
di SETUP-15: `contesto.py` aggiunge la sua, e `motore.py` le somma. Nessuno dei
due elenchi e' normativo da solo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Mapping, Optional, Sequence

from core.definizioni import (
    Bias, Candela, Gap, KeyLevel, Mitigazione, TipoKeyLevel, cisd,
    divergenza_smt, double_purge, meta_ombra, meta_tenuta, peso_ombre,
    verso_del_double_purge,
)
from core.parametri import (
    PESO_OMBRE_MINIMO,
    conferma_attiva,
    DIREZIONE_DA_BIAS_DXY,
    MAX_POSIZIONI_PER_STRUMENTO,
    TF,
    TF_SOLO_GAP,
    UNIVERSO,
    gerarchia,
)

# ===========================================================================
# Tipi
# ===========================================================================


@dataclass(frozen=True)
class Crt:
    """Un CRT formato (SETUP-01, SETUP-02).

    `N1` costruisce il range, `N2` manipola prendendo liquidita' oltre un
    estremo, `N3` distribuisce. Il CRT e' FORMATO **alla chiusura di N2**:
    `N3` non esiste ancora, ed e' la candela sulla cui apertura si entrera'
    (SETUP-03).

    `key_level` e' quello preso da `N2`, e appartiene sempre a un timeframe
    strettamente superiore a `tf` (SETUP-02, DEF-30).
    """

    direzione: Bias
    tf: TF
    n1: Candela
    n2: Candela
    key_level: KeyLevel


@dataclass(frozen=True)
class EsitoSetup:
    """Il risultato della valutazione di un setup, sempre tracciabile.

    `regole_applicate` elenca gli ID che hanno concorso alla decisione,
    `regole_che_bloccano` quelli che l'hanno impedita. Quando il bot non opera
    deve poter dire quale regola gliel'ha vietato, non "non c'erano le
    condizioni".
    """

    ammesso: bool
    crt: Optional[Crt]
    regole_applicate: tuple[str, ...]
    regole_che_bloccano: tuple[str, ...]


class CategoriaGiudizio:
    """Le tre risposte chiuse di GIUD-01. Mai giudizio libero."""

    GAP = "A"
    KEY_LEVEL = "B"
    AMBIGUO = "C"


# ===========================================================================
# 1. Timeframe ammessi per il CRT
# ===========================================================================


def _piu_alto(a: TF, b: TF) -> bool:
    """True se `a` sta piu' in alto di `b` nella gerarchia di DEF-01."""
    ordine = gerarchia()
    return ordine.index(a) < ordine.index(b)


def timeframe_crt_ammesso(
    tf_crt: TF,
    tf_key_level: TF,
    tf_gap: Optional[TF] = None,
) -> bool:
    """DEF-30, SETUP-02, SETUP-10 — Il CRT puo' formarsi su questo timeframe?

    Due vincoli distinti, che SETUP-10 avverte di non confondere:

    - rispetto al **key level** il CRT deve stare su un timeframe
      strettamente inferiore;
    - rispetto al **gap**, se c'e', puo' stare sullo stesso timeframe o piu'
      in basso.

    `TF_H12` e `TF_H6` non ospitano mai un CRT: DEF-31 li riserva ai gap e
    SETUP-05 non definisce per essi alcuna condizione di allineamento, quindi
    un CRT formato li' non potrebbe mai superare SETUP-15 (REV-11).
    """
    if tf_crt in TF_SOLO_GAP:
        return False
    if not _piu_alto(tf_key_level, tf_crt):
        return False
    if tf_gap is not None and _piu_alto(tf_crt, tf_gap):
        return False
    return True


# ===========================================================================
# 2. Il CRT
# ===========================================================================


def _manipolazione_e_rientro(
    c_rif: Candela,
    barre: Sequence[Candela],
    verso: Bias,
) -> Optional[tuple[float, Candela]]:
    """SETUP-02 — Cerca manipolazione e rientro DENTRO la candela successiva.

    Il documento e' esplicito su dove guardare:

        La candela di riferimento E' il range: CRT_high = high[C_rif].
        Il Power of Three si svolge DENTRO la candela di riferimento
        successiva. Li' si cercano, SUL TIMEFRAME DI ESECUZIONE, la
        manipolazione e il rientro.

        SE  una barra fa  high > CRT_high
        AND una barra successiva o la stessa chiude < CRT_high
        ALLORA il CRT short e' FORMATO a quella chiusura

    `barre` sono le candele del timeframe di ESECUZIONE che cadono dentro la
    candela di riferimento successiva, in ordine.

    Restituisce `(sweep, barra_del_rientro)`: lo sweep e' l'estremo piu'
    lontano raggiunto oltre il livello -- il documento lo chiama `sweep_high`
    -- ed e' li' che GEST-02 mette lo stop.

    `None` se la sequenza non si e' completata.
    """
    livello = c_rif.massimo if verso is Bias.SHORT else c_rif.minimo
    sweep: Optional[float] = None

    for barra in barre:
        superato = (barra.massimo > livello if verso is Bias.SHORT
                    else barra.minimo < livello)
        if superato:
            estremo = barra.massimo if verso is Bias.SHORT else barra.minimo
            if sweep is None:
                sweep = estremo
            else:
                sweep = max(sweep, estremo) if verso is Bias.SHORT else min(sweep, estremo)

        # "una barra successiva O LA STESSA": il rientro puo' avvenire sulla
        # barra che ha manipolato, e per questo il controllo sta qui sotto e
        # non in un secondo giro.
        if sweep is None:
            continue
        rientrato = (barra.chiusura < livello if verso is Bias.SHORT
                     else barra.chiusura > livello)
        if rientrato:
            return sweep, barra
    return None


def _n2_sintetica(sweep: float, rientro: Candela, verso: Bias) -> Candela:
    """La fase di manipolazione, come se fosse una candela sola.

    A valle il motore chiede a `N2` due cose: l'estremo spazzato, per lo stop
    di GEST-02, e la chiusura, che e' il prezzo a cui il CRT si e' formato.
    Confezionarle in una `Candela` evita di cambiare la firma di tutto cio'
    che sta piu' in basso -- `stop_aggressivo`, `peso_ombre`, il dossier --
    per un dato che quelle funzioni sanno gia' leggere.
    """
    if verso is Bias.SHORT:
        return Candela(rientro.orario, rientro.apertura, sweep,
                       min(rientro.minimo, rientro.chiusura), rientro.chiusura)
    return Candela(rientro.orario, rientro.apertura,
                   max(rientro.massimo, rientro.chiusura), sweep, rientro.chiusura)


def crt_short(
    c_rif: Candela,
    barre: Sequence[Candela],
    tf_crt: TF,
    key_level: KeyLevel,
) -> Optional[Crt]:
    """SETUP-02A — CRT short, formato alla chiusura del rientro.

    Due condizioni, quelle del documento e nessuna in piu':

        una barra fa high > CRT_high          (manipolazione)
        una barra successiva o la stessa chiude < CRT_high   (rientro)

    Il key level dev'essere un `KL_max` di timeframe strettamente superiore
    (SETUP-00, SETUP-02), e lo sweep deve averlo preso davvero (DEF-38).

    ## Cosa e' cambiato, e perche' contava

    Fino al 2026-09-23 questa funzione confrontava DUE CANDELE DEL TIMEFRAME
    DI RANGE e chiedeva quattro condizioni, una delle quali -- `close[N2] <
    close[N1]` -- non compare in nessun documento. Erano tre scostamenti che
    si moltiplicavano:

    1. **il timeframe sbagliato.** Il documento legge manipolazione e rientro
       sulle barre di ESECUZIONE dentro la candela successiva. Su `4h -> 15m`
       sono sedici occasioni dentro quattro ore; il codice ne concedeva una,
       e pretendeva che fosse l'intera candela da quattro ore a spazzare e
       richiudere.
    2. **il momento sbagliato.** Il CRT nasceva solo alla chiusura della
       candela di range, cioe' quando il movimento era gia' finito. Il
       documento lo forma alla chiusura della barra bassa che rientra --
       anche mezz'ora dentro le quattro ore. E' anche il motivo per cui
       "a volte si entra sulla seconda candela e non sulla terza".
    3. **una condizione in piu'**, che restringeva ancora.

    Misurato sul bot dal vivo: 51 CRT in 19 ore, zero ingressi.
    """
    if key_level.tipo is not TipoKeyLevel.MAX:
        return None
    if not timeframe_crt_ammesso(tf_crt, key_level.tf):
        return None
    esito = _manipolazione_e_rientro(c_rif, barre, Bias.SHORT)
    if esito is None:
        return None
    sweep, rientro = esito
    if sweep <= key_level.valore:          # presa del key level (DEF-38)
        return None
    return Crt(Bias.SHORT, tf_crt, c_rif, _n2_sintetica(sweep, rientro, Bias.SHORT), key_level)


def crt_long(
    c_rif: Candela,
    barre: Sequence[Candela],
    tf_crt: TF,
    key_level: KeyLevel,
) -> Optional[Crt]:
    """SETUP-02B — CRT long. Vale a specchio la nota di `crt_short`."""
    if key_level.tipo is not TipoKeyLevel.MIN:
        return None
    if not timeframe_crt_ammesso(tf_crt, key_level.tf):
        return None
    esito = _manipolazione_e_rientro(c_rif, barre, Bias.LONG)
    if esito is None:
        return None
    sweep, rientro = esito
    if sweep >= key_level.valore:
        return None
    return Crt(Bias.LONG, tf_crt, c_rif, _n2_sintetica(sweep, rientro, Bias.LONG), key_level)


def cerca_crt(
    c_rif: Candela,
    barre: Sequence[Candela],
    tf_crt: TF,
    key_level_presi: Sequence[KeyLevel],
) -> Optional[Crt]:
    """SETUP-00 e SETUP-02 — Cerca un CRT fra i key level presi.

    SETUP-00 e' il vincolo fondamentale: *"Il CRT esiste solo come reazione
    alla presa di un key level. In assenza di un key level preso, nessun CRT
    e' valido, qualunque sia la forma delle candele."* Con l'elenco vuoto qui
    non si cerca nemmeno.

    `c_rif` e' la candela di riferimento -- il RANGE, sul timeframe alto --
    e `barre` sono le candele del timeframe di ESECUZIONE che cadono dentro
    la candela di riferimento successiva.

    Se piu' key level producono un CRT si tiene quello del **timeframe piu'
    alto**: PREC-02, il timeframe piu' alto comanda.
    """
    if not barre:
        return None
    trovati: list[Crt] = []
    for livello in key_level_presi:
        for tentativo in (crt_short(c_rif, barre, tf_crt, livello),
                          crt_long(c_rif, barre, tf_crt, livello)):
            if tentativo is not None:
                trovati.append(tentativo)
    if not trovati:
        return None
    ordine = gerarchia()
    return min(trovati, key=lambda crt: ordine.index(crt.key_level.tf))


# ===========================================================================
# 3. Bias di comando
# ===========================================================================


def bias_comando(
    bias_per_tf: Mapping[TF, Bias],
    target_raggiunto_per_tf: Mapping[TF, bool],
) -> tuple[Bias, Optional[TF]]:
    """SETUP-06 — Bias di comando e timeframe che comanda.

    Si scorrono i timeframe nell'ordine esatto di SETUP-06 — che si ferma a
    `TF_1D` e non scende oltre — e ci si ferma al primo che ha una bias
    definita **e** un target non ancora raggiunto.

    Il "target associato" e' quello di DEF-46: il key level del timeframe
    immediatamente superiore, o per `TF_12M` il target globale di DEF-22
    (REV-07). Qui arriva gia' valutato: questa funzione non lo calcola.

    Restituisce (NESSUNA, None) se nessun timeframe soddisfa entrambe: chi
    chiama applica PRIN-99.
    """
    for tf in (TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1):
        bias = bias_per_tf.get(tf, Bias.NESSUNA)
        if bias is Bias.NESSUNA:
            continue
        if target_raggiunto_per_tf.get(tf, False):
            continue
        return bias, tf
    return Bias.NESSUNA, None


def reversal_ammesso(target_tf_comando_raggiunto: bool) -> bool:
    """SETUP-07, SETUP-08, ESCL-03 — Il reversal e' ammesso solo dopo il target.

    Finche' il target di `tf_comando` non e' raggiunto sono ammessi
    esclusivamente ingressi nella direzione di `bias_comando`, su nessun
    timeframe e nemmeno con un CRT formato correttamente.
    """
    return target_tf_comando_raggiunto


def direzione_concorde(direzione_crt: Bias, comando: Bias) -> bool:
    """SETUP-07 — Un segnale contrario a bias_comando non si esegue mai."""
    if comando is Bias.NESSUNA:
        return False
    return direzione_crt is comando


# ===========================================================================
# 4. Allineamento
# ===========================================================================


def allineamento_soddisfatto(
    tf_trigger: TF,
    sbilanciamenti: Mapping[TF, Bias],
    direzione: Bias,
) -> bool:
    """SETUP-05 — Regola dei due timeframe immediatamente superiori.

    Per operare su un timeframe, i **due** timeframe immediatamente superiori
    devono aver sbilanciato un key level nella stessa direzione.

    SETUP-05 contiene due blocchi diversi con lo stesso ID. Questo e' il
    secondo, quello introdotto da "Numero minimo", ed e' il cancello a cui si
    riferiscono SETUP-15 e CTX-01 #4 quando parlano di "meno di 2 timeframe
    allineati" (REV-22). Il primo blocco definisce il termine "allineati" per
    l'annotazione dei casi, e non e' una condizione di ingresso.

    `TF_H12` e `TF_H6` non compaiono nella tabella: non sono timeframe di
    allineamento, ed e' la ragione per cui un CRT non puo' nascere li'.

    ## La direzione confrontata e' quella dello SPAZZAMENTO (REV-46)

    Il documento scrive "nella direzione dell'operazione". Preso alla lettera
    e' **autocontraddittorio**, e si dimostra dalla meccanica del CRT:

    - `SETUP-02A` costruisce un CRT short sopra un `KL_max`, che `N2` supera
      verso l'ALTO. `DEF-38` chiama quella una presa a RIALZO, e
      `sbilanciamenti_per_timeframe` la registra come `LONG`.
    - Quindi il timeframe che ha generato il key level ha sempre sbilanciato
      nel verso OPPOSTO all'operazione.
    - `DUE_TF_SUPERIORI` garantisce che quel timeframe sia uno dei due che
      questa funzione interroga (`SETUP-00` vuole il key level da un
      timeframe strettamente superiore, e la tabella elenca proprio i due
      immediatamente sopra).

    Pretendere `sbilanciamento == direzione` chiede quindi che LONG sia
    uguale a SHORT: mai vero. Misurato sui prezzi reali, sei strumenti su
    ventisei anni, la condizione non si e' verificata **nemmeno una volta** su
    298 candidati che avevano superato tutto il resto.

    La lettura corretta e' l'unica che rende la regola applicabile, e
    corrisponde a come un CRT funziona: i due timeframe superiori devono aver
    spazzato **dalla stessa parte**, e l'operazione e' la reazione contraria a
    quello spazzamento. Il valore della regola — i due superiori devono essere
    d'accordo — resta intatto: cambia il verso, non il vincolo.

    I test precedenti non lo avevano visto perche' costruivano
    `sbilanciamenti` a mano, gia' concordi con l'operazione: uno stato che la
    catena reale non puo' produrre.
    """
    from core.parametri import DUE_TF_SUPERIORI

    if direzione is Bias.NESSUNA:
        return False
    coppia = DUE_TF_SUPERIORI.get(tf_trigger)
    if coppia is None:
        # Nessuna riga per questo timeframe: la condizione non e' definita,
        # quindi non e' soddisfabile. Vale per TF_H12, TF_H6 e TF_12M.
        return False
    atteso = direzione_dello_spazzamento(direzione)
    return all(sbilanciamenti.get(tf) is atteso for tf in coppia)


def direzione_dello_spazzamento(direzione: Bias) -> Bias:
    """Il verso in cui il key level e' stato spazzato, data l'operazione.

    Un'operazione short nasce da un massimo preso verso l'alto, una long da un
    minimo preso verso il basso: lo spazzamento e' sempre l'opposto
    dell'operazione. Sta in una funzione sua perche' e' il perno di REV-46 e
    va potuto citare da un test.
    """
    return Bias.LONG if direzione is Bias.SHORT else Bias.SHORT


# ===========================================================================
# 5. Direzione dal DXY
# ===========================================================================


def direzione_da_dxy(bias_dxy: Bias, strumento: str) -> Optional[Bias]:
    """SETUP-19 — Direzione operativa CFD a partire dalla bias del DXY.

    Restituisce la direzione **sul CFD**. Per sapere quale CRT cercare sul
    future va poi applicato DEF-33, che per `6J` e `6S` inverte il segno: le
    due trasformazioni sono indipendenti e vanno applicate entrambe.

    `XAUUSD` non deriva la direzione dal DXY (PRIN-09): restituisce None, e la
    sua bias si calcola con SETUP-06 applicato a `GC`, senza alcun filtro
    valutario (PA-05).

    Con bias DXY NESSUNA non si opera su alcuna coppia.
    """
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")
    if not UNIVERSO[strumento].deriva_direzione_dal_dxy:
        return None

    tabella = DIREZIONE_DA_BIAS_DXY.get(bias_dxy.value, {})
    ordine = tabella.get(strumento)
    if ordine is None:
        return None
    return Bias.LONG if ordine == "BUY" else Bias.SHORT


# ===========================================================================
# 6. Ingresso su gap
# ===========================================================================


def ingresso_da_gap_ammesso(gap_fase: int, mitigazione: Mitigazione) -> tuple[bool, tuple[str, ...]]:
    """SETUP-09 — L'ingresso su gap e' ammesso solo in fase 3, con un CRT.

    Le fasi 1 e 2 non sono operative: la fase 1 e' il movimento che gli
    appunti chiamano fake. La fase 3 **senza CRT** non produce ordini: lo
    sbilanciamento dell'estremo della fase 1, da solo, non e' un segnale.
    Questa funzione controlla la fase; il CRT lo verifica chi chiama.

    `mitigazione_attesa = NON_DETERMINATA` blocca l'ingresso da gap (DEF-42,
    CTX-01 #10): non e' un errore, e' astensione prevista.

    Restituisce (ammesso, regole_che_bloccano).
    """
    blocchi: list[str] = []
    if gap_fase != 3:
        blocchi.append("SETUP-09")
    if mitigazione is Mitigazione.NON_DETERMINATA:
        blocchi.append("DEF-42")
    return not blocchi, tuple(blocchi)


def doppio_ingresso(crt: Crt, gap: Optional[Gap]) -> bool:
    """SETUP-10 — Due ingressi quando il CRT e' a supporto di un gap.

    Il rischio si divide a meta' fra i due (RISK-04): non due ingressi a
    rischio pieno. Uno viene ancorato al CRT con stop aggressivo, l'altro al
    gap con stop conservativo (SETUP-12, GEST-02).
    """
    if gap is None:
        return False
    return not _piu_alto(crt.tf, gap.tf)


# ===========================================================================
# 7. Esclusioni di SETUP-15
# ===========================================================================


def target_iniziale(crt: Crt, key_level_correnti: Sequence[KeyLevel]) -> Optional[float]:
    """SETUP-14 — Il target del 75% residuo, prima di ogni estensione.

    *"Il target del 75% residuo e' il key level del timeframe piu' alto
    disponibile nella direzione dell'operazione"*, e l'esempio conforme dice
    da dove parte: *"CRT su TF_H4, ingresso short. **Target iniziale sul key
    level TF_H4**. Alla chiusura di TF_1D, se il giornaliero conferma il
    pattern, il target si estende al minimo TF_1D"*. Da li' in poi comanda
    `GEST-08`.

    ## Perche' non e' TP1 (REV-49)

    Il motore usava `TP1` anche come target finale. Con i due valori uguali il
    75% residuo si chiude nello stesso istante del 25%, e allora:

    - `GEST-04` chiude un quarto e porta il resto a break even... di niente;
    - `GEST-05` protegge un residuo che non esiste;
    - `GEST-08` e `SETUP-14` non hanno nulla da estendere.

    Misurato sull'archivio reale: 50 operazioni, **zero** pareggi e **una**
    sola estensione del target, perche' le posizioni morivano nella barra
    successiva all'ingresso. Meta' dell'apparato di gestione era lettera
    morta.

    ## Quale key level

    Quello del timeframe del CRT, nel verso dell'operazione: `KL_min` per una
    short, `KL_max` per una long. `TF_H1` non produce key level propri
    (DEF-36, REV-48), quindi per un CRT orario si usa quello del timeframe
    immediatamente superiore, che e' quanto `DEF-46` prescrive per `TF_H1`.

    `None` se nessuno dei due esiste: chi chiama applica `PRIN-99`, perche'
    una posizione senza bersaglio non ha ragione di essere aperta.
    """
    from core.parametri import TARGET_DI

    cercato = TipoKeyLevel.MIN if crt.direzione is Bias.SHORT else TipoKeyLevel.MAX
    superiore = TARGET_DI.get(crt.tf)
    for tf in (crt.tf, superiore):
        if tf is None:
            continue
        for livello in key_level_correnti:
            if livello.tf is tf and livello.tipo is cercato:
                return livello.valore
    return None


def esclusioni_setup(
    crt: Optional[Crt],
    comando: Bias,
    key_level_preso: bool,
    sbilanciamenti: Mapping[TF, Bias],
    posizioni_aperte_strumento: int,
    limite_rischio_raggiunto: bool,
    dentro_finestra_news: bool,
    dati_coerenti: bool,
    da_gap: bool = False,
    mitigazione: Mitigazione = Mitigazione.NON_ATTESA,
) -> tuple[str, ...]:
    """SETUP-15 — Le dieci condizioni che vietano l'ingresso.

    Restituisce gli ID delle regole violate, in ordine di elenco. Vuoto
    significa che SETUP-15 non si oppone — **non** che si possa operare:
    mancano ancora le condizioni di CTX-01, che per REV-17 vanno unite a
    queste.

    `SETUP-15` cita `RISK-13` per la finestra news mentre `CTX-01` cita
    `CTX-02` per la stessa condizione: sono la stessa regola scritta in due
    file, e il filtro e' per strumento (REV-18).
    """
    violate: list[str] = []

    if not key_level_preso:
        violate.append("SETUP-00")
    if comando is Bias.NESSUNA:
        violate.append("SETUP-06")
    if crt is not None and not direzione_concorde(crt.direzione, comando):
        violate.append("SETUP-07")
    if crt is not None and not _piu_alto(crt.key_level.tf, crt.tf):
        violate.append("DEF-30")
    if crt is not None and not allineamento_soddisfatto(crt.tf, sbilanciamenti, crt.direzione):
        violate.append("SETUP-05")
    if da_gap and mitigazione is Mitigazione.NON_DETERMINATA:
        violate.append("DEF-42")
    if posizioni_aperte_strumento >= MAX_POSIZIONI_PER_STRUMENTO:
        violate.append("RISK-06")
    if limite_rischio_raggiunto:
        violate.append("RISK-07")
    if dentro_finestra_news:
        violate.append("RISK-13")
    if not dati_coerenti:
        violate.append("PRIN-99")

    return tuple(violate)


def setup_recuperabile() -> bool:
    """SETUP-16 e SETUP-04 — Un setup non eseguito non si recupera mai.

    Due regole diverse dicono la stessa cosa da due lati: SETUP-04 fa decadere
    il CRT non eseguito all'apertura di `N3`, SETUP-16 vieta di recuperare un
    setto saltato per un limite di rischio. Anche la conferma manuale mancata
    in modalita' `semi` ricade qui (PA-51).

    Esiste come funzione, invece che come commento, perche' e' una regola che
    verra' cercata: restituisce sempre False, e il suo docstring dice perche'.
    """
    return False


def nuovo_ingresso_dopo_stop(tf_nuovo: TF, tf_andato_in_stop: TF) -> bool:
    """SETUP-11 e AMM-02 — Lo stop su un timeframe non brucia gli altri.

    Un ingresso anticipato su `TF_H1` andato in stop non impedisce l'ingresso
    su `N3` di `TF_1D` se il mercato lo ripropone. E per AMM-02 nemmeno lo
    stesso timeframe resta bruciato, se il setup si riforma.
    """
    return True


# ===========================================================================
# 8. Punto di giudizio
# ===========================================================================


def giud01_scelta_target(
    distanza_kl_gap: Optional[float] = None,
    atr_tf: Optional[float] = None,
) -> tuple[str, str]:
    """GIUD-01 — Target fra key level e gap vicini.

    Restituisce (categoria, motivo). Le risposte sono chiuse: A il gap,
    B il key level, C ambiguo.

    **Oggi restituisce sempre C.** La soglia numerica fra "vicini" e
    "distanti" non esiste (PA-44), e GIUD-01 ha gia' la propria via d'uscita:
    *"REGOLA DI USCITA: se C, il target resta al key level e non si estende al
    gap."* Inventare una soglia sarebbe la cosa peggiore da fare, perche'
    sembrerebbe funzionare.

    `distanza_kl_gap` e `atr_tf` vanno passati lo stesso: il loro rapporto
    viene registrato per ogni decisione, ed e' esattamente il dato che serve a
    chiudere PA-44 con i numeri invece che a occhio (07_casi.md §3.1).
    """
    del distanza_kl_gap, atr_tf   # registrati altrove, non usati per decidere
    return (
        CategoriaGiudizio.AMBIGUO,
        "PA-44: soglia vicini/distanti non definita, il target resta al key level",
    )


def rapporto_giud01(distanza_kl_gap: float, atr_tf: float) -> Optional[float]:
    """07_casi.md §3.1 — Il campo `rapporto`, da registrare per ogni decisione.

    E' la distanza fra key level e bordo del gap, normalizzata sull'ATR del
    timeframe di riferimento. L'ATR e' ammesso qui e solo qui, come unita' di
    misura e mai come generatore di segnali (ESCL-15 b).

    None se l'ATR non e' disponibile o e' nullo: un rapporto inventato
    inquinerebbe proprio i dati che devono chiudere PA-44.
    """
    if atr_tf is None or atr_tf <= 0:
        return None
    return distanza_kl_gap / atr_tf


# ===========================================================================
# CRT-06 — tre modelli CRT allineati
# ===========================================================================


def modelli_allineati(
    crt_per_tf: Mapping[TF, Optional[Crt]],
    coppie: Optional[Mapping[TF, TF]] = None,
) -> tuple[Bias, int]:
    """CRT-06 — Quanti modelli CRT puntano nella stessa direzione.

    *«Tre modelli CRT allineati — `1h/5m` + `4h/15m` + `D/1h` — danno
    l'accuratezza massima.»*

    Non e' la stessa cosa di `SETUP-06`/`bias_comando`, e confonderle sarebbe
    facile. `bias_comando` guarda le **bias** dei timeframe superiori, che
    nascono da accettazione e rifiuto (DEF-16). Questa guarda i **CRT**: il
    pattern completo, sweep e richiusura, formato su piu' coppie insieme.

    Restituisce (direzione comune, quanti). `NESSUNA` e 0 quando i CRT
    presenti non concordano: un disaccordo non e' una direzione debole, e'
    assenza di direzione, e va distinto da "nessun CRT".

    ## Quante coppie si possono davvero guardare

    Le fonti ne nominano tre. Di quelle, **una sola** e' esprimibile coi
    timeframe che DEF-01 ammette: `D1 -> H1`. Le altre due nominano 5 e 15
    minuti, che DEF-01 non contiene (vedi `COPPIE_CRT_FUORI_DEF01`).

    La funzione non lo sa e non deve saperlo: riceve i CRT che le si danno e
    conta. Con le coppie di `COPPIE_CRT` ne guardera' tre — `M1/D1`, `W1/H4`,
    `D1/H1` — che sono le tre esprimibili, non le tre delle fonti. La
    differenza va tenuta a mente leggendo qualunque misura.
    """
    del coppie          # firma tenuta per chi vorra' passare un altro insieme

    direzioni = [crt.direzione for crt in crt_per_tf.values() if crt is not None]
    if not direzioni:
        return Bias.NESSUNA, 0
    prima = direzioni[0]
    if prima is Bias.NESSUNA or any(d is not prima for d in direzioni):
        return Bias.NESSUNA, 0
    return prima, len(direzioni)


# ===========================================================================
# Le otto conferme di Romeo, una funzione ciascuna
# ===========================================================================
#
# Stavano tutte dentro `conferme_di_romeo`, 112 righe in un blocco unico.
# Cosi' NON SE NE POTEVA MISURARE UNA SOLA: per sapere quanto pesa ciascuna
# serve poterla calcolare, provare e pesare da sola, e finche' erano un blocco
# l'unica cosa misurabile era il loro AND — che infatti, con tutte accese, su
# 18 CRT ne blocca 18 e fa tacere il bot del tutto.
#
# Ognuna restituisce `True` (c'e'), `False` (manca) o `None` (non valutabile),
# e prende SOLO cio' che le serve: niente `Fotografia`, niente archivio.
# `None` non e' un no: trasformare "non lo so" in "no" spegnerebbe il bot
# senza dirlo.


def crt20_peso_ombre(n2: Candela, peso_minimo: float = PESO_OMBRE_MINIMO) -> Optional[bool]:
    """CRT-20 — Le ombre di N2 pesano abbastanza?

    Ombre piccole: 33,6% di winrate contro il 59,6% della base. Uno sweep
    "pulito" e' un cattivo segno per la mean-reversion.
    """
    peso = peso_ombre(n2)
    return None if peso is None else peso >= peso_minimo


# Un CISD e' il livello di una consegna che viene superato: serve almeno una
# candela che consegna e una che rompe. Con meno, la risposta onesta e' "non
# valutabile" -- e la differenza NON e' accademica: `False` su CRT-11 fa
# armare il setup (CRT-13 aspetta il CISD), `None` lo lascia proseguire.
CISD_CANDELE_MINIME: Final[int] = 2


def crt11_cisd(candele_ingresso: Sequence[Candela], direzione: Bias) -> Optional[bool]:
    """CRT-11 — C'e' un cambio di carattere sul timeframe di ingresso?

    Con l'ingresso di CRT-13 questa e' INTRINSECA: il CISD e' il primo passo
    della sequenza. Resta perche' il responso serve a chi pesa.

    Con meno di `CISD_CANDELE_MINIME` barre si risponde `None`, non `False`:
    un CISD che non si puo' cercare non e' un CISD che manca. Trasformare
    "non lo so" in "no" e' proprio cio' che questo file vieta -- e qui
    costerebbe caro, perche' su `False` il setup si arma e aspetta.
    """
    if len(candele_ingresso) < CISD_CANDELE_MINIME:
        return None
    return cisd(candele_ingresso, direzione) is not None


def crt12_smt(
    strumento: str,
    candele_strumento: Optional[Sequence[Candela]],
    candele_compagne: Optional[Mapping[str, Sequence[Candela]]],
    direzione: Bias,
) -> Optional[bool]:
    """CRT-12 — C'e' divergenza SMT con almeno una compagna?

    Le fonti la dichiarano una delle tre confluenze NON NEGOZIABILI.
    """
    if not candele_compagne or not candele_strumento:
        return None
    verso_sweep = Bias.LONG if direzione is Bias.SHORT else Bias.SHORT
    giudizi = []
    for compagna, serie in candele_compagne.items():
        esito = divergenza_smt(
            strumento, candele_strumento, serie, compagna, verso_sweep)
        if esito is not None:
            giudizi.append(esito)
    return any(giudizi) if giudizi else None


def crt10_double_purge(n1: Candela, n2: Candela, direzione: Bias) -> Optional[bool]:
    """CRT-10 — Se e' un Double Purge, il lato piu' respinto concorda?

    Se la candela non e' un double purge la regola non ha nulla da dire:
    `None`, non `False`.
    """
    if not double_purge(n1, n2):
        return None
    verso = verso_del_double_purge(n2)
    return None if verso is Bias.NESSUNA else verso is direzione


def crt15_finestra_ny(istante: datetime, tf_crt: TF) -> Optional[bool]:
    """CRT-15 — Siamo dentro una delle finestre orarie di New York?"""
    from core.contesto import dentro_finestra_crt
    return dentro_finestra_crt(istante, tf_crt)


def crt17_meta_range(
    n1: Candela, candele_ingresso: Sequence[Candela], direzione: Bias
) -> Optional[bool]:
    """CRT-17 — La meta' del range tiene, e dalla parte giusta?"""
    if not candele_ingresso:
        return None
    tenuta = meta_tenuta(n1, candele_ingresso)
    if tenuta is None or tenuta is Bias.NESSUNA:
        return None
    return tenuta is direzione


def crt18_meta_ombra(n2: Candela, direzione: Bias) -> Optional[bool]:
    """CRT-18 — N2 chiude oltre il punto medio della propria ombra?"""
    meta = meta_ombra(n2, superiore=(direzione is Bias.SHORT))
    if meta is None:
        return None
    if direzione is Bias.SHORT:
        return n2.chiusura <= meta
    return n2.chiusura >= meta


def crt06_allineamento(
    crt_per_tf: Optional[Mapping[TF, Any]], tf_crt: TF, direzione: Bias
) -> Optional[bool]:
    """CRT-06 — Gli altri timeframe con un CRT puntano dalla stessa parte?"""
    if not crt_per_tf:
        return None
    altri = [c.direzione for t, c in crt_per_tf.items()
             if c is not None and t is not tf_crt]
    return all(d is direzione for d in altri) if altri else None


# ===========================================================================
# CRT-11 e CRT-19/CRT-20 — le due conferme misurate
# ===========================================================================


def conferme_di_romeo(
    n1: Candela,
    n2: Candela,
    candele_ingresso: Sequence[Candela],
    direzione: Bias,
    istante: datetime,
    tf_crt: TF,
    candele_compagne: Optional[Mapping[str, Sequence[Candela]]] = None,
    candele_strumento: Optional[Sequence[Candela]] = None,
    strumento: str = "",
    crt_per_tf: Optional[Mapping[TF, Any]] = None,
    peso_ombre_minimo: float = PESO_OMBRE_MINIMO,
) -> tuple[bool, tuple[str, ...], dict[str, Optional[bool]]]:
    """TUTTE le conferme di Romeo. Restituisce anche COSA HA DETTO CIASCUNA.

    `(ammesso, regole_che_bloccano, responso)`.

    ## Il cambio che conta: filtro e informazione non sono la stessa cosa

    Prima questa funzione faceva solo da filtro in AND: se una conferma
    diceva no, l'operazione moriva. Misurato sull'archivio reale, con tutte
    accese si trovano 18 CRT e se ne bloccano 18 — il bot tace del tutto.

    Ma il bot non decide da solo: c'e' un trader discrezionale a valle, ed e'
    esattamente cio' che `CRT-14` prescrive — *"non si prende ogni istanza, il
    contesto decide quali istanze valgono"*. A un giudice le conferme servono
    **tutte insieme**, pesate, non applicate una per una come veti.

    Per questo il responso e' sempre completo, anche per le conferme spente:

        True   la conferma c'e'
        False  la conferma manca
        None   non valutabile (dati assenti)

    Solo le conferme **accese** in `CONFERME_ROMEO` bloccano. Le altre
    parlano, e chi ascolta decide. `None` non blocca mai: trasformare "non lo
    so" in "no" spegnerebbe il bot senza dirlo.
    """
    blocchi: list[str] = []
    responso: dict[str, Optional[bool]] = {}

    def registra(regola: str, esito: Optional[bool]) -> None:
        """Il verdetto va nel responso sempre; blocca solo se acceso."""
        responso[regola] = esito
        if esito is False and conferma_attiva(regola):
            blocchi.append(regola)

    # L'ordine e' quello storico e non conta: ogni conferma e' indipendente
    # e nessuna legge il responso delle altre. La regola di ciascuna vive
    # nella sua funzione, qui c'e' solo la raccolta.
    registra("CRT-20", crt20_peso_ombre(n2, peso_ombre_minimo))
    registra("CRT-11", crt11_cisd(candele_ingresso, direzione))
    registra("CRT-12", crt12_smt(
        strumento, candele_strumento, candele_compagne, direzione))
    registra("CRT-10", crt10_double_purge(n1, n2, direzione))
    registra("CRT-15", crt15_finestra_ny(istante, tf_crt))
    registra("CRT-17", crt17_meta_range(n1, candele_ingresso, direzione))
    registra("CRT-18", crt18_meta_ombra(n2, direzione))
    registra("CRT-06", crt06_allineamento(crt_per_tf, tf_crt, direzione))

    return not blocchi, tuple(blocchi), responso
