"""Semina i timeframe INTRADAY: M15, M5, M1min. Senza questi Romeo non gira.

## Perche' serve, e perche' non basta `importa_dukascopy.py`

Quello legge i file **orari** di Dukascopy, e da un'ora non si ricava un
quarto d'ora: l'informazione dentro non c'e'. I minuti stanno in file
**giornalieri**, uno per giorno per strumento per lato.

Senza di essi le tre coppie intraday di `CRT-04` — `4h -> 15m`, `1h -> 5m`,
`15m -> 1m` — non hanno il timeframe di ingresso, e il motore non arma
nemmeno il setup: `motore.valuta` controlla che le candele ci siano prima di
mettersi in attesa, perche' un setup armato che nessuno potra' far scattare e'
peggio di un ingresso mediocre.

E' proprio la coppia `4h -> 15m` a dare il risultato migliore misurato:
62,4% di winrate, +0,3613 R netto. Senza i minuti, quella configurazione non
puo' girare.

## Quanta storia serve davvero

Molta meno di quella dei timeframe alti, e per una ragione precisa: i
timeframe intraday sono **solo timeframe di ingresso**. Non producono bias
(`DEF-16` parla di accettazione e rifiuto su orizzonti dove una candela e' un
fatto, non rumore) e non hanno un target di `DEF-46`. Servono a vedere il
CISD, l'FVG e il ritorno — una manciata di barre.

`DEF-26` chiede cinque anni per i timeframe di **bias**, e quelli ce li ha
gia' la semina oraria. Qui un anno basta e avanza per operare; di piu' serve
solo a chi vuole rimisurare.

Un anno sono circa **quattromila file**. Vent'anni sarebbero ottantamila, ore
di scaricamento e parecchi giga per un'informazione che il bot non usa.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from core import storage
from core.definizioni import Candela
from core.duka_minuti import minuti_del_giorno
from core.log import configura as configura_log
from core.parametri import TF

SIMBOLI = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD"]
ORIGINE = "dukascopy"

# Quanti blocchi da un minuto fa ciascun timeframe.
BLOCCHI: dict[TF, int] = {TF.MIN1: 1, TF.MIN5: 5, TF.MIN15: 15}


def aggrega(minuti: Sequence[Candela], quanti: int) -> list[Candela]:
    """Da candele al minuto a candele di `quanti` minuti.

    Il raggruppamento e' su **minuti assoluti**, non su `(data, ora, minuto //
    quanti)`: quella forma, per blocchi da sessanta minuti in su, da' sempre
    zero e collassa tutto a un'ora. E' un errore che non produce eccezioni —
    produce candele sbagliate che sembrano giuste.

    I minuti senza scambi mancano gia' (volume zero, scartati a monte): un
    blocco puo' averne meno di `quanti`, ed e' giusto cosi'. Inventare i
    minuti mancanti inventerebbe prezzi.
    """
    if quanti <= 0:
        return []
    gruppi: dict[int, list[Candela]] = {}
    for c in minuti:
        apertura = c.orario - timedelta(minutes=1)   # l'orario e' la CHIUSURA
        gruppi.setdefault(int(apertura.timestamp()) // 60 // quanti, []).append(c)

    fuori: list[Candela] = []
    for chiave in sorted(gruppi):
        pezzi = gruppi[chiave]
        fuori.append(Candela(
            pezzi[-1].orario, pezzi[0].apertura,
            max(p.massimo for p in pezzi), min(p.minimo for p in pezzi),
            pezzi[-1].chiusura,
        ))
    return fuori


def giorni_di(da: date, a: date) -> list[date]:
    """I giorni fra due date, senza i sabati: il mercato e' chiuso."""
    fuori, giorno = [], da
    while giorno <= a:
        if giorno.weekday() != 5:
            fuori.append(giorno)
        giorno += timedelta(days=1)
    return fuori


def importa(simbolo: str, da: date, a: date, paralleli: int = 16) -> None:
    giorni = giorni_di(da, a)
    print(f"\n{simbolo}  ({da} -> {a}, {len(giorni)} giorni)")

    minuti: list[Candela] = []
    fatti = 0
    with cf.ThreadPoolExecutor(max_workers=paralleli) as pool:
        lavori = [pool.submit(minuti_del_giorno, simbolo, g, "BID") for g in giorni]
        for compito in cf.as_completed(lavori):
            minuti.extend(compito.result())
            fatti += 1
            if fatti % 60 == 0 or fatti == len(giorni):
                print(f"    {fatti:4d}/{len(giorni)} giorni, {len(minuti):,} minuti",
                      flush=True)

    if not minuti:
        print("    nessun minuto scaricato")
        return
    minuti.sort(key=lambda c: c.orario)

    # L'ultimo minuto si scarta: il giorno corrente si pubblica man mano e
    # l'ultima riga di un file appena scritto puo' essere incompleta. ESCL-13
    # vieta di valutare una candela in formazione.
    chiusi = minuti[:-1]

    for tf, quanti in BLOCCHI.items():
        candele = aggrega(chiusi, quanti)
        if not candele:
            continue
        righe = [{
            "strumento": simbolo, "tf": tf.value,
            "chiusura_utc": c.orario.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "apertura": c.apertura, "massimo": c.massimo,
            "minimo": c.minimo, "chiusura": c.chiusura,
        } for c in candele]
        nuove, _ = storage.salva_candele(righe, origine=ORIGINE)
        print(f"  {tf.value:9s} {len(candele):7d} candele  ({nuove} nuove)")


def main() -> int:
    oggi = datetime.now(timezone.utc).date()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("simbolo", nargs="?", help=f"uno di: {', '.join(SIMBOLI)}")
    # Tre mesi bastano a OPERARE: il CISD guarda otto barre, l'FVG cinque.
    # Di piu' serve solo a chi vuole rimisurare la strategia, e costa: un mese
    # per strumento e' quasi un minuto di scaricamento.
    p.add_argument("--mesi", type=int, default=3,
                   help="quanti mesi indietro (predefinito 3, bastano a operare)")
    scelte = p.parse_args()

    configura_log()
    storage.inizializza()

    da = oggi - timedelta(days=int(scelte.mesi * 30.5))
    quali = [scelte.simbolo] if scelte.simbolo else SIMBOLI
    for s in quali:
        if s not in SIMBOLI:
            raise SystemExit(f"simbolo sconosciuto: {s}")
        importa(s, da, oggi)

    print("\nFatto. I timeframe di ingresso di CRT-04 sono in archivio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
