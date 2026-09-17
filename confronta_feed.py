"""Quanto diverse sono le candele di MT5 da quelle di Dukascopy?

## Perche' va girato PRIMA di spostare il motore su MT5

Ogni misura di questo progetto e' stata fatta su Dukascopy. `+0,3613 R` su
`4h -> 15m`, il 62,4% di winrate, il costo di spread di 0,071 R: tutti numeri
misurati su quelle candele.

Spostare il motore sul listino del broker non e' una scelta neutra. Le due
serie saranno vicine -- sono entrambe il vero mercato, non quotazioni
indicative -- ma "vicine" non e' "uguali", e su una strategia a stop e
bersaglio la differenza fra le due si paga negli esiti, non nella media.

C'e' un precedente nel progetto e dice quanto puo' pesare: confrontando le
barre della fonte gratuita con quelle di Dukascopy, il **37,7% degli esiti
cambiava** e 274 vittorie diventavano perdite. Quella era una fonte
aggregata con gli estremi attenuati, quindi il caso peggiore; qui sono due
feed veri e ci si aspetta molto meno. Ma "ci si aspetta" non e' un numero.

## Cosa misura

Sulle ore in cui entrambe le fonti hanno una candela:

- quante sono **identiche** in tutto;
- di quanto si scostano massimo e minimo, che sono cio' che fa toccare uno
  stop o un bersaglio;
- quante volte l'**ampiezza** differisce, perche' e' da li' che nascono i
  livelli del CRT.

Non decide al posto di nessuno: stampa i numeri su cui decidere.
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from datetime import datetime, timezone

from core import storage
from core.log import configura as configura_log
from core.mercato_mt5 import QUANTE, TIMEFRAME_MT5, in_candele
from core.parametri import TF, UNIVERSO
from core.simboli import simbolo_esecuzione


def archiviate(strumento: str, tf: TF) -> dict[datetime, tuple]:
    """Le candele in archivio, quelle su cui il progetto ha misurato."""
    fuori = {}
    for r in storage.candele_archiviate(strumento, tf.value):
        try:
            quando = datetime.fromisoformat(
                str(r["chiusura_utc"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        fuori[quando] = (float(r["apertura"]), float(r["massimo"]),
                         float(r["minimo"]), float(r["chiusura"]))
    return fuori


def scala_di(strumento: str) -> float:
    """Da unita' di prezzo a punti, per riportare gli scostamenti."""
    return 1e3 if strumento in ("USDJPY", "XAUUSD") else 1e5


def confronta(strumento: str, tf: TF, suffisso: str) -> None:
    from core import broker

    ok, barre, messaggio = broker.candele(
        simbolo_esecuzione(strumento, suffisso), TIMEFRAME_MT5[tf], QUANTE[tf])
    if not ok:
        print(f"  {strumento:8s} {tf.value:9s} MT5 non risponde: {messaggio}")
        return

    mt5 = {c.orario: (c.apertura, c.massimo, c.minimo, c.chiusura)
           for c in in_candele(barre, tf)}
    duka = archiviate(strumento, tf)
    comuni = sorted(set(mt5) & set(duka))
    if len(comuni) < 10:
        print(f"  {strumento:8s} {tf.value:9s} solo {len(comuni)} ore in comune: "
              f"non misurabile")
        return

    scala = scala_di(strumento)
    identiche = 0
    d_massimo, d_minimo, d_ampiezza = [], [], []
    for t in comuni:
        a, b = duka[t], mt5[t]
        if a == b:
            identiche += 1
        d_massimo.append(abs(a[1] - b[1]) * scala)
        d_minimo.append(abs(a[2] - b[2]) * scala)
        d_ampiezza.append(((a[1] - a[2]) - (b[1] - b[2])) * scala)

    ampiezza_media = st.mean((a[1] - a[2]) * scala for a in
                             (duka[t] for t in comuni))
    print(f"  {strumento:8s} {tf.value:9s} {len(comuni):5d} ore   "
          f"identiche {100 * identiche / len(comuni):5.1f}%   "
          f"massimo {st.mean(d_massimo):6.2f} pt   "
          f"minimo {st.mean(d_minimo):6.2f} pt   "
          f"(ampiezza media {ampiezza_media:.1f} pt)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tf", default="TF_H1",
                   help="quale timeframe confrontare (predefinito TF_H1)")
    scelte = p.parse_args()

    configura_log()
    storage.inizializza()

    from core.config import impostazioni

    try:
        tf = TF(scelte.tf)
    except ValueError:
        raise SystemExit(f"timeframe sconosciuto: {scelte.tf}")
    if tf not in TIMEFRAME_MT5:
        raise SystemExit(f"{tf.value} non ha un corrispondente su MT5")

    print(f"Dukascopy (archivio) contro MT5 (broker), su {tf.value}\n")
    suffisso = impostazioni().MT5_SUFFISSO_SIMBOLI
    for strumento in UNIVERSO:
        confronta(strumento, tf, suffisso)

    print()
    print("Come leggerlo:")
    print("  'identiche' vicino al 100%  -> i due listini sono lo stesso")
    print("     mercato e spostare il motore su MT5 non cambia le misure.")
    print("  scostamenti ben sotto l'ampiezza media -> le differenze ci sono")
    print("     ma sono piccole rispetto al movimento su cui si opera.")
    print("  scostamenti confrontabili con l'ampiezza -> le misure del")
    print("     progetto NON valgono su questo listino e vanno rifatte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
