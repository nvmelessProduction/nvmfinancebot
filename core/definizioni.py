"""Le definizioni di `docs/01_definizioni.md`, tradotte in funzioni pure.

Ogni funzione porta nel docstring l'ID della regola che implementa. Se una
funzione non cita un ID, non appartiene a questo file.

**Purezza.** Nessuna funzione qui dentro tiene stato, legge da disco, tocca la
rete o guarda l'orologio. Riceve candele e valori, restituisce un risultato.
E' la ragione per cui il backtest e il live possono usare lo stesso codice
senza accorgersi della differenza, e per cui ogni regola e' collaudabile da
sola.

**Solo candele chiuse.** Ogni funzione che riceve una `Candela` riceve una
candela gia' chiusa (DEF-02, PRIN-11, ESCL-13). Le poche regole che lavorano
sul prezzo scambiato sono marcate SORVEGLIANZA nel docstring e ricevono un
prezzo, mai una candela in formazione (DEF-45).

Le decisioni prese sui punti aperti sono in `docs/DECISIONI-2026-09-03.md` e
vivono in `core/parametri.py`. Qui vengono usate, non ridiscusse.

**Regole di 01_definizioni.md che non stanno qui, e dove stanno.** Otto delle
quarantaquattro non sono funzioni pure su candele, e metterle qui sarebbe
stato sbagliato:

| Regola | Dove vive | Perche' |
|---|---|---|
| DEF-01 | `parametri.py` | Elenco e gerarchia dei timeframe: dati, non calcolo |
| DEF-18 | `motore.py` | Quando ricalcolare la bias: e' pianificazione |
| DEF-28 | `parametri.py` | Frequenza di ricalcolo dei livelli |
| DEF-32 | livello dati | Fonte e latenza: sta fuori dal motore di strategia |
| DEF-34 | `gestione.py` | Chiusura di una posizione: non e' una definizione |
| DEF-35 | nessun codice | I gap da rollover sono gap normali: nessun filtro da scrivere. Resta il campo statistico `gap_da_rollover` |
| DEF-46 | `parametri.py` | Mappa `TARGET_DI`: dati |
| DEF-47 | `parametri.py` | `distanza_relativa_stop()`, perche' e' il primo passo del calcolo della size |

Le altre trentasei sono qui. `DEF-05`, `DEF-06`, `DEF-07`, `DEF-08` e `DEF-15`
sono ritirate e i loro ID non tornano mai (ESCL-18).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Sequence

from core.parametri import (
    MINIMO_CANDELE_CHIUSE_PER_TF,
    ORDINE_SCANSIONE_TARGET,
    RSI_PERIODO,
    SOGLIA_SIMMETRIA_OMBRE,
    SOGLIA_SPIKE_RIFIUTO_FORTE,
    TF,
    TF_SOLO_GAP,
    UNIVERSO,
    gerarchia,
    ordine_scansione_gap,
    soglia_corpo_indecisione,
)

# ===========================================================================
# Tipi di base
# ===========================================================================


class Bias(str, Enum):
    """Direzione di un timeframe o del comando (DEF-16)."""

    LONG = "LONG"
    SHORT = "SHORT"
    NESSUNA = "NESSUNA"

    def opposta(self) -> "Bias":
        """La direzione contraria. NESSUNA non ha contrario."""
        if self is Bias.LONG:
            return Bias.SHORT
        if self is Bias.SHORT:
            return Bias.LONG
        return Bias.NESSUNA


class Polarita(str, Enum):
    """Polarita' di un gap (DEF-10, DEF-11).

    Attenzione: la polarita' NON e' la direzione operativa. Un gap rialzista
    sotto il prezzo e' un target ribassista (DEF-15bis).
    """

    RIALZISTA = "RIALZISTA"
    RIBASSISTA = "RIBASSISTA"


class Mitigazione(str, Enum):
    """Esito di DEF-42."""

    ATTESA = "ATTESA"
    NON_ATTESA = "NON_ATTESA"
    NON_DETERMINATA = "NON_DETERMINATA"


class TipoKeyLevel(str, Enum):
    """I tre key level di DEF-36."""

    MAX = "KL_max"
    MIN = "KL_min"
    META = "KL_50"


class Presa(str, Enum):
    """Esito di DEF-38."""

    RIALZO = "PRESO_RIALZO"
    RIBASSO = "PRESO_RIBASSO"
    NESSUNA = "NON_PRESO"


class Divergenza(str, Enum):
    """Esito di DEF-44."""

    RIALZISTA = "RIALZISTA"
    RIBASSISTA = "RIBASSISTA"
    NESSUNA = "NESSUNA"


@dataclass(frozen=True)
class Candela:
    """Una candela chiusa (DEF-02).

    `orario` e' l'istante di chiusura del periodo, in UTC. I confini del
    periodo seguono la sessione ETH dell'exchange (DEF-03): questo modulo li
    riceve gia' costruiti, non li calcola.
    """

    orario: datetime
    apertura: float
    massimo: float
    minimo: float
    chiusura: float

    def __post_init__(self) -> None:
        # Una candela con il massimo sotto il minimo non e' un dato da
        # interpretare: e' un errore di chi l'ha costruita.
        if self.massimo < self.minimo:
            raise ValueError(f"massimo {self.massimo} sotto il minimo {self.minimo}")
        if not (self.minimo <= self.apertura <= self.massimo):
            raise ValueError(f"apertura {self.apertura} fuori dal range")
        if not (self.minimo <= self.chiusura <= self.massimo):
            raise ValueError(f"chiusura {self.chiusura} fuori dal range")


@dataclass(frozen=True)
class Gap:
    """Un gap di tre candele (DEF-10, DEF-11, DEF-12)."""

    polarita: Polarita
    zona_inf: float
    zona_sup: float
    livello_inv: float
    tf: TF
    orario_formazione: datetime

    def contiene(self, prezzo: float) -> bool:
        """True se il prezzo e' dentro la zona, estremi inclusi."""
        return self.zona_inf <= prezzo <= self.zona_sup


