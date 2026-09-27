"""Il Rischio sul conto intero: le operazioni aperte insieme.

Una puntata giusta da sola puo' essere troppo se sul conto ci sono gia' operazioni che si
muovono insieme a lei: EURUSD e GBPUSD comprati insieme sono quasi una scommessa sola contro
il dollaro, e se il dollaro sale si perdono tutte e due. Il Rischio impara dai vent'anni
quanto gli esiti delle operazioni aperte nello stesso momento vanno insieme, secondo quello
che hanno in comune (`gambe`), e riduce la puntata di conseguenza: e' il criterio di Kelly per
piu' scommesse insieme. Nessun tetto fisso: quanto ridurre lo dicono i dati, e se conviene lo
dice la simulazione del conto intero (`simula`), con tutte le operazioni dei vent'anni.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from nvm.agenti.rischio import PARTI
from nvm.dati.strumenti import STRUMENTI

# Quanto due operazioni hanno in comune: da -1 (una e' il contrario dell'altra) a +1 (la stessa).
CLASSI = (-1.0, -0.5, 0.0, 0.5, 1.0)


def gambe(strumento: str, verso: int) -> dict[str, float]:
    """Su cosa scommette un'operazione: +1 su quello che compra, -1 su quello che vende.
    EURUSD in acquisto compra euro e vende dollari; un indice o il petrolio in acquisto
    comprano loro e vendono la valuta in cui sono quotati."""
    s = STRUMENTI.get(strumento)
    if s is not None and s.famiglia in ("indici", "petrolio"):
        base, quota = strumento, s.codice[-3:]
    else:
        base, quota = strumento[:3], strumento[3:6]
    return {base: float(verso), quota: -float(verso)}


def in_comune(a: dict[str, float], b: dict[str, float]) -> float:
    """Da -1 a +1: quanto due operazioni scommettono sulle stesse cose, nello stesso verso."""
    return sum(v * b.get(k, 0.0) for k, v in a.items()) / 2


def _classe(s: float) -> float:
    return min(CLASSI, key=lambda c: abs(c - s))


@dataclass
class Operazioni:
    """Le operazioni di un conto, in ordine di ingresso: quando entrano e escono, lo strumento
    e il verso, la puntata di Kelly piena con le stime del Capo, e il risultato in R."""

    entrata: np.ndarray
    chiusa: np.ndarray
    strumento: np.ndarray
    verso: np.ndarray
    kelly: np.ndarray
    erre: np.ndarray

    def __post_init__(self):
        o = np.argsort(self.entrata, kind="stable")
        for k in ("entrata", "chiusa", "strumento", "verso", "kelly", "erre"):
            setattr(self, k, np.asarray(getattr(self, k))[o])

    def __len__(self) -> int:
        return len(self.entrata)

    def fino_a(self, istante: int) -> "Operazioni":
        """Solo quelle gia' chiuse prima di `istante`: il passato, per imparare senza sbirciare."""
        m = self.chiusa < istante
        return Operazioni(*(getattr(self, k)[m] for k in ("entrata", "chiusa", "strumento", "verso", "kelly", "erre")))


def correlazioni(op: Operazioni, minimo: int = 30) -> dict[float, float]:
    """Per ogni classe (quanto due operazioni hanno in comune), quanto sono andati insieme i
    loro risultati quando erano aperte nello stesso momento: la media dei prodotti dei
    risultati standardizzati. Con meno di `minimo` coppie la classe vale quanto dice il suo nome."""
    if len(op) < 2:
        return {c: c for c in CLASSI}
    z = (op.erre - op.erre.mean()) / (op.erre.std() or 1.0)
    g = [gambe(s, v) for s, v in zip(op.strumento, op.verso)]
    somme = {c: [0.0, 0] for c in CLASSI}
    for i in range(len(op)):
        # Le operazioni entrate mentre la i-esima era aperta (le entrate sono in ordine).
        j = i + 1
        fine = np.searchsorted(op.entrata, op.chiusa[i], side="left")
        for j in range(i + 1, fine):
            c = _classe(in_comune(g[i], g[j]))
            somme[c][0] += z[i] * z[j]
            somme[c][1] += 1
    return {c: (s / n if n >= minimo else c) for c, (s, n) in somme.items()}


def puntata(kelly: float, parte: float, gamba: dict[str, float], aperte: list[tuple[dict[str, float], float]],
            corr: Optional[dict[float, float]]) -> float:
    """La frazione del conto da rischiare, con le operazioni gia' aperte (gambe, frazione a
    rischio). Da sola e' `parte` x Kelly; con le altre aperte si toglie quanto rischiano,
    pesato da quanto vanno insieme (il Kelly di piu' scommesse: f = parte x K - somma rho x f_j).
    Senza `corr` le operazioni si trattano come se fossero sole (il modo di prima)."""
    return max(parte * kelly - riduzione(gamba, aperte, corr), 0.0)


