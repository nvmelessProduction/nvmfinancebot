"""Il Grilletto: sul CRT armato, e' scattato il Model#1?

Regole in `documenti/spec/grilletto.md`. Il Model#1 come lo disegna Romeo (msg 4836):
una candela bassa rialzista che spazza il `CRT high` e' il turtle soup, la
sua apertura e' il livello, e lo scatto e' la prima chiusura sotto il
livello. Per il long e' lo specchio.

Come il Cacciatore, ogni decisione usa solo candele gia' chiuse: lo scatto
di un CRT e' quello che il Grilletto avrebbe visto in quel momento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import CRT, MAI as MAI_3, Verso
from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import NEW_YORK, TF


@dataclass
class Scatto:
    crt: CRT
    # La candela bassa che ha rotto il livello: si entra alla sua chiusura.
    quando: int
    indice: int
    livello: float
    turtle_soup_inizio: int
    # Massimo e minimo della candela del turtle soup: servono allo stop stretto.
    turtle_soup_massimo: float
    turtle_soup_minimo: float
    # Quale entrata: "model1" (sul turtle soup del CRT, candela 2 o 3) o "candela 3" (il metodo dei
    # video: aspettata la chiusura della candela 2, turtle soup nella candela 3 oltre la sua apertura).
    modello: str = "model1"
    # Per la candela 3: la punta della candela del turtle soup (lo stop di Romeo), quanto era spessa
    # rispetto alle 20 candele prima, e l'apertura della candela 3.
    punta: Optional[float] = None
    spessore: float = 0.0
    apertura_3: Optional[float] = None


# Le entrate di Romeo nella candela 3 (`scatti_romeo`): il nome nello `Scatto.modello`.
MODELLI_ROMEO = ("candela 3", "vera rottura", "kiss of death")

# La candela del Model#1 dev'essere spessa: *"the thick candle that scares everyone"* (V1 37:18,
# V3 11:13, V8 18:21). Spessa = il corpo almeno tante volte il corpo medio delle 20 candele prima.
SPESSORE = 1.2
CANDELE_SPESSORE = 20


def _spessore(basse: Candele, n: int) -> float:
    corpi = np.abs(basse.bid[max(0, n - CANDELE_SPESSORE):n, CHIUSURA] - basse.bid[max(0, n - CANDELE_SPESSORE):n, APERTURA])
    medio = float(corpi.mean()) if len(corpi) else 0.0
    corpo = abs(float(basse.bid[n, CHIUSURA]) - float(basse.bid[n, APERTURA]))
    return corpo / medio if medio > 0 else 0.0


def apertura_romeo(crt: CRT, basse: Candele, orarie: Optional[Candele] = None) -> Optional[tuple[int, float]]:
    """L'apertura della candela 3 come la usa Romeo: (istante, prezzo).

    Il giorno apre a mezzanotte di New York (V1 10:02, 21:31); la settimana lunedi' a mezzanotte, *"not
    Sunday evening"* (V3 24:01, V8 14:30); il mese il primo giorno a mezzanotte. Le nostre candele aprono
    alle 17:00 di New York: l'apertura di Romeo arriva 7 ore dopo. La candela a 4 ore apre quando apre.
    Il prezzo si prende dalle orarie, se ci sono; se no dalla prima candela bassa che apre da li' in poi."""
    inizio_3 = int(crt.armato_quando)
    if crt.alto_tf in (TF.D1, TF.W1, TF.MN):
        t0 = int((datetime.fromtimestamp(inizio_3, tz=NEW_YORK) + timedelta(hours=7)).timestamp())
    else:
        t0 = inizio_3
    if orarie is not None and len(orarie):
        k = int(np.searchsorted(orarie.inizio, t0))
        if k < len(orarie) and int(orarie.inizio[k]) == t0:
            return t0, float(orarie.bid[k, APERTURA])
    k = int(np.searchsorted(basse.inizio, t0))
    if k < len(basse) and int(basse.inizio[k]) < crt.fine_candela_3:
        return int(basse.inizio[k]), float(basse.bid[k, APERTURA])
    return None


# Quante candele basse indietro si cercano i vecchi massimi (minimi) da prendere.
CANDELE_VECCHI = 60