@dataclass(frozen=True)
class KeyLevel:
    """Uno dei tre key level di un timeframe (DEF-36)."""

    tf: TF
    tipo: TipoKeyLevel
    valore: float


@dataclass(frozen=True)
class LivelloStrutturale:
    """Un massimo o minimo di candela chiusa (DEF-25)."""

    tf: TF
    valore: float
    orario: datetime
    rialzista: bool


# ===========================================================================
# 1. Misure di base sulla candela
# ===========================================================================


def intervallo(candela: Candela) -> float:
    """DEF-04 — Range della candela.

    Un range nullo e' dato incoerente: chi chiama applica PRIN-99. Qui viene
    restituito com'e', perche' una funzione pura non decide di astenersi.
    """
    return candela.massimo - candela.minimo


def range_coerente(candela: Candela) -> bool:
    """DEF-04 — True se il range e' utilizzabile, False se impone PRIN-99."""
    return intervallo(candela) > 0


def corpo(candela: Candela) -> float:
    """DEF-39 — Corpo della candela."""
    return abs(candela.chiusura - candela.apertura)


def ombra_superiore(candela: Candela) -> float:
    """DEF-39 — Ombra superiore."""
    return candela.massimo - max(candela.apertura, candela.chiusura)


def ombra_inferiore(candela: Candela) -> float:
    """DEF-39 — Ombra inferiore."""
    return min(candela.apertura, candela.chiusura) - candela.minimo


def e_inside_bar(c0: Candela, c1: Candela) -> bool:
    """DEF-09 — Inside bar. Confronto esatto, nessuna tolleranza."""
    return c0.massimo <= c1.massimo and c0.minimo >= c1.minimo


# ===========================================================================
# 2. Gap
# ===========================================================================


def gap_rialzista(p1: Candela, p2: Candela, p3: Candela, tf: TF) -> Optional[Gap]:
    """DEF-10 — Gap rialzista su tre candele consecutive.

    `p2` non entra nella condizione: il gap e' definito dal rapporto fra la
    prima e la terza. Resta nella firma perche' DEF-10 parla di un pattern a
    tre candele e ometterlo renderebbe la chiamata ambigua.
    """
    if p3.minimo > p1.massimo:
        return Gap(
            polarita=Polarita.RIALZISTA,
            zona_inf=p1.massimo,
            zona_sup=p3.minimo,
            livello_inv=p1.minimo,
            tf=tf,
            orario_formazione=p3.orario,
        )
    return None


