"""Il metodo delle foto del proprietario (06/10/2026): `spec/metodo_foto.md`.

Il proprietario ha mandato 23 esempi (`casi/ESEMPI-PROPRIETARIO.md`) e alle domande ha risposto *"come
nelle foto"*. Qui le regole, una funzione per ognuna, tutte sulle sole candele gia' chiuse:

- **il CRT** (`trova`): la candela 2 prende la liquidita' di un lato del range e chiude dentro; il range e'
  la candela 1, o la candela madre se la candela 1 e le seguenti sono inside bar (*"è il range low h6 ...
  quando il prezzo o con la candela successiva fa inside bar o comunque fa il crt"*);
- **l'entrata** all'apertura della candela 3 (*"non c'è limite di orario, entra ad apertura candela"*),
  **lo stop** oltre l'estremo della candela 2, **il primo target** l'altro lato del range con parziale e
  pareggio (*"il kl è sempre il tp1+be"*), **il target finale** il gap del timeframe alto, o il key level
  se il gap non c'e' (`obiettivo_finale`);
- **il key level** (`livelli_prima`): il massimo o minimo del periodo prima (DH/DL, WH/WL, MH/ML, 3 mesi,
  anno) preso dalla candela 2;
- **la direzione** (`direzione`): il timeframe di comando (settimana, mese, 3, 6, 12 mesi); la candela
  che "non accetta" (inside bar, o liquidita' presa senza chiudere oltre) e il ritracciamento verso un gap;
- **il gap** (`gap_di`, `fase`): zona d'entrata o target; le fasi aggressione, reazione automatica,
  liquidazione, continuazione, con la divergenza RSI *"solo ed esclusivamente per i gap"*;
- **il DXY** (`dxy`): sintetico dalle coppie del dollaro; un suo setup vale per tutte le coppie col dollaro.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import CRT, Motivo, Verso
from nvm.dati.candele import Candele, costruisci, weekend
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, PUNTO, Minuti
from nvm.tempo import ORDINE, TF, fine_candela, inizio_candela

# I timeframe su cui il proprietario opera il CRT (foto: 1 ora, 4 ore, 6 ore, giorno, settimana, mese).
TF_CRT = (TF.H1, TF.H4, TF.H6, TF.D1, TF.W1, TF.MN)
# I key level: il massimo e il minimo del periodo prima.
TF_KL = (TF.D1, TF.W1, TF.MN, TF.Q3, TF.Y1)
# I gap dei timeframe alti: zona d'entrata o target finale.
TF_GAP = (TF.D1, TF.W1, TF.MN, TF.Q3, TF.S6, TF.Y1)
# I timeframe di comando: da qui viene la direzione.
TF_COMANDO = (TF.D1, TF.W1, TF.MN, TF.Q3, TF.S6, TF.Y1)
# I timeframe che si costruiscono dalle ore; quelli sopra, se ci sono, dalle candele giornaliere lunghe.
DALLE_ORE = (TF.H1, TF.H4, TF.H6, TF.H12, TF.D1)
LUNGHI = (TF.W1, TF.MN, TF.Q3, TF.S6, TF.Y1)

NOMI = {TF.H1: "1 ora", TF.H4: "4 ore", TF.H6: "6 ore", TF.H12: "12 ore", TF.D1: "giornaliero",
        TF.W1: "settimanale", TF.MN: "mensile", TF.Q3: "3 mesi", TF.S6: "6 mesi", TF.Y1: "annuale"}
SIGLE = {TF.D1: "D", TF.W1: "W", TF.MN: "M"}
LUNGO = {TF.Q3: "dei 3 mesi", TF.S6: "dei 6 mesi", TF.Y1: "annuale"}

# Quante candele indietro si cerca la candela madre (le inside bar che rimandano).
MADRE_MASSIMA = 12
# Di quanto la candela 2 puo' chiudere oltre il lato del range: niente. Il proprietario, 07/10/2026: *"non deve
# sforare. potrebbe essere un errore mio, ho dato per scontato che non avesse accettato"* (la foto 6 della
# cartella 5, oro del 1 maggio 2026, chiudeva 0,1 sopra il massimo della candela 1).
TOLLERANZA_CHIUSURA = 0.0
# Quante candele indietro si guardano i gap, per timeframe: un gap piu' vecchio non e' piu' "attivo" (nelle
# foto i gap usati come target sono di 1-2 anni al massimo; il gap annuale della sterlina del 2017 o quello
# dei 3 mesi dell'euro del 2022 il proprietario non li guarda).
GAP_INDIETRO = {TF.D1: 120, TF.W1: 52, TF.MN: 24, TF.Q3: 8, TF.S6: 6, TF.Y1: 6}
# L'RSI: periodo e quante ore intorno al minimo si cerca il suo minimo.
RSI_PERIODO = 14


def _sopra(a: TF, b: TF) -> bool:
    return ORDINE.index(a) > ORDINE.index(b)


def _almeno(a: TF, b: TF) -> bool:
    return ORDINE.index(a) >= ORDINE.index(b)


def _v(short: bool, compra: str, vende: str) -> str:
    return vende if short else compra


# --- il quadro: le candele di tutti i timeframe di uno strumento, chiuse a un istante -----------------

@dataclass
class Quadro:
    strumento: str
    adesso: int
    candele: dict
    _rsi: dict = field(default_factory=dict, repr=False)

    @property
    def ore(self) -> Candele:
        return self.candele[TF.H1]

    def rsi(self, tf: TF) -> np.ndarray:
        if tf not in self._rsi:
            self._rsi[tf] = rsi(self.candele[tf].bid[:, CHIUSURA])
        return self._rsi[tf]

    def taglia(self, t: int) -> "Quadro":
        """Lo stesso quadro com'era a `t`: solo le candele gia' chiuse (l'RSI e' causale, si taglia anche lui)."""
        c = {tf: x.chiuse_entro(t) for tf, x in self.candele.items()}
        r = {tf: v[:len(c[tf])] for tf, v in self._rsi.items()}
        return Quadro(self.strumento, int(t), c, r)

    @classmethod
    def da(cls, ore: Minuti, adesso: int, lunghe: Optional[Minuti] = None) -> "Quadro":
        """`ore`: le orarie; `lunghe`: candele giornaliere di tanti anni (dal vivo, per i 3, 6, 12 mesi)."""
        c = {}
        for tf in DALLE_ORE:
            c[tf] = costruisci(ore, tf).chiuse_entro(adesso)
        for tf in LUNGHI:
            dalle_ore = costruisci(ore, tf).chiuse_entro(adesso)
            if lunghe is not None and len(lunghe):
                lunghe_tf = costruisci(lunghe, tf).chiuse_entro(adesso)
                # Le giornaliere lunghe danno gli anni passati; le ore, se arrivano piu' in la', l'ultimo pezzo.
                if len(dalle_ore) and len(lunghe_tf) and dalle_ore.fine[-1] > lunghe_tf.fine[-1]:
                    nuove = dalle_ore.fra(int(lunghe_tf.fine[-1]), int(dalle_ore.fine[-1]) + 1)
                    lunghe_tf = _attacca(lunghe_tf, nuove)
                c[tf] = lunghe_tf if len(lunghe_tf) >= len(dalle_ore) else dalle_ore
            else:
                c[tf] = dalle_ore
        return cls(ore.strumento, int(adesso), c)


def _attacca(a: Candele, b: Candele) -> Candele:
    if not len(b):
        return a
    return Candele(a.strumento, a.tf, np.r_[a.inizio, b.inizio], np.r_[a.fine, b.fine],
                   np.r_[a.bid, b.bid], np.r_[a.ask, b.ask], np.r_[a.volume, b.volume])


def rsi(chiusure: np.ndarray, periodo: int = RSI_PERIODO) -> np.ndarray:
    """L'RSI di Wilder; NaN finche' non ci sono abbastanza candele."""
    n = len(chiusure)
    fuori = np.full(n, np.nan)
    if n <= periodo:
        return fuori
    d = np.diff(chiusure)
    su, giu = np.maximum(d, 0.0), np.maximum(-d, 0.0)
    m_su, m_giu = su[:periodo].mean(), giu[:periodo].mean()
    for i in range(periodo, n):
        if i > periodo:
            m_su = (m_su * (periodo - 1) + su[i - 1]) / periodo
            m_giu = (m_giu * (periodo - 1) + giu[i - 1]) / periodo
        fuori[i] = 100.0 if m_giu == 0 else 100.0 - 100.0 / (1.0 + m_su / m_giu)
    return fuori


# --- la direzione di una candela (Romeo V1 35:12, e la candela che "non accetta") ---------------------

def bias_candela(c: Candele, k: int, eredita: int = 3) -> tuple[int, str]:
    """+1 rialzista, -1 ribassista, 0 nessuna: la candela k rispetto alla k-1.

    Chiude sopra il massimo di prima: accetta piu' in alto. Prende il massimo ma chiude dentro: non accetta,
    si va giu' (e lo specchio). Inside bar (ne' massimo ne' minimo nuovo): non accetta, rimanda; vale la
    direzione di prima. Prende tutti e due i lati e chiude dentro: nessuna."""
    if k < 1 or k >= len(c):
        return 0, ""
    p, q = c.bid[k - 1], c.bid[k]
    su, giu = q[MASSIMO] > p[MASSIMO], q[MINIMO] < p[MINIMO]
    if q[CHIUSURA] > p[MASSIMO]:
        return 1, "ha chiuso sopra il massimo della candela prima: accetta più in alto"
    if q[CHIUSURA] < p[MINIMO]:
        return -1, "ha chiuso sotto il minimo della candela prima: accetta più in basso"
    if su and not giu:
        return -1, "ha preso il massimo della candela prima ma non ha accettato (ha chiuso dentro)"
    if giu and not su:
        return 1, "ha preso il minimo della candela prima ma non ha accettato (ha chiuso dentro)"
    if not su and not giu:
        if eredita > 0:
            b, _ = bias_candela(c, k - 1, eredita - 1)
            if b:
                return b, "inside bar: non accetta, resta la direzione di prima"
        return 0, "inside bar"
    return 0, "ha preso tutti e due i lati e ha chiuso dentro"


# --- i key level: massimo e minimo del periodo prima ----------------------------------------------------

@dataclass
class Livello:
    tf: TF
    alto: bool
    prezzo: float
    inizio: int
    # Il massimo (minimo) del periodo in corso fatto prima del CRT, non del periodo prima.
    oggi: bool = False

    @property
    def nome(self) -> str:
        if self.tf in SIGLE:
            return SIGLE[self.tf] + ("H" if self.alto else "L") + (" di oggi" if self.oggi else "")
        return ("massimo " if self.alto else "minimo ") + LUNGO.get(self.tf, NOMI.get(self.tf, ""))


def livelli_prima(q: Quadro, t: int, tfs=TF_KL) -> list[Livello]:
    """Il massimo e il minimo dell'ultimo periodo chiuso prima di `t`, per ogni timeframe."""
    fuori = []
    for tf in tfs:
        c = q.candele.get(tf)
        if c is None or not len(c):
            continue
        k = int(np.searchsorted(c.fine, t, side="right")) - 1
        if k < 0:
            continue
        fuori.append(Livello(tf, True, float(c.bid[k, MASSIMO]), int(c.inizio[k])))
        fuori.append(Livello(tf, False, float(c.bid[k, MINIMO]), int(c.inizio[k])))
    return fuori


