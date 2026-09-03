"""Tutti i valori numerici della strategia, e tutti i punti non ancora decisi.

Due regole che questo file fa rispettare al resto del motore:

1. **Nessun numero vive dentro la logica.** Ogni soglia, percentuale e periodo
   sta qui, con l'ID della regola che la stabilisce.

2. **Nessun punto aperto viene deciso di nascosto.** Dove i documenti non
   dicono, o dicono due cose, questo file **non sceglie**: espone le letture
   possibili e solleva `PuntoApertoError` finché non si compila `SCELTE`.
   Un motore che gira ma applica una regola inventata è peggio di un motore
   che si ferma.

Gli ID citati sono di tre famiglie:
  `DEF-`, `SETUP-`, `GEST-`, `RISK-`, `CTX-`, `PRIN-`, `ESCL-`, `GIUD-`
        regole dei documenti in docs/
  `PA-`   punti aperti dichiarati dai documenti stessi
  `REV-`  contraddizioni e ambiguita' rilevate in docs/REVISIONE-2026-09-03.md

Nessuna dipendenza esterna: questo modulo sta sotto tutto il resto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Optional

# ===========================================================================
# 1. Timeframe (DEF-01, PRIN-10)
# ===========================================================================


class TF(str, Enum):
    """I dieci timeframe ammessi. Nessun altro puo' essere citato (DEF-01)."""

    M12 = "TF_12M"
    M6 = "TF_6M"
    M3 = "TF_3M"
    M1 = "TF_1M"
    W1 = "TF_1W"
    D1 = "TF_1D"
    H12 = "TF_H12"
    H6 = "TF_H6"
    H4 = "TF_H4"
    H1 = "TF_H1"


# DEF-01 contiene DUE gerarchie diverse, a diciassette righe di distanza.
# Non scelgo io quale: vedi REV-10 e `gerarchia()` piu' sotto.
GERARCHIA_COMPLETA: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H12, TF.H6, TF.H4, TF.H1,
)
GERARCHIA_RIDOTTA: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H4, TF.H1,
)

# Ruoli dichiarati da DEF-01 e PRIN-10.
TF_BIAS: Final[tuple[TF, ...]] = (TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1)
TF_SOLO_GAP: Final[tuple[TF, ...]] = (TF.H12, TF.H6)
TF_ESECUZIONE: Final[tuple[TF, ...]] = (TF.D1, TF.H4, TF.H1)

# DEF-22 passo 1: ordine di scansione per il target direzionale globale.
# Nota: salta TF_H12 e TF_H6, coerentemente con DEF-28.
ORDINE_SCANSIONE_TARGET: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H4, TF.H1,
)

# DEF-46: target di un singolo timeframe = key level del TF immediatamente
# superiore. TF_12M e' il caso speciale: usa il target globale di DEF-22.
TARGET_DI: Final[dict[TF, Optional[TF]]] = {
    TF.H1: TF.H4,
    TF.H4: TF.D1,
    TF.D1: TF.W1,
    TF.W1: TF.M1,
    TF.M1: TF.M3,
    TF.M3: TF.M6,
    TF.M6: TF.M12,
    TF.M12: None,  # vedi DEF-22
}

# SETUP-05, "regola dei due timeframe superiori".
# TF_H12 e TF_H6 non compaiono: la regola lo dice esplicitamente. E' la
# ragione per cui un CRT su quei due timeframe non e' eseguibile (REV-11).
DUE_TF_SUPERIORI: Final[dict[TF, tuple[TF, TF]]] = {
    TF.H1: (TF.H4, TF.D1),
    TF.H4: (TF.D1, TF.W1),
    TF.D1: (TF.W1, TF.M1),
    TF.W1: (TF.M1, TF.M3),
    TF.M1: (TF.M3, TF.M6),
}

# DEF-28: ogni quanto si ricalcolano livelli strutturali e key level.
# Presente per completezza; il motore la usa solo per gli assert.
RICALCOLO_ANNUO: Final[dict[TF, int]] = {
    TF.M12: 1, TF.M6: 2, TF.M3: 4, TF.M1: 12,
}


# ===========================================================================
# 2. Soglie sulle candele
# ===========================================================================

# DEF-21, rifiuto forte: ombra > SOGLIA x corpo.
SOGLIA_SPIKE_RIFIUTO_FORTE: Final[float] = 0.5

# DEF-41, indecisione: min(ombre) >= SOGLIA x max(ombre).
SOGLIA_SIMMETRIA_OMBRE: Final[float] = 0.40

# DEF-41, corpo minuscolo. Il testo della regola dice 0.05, PA-29 chiede di
# "confermare 0.10". Non scelgo: vedi REV-32.
SOGLIA_CORPO_INDECISIONE_TESTO_DEF41: Final[float] = 0.05
SOGLIA_CORPO_INDECISIONE_PA29: Final[float] = 0.10