def riduzione(gamba: dict[str, float], aperte: list[tuple[dict[str, float], float]],
              corr: Optional[dict[float, float]]) -> float:
    """Quanto togliere alla puntata per le operazioni gia' aperte: quello che rischiano, pesato
    da quanto vanno insieme a questa (negativo se la bilanciano)."""
    if not corr:
        return 0.0
    return sum(corr[_classe(in_comune(gamba, g))] * fj for g, fj in aperte)


def legate(gamba: dict[str, float], aperte: list[tuple[str, dict[str, float]]], corr: Optional[dict[float, float]],
           soglia: float = 0.1) -> list[str]:
    """Gli strumenti aperti che vanno insieme a questa operazione (per dirlo in equipe)."""
    if not corr:
        return []
    return [k for k, g in aperte if corr[_classe(in_comune(gamba, g))] >= soglia]


@dataclass
class Conto:
    """Com'e' andato il conto intero nella simulazione."""

    crescita: float          # la crescita media all'anno, in logaritmo (0,10 = circa +10,5%)
    finale: float            # il conto alla fine, partendo da 1
    peggior_calo: float      # il calo piu' grande dal massimo, in frazione (0,30 = -30%)
    peggior_giorno: float    # la giornata peggiore, in frazione del conto
    massimo_a_rischio: float  # la parte del conto piu' alta mai a rischio insieme
    prese: int
    anni: dict               # anno -> crescita di quell'anno, in logaritmo
    # anno -> il conto (in logaritmo, da inizio anno) a ogni chiusura: per rimescolare gli anni.
    percorsi: dict = field(default_factory=dict, repr=False)