# --- i gap (FVG) dei timeframe alti ---------------------------------------------------------------------

@dataclass
class Gap:
    tf: TF
    rialzista: bool
    basso: float
    alto: float
    nato: int
    # Il primo istante in cui il prezzo ci entra, e quando lo attraversa tutto (None: non ancora).
    toccato: Optional[int] = None
    riempito: Optional[int] = None

    @property
    def bordo(self) -> float:
        """Il bordo che il prezzo incontra arrivando: l'alto di un gap rialzista (sotto il prezzo), il basso
        di un gap ribassista (sopra)."""
        return self.alto if self.rialzista else self.basso

    @property
    def nome(self) -> str:
        return f"gap {NOMI.get(self.tf, self.tf.value)} {'rialzista' if self.rialzista else 'ribassista'}"


def gap_di(q: Quadro, tf: TF, t: int) -> list[Gap]:
    """I gap del timeframe nati prima di `t`, con quando il prezzo li ha toccati e riempiti (fino a `t`)."""
    c = q.candele.get(tf)
    if c is None or len(c) < 3:
        return []
    n = int(np.searchsorted(c.fine, t, side="right"))
    a = max(2, n - GAP_INDIETRO.get(tf, 100))
    h, l = c.bid[:n, MASSIMO], c.bid[:n, MINIMO]
    ore = q.ore
    m = int(np.searchsorted(ore.fine, t, side="right"))
    o_ini, o_h, o_l = ore.inizio[:m], ore.bid[:m, MASSIMO], ore.bid[:m, MINIMO]
    fuori = []
    for i in range(a, n):
        if h[i - 2] < l[i]:
            g = Gap(tf, True, float(h[i - 2]), float(l[i]), int(c.fine[i]))
        elif l[i - 2] > h[i]:
            g = Gap(tf, False, float(h[i]), float(l[i - 2]), int(c.fine[i]))
        else:
            continue
        j = int(np.searchsorted(o_ini, g.nato))
        if g.rialzista:
            dentro, oltre = o_l[j:] <= g.alto, o_l[j:] < g.basso
        else:
            dentro, oltre = o_h[j:] >= g.basso, o_h[j:] > g.alto
        if dentro.any():
            g.toccato = int(o_ini[j + int(np.argmax(dentro))])
        if oltre.any():
            g.riempito = int(o_ini[j + int(np.argmax(oltre))])
        fuori.append(g)
    return fuori