# DEF-19: nessuna tolleranza sul superamento di un livello. Un tick basta.
# DEF-09 e DEF-37: confronto esatto, nessuna tolleranza.
TOLLERANZA_CONFRONTO_PREZZI: Final[float] = 0.0


# ===========================================================================
# 3. Storico e indicatori
# ===========================================================================

# DEF-26
LOOKBACK_ANNI: Final[int] = 5
MINIMO_CANDELE_CHIUSE_PER_TF: Final[int] = 3

# DEF-44. Unico indicatore ammesso per generare un dato (ESCL-15 a).
RSI_PERIODO: Final[int] = 14

# ESCL-15 b e 07_casi.md §3.1. Ammesso SOLO come unita' di misura in GIUD-01:
# non puo' generare segnali, filtrare ingressi, determinare stop o size.
ATR_PERIODO: Final[int] = 14


# ===========================================================================
# 4. Ingresso e gestione
# ===========================================================================

# GEST-01, come corretta in 04_gestione.md v0.3: il rapporto si calcola su TP1.
RR_MINIMO: Final[float] = 1.5

# SETUP-13 e GEST-07: al raggiungimento di TP1 si chiude questa frazione e il
# resto va a break even. Il residuo non ha ulteriori parziali.
FRAZIONE_CHIUSA_A_TP1: Final[float] = 0.25
FRAZIONE_RESIDUA: Final[float] = 0.75

# GIUD-01, regola di uscita: categoria C significa sempre astensione dal
# gap, e il target resta al key level. Questo e' deterministico e non aperto.
GIUD01_CATEGORIA_C_TARGET_RESTA_AL_KEY_LEVEL: Final[bool] = True


# ===========================================================================
# 5. Rischio (05_rischio.md)
# ===========================================================================

# RISK-01
RISCHIO_BASE: Final[float] = 0.0100

# RISK-02, scala per correlazione piena.
SCALA_RISCHIO: Final[dict[int, float]] = {1: 0.0100, 2: 0.0075}
SCALA_RISCHIO_DA_3_IN_SU: Final[float] = 0.0045

# RISK-06
MAX_POSIZIONI_PER_STRUMENTO: Final[int] = 4

# RISK-07, RISK-08, RISK-09. Calcolati sul P&L chiuso (RISK-10).
LIMITE_GIORNALIERO: Final[float] = 0.03
LIMITE_SETTIMANALE: Final[float] = 0.06
LIMITE_MENSILE: Final[float] = 0.10

# RISK-03: la size si arrotonda sempre per difetto al passo del broker.
# Se l'arrotondamento produce zero, non si opera.
ARROTONDAMENTO_SIZE_PER_DIFETTO: Final[bool] = True


# ===========================================================================
# 6. Contesto e calendario (02_contesto.md)
# ===========================================================================

# CTX-02 e RISK-13: finestra di blocco attorno alle news a 3 stelle.
FINESTRA_NEWS_MINUTI_PRIMA: Final[int] = 30
FINESTRA_NEWS_MINUTI_DOPO: Final[int] = 30
NEWS_IMPATTO_MINIMO_STELLE: Final[int] = 3

# CTX-06 e DEF-32: latenza tollerata del solo dato DXY.
LATENZA_DXY_MINUTI: Final[int] = 10

# CTX-04. Valide per il 2026, verificate data per data. PA-53 chiede di
# aggiornarle a inizio anno o di sostituirle con il calcolo automatico delle
# festivita' USA a data mobile: quelle segnate MOBILE cambiano ogni anno.
ANNO_DI_VALIDITA_FESTIVITA: Final[int] = 2026
FESTIVITA_MERCATO: Final[dict[tuple[int, int], str]] = {
    (1, 1): "Capodanno",
    (1, 19): "Martin Luther King Day (MOBILE)",
    (2, 16): "Presidents' Day (MOBILE)",
    (4, 3): "Venerdi' Santo (MOBILE)",
    (5, 25): "Memorial Day (MOBILE)",
    (6, 19): "Juneteenth",
    (7, 3): "Independence Day, osservato (MOBILE)",
    (9, 7): "Labor Day (MOBILE)",
    (11, 26): "Thanksgiving (MOBILE)",
    (11, 27): "Giorno dopo Thanksgiving (MOBILE)",
    (12, 24): "Vigilia di Natale",
    (12, 25): "Natale",
}


# ===========================================================================
# 7. Strumenti (PRIN-08, DEF-33, SETUP-19)
# ===========================================================================


