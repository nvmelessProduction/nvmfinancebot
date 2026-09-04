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
from typing import Mapping, Optional, Sequence

from core.definizioni import Bias, Candela, Gap, KeyLevel, Mitigazione, TipoKeyLevel
from core.parametri import (
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


def crt_short(n1: Candela, n2: Candela, tf_crt: TF, key_level: KeyLevel) -> Optional[Crt]:
    """SETUP-02A — CRT short, formato alla chiusura di N2.

    Quattro condizioni simultanee: `N2` prende il key level, supera il massimo
    di `N1`, richiude dentro il range di `N1`, e chiude sotto la chiusura di
    `N1`.

    Il key level dev'essere un `KL_max` di timeframe strettamente superiore
    (SETUP-00, SETUP-02).

    **Nota sulla terza condizione.** `close[N2] <= high[N1]` e' logicamente
    implicata dalla quarta: poiche' `close[N1] <= high[N1]` per costruzione di
    una candela, da `close[N2] < close[N1]` segue sempre
    `close[N2] < high[N1]`. La terza non puo' mai essere l'unica a fallire, e
    nessun test puo' distinguerla. E' scritta qui lo stesso perche' il
    documento la elenca, e questo file traduce il documento: toglierla
    renderebbe il codice piu' corto e meno confrontabile con SETUP-02A.
    (REV-45)
    """
    if key_level.tipo is not TipoKeyLevel.MAX:
        return None
    if not timeframe_crt_ammesso(tf_crt, key_level.tf):
        return None
    if not (
        n2.massimo > key_level.valore          # presa del key level (DEF-38)
        and n2.massimo > n1.massimo
        and n2.chiusura <= n1.massimo
        and n2.chiusura < n1.chiusura
    ):
        return None
    return Crt(Bias.SHORT, tf_crt, n1, n2, key_level)


def crt_long(n1: Candela, n2: Candela, tf_crt: TF, key_level: KeyLevel) -> Optional[Crt]:
    """SETUP-02B — CRT long, formato alla chiusura di N2.

    Vale a specchio la nota di `crt_short` sulla terza condizione: da
    `close[N2] > close[N1]` e `close[N1] >= low[N1]` segue sempre
    `close[N2] >= low[N1]` (REV-45).
    """
    if key_level.tipo is not TipoKeyLevel.MIN:
        return None
    if not timeframe_crt_ammesso(tf_crt, key_level.tf):
        return None
    if not (
        n2.minimo < key_level.valore
        and n2.minimo < n1.minimo
        and n2.chiusura >= n1.minimo
        and n2.chiusura > n1.chiusura
    ):
        return None
    return Crt(Bias.LONG, tf_crt, n1, n2, key_level)


def cerca_crt(
    n1: Candela,
    n2: Candela,
    tf_crt: TF,
    key_level_presi: Sequence[KeyLevel],
) -> Optional[Crt]:
    """SETUP-00 e SETUP-02 — Cerca un CRT fra i key level presi.

    SETUP-00 e' il vincolo fondamentale: *"Il CRT esiste solo come reazione
    alla presa di un key level. In assenza di un key level preso, nessun CRT
    e' valido, qualunque sia la forma delle candele."* Con l'elenco vuoto qui
    non si cerca nemmeno.

    Se piu' key level producono un CRT si tiene quello del **timeframe piu'
    alto**: PREC-02, il timeframe piu' alto comanda.
    """
    trovati: list[Crt] = []
    for livello in key_level_presi:
        for tentativo in (crt_short(n1, n2, tf_crt, livello), crt_long(n1, n2, tf_crt, livello)):
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
    devono aver sbilanciato un key level nella direzione dell'operazione.

    SETUP-05 contiene due blocchi diversi con lo stesso ID. Questo e' il
    secondo, quello introdotto da "Numero minimo", ed e' il cancello a cui si
    riferiscono SETUP-15 e CTX-01 #4 quando parlano di "meno di 2 timeframe
    allineati" (REV-22). Il primo blocco definisce il termine "allineati" per
    l'annotazione dei casi, e non e' una condizione di ingresso.

    `TF_H12` e `TF_H6` non compaiono nella tabella: non sono timeframe di
    allineamento, ed e' la ragione per cui un CRT non puo' nascere li'.
    """
    from core.parametri import DUE_TF_SUPERIORI

    if direzione is Bias.NESSUNA:
        return False
    coppia = DUE_TF_SUPERIORI.get(tf_trigger)
    if coppia is None:
        # Nessuna riga per questo timeframe: la condizione non e' definita,
        # quindi non e' soddisfabile. Vale per TF_H12, TF_H6 e TF_12M.
        return False
    return all(sbilanciamenti.get(tf) is direzione for tf in coppia)


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