@dataclass
class Fase:
    numero: int            # 0 non toccato, 1 aggressione, 2 reazione automatica, 3 liquidazione, 4 continuazione
    divergenza: bool
    testo: str
    # L'estremo fatto nell'aggressione (il minimo per un gap rialzista): la liquidita' che la fase 3 va a prendere.
    estremo: Optional[float] = None


NOMI_FASI = {0: "non ancora toccato", 1: "aggressione", 2: "reazione automatica", 3: "liquidazione",
             4: "continuazione"}
# Su che grafico si leggono le fasi di un gap: due timeframe sotto il suo (il gap dei 3 mesi sul giornaliero,
# quello settimanale sul 4 ore, quello giornaliero sull'orario). Nella foto 1 della cartella 4 il minimo
# dell'aggressione nel gap dei 3 mesi e' il minimo di giugno, non quello di un'ora.
TF_FASE = {TF.D1: TF.H1, TF.W1: TF.H4, TF.MN: TF.D1, TF.Q3: TF.D1, TF.S6: TF.D1, TF.Y1: TF.W1}


def fase(q: Quadro, g: Gap, t: int) -> Fase:
    """A che fase e' il gap all'istante `t`, sulle orarie (il proprietario, 06/10/2026):

    1. aggressione: il prezzo entra nel gap per la prima volta, con forza;
    2. reazione automatica: per la prima volta reagisce nel verso del gap (gap rialzista, reazione al rialzo):
       una chiusura oltre il massimo della candela che ha fatto il minimo dell'aggressione;
    3. liquidazione: il prezzo va a prendere il minimo fatto nell'aggressione;
    4. continuazione: le tre fasi fatte, e l'RSI conferma (minimi decrescenti sul grafico, crescenti sull'RSI).
    Scritto per un gap rialzista; il ribassista e' lo specchio."""
    if g.toccato is None or g.toccato >= t:
        return Fase(0, False, "il prezzo non è ancora entrato nel gap")
    tf_fase = TF_FASE.get(g.tf, TF.H1)
    ore = q.candele[tf_fase]
    # La candela che contiene il primo tocco.
    i = max(int(np.searchsorted(ore.fine, g.toccato, side="right")), 0)
    m = int(np.searchsorted(ore.fine, t, side="right"))
    if i >= m:
        return Fase(1, False, "il prezzo è appena entrato nel gap (aggressione)")
    s = 1.0 if g.rialzista else -1.0
    # Tutto scritto per il gap rialzista: per il ribassista i prezzi cambiano segno.
    basso = (ore.bid[i:m, MINIMO] if g.rialzista else -ore.bid[i:m, MASSIMO])
    alto = (ore.bid[i:m, MASSIMO] if g.rialzista else -ore.bid[i:m, MINIMO])
    chiusura = ore.bid[i:m, CHIUSURA] * s
    r = q.rsi(tf_fase)[i:m] if g.rialzista else (100.0 - q.rsi(tf_fase)[i:m])
    # La reazione automatica: la prima chiusura oltre il massimo della candela del minimo fin li'.
    reazione, k_min = None, 0
    for j in range(len(basso)):
        if basso[j] <= basso[k_min]:
            k_min = j
        elif chiusura[j] > alto[k_min]:
            reazione = j
            break
    if reazione is None:
        return Fase(1, False, "il prezzo è entrato nel gap e non ha ancora reagito (aggressione)")
    minimo_aggr, k_aggr = basso[k_min], k_min
    estremo = float(minimo_aggr if g.rialzista else -minimo_aggr)
    dopo = basso[reazione + 1:]
    presi = np.flatnonzero(dopo < minimo_aggr)
    if not len(presi):
        return Fase(2, False, "il prezzo ha reagito per la prima volta nel verso del gap (reazione automatica)", estremo)
    k_liq = reazione + 1 + int(np.argmin(dopo))
    div = bool(np.isfinite(r[k_aggr]) and np.isfinite(r[k_liq]) and r[k_liq] > r[k_aggr])
    if div:
        return Fase(4, True, estremo=estremo, testo=_v(not g.rialzista,
                                "il prezzo ha preso il minimo dell'aggressione (liquidazione) e l'RSI non l'ha seguito: "
                                "minimi decrescenti sul grafico e crescenti sull'RSI, la continuazione",
                                "il prezzo ha preso il massimo dell'aggressione (liquidazione) e l'RSI non l'ha seguito: "
                                "massimi crescenti sul grafico e decrescenti sull'RSI, la continuazione"))
    return Fase(3, False, _v(not g.rialzista, "il prezzo ha preso il minimo dell'aggressione (liquidazione)",
                             "il prezzo ha preso il massimo dell'aggressione (liquidazione)"), estremo)