@dataclass(frozen=True)
class Strumento:
    """Corrispondenza fra strumento di esecuzione e strumento di analisi.

    `segno_invertito` (DEF-33): una bias LONG rilevata sul future corrisponde
    a un ordine SELL sul CFD. Vale per `6J` e `6S`.
    """

    cfd: str
    future: str
    borsa: str
    segno_invertito: bool
    deriva_direzione_dal_dxy: bool


UNIVERSO: Final[dict[str, Strumento]] = {
    "XAUUSD": Strumento("XAUUSD", "GC", "COMEX", False, False),
    "EURUSD": Strumento("EURUSD", "6E", "CME", False, True),
    "GBPUSD": Strumento("GBPUSD", "6B", "CME", False, True),
    "AUDUSD": Strumento("AUDUSD", "6A", "CME", False, True),
    "USDCHF": Strumento("USDCHF", "6S", "CME", True, True),
    "USDJPY": Strumento("USDJPY", "6J", "CME", True, True),
}

# DEF-33: strumenti di sola analisi, mai operati.
DXY_TF_ALTI: Final[str] = "ICEUS"          # future ICE, per TF_1D e superiori
DXY_TF_BASSI: Final[str] = "CAPITALCOM:DXY"  # CFD, per TF_H12 e inferiori

# SETUP-19. Direzioni espresse in ordini **CFD**. Per gli strumenti a segno
# invertito va poi applicato DEF-33 per sapere quale CRT cercare sul future.
DIREZIONE_DA_BIAS_DXY: Final[dict[str, dict[str, str]]] = {
    "LONG": {
        "EURUSD": "SELL", "GBPUSD": "SELL", "AUDUSD": "SELL",
        "USDCHF": "BUY", "USDJPY": "BUY",
    },
    "SHORT": {
        "EURUSD": "BUY", "GBPUSD": "BUY", "AUDUSD": "BUY",
        "USDCHF": "SELL", "USDJPY": "SELL",
    },
    "NESSUNA": {},  # nessuna operazione su alcuna coppia
}


# ===========================================================================
# 8. Punti aperti
# ===========================================================================


class PuntoApertoError(NotImplementedError):
    """Il motore ha incontrato un punto che i documenti non hanno deciso.

    Non e' un bug: e' il comportamento richiesto. Si scioglie compilando
    `SCELTE` oppure aggiornando il documento che genera il punto.
    """


@dataclass(frozen=True)
class PuntoAperto:
    """Un buco noto nei documenti, con l'effetto che ha sul motore."""

    identificativo: str
    regole: tuple[str, ...]
    descrizione: str
    # Se True, senza risposta la regola non si puo' eseguire affatto.
    bloccante: bool
    # Letture possibili, quando il documento ne ammette piu' di una.
    letture: tuple[str, ...] = ()
    # Valore usato se nessuno compila SCELTE. Solo per i punti non bloccanti.
    default: Any = None
    motivo_default: str = ""


