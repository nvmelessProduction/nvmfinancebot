"""Importa lo storico esportato da TradingView nell'archivio del bot.

`DEF-26` vuole cinque anni di storia. Gli alert la costruiscono un pezzo alla
volta, ma aspettare cinque anni non ha senso: si esporta una volta il grafico
da TradingView e da li' in poi gli alert lo tengono aggiornato.

## Come si esporta da TradingView

Apri il grafico del **future** (`GC1!`, `6E1!`, ...) sul timeframe che ti
serve, poi menu in alto a destra → *Export chart data...* → CSV.

Il file esce con una colonna `time` e le quattro OHLC. Il `time` di TradingView
e' l'**apertura** della barra: questo script lo converte in chiusura come fa
il fornitore, e scarta l'ultima riga perche' e' la barra in corso.

## Uso

    python importa_storico.py GC TF_1D dati/GC_giornaliero.csv
    python importa_storico.py 6E TF_1W dati/6E_settimanale.csv

Lo strumento e' il codice di `PRIN-08` (`GC`, `6E`, `6B`, `6A`, `6S`, `6J`,
oppure `ICEUS` per il DXY). Il timeframe e' uno di `DEF-01`.

Reimportare lo stesso file non duplica niente: la chiave e' (strumento,
timeframe, chiusura).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from core import storage
from core.log import configura as configura_log
from core.parametri import TF
from core.simboli import FUTURE_A_CFD, SOLO_ANALISI

# I nomi che TradingView usa nell'export, in minuscolo.
COLONNE_TEMPO = ("time", "date", "datetime")
COLONNE_OHLC = {
    "apertura": ("open",),
    "massimo": ("high",),
    "minimo": ("low",),
    "chiusura": ("close",),
}


class CsvNonValido(ValueError):
    """Il file non ha la forma di un export di TradingView."""


def _colonna(intestazioni: list[str], candidati: tuple[str, ...], quale: str) -> str:
    minuscole = {h.strip().lower(): h for h in intestazioni}
    for nome in candidati:
        if nome in minuscole:
            return minuscole[nome]
    raise CsvNonValido(f"colonna {quale} non trovata fra {intestazioni}")


def _momento(grezzo: str) -> datetime:
    """Interpreta il tempo di TradingView: ISO oppure unix in secondi."""
    testo = grezzo.strip()
    if testo.isdigit():
        return datetime.fromtimestamp(int(testo), tz=timezone.utc)
    momento = datetime.fromisoformat(testo.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def leggi_csv(percorso: Path) -> list[dict]:
    """Legge le barre dal CSV, con gli orari ancora di **apertura**."""
    with percorso.open(encoding="utf-8-sig", newline="") as file:
        lettore = csv.DictReader(file)
        if not lettore.fieldnames:
            raise CsvNonValido(f"{percorso}: file senza intestazione")

        colonna_tempo = _colonna(lettore.fieldnames, COLONNE_TEMPO, "tempo")
        colonne = {
            campo: _colonna(lettore.fieldnames, nomi, campo)
            for campo, nomi in COLONNE_OHLC.items()
        }

        barre: list[dict] = []
        for numero, riga in enumerate(lettore, start=2):
            grezzo = (riga.get(colonna_tempo) or "").strip()
            if not grezzo:
                continue
            try:
                barra = {
                    "apertura_utc": _momento(grezzo),
                    **{campo: float(riga[colonna]) for campo, colonna in colonne.items()},
                }
            except (ValueError, TypeError) as errore:
                raise CsvNonValido(f"{percorso} riga {numero}: {errore}") from errore
            barre.append(barra)

    return sorted(barre, key=lambda b: b["apertura_utc"])


def estremi_coerenti(barra: dict) -> Optional[tuple[float, float, int]]:
    """Restituisce (massimo, minimo, quante correzioni) oppure None.

    Per definizione il massimo di un periodo e' il piu' alto prezzo scambiato
    in quel periodo, e apertura e chiusura sono prezzi scambiati in quel
    periodo: quindi il massimo non puo' stare sotto di loro, e il minimo non
    puo' stare sopra. E' un'invariante, non un'opinione, ed e' la stessa che
    `Candela` fa rispettare in `core/definizioni.py`.

    Le fonti gratuite la violano piu' spesso di quanto si creda: aggregano gli
    estremi su una finestra di sessione e la chiusura su un'altra, e ne esce
    una barra che chiude sopra il proprio massimo. Qui la si riporta a norma
    prendendo il piu' alto dei valori che la fonte stessa ha dichiarato per
    quella barra: non si inventa un prezzo, si sceglie fra quelli dati.

    None se la barra e' irrecuperabile: un prezzo non finito o non positivo,
    oppure un massimo sotto il proprio minimo. Quelle si scartano, perche' non
    c'e' niente da cui ricostruirle.
    """
    try:
        valori = [float(barra[campo]) for campo in
                  ("apertura", "massimo", "minimo", "chiusura")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in valori):
        return None

    apertura, massimo, minimo, chiusura = valori
    if massimo < minimo:
        # Massimo sotto il minimo non e' un estremo da correggere: e' una
        # barra che si contraddice da sola (colonne invertite, dato corrotto).
        # Allargarla ad apertura e chiusura la renderebbe plausibile senza
        # renderla vera, e non c'e' nulla da cui ricostruire l'originale.
        return None
    corretto_massimo = max(massimo, apertura, chiusura)
    corretto_minimo = min(minimo, apertura, chiusura)
    corretta = int(corretto_massimo != massimo or corretto_minimo != minimo)
    return corretto_massimo, corretto_minimo, corretta


def in_candele(barre: list[dict], strumento: str, tf: TF) -> tuple[list[dict], int]:
    """Converte le barre in righe d'archivio, con l'orario di **chiusura**.

    La chiusura della barra `i` e' l'apertura della barra `i+1`. L'ultima non
    ha successore, quindi non ha chiusura nota: e' la barra in corso, e viene
    scartata (`ESCL-13`). E' la stessa conversione che fa il fornitore, ed e'
    il punto in cui un import distratto introdurrebbe un lookahead di un
    periodo intero.

    Restituisce `(righe, riparate)`: `riparate` sono le barre a cui e' stato
    corretto un estremo incoerente (vedi `estremi_coerenti`). Il numero va
    mostrato a chi importa: se e' alto, la fonte non e' buona.
    """
    righe: list[dict] = []
    riparate = 0
    for indice in range(len(barre) - 1):
        barra = barre[indice]
        chiusura = barre[indice + 1]["apertura_utc"]
        estremi = estremi_coerenti(barra)
        if estremi is None:
            continue                     # barra irrecuperabile: si scarta
        massimo, minimo, corretta = estremi
        riparate += corretta
        righe.append({
            "strumento": strumento,
            "tf": tf.value,
            "chiusura_utc": chiusura.isoformat().replace("+00:00", "Z"),
            "apertura": barra["apertura"],
            "massimo": massimo,
            "minimo": minimo,
            "chiusura": barra["chiusura"],
        })
    return righe, riparate


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argomenti.add_argument("strumento", help="codice di PRIN-08: GC, 6E, 6B, 6A, 6S, 6J, ICEUS")
    argomenti.add_argument("timeframe", help="timeframe di DEF-01: TF_1D, TF_1W, TF_1M...")
    argomenti.add_argument("csv", help="il file esportato da TradingView")
    opzioni = argomenti.parse_args()

    configura_log()

    strumento = opzioni.strumento.strip().upper()
    ammessi = set(FUTURE_A_CFD) | set(SOLO_ANALISI)
    if strumento not in ammessi:
        print(f"ERRORE  {strumento} non e' uno strumento di PRIN-08.")
        print(f"        Ammessi: {', '.join(sorted(ammessi))}")
        return 1

    try:
        tf = TF(opzioni.timeframe.strip().upper())
    except ValueError:
        print(f"ERRORE  {opzioni.timeframe} non e' un timeframe di DEF-01.")
        print(f"        Ammessi: {', '.join(t.value for t in TF)}")
        return 1

    percorso = Path(opzioni.csv)
    if not percorso.exists():
        print(f"ERRORE  file non trovato: {percorso}")
        return 1

    try:
        barre = leggi_csv(percorso)
    except CsvNonValido as errore:
        print(f"ERRORE  {errore}")
        return 1

    righe, riparate = in_candele(barre, strumento, tf)
    if not righe:
        print(f"ERRORE  nessuna candela chiusa nel file ({len(barre)} barre lette)")
        return 1

    storage.inizializza()
    nuove, gia_viste = storage.salva_candele(righe, origine=f"import:{percorso.name}")

    print(f"OK      {strumento} {tf.value}")
    print(f"        {len(barre)} barre lette, l'ultima scartata perche' in corso")
    print(f"        {nuove} candele nuove, {gia_viste} gia' presenti")
    print(f"        dal {righe[0]['chiusura_utc'][:10]} al {righe[-1]['chiusura_utc'][:10]}")

    print()
    print("Copertura attuale dell'archivio:")
    for riga in storage.copertura_candele():
        print(f"  {riga['strumento']:8} {riga['tf']:8} {riga['quante']:6} candele  "
              f"dal {riga['dalla'][:10]} al {riga['alla'][:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