# --- il CRT delle foto ----------------------------------------------------------------------------------

@dataclass
class Setup:
    strumento: str
    tf: TF
    verso: Verso
    # Il range: la candela madre (con le inside bar dopo di lei) e la candela 2.
    range_inizio: int
    range_alto: float
    range_basso: float
    dentro: int                 # quante inside bar c'erano fra la madre e la candela 2
    n2_inizio: int
    n3_inizio: int
    n3_fine: int
    n2_alto: float
    n2_basso: float
    n2_chiusura: float
    entrata: float              # il prezzo d'entrata (bid; per comprare si paga l'ask)
    spread: float
    stop: float
    tp1: float
    presi: list = field(default_factory=list)   # i key level presi dalla candela 2
    h4_preso: Optional[float] = None            # per il CRT a 1 ora: il massimo (minimo) a 4 ore preso
    dal_dxy: bool = False                       # nato da un setup del DXY
    prima_inizio: int = 0                       # l'inizio della candela prima del range

    @property
    def short(self) -> bool:
        return self.verso is Verso.SHORT

    @property
    def ingresso(self) -> float:
        return self.entrata if self.short else self.entrata + self.spread

    def crt(self, basso_tf: TF = TF.H1) -> CRT:
        """Lo stesso setup come `CRT` del Cacciatore, per il resto del bot (disegni, messaggi, prove)."""
        estremo = self.n2_alto if self.short else self.n2_basso
        return CRT(self.strumento, self.tf, basso_tf, self.verso, self.range_inizio, self.range_alto,
                   self.range_basso, self.n3_inizio, self.n3_fine, Motivo.SCADENZA, self.n2_inizio, self.n3_fine,
                   np.array([self.n3_inizio], np.int64), np.array([estremo], np.float64))


def _madre(c: Candele, k1: int) -> int:
    """La candela madre: se la candela 1 e' una inside bar (ne' massimo ne' minimo nuovo), il range e' quella
    prima, e cosi' via."""
    m = k1
    while m > 0 and k1 - m < MADRE_MASSIMA:
        if c.bid[m - 1, MASSIMO] >= c.bid[m, MASSIMO] and c.bid[m - 1, MINIMO] <= c.bid[m, MINIMO]:
            m -= 1
        else:
            break
    return m


def _apertura(q: Quadro, t: int, ripiego: float) -> float:
    """Il prezzo d'apertura a `t` dalle orarie, se la prima ora e' gia' nota; se no la chiusura di prima."""
    ore = q.ore
    k = int(np.searchsorted(ore.inizio, t))
    if k < len(ore) and int(ore.inizio[k]) == t:
        return float(ore.bid[k, APERTURA])
    return ripiego


