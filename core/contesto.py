"""I filtri di astensione di `docs/02_contesto.md`, come funzioni pure.

`CTX-00` dice la cosa che governa tutto il file: *"Il bot analizza sempre, in
ogni momento di mercato aperto. Opera solo quando esiste un setup E nessun
filtro di questo file e' attivo."* Analisi e operativita' sono cose distinte:
il sistema non si spegne mai, si astiene.

Per `PREC-04` questi filtri battono `03_setup.md`: un filtro attivo impedisce
l'esecuzione di qualsiasi setup, per quanto valido.

**L'elenco di CTX-01 e quello di SETUP-15 non coincidono**, e per REV-17 il
motore applica la loro **unione**. Qui c'e' la parte di CTX-01. Le due
condizioni che solo CTX-01 elenca — festivita' di mercato e rapporto
rischio/rendimento sotto soglia — sono quelle che si perderebbero applicando
il solo SETUP-15.

Nessuna funzione qui legge il calendario da disco: gli eventi arrivano come
dati. Il caricamento e' compito di `motore.py` (PA-54).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping, Optional, Sequence

from core.definizioni import Bias
from core.parametri import (
    FINESTRA_NEWS_MINUTI_DOPO,
    gerarchia,
    FINESTRA_NEWS_MINUTI_PRIMA,
    MAX_POSIZIONI_PER_STRUMENTO,
    NEWS_IMPATTO_MINIMO_STELLE,
    RR_MINIMO,
    TF,
    UNIVERSO,
    e_festivita,
    richiedi,
)

# ===========================================================================
# Tipi
# ===========================================================================


@dataclass(frozen=True)
class EventoNews:
    """Un evento del calendario economico (CTX-02, RISK-13)."""

    orario_utc: datetime
    valuta: str
    stelle: int


@dataclass(frozen=True)
class Astensione:
    """Un motivo per non operare, con l'ID della regola che lo impone."""

    regola: str
    motivo: str


# ===========================================================================
# CTX-02 — news ad alto impatto
# ===========================================================================


def valute_di(strumento: str) -> Optional[frozenset[str]]:
    """Le due valute di una coppia forex.

    Per `XAUUSD` restituisce None, che significa **tutte**: per l'oro il
    filtro non e' ristretto a una valuta, ogni news a 3 stelle di qualsiasi
    paese blocca le nuove aperture (CTX-02, RISK-13, PA-36).
    """
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")
    if not UNIVERSO[strumento].deriva_direzione_dal_dxy:
        return None
    return frozenset({strumento[:3], strumento[3:]})


def dentro_finestra_news(
    adesso: datetime,
    strumento: str,
    eventi: Sequence[EventoNews],
) -> Optional[EventoNews]:
    """CTX-02 e RISK-13 — L'evento che blocca le nuove aperture, se c'e'.

    Finestra da 30 minuti prima a 30 minuti dopo l'orario della news, estremi
    inclusi. Il filtro e' **per strumento** (REV-18): una news sulla sterlina
    ferma `GBPUSD`, non `EURUSD`. Il blocco riguarda solo le nuove aperture:
    una posizione gia' aperta attraversa la news senza modifiche.

    Restituisce il primo evento che blocca, o None.
    """
    valute = valute_di(strumento)
    prima = timedelta(minutes=FINESTRA_NEWS_MINUTI_PRIMA)
    dopo = timedelta(minutes=FINESTRA_NEWS_MINUTI_DOPO)

    for evento in eventi:
        if evento.stelle < NEWS_IMPATTO_MINIMO_STELLE:
            continue
        if valute is not None and evento.valuta not in valute:
            continue
        if evento.orario_utc - prima <= adesso <= evento.orario_utc + dopo:
            return evento
    return None


def calendario_utilizzabile(
    eventi: Optional[Sequence[EventoNews]],
    eta_ore: Optional[float],
) -> bool:
    """PA-55 — Il calendario news e' disponibile e abbastanza fresco?

    Se manca, e' vuoto o e' piu' vecchio della soglia, non si opera: e'
    PRIN-99, e il filtro news e' obbligatorio in CTX-01 #8 e SETUP-15.
    Operare senza sapere se fra due minuti esce un dato a 3 stelle sarebbe
    peggio che saltare la giornata.
    """
    from core.parametri import ETA_MASSIMA_CALENDARIO_ORE

    if richiedi("PA-55") != "astieniti":
        raise ValueError(f"PA-55: lettura non riconosciuta: {richiedi('PA-55')!r}")
    if eventi is None or eta_ore is None:
        return False
    return eta_ore <= ETA_MASSIMA_CALENDARIO_ORE


# ===========================================================================
# CTX-04 — festivita'
# ===========================================================================


def giorno_di_festivita(giorno: date) -> Optional[str]:
    """CTX-04 — Nei giorni di festivita' il bot non apre nuove posizioni.

    Le date sono calcolate, non tabellate: sei delle dodici sono mobili e una
    tabella scadrebbe ogni 1 gennaio (PA-53).
    """
    return e_festivita(giorno)


