"""Le invarianti dell'esecuzione: cose che sono bug in QUALUNQUE configurazione.

## A cosa serve

Col modo diagnostico (`APRI_OGNI_CRT`) il bot apre su ogni CRT che vede. Non
e' una strategia e non diventera' mai redditizio: in Romeo la selezione *e'*
la strategia, e un CRT qualsiasi su `M1` senza contesto perde in spread anche
con l'esecuzione perfetta. Guardare l'equity di quella modalita' non dice
niente.

Quello che quella modalita' dice invece benissimo e' **dove l'impianto
sbaglia**, perche' toglie i filtri che mascherano i difetti. Il TP1 dal lato
sbagliato -- dodici posizioni su diciassette morte in sei secondi -- e'
venuto fuori solo cosi': in esercizio `GEST-01` lo copriva rifiutando
l'operazione per un altro motivo, e il bug restava invisibile.

Questo file e' il quadrante di quella prova. Non misura il rendimento:
controlla un elenco di invarianti che devono valere con i filtri accesi e con
i filtri spenti allo stesso modo. Quando sono tutte verdi l'impianto e'
strutturalmente sano, e *allora* accendere i criteri ha senso -- perche' si
aggiunge selezione a un'esecuzione che funziona, invece che a una che sbaglia
in silenzio.

## Perche' i livelli si leggono da `decisione` e non da `posizione`

`posizione.sl` viene RISCRITTO quando GEST-04 porta lo stop a break even.
Letto li', uno stop dal lato sbagliato e uno stop spostato correttamente
dopo il parziale sono indistinguibili. I livelli di partenza -- quelli che
sono davvero andati al broker -- stanno in `decisione.sl` e `decisione.tp`.

## L'unica approssimazione, dichiarata

Il nozionale usa le dimensioni di contratto standard (100.000 unita' per le
coppie valutarie, 100 once per l'oro) invece di leggere `trade_contract_size`
dal broker. Serve a non dover aprire una seconda connessione a MT5 mentre il
bot e' vivo. Sulle sei coppie di PRIN-08 i valori coincidono; se un giorno il
broker cambiasse taglio, questo controllo andrebbe riletto da li'.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from core.parametri import COSTO_SPREAD_MASSIMO_IN_R, LEVA_MASSIMA

# Sotto questa vita una posizione non ha avuto il tempo di essere
# un'operazione: e' un sintomo, non un'invariante, e viene contato a parte.
VITA_SOSPETTA_SEC = 15.0


@dataclass
class Caso:
    """Una posizione con i livelli di partenza della sua decisione."""

    ticket: int
    simbolo: str
    direzione: str
    volume: float
    ingresso: float
    stop: Optional[float]
    target: Optional[float]
    tp1: Optional[float]
    spread: float
    aperta: str
    durata_sec: Optional[float]
    motivo_chiusura: str
    azione_decisa: Optional[str]

    @property
    def short(self) -> bool:
        return self.direzione.upper() == "SELL"

    def nozionale_usd(self) -> Optional[float]:
        """Il controvalore dell'ordine, in DOLLARI.

        Attenzione all'unita': il conto e' in euro, e confrontare un nozionale
        in dollari con un'equity in euro sovrastima la leva del cambio --
        circa il 15%. E' un errore che questo file ha fatto davvero: segnalava
        "23x l'equity" su posizioni che `core/rischio.py` aveva tagliato
        esattamente a 20x. Chi confronta deve passare da `nozionale_in_conto`.
        """
        base = self.simbolo.rstrip("+").upper()
        if base.startswith("XAU"):
            return self.volume * 100.0 * self.ingresso
        if base.startswith("USD"):          # USDJPY, USDCHF: la base e' il dollaro
            return self.volume * 100_000.0
        if base.endswith("USD"):            # EURUSD, GBPUSD, AUDUSD
            return self.volume * 100_000.0 * self.ingresso
        return None

    def nozionale_in_conto(self, eurusd: float) -> Optional[float]:
        """Lo stesso controvalore nella valuta del conto, per il confronto.

        `core/rischio.py` calcola `lotti x valore_punto x prezzo`, e
        `valore_punto` arriva da MT5 gia' nella valuta del conto: il suo
        nozionale e' in euro. Qui si arriva allo stesso numero dividendo per
        il cambio, senza dover aprire una seconda connessione al broker.
        """
        in_dollari = self.nozionale_usd()
        if in_dollari is None or eurusd <= 0:
            return None
        return in_dollari / eurusd


@dataclass
class Invariante:
    codice: str
    titolo: str
    perche: str
    prova: Callable[[Caso], Optional[str]]   # None = passata, stringa = come e' rotta
    rotti: list[tuple[Caso, str]] = field(default_factory=list)
    esaminati: int = 0


# ===========================================================================
# Le invarianti
# ===========================================================================

def _stop_dal_lato_giusto(c: Caso) -> Optional[str]:
    if c.stop is None:
        return "nessuno stop registrato nella decisione"
    if c.short and c.stop <= c.ingresso:
        return f"SELL con stop {c.stop:.5f} SOTTO l'ingresso {c.ingresso:.5f}"
    if not c.short and c.stop >= c.ingresso:
        return f"BUY con stop {c.stop:.5f} SOPRA l'ingresso {c.ingresso:.5f}"
    return None


def _target_dal_lato_giusto(c: Caso) -> Optional[str]:
    if c.target is None:
        return None                      # una posizione puo' non avere target finale
    if c.short and c.target >= c.ingresso:
        return f"SELL con target {c.target:.5f} SOPRA l'ingresso {c.ingresso:.5f}"
    if not c.short and c.target <= c.ingresso:
        return f"BUY con target {c.target:.5f} SOTTO l'ingresso {c.ingresso:.5f}"
    return None


def _tp1_verso_il_guadagno(c: Caso) -> Optional[str]:
    """Il parziale di GEST-04 non puo' stare alle spalle del prezzo.

    Se ci sta, `gestione.raggiunge_tp1` lo trova centrato al primo giro di
    sentinella: parziale chiuso e stop a break even, cioe' dentro lo spread.
    """
    if c.tp1 is None:
        return None                      # nessun parziale: legittimo
    if c.short and c.tp1 >= c.ingresso:
        return f"SELL con TP1 {c.tp1:.5f} SOPRA l'ingresso {c.ingresso:.5f}"
    if not c.short and c.tp1 <= c.ingresso:
        return f"BUY con TP1 {c.tp1:.5f} SOTTO l'ingresso {c.ingresso:.5f}"
    return None


def _stop_fuori_dallo_spread(c: Caso) -> Optional[str]:
    if c.stop is None:
        return None
    # Spread mancante: non e' un'esenzione, e' un dato che manca. Passare in
    # silenzio farebbe sembrare sana una posizione che non e' stata guardata
    # -- ed e' successo: il ticket 326904669 aveva uno stop a 0,00002 e
    # nessuno spread registrato, quindi risultava a posto.
    if c.spread <= 0:
        return "spread non registrato: il controllo non e' stato possibile"
    rischio = abs(c.ingresso - c.stop)
    if rischio <= 0:
        return "rischio nullo: ingresso e stop coincidono"
    costo = c.spread / rischio
    if costo > COSTO_SPREAD_MASSIMO_IN_R:
        return (f"lo spread costa {costo:.2f} R (lo stop dista "
                f"{rischio / c.spread:.1f} spread, il minimo e' "
                f"{1 / COSTO_SPREAD_MASSIMO_IN_R:.0f})")
    return None


def _leva_sotto_il_tetto(c: Caso, equity: float, eurusd: float) -> Optional[str]:
    nozionale = c.nozionale_in_conto(eurusd)
    if nozionale is None:
        return None
    volte = nozionale / equity
    if volte > LEVA_MASSIMA * 1.02:      # 2% di tolleranza sull'equity stimata
        return f"nozionale {volte:.1f}x l'equity, il tetto e' {LEVA_MASSIMA:.0f}x"
    return None


def _verso_coerente(c: Caso) -> Optional[str]:
    """L'ordine partito deve avere il verso che la decisione ha deciso.

    E' il controllo che avrebbe preso l'inversione su `USDCHF` e `USDJPY`:
    li' la conversione future -> CFD girava il verso degli ordini.
    """
    if c.azione_decisa is None:
        return None
    if c.azione_decisa.upper() != c.direzione.upper():
        return f"decisione {c.azione_decisa}, ordine {c.direzione}"
    return None


# ===========================================================================
# Lettura dell'archivio
# ===========================================================================

def carica(db: str, da: Optional[str]) -> list[Caso]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    dove = "WHERE p.aperta_utc >= ?" if da else ""
    parametri = (da,) if da else ()
    righe = conn.execute(f"""
        SELECT p.ticket, p.simbolo, p.direzione, p.volume_iniziale, p.volume,
               p.prezzo_ingresso, p.tp1, p.spread_ingresso, p.aperta_utc,
               p.chiusa_utc, p.motivo_chiusura,
               d.sl AS sl_deciso, d.tp AS tp_deciso, d.azione
          FROM posizione p
          LEFT JOIN decisione d ON d.ticket = p.ticket
          {dove}
         ORDER BY p.id
    """, parametri).fetchall()

    casi: list[Caso] = []
    for r in righe:
        durata = None
        if r["chiusa_utc"]:
            durata = (datetime.fromisoformat(r["chiusa_utc"])
                      - datetime.fromisoformat(r["aperta_utc"])).total_seconds()
        casi.append(Caso(
            ticket=int(r["ticket"]),
            simbolo=str(r["simbolo"]),
            direzione=str(r["direzione"]),
            # Il volume di partenza: quello attuale e' gia' ridotto dal parziale.
            volume=float(r["volume_iniziale"] or r["volume"]),
            ingresso=float(r["prezzo_ingresso"]),
            stop=None if r["sl_deciso"] is None else float(r["sl_deciso"]),
            target=None if r["tp_deciso"] is None else float(r["tp_deciso"]),
            tp1=None if r["tp1"] is None else float(r["tp1"]),
            spread=float(r["spread_ingresso"] or 0.0),
            aperta=str(r["aperta_utc"]),
            durata_sec=durata,
            motivo_chiusura=str(r["motivo_chiusura"] or ""),
            azione_decisa=None if r["azione"] is None else str(r["azione"]),
        ))
    return casi


# ===========================================================================
# Esecuzione e resoconto
# ===========================================================================

def cambio_eurusd(db: str, difetto: float = 1.15) -> float:
    """Il cambio piu' recente che l'archivio conosce, per la conversione.

    Si legge dalle posizioni su `EURUSD`, che sono prezzi davvero scambiati
    su questo conto. Se non ce ne sono si usa un valore di ripiego, e allora
    la leva va letta come un ordine di grandezza.
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    r = conn.execute(
        "SELECT prezzo_ingresso FROM posizione "
        "WHERE simbolo LIKE 'EURUSD%' ORDER BY id DESC LIMIT 1").fetchone()
    return float(r[0]) if r else difetto


