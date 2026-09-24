"""Il campo di prova: tutti i CRT di vent'anni, con punteggi ed esito.

## Cosa produce

Un CSV, una riga per CRT: quando, dove, gli otto punteggi delle conferme come
si vedevano **all'istante del rientro**, i tre livelli, e com'e' finito in R al
netto dei costi misurati. E' il dataset che la Fase 2 dovra' pesare, e finche'
non esiste non c'e' niente da pesare.

## Il punto che decide se il numero vale qualcosa

Il CRT si forma **alla chiusura della barra bassa che rientra** (SETUP-02A/B),
non alla chiusura della candela di riferimento. Quindi si avanza **barra per
barra**: ad ogni barra di esecuzione si guarda solo cio' che e' chiuso fino a
quel momento, e il primo momento in cui un CRT c'e' e' l'ingresso.

`backtest/resa_crt.py` non lo faceva -- guardava la finestra intera in un colpo
solo e calcolava i key level alla sua fine. Per contare quanti CRT esistono va
benissimo; per **etichettarli** no, perche' i key level presi a fine settimana
non sono quelli che si vedevano il martedi'. Sarebbe stata una sbirciata lunga
fino a una candela alta intera, e su `W -> 4h` una candela alta e' una
settimana.

## Cosa NON fa

Non applica filtri, esclusioni, bias, rischio. Qui si raccoglie ogni CRT che
ESISTE con quello che le conferme dicevano. Quali valga la pena prendere e' la
domanda della Fase 2, e rispondervi qui vorrebbe dire rispondere prima di
misurare.

## Le coppie, e l'holdout

Solo `W -> 4h` e `D -> 1h`. `M -> D` e' uscita dal piano il primo giorno con
560 CRT contro i 1.000 di soglia, e le tre coppie intraday hanno tre mesi di
storia invece di venti (Fase 1bis). L'holdout -- dal 2024 in poi -- si tiene
chiuso con `--fino`, ed e' chiuso per difetto.

## Uso

    python backtest/campo_prova.py --fino 2024-01-01
    python backtest/campo_prova.py --coppia TF_1W --strumento EURUSD
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import costi_misurati                                          # noqa: E402
from estrazione import LE_OTTO, Riga, etichetta, punteggi_dallo_storico  # noqa: E402

from core import setup as stp                                  # noqa: E402
from core import stato                                         # noqa: E402
from core.config import impostazioni                           # noqa: E402
from core.fornitore_tradingview import FornitoreTradingView    # noqa: E402
from core.parametri import COMPAGNE_SMT, COPPIE_CRT, TF, UNIVERSO  # noqa: E402
from core.simboli import simbolo_esecuzione                    # noqa: E402

# Le due coppie che restano dopo la misura del primo giorno.
COPPIE_VIVE: tuple[TF, ...] = (TF.W1, TF.D1)

# Dopo quante barre di esecuzione un CRT non chiuso si dichiara scaduto. E'
# il terzo esito del protocollo: senza, un'operazione che non arriva mai ne'
# al bersaglio ne' allo stop resterebbe aperta per sempre e il campione
# conterebbe solo i casi che si chiudono.
BARRE_MASSIME: int = 48

# L'inizio dell'holdout. Chiuso per difetto: si apre dichiarandolo.
HOLDOUT: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _serie_ordinata(storico: dict, tf: TF) -> list:
    serie = list(storico.get(tf, ()))
    serie.sort(key=lambda c: c.orario)
    return serie


def crt_della_coppia(
    storico: dict, tf_range: TF, tf_esecuzione: TF, fino: Optional[datetime],
) -> Iterator[tuple]:
    """Ogni CRT della coppia, nell'istante in cui si e' formato davvero.

    Restituisce `(crt, istante, barre_dopo)`. `istante` e' la chiusura della
    barra di rientro -- il momento in cui il CRT esiste e in cui un ingresso
    sarebbe possibile -- e `barre_dopo` sono le barre che vengono dopo, che
    servono SOLO all'etichetta.

    ## Un CRT per candela di riferimento

    Dentro una stessa candela alta il CRT, una volta formato, resta formato:
    le barre successive continuerebbero a soddisfare manipolazione e rientro e
    produrrebbero lo stesso CRT decine di volte. Si prende il **primo**
    istante in cui appare, che e' anche l'unico in cui l'ingresso sarebbe
    nuovo, e si passa alla candela dopo.
    """
    alte = _serie_ordinata(storico, tf_range)
    basse = _serie_ordinata(storico, tf_esecuzione)
    if len(alte) < 2 or not basse:
        return
    utili = stp.tf_key_level_utili(tf_range)

    i = 0
    for indice in range(len(alte) - 1):
        c_rif, successiva = alte[indice], alte[indice + 1]
        if fino is not None and successiva.orario >= fino:
            return
        while i < len(basse) and basse[i].orario <= c_rif.orario:
            i += 1
        fine = i
        while fine < len(basse) and basse[fine].orario <= successiva.orario:
            fine += 1
        if fine == i:
            continue

        for k in range(i, fine):
            istante = basse[k].orario
            # I key level come si vedevano A QUESTA barra, non alla fine
            # della finestra: e' il punto in cui una sbirciata lunga una
            # candela alta entrerebbe senza farsi notare.
            presi = stato.key_level_presi(storico, istante, utili)
            if not presi:
                continue
            crt = stp.cerca_crt(c_rif, basse[i:k + 1], tf_range, presi)
            if crt is None:
                continue
            yield crt, istante, basse[k + 1:]
            break


def riga_del_crt(
    crt, istante: datetime, dopo: list, storico: dict,
    tf_range: TF, tf_esecuzione: TF, strumento: str,
    compagni: dict, tabella, fattore: float,
) -> Optional[Riga]:
    """Un CRT completo: punteggi da prima, esito da dopo."""
    costo = costi_misurati.costo_per_lato(
        tabella, strumento, _simbolo_broker(strumento),
        ingresso_stimato(crt), istante.hour, fattore=fattore)
    esito, ingresso, stop, target = etichetta(crt, dopo, BARRE_MASSIME, costo)
    if esito is None:
        return None                     # in fondo all'archivio: nessun esito

    compagne = {}
    for nome in COMPAGNE_SMT.get(strumento, ()):
        serie = (compagni.get(nome) or {}).get(tf_esecuzione, ())
        tagliate = tuple(c for c in serie if c.orario <= istante)
        if tagliate:
            compagne[nome] = tagliate

    conferme, allineati = punteggi_dallo_storico(
        crt, storico, tf_range, tf_esecuzione, istante,
        strumento=strumento, compagne=compagne,
        crt_per_tf=crt_sulle_altre_coppie(storico, istante))

    rischio = abs(ingresso - stop)
    return Riga(
        strumento=strumento,
        coppia=f"{tf_range.value}->{tf_esecuzione.value}",
        quando=istante.isoformat(),
        verso=crt.direzione.name,
        ingresso=ingresso, stop=stop, target=target,
        rapporto=abs(target - ingresso) / rischio if rischio else 0.0,
        conferme=conferme, allineati=allineati,
        esito=esito.come, erre=esito.erre, barre=esito.barre)


def ingresso_stimato(crt) -> float:
    """Il prezzo a cui si entra: la chiusura del rientro."""
    return crt.n2.chiusura


def _simbolo_broker(strumento: str) -> str:
    """Il nome sotto cui lo spread e' stato misurato.

    La tabella dei costi e' indicizzata coi nomi del broker (`XAUUSD+`), non
    con quelli di `PRIN-08`. Si usa la stessa funzione del bot invece di
    incollare il suffisso a mano: e' il punto in cui due copie della stessa
    regola divergerebbero senza che nessuno se ne accorga.
    """
    return simbolo_esecuzione(UNIVERSO[strumento].cfd,
                              impostazioni().MT5_SUFFISSO_SIMBOLI)


def crt_sulle_altre_coppie(storico: dict, istante: datetime) -> dict:
    """CRT-06 — i CRT delle altre coppie, come li vede il bot.

    Si chiama la funzione del bot, non una copia: se un giorno cambia idea,
    cambia anche qui. E' la stessa ragione per cui `tf_key_level_utili` e'
    derivata da `timeframe_crt_ammesso` invece di essere una seconda tabella.
    """
    return stato._crt_sulle_altre_coppie(storico, istante)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--coppia", default=None, help="un solo range, es. TF_1W")
    p.add_argument("--strumento", default=None, help="un solo strumento")
    p.add_argument("--fino", default=HOLDOUT.isoformat(),
                   help="ISO: esclude tutto da qui in poi (l'holdout)")
    p.add_argument("--tutto", action="store_true",
                   help="apre l'holdout: da usare una volta sola, alla fine")
    p.add_argument("--fattore", type=float, default=1.0,
                   help="moltiplicatore dei costi per la prova di robustezza")
    p.add_argument("--uscita", default="dati/campo_prova.csv")
    a = p.parse_args()

    fino = None
    if not a.tutto:
        fino = datetime.fromisoformat(a.fino)
        if fino.tzinfo is None:
            fino = fino.replace(tzinfo=timezone.utc)

    coppie = COPPIE_VIVE
    if a.coppia:
        coppie = tuple(t for t in COPPIE_VIVE if t.value == a.coppia)
        if not coppie:
            print(f"coppia non riconosciuta: {a.coppia}")
            return 2
    strumenti = sorted(UNIVERSO)
    if a.strumento:
        if a.strumento not in UNIVERSO:
            print(f"strumento fuori da PRIN-08: {a.strumento}")
            return 2
        strumenti = [a.strumento]

    tabella = costi_misurati.costruisci()
    print(tabella.copertura())
    if fino:
        print(f"holdout CHIUSO: niente dal {fino:%Y-%m-%d} in poi")
    else:
        print("!!! holdout APERTO: questo numero si guarda una volta sola")
    print()

    fornitore = FornitoreTradingView()
    # Gli archivi delle compagne, caricati una volta: servono a CRT-12.
    archivi: dict[str, dict] = {}
    for nome in sorted(UNIVERSO):
        archivi[nome] = fornitore.storico(UNIVERSO[nome].future)

    uscita = Path(a.uscita)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    intestazione = (["strumento", "coppia", "quando", "verso", "ingresso",
                     "stop", "target", "rapporto"]
                    + list(LE_OTTO) + ["allineati", "esito", "erre", "barre"])

    scritte = 0
    senza_esito = 0
    inizio = time.time()
    with uscita.open("w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(intestazione)
        for tf_range in coppie:
            tf_ese = COPPIE_CRT[tf_range]
            for strumento in strumenti:
                storico = archivi[strumento]
                quante = 0
                for crt, istante, dopo in crt_della_coppia(
                        storico, tf_range, tf_ese, fino):
                    riga = riga_del_crt(
                        crt, istante, dopo, storico, tf_range, tf_ese,
                        strumento, archivi, tabella, a.fattore)
                    if riga is None:
                        senza_esito += 1
                        continue
                    scrittore.writerow(
                        [riga.strumento, riga.coppia, riga.quando, riga.verso,
                         f"{riga.ingresso:.6f}", f"{riga.stop:.6f}",
                         f"{riga.target:.6f}", f"{riga.rapporto:.4f}"]
                        + [_cella(riga.conferme.get(k)) for k in LE_OTTO]
                        + [_cella(riga.allineati), riga.esito,
                           f"{riga.erre:.4f}", riga.barre])
                    quante += 1
                    scritte += 1
                print(f"  {tf_range.value} -> {tf_ese.value}  {strumento:8} "
                      f"{quante:>6,} CRT   ({time.time() - inizio:.0f}s)")

    print()
    print(f"scritte {scritte:,} righe in {uscita}")
    if senza_esito:
        print(f"scartati {senza_esito:,} CRT senza esito misurabile "
              f"({100 * senza_esito / (scritte + senza_esito):.1f}%)")
        print("  quasi tutti hanno TP1 GIA' ALLE SPALLE: il rientro ha chiuso "
              "oltre il 50% del range, quindi il bersaglio sta dalla parte "
              "sbagliata dell'ingresso. E' lo stesso caso che dal vivo il bot "
              "rifiuta con `tp1_alle_spalle`; un'etichetta inventata su "
              "livelli incoerenti sarebbe peggio di un'etichetta assente.")
    print(f"tempo: {time.time() - inizio:.0f}s")
    return 0


def _cella(valore) -> str:
    """`None` resta vuoto: e' 'non lo so', non 'no'."""
    if valore is None:
        return ""
    if valore is True:
        return "1"
    if valore is False:
        return "0"
    return str(valore)


if __name__ == "__main__":
    sys.exit(main())