def gap_ribassista(p1: Candela, p2: Candela, p3: Candela, tf: TF) -> Optional[Gap]:
    """DEF-11 — Gap ribassista su tre candele consecutive."""
    if p3.massimo < p1.minimo:
        return Gap(
            polarita=Polarita.RIBASSISTA,
            zona_inf=p3.massimo,
            zona_sup=p1.minimo,
            livello_inv=p1.massimo,
            tf=tf,
            orario_formazione=p3.orario,
        )
    return None


def gap_invalidato(gap: Gap, candele_successive: Sequence[Candela]) -> bool:
    """DEF-14 — Invalidazione di un gap.

    Le candele vanno prese **sul timeframe su cui il gap si e' formato**:
    chiusure su timeframe diversi non invalidano nulla.

    Conta esclusivamente `close`. Le ombre non invalidano mai un gap, per
    quanto profondamente attraversino il livello.
    """
    for candela in candele_successive:
        if gap.polarita is Polarita.RIALZISTA and candela.chiusura < gap.livello_inv:
            return True
        if gap.polarita is Polarita.RIBASSISTA and candela.chiusura > gap.livello_inv:
            return True
    return False


def gap_attivo(gap_per_tf: dict[TF, Sequence[Gap]], polarita: Polarita) -> Optional[Gap]:
    """DEF-13 — Selezione del gap attivo, uno solo per direzione.

    Si scorrono i timeframe nell'ordine di DEF-13 (che include TF_H12 e TF_H6
    per DEF-31, vedi REV-15) e ci si ferma al primo che contiene almeno un gap
    non invalidato della polarita' richiesta. A parita' di timeframe vince il
    piu' recente.

    I gap passati devono essere gia' filtrati da DEF-14: qui non si rivaluta
    l'invalidazione.
    """
    for tf in ordine_scansione_gap():
        candidati = [g for g in gap_per_tf.get(tf, ()) if g.polarita is polarita]
        if candidati:
            return max(candidati, key=lambda g: g.orario_formazione)
    return None


def direzione_verso_gap(gap: Gap, prezzo: float) -> Bias:
    """DEF-15bis — Direzione operativa per raggiungere il gap target.

    La polarita' del gap non c'entra: conta dove sta la zona rispetto al
    prezzo. Un gap rialzista sotto il prezzo e' un target ribassista.

    Restituisce NESSUNA se il prezzo e' gia' dentro la zona: il gap non e'
    piu' un target.
    """
    if prezzo > gap.zona_sup:
        return Bias.SHORT
    if prezzo < gap.zona_inf:
        return Bias.LONG
    return Bias.NESSUNA


# ===========================================================================
# 3. Accettazione e rifiuto
# ===========================================================================


def livelli_riferimento(c1: Candela) -> tuple[float, float]:
    """DEF-19 — Livelli di riferimento: estremi di C1, ombre incluse.

    Restituisce (livello_sup, livello_inf). Nessuna tolleranza: un tick oltre
    conta come superamento.
    """
    return c1.massimo, c1.minimo


def e_accettazione_rialzo(c0: Candela, c1: Candela) -> bool:
    """DEF-20 — Accettazione a rialzo."""
    livello_sup, _ = livelli_riferimento(c1)
    return c0.chiusura > livello_sup


def e_accettazione_ribasso(c0: Candela, c1: Candela) -> bool:
    """DEF-20 — Accettazione a ribasso."""
    _, livello_inf = livelli_riferimento(c1)
    return c0.chiusura < livello_inf


def e_rifiuto_rialzo(c0: Candela, c1: Candela) -> bool:
    """DEF-21 — Rifiuto semplice a rialzo. Nessuna soglia sulla spike.

    E' il grado usato da DEF-16 per la bias. Il preambolo di DEF-21 che
    attribuiva la condizione sulla spike a entrambi i gradi e' stato corretto
    in v1.9 (PA-31).
    """
    livello_sup, _ = livelli_riferimento(c1)
    return c0.massimo > livello_sup and c0.chiusura <= livello_sup and c0.chiusura < c1.chiusura


def e_rifiuto_ribasso(c0: Candela, c1: Candela) -> bool:
    """DEF-21 — Rifiuto semplice a ribasso."""
    _, livello_inf = livelli_riferimento(c1)
    return c0.minimo < livello_inf and c0.chiusura >= livello_inf and c0.chiusura > c1.chiusura