PUNTI_APERTI: Final[dict[str, PuntoAperto]] = {
    # --- bloccanti dichiarati dai documenti stessi -------------------------
    "PA-62": PuntoAperto(
        "PA-62",
        ("DEF-47", "RISK-03"),
        "Fattore k di conversione fra punto future e punto CFD, per ciascuno "
        "dei sei strumenti. Senza, nessuna size e' calcolabile.",
        bloccante=True,
    ),
    "PA-44": PuntoAperto(
        "PA-44",
        ("GIUD-01",),
        "Soglia numerica fra 'vicini' e 'distanti' in GIUD-01, in multipli di "
        "ATR o in percentuale del range di N1.",
        bloccante=True,
    ),
    "PA-31": PuntoAperto(
        "PA-31",
        ("DEF-16", "DEF-21"),
        "Cosa fa la bias quando una candela spazza un estremo e richiude "
        "dentro ma non supera la soglia spike/corpo. Il preambolo di DEF-21 "
        "e le sue due definizioni si contraddicono (REV-08).",
        bloccante=True,
    ),
    "PA-05": PuntoAperto(
        "PA-05",
        ("PRIN-09", "SETUP-19"),
        "Regole proprie di XAUUSD. PRIN-09 dice che ha bias propria e non la "
        "deriva dal DXY, ma nessuna regola dice come si determina.",
        bloccante=True,
    ),
    "PA-15": PuntoAperto(
        "PA-15",
        ("SETUP-03",),
        "Conferma dei correlati: quali future devono essere allineati e con "
        "quale criterio. Non e' detto se sia una condizione di ingresso o un "
        "dato statistico.",
        bloccante=True,
    ),
    "PA-51": PuntoAperto(
        "PA-51",
        ("PRIN-16", "SETUP-04"),
        "Setup proposto e non confermato entro l'apertura di N3. PRIN-16 "
        "impone la conferma manuale, SETUP-04 fa decadere il setto subito "
        "dopo (REV-21).",
        bloccante=True,
    ),
    "PA-47": PuntoAperto(
        "PA-47",
        ("GEST-06",),
        "Posizione con stop aggressivo quando il gap che la motivava viene "
        "invalidato e lo stop non e' stato colpito.",
        bloccante=True,
    ),
    "PA-48": PuntoAperto(
        "PA-48",
        ("GEST-09",),
        "Target consumato prima del raggiungimento di TP1: la posizione e' "
        "ancora allo stop iniziale e non esiste una regola.",
        bloccante=True,
    ),
    "PA-60": PuntoAperto(
        "PA-60",
        ("SETUP-14", "GEST-08", "DEF-36", "DEF-25"),
        "SETUP-14 usa i key level come target finale, mentre DEF-36 assegna "
        "ai key level l'ingresso e ai livelli strutturali il target (REV-25).",
        bloccante=True,
    ),
    "PA-63": PuntoAperto(
        "PA-63",
        ("RISK-02",),
        "Ridimensionamento non eseguibile perche' il volume risultante e' "
        "sotto il passo minimo del broker.",
        bloccante=True,
    ),
    "PA-54": PuntoAperto(
        "PA-54",
        ("CTX-02", "RISK-13"),
        "Come si legge il calendario news di investing.com: manuale, file o "
        "interrogazione automatica. Il filtro news e' obbligatorio in CTX-01 "
        "#8 e SETUP-15, quindi senza calendario nessun setup e' valutabile.",
        bloccante=True,
    ),

    # --- contraddizioni con due letture possibili -------------------------
    "REV-10": PuntoAperto(
        "REV-10",
        ("DEF-01", "DEF-30", "SETUP-05"),
        "DEF-01 contiene due gerarchie diverse. DEF-30 usa la completa, "
        "SETUP-05 la ridotta.",
        bloccante=True,
        letture=("completa", "ridotta"),
    ),
    "REV-15": PuntoAperto(
        "REV-15",
        ("DEF-13", "DEF-31"),
        "Ordine di scansione del gap attivo: DEF-13 elenca sei timeframe, "
        "DEF-31 dice che TF_H12 e TF_H6 vi rientrano.",
        bloccante=True,
        letture=("senza_h12_h6", "con_h12_h6"),
    ),
    "REV-23": PuntoAperto(
        "REV-23",
        ("DEF-36", "DEF-38", "SETUP-02"),
        "I key level si calcolano su C1 (lettera di DEF-36) o su C0 (uso "
        "corrente di 'candela precedente')? Sposta ogni livello di un periodo.",
        bloccante=True,
        letture=("C1", "C0"),
    ),
    "REV-42": PuntoAperto(
        "REV-42",
        ("RISK-02", "RISK-06"),
        "RISK-02 dice sia che tutte le posizioni aperte vengono "
        "ridimensionate, sia che non lo sono. Cambia l'esposizione massima "
        "per strumento da 1,80% a 2,65%.",
        bloccante=True,
        letture=("ridimensiona", "non_ridimensiona"),
    ),
    "REV-03": PuntoAperto(
        "REV-03",
        ("RISK-01", "RISK-02", "RISK-06"),
        "XAUUSD: RISK-02 si applica 'esclusivamente' al forex, ma RISK-06 "
        "dice che ogni posizione segue la scala di RISK-02. Con RISK-01 "
        "secco, quattro posizioni sull'oro valgono il 4,00%.",
        bloccante=True,
        letture=("scala_risk02", "rischio_pieno_risk01"),
    ),
    "REV-43": PuntoAperto(
        "REV-43",
        ("DEF-43", "DEF-45", "SETUP-09"),
        "DEF-45 non elenca DEF-43 fra le regole di sorveglianza, quindi le "
        "fasi del gap sarebbero calcolo su candela chiusa; ma il testo di "
        "DEF-43 dice tre volte 'prezzo scambiato' e 'in continuo'.",
        bloccante=True,
        letture=("sorveglianza_tick", "calcolo_candela_chiusa"),
    ),
    "REV-22": PuntoAperto(
        "REV-22",
        ("SETUP-05", "CTX-01", "SETUP-15"),
        "SETUP-05 definisce due condizioni diverse con lo stesso ID: bias+CRT "
        "concordi, oppure due TF superiori che hanno sbilanciato un key level.",
        bloccante=True,
        letture=("bias_e_crt", "due_tf_key_level"),
    ),
    "REV-26": PuntoAperto(
        "REV-26",
        ("SETUP-14", "GEST-08"),
        "'quel timeframe conferma il pattern' non e' definito. Governa "
        "l'estensione progressiva del target.",
        bloccante=True,
        letture=("crt_formato", "bias_concorde", "key_level_sbilanciato"),
    ),
    "REV-27": PuntoAperto(
        "REV-27",
        ("DEF-13", "DEF-15bis", "DEF-30"),
        "Con gap_attivo_long e gap_attivo_short su timeframe diversi, non e' "
        "detto quale sia il gap target e quale il TF_riferimento.",
        bloccante=True,
        letture=("tf_piu_alto", "concorde_con_bias_comando"),
    ),
    "REV-28": PuntoAperto(
        "REV-28",
        ("DEF-30",),
        "TF_riferimento e' quello del gap attivo o del key level preso, "
        "'a seconda di quale abbia generato il contesto'. La regola che lo "
        "stabilisce non esiste.",
        bloccante=True,
        letture=("gap", "key_level", "il_piu_alto_dei_due"),
    ),
    "REV-29": PuntoAperto(
        "REV-29",
        ("DEF-42", "DEF-15bis"),
        "'direzione del gap' in DEF-42 e' la polarita' o la direzione "
        "operativa verso il target? DEF-15bis dice che possono essere opposte.",
        bloccante=True,
        letture=("polarita", "direzione_operativa"),
    ),
    "REV-30": PuntoAperto(
        "REV-30",
        ("DEF-43",),
        "Fase 2: 'esce nella direzione contraria' a cosa. Fase 3: se "
        "estremo_fase1 e' interno alla zona, 'rientra' e 'supera' possono non "
        "essere simultaneamente vere.",
        bloccante=True,
    ),
    "REV-31": PuntoAperto(
        "REV-31",
        ("DEF-44",),
        "RSI sul timeframe del gap (DEF-44) o su quello di trigger "
        "(vocabolario)? Per DEF-30 non coincidono mai.",
        bloccante=True,
        letture=("tf_del_gap", "tf_di_trigger"),
    ),
    "REV-32": PuntoAperto(
        "REV-32",
        ("DEF-41", "PA-29"),
        "Soglia del corpo per l'indecisione: 0.05 nel testo di DEF-41, 0.10 "
        "in PA-29.",
        bloccante=True,
        letture=("0.05", "0.10"),
    ),
    "REV-13": PuntoAperto(
        "REV-13",
        ("DEF-32", "ESCL-12", "DEF-03"),
        "DEF-32 dice che ogni OHLC viene dal future, poi indica il CFD come "
        "fonte primaria su TF_H12/H6/H4/H1 con conferma del future. ESCL-12 "
        "vieta di confrontare i due.",
        bloccante=True,
        letture=("solo_future", "cfd_con_conferma_future"),
    ),
    "REV-14": PuntoAperto(
        "REV-14",
        ("DEF-32", "CTX-05", "SETUP-04"),
        "Ritardo di esecuzione: 'nessun ritardo prestabilito' (v1.6) contro "
        "'fino a 10 minuti, ogni backtest deve usare lo stesso ritardo'.",
        bloccante=False,
        default=0,
        motivo_default=(
            "La revisione v1.6 e' la piu' recente e CTX-05 la conferma: "
            "l'ingresso e' all'apertura di N3, il prima possibile, e la "
            "tollerabilita' del ritardo la decide rr >= 1.5, non un timer. "
            "Valore in minuti: 0 = nessun ritardo simulato."
        ),
    ),
    "REV-18": PuntoAperto(
        "REV-18",
        ("CTX-02", "RISK-13"),
        "La finestra news blocca tutti gli strumenti (CTX-02) o solo quello "
        "con la valuta coinvolta (RISK-13)?",
        bloccante=True,
        letture=("globale", "per_strumento"),
    ),
    "REV-17": PuntoAperto(
        "REV-17",
        ("CTX-01", "SETUP-15"),
        "Due elenchi di esclusioni che non coincidono. Quale e' normativo?",
        bloccante=True,
        letture=("ctx01", "setup15", "unione"),
    ),
    "REV-20": PuntoAperto(
        "REV-20",
        ("CTX-08", "CTX-10"),
        "All'avvio nessun timeframe e' mai stato ricalcolato dal sistema: "
        "CTX-08 dice di operare subito, CTX-10 lo vieta.",
        bloccante=True,
        letture=("opera_subito", "ricalcola_prima"),
    ),
    "REV-16": PuntoAperto(
        "REV-16",
        ("DEF-18", "DEF-03"),
        "Chiusura della candela TF_12M: 31 dicembre 24:00 UTC (DEF-18) o "
        "chiusura della sessione ETH (DEF-03)?",
        bloccante=True,
        letture=("31_dicembre_utc", "sessione_eth"),
    ),
    "REV-11": PuntoAperto(
        "REV-11",
        ("SETUP-10", "SETUP-05", "SETUP-15"),
        "SETUP-10 ammette un CRT su TF_H12/TF_H6, SETUP-05 non definisce per "
        "quei timeframe la condizione di allineamento che SETUP-15 pretende.",
        bloccante=True,
        letture=("crt_ammesso_su_h12_h6", "crt_vietato_su_h12_h6"),
    ),

    # --- non bloccanti, con default ragionevole ---------------------------
    "PA-46": PuntoAperto(
        "PA-46",
        ("GEST-04",),
        "buffer_be per strumento, in punti: copre spread e commissioni "
        "perche' il pareggio sia reale.",
        bloccante=False,
        default=0.0,
        motivo_default=(
            "Zero e' il valore neutro e dichiaratamente ottimistico: lo stop a "
            "pareggio chiudera' in leggera perdita per i costi. Va misurato "
            "sullo spread medio di ciascuno strumento sul conto demo."
        ),
    ),
    "PA-53": PuntoAperto(
        "PA-53",
        ("CTX-04",),
        "Aggiornamento annuale del calendario festivita', o calcolo "
        "automatico delle festivita' USA a data mobile.",
        bloccante=False,
        default=ANNO_DI_VALIDITA_FESTIVITA,
        motivo_default=(
            "La tabella FESTIVITA_MERCATO e' corretta per il 2026, verificata "
            "data per data. Il motore deve rifiutarsi di usarla in un anno "
            "diverso invece di operare in giorni sbagliati."
        ),
    ),
    "PA-55": PuntoAperto(
        "PA-55",
        ("CTX-02", "RISK-13"),
        "Comportamento se il calendario news non e' disponibile al momento "
        "della valutazione di un setup.",
        bloccante=False,
        default="astieniti",
        motivo_default=(
            "PRIN-99: in presenza di dati mancanti non si opera. Un trade "
            "saltato costa zero. E' l'unico default coerente con il documento."
        ),
    ),
    "PA-39": PuntoAperto(
        "PA-39",
        ("DEF-44",),
        "Se la divergenza RSI debba restare statistica o diventare operativa.",
        bloccante=False,
        default="solo_statistica",
        motivo_default=(
            "DEF-44 lo dice gia': 'La divergenza non e' condizione necessaria "
            "per l'ingresso' e 'non modifica alcuna decisione del bot'."
        ),
    ),
    "PA-49": PuntoAperto(
        "PA-49",
        ("GEST-12",),
        "Dove e con quale frequenza si salva lo stato delle posizioni.",
        bloccante=False,
        default="sqlite_tabella_posizione",
        motivo_default=(
            "L'archivio SQLite dell'impianto ha gia' la tabella `posizione` "
            "con stop, TP1 e target, scritta a ogni cambiamento."
        ),
    ),
    "PA-30": PuntoAperto(
        "PA-30",
        ("DEF-42", "CTX-01"),
        "Comportamento con mitigazione_attesa = NON_DETERMINATA.",
        bloccante=False,
        default="astieniti",
        motivo_default=(
            "Gia' risolto dai documenti: DEF-42 dice 'nessun ingresso e' "
            "ammesso su quel gap' e CTX-01 #10 lo elenca fra i filtri."
        ),
    ),
}


