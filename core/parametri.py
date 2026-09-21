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
from datetime import date, timedelta
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
    # --- Sotto l'ora: le coppie intraday di Romeo (CRT-04) ----------------
    #
    # DEF-01 dichiarava dieci timeframe e vietava di citarne altri. Quel
    # vincolo e' stato sollevato, e la ragione sta in un numero: il bot
    # produceva 413 segnali in vent'anni, Romeo ne apre cinque o sei AL
    # GIORNO. Fattore cento.
    #
    # La causa era che quattro delle sue sette coppie sono intraday —
    # `1h -> 5m`, `15m -> 1m`, `4h -> 15m`, `5m -> 15s` — e senza questi
    # timeframe il bot poteva usare solo le tre piu' lente. Non era una
    # configurazione da aggiustare: era un'altra strategia.
    MIN15 = "TF_M15"
    MIN5 = "TF_M5"
    MIN1 = "TF_M1min"


# DEF-01 contiene DUE gerarchie diverse, a diciassette righe di distanza.
# Non scelgo io quale: vedi REV-10 e `gerarchia()` piu' sotto.
# I timeframe intraday chiudono entrambe le gerarchie, sotto l'ora, dove
# stanno per durata. Senza di essi ogni confronto di altezza — `_piu_alto`,
# `timeframe_crt_ammesso`, l'estensione del target di GEST-08 — solleva
# `ValueError: x not in tuple` appena il motore incontra una candela a 15
# minuti. Sono nella gerarchia perche' vanno ORDINATI, non perche' abbiano
# acquisito i ruoli dei timeframe alti: la bias resta a TF_BIAS e il target
# di DEF-46 a TARGET_DI, che li escludono entrambi.
GERARCHIA_COMPLETA: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H12, TF.H6, TF.H4, TF.H1,
    TF.MIN15, TF.MIN5, TF.MIN1,
)
GERARCHIA_RIDOTTA: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H4, TF.H1,
    TF.MIN15, TF.MIN5, TF.MIN1,
)

# Ruoli dichiarati da DEF-01 e PRIN-10.
TF_BIAS: Final[tuple[TF, ...]] = (TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1)

# I timeframe sotto l'ora. Servono SOLO come timeframe di ingresso delle
# coppie intraday di CRT-04: non producono bias (DEF-16 parla di accettazione
# e rifiuto su orizzonti dove una candela e' un fatto, non rumore) e non hanno
# un target di DEF-46. Sono il posto dove si entra, non dove si decide.
TF_INTRADAY: Final[tuple[TF, ...]] = (TF.MIN15, TF.MIN5, TF.MIN1)
TF_SOLO_GAP: Final[tuple[TF, ...]] = (TF.H12, TF.H6)
TF_ESECUZIONE: Final[tuple[TF, ...]] = (TF.D1, TF.H4, TF.H1)

# DEF-36 elenca sei timeframe per i key level e si ferma a `TF_1D`. SETUP-05
# pero' scrive una riga per `TF_H1` che pretende lo sbilanciamento di un key
# level di `TF_H4`, e PRIN-10 mette `TF_H1` fra i timeframe di esecuzione.
# Le tre cose insieme non stanno in piedi: senza key level su `TF_H4` quella
# riga non e' soddisfabile e `TF_H1` non e' eseguibile (REV-48).
#
# Adottata la lettura che le tiene tutte: i key level si calcolano anche su
# `TF_H4`, con la stessa formula di DEF-36 sulla sua `C1`. `TF_H12` e `TF_H6`
# restano fuori (DEF-31, REV-11).
#
# `TF_H1`, `TF_M15` e `TF_M5` ne producono per la STESSA ragione, che prima
# era scritta al contrario: la riga diceva "TF_H1 non ne produce di propri,
# perche' sotto di lui non c'e' nessun trigger". Era vero quando `TF_H1` era
# il trigger piu' basso. Oggi `COPPIE_CRT` ha `H1 -> M5` e `M15 -> M1min`:
# sotto `TF_H1` ci sono tre trigger, e senza key level propri quei timeframe
# non hanno NIENTE da spazzare.
#
# La conseguenza era pesante e silenziosa: `SETUP-02` vuole che `N2` prenda
# un key level di timeframe strettamente superiore, quindi un CRT su un
# minuto doveva andare a spazzare un livello a quattro ore. Misurato il
# 2026-09-21: 33 decisioni su 40 fermate da `SETUP-00` -- "nessun CRT
# valido: serve la presa di un key level di timeframe superiore" -- che
# sembrava selettivita' della strategia ed era una tabella mai estesa.
#
# `TF_M1min` resta fuori: sotto di lui non c'e' nessun trigger, e stavolta
# e' vero.
TF_KEY_LEVEL: Final[tuple[TF, ...]] = TF_BIAS + (TF.H4, TF.H1, TF.MIN15, TF.MIN5)

# DEF-22 passo 1: ordine di scansione per il target direzionale globale.
# Nota: salta TF_H12 e TF_H6, coerentemente con DEF-28.
ORDINE_SCANSIONE_TARGET: Final[tuple[TF, ...]] = (
    TF.M12, TF.M6, TF.M3, TF.M1, TF.W1, TF.D1, TF.H4, TF.H1,
)