# ===========================================================================
# CTX-05 — momento dell'ingresso
# ===========================================================================


def rapporto_rischio_rendimento(
    prezzo_ingresso: float,
    livello_stop: float,
    target: float,
) -> Optional[float]:
    """GEST-01 e CTX-05 — Rapporto rischio/rendimento sui prezzi effettivi.

    Si calcola su `TP1` (GEST-01 v0.3), non sul target finale, e sui prezzi
    **al momento dell'ordine**, non su quelli teorici alla chiusura di `N2`.

    None in due casi, entrambi PRIN-99:

    - **rischio nullo**, cioe' stop coincidente con l'ingresso (RISK-03);
    - **stop e target dallo stesso lato** dell'ingresso. GEST-01 scrive la
      formula con i valori assoluti e tace su questo caso, ma un target che
      sta dalla stessa parte dello stop descrive un'operazione che non puo'
      vincere: con gli assoluti darebbe un rapporto positivo e plausibile, e
      la size verrebbe calcolata su di esso. E' dato incoerente, non un
      setup sfortunato.
    """
    rischio = abs(prezzo_ingresso - livello_stop)
    if rischio == 0:
        return None
    if (livello_stop - prezzo_ingresso) * (target - prezzo_ingresso) >= 0:
        return None
    return abs(target - prezzo_ingresso) / rischio


def ritardo_tollerabile(
    prezzo_ingresso: float,
    livello_stop: float,
    target: float,
) -> bool:
    """CTX-05 — E' il rapporto a stabilire se il ritardo sia accettabile.

    *"Non esiste un ritardo prestabilito. Un ritardo di alcuni minuti e'
    accettabile purche', ricalcolando il rapporto sui prezzi effettivi, questo
    resti pari o superiore a 1,5."* Non c'e' alcun limite di tempo: se il
    prezzo si e' mosso troppo, e' il rapporto a dirlo.
    """
    rapporto = rapporto_rischio_rendimento(prezzo_ingresso, livello_stop, target)
    return rapporto is not None and rapporto >= RR_MINIMO


# ===========================================================================
# CTX-03, CTX-07, CTX-08, CTX-09 — cio' che NON filtra
# ===========================================================================


def filtro_su_condizioni_di_mercato() -> bool:
    """CTX-03 — Non esistono filtri su volatilita', spread o divergenza CFD.

    Restituisce sempre False, ed esiste come funzione perche' e' una regola
    che verra' cercata. *"Nessuna condizione del CFD puo' impedire
    un'operazione ne' provocarne la chiusura."*

    Conseguenza dichiarata: in momenti di liquidita' ridotta l'ordine puo'
    essere eseguito a un prezzo sensibilmente peggiore di quello del future.
    Non e' un errore, e' il prezzo della scelta di CTX-03.
    """
    return False


def blocco_per_perdite_consecutive(perdite_di_fila: int) -> bool:
    """CTX-09 — Non esiste un limite al numero di perdite consecutive.

    L'unica protezione sono i limiti percentuali di RISK-07, RISK-08 e
    RISK-09. Con il rischio all'1% il limite giornaliero del 3% arriva dopo
    tre stop pieni.
    """
    del perdite_di_fila
    return False


def timeframe_escluso_per_buchi(candele_mancanti: int) -> bool:
    """CTX-07 — I buchi nello storico non escludono un timeframe.

    Resta valido il pavimento di DEF-26 — almeno tre candele chiuse dentro il
    lookback — che e' cosa diversa: un conto sono i buchi, un altro la
    quantita' minima di storia (REV-19).
    """
    del candele_mancanti
    return False


def pronto_all_avvio(timeframe_ricalcolati: Sequence[TF], timeframe_attesi: Sequence[TF]) -> bool:
    """CTX-08 e CTX-10 — Il bot opera subito, ma dopo aver ricalcolato.

    `CTX-08` vieta un **periodo di osservazione**: non si aspettano candele
    nuove. Non vieta di calcolare da candele che esistono gia'. All'avvio si
    ricostruisce tutto dallo storico e poi si e' operativi: il ricalcolo e'
    istantaneo e non e' un riscaldamento (REV-20).

    `CTX-10` pretende che l'analisi del timeframe appena chiuso sia
    ricalcolata prima di operare sui timeframe inferiori.
    """
    if richiedi("REV-20") != "ricalcola_prima":
        raise ValueError(f"REV-20: lettura non riconosciuta: {richiedi('REV-20')!r}")
    return set(timeframe_attesi) <= set(timeframe_ricalcolati)


# ===========================================================================
# PRIN-12, PRIN-13, PRIN-14 — finestra operativa
# ===========================================================================


def fasce_orarie_escluse() -> bool:
    """PRIN-12 — Il sistema e' attivo 24 ore su 24 nei giorni di mercato aperto.

    Non esistono fasce orarie escluse ne' periodi dell'anno di sospensione.
    Restituisce sempre False, ed esiste perche' e' una regola che verra'
    cercata.
    """
    return False