# ===========================================================================
# 9. Le tue scelte
# ===========================================================================

SCELTE: dict[str, Any] = {
    # Compila qui per sciogliere un punto aperto, con l'ID come chiave.
    # Ogni voce va accompagnata da una riga di commento che dice su quale
    # documento o decisione si basa, cosi' resta tracciabile.
    #
    # Esempi di forma, NON scelte fatte:
    #   "REV-10": "completa",     # deciso il gg/mm: DEF-01 corretta, resta la completa
    #   "PA-62": {"XAUUSD": 1.0, "EURUSD": 1.25, ...}
}


def richiedi(identificativo: str) -> Any:
    """Restituisce il valore deciso per un punto aperto.

    Ordine: prima `SCELTE`, poi il default se il punto non e' bloccante.
    Se il punto e' bloccante e non e' stato deciso, solleva.
    """
    if identificativo in SCELTE:
        return SCELTE[identificativo]

    punto = PUNTI_APERTI.get(identificativo)
    if punto is None:
        raise KeyError(f"punto aperto sconosciuto: {identificativo}")

    if not punto.bloccante:
        return punto.default

    letture = (
        f"\n  Letture possibili: {', '.join(punto.letture)}" if punto.letture else ""
    )
    raise PuntoApertoError(
        f"\n{punto.identificativo} non e' stato deciso."
        f"\n  Regole coinvolte: {', '.join(punto.regole)}"
        f"\n  {punto.descrizione}{letture}"
        f"\n  Per sciogliere: aggiungi \"{punto.identificativo}\" a SCELTE in "
        f"core/parametri.py, oppure aggiorna il documento che lo genera."
    )