def _spike_prevale(ombra: float, corpo_candela: float) -> bool:
    """DEF-21 — La spike prevale sul corpo.

    Con corpo nullo qualsiasi ombra maggiore di zero soddisfa la condizione:
    lo dice DEF-21 esplicitamente, ed evita una divisione per zero che non
    avrebbe senso.
    """
    if corpo_candela == 0:
        return ombra > 0
    return ombra > SOGLIA_SPIKE_RIFIUTO_FORTE * corpo_candela


def e_rifiuto_forte_rialzo(c0: Candela, c1: Candela) -> bool:
    """DEF-21 — Rifiuto forte a rialzo: semplice piu' spike prevalente."""
    return e_rifiuto_rialzo(c0, c1) and _spike_prevale(ombra_superiore(c0), corpo(c0))


def e_rifiuto_forte_ribasso(c0: Candela, c1: Candela) -> bool:
    """DEF-21 — Rifiuto forte a ribasso."""
    return e_rifiuto_ribasso(c0, c1) and _spike_prevale(ombra_inferiore(c0), corpo(c0))


def e_confluente_rialzo(c0: Candela, c1: Candela) -> bool:
    """DEF-40 — Candela confluente al trend rialzista."""
    return (
        c0.chiusura > c0.apertura
        and corpo(c0) > ombra_superiore(c0)
        and c0.chiusura > c1.massimo
    )


def e_confluente_ribasso(c0: Candela, c1: Candela) -> bool:
    """DEF-40 — Candela confluente al trend ribassista."""
    return (
        c0.chiusura < c0.apertura
        and corpo(c0) > ombra_inferiore(c0)
        and c0.chiusura < c1.minimo
    )


def e_indecisione(c0: Candela) -> bool:
    """DEF-41 — Candela di indecisione (doji).

    Due condizioni: corpo minuscolo rispetto al range, e ombre confrontabili
    fra loro. La seconda esclude martelli e shooting star, che hanno il corpo
    piccolo ma una sola ombra lunga.

    Un range nullo non e' indecisione ma dato incoerente (DEF-04): si
    restituisce False e chi chiama applica PRIN-99.
    """
    ampiezza = intervallo(c0)
    if ampiezza <= 0:
        return False
    if corpo(c0) > soglia_corpo_indecisione() * ampiezza:
        return False

    sopra, sotto = ombra_superiore(c0), ombra_inferiore(c0)
    piu_lunga = max(sopra, sotto)
    if piu_lunga == 0:
        return False
    return min(sopra, sotto) >= SOGLIA_SIMMETRIA_OMBRE * piu_lunga


def e_indecisione_forte(c0: Candela, c1: Candela) -> bool:
    """DEF-41 — Indecisione con mancata accettazione della candela precedente."""
    livello_sup, livello_inf = livelli_riferimento(c1)
    return e_indecisione(c0) and livello_inf <= c0.chiusura <= livello_sup


# ===========================================================================
# 4. Aspettativa di mitigazione
# ===========================================================================


def mitigazione_attesa(c0: Candela, c1: Candela, polarita: Polarita) -> Mitigazione:
    """DEF-42 — Aspettativa di mitigazione del gap formato con P3 = C0.

    `polarita` e' la polarita' del gap (DEF-10/DEF-11), non la direzione
    operativa di DEF-15bis: quando DEF-42 valuta il gap, il gap si e' appena
    formato e una direzione operativa non esiste ancora (REV-29).

    Il rifiuto forte conta in **entrambe** le direzioni: DEF-42 scrive
    "C0 e' RIFIUTO_FORTE" senza qualificarlo.

    NON_DETERMINATA non e' un errore: e' una condizione prevista che comporta
    astensione (CTX-01 #10).
    """
    confluente = (
        e_confluente_rialzo(c0, c1)
        if polarita is Polarita.RIALZISTA
        else e_confluente_ribasso(c0, c1)
    )
    if confluente:
        return Mitigazione.NON_ATTESA

    if (
        e_rifiuto_forte_rialzo(c0, c1)
        or e_rifiuto_forte_ribasso(c0, c1)
        or e_indecisione(c0)
        or e_inside_bar(c0, c1)
    ):
        return Mitigazione.ATTESA

    return Mitigazione.NON_DETERMINATA


# ===========================================================================
# 5. Le quattro fasi del gap
# ===========================================================================