# DEF-46: target di un singolo timeframe = key level del TF immediatamente
# superiore. TF_12M e' il caso speciale: usa il target globale di DEF-22.
#
# I tre intraday puntano a `TF_H4` per la stessa ragione per cui ci punta
# `TF_H1`: sotto le quattro ore nessun timeframe produce key level propri
# (`TF_KEY_LEVEL` qui sopra), quindi il primo disponibile e' quello.
#
# Mancavano, e mancare qui non fa rumore: `target_iniziale` restituisce None,
# il motore applica `PRIN-99` -- "una posizione senza bersaglio non ha ragione
# di essere aperta" -- e non si apre. Mai, qualunque cosa dicano tutte le
# altre regole. Questa tabella e' stata scritta quando il bot operava da
# `TF_H1` in su, e nessuno l'ha estesa quando `M15`, `M5` e `M1min` sono
# diventati timeframe di innesco: da allora meta' delle coppie di `CRT-04`
# non poteva produrre un ordine nemmeno con ogni filtro spento.
#
# Trovato il 2026-09-21 accendendo il modo diagnostico che apre su ogni CRT:
# quattro CRT superavano tutto e morivano qui, su `SETUP-14` e `PRIN-99`.
TARGET_DI: Final[dict[TF, Optional[TF]]] = {
    TF.MIN1: TF.H4,
    TF.MIN5: TF.H4,
    TF.MIN15: TF.H4,
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

# Quanti giorni puo' essere vecchio l'archivio del DXY prima che la sua bias
# smetta di valere. DEF-26 conta le candele e non guarda la data: una serie
# ferma a quarantasette giorni fa ne ha in abbondanza, quindi una bias la
# produce, e SETUP-19 ci fa passare o bloccare ogni operazione su cinque
# coppie su sei. E' successo davvero, in silenzio, perche' un archivio
# vecchio e uno aggiornato hanno lo stesso aspetto dal conteggio.
#
# Sei giorni, e la soglia va scelta guardando il calendario vero del forex,
# non a occhio. La chiusura piu' lunga e' il fine settimana: venerdi' 22:00
# UTC fino a domenica 22:00, cioe' due giorni. A Natale e Capodanno il ponte
# con il fine settimana puo' arrivare a quattro giorni e mezzo.
#
# Con quattro giorni -- il primo valore che avevo scritto -- il bot si
# sarebbe zittito da solo il 28 dicembre, senza che niente fosse rotto. Con
# sei c'e' un giorno e mezzo di margine sopra la chiusura piu' lunga che
# esista, e un guasto vero lo supera comunque: l'archivio non aggiornato che
# ha fatto nascere questo parametro era indietro di quarantasette giorni.
RITARDO_MASSIMO_DXY_GIORNI: Final[int] = 6

# Lo stesso, per l'archivio dello strumento su cui si opera. E qui la posta
# e' molto piu' alta che sul DXY, dove un ritardo degrada un filtro: qui
# degrada l'ordine.
#
# Il motore cerca il CRT sulle candele in archivio e manda l'ordine al broker
# al prezzo CORRENTE. Con un archivio fermo a due settimane prima, stop e
# bersaglio nascono da livelli vecchi di due settimane mentre l'ingresso
# avviene oggi: un'operazione costruita su un grafico e aperta su un altro.
# Niente in DEF-26 lo impedisce, perche' DEF-26 conta le candele e non ne
# guarda la data -- e l'archivio di una macchina a cui la fonte ha chiuso la
# porta ne ha in abbondanza.
#
# Misurato sulla VPS il 2026-09-17: i sei strumenti fermi al 31 agosto, 16
# giorni prima, con il bot pronto a operare e nessun segno che qualcosa non
# andasse.
#
# Cinque giorni, per la stessa ragione dei sei del DXY: la chiusura piu'
# lunga che il forex conosce e' il ponte di Natale, circa quattro giorni e
# mezzo. Sotto si avrebbero falsi allarmi a fine dicembre; sopra si lascia
# passare un'avaria vera. Non e' una soglia fine -- non protegge da un
# ritardo di un giorno -- ma coglie il caso in cui la fonte ha smesso di
# rispondere, che e' quello che succede davvero.
RITARDO_MASSIMO_ARCHIVIO_GIORNI: Final[int] = 5

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

# DEF-47 come corretta in DECISIONI-2026-09-03 (PA-62).
#
# La distanza di stop si misura sul future in forma ADIMENSIONALE:
#     r = |chiusura_N2_future - stop_future| / chiusura_N2_future
# e si applica al prezzo CFD:
#     distanza_cfd = r * prezzo_cfd_corrente
#
# Nessun prezzo future viene confrontato con un prezzo CFD (ESCL-12): `r` e'
# un numero puro. Il fattore `k` costante previsto da DEF-47 non puo'
# esistere per `6J` e `6S`, che quotano il reciproco del rispettivo CFD: la
# derivata di 1/x non e' costante, quindi nessun `k` sarebbe corretto per piu'
# di un istante.
METODO_SIZE: Final[str] = "distanza_relativa"

# GEST-04, buffer del break even (PA-46). Letto dallo spread al momento, non
# fissato per strumento: uno spread cambia, un numero in tabella no.
BUFFER_BE_MOLTIPLICATORE_SPREAD: Final[float] = 2.0

# DEF-32 / CTX-05 come corrette (REV-14): nessun ritardo di esecuzione.
RITARDO_ESECUZIONE_MINUTI: Final[int] = 0

# PA-54: il calendario news e' un file locale, letto a ogni valutazione.
# Se manca, e' vuoto o e' piu' vecchio di questa soglia, si applica PA-55.
PERCORSO_CALENDARIO_NEWS: Final[str] = "dati/news.csv"
ETA_MASSIMA_CALENDARIO_ORE: Final[int] = 24


# ===========================================================================
# 6. Contesto e calendario (02_contesto.md)
# ===========================================================================

# CTX-02 e RISK-13: finestra di blocco attorno alle news a 3 stelle.
FINESTRA_NEWS_MINUTI_PRIMA: Final[int] = 30
FINESTRA_NEWS_MINUTI_DOPO: Final[int] = 30
NEWS_IMPATTO_MINIMO_STELLE: Final[int] = 3

# CTX-06 e DEF-32: latenza tollerata del solo dato DXY.
LATENZA_DXY_MINUTI: Final[int] = 10

# CTX-04, festivita' di mercato. PA-53 chiedeva se aggiornare la tabella ogni
# anno o calcolarla: calcolata (vedi DECISIONI-2026-09-03, sezione Misure).
# Sei date su dodici sono mobili, e una tabella fissa scade il 1 gennaio.


def _pasqua(anno: int) -> date:
    """Domenica di Pasqua, algoritmo gregoriano anonimo (computus)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lu = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lu) // 451
    mese, giorno = divmod(h + lu - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def _nesimo(anno: int, mese: int, giorno_settimana: int, n: int) -> date:
    """N-esimo giorno della settimana del mese. 0 = lunedi'."""
    primo = date(anno, mese, 1)
    scarto = (giorno_settimana - primo.weekday()) % 7
    return primo + timedelta(days=scarto + 7 * (n - 1))


def _ultimo(anno: int, mese: int, giorno_settimana: int) -> date:
    """Ultimo giorno della settimana del mese. 0 = lunedi'."""
    giorno = date(anno, mese, 28)
    while (giorno + timedelta(days=7)).month == mese:
        giorno += timedelta(days=7)
    return giorno - timedelta(days=(giorno.weekday() - giorno_settimana) % 7)


def _osservata(giorno: date) -> date:
    """Festivita' a data fissa che cade nel fine settimana: si sposta.

    Sabato -> venerdi' precedente, domenica -> lunedi' successivo. E' la
    regola di osservanza degli exchange statunitensi.
    """
    if giorno.weekday() == 5:
        return giorno - timedelta(days=1)
    if giorno.weekday() == 6:
        return giorno + timedelta(days=1)
    return giorno


def festivita_mercato(anno: int) -> dict[date, str]:
    """Le chiusure di CTX-04, calcolate per l'anno richiesto.

    Sono dodici voci, ma le **date distinte** possono essere undici: quando
    Natale cade di sabato l'osservanza scivola al 24 dicembre e si sovrappone
    alla Vigilia. In quel caso la data porta entrambe le etichette.

    Un caso simile riguarda il Capodanno: se il 1 gennaio cade di sabato,
    l'osservanza e' il 31 dicembre dell'anno **precedente**, quindi la data
    restituita puo' cadere fuori da `anno`. Per sapere se un giorno qualsiasi
    e' festivo usa `e_festivita()`, che tiene conto del confine.
    """
    pasqua = _pasqua(anno)
    thanksgiving = _nesimo(anno, 11, 3, 4)          # 4 = giovedi'
    voci: list[tuple[date, str]] = [
        (_osservata(date(anno, 1, 1)), "Capodanno"),
        (_nesimo(anno, 1, 0, 3), "Martin Luther King Day"),
        (_nesimo(anno, 2, 0, 3), "Presidents' Day"),
        (pasqua - timedelta(days=2), "Venerdi' Santo"),
        (_ultimo(anno, 5, 0), "Memorial Day"),
        (_osservata(date(anno, 6, 19)), "Juneteenth"),
        (_osservata(date(anno, 7, 4)), "Independence Day"),
        (_nesimo(anno, 9, 0, 1), "Labor Day"),
        (thanksgiving, "Thanksgiving"),
        (thanksgiving + timedelta(days=1), "Giorno dopo Thanksgiving"),
        (date(anno, 12, 24), "Vigilia di Natale"),
        (_osservata(date(anno, 12, 25)), "Natale"),
    ]

    calendario: dict[date, str] = {}
    for giorno, nome in voci:
        # Due festivita' sullo stesso giorno: il giorno resta uno, le ragioni
        # sono due. Perderne una renderebbe illeggibile il motivo del blocco.
        calendario[giorno] = f"{calendario[giorno]} / {nome}" if giorno in calendario else nome
    return calendario


def e_festivita(giorno: date) -> Optional[str]:
    """Nome della festivita' se il giorno e' di chiusura, altrimenti None.

    Interroga il calendario dell'anno del giorno e quello dell'anno dopo,
    perche' l'osservanza del Capodanno puo' ricadere nel dicembre precedente.
    """
    for anno in (giorno.year, giorno.year + 1):
        nome = festivita_mercato(anno).get(giorno)
        if nome is not None:
            return nome
    return None


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

# RISK-02 come corretta (REV-03): `n` si conta dentro il gruppo di
# correlazione, non sull'intero portafoglio.
GRUPPI_CORRELAZIONE: Final[dict[str, tuple[str, ...]]] = {
    "forex_dxy": ("EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY"),
    "oro": ("XAUUSD",),
}


def gruppo_di(strumento: str) -> str:
    """Gruppo di correlazione a cui appartiene lo strumento (RISK-02, REV-03)."""
    for nome, membri in GRUPPI_CORRELAZIONE.items():
        if strumento in membri:
            return nome
    raise ValueError(f"strumento fuori da PRIN-08: {strumento}")


# ===========================================================================
# CRT-12 — le coppie su cui si cerca la divergenza SMT
# ===========================================================================
#
# SMT = Smart Money Technique/Tool. Due strumenti che di norma si muovono
# insieme; quando uno fa un nuovo estremo e l'altro no, la divergenza dice
# che la spinta non e' sostenuta.
#
# Il segno conta ed e' la meta' del lavoro. `6E` e `6B` salgono insieme:
# divergenza significa che uno fa un nuovo MASSIMO e l'altro no. `6E` e `6S`
# si muovono al contrario: la controparte di un nuovo massimo su `6E` e' un
# nuovo MINIMO su `6S`, e la divergenza e' che quel minimo non arriva.
#
# Il verso e' espresso col segno degli strumenti gia' dichiarato in UNIVERSO
# (`segno_invertito`): due strumenti hanno correlazione positiva se hanno lo
# stesso segno, negativa se lo hanno diverso. Non e' un'assunzione libera,
# e' la stessa proprieta' che DEF-33 usa per convertire le direzioni.
#
# Il DXY sta a parte: correla negativamente con tutte e cinque le coppie che
# quotano il dollaro al denominatore e positivamente con le due che lo
# quotano al numeratore. Non e' nell'UNIVERSO (PRIN-08) ma e' in archivio.
# Su quante candele si cerca il nuovo estremo. Venti e' la lunghezza su cui
# le fonti descrivono lo sweep di un "pool di liquidita' significativo": meno
# e ogni oscillazione conta come nuovo estremo, molto di piu' e nessuno sweep
# ordinario lo e'. Non e' ottimizzata su dati, ed e' bene che si sappia.
FINESTRA_SMT: Final[int] = 20

# CRT-19/CRT-20 — quanto devono pesare le ombre di N2 perche' il CRT valga.
# Le ombre piccole danno 33,6% di winrate contro il 59,6% della base: uno
# sweep "pulito" e' un cattivo segno per un'operazione di mean-reversion.
# Taglio grossolano, non ottimizzato finemente.
PESO_OMBRE_MINIMO: Final[float] = 0.6

# CRT-13 — si entra come Romeo, sul ritorno nell'FVG dal timeframe basso,
# invece che alla chiusura della candela di range.
#
#   ingresso alla chiusura di N2    winrate 30,8%   -0,0782 R
#   ingresso di ROMEO (CRT-13)      winrate 62,4%   +0,3613 R
#
# Il winrate raddoppia perche' il prezzo di ingresso e' molto migliore. E'
# la differenza piu' grande misurata in tutto il progetto, e non e' una
# regolazione: e' un'altra operazione.
#
# A False il motore torna a ordinare alla chiusura del range — piu' semplice
# e misurato peggio. Resta commutabile perche' l'ingresso di Romeo richiede
# dati sul timeframe basso, e dove non ci sono e' meglio un ingresso
# mediocre che nessuno.
INGRESSO_ROMEO: Final[bool] = True

# ===========================================================================
# Le conferme di Romeo: quali si applicano
# ===========================================================================
#
# Ogni voce e' una regola delle fonti. Tutte accese significa "la strategia
# per intero", ed e' il valore predefinito perche' e' cio' che la strategia
# chiede.
#
# La colonna che conta e' la MISURA, presa su prezzi veri Dukascopy con BID e
# ASK (docs/MISURA-REGOLE-MANCANTI-2026-09-16.md):
#
#   CRT-11  CISD              +3,0 sigma sopra la base.  REGGE.
#   CRT-20  ombre di N2       le piccole danno 33,6% di winrate contro 59,6%.
#                             Il filtro evita le peggiori. REGGE dal lato
#                             negativo: serve a non fare la cosa sbagliata.
#   CRT-12  divergenza SMT    +0,5 / -0,6 sigma. Le fonti la dichiarano non
#                             negoziabile, i dati non mostrano nulla.
#   CRT-10  double purge      88,7% di winrate e R NEGATIVA. La variante
#                             concorde e' PEGGIO della base (-1,4 sigma).
#   CRT-15  finestre orarie   nessuna differenza (+0,0 / -0,2 sigma).
#   CRT-17  meta' del range   la prima misura era un lookahead; corretta,
#                             sparisce sotto i 30 campioni.
#   CRT-18  meta' dell'ombra  mai misurata da sola.
#   CRT-06  modelli allineati mai misurata.
#
# Chi spegne una voce sa cosa sta spegnendo. Chi le lascia tutte accese ha la
# strategia di Romeo per intero, e paga quello che le misure dicono che costa.
# ===========================================================================
# Le conferme di Romeo: TUTTE si applicano, ma non tutte sono veti
# ===========================================================================
#
# ATTENZIONE, perche' il nome precedente di questa tabella traeva in inganno.
#
# **Tutte e otto le regole di Romeo vengono valutate su OGNI setup, sempre.**
# Il loro verdetto — si, no, non valutabile — finisce nel `responso`, che
# viaggia nella Decisione fino al dossier, e il dossier e' cio' che arriva al
# trader discrezionale. Nessuna regola e' spenta e nessuna viene saltata.
#
# Questa tabella dice un'altra cosa: **quali possono uccidere l'operazione DA
# SOLE**, prima che qualcuno la guardi.
#
# Applicarle tutte come veti automatici in AND non e' la strategia di Romeo:
# e' una caricatura. `CRT-14` dice testualmente *"non si prende ogni istanza,
# il contesto decide quali istanze valgono"* — cioe' che le conferme vanno
# pesate insieme, non subite una per una.
#
# E la misura lo conferma: come veti in AND, su 360 valutazioni dell'archivio
# reale si trovano 18 CRT e se ne bloccano 18. Il bot tace del tutto. Non e'
# rigore, e' paralisi.
#
# `CRT-20` e' l'unico veto automatico perche' e' l'unico misurato come tale:
# con l'ingresso di CRT-13 porta il winrate dal 57,4% al 62,4%. Le altre
# parlano al giudice, che e' il posto dove Romeo stesso le mette.
CONFERME_CHE_BLOCCANO_DA_SOLE: Final[dict[str, bool]] = {
    # Spenta il 2026-09-21, per decisione esplicita dell'utente.
    #
    # Era l'ultima delle otto ancora attiva come veto, e da sola fermava il
    # 49% dei CRT: misurato su `D1 -> H1`, sei strumenti, 1,6 anni, 146 su
    # 298. Dietro di lei RISK-05 ne aspettava altri 127, e il risultato era
    # zero operazioni -- non poche: zero, su ogni coppia e su tutto lo
    # storico.
    #
    # Il numero che la difendeva resta vero e va ricordato: con ombre piccole
    # su N2 il winrate misurato e' 33,6% contro il 59,6% della base. Spegnerla
    # NON e' una correzione, e' una scelta operativa -- si accettano setup che
    # la misura dice peggiori, in cambio di un bot che apre. Per rimetterla
    # basta riportare True qui.
    #
    # Continua a essere VALUTATA e a comparire nel responso: chi legge una
    # decisione vede lo stesso cosa diceva CRT-20, e il giudizio discrezionale
    # la pesa insieme alle altre. Cambia solo che non ferma da sola.
    "CRT-20": False,  # peso delle ombre di N2 — misurato come veto
    "CRT-06": False,  # tre modelli CRT allineati
    "CRT-10": False,  # Double Purge Sweep
    "CRT-11": False,  # CISD — gia' INTRINSECO all'ingresso di CRT-13
    "CRT-12": False,  # divergenza SMT
    "CRT-15": False,  # finestre orarie di New York
    "CRT-17": False,  # tenuta della meta' del range
    "CRT-18": False,  # punto medio dell'ombra
}

# Il vecchio nome, perche' il codice che lo usa continui a funzionare.
CONFERME_ROMEO = CONFERME_CHE_BLOCCANO_DA_SOLE


def blocca_da_sola(regola: str) -> bool:
    """Questa conferma puo' fermare l'operazione SENZA che nessuno la valuti?

    Non e' "la regola si applica": quello lo fanno tutte, sempre. E' "questa
    regola e' un veto automatico". Le altre parlano al giudice.
    """
    if regola not in CONFERME_CHE_BLOCCANO_DA_SOLE:
        raise ValueError(f"conferma non riconosciuta: {regola}")
    return CONFERME_CHE_BLOCCANO_DA_SOLE[regola]


# Il vecchio nome. Diceva "attiva" per una cosa che significa "blocca", ed e'
# la ragione per cui sembrava che meta' delle regole fosse spenta.
conferma_attiva = blocca_da_sola

# ===========================================================================
# CRT-04 — le coppie di timeframe canoniche
# ===========================================================================
#
# Un CRT si legge SEMPRE su due timeframe: il range sta sull'alto, lo sweep e
# l'ingresso sul basso. Non sono tre candele dello stesso timeframe — quella
# lettura era in SETUP-01 fino a REV-50 ed e' un'altra strategia.
#
# Le coppie sono quelle delle fonti, verbatim. Quelle sotto l'ora richiedono
# dati a 15 secondi e a 1 minuto che l'archivio non ha, e sono qui lo stesso:
# il giorno in cui i dati arrivano, l'elenco non va indovinato di nuovo.
#
# `W1 -> H4` merita una riga a parte. Il risultato migliore che avevo
# riportato era su `W1 -> D1`, che **non e' una coppia delle fonti**: quel
# numero riguardava una strategia che nessuno ha descritto.
COPPIE_CRT: Final[dict[TF, TF]] = {
    TF.M1: TF.D1,      # mensile     -> giornaliero
    TF.W1: TF.H4,      # settimanale -> 4 ore
    TF.D1: TF.H1,      # giornaliero -> orario
    # Le intraday, dove Romeo opera davvero: e' da queste che vengono le
    # cinque o sei operazioni al giorno.
    TF.H4: TF.MIN15,   # 4 ore  -> 15 minuti
    TF.H1: TF.MIN5,    # 1 ora  -> 5 minuti
    TF.MIN15: TF.MIN1,  # 15 min -> 1 minuto
}

# ---------------------------------------------------------------------------
# CONFLITTO APERTO fra CRT-04 e DEF-01, da risolvere e non da aggirare.
#
# Le fonti danno sette coppie. Tre stanno qui sopra. Le altre quattro
# nominano timeframe che **DEF-01 non ammette**:
#
#     5m -> 15s      15m -> 1m      1h -> 5m      4h -> 15m
#
# DEF-01 dichiara dieci timeframe e dice che «nessun altro puo' essere citato
# da nessuna regola». Metterli in un enum sarebbe violare DEF-01 di nascosto;
# lasciarli fuori senza dirlo sarebbe perdere meta' della strategia.
#
# Stanno qui come stringhe, che e' esattamente cio' che sono finche' qualcuno
# non decide: o DEF-01 si allarga, oppure il bot opera dichiaratamente su un
# sottoinsieme del CRT. Non lo decido io.
# Resta fuori solo `5m -> 15s`: i 15 secondi richiedono i tick, non le
# candele, ed e' un livello di dati diverso — non una riga di configurazione.
COPPIE_CRT_FUORI_DEF01: Final[tuple[tuple[str, str], ...]] = (
    ("5m", "15s"),
)

# ===========================================================================
# CRT-15 — le finestre orarie
# ===========================================================================
#
# Ore di **New York**, non UTC: le fonti le scrivono cosi' e l'ora di New York
# cambia rispetto a UTC due volte l'anno. Convertirle qui una volta per tutte
# darebbe due finestre sbagliate per meta' anno.
#
# Le killzone che avevo misurato (Londra 3-6, New York 8:30-11:30) sono UN
# ALTRO insieme di finestre, preso dalla letteratura ICT generale e non da
# Romeo. Le sue non erano mai state provate.
#
# Ogni intervallo e' [inizio, fine), ore intere.
FINESTRE_CRT_NY: Final[dict[TF, tuple[tuple[int, int], ...]]] = {
    TF.H1: ((2, 4), (7, 9), (8, 10), (20, 22)),
    TF.H4: ((1, 9), (13, 21)),
}
FUSO_NEW_YORK: Final[str] = "America/New_York"

COMPAGNE_SMT: Final[dict[str, tuple[str, ...]]] = {
    # I partner naturali: stessa valuta forte contro dollaro.
    "EURUSD": ("GBPUSD", "AUDUSD", "USDCHF"),
    "GBPUSD": ("EURUSD", "AUDUSD", "USDCHF"),
    "AUDUSD": ("EURUSD", "GBPUSD"),
    "USDCHF": ("EURUSD", "USDJPY"),
    "USDJPY": ("USDCHF", "EURUSD"),
    # L'oro non ha compagne nell'universo: il suo riferimento e' il DXY, che
    # pero' non e' uno strumento operabile. Resta vuoto finche' non si decide
    # come trattarlo, e con l'elenco vuoto la divergenza non si cerca.
    "XAUUSD": (),
}


def correlazione_positiva(uno: str, altro: str) -> bool:
    """CRT-12 — I due strumenti si muovono nello stesso verso?

    Discende dal segno gia' dichiarato in `UNIVERSO`: `EURUSD` e `GBPUSD`
    quotano entrambi una valuta contro dollaro e salgono insieme; `EURUSD` e
    `USDCHF` quotano il dollaro da lati opposti e si muovono al contrario.

    E' la stessa proprieta' che DEF-33 usa per convertire le direzioni, letta
    per un altro scopo. Derivarla invece di scrivere una seconda tabella
    significa che non possono divergere.
    """
    if uno not in UNIVERSO or altro not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {uno} / {altro}")
    return UNIVERSO[uno].segno_invertito == UNIVERSO[altro].segno_invertito


# DEF-33: strumenti di sola analisi, mai operati.
DXY_TF_ALTI: Final[str] = "ICEUS"          # future ICE, per TF_1D e superiori
DXY_TF_BASSI: Final[str] = "CAPITALCOM:DXY"  # CFD, per TF_H12 e inferiori

# SETUP-19. Direzioni espresse in ordini **CFD**. Per gli strumenti a segno
# invertito va poi applicato DEF-33 per sapere quale CRT cercare sul future.
# Su quali timeframe di RANGE la bias del dollaro ferma DA SOLA un CRT?
#
# Non e' un interruttore acceso/spento: la regola vale, ma quanto pesa dipende
# da quanto dura l'operazione. La bias del dollaro si legge su giornaliero e
# superiori, e governa un movimento di ore o giorni. Un CRT su `H4` o `D1`
# vive dentro quell'orizzonte, quindi andargli contro e' andare contro il
# contesto che lo domina. Un CRT su `M5` vive dieci minuti: il dollaro, li',
# e' rumore che nessuna bias giornaliera predice.
#
# Sotto `TF_H4` la regola non sparisce -- viene calcolata, registrata e
# sottoposta al GIUDIZIO discrezionale, che la pesa insieme al resto del
# dossier. Se il giudizio non e' disponibile (spento, tetto di spesa
# esaurito, rete giu') l'obiezione REGGE e non si apre: e' PRIN-99, non
# sapere e' un no.
#
# La soglia e' una scelta, non una misura: nessuno ha misurato dove stia il
# confine. E' fissata a `TF_H4` perche' e' il range della configurazione su
# cui il progetto ha il suo unico numero positivo (`4h -> 15m`), quindi da li'
# in su si resta severi. Chi volesse restare severo ovunque aggiunge i
# timeframe bassi a questo insieme.
#
# Contesto della scelta, 2026-09-21: con RISK-05 assoluta ovunque, 251 CRT su
# 298 venivano fermati da lei su `D1 -> H1` e 306 su 617 su `W1 -> H4`, e in
# tutto lo storico non arrivava all'ingresso un solo setup.
RISK_05_BLOCCA_DA_SOLA: Final[frozenset] = frozenset({"TF_1M", "TF_1W", "TF_1D", "TF_H4"})

# SETUP-19. Direzioni espresse in ordini **CFD**. Vedi `RISK_05_BLOCCA` qui
# sopra per chi decide se questa tabella ferma davvero un ordine.
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
        letture=("per_gruppo_correlazione", "scala_risk02", "rischio_pieno_risk01"),
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
        letture=("dipende_dal_tipo_di_ingresso", "gap", "key_level"),
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
        letture=("uscita_lato_entrata_sequenziale",),
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
        default="calcolate",
        motivo_default=(
            "Calcolate da festivita_mercato(anno): sei date su dodici sono "
            "mobili e una tabella fissa scade il 1 gennaio. Il calcolo e' "
            "verificato contro la tabella 2026 scritta a mano in CTX-04."
        ),
    ),
    "PA-55": PuntoAperto(
        "PA-55",
        ("CTX-02", "RISK-13"),
        "Comportamento se il calendario news non e' disponibile al momento "
        "della valutazione di un setup.",
        bloccante=False,
        letture=("astieniti", "opera"),
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
    # Sciolti il 2026-09-03 su richiesta esplicita dell'autore.
    # Il ragionamento di ciascuna sta in docs/DECISIONI-2026-09-03.md.
    # Cambiare una riga qui cambia il comportamento del motore, e nient'altro.

    # --- RICOSTRUZIONI: la risposta era nei documenti -------------------
    "REV-10": "completa",                   # DEF-01, gerarchia residua rimossa
    "REV-42": "ridimensiona",               # RISK-02 v0.6, frase residua rimossa
    "REV-14": 0,                            # minuti; DEF-32 v1.6 + CTX-05
    "REV-13": "solo_future",                # ESCL-12 + PREC-05
    "REV-17": "unione",                     # PRIN-99 su due elenchi di divieti
    "REV-18": "per_strumento",              # CTX-02 lo qualifica gia'
    "REV-20": "ricalcola_prima",            # CTX-08 vieta l'attesa, non il calcolo
    "REV-16": "sessione_eth",               # DEF-03 conseguenza vincolante
    "REV-15": "con_h12_h6",                 # DEF-31 esplicita
    "REV-11": "crt_vietato_su_h12_h6",      # SETUP-05 regola batte esempio
    "REV-22": "due_tf_key_level",           # il blocco "Numero minimo" di SETUP-05
    "REV-23": "C1",                         # con C0 DEF-38 sarebbe vacua
    "REV-26": "crt_formato",                # "pattern" = CRT in 00_principi
    "REV-27": "tf_piu_alto",                # DEF-13 passo 2 + PREC-02
    "REV-28": "dipende_dal_tipo_di_ingresso",   # SETUP-09 vs SETUP-02
    "REV-29": "polarita",                   # DEF-42 valuta il gap alla formazione
    "REV-31": "tf_del_gap",                 # DEF-44 lo scrive come assegnazione
    "REV-43": "sorveglianza_tick",          # fasi 1-3; la fase 4 resta calcolo
    "PA-31": "rifiuto_semplice_senza_spike",    # il preambolo descriveva il forte
    "PA-05": "setup06_senza_dxy",           # PRIN-09: una regola in meno
    "PA-44": "tutto_categoria_c",           # regola di uscita di GIUD-01
    "PA-47": "nessuna_azione",              # GEST-06 lo dice gia'
    "PA-48": "ricalcola_target",            # modello di DEF-29
    "PA-51": "scade_non_si_recupera",       # modello di SETUP-16
    "PA-60": "nessun_conflitto_def46",      # DEF-46 formalizza i due target

    # --- GIUDIZI: i documenti tacciono, la scelta e' mia ----------------
    "REV-32": "0.05",                       # testo normativo, e piu' selettivo
    "REV-03": "per_gruppo_correlazione",    # l'oro correla con se' stesso
    "REV-30": "uscita_lato_entrata_sequenziale",   # il meno sicuro dei giudizi
    "PA-15": "solo_statistica",             # un filtro senza criterio non e' tale
    "PA-63": "non_aprire_la_nuova",         # RISK-11 + PRIN-99
    "PA-46": 2.0,                           # moltiplicatore dello spread corrente
    "PA-54": "file_locale",                 # dati/news.csv, nessuna rete

    # --- SCELTE DELL'AUTORE che si scostano dai documenti ---------------
    #
    # PA-55, deciso il 2026-09-17 su istruzione esplicita: *"Il calendario
    # deve restare senza aggiornamento obbligatorio ogni 24h, se non c'e'
    # calendario opera normalmente."*
    #
    # Il default era `astieniti`, ed era la lettura coerente con PRIN-99:
    # dati mancanti, nessuna operazione. Questa lettura la ribalta, e cosa
    # comporta va scritto qui e non lasciato scoprire dopo.
    #
    # `CTX-02` vieta di aprire dentro la finestra di una news a tre stelle.
    # Senza calendario quel divieto non diventa meno preciso: **non esiste
    # piu'**, perche' non c'e' nessun evento contro cui confrontare l'orario.
    # Il bot puo' aprire un minuto prima di un NFP o di un CPI. Lo stesso
    # vale per un calendario vecchio: gli eventi che contiene sono tutti
    # passati, quindi `dentro_finestra_news` non trova mai nulla e il filtro
    # e' spento pur essendo formalmente acceso -- che e' il modo piu'
    # silenzioso di non avere un filtro.
    #
    # Resta acceso tutto il resto: `SETUP-15` continua a citare `RISK-13`,
    # e quando il calendario c'e' ed e' fresco il filtro funziona come prima.
    # Cambia solo cosa succede quando manca.
    "PA-55": "opera",

    # --- MISURE: risolte leggendo, non decidendo ------------------------
    "PA-62": "distanza_relativa",           # k costante non esiste per 6J e 6S
    "PA-53": "calcolate",                   # festivita_mercato(anno)
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
    """Rischio per singola posizione (RISK-01, RISK-02, RISK-06).

    `n` e' il numero di posizioni del **gruppo di correlazione** dello
    strumento, contando quella in valutazione (REV-03). Le cinque coppie forex
    formano un gruppo unico; XAUUSD un gruppo proprio.
    """
    if n < 1:
        raise ValueError(f"n deve essere almeno 1, ricevuto {n}")
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")

    # REV-42 decide se le posizioni aperte si adeguino: cambia l'esposizione
    # totale anche quando non cambia questo valore.
    if richiedi("REV-42") not in ("ridimensiona", "non_ridimensiona"):
        raise PuntoApertoError(f"REV-42: lettura non riconosciuta: {richiedi('REV-42')!r}")

    scelta = richiedi("REV-03")
    if scelta not in ("per_gruppo_correlazione", "scala_risk02", "rischio_pieno_risk01"):
        raise PuntoApertoError(f"REV-03: lettura non riconosciuta: {scelta!r}")
    if scelta == "rischio_pieno_risk01" and gruppo_di(strumento) == "oro":
        # Lettura letterale di RISK-01: nessuna scala sull'oro.
        return RISCHIO_BASE

    return SCALA_RISCHIO.get(n, SCALA_RISCHIO_DA_3_IN_SU)


def posizioni_ridimensionate() -> bool:
    """True se aprire una posizione adegua il volume di quelle gia' aperte."""
    return richiedi("REV-42") == "ridimensiona"


def distanza_relativa_stop(chiusura_n2_future: float, stop_future: float) -> float:
    """Distanza di stop in forma adimensionale, misurata sul future.

    Primo passo del calcolo della size (DEF-47 come corretta da PA-62).
    Restituisce un numero puro: nessun prezzo CFD entra qui, quindi ESCL-12 e'
    rispettata. Chi chiama lo moltiplica per il prezzo CFD corrente per
    ottenere la distanza in punti dello strumento operativo.
    """
    metodo = richiedi("PA-62")
    if metodo != "distanza_relativa":
        raise PuntoApertoError(f"PA-62: metodo non riconosciuto: {metodo!r}")
    if chiusura_n2_future <= 0:
        raise ValueError(f"prezzo future non valido: {chiusura_n2_future}")
    distanza = abs(chiusura_n2_future - stop_future)
    if distanza == 0:
        # RISK-03: distanza nulla e' dato incoerente, si applica PRIN-99.
        raise ValueError("distanza di stop nulla: PRIN-99, nessun ordine")
    return distanza / chiusura_n2_future


def calendario_festivita_valido_per(anno: int) -> dict[date, str]:
    """Festivita' di CTX-04 per l'anno richiesto (PA-53, chiuso).

    Non c'e' piu' una tabella da aggiornare: le sei date mobili si calcolano.
    """
    scelta = richiedi("PA-53")
    if scelta != "calcolate":
        raise PuntoApertoError(f"PA-53: lettura non riconosciuta: {scelta!r}")
    return festivita_mercato(anno)


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
    assert (set(TF_BIAS) | set(TF_SOLO_GAP) | {TF.H4, TF.H1}
            | set(TF_INTRADAY)) == set(TF)
    assert not (set(TF_BIAS) & set(TF_SOLO_GAP))

    # DEF-46 copre tutti i timeframe da cui puo' nascere un ordine. Gli
    # intraday ci sono: sono timeframe di innesco di CRT-04, e senza un
    # bersaglio `target_iniziale` torna None e PRIN-99 impedisce l'apertura.
    assert set(TARGET_DI) == set(TF) - set(TF_SOLO_GAP)
    # E il target di un TF e' davvero quello immediatamente superiore nella
    # gerarchia ridotta: e' cio' che DEF-46 dichiara di essere.
    for tf, superiore in TARGET_DI.items():
        if superiore is None:
            assert tf is TF.M12, f"solo TF_12M puo' non avere superiore, non {tf}"
            continue
        if tf in TF_INTRADAY or tf is TF.H1:
            # Sotto le quattro ore nessun timeframe produce key level propri
            # (`TF_KEY_LEVEL`), quindi il primo disponibile e' TF_H4 per
            # tutti: non e' "quello immediatamente superiore" ma "il primo
            # che ha davvero un key level da offrire".
            assert superiore is TF.H4, f"{tf}: atteso TF_H4, non {superiore}"
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

    # Festivita' calcolate: dodici per anno, e coincidono con la tabella 2026
    # scritta a mano in CTX-04. E' la prova che il calcolo e' quello giusto.
    attese_2026 = {
        (1, 1), (1, 19), (2, 16), (4, 3), (5, 25), (6, 19),
        (7, 3), (9, 7), (11, 26), (11, 27), (12, 24), (12, 25),
    }
    calcolate = festivita_mercato(2026)
    assert len(calcolate) == 12, len(calcolate)
    ottenute = {(g.month, g.day) for g in calcolate}
    assert ottenute == attese_2026, sorted(ottenute ^ attese_2026)

    # Negli altri anni le date distinte sono 11 o 12: 11 quando Natale cade di
    # sabato e la sua osservanza si sovrappone alla Vigilia.
    for anno in range(2020, 2041):
        quante = len(festivita_mercato(anno))
        assert 11 <= quante <= 12, (anno, quante)
        # Nessuna data e' silenziosamente persa: le etichette restano dodici.
        etichette = sum(len(n.split(" / ")) for n in festivita_mercato(anno).values())
        assert etichette == 12, (anno, etichette)

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