def simula(op: Operazioni, parte: float, corr: Optional[dict[float, float]], minimo: float = 0.0) -> Conto:
    """Il conto intero, operazione per operazione, con quelle aperte insieme: la puntata si
    decide all'ingresso sul conto di quel momento, il risultato arriva all'uscita. Le operazioni
    con il Kelly pieno sotto `minimo` non prendono soldi (fiducia troppo bassa)."""
    conto, massimo, calo, a_rischio_max = 1.0, 1.0, 0.0, 0.0
    aperte: list = []           # (uscita, n, soldi a rischio, gambe, R)
    per_giorno: dict[int, list] = {}
    anni: dict[int, list] = {}
    percorsi: dict[int, list] = {}
    prese, n = 0, 0

    def chiudi(fino: float) -> None:
        nonlocal conto, massimo, calo
        while aperte and aperte[0][0] <= fino:
            uscita, _, soldi, _, r = heapq.heappop(aperte)
            prima = conto
            conto += soldi * r
            if conto <= 0:
                conto = 0.0
            giorno = int(uscita // 86400)
            g = per_giorno.setdefault(giorno, [prima, conto])
            g[1] = conto
            a = datetime.fromtimestamp(int(uscita), tz=timezone.utc).year
            inizio = anni.setdefault(a, [prima, conto])
            inizio[1] = conto
            percorsi.setdefault(a, []).append(np.log(conto / inizio[0]) if conto > 0 and inizio[0] > 0 else -np.inf)
            massimo = max(massimo, conto)
            calo = max(calo, 1 - conto / massimo)

    for i in range(len(op)):
        chiudi(op.entrata[i])
        if conto <= 0:
            break
        if op.kelly[i] < minimo:
            continue
        gamba = gambe(op.strumento[i], int(op.verso[i]))
        in_corso = [(g, soldi / conto) for _, _, soldi, g, _ in aperte]
        f = puntata(float(op.kelly[i]), parte, gamba, in_corso, corr)
        if f <= 0:
            continue
        soldi = f * conto
        n += 1
        heapq.heappush(aperte, (float(op.chiusa[i]), n, soldi, gamba, float(op.erre[i])))
        prese += 1
        a_rischio_max = max(a_rischio_max, sum(x[2] for x in aperte) / conto)
    chiudi(np.inf)
    peggiore = min((fine / inizio - 1 for inizio, fine in per_giorno.values() if inizio > 0), default=0.0)
    durata = (float(op.chiusa.max()) - float(op.entrata.min())) / (365.25 * 86400) if len(op) else 1.0
    crescita = (np.log(conto) / max(durata, 1e-9)) if conto > 0 else -np.inf
    per_anno = {a: (np.log(f / i) if i > 0 and f > 0 else -np.inf) for a, (i, f) in sorted(anni.items())}
    return Conto(float(crescita), conto, calo, -peggiore, a_rischio_max, prese, per_anno,
                 {a: np.array(v) for a, v in percorsi.items()})


# --- Le storie sfortunate -----------------------------------------------------------------------

# Il profilo di rischio: il calo dal massimo che il conto non deve superare nemmeno nelle storie
# sfortunate. E' una scelta dell'utente (quanto e' disposto a vedere scendere il conto), non
# un'opinione del bot: il Rischio cerca la crescita piu' alta che la rispetta.
CALO_MASSIMO = 0.20
# Quante storie e quale sfortuna: gli anni rimescolati a caso, e il 10% peggiore.
STORIE = 500
SFORTUNA = 0.9


def sfortuna(c: Conto, rng: np.random.Generator, storie: int = STORIE, q: float = SFORTUNA) -> tuple[float, float]:
    """Il calo dal massimo e la crescita all'anno nelle storie sfortunate: gli stessi anni presi
    a caso, `storie` volte, come se il passato fosse andato in un altro ordine e con altri anni
    ripetuti. Il calo che si supera solo nel 10% delle storie, la crescita che si fa almeno nel 90%."""
    anni = sorted(a for a in c.percorsi if len(c.percorsi[a]))
    if not anni:
        return 0.0, 0.0
    scelte = rng.integers(0, len(anni), size=(storie, len(anni)))
    fine = np.array([c.percorsi[a][-1] for a in anni])
    cali = np.empty(storie)
    for k, riga in enumerate(scelte):
        pezzi, base = [], 0.0
        for j in riga:
            pezzi.append(base + c.percorsi[anni[j]])
            base += fine[j]
        cammino = np.concatenate([[0.0]] + pezzi)
        if not np.isfinite(cammino).all():
            cali[k] = 1.0
            continue
        cali[k] = 1 - np.exp((cammino - np.maximum.accumulate(cammino)).min())
    crescite = fine[scelte].sum(axis=1) / len(anni)
    return float(np.quantile(cali, q)), float(np.quantile(crescite, 1 - q))


@dataclass
class Scelta:
    """Quello che il Rischio ha imparato sul conto intero."""

    minimo: float            # il Kelly pieno sotto cui un'operazione non prende soldi
    parte: float             # la parte del Kelly
    correlazioni: bool       # se tiene conto delle operazioni legate gia' aperte
    conto: Conto             # com'e' andato il conto vero dei vent'anni
    calo_sfortunato: float
    crescita_sfortunata: float


SOGLIE = (0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.13, 0.16)
PARTI_CONTO = (0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.07, 0.1, 0.15, 0.2)


def scegli(op: Operazioni, corr: Optional[dict[float, float]], calo: float = CALO_MASSIMO,
           soglie=SOGLIE, parti=PARTI_CONTO, seme: int = 0) -> Scelta:
    """La fiducia minima, la parte del Kelly e se guardare le operazioni legate: la combinazione
    che fa crescere di piu' il conto nelle storie sfortunate senza superare `calo` nemmeno in
    quelle. Se nessuna ci sta, la meno rischiosa. Con e senza correlazioni: decidono i dati."""
    migliore, prudente = None, None
    for usa in ((False, True) if corr else (False,)):
        for m in soglie:
            for p in parti:
                c = simula(op, float(p), corr if usa else None, float(m))
                cs, gs = sfortuna(c, np.random.default_rng(seme))
                s = Scelta(float(m), float(p), usa, c, cs, gs)
                if cs <= calo and (migliore is None or gs > migliore.crescita_sfortunata):
                    migliore = s
                if prudente is None or cs < prudente.calo_sfortunato:
                    prudente = s
    return migliore or prudente


def impara(op: Operazioni, corr: Optional[dict[float, float]], parti=PARTI) -> tuple[float, Conto]:
    """La parte del Kelly che fa crescere di piu' il conto intero (senza guardare la sfortuna)."""
    migliore = None
    for p in parti:
        c = simula(op, float(p), corr)
        if migliore is None or c.crescita > migliore[1].crescita:
            migliore = (float(p), c)
    return migliore


def _riassunto(c: Conto) -> dict:
    return {"crescita": float(c.crescita), "peggior_calo": float(c.peggior_calo),
            "peggior_giorno": float(c.peggior_giorno), "massimo_a_rischio": float(c.massimo_a_rischio), "prese": c.prese}


def come_dati(s: Scelta, corr: Optional[dict[float, float]], prima: Optional[tuple] = None, quando: Optional[int] = None) -> dict:
    """Quello che il Rischio ha imparato, per il bot dal vivo (`rischio.json`)."""
    import time
    d = {"quando": int(time.time() if quando is None else quando), "parte": s.parte, "minimo": s.minimo,
         "correlazioni": {str(c): float(r) for c, r in corr.items()} if (corr and s.correlazioni) else None,
         "calo_massimo": CALO_MASSIMO, "calo_sfortunato": s.calo_sfortunato,
         "crescita_sfortunata": s.crescita_sfortunata, "conto": _riassunto(s.conto)}
    if prima is not None:
        d["prima"] = {"parte": prima[0], **_riassunto(prima[1])}
    return d