@dataclass(frozen=True)
class StatoFasi:
    """Stato del modello a fasi di DEF-43.

    Immutabile: `avanza_fasi` restituisce un nuovo stato. Cosi' il backtest
    puo' tenere la storia degli stati senza copie difensive.

    `fase = 0` significa che il prezzo non ha ancora toccato la zona.
    """

    fase: int = 0
    estremo_fase1: Optional[float] = None
    # True mentre il prezzo e' dentro la zona: serve a distinguere l'uscita
    # dal semplice restare fuori.
    dentro_zona: bool = False


def avanza_fasi(stato: StatoFasi, gap: Gap, bias: Bias, prezzo: float) -> StatoFasi:
    """DEF-43 — SORVEGLIANZA. Avanza il modello a fasi su un prezzo scambiato.

    Fasi 1, 2 e 3 sono sorveglianza (DEF-45): verificano se una zona gia'
    calcolata su candele chiuse viene toccata. La **fase 4 non e' qui**:
    richiede un CRT formato, che e' calcolo su candele chiuse e vive in
    `setup.py`.

    `bias` dice da che parte sta la zona rispetto al prezzo:
      SHORT  zona sopra, il prezzo vi entra salendo
      LONG   zona sotto, il prezzo vi entra scendendo

    Letture adottate in REV-30, dove DEF-43 taceva:
      - fase 2, "esce nella direzione contraria" = esce dal lato da cui e'
        entrato. E' l'unica lettura che rende la fase una *automatic
        reaction*, cioe' un ritorno indietro.
      - fase 3, "rientra" e "supera estremo_fase1" sono **sequenziali**: prima
        il rientro, poi il superamento, che puo' portare il prezzo fuori dalla
        zona ed e' normale.
    """
    if bias is Bias.NESSUNA:
        return stato

    dentro = gap.contiene(prezzo)
    verso_alto = bias is Bias.SHORT  # zona sopra: l'estremo di fase 1 e' un massimo

    # --- non ancora iniziato: il primo ingresso in zona apre la fase 1 -----
    if stato.fase == 0:
        if dentro:
            return StatoFasi(fase=1, estremo_fase1=prezzo, dentro_zona=True)
        return stato

    # --- fase 1: aggiornamento continuo dell'estremo, poi uscita ----------
    if stato.fase == 1:
        if dentro:
            precedente = stato.estremo_fase1
            estremo = (
                prezzo
                if precedente is None
                else (max(precedente, prezzo) if verso_alto else min(precedente, prezzo))
            )
            return StatoFasi(fase=1, estremo_fase1=estremo, dentro_zona=True)
        # Uscita dal lato di entrata: sotto la zona se si saliva, sopra se si
        # scendeva. L'uscita dal lato opposto non apre la fase 2.
        uscita_giusta = prezzo < gap.zona_inf if verso_alto else prezzo > gap.zona_sup
        if uscita_giusta:
            return StatoFasi(fase=2, estremo_fase1=stato.estremo_fase1, dentro_zona=False)
        return StatoFasi(fase=1, estremo_fase1=stato.estremo_fase1, dentro_zona=False)

    # --- fase 2: si aspetta il rientro ------------------------------------
    if stato.fase == 2:
        if dentro:
            return StatoFasi(fase=2, estremo_fase1=stato.estremo_fase1, dentro_zona=True)
        return stato

    return stato


def fase_tre_raggiunta(stato: StatoFasi, prezzo: float, bias: Bias) -> bool:
    """DEF-43 — SORVEGLIANZA. Il prezzo ha superato `estremo_fase1` dopo il rientro.

    Va chiamata solo su uno stato in fase 2 che sia gia' rientrato in zona
    (`dentro_zona`). Il superamento puo' portare il prezzo fuori dalla zona:
    la fase 3 e' definita dallo sbilanciamento dell'estremo, non dalla
    permanenza dentro (REV-30).
    """
    if stato.fase != 2 or not stato.dentro_zona or stato.estremo_fase1 is None:
        return False
    if bias is Bias.SHORT:
        return prezzo > stato.estremo_fase1
    if bias is Bias.LONG:
        return prezzo < stato.estremo_fase1
    return False


# ===========================================================================
# 6. RSI e divergenza
# ===========================================================================