def prende_vecchio(basse: Candele, n: int, short: bool, da: int = 0) -> Optional[float]:
    """La candela `n` si infila in un vecchio massimo (per vendere) mai ripreso? Restituisce il livello.

    *"You have an old high, and then you stab again into the old high"* (V3 10:00, V1 38:31): un massimo
    di swing (piu' alto delle due candele prima e delle due dopo), formato prima di `n` e mai superato
    fino a `n`, che la candela `n` supera. Per comprare e' lo specchio."""
    b = basse.bid
    h = b[:, MASSIMO] if short else -b[:, MINIMO]
    da = max(da, n - CANDELE_VECCHI, 2)
    preso = None
    for j in range(n - 3, da - 1, -1):
        if not (h[j] >= h[j - 2:j].max() and h[j] >= h[j + 1:j + 3].max()):
            continue
        if h[j + 1:n].max() > h[j]:
            continue                    # gia' ripreso prima
        if h[n] > h[j]:
            preso = h[j] if preso is None else max(preso, h[j])
    return None if preso is None else float(preso if short else -preso)


def _spesso_che_prende(basse: Candele, n: int, short: bool, apertura: float, da: int, spessore: float):
    """La candela del Model#1: spessa, nel colore della finta, che si infila in un vecchio massimo sopra
    l'apertura (per vendere). Restituisce lo spessore se lo e'."""
    o, c = float(basse.bid[n, APERTURA]), float(basse.bid[n, CHIUSURA])
    colore = (c > o and o >= apertura) if short else (c < o and o <= apertura)
    if not colore or prende_vecchio(basse, n, short, da) is None:
        return None
    k = _spessore(basse, n)
    return k if k >= spessore else None


def scatto_candela_3(crt: CRT, basse: Candele, spessore: Optional[float] = None,
                     orarie: Optional[Candele] = None) -> Optional[Scatto]:
    """Il Model#1 nella candela 3, come nei video (`documenti/spec/metodo_romeo.md`, 2 e 6).

    Il CRT dev'essere della variante `CHIUSURA_DENTRO`: la candela 2 ha spazzato un lato e ha chiuso
    dentro (V9 06:02). Nella candela 3, per vendere: dopo l'apertura di Romeo (`apertura_romeo`), una
    candela rialzista **spessa** sopra l'apertura si infila in un **vecchio massimo** (V3 10:00, V1 37:32);
    si entra alla prima chiusura sotto il suo corpo (V1 37:32 *"ignore the wicks, look at the bodies"*).
    Stop alla sua punta (V3 20:02). Se prima il prezzo ha gia' preso il 50% del range, il CRT ha gia'
    funzionato (V10 12:01): niente Model#1 (resta il kiss of death, `scatto_kod`). Per comprare e' lo
    specchio."""
    spessore = SPESSORE if spessore is None else spessore
    finestra = _finestra_3(crt, basse, orarie)
    if finestra is None:
        return None
    i, i0, j, t0, apertura_3 = finestra
    short = crt.verso is Verso.SHORT
    meta = crt.crt_50
    livello: Optional[float] = None
    ts = (0, 0.0, 0.0)
    punta, spessa = 0.0, 0.0
    for n in range(i, j):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        if livello is not None and (c < livello if short else c > livello):
            return Scatto(crt, int(basse.fine[n]), n, livello, *ts, modello="candela 3", punta=punta,
                          spessore=spessa, apertura_3=apertura_3)
        # Il 50% gia' preso: il CRT ha funzionato senza di noi.
        if (l <= meta) if short else (h >= meta):
            return None
        if n < i0:
            continue                    # prima dell'apertura di Romeo non si vende "sopra l'apertura"
        k = _spesso_che_prende(basse, n, short, apertura_3, 0, spessore)
        if k is not None:
            livello, ts, punta, spessa = o, (int(basse.inizio[n]), h, l), (h if short else l), k
    return None


def _finestra_3(crt: CRT, basse: Candele, orarie: Optional[Candele]):
    """Le candele basse della candela 3: (prima, prima dopo l'apertura di Romeo, fine, istante, apertura)."""
    if crt.fine_candela_3 >= MAI_3 or crt.armato_quando >= crt.decaduto_quando:
        return None
    i = int(np.searchsorted(basse.inizio, crt.armato_quando))
    j = int(np.searchsorted(basse.fine, crt.decaduto_quando, side="left"))
    j = min(j, int(np.searchsorted(basse.fine, crt.fine_candela_3, side="right")))
    if i >= len(basse) or i >= j:
        return None
    ap = apertura_romeo(crt, basse, orarie)
    if ap is None:
        return None
    t0, apertura_3 = ap
    i0 = int(np.searchsorted(basse.inizio, t0))
    return i, i0, j, t0, apertura_3