def invarianti(equity: float, eurusd: float) -> list[Invariante]:
    return [
        Invariante(
            "EXE-01", "lo stop sta dal lato giusto dell'ingresso",
            "uno stop dalla parte del guadagno e' gia' toccato alla partenza",
            _stop_dal_lato_giusto),
        Invariante(
            "EXE-02", "il target sta dal lato giusto dell'ingresso",
            "un target alle spalle descrive un'operazione che non puo' vincere",
            _target_dal_lato_giusto),
        Invariante(
            "EXE-03", "TP1 sta in direzione del guadagno",
            "un parziale alle spalle scatta al primo giro e porta lo stop "
            "a break even dentro lo spread",
            _tp1_verso_il_guadagno),
        Invariante(
            "EXE-04", f"lo stop dista almeno {1/COSTO_SPREAD_MASSIMO_IN_R:.0f} spread",
            "sotto quella distanza l'oscillazione fra bid e ask basta a "
            "chiudere l'operazione",
            _stop_fuori_dallo_spread),
        Invariante(
            "EXE-05", f"il nozionale resta entro {LEVA_MASSIMA:.0f}x l'equity",
            "RISK-03 dimensiona sul rischio: uno stop minuscolo produce una "
            "size enorme",
            lambda c: _leva_sotto_il_tetto(c, equity, eurusd)),
        Invariante(
            "EXE-06", "il verso dell'ordine e' quello deciso",
            "la conversione future -> CFD ha gia' girato ordini su USDCHF e USDJPY",
            _verso_coerente),
    ]