def rsi(chiusure: Sequence[float], periodo: int = RSI_PERIODO) -> Optional[float]:
    """DEF-44 — RSI di Wilder sull'ultima chiusura della serie.

    Restituisce None se la serie e' piu' corta di `periodo + 1`: senza abbastanza
    storia l'indicatore non esiste, e inventarne un valore sarebbe peggio.

    E' l'unico indicatore che genera un dato in tutta la strategia (ESCL-15 a),
    e serve solo a registrare la divergenza: non modifica alcuna decisione.
    """
    if periodo < 1 or len(chiusure) < periodo + 1:
        return None

    guadagni: list[float] = []
    perdite: list[float] = []
    for precedente, corrente in zip(chiusure, chiusure[1:]):
        variazione = corrente - precedente
        guadagni.append(max(variazione, 0.0))
        perdite.append(max(-variazione, 0.0))

    media_g = sum(guadagni[:periodo]) / periodo
    media_p = sum(perdite[:periodo]) / periodo
    # Smorzamento di Wilder sul resto della serie.
    for g, p in zip(guadagni[periodo:], perdite[periodo:]):
        media_g = (media_g * (periodo - 1) + g) / periodo
        media_p = (media_p * (periodo - 1) + p) / periodo

    if media_p == 0:
        # Nessuna perdita nel periodo: RSI massimo per definizione.
        return 100.0
    forza = media_g / media_p
    return 100.0 - (100.0 / (1.0 + forza))


def divergenza_rsi(
    prezzo_a: float,
    rsi_a: float,
    prezzo_b: float,
    rsi_b: float,
    bias_gap: Bias,
) -> Divergenza:
    """DEF-44 — Divergenza fra l'estremo di fase 1 e quello di fase 3.

    `punto_A` e' `estremo_fase1`, `punto_B` l'estremo che lo rompe (DEF-43).
    Se la fase 3 produce piu' estremi, il confronto si ripete usando sempre A
    come riferimento fisso: chi chiama richiama questa funzione, `punto_A` non
    cambia mai.

    La divergenza e' registrata a fini statistici e non modifica alcuna
    decisione (DEF-44, PA-39).
    """
    if bias_gap is Bias.SHORT and prezzo_b > prezzo_a and rsi_b < rsi_a:
        return Divergenza.RIBASSISTA
    if bias_gap is Bias.LONG and prezzo_b < prezzo_a and rsi_b > rsi_a:
        return Divergenza.RIALZISTA
    return Divergenza.NESSUNA


# ===========================================================================
# 7. Bias
# ===========================================================================


def bias_timeframe(
    c0: Candela,
    c1: Candela,
    c2: Optional[Candela] = None,
    bias_precedente: Bias = Bias.NESSUNA,
) -> Bias:
    """DEF-16 — Bias di un singolo timeframe.

    Si applica il **primo** passo la cui condizione e' vera e si interrompe.

    `c2` serve solo al passo 6: una inside bar puo' formare un gap con
    `P1 = c2`, `P2 = c1`, `P3 = c0` (DEF-23). Senza `c2` quel controllo non e'
    possibile e si passa all'eredita' (DEF-24).

    `bias_precedente` e' il valore di `bias_TF` alla candela precedente dello
    stesso timeframe, per l'eredita' ricorsiva di DEF-24.

    Non si applica a TF_H12 e TF_H6, dove non si calcola alcuna bias (DEF-31).
    """
    livello_sup, livello_inf = livelli_riferimento(c1)

    # Passo 1 — rompe entrambi gli estremi e chiude in mezzo: rifiuto a
    # rialzo e a ribasso sarebbero simultanei, quindi nessuna bias.
    if (
        c0.massimo > livello_sup
        and c0.minimo < livello_inf
        and livello_inf <= c0.chiusura <= livello_sup
    ):
        return Bias.NESSUNA

    if e_accettazione_rialzo(c0, c1):        # Passo 2
        return Bias.LONG
    if e_accettazione_ribasso(c0, c1):       # Passo 3
        return Bias.SHORT
    if e_rifiuto_rialzo(c0, c1):             # Passo 4
        return Bias.SHORT
    if e_rifiuto_ribasso(c0, c1):            # Passo 5
        return Bias.LONG
    if e_inside_bar(c0, c1):                 # Passo 6
        return _bias_inside_bar(c0, c1, c2, bias_precedente)

    return Bias.NESSUNA                      # Passo 7