def scatto_vera_rottura(crt: CRT, basse: Candele, orarie: Optional[Candele] = None) -> Optional[Scatto]:
    """La seconda entrata di Romeo: la vera rottura di struttura e il ritorno (V11 15:32-16:38, V5 17:32).

    *"Every single entry you will ever take is either going to be a model number one or a true market
    structure shift"* (V11 14:30). Per vendere, nella candela 3 dopo l'apertura di Romeo: un massimo, un
    minimo, un massimo piu' alto sopra l'apertura che si infila nel vecchio massimo (il turtle soup), poi
    una chiusura sotto il minimo che aveva fatto il massimo: la rottura vera. Si entra quando il prezzo
    torna nella zona fra quel minimo e il turtle soup (*"the area between the high and the low"*), alla
    chiusura della candela che ci arriva e richiude sotto la meta' della zona; stop al turtle soup (*"if
    your stop loss is the turtle soup, it's unlikely that you get turtle souped"*). Niente se il 50% del
    range e' gia' preso o se il turtle soup viene superato."""
    finestra = _finestra_3(crt, basse, orarie)
    if finestra is None:
        return None
    i, i0, j, t0, apertura_3 = finestra
    short = crt.verso is Verso.SHORT
    s = 1.0 if short else -1.0
    b = basse.bid
    hi = (b[:, MASSIMO] if short else b[:, MINIMO]) * s      # verso la finta
    lo = (b[:, MINIMO] if short else b[:, MASSIMO]) * s      # verso l'obiettivo
    cl = b[:, CHIUSURA] * s
    meta = crt.crt_50 * s
    ts_n: Optional[int] = None       # la candela del turtle soup
    rottura: Optional[float] = None  # il minimo da rompere
    zona: Optional[tuple[float, float]] = None
    for n in range(i, j):
        if lo[n] <= meta:
            return None                 # il 50% gia' preso
        if zona is not None:
            if hi[n] > hi[ts_n]:
                return None             # turtle soup superato: l'idea non vale piu'
            met = (zona[0] + zona[1]) / 2
            if hi[n] >= met and cl[n] < met:
                return Scatto(crt, int(basse.fine[n]), n, float(met * s), int(basse.inizio[ts_n]),
                              float(b[ts_n, MASSIMO]), float(b[ts_n, MINIMO]), modello="vera rottura",
                              punta=float(hi[ts_n] * s), spessore=_spessore(basse, ts_n), apertura_3=apertura_3)
            continue
        if ts_n is not None and rottura is not None and cl[n] < rottura:
            zona = (rottura, float(hi[ts_n]))
            continue
        if n >= i0 and hi[n] >= apertura_3 * s and prende_vecchio(basse, n, short) is not None \
                and (ts_n is None or hi[n] > hi[ts_n]):
            # Il turtle soup: il minimo da rompere e' il piu' basso fra il vecchio massimo preso e lui.
            ts_n = n
            a = max(0, n - CANDELE_VECCHI)
            j_vecchio = a + int(np.argmax(hi[a:n])) if n > a else n
            rottura = float(lo[j_vecchio:n].min()) if n > j_vecchio else None
    return None


def scatto_kod(crt: CRT, basse: Candele, orarie: Optional[Candele] = None,
               spessore: Optional[float] = None) -> Optional[Scatto]:
    """Il kiss of death: l'ultimo turtle soup prima dell'obiettivo (V4 06:30-19:07, V9 17:31, V16 07:31).

    Per vendere: il prezzo ha gia' preso il 50% del range; rimbalza, una candela rialzista spessa si
    infila in un vecchio massimo (*"the final turtle soup before the target is hit... usually a very fast,
    vicious move into the target"*), e si entra alla chiusura sotto il suo corpo, verso il lato opposto
    del range. Stop alla sua punta, che non deve stare oltre il 50% piu' di quanto Romeo disegna: il KOD
    sta sotto il 50% (V4 19:07 *"lower 25% of the range... or as an OTE"*)."""
    spessore = SPESSORE if spessore is None else spessore
    finestra = _finestra_3(crt, basse, orarie)
    if finestra is None:
        return None
    i, i0, j, t0, apertura_3 = finestra
    short = crt.verso is Verso.SHORT
    meta = crt.crt_50
    obiettivo = crt.crt_low if short else crt.crt_high
    preso_50: Optional[int] = None
    livello: Optional[float] = None
    ts = (0, 0.0, 0.0)
    punta, spessa = 0.0, 0.0
    for n in range(i, j):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        if (l <= obiettivo) if short else (h >= obiettivo):
            return None                 # obiettivo gia' preso
        if preso_50 is None:
            if (l <= meta) if short else (h >= meta):
                preso_50 = n
            continue
        if livello is not None and (c < livello if short else c > livello):
            return Scatto(crt, int(basse.fine[n]), n, livello, *ts, modello="kiss of death", punta=punta,
                          spessore=spessa, apertura_3=apertura_3)
        if n > preso_50:
            colore = (c > o) if short else (c < o)
            sotto_50 = (h <= meta) if short else (l >= meta)
            if colore and sotto_50 and prende_vecchio(basse, n, short, preso_50) is not None:
                k = _spessore(basse, n)
                if k >= spessore:
                    livello, ts, punta, spessa = o, (int(basse.inizio[n]), h, l), (h if short else l), k
    return None