def esegui(casi: list[Caso], equity: float, eurusd: float) -> list[Invariante]:
    prove = invarianti(equity, eurusd)
    for caso in casi:
        for inv in prove:
            esito = inv.prova(caso)
            inv.esaminati += 1
            if esito is not None:
                inv.rotti.append((caso, esito))
    return prove


def resoconto(casi: list[Caso], prove: list[Invariante]) -> int:
    print(f"posizioni esaminate: {len(casi)}")
    if casi:
        print(f"dalla {casi[0].aperta} alla {casi[-1].aperta}")
    print()

    larghezza = max(len(i.titolo) for i in prove)
    rotte = 0
    for inv in prove:
        quante = len(inv.rotti)
        rotte += quante > 0
        segno = "ok  " if quante == 0 else "ROTTA"
        print(f"  {segno} {inv.codice}  {inv.titolo:<{larghezza}}  "
              f"{quante}/{inv.esaminati}")
    print()

    for inv in prove:
        if not inv.rotti:
            continue
        print(f"--- {inv.codice}: {inv.titolo} ---")
        print(f"    perche' conta: {inv.perche}")
        for caso, esito in inv.rotti[:5]:
            print(f"    {caso.ticket} {caso.simbolo:9s} {caso.direzione:4s} {esito}")
        if len(inv.rotti) > 5:
            print(f"    ... e altre {len(inv.rotti) - 5}")
        print()

    # I sintomi: non sono invarianti, ma dicono se i difetti stanno ancora
    # uccidendo le posizioni prima che possano essere valutate.
    chiuse = [c for c in casi if c.durata_sec is not None]
    if chiuse:
        durate = sorted(c.durata_sec for c in chiuse)
        brevi = sum(1 for d in durate if d < VITA_SOSPETTA_SEC)
        print("--- sintomi (non invarianti) ---")
        print(f"    durata mediana: {durate[len(durate)//2]:.0f}s")
        print(f"    sotto i {VITA_SOSPETTA_SEC:.0f}s: {brevi}/{len(chiuse)}")
        esiti: dict[str, int] = {}
        for c in chiuse:
            esiti[c.motivo_chiusura or "(nessuno)"] = esiti.get(c.motivo_chiusura or "(nessuno)", 0) + 1
        for motivo, n in sorted(esiti.items(), key=lambda x: -x[1]):
            print(f"    {motivo}: {n}")
        print()

    if rotte:
        print(f"{rotte} invarianti su {len(prove)} sono rotte: l'impianto ha "
              "ancora difetti strutturali.")
    else:
        print("tutte le invarianti tengono: l'esecuzione e' sana, i filtri "
              "possono tornare ad essere il discorso.")
    return 1 if rotte else 0


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default="bot.db")
    p.add_argument("--da", default=None,
                   help="ISO UTC: esamina solo le posizioni aperte da qui in poi")
    p.add_argument("--equity", type=float, default=1000.0,
                   help="equity di riferimento per il controllo sulla leva")
    a = p.parse_args()

    casi = carica(a.db, a.da)
    if not casi:
        print("nessuna posizione nell'intervallo richiesto")
        return 0
    eurusd = cambio_eurusd(a.db)
    print(f"cambio EURUSD usato per la leva: {eurusd:.5f}")
    return resoconto(casi, esegui(casi, a.equity, eurusd))


if __name__ == "__main__":
    sys.exit(main())
