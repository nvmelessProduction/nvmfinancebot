"""Quanti CRT produce davvero ogni coppia, prima di costruirci sopra.

## Perche' esiste, e perche' viene PRIMA

La Fase 1 del piano vuole un dataset: per ogni CRT di vent'anni, gli otto
punteggi delle conferme e com'e' finito. Ma il piano dice anche di contare la
resa **il primo giorno**, perche' ci sono soglie sotto le quali il lavoro non
ha senso:

    meno di ~1.000 CRT utilizzabili su una coppia  ->  quella coppia esce

Il sospetto e' su `M -> D`: vent'anni danno **262 candele mensili** per
strumento, cioe' 1.647 candele di riferimento su sei strumenti, e quello e' un
TETTO -- un CRT al massimo per candela. `SETUP-00` ne toglie la maggior parte,
perche' senza un key level preso non c'e' CRT.

Meglio saperlo adesso che dopo aver costruito il campo di prova.

## Cosa fa, e cosa non fa

Chiama `setup.cerca_crt` esattamente come il motore, con gli stessi key level
che il motore userebbe (`stato.key_level_presi`). **Non** applica filtri,
esclusioni, bias o rischio: qui si conta quanti CRT ESISTONO, non quanti il
bot aprirebbe. Sono due numeri diversi e servono a due cose diverse.

**Nessuna sbirciata al futuro.** Per ogni candela di riferimento si guardano
solo le barre chiuse entro la sua successiva, e i key level si calcolano
all'istante di quella chiusura.

## Le coppie che si possono davvero misurare

Solo tre: `M->D`, `W->4h`, `D->1h`. Le altre tre -- `4h->15m`, `1h->5m`,
`15m->1m` -- hanno tre mesi di storia, non venti, e su tre mesi non esistono
ne' walk-forward ne' holdout. E' il vincolo che la Fase 1 dichiara e il motivo
per cui esiste la Fase 1bis.

## Uso

    python backtest/resa_crt.py                     # tutte le coppie alte
    python backtest/resa_crt.py --coppia TF_1D      # una sola
    python backtest/resa_crt.py --fino 2024-01-01   # esclude l'holdout
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import setup as stp                                  # noqa: E402
from core.fornitore_tradingview import FornitoreTradingView    # noqa: E402
from core import stato                                         # noqa: E402
from core.parametri import COPPIE_CRT, TF, UNIVERSO            # noqa: E402

# Le tre coppie con vent'anni di storia. Le altre tre ne hanno tre mesi:
# misurarle qui darebbe un numero che non regge il protocollo della Fase 2.
COPPIE_ALTE: tuple[TF, ...] = (TF.M1, TF.W1, TF.D1)


def resa(
    storico: dict, tf_range: TF, tf_esecuzione: TF, fino: datetime | None,
) -> Counter:
    """Conta le candele di riferimento e i CRT che producono.

    Una candela di riferimento per volta: il range e' lei, e le barre in cui
    cercare manipolazione e rientro sono quelle del timeframe di esecuzione
    chiuse dentro la candela di riferimento SUCCESSIVA (SETUP-02).
    """
    alte = storico.get(tf_range, ())
    basse = storico.get(tf_esecuzione, ())
    conta: Counter = Counter()
    if len(alte) < 2 or not basse:
        conta["senza_dati"] = 1
        return conta

    # Le barre basse, ordinate una volta sola: si scorre insieme alle alte.
    basse = sorted(basse, key=lambda c: c.orario)
    i = 0
    for indice in range(len(alte) - 1):
        c_rif, successiva = alte[indice], alte[indice + 1]
        if fino is not None and successiva.orario >= fino:
            break
        conta["riferimento"] += 1

        # Le barre dentro la candela successiva: dopo `c_rif`, fino a
        # `successiva` compresa. Si avanza senza ripartire da capo.
        while i < len(basse) and basse[i].orario <= c_rif.orario:
            i += 1
        barre = []
        j = i
        while j < len(basse) and basse[j].orario <= successiva.orario:
            barre.append(basse[j])
            j += 1
        if not barre:
            conta["senza_barre"] += 1
            continue

        # I key level come li vedrebbe il motore all'istante del rientro.
        presi = stato.key_level_presi(storico, barre[-1].orario)
        if not presi:
            conta["setup00"] += 1
            continue

        crt = stp.cerca_crt(c_rif, barre, tf_range, presi)
        if crt is None:
            conta["niente_crt"] += 1
            continue
        conta["crt"] += 1
        conta["crt_short" if crt.direzione.name == "SHORT" else "crt_long"] += 1
    return conta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--coppia", default=None,
                   help="un solo timeframe di range, es. TF_1D")
    p.add_argument("--fino", default=None,
                   help="ISO: esclude tutto da qui in poi (l'holdout)")
    a = p.parse_args()

    fino = None
    if a.fino:
        fino = datetime.fromisoformat(a.fino)
        if fino.tzinfo is None:
            fino = fino.replace(tzinfo=timezone.utc)

    coppie = COPPIE_ALTE
    if a.coppia:
        coppie = tuple(t for t in COPPIE_ALTE if t.value == a.coppia)
        if not coppie:
            print(f"coppia non riconosciuta: {a.coppia}")
            return 2

    print(f"strumenti: {', '.join(sorted(UNIVERSO))}")
    if fino:
        print(f"fino a {fino:%Y-%m-%d} escluso (holdout tenuto chiuso)")
    print()

    # Il fornitore e non `archivio.carica`: risolve il nome sotto cui le
    # candele stanno davvero (`6E` -> `EURUSD` con MT5) ed e' la stessa
    # lettura che fa il motore. `archivio.carica` punta a `dati/bot.db`, che
    # su questa macchina non esiste.
    fornitore = FornitoreTradingView()
    totali: dict[str, Counter] = {}
    for tf_range in coppie:
        tf_ese = COPPIE_CRT[tf_range]
        nome = f"{tf_range.value} -> {tf_ese.value}"
        somma: Counter = Counter()
        for strumento in sorted(UNIVERSO):
            storico = fornitore.storico(UNIVERSO[strumento].future)
            somma += resa(storico, tf_range, tf_ese, fino)
        totali[nome] = somma
        print(f"--- {nome} ---")
        print(f"    candele di riferimento : {somma['riferimento']:>7,}")
        print(f"    senza barre di esecuz. : {somma['senza_barre']:>7,}")
        print(f"    fermate da SETUP-00    : {somma['setup00']:>7,}")
        print(f"    nessun CRT nella forma : {somma['niente_crt']:>7,}")
        print(f"    CRT TROVATI            : {somma['crt']:>7,}"
              f"   (short {somma['crt_short']:,} / long {somma['crt_long']:,})")
        print()

    print("=== contro la soglia del piano (1.000 CRT per coppia) ===")
    uscite = []
    for nome, c in totali.items():
        verdetto = "ok" if c["crt"] >= 1000 else "SOTTO SOGLIA"
        if c["crt"] < 1000:
            uscite.append(nome)
        print(f"  {nome:20} {c['crt']:>7,}   {verdetto}")
    if uscite:
        print()
        print("Escono dal piano: " + ", ".join(uscite))
        print("Non e' un guasto: e' il numero che il piano chiedeva di "
              "guardare il primo giorno.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
