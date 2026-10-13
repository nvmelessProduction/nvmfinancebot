"""Le foto del proprietario, una per una: cosa fanno il bot e la rete neurale su ognuna.

    python -m strumenti.foto --dati percorso/histdata          # tutte le foto (servono le ore di HistData)
    python -m strumenti.foto --dati dati/grezzi --solo 3/4 4/6   # solo alcune

Il proprietario, 13/10/2026: *"vedi una foto, vedi la rete neurale che fa, vedi un'altra foto ... fino a quando quello
che sta scritto su quelle foto non lo fa anche la rete neurale"*; *"quelli sono i trade che il bot e la rete neurale
devono fare. Sono esattamente quelli"*. Per ogni foto passa tutta la catena del bot dal vivo: il CRT, il key level,
la direzione, il target finale, il piano (`giro._decisione_foto`), le regole del metodo per la squadra
(`metodo.valuta_foto`) e la rete (`rete_vivo.Rete`). Una foto nuova si aggiunge con una riga in `FOTO`.

Le foto sono grafici dei future; i dati sono spot: il target si confronta entro mezzo range (piu' lo 0,4%), come in
`tests/test_foto.py`. Le foto sono in `documenti/casi/foto/`, riassunte in `documenti/casi/ESEMPI-PROPRIETARIO.md`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from nvm.agenti import foto as F
from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import PUNTO
from nvm.dati.ore import carica
from nvm.intelligenti import metodo
from nvm.tempo import TF
from nvm.vivo import giro

RADICE = Path(__file__).resolve().parent.parent
ROMA = ZoneInfo("Europe/Rome")
PUNTO.setdefault("DXY", 1e-3)
METALLI = ("XAUUSD", "XAGUSD")

# id, strumento, timeframe del CRT, apertura della candela 3 (ora italiana, come sulla foto), verso, se si entra,
# target finale sullo spot (None: non si entra).
FOTO = [
    ("2/1", "EURUSD", TF.W1, "2026-02-16 00:00", "S", True, 1.1404),
    ("2/2", "EURUSD", TF.MN, "2026-05-01 00:00", "S", True, 1.1373),
    ("2/3", "EURUSD", TF.W1, "2026-06-01 00:00", "S", True, 1.1412),
    ("2/5", "DXY", TF.MN, "2025-02-03 00:00", "S", True, 99.235),      # gap annuale
    ("2/6", "XAUUSD", TF.D1, "2026-08-26 00:00", "S", True, 4308.6),   # gap settimanale
    ("2/7", "XAUUSD", TF.H6, "2026-05-12 06:00", "S", True, 4101.0),   # gap dei 3 mesi
    ("2/8", "XAGUSD", TF.W1, "2026-05-18 00:00", "S", True, 61.28),    # gap dei 3 mesi, 1,1 R
    ("3/1", "EURUSD", TF.MN, "2025-12-01 00:00", "L", True, 1.1779),   # tutto al massimo del CRT
    ("3/2", "EURUSD", TF.W1, "2025-11-10 00:00", "L", True, 1.1798),
    ("3/3", "EURUSD", TF.D1, "2025-11-06 00:00", "L", True, 1.1803),
    ("3/4", "XAUUSD", TF.H4, "2026-09-03 20:00", "S", True, 4283.1),   # il WL dove il gap va a liquidare
    ("4/1", "EURUSD", TF.W1, "2026-09-14 00:00", "S", True, 1.1358),   # il minimo dei 3 mesi (liquidazione)
    ("4/5", "XAUUSD", TF.H4, "2026-09-18 12:00", "S", True, 4257.1),   # il DL (4294.5 sul future)
    ("4/6", "XAUUSD", TF.H1, "2026-09-10 09:00", "S", True, 4285.4),   # il WL, oltre il DL
    ("5/1", "GBPUSD", TF.MN, "2025-12-01 00:00", "L", True, 1.3793),
    ("5/2", "GBPUSD", TF.W1, "2025-11-10 00:00", "L", True, 1.3794),
    ("5/5", "XAUUSD", TF.H4, "2026-04-30 16:00", "S", True, 4100.5),
    ("5/6", "XAUUSD", TF.H4, "2026-05-01 20:00", "S", False, None),    # la candela 2 sfora: *"non deve sforare"*
    ("5/7", "XAUUSD", TF.H4, "2026-06-09 16:00", "S", True, 4100.5),
    ("5/8", "XAUUSD", TF.H4, "2026-09-02 08:00", "L", True, 4475.6),
    ("CASO-009", "XAUUSD", TF.H4, "2022-11-08 12:00", "L", True, 1683.7),
    # I tre trade aperti dal bot il 07/10/2026, con le correzioni del proprietario sui suoi grafici.
    ("franco-yen", "CHFJPY", TF.H1, "2026-10-07 11:00", "L", False, None),  # la bias errata: il 3 mesi accetta giu'
    ("euro-yen", "EURJPY", TF.H1, "2026-10-07 11:00", "L", True, 178.336),   # il DH: il gap settimanale e' mitigato
    ("euro-australiano", "EURAUD", TF.H1, "2026-10-07 11:00", "L", True, 1.61450),  # il DH: il gap ha accettato
]


def una(dati: Path, rete, nome, strumento, tf, quando, verso, deve, target, orari_tv: bool = False) -> tuple[bool, str]:
    """(giusto, la riga da stampare) per una foto. `orari_tv`: le candele come sui grafici di TradingView del
    proprietario (dalle 18 di New York, la mezzanotte italiana), come le vede il bot dal vivo dal 13/10/2026."""
    n3 = int(dt.datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA).timestamp())
    # Le foto hanno le candele dei future (mezzanotte italiana); senza gli orari di TradingView il forex ha quelle di
    # MT5 (le 23). Le orarie e i metalli (candele del future) non cambiano.
    if tf is not TF.H1 and strumento not in METALLI and not orari_tv:
        n3 -= 3600
    m, _ = carica(dati, strumento, int(dt.datetime(2010, 1, 1, tzinfo=dt.timezone.utc).timestamp()), n3 + 1,
                  solo_bid=True)
    if not len(m):
        return False, f"{nome}: mancano i dati di {strumento}"
    q = F.Quadro.da(m, n3)
    vv = Verso.SHORT if verso == "S" else Verso.LONG
    # Il mese e la settimana aprono la domenica sera o il primo del mese, la foto il primo giorno di borsa.
    prima = 4 * 86400 if tf in (TF.W1, TF.MN) else 3600
    trovati = [s for s in F.trova(q, tf, n3 - prima, n3 + 3600) if s.verso is vv and giro.setup_buono(s)]
    if not trovati:
        return not deve, f"{nome}: nessun setup"
    s = trovati[0]
    d = giro._decisione_foto(s, q, SimpleNamespace())
    ob = F.obiettivo_finale(q, s)
    if d is None:
        rr = abs(ob.prezzo - s.ingresso) / abs(s.ingresso - s.stop)
        return not deve, f"{nome}: nessun piano (target {F.numero(ob.prezzo)} a {rr:.2f} R)"
    regole = metodo.valuta_foto(d)
    mancano = ", ".join(x.nome for x in regole.mancano)
    g = rete.giudica(d) if rete is not None else None
    entra = regole.a_piu and (g is None or g.entra)
    giusto = entra == deve
    vicino = target is None or abs(ob.prezzo - target) <= 0.5 * (s.range_alto - s.range_basso) + 0.004 * target
    giusto = giusto and (not entra or vicino)
    riga = (f"{nome}: {'entra' if entra else 'lascia'}" + (f" (manca: {mancano})" if mancano else "") +
            f" | entrata {F.numero(d.op.ingresso)} stop {F.numero(d.op.stop)} TP1 {F.numero(d.op.tp1)} | target "
            f"{ob.nome} {F.numero(ob.prezzo)}" + (f" (foto {F.numero(target)})" if target else "") +
            ("" if g is None else f" | rete {'entra' if g.entra else 'lascia'}, stima {g.erre:+.2f} R"))
    return giusto, riga


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--dati", type=Path, default=RADICE / "dati" / "grezzi",
                   help="la cartella dei dati (quella di HistData ha tutti gli strumenti delle foto)")
    a.add_argument("--solo", nargs="*", help="solo queste foto (es. 3/4 euro-yen)")
    a.add_argument("--senza-rete", action="store_true", help="senza la rete neurale (senza PyTorch)")
    a.add_argument("--orari-tradingview", action="store_true",
                   help="candele dalle 18 di New York per tutto (tranne le crypto), come i grafici di TradingView")
    x = a.parse_args(argv)
    if x.orari_tradingview:
        from nvm.dati import candele
        from nvm.dati.candele import weekend
        for f in FOTO:
            if not weekend(f[1]):
                candele.SESSIONI[f[1]] = "18"
    rete = None
    if not x.senza_rete:
        from nvm.vivo.rete_vivo import Rete
        rete, perche = Rete.carica()
        if rete is None:
            print(f"Rete neurale spenta: {perche}. Provo solo le regole del bot.")
    giuste = tutte = 0
    for f in FOTO:
        if x.solo and f[0] not in x.solo:
            continue
        try:
            ok, riga = una(x.dati, rete, *f, orari_tv=x.orari_tradingview)
        except Exception as errore:
            ok, riga = False, f"{f[0]}: errore ({type(errore).__name__}: {errore})"
        giuste += ok
        tutte += 1
        print(("✅ " if ok else "❌ ") + riga, flush=True)
    print(f"\n{giuste} foto su {tutte} come le vuole il proprietario.")
    return 0 if giuste == tutte else 1


if __name__ == "__main__":
    sys.exit(main())