def deciso(identificativo: str) -> bool:
    """True se il punto e' stato deciso o ha un default utilizzabile."""
    if identificativo in SCELTE:
        return True
    punto = PUNTI_APERTI.get(identificativo)
    return punto is not None and not punto.bloccante


def bloccanti_non_decisi() -> list[str]:
    """Elenco dei punti che oggi fermerebbero il motore."""
    return sorted(
        identificativo
        for identificativo, punto in PUNTI_APERTI.items()
        if punto.bloccante and identificativo not in SCELTE
    )


# ===========================================================================
# 10. Accessori sui punti contesi
# ===========================================================================
# Ognuno di questi restituisce un valore solo dopo che il punto e' stato
# deciso. Sono qui, e non nella logica, proprio perche' la logica non possa
# scegliere di nascosto.


def gerarchia() -> tuple[TF, ...]:
    """Gerarchia dei timeframe da usare (DEF-01, contesa: REV-10)."""
    scelta = richiedi("REV-10")
    if scelta == "completa":
        return GERARCHIA_COMPLETA
    if scelta == "ridotta":
        return GERARCHIA_RIDOTTA
    raise PuntoApertoError(f"REV-10: lettura non riconosciuta: {scelta!r}")


def ordine_scansione_gap() -> tuple[TF, ...]:
    """Ordine di scansione del gap attivo (DEF-13, contesa: REV-15)."""
    scelta = richiedi("REV-15")
    if scelta == "senza_h12_h6":
        return TF_BIAS
    if scelta == "con_h12_h6":
        return TF_BIAS + TF_SOLO_GAP
    raise PuntoApertoError(f"REV-15: lettura non riconosciuta: {scelta!r}")