def _bias_inside_bar(
    c0: Candela,
    c1: Candela,
    c2: Optional[Candela],
    bias_precedente: Bias,
) -> Bias:
    """DEF-23 e DEF-24 — Bias di una inside bar.

    Se la inside bar forma un gap, la bias e' quella del gap. Se non lo forma,
    si eredita: una serie consecutiva di inside bar senza gap mantiene
    invariata l'ultima bias determinata da una candela non inside.

    Senza alcun valore precedente (avvio del sistema, storico insufficiente)
    la bias e' NESSUNA.
    """
    if c2 is not None:
        # Il timeframe non incide sulla polarita': si usa un segnaposto.
        if gap_rialzista(c2, c1, c0, TF.D1) is not None:
            return Bias.LONG
        if gap_ribassista(c2, c1, c0, TF.D1) is not None:
            return Bias.SHORT
    return bias_precedente


def timeframe_operabile(bias_tf: Bias, bias_12m: Bias) -> bool:
    """DEF-17 — Gerarchia della bias fra timeframe.

    Un timeframe la cui bias e' opposta a `bias_12M` non produce alcun segnale
    operativo: si attende il riallineamento.

    Con `bias_12M` NESSUNA non c'e' nulla a cui opporsi, quindi il timeframe
    resta utilizzabile.
    """
    if bias_12m is Bias.NESSUNA:
        return True
    return bias_tf is not bias_12m.opposta()


# ===========================================================================
# 8. Key level
# ===========================================================================


def liv_50(candela: Candela) -> float:
    """DEF-36 — Livello del 50% di una candela qualsiasi.

    Aggiunta in v1.9: e' la formula usata da TP1 su `N1` (GEST-07), che vale
    su qualsiasi timeframe, `TF_H4` e `TF_H1` compresi. Non va confusa con
    `KL_50_TF`, che e' la stessa formula applicata a `C1`.
    """
    return (candela.massimo + candela.minimo) / 2


def key_levels(c1: Candela, tf: TF) -> tuple[KeyLevel, KeyLevel, KeyLevel]:
    """DEF-36 — I tre key level di un timeframe, calcolati su `C1`.

    `C1` e non `C0`: con `C0` la presa di DEF-38 confronterebbe `high[C0]` con
    se' stesso e sarebbe sempre falsa (REV-23).
    """
    return (
        KeyLevel(tf, TipoKeyLevel.MAX, c1.massimo),
        KeyLevel(tf, TipoKeyLevel.MIN, c1.minimo),
        KeyLevel(tf, TipoKeyLevel.META, liv_50(c1)),
    )


def assorbi_key_level(livelli: Iterable[KeyLevel]) -> list[KeyLevel]:
    """DEF-37 — Priorita' e assorbimento fra key level coincidenti.

    Quando due key level di timeframe diversi hanno lo **stesso identico
    valore**, resta solo quello del timeframe piu' alto. Uguaglianza esatta,
    nessuna tolleranza: non e' un caso raro, perche' il minimo di una candela
    mensile e' per costruzione identico al minimo di una delle sue settimanali.
    """
    ordine = gerarchia()
    rimasti: dict[float, KeyLevel] = {}
    for livello in livelli:
        precedente = rimasti.get(livello.valore)
        if precedente is None or ordine.index(livello.tf) < ordine.index(precedente.tf):
            rimasti[livello.valore] = livello
    return sorted(rimasti.values(), key=lambda k: (ordine.index(k.tf), k.valore))


def presa_key_level(c0: Candela, livello: KeyLevel) -> Presa:
    """DEF-38 — Presa di un key level, alla chiusura di candela.

    Dalla v1.9 la presa si conferma **a candela chiusa**, mai sul prezzo
    scambiato (DEF-45): uno sfioramento intraday rientrato prima della
    chiusura non e' una presa e non abilita alcun setup.

    La candela va presa sul timeframe del key level.
    """
    if livello.tipo is TipoKeyLevel.MAX and c0.massimo > livello.valore:
        return Presa.RIALZO
    if livello.tipo is TipoKeyLevel.MIN and c0.minimo < livello.valore:
        return Presa.RIBASSO
    return Presa.NESSUNA


