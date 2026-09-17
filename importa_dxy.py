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
import gzip
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import storage
from core.definizioni import Candela
from core.duka_dxy import NOME_ARCHIVIO, PESI, componi
from core.fonte_dukascopy import MeseNonScaricato, orarie_del_mese
from core.log import configura as configura_log
from core.mercato_duka import costruisci

ORIGINE = "dukascopy"

# La serie gia' calcolata, che viaggia col repository. Esiste perche'
# Dukascopy limita gli indirizzi che chiedono troppo, e una VPS che ha gia'
# seminato vent'anni di storia puo' trovarsi la porta chiusa per ore -- o,
# se l'indirizzo appartiene a un intervallo di hosting, senza riaprirsi.
#
# Il file pesa poche centinaia di kilobyte perche' contiene solo l'indice,
# non i sei costituenti da cui nasce. Chi vuole ricalcolarlo da capo usa
# `--rete`: la formula e il metodo sono in `core/duka_dxy.py` e il risultato
# deve coincidere.
SERIE_PRONTA = Path("dati/dxy_orarie.csv.gz")


def scarica(
    da: int, a: int, paralleli: int = 4
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


def da_file(percorso: Path) -> list[Candela]:
    """Legge la serie oraria del DXY dal CSV che viaggia col repository."""
    apri = gzip.open if percorso.suffix == ".gz" else open
    fuori: list[Candela] = []
    with apri(percorso, "rt", encoding="utf-8") as file:
        intestazione = file.readline()
        if not intestazione.startswith("orario_utc"):
            raise SystemExit(f"{percorso}: intestazione inattesa: {intestazione!r}")
        for riga in file:
            pezzi = riga.strip().split(",")
            if len(pezzi) != 5:
                continue
            fuori.append(Candela(
                datetime.strptime(pezzi[0], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc),
                float(pezzi[1]), float(pezzi[2]), float(pezzi[3]), float(pezzi[4]),
            ))
    return fuori


def main() -> int:
    oggi = datetime.now(timezone.utc)
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # Cinque anni e' il minimo di DEF-26 per i timeframe di bias, ed e'
    # esattamente la bias che serve qui.
    p.add_argument("--da", type=int, default=oggi.year - 5)
    p.add_argument("--a", type=int, default=oggi.year)
    # Quattro, non dodici. Con dodici Dukascopy risponde 503 a raffica e il
    # risultato e' piu' lento, non piu' veloce: i mesi vanno riprovati tutti.
    # Se la fonte protesta comunque, il freno in `core/fonte_dukascopy.py`
    # rallenta da solo; questo numero e' solo il punto di partenza.
    p.add_argument("--paralleli", type=int, default=4,
                   help="quante richieste insieme (predefinito 4)")
    p.add_argument("--rete", action="store_true",
                   help="ricalcola dai sei costituenti invece di leggere "
                        f"{SERIE_PRONTA} (serve accesso a Dukascopy)")
    scelte = p.parse_args()

    configura_log()
    storage.inizializza()

    falliti: list[str] = []
    if scelte.rete or not SERIE_PRONTA.exists():
        print(f"DXY dai sei costituenti ({scelte.da}-{scelte.a})")
        serie, falliti = scarica(scelte.da, scelte.a, scelte.paralleli)
        dxy = componi(serie)
    else:
        print(f"DXY dalla serie gia' calcolata: {SERIE_PRONTA}")
        print("(per ricalcolarla dai sei costituenti: --rete)")
        dxy = da_file(SERIE_PRONTA)

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
        if not scelte.rete:
            print("  La serie nel repository non si aggiorna da sola: il")
            print("  ciclo di mercato la porta avanti un'ora alla volta, se")
            print("  Dukascopy risponde. Altrimenti `--rete` la ricalcola.")

    if completo:
        print("\nFatto. SETUP-19 ha la bias su cui decidere.")
        return 0

    print("\nARCHIVIO INCOMPLETO. Nulla e' andato perso: i mesi gia' presi")
    print("sono su disco in `dukascopy_ore` e il rilancio NON li richiede.")
    print("Rilancia `python importa_dxy.py`: riprovera' solo cio' che manca,")
    print("e ogni giro parte da piu' avanti del precedente.")
    print()
    print("Se i messaggi sono 'connessione chiusa' o 'host non risponde' e non")
    print("503, Dukascopy ha smesso di rispondere a questo indirizzo: e' una")
    print("misura temporanea contro chi chiede troppo. Insistere la allunga.")
    print("Aspetta un'ora e rilancia, oppure prova con meno richieste insieme:")
    print("    python importa_dxy.py --paralleli 2")
    print()
    print("Finche' questo messaggio compare, la bias del DXY e' vecchia o")
    print("assente e SETUP-19 non abilita nulla sulle cinque coppie FX.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