def unica_sospensione_prevista() -> str:
    """PRIN-14 — L'unica interruzione e' la finestra news a 3 stelle (RISK-13)."""
    return "RISK-13"


def operativita_domenicale_ammessa(istante: datetime, tf_setup: TF) -> bool:
    """PRIN-13 — All'apertura domenicale si opera solo da TF_1W in su.

    *"SE all'apertura domenicale esiste un setup valido su TF_1W o superiore
    ALLORA l'ingresso sulla candela N3 e' ammesso ALTRIMENTI nessuna
    operativita' domenicale."*

    Il giorno di contrattazione del future comincia alle 18:00 di New York
    della domenica (DEF-03), quindi la "domenica" del calendario solare
    contiene sia la chiusura del fine settimana sia l'apertura della
    settimana nuova. Qui si usa il giorno solare UTC: e' il criterio piu'
    prudente, perche' copre l'intera finestra in cui la regola si applica.

    Fuori dalla domenica non c'e' alcuna restrizione: la regola parla solo
    dell'apertura domenicale.
    """
    if istante.weekday() != 6:            # 6 = domenica
        return True
    ordine = gerarchia()
    return ordine.index(tf_setup) <= ordine.index(TF.W1)


# ===========================================================================
# CTX-01 — l'elenco completo
# ===========================================================================


def filtri_attivi(
    adesso: datetime,
    strumento: str,
    key_level_preso: bool,
    comando: Bias,
    direzione_crt: Optional[Bias],
    allineamento_ok: bool,
    rapporto_su_tp1: Optional[float],
    posizioni_aperte_strumento: int,
    limite_rischio_raggiunto: bool,
    eventi_news: Sequence[EventoNews],
    mitigazione_non_determinata: bool,
    dati_coerenti: bool,
) -> tuple[Astensione, ...]:
    """CTX-01 — Le undici condizioni che impediscono l'invio di un ordine.

    Restituisce l'elenco delle astensioni attive, ciascuna con l'ID della
    regola e il motivo in chiaro. Vuoto significa che questo file non si
    oppone: le condizioni di SETUP-15 vanno verificate a parte e unite
    (REV-17).

    Le due voci che solo CTX-01 porta sono la #5 (rapporto sotto 1,5) e la
    #9 (festivita'): sono quelle che si perderebbero usando il solo SETUP-15.
    """
    attive: list[Astensione] = []

    if not key_level_preso:                                             # 1
        attive.append(Astensione("SETUP-00", "nessun key level e' stato preso"))
    if comando is Bias.NESSUNA:                                         # 2
        attive.append(Astensione("SETUP-06", "bias_comando e' NESSUNA"))
    if direzione_crt is not None and comando is not Bias.NESSUNA and direzione_crt is not comando:
        attive.append(Astensione("SETUP-07", "direzione del CRT opposta a bias_comando"))  # 3
    if not allineamento_ok:                                             # 4
        attive.append(Astensione("SETUP-05", "meno di 2 timeframe superiori allineati"))
    if rapporto_su_tp1 is None or rapporto_su_tp1 < RR_MINIMO:          # 5
        attive.append(
            Astensione("GEST-01", f"rapporto su TP1 sotto {RR_MINIMO}: {rapporto_su_tp1}")
        )
    if posizioni_aperte_strumento >= MAX_POSIZIONI_PER_STRUMENTO:       # 6
        attive.append(Astensione("RISK-06", f"gia' {posizioni_aperte_strumento} posizioni aperte"))
    if limite_rischio_raggiunto:                                        # 7
        attive.append(Astensione("RISK-07", "limite di perdita raggiunto"))

    evento = dentro_finestra_news(adesso, strumento, eventi_news)       # 8
    if evento is not None:
        attive.append(
            Astensione("CTX-02", f"news {evento.stelle} stelle su {evento.valuta} alle {evento.orario_utc}")
        )

    festivita = giorno_di_festivita(adesso.date())                      # 9
    if festivita is not None:
        attive.append(Astensione("CTX-04", f"festivita' di mercato: {festivita}"))

    if mitigazione_non_determinata:                                     # 10
        attive.append(Astensione("DEF-42", "mitigazione_attesa NON_DETERMINATA su ingresso da gap"))
    if not dati_coerenti:                                               # 11
        attive.append(Astensione("PRIN-99", "dato del vocabolario mancante o incoerente"))

    return tuple(attive)


# ===========================================================================
# Precedenze
# ===========================================================================

PRECEDENZE: Mapping[str, str] = {
    "PREC-01": "In conflitto: RISK batte SETUP",
    "PREC-02": "In conflitto tra timeframe: il timeframe piu' alto comanda",
    "PREC-03": "In conflitto tra fonti dati: il future comanda",
    "PREC-04": "In conflitto: CONTESTO batte SETUP",
    "PREC-05": "In conflitto: ESCLUSIONI batte tutto",
}