def trova(q: Quadro, tf: TF, dal: int, al: int) -> list[Setup]:
    """I CRT delle foto con la candela 3 che apre in [dal, al]."""
    c = q.candele.get(tf)
    if c is None or len(c) < 3:
        return []
    fuori = []
    we = weekend(q.strumento)
    # La candela 3 apre dove apre la candela dopo la 2 (dopo il fine settimana, la domenica sera).
    aperture = inizio_candela(c.fine, tf, we)
    a = int(np.searchsorted(aperture, dal, side="left"))
    b = int(np.searchsorted(aperture, al, side="right"))
    for k2 in range(max(a, 2), b):
        k1 = k2 - 1
        m = _madre(c, k1)
        alto, basso = float(c.bid[m, MASSIMO]), float(c.bid[m, MINIMO])
        if alto <= basso:
            continue
        o2, h2, l2, c2 = (float(x) for x in c.bid[k2])
        tolleranza = TOLLERANZA_CHIUSURA * (alto - basso)
        n3 = int(aperture[k2])
        n3_fine = fine_candela(n3, tf, we)
        spread = max(float(c.ask[k2, CHIUSURA] - c.bid[k2, CHIUSURA]), 0.0)
        entrata = _apertura(q, n3, c2)
        for verso in (Verso.SHORT, Verso.LONG):
            if verso is Verso.SHORT:
                valido = h2 > alto and basso < c2 <= alto + tolleranza and l2 > basso
                stop, tp1 = float(c.ask[k2, MASSIMO]), basso
                giusto = stop > entrata > tp1
            else:
                valido = l2 < basso and basso - tolleranza <= c2 < alto and h2 < alto
                stop, tp1 = l2, alto
                giusto = stop < entrata + spread < tp1
            if not (valido and giusto):
                continue
            s = Setup(q.strumento, tf, verso, int(c.inizio[m]), alto, basso, k1 - m, int(c.inizio[k2]), n3, n3_fine,
                      h2, l2, c2, entrata, spread, stop, tp1, prima_inizio=int(c.inizio[max(m - 1, 0)]))
            s.presi = key_level_presi(q, s)
            if tf is TF.H1:
                s.h4_preso = _h4_preso(q, s)
            fuori.append(s)
    return fuori


def key_level_presi(q: Quadro, s: Setup) -> list[Livello]:
    """I key level presi dalla candela 2: massimi (per vendere) o minimi (per comprare) dei periodi prima,
    dei timeframe almeno giornalieri e almeno grandi come quello del CRT (per la settimana e il mese la
    candela 1 e' gia' il periodo prima: WH, MH). Presi per la prima volta: *"il prezzo mi ha sbilanciato un
    KL, il daily high, e successivamente mi ha formato il CRT"* (foto 5 e 6 della cartella 4): il key level lo
    prende il CRT (la candela 1 o la 2) o la candela appena prima. Se il prezzo l'aveva superato prima ancora,
    li' non c'era piu' liquidita' da prendere."""
    minimo_tf = s.tf if _almeno(s.tf, TF.D1) else TF.D1
    ore = q.ore
    fuori = []
    candidati = livelli_prima(q, s.n2_inizio)
    if s.tf in (TF.H4, TF.H6, TF.H12):
        # Per i CRT a 4, 6 e 12 ore conta anche il massimo (minimo) di oggi fatto prima del range: *"per
        # l'entry H4 come KL ho usato il DH"* (foto 4 della cartella 3). Per quello a 1 ora no: il proprietario
        # vuole il KL giornaliero e il massimo (minimo) a 4 ore (`_h4_preso`).
        g = int(inizio_candela(np.array([s.n2_inizio]), TF.D1, weekend(q.strumento))[0])
        a, b = np.searchsorted(ore.inizio, [g, s.prima_inizio])
        if b > a:
            p = float(ore.bid[a:b, MASSIMO].max() if s.short else ore.bid[a:b, MINIMO].min())
            candidati.append(Livello(TF.D1, s.short, p, g, oggi=True))
    for liv in candidati:
        if not _almeno(liv.tf, minimo_tf) or liv.alto != s.short:
            continue
        if not ((s.n2_alto > liv.prezzo) if s.short else (s.n2_basso < liv.prezzo)):
            continue
        if liv.oggi:
            fuori.append(liv)
            continue
        # Fra la fine del suo periodo e la candela prima del range il prezzo non l'aveva gia' preso.
        fine = fine_candela(liv.inizio, liv.tf, weekend(q.strumento))
        a, b = np.searchsorted(ore.inizio, [fine, s.prima_inizio])
        prima = ore.bid[a:b, MASSIMO] if s.short else ore.bid[a:b, MINIMO]
        if len(prima) and ((prima.max() > liv.prezzo) if s.short else (prima.min() < liv.prezzo)):
            continue
        fuori.append(liv)
    return fuori


def _h4_preso(q: Quadro, s: Setup) -> Optional[float]:
    """Per il CRT a 1 ora: la candela 2 ha preso il massimo (minimo) dell'ultima candela a 4 ore chiusa?"""
    c = q.candele[TF.H4]
    k = int(np.searchsorted(c.fine, s.n2_inizio, side="right")) - 1
    if k < 0:
        return None
    livello = float(c.bid[k, MASSIMO] if s.short else c.bid[k, MINIMO])
    preso = s.n2_alto > livello if s.short else s.n2_basso < livello
    return livello if preso else None


# --- il target finale: il gap, se no il key level ----------------------------------------------------