def soglia_corpo_indecisione() -> float:
    """Soglia del corpo per DEF-41 (contesa: REV-32, PA-29)."""
    scelta = richiedi("REV-32")
    if scelta in ("0.05", 0.05):
        return SOGLIA_CORPO_INDECISIONE_TESTO_DEF41
    if scelta in ("0.10", 0.10):
        return SOGLIA_CORPO_INDECISIONE_PA29
    raise PuntoApertoError(f"REV-32: lettura non riconosciuta: {scelta!r}")


def rischio_per_posizione(n: int, strumento: str) -> float:
    """Rischio per singola posizione secondo RISK-01, RISK-02 e RISK-06.

    Due punti contesi entrano qui: se XAUUSD segua la scala (REV-03) e se le
    posizioni aperte vengano ridimensionate (REV-42). Il secondo non cambia
    questo valore ma cambia l'esposizione totale, quindi va deciso prima che
    il motore apra alcunche'.
    """
    if n < 1:
        raise ValueError(f"n deve essere almeno 1, ricevuto {n}")
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")

    # REV-42 va sciolto comunque: senza, non so quale sia l'esposizione reale.
    richiedi("REV-42")

    if not UNIVERSO[strumento].deriva_direzione_dal_dxy:
        # XAUUSD: RISK-02 lo esclude, RISK-06 lo include.
        scelta = richiedi("REV-03")
        if scelta == "rischio_pieno_risk01":
            return RISCHIO_BASE
        if scelta != "scala_risk02":
            raise PuntoApertoError(f"REV-03: lettura non riconosciuta: {scelta!r}")

    return SCALA_RISCHIO.get(n, SCALA_RISCHIO_DA_3_IN_SU)


def fattore_conversione_punto(strumento: str) -> float:
    """Fattore `k` fra punto future e punto CFD (DEF-47, RISK-03, PA-62)."""
    tabella = richiedi("PA-62")
    if strumento not in tabella:
        raise PuntoApertoError(
            f"PA-62: manca il fattore k per {strumento}. "
            "Va misurato una volta per ciascuno dei sei strumenti."
        )
    return float(tabella[strumento])


def calendario_festivita_valido_per(anno: int) -> dict[tuple[int, int], str]:
    """Festivita' di CTX-04, solo se la tabella vale per quell'anno (PA-53)."""
    if anno != richiedi("PA-53"):
        raise PuntoApertoError(
            f"PA-53: FESTIVITA_MERCATO vale per il {ANNO_DI_VALIDITA_FESTIVITA}, "
            f"non per il {anno}. Sei delle dodici date sono mobili. "
            "Aggiorna la tabella o sostituiscila con il calcolo automatico."
        )
    return FESTIVITA_MERCATO


# ===========================================================================
# 11. Verifica interna
# ===========================================================================


