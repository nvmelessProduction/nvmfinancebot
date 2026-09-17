"""Semina il DXY, calcolato dai suoi sei costituenti. Senza, il bot si astiene.

## Perche' questo script esiste

`SETUP-19` fa dipendere cinque coppie su sei dalla bias del dollar index, e
con bias DXY `NESSUNA` dice di **non operare su alcuna coppia**. Finche'
l'archivio del DXY e' vuoto, il bot si astiene sempre: l'unico strumento che
resta libero e' l'oro, che `PRIN-09` esenta.

Dukascopy pubblica `USDIDX` e sembra risolvere il problema. Non lo risolve:
quel file e' inerte — volume zero su tutti i record, un solo valore ripetuto
per l'intero mese, verificato su 2020, 2025 e 2026. In archivio avrebbe dato
una serie piatta, quindi una bias sempre `NESSUNA`, quindi lo stesso bot
fermo di prima con l'aria di essere a posto. E' il genere di dato che e'
peggio di nessun dato.

I sei costituenti dell'indice, invece, ci sono e sono veri. La formula sta in
`core/duka_dxy.py` insieme a cio' che di essa e' esatto e cio' che non lo e'.

## Quanta storia

`DEF-26` chiede cinque anni per i timeframe di bias, e la bias del DXY e'
esattamente cio' che serve qui: cinque anni sono il minimo, non il comodo.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import sys
from datetime import datetime, timezone

from core import storage
from core.definizioni import Candela
from core.duka_dxy import NOME_ARCHIVIO, PESI, componi
from core.fonte_dukascopy import MeseNonScaricato, orarie_del_mese
from core.log import configura as configura_log
from core.mercato_duka import costruisci

ORIGINE = "dukascopy"


def scarica(
    da: int, a: int, paralleli: int = 12
) -> tuple[dict[str, list[Candela]], list[str]]:
    """Le orarie dei sei costituenti fra due anni, e cosa non e' arrivato.

    I mesi non arrivati si restituiscono invece di ignorarli. Un mese che
    non arriva e un mese che non esiste producevano la stessa tupla vuota, e
    la conseguenza era un archivio troncato annunciato come completo: sei
    coppie a 10.000 ore ciascuna, la loro intersezione ferma a quarantasette
    giorni prima, e sotto la scritta "Fatto".
    """
    mesi = [(anno, m) for anno in range(da, a + 1) for m in range(1, 13)]
    serie: dict[str, list[Candela]] = {s: [] for s in PESI}
    falliti: list[str] = []
    lavori_totali = len(mesi) * len(PESI)
    fatti = 0

    with cf.ThreadPoolExecutor(max_workers=paralleli) as pool:
        lavori = {
            pool.submit(orarie_del_mese, s, anno, mese, "BID", True): (s, anno, mese)
            for s in PESI for anno, mese in mesi
        }
        for compito in cf.as_completed(lavori):
            simbolo, anno, mese = lavori[compito]
            try:
                serie[simbolo].extend(compito.result())
            except MeseNonScaricato:
                falliti.append(f"{simbolo} {anno}-{mese:02d}")
            fatti += 1
            if fatti % 24 == 0 or fatti == lavori_totali:
                print(f"    {fatti:4d}/{lavori_totali} mesi", flush=True)

    for s in serie:
        serie[s].sort(key=lambda c: c.orario)
        print(f"  {s:8s} {len(serie[s]):7d} ore")
    return serie, falliti


def main() -> int:
    oggi = datetime.now(timezone.utc)
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # Cinque anni e' il minimo di DEF-26 per i timeframe di bias, ed e'
    # esattamente la bias che serve qui.
    p.add_argument("--da", type=int, default=oggi.year - 5)
    p.add_argument("--a", type=int, default=oggi.year)
    scelte = p.parse_args()

    configura_log()
    storage.inizializza()

    print(f"DXY dai sei costituenti ({scelte.da}-{scelte.a})")
    serie, falliti = scarica(scelte.da, scelte.a)

    dxy = componi(serie)
    if not dxy:
        raise SystemExit(
            "nessuna ora in cui tutti e sei i costituenti abbiano una candela: "
            "l'indice non e' calcolabile e non si archivia nulla di finto")
    print(f"\n  DXY      {len(dxy):7d} ore "
          f"({dxy[0].orario:%Y-%m-%d} -> {dxy[-1].orario:%Y-%m-%d})")

    for tf, candele in costruisci(dxy).items():
        if not candele:
            continue
        righe = [{
            "strumento": NOME_ARCHIVIO, "tf": tf.value,
            "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "apertura": c.apertura, "massimo": c.massimo,
            "minimo": c.minimo, "chiusura": c.chiusura,
        } for c in candele]
        nuove, _ = storage.salva_candele(righe, origine=ORIGINE)
        print(f"  {tf.value:9s} {len(candele):7d} candele  ({nuove} nuove)")

    # --- Cio' che manca si dice PRIMA di dichiarare finito ----------------
    #
    # L'indice esiste solo nelle ore in cui TUTTI E SEI i costituenti hanno
    # una candela: un mese mancante a uno solo di essi cancella quel mese
    # dall'indice. Per questo il buco va detto qui e non lasciato dedurre dai
    # conteggi, che sembrano tutti generosi.
    ritardo = (oggi - dxy[-1].orario).total_seconds() / 86400
    completo = True

    if falliti:
        completo = False
        print(f"\n  {len(falliti)} mesi NON scaricati (rete, non assenza):")
        for f in sorted(falliti)[:12]:
            print(f"    {f}")
        if len(falliti) > 12:
            print(f"    ... e altri {len(falliti) - 12}")

    # Tre giorni coprono un fine settimana lungo. Oltre, l'indice e' vecchio.
    if ritardo > 3:
        completo = False
        print(f"\n  L'indice si ferma a {dxy[-1].orario:%Y-%m-%d %H:%M}, "
              f"{ritardo:.0f} giorni fa.")

    if completo:
        print("\nFatto. SETUP-19 ha la bias su cui decidere.")
        return 0

    print("\nARCHIVIO INCOMPLETO. Le candele scaricate sono in archivio e non")
    print("vanno perse: rilancia `python importa_dxy.py` e riprovera' SOLO i")
    print("mesi mancanti. Ripeti finche' questo messaggio non compare piu'.")
    print("Finche' compare, la bias del DXY e' vecchia o assente e SETUP-19")
    print("si comporta di conseguenza.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