@dataclass
class Obiettivo:
    prezzo: float
    tipo: str        # "gap", "key level" o "range"
    nome: str
    tf: Optional[TF] = None


def gap_contro(q: Quadro, s: Setup, t: Optional[int] = None) -> list[Gap]:
    """I gap gia' toccati e non ancora attraversati che fanno pressione contro di noi, davanti al primo
    target: per vendere i gap rialzisti sotto (*"pressione long al suo interno"*, foto 4 della cartella 3),
    per comprare quelli ribassisti sopra. Il prezzo li ha raggiunti e dentro puo' girare."""
    t = s.n3_inizio if t is None else t
    fuori = []
    for tf in TF_GAP:
        if not _sopra(tf, s.tf):
            continue
        for g in gap_di(q, tf, t):
            if g.toccato is None or g.riempito is not None:
                continue
            if s.short and g.rialzista and g.bordo < s.tp1:
                fuori.append(g)
            elif not s.short and not g.rialzista and g.bordo > s.tp1:
                fuori.append(g)
    fuori.sort(key=lambda g: abs(g.bordo - s.tp1))
    return fuori


def gap_target(q: Quadro, s: Setup, t: Optional[int] = None) -> list[Gap]:
    """I gap ancora intatti nel verso dell'operazione, oltre il primo target, dei timeframe sopra il CRT
    (almeno il giornaliero): per vendere i gap rialzisti sotto, per comprare quelli ribassisti sopra. Quelli
    oltre un gap che fa pressione contro di noi (`gap_contro`) non si contano: prima c'e' quello."""
    t = s.n3_inizio if t is None else t
    muro = gap_contro(q, s, t)
    fuori = []
    for tf in TF_GAP:
        if not _sopra(tf, s.tf):
            continue
        for g in gap_di(q, tf, t):
            if g.toccato is not None:
                continue
            if s.short and g.rialzista and g.bordo < s.tp1:
                fuori.append(g)
            elif not s.short and not g.rialzista and g.bordo > s.tp1:
                fuori.append(g)
    if muro:
        bordo = muro[0].bordo
        fuori = [g for g in fuori if ((g.bordo >= bordo) if s.short else (g.bordo <= bordo))]
    fuori.sort(key=lambda g: abs(g.bordo - s.tp1))
    return fuori


def kl_target(q: Quadro, s: Setup) -> Optional[Livello]:
    """Il key level target: l'altro lato del periodo piu' grande di cui la candela 2 ha preso la liquidita'
    (presa del ML -> il MH; presa del DH -> il DL: e' il CRT del timeframe del key level). L'anno solo per i
    CRT della settimana e del mese. None se sta prima del primo target."""
    tfs = [l.tf for l in s.presi if not l.oggi and (l.tf is not TF.Y1 or _almeno(s.tf, TF.W1))]
    if not tfs:
        return None
    tf = max(tfs, key=ORDINE.index)
    preso = next(l for l in s.presi if l.tf is tf and not l.oggi)
    altro = next((l for l in livelli_prima(q, s.n2_inizio, (tf,)) if l.alto != preso.alto), None)
    if altro is None or not ((altro.prezzo < s.tp1) if s.short else (altro.prezzo > s.tp1)):
        return None
    return altro


def liquidazione(q: Quadro, s: Setup) -> list[tuple[float, Gap]]:
    """Il gap che fa pressione contro di noi e' nella reazione automatica: la fase dopo e' la liquidazione,
    il prezzo va a prendere l'estremo fatto nell'aggressione (foto 1 della cartella 4: *"stiamo andando per la
    fase di liquidazione (3) dopo ... aggressione (1) - automatic reaction (2)"*, target il minimo dei 3 mesi;
    foto 4 della cartella 3 e 6 della 4: il WL dentro il gap settimanale)."""
    fuori = []
    for g in gap_contro(q, s):
        f = fase(q, g, s.n3_inizio)
        if f.numero == 2 and f.estremo is not None and ((f.estremo < s.tp1) if s.short else (f.estremo > s.tp1)):
            fuori.append((f.estremo, g))
    return fuori


def obiettivo_finale(q: Quadro, s: Setup) -> Obiettivo:
    """Il proprietario: *"il gap il target finale, ovvio che se non c'è gap il target è il kl"*.

    Il gap ancora intatto piu' vicino oltre il primo target; o, se davanti c'e' un gap toccato che ha appena
    reagito contro di noi, l'estremo della sua aggressione (la liquidazione): il piu' vicino dei due. Senza
    gap, il key level (`kl_target`). Senza neanche quello, tutto al primo target (foto 1 della cartella 3)."""
    candidati = [(g.bordo, Obiettivo(g.bordo, "gap", g.nome, g.tf)) for g in gap_target(q, s)]
    candidati += [(p, Obiettivo(p, "liquidazione", f"l'estremo dell'aggressione nel {g.nome}", g.tf))
                  for p, g in liquidazione(q, s)]
    if candidati:
        return min(candidati, key=lambda c: abs(c[0] - s.tp1))[1]
    k = kl_target(q, s)
    if k is not None:
        return Obiettivo(k.prezzo, "key level", k.nome, k.tf)
    return Obiettivo(s.tp1, "range", "l'altro lato del range", s.tf)