def verifica() -> None:
    """Controlla la coerenza interna di questo file. Non tocca i documenti."""
    # Le gerarchie contengono solo timeframe validi e senza ripetizioni.
    for nome, gerarchia_ in (("completa", GERARCHIA_COMPLETA), ("ridotta", GERARCHIA_RIDOTTA)):
        assert len(set(gerarchia_)) == len(gerarchia_), f"gerarchia {nome} con ripetizioni"
        assert all(isinstance(tf, TF) for tf in gerarchia_), f"gerarchia {nome} con TF ignoti"

    # La ridotta e' un sottoinsieme ordinato della completa.
    assert set(GERARCHIA_RIDOTTA) < set(GERARCHIA_COMPLETA)
    assert set(GERARCHIA_COMPLETA) - set(GERARCHIA_RIDOTTA) == set(TF_SOLO_GAP)

    # Ogni timeframe compare in esattamente un ruolo di bias/gap.
    assert set(TF_BIAS) | set(TF_SOLO_GAP) | {TF.H4, TF.H1} == set(TF)
    assert not (set(TF_BIAS) & set(TF_SOLO_GAP))

    # DEF-46 copre tutti i timeframe di bias ed esecuzione, e solo quelli.
    assert set(TARGET_DI) == set(TF) - set(TF_SOLO_GAP)
    # E il target di un TF e' davvero quello immediatamente superiore nella
    # gerarchia ridotta: e' cio' che DEF-46 dichiara di essere.
    for tf, superiore in TARGET_DI.items():
        if superiore is None:
            assert tf is TF.M12, f"solo TF_12M puo' non avere superiore, non {tf}"
            continue
        indice = GERARCHIA_RIDOTTA.index(tf)
        assert GERARCHIA_RIDOTTA[indice - 1] is superiore, f"{tf}: atteso {superiore}"

    # SETUP-05: i due TF superiori sono davvero superiori nella ridotta.
    for tf, (primo, secondo) in DUE_TF_SUPERIORI.items():
        indice = GERARCHIA_RIDOTTA.index(tf)
        assert GERARCHIA_RIDOTTA[indice - 1] is primo, f"{tf}: atteso {primo}"
        assert GERARCHIA_RIDOTTA[indice - 2] is secondo, f"{tf}: atteso {secondo}"

    # Frazioni di SETUP-13 e GEST-07.
    assert abs(FRAZIONE_CHIUSA_A_TP1 + FRAZIONE_RESIDUA - 1.0) < 1e-9

    # Limiti di perdita crescenti (RISK-07 < RISK-08 < RISK-09).
    assert LIMITE_GIORNALIERO < LIMITE_SETTIMANALE < LIMITE_MENSILE

    # Scala del rischio decrescente (RISK-02).
    assert SCALA_RISCHIO[1] > SCALA_RISCHIO[2] > SCALA_RISCHIO_DA_3_IN_SU

    # Universo: solo XAUUSD non deriva dal DXY (PRIN-09).
    non_dxy = [s for s, d in UNIVERSO.items() if not d.deriva_direzione_dal_dxy]
    assert non_dxy == ["XAUUSD"], non_dxy
    # Solo 6J e 6S hanno segno invertito (DEF-33).
    invertiti = sorted(d.future for d in UNIVERSO.values() if d.segno_invertito)
    assert invertiti == ["6J", "6S"], invertiti

    # SETUP-19 copre le cinque coppie e nessun'altra.
    coppie = {s for s, d in UNIVERSO.items() if d.deriva_direzione_dal_dxy}
    assert set(DIREZIONE_DA_BIAS_DXY["LONG"]) == coppie
    assert set(DIREZIONE_DA_BIAS_DXY["SHORT"]) == coppie
    assert DIREZIONE_DA_BIAS_DXY["NESSUNA"] == {}
    # LONG e SHORT sono l'una l'opposta dell'altra.
    for coppia in coppie:
        assert DIREZIONE_DA_BIAS_DXY["LONG"][coppia] != DIREZIONE_DA_BIAS_DXY["SHORT"][coppia]

    # Festivita': date esistenti nel calendario.
    for mese, giorno in FESTIVITA_MERCATO:
        assert 1 <= mese <= 12 and 1 <= giorno <= 31, (mese, giorno)

    # I punti aperti sono coerenti con la propria dichiarazione.
    for identificativo, punto in PUNTI_APERTI.items():
        assert identificativo == punto.identificativo
        assert punto.regole, f"{identificativo} non cita alcuna regola"
        assert punto.descrizione, f"{identificativo} senza descrizione"
        if punto.bloccante:
            assert punto.default is None, f"{identificativo} bloccante ma con default"
        else:
            assert punto.motivo_default, f"{identificativo} ha un default senza motivo"


if __name__ == "__main__":
    verifica()
    bloccanti = bloccanti_non_decisi()
    print("parametri.py — verifica interna superata")
    print(f"punti aperti censiti: {len(PUNTI_APERTI)}")
    print(f"bloccanti non ancora decisi: {len(bloccanti)}")
    for identificativo in bloccanti:
        punto = PUNTI_APERTI[identificativo]
        print(f"  {identificativo:8} {', '.join(punto.regole)}")