def scatti_romeo(crt: CRT, basse: Candele, orarie: Optional[Candele] = None) -> list[Scatto]:
    """Le entrate di Romeo su un CRT, al massimo una per modello: Model#1, vera rottura, kiss of death
    (il viaggio della candela, V5 10:30)."""
    fuori = [s for s in (scatto_candela_3(crt, basse, orarie=orarie), scatto_vera_rottura(crt, basse, orarie),
                         scatto_kod(crt, basse, orarie)) if s is not None]
    fuori.sort(key=lambda s: s.quando)
    return fuori


def scatto(crt: CRT, basse: Candele, dopo: Optional[int] = None) -> Optional[Scatto]:
    """Il Model#1 su un CRT, se scatta mentre il CRT e' armato.

    Con `dopo` si guardano solo le candele che aprono da quell'istante in poi:
    serve per sparare di nuovo dopo uno stop, con un turtle soup nuovo.
    """
    inizio = crt.manipolazione_inizio if dopo is None else max(crt.manipolazione_inizio, dopo)
    i = int(np.searchsorted(basse.inizio, inizio))
    # Le candele che chiudono prima che il CRT decada: quella che lo fa
    # decadere (per esempio toccando il lato opposto) e' gia' troppo tardi.
    j = int(np.searchsorted(basse.fine, crt.decaduto_quando, side="left"))
    short = crt.verso is Verso.SHORT
    livello: Optional[float] = None
    ts = (0, 0.0, 0.0)
    for n in range(i, j):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        # Si scatta solo sul CRT gia' armato. Col manuale e' sempre cosi'; con
        # la chiusura dentro il CRT si arma alla fine della candela 2, e una
        # chiusura sotto il livello prima di allora non si poteva usare.
        armato = int(basse.fine[n]) >= crt.armato_quando
        if livello is not None and armato and (c < livello if short else c > livello):
            return Scatto(crt, int(basse.fine[n]), n, livello, *ts)
        # La candela del turtle soup: rialzista oltre CRT high per uno short,
        # ribassista oltre CRT low per un long. Una piu' recente sposta il livello.
        if (c > o and h > crt.crt_high) if short else (c < o and l < crt.crt_low):
            livello, ts = o, (int(basse.inizio[n]), h, l)
    return None


def scatti(crt: list[CRT], basse: Candele) -> list[Scatto]:
    trovati = [s for c in crt if (s := scatto(c, basse)) is not None]
    trovati.sort(key=lambda s: (s.quando, s.crt.range_inizio, s.crt.verso.value))
    return trovati


def kod_superato(basse: Candele, short: bool) -> Optional[float]:
    """Dopo il primo obiettivo: il kiss of death e' stato superato? Restituisce il suo livello, se si'.

    *"Usually you don't want them to ever go above a kiss of death turtle soup... it's a good litmus test to
    see if the target is actually going to be reached"* (V16 15:32); *"had they closed above this high, then
    that would be a warning sign"* (V16 17:31). Sulle candele dopo il primo obiettivo, per vendere: ogni
    minimo nuovo azzera; il rimbalzo che segue fa un massimo; quando una candela fa un massimo piu' basso e
    chiude ribassista, quel massimo e' il kiss of death. Se poi una candela chiude sopra, l'obiettivo non
    arriva. Per comprare e' lo specchio."""
    s = 1.0 if short else -1.0
    estremo_obiettivo = float("inf")
    rimbalzo: Optional[float] = None
    kod: Optional[float] = None
    for n in range(len(basse)):
        o, h, l, c = (float(x) for x in basse.bid[n, [APERTURA, MASSIMO, MINIMO, CHIUSURA]])
        verso_obiettivo, verso_finta = (l, h) if short else (-h, -l)
        o, c = o * s, c * s
        if kod is not None and c > kod:
            return kod * s
        if verso_obiettivo < estremo_obiettivo:
            estremo_obiettivo, rimbalzo, kod = verso_obiettivo, None, None
            continue
        if rimbalzo is None or verso_finta > rimbalzo:
            rimbalzo = verso_finta
        elif c < o:
            kod = rimbalzo
    return None