def target_dopo(q: Quadro, s: Setup, ob: Obiettivo) -> Optional[Obiettivo]:
    """Il target ancora piu' in la' di quello finale (per il terzo piano di Livelli): il gap intatto o il key
    level dei periodi prima (almeno giornaliero) piu' vicino oltre il target finale."""
    oltre = (lambda p: p < ob.prezzo) if s.short else (lambda p: p > ob.prezzo)
    candidati = [Obiettivo(g.bordo, "gap", g.nome, g.tf) for g in gap_target(q, s) if oltre(g.bordo)]
    for liv in livelli_prima(q, s.n3_inizio, TF_KL):
        if liv.alto != s.short and oltre(liv.prezzo):
            candidati.append(Obiettivo(liv.prezzo, "key level", liv.nome, liv.tf))
    if not candidati:
        return None
    return min(candidati, key=lambda o: abs(o.prezzo - ob.prezzo))


# I piani fra cui Livelli sceglie (nell'ordine di `nvm/vivo/giro.piani_foto`): sempre il TP1 all'altro lato del
# range; cambia dove va il resto. Si parte da quello delle foto e si cambia solo se un altro rende di piu' dal vivo.
PIANI = (
    ("tutto al TP1", "chiudo tutto al TP1, l'altro lato del range"),
    ("metà al TP1 e il resto al target finale", "metà al TP1 col pareggio e il resto al target finale, come nelle foto"),
    ("metà al TP1 e il resto più in là", "metà al TP1 col pareggio e il resto al target ancora più in là"),
)
PIANO_FOTO = 1


# --- la direzione: il timeframe di comando -----------------------------------------------------------

@dataclass
class Direzione:
    ok: bool
    comando: Optional[TF]
    testo: str
    a_favore: list = field(default_factory=list)
    contro: list = field(default_factory=list)


def biases(q: Quadro, t: int) -> dict:
    """La direzione dell'ultima candela chiusa di ogni timeframe di comando, a `t`."""
    fuori = {}
    for tf in TF_COMANDO:
        c = q.candele.get(tf)
        if c is None or len(c) < 2:
            continue
        k = int(np.searchsorted(c.fine, t, side="right")) - 1
        if k < 1:
            continue
        fuori[tf] = bias_candela(c, k)
    return fuori


def direzione(q: Quadro, s: Setup) -> Direzione:
    """Il timeframe di comando deve essere dalla nostra parte. Nelle foto il comando cambia (settimana, mese,
    3, 6, 12 mesi; per il CRT del giorno, della settimana e del mese anche il suo timeframe) e i timeframe
    piu' grandi possono andare contro (*"ritracciamento"*): basta che uno dei timeframe sopra il CRT spinga
    dalla nostra parte, o che ci sia un gap da riempire nel nostro verso. Quale conta di piu' lo impara il
    Bias dal vivo (`Metodo.numeri`)."""
    segno = -1 if s.short else 1
    b = biases(q, s.n3_inizio)
    a_favore, contro = [], []
    for tf, (v, testo) in b.items():
        if not _sopra(tf, s.tf):
            continue
        if v == segno:
            a_favore.append((tf, testo))
        elif v == -segno:
            contro.append((tf, testo))
    if a_favore:
        tf, testo = a_favore[0]
        return Direzione(True, tf, f"il {NOMI[tf]} {testo}", a_favore, contro)
    gaps = gap_target(q, s)
    if gaps:
        g = gaps[0]
        return Direzione(True, g.tf, f"c'è un {g.nome} ancora da riempire: il prezzo ci deve andare "
                                     "(ritracciamento)", a_favore, contro)
    liq = liquidazione(q, s)
    if liq:
        p, g = liq[0]
        return Direzione(True, g.tf, f"nel {g.nome} il prezzo ha fatto l'aggressione e la reazione automatica: "
                                     f"ora va a prendere l'estremo dell'aggressione ({numero(p)}), la liquidazione",
                         a_favore, contro)
    if contro:
        tf, testo = contro[0]
        return Direzione(False, tf, f"il {NOMI[tf]} {testo}: tutti i timeframe sopra spingono dall'altra parte",
                         a_favore, contro)
    return Direzione(False, None, "nessun timeframe sopra dà una direzione", a_favore, contro)


# --- il DXY sintetico ---------------------------------------------------------------------------------

# L'indice del dollaro (ICE): 50,14348112 x EURUSD^-0,576 x USDJPY^0,136 x GBPUSD^-0,119 x USDCAD^0,091 x
# USDSEK^0,042 x USDCHF^0,036. La corona svedese i broker di solito non ce l'hanno: si tiene ferma a 10.
PESI_DXY = {"EURUSD": -0.576, "USDJPY": 0.136, "GBPUSD": -0.119, "USDCAD": 0.091, "USDCHF": 0.036}
COSTANTE_DXY = 50.14348112 * 10 ** 0.042
# Le coppie col dollaro: un setup rialzista del DXY vende quelle col dollaro al denominatore e compra
# quelle col dollaro al numeratore (il proprietario, 06/10/2026). L'oro e l'argento sono "XAU/USD".
DOLLARO_SOTTO = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD")
DOLLARO_SOPRA = ("USDJPY", "USDCHF", "USDCAD")
PUNTO.setdefault("DXY", 1e-3)


