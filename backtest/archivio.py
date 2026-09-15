"""Carica lo storico reale dall'archivio e lo prepara per il motore.

Nessuna riga di questo file entra in produzione: serve solo a misurare.
"""
from __future__ import annotations

import os
import sqlite3
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from typing import Sequence

from core.aggregazione import costruisci_superiori
from core.definizioni import Candela
from core.parametri import TF, UNIVERSO

# L'archivio da leggere. Stessa variabile che usa il resto dell'impianto, cosi'
# il backtest non puo' misurare un database diverso da quello del bot.
DB = os.environ.get("DB_PATH", "dati/bot.db")

FUTURE = {s: d.future for s, d in UNIVERSO.items()}


def _t(testo: str) -> datetime:
    m = datetime.fromisoformat(str(testo).replace("Z", "+00:00"))
    return (m if m.tzinfo else m.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def carica(future: str) -> dict[TF, tuple[Candela, ...]]:
    con = sqlite3.connect(DB)
    storico: dict[TF, tuple[Candela, ...]] = {}
    for tf in (TF.H1, TF.D1, TF.W1, TF.M1):
        righe = con.execute(
            "select chiusura_utc, apertura, massimo, minimo, chiusura from candela "
            "where strumento=? and tf=? order by chiusura_utc",
            (future, tf.value),
        ).fetchall()
        storico[tf] = tuple(
            Candela(_t(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
            for r in righe
        )
    con.close()
    storico.update(costruisci_superiori(storico[TF.M1]))
    storico[TF.H4] = aggrega_orarie(storico[TF.H1], 4)
    return storico


def aggrega_orarie(orarie: Sequence[Candela], quante: int) -> tuple[Candela, ...]:
    """TF_H4 approssimato da TF_H1 in blocchi UTC fissi.

    APPROSSIMAZIONE, valida solo per la misura: il vero TF_H4 di TradingView
    e' ancorato all'apertura di sessione del contratto, non alle 00:00 UTC.
    Serve a stimare quanti setup un trigger H4 aggiungerebbe, non a operare.
    """
    gruppi: dict[tuple, list[Candela]] = {}
    for c in orarie:
        # `orario` e' la CHIUSURA (DEF-02): l'ora di appartenenza e' quella
        # che precede, altrimenti la barra che chiude alle 04:00 finirebbe nel
        # blocco successivo invece che in quello che l'ha vista formarsi.
        appartenenza = c.orario - timedelta(hours=1)
        chiave = (appartenenza.date(), appartenenza.hour // quante)
        gruppi.setdefault(chiave, []).append(c)

    fuori: list[Candela] = []
    for _, blocco in sorted(gruppi.items()):
        fuori.append(
            Candela(
                orario=blocco[-1].orario,
                apertura=blocco[0].apertura,
                massimo=max(c.massimo for c in blocco),
                minimo=min(c.minimo for c in blocco),
                chiusura=blocco[-1].chiusura,
            )
        )
    return tuple(fuori)


def finestra(
    candele: Sequence[Candela],
    tempi: Sequence[datetime],
    istante: datetime,
    quante: int,
) -> tuple[Candela, ...]:
    """Le ultime `quante` candele chiuse entro `istante`.

    Il taglio e' una necessita' di calcolo: `gap_del_timeframe` e' quadratico,
    e su ventisei anni di storia non si puo' rivalutare a ogni barra oraria.
    `LOOKBACK_ANNI` vale 5, quindi le finestre sono scelte per coprirlo.

    `tempi` arriva gia' costruito: ricavarlo dalle candele a ogni chiamata
    costava piu' della ricerca binaria che deve rendere veloce.
    """
    fine = bisect_right(tempi, istante)
    inizio = max(0, fine - quante)
    return tuple(candele[inizio:fine])


def indice_temporale(storico: dict) -> dict:
    """Gli orari di chiusura di ogni serie, pronti per la ricerca binaria."""
    return {tf: [c.orario for c in candele] for tf, candele in storico.items()}
