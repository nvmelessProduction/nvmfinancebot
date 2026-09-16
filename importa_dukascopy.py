"""Semina l'archivio con i prezzi di Dukascopy: scambi veri, spread vero.

## Perche' esiste, accanto a `scarica_storico.py`

`scarica_storico.py` prende i **future** da una fonte gratuita che serve barre
aggregate. Va bene per avere una storia, ma ha un limite scoperto misurando:
un feed puo' avere gli **estremi attenuati**, cioe' massimi e minimi campionati
invece che realmente toccati. Su una strategia a stop e bersaglio quel difetto
e' letale — misurato sullo spot di Yahoo, il **37,7%** degli esiti cambiava, e
un vantaggio inesistente sembrava reale (vedi
`docs/SPOT-CONTRO-FUTURE-2026-09-16.md`).

Dukascopy serve il proprio book: prezzi che qualcuno ha davvero pagato, e
**BID e ASK separati**. Due cose che nessun'altra fonte gratuita da':

- gli estremi sono quelli toccati, non campionati;
- lo spread si **misura** invece di assumerlo, ora per ora e strumento per
  strumento.

## Che strumento e', esattamente

**Non e' il future CME.** E' il book di un broker, quindi e' della stessa
famiglia del CFD su cui `DEF-34` fa eseguire. Per questo le candele si
archiviano sotto il **nome del CFD** (`EURUSD`, `XAUUSD`) e non sotto quello
del future (`6E`, `GC`): mischiarle sarebbe esattamente il genere di scambio
di identita' che questo progetto ha gia' pagato caro.

Usarle per l'**analisi** contraddice `DEF-32`, che vuole il future. E' una
scelta che spetta a chi opera, e va presa guardando la misura, non per comodita'.

## Il confine della giornaliera

Costruita con il taglio delle **22:00 UTC**, che e' la convenzione del mercato
forex (17:00 New York) e quindi il confine su cui stanno i massimi e minimi
giornalieri che gli operatori guardano davvero. E' esatto d'inverno e sbaglia
di un'ora durante l'ora legale americana: la stessa approssimazione, dichiarata,
di `aggregazione.aggrega_orarie`.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Sequence

from core import storage
from core.definizioni import Candela
from core.log import configura as configura_log
from core.log import diario
from core.parametri import TF

sys.path.insert(0, "backtest")
from dukascopy import orarie, scala_di          # noqa: E402

log = diario("dukascopy")

SIMBOLI = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD"]
ORIGINE = "dukascopy"
TAGLIO_GIORNALIERO = 22                          # 17:00 New York, in UTC d'inverno


def _giorno_di(momento: datetime) -> datetime:
    """La giornata forex a cui appartiene un'ora, marcata sulla sua chiusura."""
    confine = momento.replace(hour=TAGLIO_GIORNALIERO, minute=0, second=0, microsecond=0)
    if momento > confine:
        confine += timedelta(days=1)
    return confine


def _raggruppa(candele: Sequence[Candela], chiave) -> tuple[Candela, ...]:
    """Aggrega per una chiave qualsiasi, scartando l'ultimo gruppo in formazione."""
    gruppi: dict = {}
    for c in candele:
        gruppi.setdefault(chiave(c), []).append(c)
    ordinate = sorted(gruppi)
    fuori = []
    for k in ordinate[:-1]:                      # l'ultimo periodo non e' chiuso
        g = gruppi[k]
        fuori.append(Candela(orario=g[-1].orario, apertura=g[0].apertura,
                             massimo=max(x.massimo for x in g),
                             minimo=min(x.minimo for x in g),
                             chiusura=g[-1].chiusura))
    return tuple(fuori)


def costruisci(orarie_bid: Sequence[Candela]) -> dict[TF, tuple[Candela, ...]]:
    """Dalle orarie ai timeframe che il motore usa."""
    giornaliere = _raggruppa(orarie_bid, lambda c: _giorno_di(c.orario))
    return {
        TF.H1: tuple(orarie_bid[:-1]) if orarie_bid else (),
        TF.H4: _raggruppa(orarie_bid, lambda c: (
            (c.orario - timedelta(microseconds=1)).date(),
            (c.orario - timedelta(microseconds=1)).hour // 4)),
        TF.D1: giornaliere,
        TF.W1: _raggruppa(giornaliere, lambda c: (c.orario - timedelta(microseconds=1)).isocalendar()[:2]),
        TF.M1: _raggruppa(giornaliere, lambda c: (
            (c.orario - timedelta(microseconds=1)).year,
            (c.orario - timedelta(microseconds=1)).month)),
    }


def spread_misurato(bid: Sequence[Candela], ask: Sequence[Candela]) -> dict[str, float]:
    """Lo spread vero, dalla differenza fra le due serie sulla chiusura."""
    per_orario = {c.orario: c.chiusura for c in ask}
    differenze = [per_orario[c.orario] - c.chiusura for c in bid if c.orario in per_orario]
    if not differenze:
        return {}
    differenze.sort()
    meta = differenze[len(differenze) // 2]
    return {"mediano": meta, "medio": sum(differenze) / len(differenze),
            "campione": len(differenze)}


def importa(simbolo: str, da: int, a: int) -> None:
    bid, ask = orarie(simbolo, da, a)
    if not bid:
        log.warning("%s: nessuna candela", simbolo)
        return
    sp = spread_misurato(bid, ask)
    serie = costruisci(bid)

    totale_nuove = 0
    for tf, candele in serie.items():
        righe = [{"strumento": simbolo, "tf": tf.value,
                  "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "apertura": c.apertura, "massimo": c.massimo,
                  "minimo": c.minimo, "chiusura": c.chiusura} for c in candele]
        nuove, gia = storage.salva_candele(righe, origine=ORIGINE)
        totale_nuove += nuove
        print(f"  {tf.value:6s} {len(candele):7d} candele  ({nuove} nuove)")

    if sp:
        # Il pip e' la QUARTA cifra decimale sulle coppie a cinque decimali
        # (EURUSD 1.0854|3) e la SECONDA su quelle a tre (USDJPY 150.12|3).
        # Moltiplicare per la scala del simbolo da' i **punti**, che sono
        # dieci volte i pip: e' l'errore per cui avevo riportato "10 pip"
        # dove ce n'era 1, e qui avrebbe dato 4 pip dove ce n'e' 0,4.
        per_pip = 1e4 if scala_di(simbolo) == 1e5 else 1e2
        print(f"  spread mediano misurato: {sp['mediano'] * per_pip:.2f} pip "
              f"({sp['mediano'] * scala_di(simbolo):.1f} punti) "
              f"su {sp['campione']:,} ore")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("simbolo", nargs="?", help=f"uno di: {', '.join(SIMBOLI)}")
    p.add_argument("--da", type=int, default=2006)
    p.add_argument("--a", type=int, default=datetime.now(timezone.utc).year)
    scelte = p.parse_args()

    configura_log()
    storage.inizializza()
    quali = [scelte.simbolo] if scelte.simbolo else SIMBOLI
    for s in quali:
        if s not in SIMBOLI:
            raise SystemExit(f"simbolo sconosciuto: {s}")
        print(f"\n{s}  ({scelte.da}-{scelte.a})")
        importa(s, scelte.da, scelte.a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