def dxy(basi: dict) -> Optional[Minuti]:
    """Le orarie del DXY dalle coppie che il bot ha; None se ne manca una."""
    if not all(k in basi and len(basi[k]) for k in PESI_DXY):
        return None
    t = None
    for k in PESI_DXY:
        t = basi[k].t if t is None else np.intersect1d(t, basi[k].t)
    if t is None or not len(t):
        return None
    log = {c: np.zeros(len(t)) for c in ("o", "h", "l", "c")}
    for k, peso in PESI_DXY.items():
        m = basi[k]
        idx = np.searchsorted(m.t, t)
        p = m.bid[idx] * m.punto
        lo = np.log(p)
        log["o"] += peso * lo[:, APERTURA]
        log["c"] += peso * lo[:, CHIUSURA]
        # Il massimo del DXY arriva col minimo delle coppie che pesano in negativo, e viceversa.
        log["h"] += peso * (lo[:, MASSIMO] if peso > 0 else lo[:, MINIMO])
        log["l"] += peso * (lo[:, MINIMO] if peso > 0 else lo[:, MASSIMO])
    valori = np.c_[log["o"], log["h"], log["l"], log["c"]]
    prezzi = COSTANTE_DXY * np.exp(valori)
    punti = np.rint(prezzi / PUNTO["DXY"]).astype(np.int64)
    zeri = np.zeros(len(t), np.float32)
    passo = int(next(iter(basi.values())).passo)
    return Minuti("DXY", t.astype(np.int64), punti, punti.copy(), zeri, zeri.copy(), passo=passo)


def verso_dal_dxy(strumento: str, verso_dxy: Verso) -> Optional[Verso]:
    """Il verso su una coppia col dollaro quando il DXY ha un setup."""
    if strumento in DOLLARO_SOTTO:
        return Verso.SHORT if verso_dxy is Verso.LONG else Verso.LONG
    if strumento in DOLLARO_SOPRA:
        return verso_dxy
    return None


def dal_dxy(q: Quadro, s_dxy: Setup) -> Optional[Setup]:
    """Il setup del DXY portato su una coppia col dollaro: le stesse candele, i prezzi della coppia.
    Stop oltre l'estremo della candela 2 della coppia, primo target l'altro lato del suo range."""
    verso = verso_dal_dxy(q.strumento, s_dxy.verso)
    if verso is None:
        return None
    c = q.candele.get(s_dxy.tf)
    if c is None:
        return None
    k2 = int(np.searchsorted(c.inizio, s_dxy.n2_inizio))
    if k2 >= len(c) or int(c.inizio[k2]) != s_dxy.n2_inizio or k2 < 1:
        return None
    m = int(np.searchsorted(c.inizio, s_dxy.range_inizio))
    if m >= len(c) or int(c.inizio[m]) != s_dxy.range_inizio:
        m = k2 - 1
    alto, basso = float(c.bid[m, MASSIMO]), float(c.bid[m, MINIMO])
    h2, l2, c2 = float(c.bid[k2, MASSIMO]), float(c.bid[k2, MINIMO]), float(c.bid[k2, CHIUSURA])
    spread = max(float(c.ask[k2, CHIUSURA] - c.bid[k2, CHIUSURA]), 0.0)
    entrata = _apertura(q, s_dxy.n3_inizio, c2)
    short = verso is Verso.SHORT
    stop = float(c.ask[k2, MASSIMO]) if short else l2
    tp1 = basso if short else alto
    if not ((stop > entrata > tp1) if short else (stop < entrata + spread < tp1)):
        return None
    s = Setup(q.strumento, s_dxy.tf, verso, int(c.inizio[m]), alto, basso, k2 - 1 - m, s_dxy.n2_inizio,
              s_dxy.n3_inizio, s_dxy.n3_fine, h2, l2, c2, entrata, spread, stop, tp1, dal_dxy=True,
              prima_inizio=int(c.inizio[max(m - 1, 0)]))
    s.presi = key_level_presi(q, s)
    return s


def allineati(q: Quadro, s: Setup) -> list[TF]:
    """Gli altri timeframe con un CRT nello stesso verso: *"H4 e H6 formano entrambe un CRT ed aprono a
    12:00"*, *"CRT H4 + CRT e Model1 H1"*, *"3 mesi - 1 mese - 1W"*. Un timeframe piu' piccolo conta se la
    sua candela 3 e' partita durante la nostra candela 2 o insieme alla nostra 3 (anticipa); uno piu' grande
    se siamo dentro la sua candela 3 (il CRT piu' grande in corso)."""
    fuori = []
    for tf in (TF.H1, TF.H4, TF.H6, TF.H12, TF.D1, TF.W1, TF.MN):
        if tf is s.tf:
            continue
        if _sopra(tf, s.tf):
            c = q.candele.get(tf)
            if c is None or len(c) < 3:
                continue
            # Il CRT grande la cui candela 3 e' in corso: la sua candela 2 e' l'ultima chiusa.
            trovati = trova(q, tf, s.n3_inizio - 400 * 86400, s.n3_inizio)
            if any(x.verso is s.verso and x.n3_inizio <= s.n3_inizio < x.n3_fine for x in trovati):
                fuori.append(tf)
        else:
            if any(x.verso is s.verso for x in trova(q, tf, s.n2_inizio + 1, s.n3_inizio)):
                fuori.append(tf)
    return fuori


def numero(x: float) -> str:
    if not math.isfinite(x):
        return "?"
    return f"{x:,.5g}".replace(",", "§").replace(".", ",").replace("§", ".")