def timeframe_trigger_ammessi(tf_riferimento: TF) -> tuple[TF, ...]:
    """DEF-30 — Timeframe su cui e' ammessa la ricerca dell'ingresso.

    Qualsiasi timeframe **strettamente inferiore** a quello di riferimento,
    che e' il timeframe del gap attivo per gli ingressi da gap e quello del
    key level preso per gli altri (REV-28).

    `TF_H12` e `TF_H6` sono esclusi: DEF-31 li riserva ai soli gap e SETUP-05
    non definisce per essi alcuna condizione di allineamento, quindi un CRT
    formato li' non potrebbe mai superare SETUP-15 (REV-11).
    """
    ordine = gerarchia()
    posizione = ordine.index(tf_riferimento)
    return tuple(tf for tf in ordine[posizione + 1:] if tf not in TF_SOLO_GAP)


# ===========================================================================
# 9. Livelli strutturali e target
# ===========================================================================


def livelli_strutturali(candele: Sequence[Candela], tf: TF) -> list[LivelloStrutturale]:
    """DEF-25 — Ogni massimo e ogni minimo di candela chiusa e' un livello.

    Ogni livello porta con se' il timeframe su cui si e' formato: serve alla
    priorita' di DEF-27 e alla scansione di DEF-22.
    """
    livelli: list[LivelloStrutturale] = []
    for candela in candele:
        livelli.append(LivelloStrutturale(tf, candela.massimo, candela.orario, True))
        livelli.append(LivelloStrutturale(tf, candela.minimo, candela.orario, False))
    return livelli


def livello_consumato(livello: LivelloStrutturale, estremo_successivo: float) -> bool:
    """DEF-27 — SORVEGLIANZA. Un livello e' consumato al tocco.

    `estremo_successivo` e' il massimo prezzo scambiato dopo la formazione per
    un livello rialzista, il minimo per uno ribassista.

    Il consumo si verifica sul prezzo scambiato, non alla chiusura di candela
    (DEF-45). Un livello consumato non torna mai disponibile (ESCL-17).
    """
    if livello.rialzista:
        return estremo_successivo >= livello.valore
    return estremo_successivo <= livello.valore


def timeframe_utilizzabile(candele_chiuse_nel_lookback: int) -> bool:
    """DEF-26 — Un timeframe produce bias e livelli solo con storia a sufficienza."""
    return candele_chiuse_nel_lookback >= MINIMO_CANDELE_CHIUSE_PER_TF


def target_direzionale(
    disponibili_per_tf: dict[TF, Sequence[LivelloStrutturale]],
    prezzo: float,
    direzione: Bias,
) -> Optional[LivelloStrutturale]:
    """DEF-22 — Target direzionale globale.

    Si scorrono i timeframe nell'ordine di DEF-22, che parte **sempre** da
    `TF_12M` indipendentemente dal timeframe del gap attivo, e ci si ferma al
    primo che contiene almeno un livello disponibile oltre il prezzo. Fra
    quelli di quel timeframe si prende il piu' vicino al prezzo.

    I livelli passati devono essere gia' filtrati da DEF-27: qui sono tutti
    considerati disponibili.

    None significa nessun target: chi chiama applica PRIN-99.
    """
    if direzione is Bias.NESSUNA:
        return None

    for tf in ORDINE_SCANSIONE_TARGET:
        livelli = disponibili_per_tf.get(tf, ())
        if direzione is Bias.LONG:
            oltre = [l for l in livelli if l.rialzista and l.valore > prezzo]
            if oltre:
                return min(oltre, key=lambda l: l.valore)
        else:
            oltre = [l for l in livelli if not l.rialzista and l.valore < prezzo]
            if oltre:
                return max(oltre, key=lambda l: l.valore)
    return None


def target_raggiunto(target: LivelloStrutturale, prezzo: float) -> bool:
    """DEF-29 — SORVEGLIANZA. Il target si raggiunge al tocco, non alla chiusura."""
    return livello_consumato(target, prezzo)


# ===========================================================================
# 10. Strumenti
# ===========================================================================


def direzione_cfd(direzione_future: Bias, strumento: str) -> Bias:
    """DEF-33 — Converte la direzione rilevata sul future in direzione CFD.

    `6J` e `6S` hanno segno invertito: quotano yen e franco contro dollaro,
    mentre i CFD corrispondenti quotano il dollaro contro quelle valute.

    Nessun **prezzo** viene convertito qui, solo il segno della direzione:
    ESCL-12 vieta di convertire prezzi, non di sapere da che parte si va.
    """
    if strumento not in UNIVERSO:
        raise ValueError(f"strumento fuori da PRIN-08: {strumento}")
    if UNIVERSO[strumento].segno_invertito:
        return direzione_future.opposta()
    return direzione_future
