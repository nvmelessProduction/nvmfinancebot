"""Le otto conferme di Romeo, confrontate con cio' che dicono davvero.

## Perche' esiste

Il 2026-09-24, verificando le conferme una per una, tre delle otto sono
risultate **degeneri**: `CRT-10` rispondeva `None` 226 volte su 226, `CRT-18`
rispondeva `True` 226 volte su 226, `CRT-17` non diceva mai `True`.

Una costante non e' un segnale. La Fase 2 del piano deve PESARE queste otto,
e pesare una costante da' un numero privo di significato: il modello
concluderebbe "questa conferma non conta" senza averla mai misurata.

Nessuno se n'era accorto perche' il responso non finiva in archivio e nessuno
lo guardava. Adesso ci finisce, e questo script lo guarda.

## Cosa controlla

**A. Nessuna conferma e' una costante.** Su un campione sufficiente, ognuna
deve aver risposto in almeno due modi diversi. E' il controllo che avrebbe
fermato i tre difetti di sopra il giorno in cui sono nati.

**B. Le tautologie aritmetiche.** Alcune formule non possono che essere vere,
e il codice sembra corretto lo stesso: `chiusura <= meta_ombra` e' sempre
vero, perche' il punto medio sta fra il corpo e l'estremo. Qui si provano su
forme di candela costruite apposta.

**C. Le regole con una fonte esterna.** CISD e double purge hanno una
definizione fuori da questi file, e il codice deve implementare quella:

  - il CISD si misura su APERTURA e CHIUSURA, non su massimi e minimi --
    quello e' l'MSS, che stampa dopo;
  - il double purge vuole ENTRAMBI i lati spazzati e la chiusura dentro.

**D. Nessuna regola in due copie.** Tre difetti su cinque trovati in due
giorni erano la stessa cosa: due implementazioni della stessa regola che
rispondono a due domande.

## Uso

    python audit_conferme.py                     # su tutto l'archivio
    python audit_conferme.py --da 2026-09-24T09:00   # dal riavvio in poi
    python audit_conferme.py --minimo 50         # esige almeno 50 decisioni

Non tocca il bot, non scrive in archivio, si puo' lanciare mentre gira.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sqlite3
import sys
from datetime import datetime, timezone

from core import setup as stp
from core.config import impostazioni
from core.definizioni import Bias, Candela, meta_ombra
from core.parametri import CONFERME_ROMEO, TF, conferma_attiva

LE_OTTO = tuple(sorted(CONFERME_ROMEO))


def _cand(massimo, minimo, chiusura, apertura, ore=0) -> Candela:
    return Candela(datetime(2026, 1, 1, ore, tzinfo=timezone.utc),
                   apertura, massimo, minimo, chiusura)


# ===========================================================================
# A. Nessuna conferma e' una costante
# ===========================================================================


def responsi_in_archivio(da: str | None = None) -> list[dict]:
    """I responsi registrati, opzionalmente solo da un istante in poi.

    `da` serve dopo una correzione: le decisioni precedenti portano il
    comportamento vecchio, e contarle terrebbe il controllo rosso per sempre
    anche quando il difetto e' chiuso. Si passa l'ISO UTC del riavvio.
    """
    conn = sqlite3.connect(f"file:{impostazioni().DB_PATH}?mode=ro", uri=True)
    try:
        if da:
            righe = conn.execute(
                "SELECT responso_romeo FROM decisione "
                "WHERE responso_romeo IS NOT NULL AND creata_utc >= ?",
                (da,)).fetchall()
        else:
            righe = conn.execute(
                "SELECT responso_romeo FROM decisione "
                "WHERE responso_romeo IS NOT NULL").fetchall()
    finally:
        conn.close()
    fuori = []
    for (testo,) in righe:
        try:
            fuori.append(json.loads(testo))
        except (TypeError, ValueError):
            continue
    return fuori


def costanti(responsi: list[dict]) -> list[str]:
    """Le conferme che hanno risposto in un modo solo."""
    guasti = []
    for regola in LE_OTTO:
        visti = {str(r.get(regola)) for r in responsi if regola in r}
        if len(visti) == 1:
            solo = visti.pop()
            guasti.append(f"{regola}: sempre {solo} su {len(responsi)} decisioni")
    return guasti


# ===========================================================================
# B. Le tautologie aritmetiche
# ===========================================================================


def tautologie() -> list[str]:
    """Formule che non possono che essere vere, su forme costruite apposta."""
    guasti = []

    # `chiusura <= meta_ombra` e' sempre vero: il punto medio sta fra il corpo
    # e l'estremo. E' il difetto che teneva CRT-18 a `True` per 226 volte.
    forme = [
        _cand(massimo=120, minimo=99, chiusura=100, apertura=101),
        _cand(massimo=120, minimo=99, chiusura=119, apertura=101),
        _cand(massimo=111, minimo=108, chiusura=110, apertura=109),
    ]
    if all(c.chiusura <= (meta_ombra(c, superiore=True) or 1e18) for c in forme):
        corpo = inspect.getsource(stp.crt18_meta_ombra)
        if "barre_fase[indice + 1:]" not in corpo:
            guasti.append(
                "CRT-18 confronta una candela con la propria ombra: "
                "`chiusura <= meta_ombra` e' vero per costruzione")

    # CRT-18 deve poter dire di no.
    spazza = _cand(massimo=120, minimo=99, chiusura=100, apertura=101)
    sopra = _cand(massimo=118, minimo=105, chiusura=115, apertura=106)
    if stp.crt18_meta_ombra([spazza, sopra], Bias.SHORT) is not False:
        guasti.append("CRT-18 non dice mai di no nemmeno quando il livello "
                      "viene attraversato")
    return guasti


# ===========================================================================
# C. Le regole con una fonte esterna
# ===========================================================================


def contro_le_fonti() -> list[str]:
    guasti = []

    # Il CISD si misura su apertura/chiusura, non su massimi/minimi: quello e'
    # l'MSS. E la conferma deve rilevare la ROTTURA, non la sola esistenza di
    # una serie da rompere.
    serie = [
        _cand(massimo=110, minimo=104, chiusura=105, apertura=109),
        _cand(massimo=106, minimo=101, chiusura=102, apertura=105),
    ]
    rotta = serie + [_cand(massimo=112, minimo=101, chiusura=110, apertura=102)]
    intatta = serie + [_cand(massimo=112, minimo=101, chiusura=106, apertura=102)]
    if stp.crt11_cisd(rotta, Bias.LONG) is not True:
        guasti.append("CRT-11 non riconosce un CISD avvenuto")
    if stp.crt11_cisd(intatta, Bias.LONG) is not False:
        guasti.append("CRT-11 dice si' a una serie che NON e' stata rotta: "
                      "sta rispondendo 'esiste' invece di 'e' avvenuto'")

    # Il double purge vuole ENTRAMBI i lati e la chiusura dentro.
    n1 = _cand(massimo=110, minimo=100, chiusura=109, apertura=101)
    doppia = _cand(massimo=112, minimo=98, chiusura=104, apertura=106)
    un_lato = _cand(massimo=112, minimo=104, chiusura=105, apertura=106)
    # Spazza entrambi i lati ma chiude FUORI dal range di N1 (100-110):
    # "una candela che rompe sopra e sotto ma chiude fuori non ha richiuso
    # niente, ha solo un range grande". La chiusura resta dentro il range
    # della candela stessa, che `Candela` pretende.
    fuori = _cand(massimo=112, minimo=98, chiusura=99, apertura=106)
    if stp.crt10_double_purge(n1, [doppia], Bias.SHORT) is None:
        guasti.append("CRT-10 non riconosce un double purge conforme")
    if stp.crt10_double_purge(n1, [un_lato], Bias.SHORT) is not None:
        guasti.append("CRT-10 accetta uno sweep su un lato solo")
    if stp.crt10_double_purge(n1, [fuori], Bias.SHORT) is not None:
        guasti.append("CRT-10 accetta una candela che chiude FUORI dal range")
    return guasti


# ===========================================================================
# D. Nessuna regola in due copie
# ===========================================================================


def doppie_implementazioni() -> list[str]:
    """Tre difetti su cinque, in due giorni, erano questo."""
    guasti = []
    from core import ingresso_ltf

    # Il CISD: il ramo armato e la conferma devono chiedere la stessa cosa.
    armato = inspect.getsource(ingresso_ltf.controlla)
    conferma = inspect.getsource(stp.crt11_cisd)
    for dove, corpo in (("ingresso_ltf.controlla", armato),
                        ("setup.crt11_cisd", conferma)):
        if "cisd(" not in corpo:
            guasti.append(f"{dove} non cerca piu' il CISD")
        elif "chiusura >" not in corpo and "chiusura <" not in corpo:
            guasti.append(f"{dove} non verifica la ROTTURA del livello")

    # CRT-06: il booleano deve derivare dal conteggio, non reimplementarlo.
    if "quanti_modelli_allineati(" not in inspect.getsource(stp.crt06_allineamento):
        guasti.append("CRT-06 ha di nuovo un conteggio suo invece di quello "
                      "condiviso")
    return guasti


# ===========================================================================


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--minimo", type=int, default=30,
                   help="quante decisioni servono per giudicare le costanti")
    p.add_argument("--da", default=None,
                   help="ISO UTC: solo le decisioni da qui in poi. Dopo una "
                        "correzione si passa l'istante del riavvio, altrimenti "
                        "le decisioni vecchie tengono il controllo rosso")
    a = p.parse_args()

    print("=== Le otto conferme, e se bloccano ===")
    for regola in LE_OTTO:
        print(f"  {regola:8} blocca da sola: {conferma_attiva(regola)}")

    guasti: list[str] = []
    guasti += tautologie()
    guasti += contro_le_fonti()
    guasti += doppie_implementazioni()

    responsi = responsi_in_archivio(a.da)
    print(f"\n=== Campione in archivio: {len(responsi)} decisioni ===")
    if len(responsi) < a.minimo:
        print(f"  sotto il minimo di {a.minimo}: il controllo sulle costanti "
              "non e' significativo e viene saltato")
    else:
        for regola in LE_OTTO:
            visti = [str(r.get(regola)) for r in responsi if regola in r]
            quante = {v: visti.count(v) for v in set(visti)}
            print(f"  {regola:8} {quante}")
        guasti += costanti(responsi)

    print()
    if not guasti:
        print("tutto regge: nessuna costante, nessuna tautologia, "
              "nessuna regola in due copie.")
        return 0
    print(f"{len(guasti)} problemi:")
    for g in guasti:
        print(f"  - {g}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
