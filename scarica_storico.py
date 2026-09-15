"""Scarica lo storico dei future di analisi senza abbonamenti a pagamento.

`importa_storico.py` vuole un CSV esportato da TradingView, ma l'export dei
dati e' una funzione dei piani a pagamento. Questo script prende le stesse
candele da una fonte gratuita, cosi' l'archivio si semina anche senza.

## Cosa cambia rispetto a TradingView, e cosa no

**Non cambia lo strumento.** Si scaricano gli stessi future di `PRIN-08`
(`GC=F` e' il contratto COMEX sull'oro, `6E=F` l'euro sul CME, e cosi' via):
l'analisi resta sul future, l'operativita' sul CFD, e `ESCL-12` regge perche'
nessun prezzo attraversa il confine. Scaricare le candele del CFD da MT5
sarebbe un'altra cosa, e resta vietato.

**Cambia il fornitore.** Due fornitori diversi ricostruiscono il contratto
continuo con regole di rollover proprie, quindi i prezzi storici possono
differire di poco. Le righe scaricate qui vengono marcate `origine="yahoo"`,
e il controllo di allineamento del fornitore lo tiene in conto invece di
pretendere che due fornitori coincidano al decimale.

**Non c'e' un'API ufficiale.** L'endpoint e' quello pubblico usato dai
grafici del sito: puo' cambiare o limitare le richieste senza preavviso. Se
un giorno smette di funzionare, l'export da TradingView resta la strada
buona, e `importa_storico.py` non e' cambiato.

## Uso

    python scarica_storico.py                 # tutti gli strumenti, TF_1M/1W/1D
    python scarica_storico.py --orari         # aggiunge TF_H1 (ultimi 2 anni)
    python scarica_storico.py GC              # un solo strumento
    python scarica_storico.py GC TF_1D        # una sola serie

Rilanciarlo non duplica niente: la chiave d'archivio e'
(strumento, timeframe, chiusura).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from core import storage
from core.aggregazione import aggrega_orarie, aggrega_per_mese
from core.definizioni import Candela
from core.log import configura as configura_log
from core.parametri import TF
from core.simboli import DXY_FUTURE, FUTURE_A_CFD
from importa_storico import in_candele

# Il future di PRIN-08 -> il simbolo con cui lo chiama la fonte.
#   GC=F   oro COMEX            6E=F  euro CME        6B=F  sterlina CME
#   6A=F   dollaro australiano  6S=F  franco CME      6J=F  yen CME
#   DX-Y.NYB  indice del dollaro ICE (lo strumento di sola analisi)
TICKER_FONTE: dict[str, str] = {
    "GC": "GC=F",
    "6E": "6E=F",
    "6B": "6B=F",
    "6A": "6A=F",
    "6S": "6S=F",
    "6J": "6J=F",
    "ICEUS": "DX-Y.NYB",
}

RADICE = "https://query1.finance.yahoo.com/v8/finance/chart/"

# Un'intestazione riconoscibile: e' piu' onesto di fingersi un browser.
INTESTAZIONI = {"User-Agent": "nvmfinancebot/1.0 (uso personale)"}


@dataclass(frozen=True)
class Intervallo:
    """Come chiedere un timeframe alla fonte, e come accorgersi se sbaglia.

    `passo_minimo` e `passo_massimo` delimitano la distanza *mediana* attesa
    fra due barre consecutive, in secondi, e non sono una precauzione teorica:
    la fonte, quando non puo' servire l'intervallo chiesto sulla finestra
    chiesta, **non protesta e cambia intervallo**. Chiedendo barre giornaliere
    su tutto lo storico risponde con barre mensili; chiedendo barre orarie
    idem. Senza questo controllo finirebbero in archivio con l'etichetta
    sbagliata, e il motore ragionerebbe su una scala che non e' quella che
    crede.

    `finestra` e' la descrizione leggibile, `richiesta` sono i parametri veri.
    Le serie lunghe si chiedono per intervallo di date (`period1`/`period2`),
    perche' la scorciatoia `range=max` e' proprio quella che fa degradare
    l'intervallo.
    """

    codice: str
    finestra: str
    richiesta: dict
    passo_minimo: float
    passo_massimo: float


def _tutto_lo_storico() -> dict:
    """Dall'inizio dei tempi a oggi, in secondi unix."""
    return {"period1": 0, "period2": int(datetime.now(timezone.utc).timestamp())}


INTERVALLI: dict[TF, Intervallo] = {
    TF.W1: Intervallo("1wk", "tutto lo storico", _tutto_lo_storico(), 500_000, 700_000),
    TF.D1: Intervallo("1d", "tutto lo storico", _tutto_lo_storico(), 72_000, 200_000),
    # Sulle orarie la fonte copre circa due anni: oltre, degrada l'intervallo.
    TF.H1: Intervallo("1h", "ultimi 2 anni", {"range": "730d"}, 3_300, 5_400),
}

# I timeframe che NON si scaricano, ma si costruiscono da un altro.
#
# Le mensili della fonte hanno buchi: sui sei future ne mancano una
# quarantina su trecento, sempre in mesi diversi. Non e' un difetto estetico:
# `aggrega` rifiuta i periodi incompleti, quindi un mese mancante cancella il
# trimestre che lo contiene e con lui l'anno, e `TF_12M` resta vuoto per
# sempre. Le giornaliere invece sono complete su tutti gli strumenti (misurato:
# 314 mesi su 314), quindi le mensili si costruiscono da li'.
# `TF_H4` si costruisce dalle orarie per lo stesso motivo: la fonte non ha
# barre a quattro ore, e senza `TF_H4` la riga `TF_H1` di SETUP-05 non e'
# soddisfabile (REV-48), cioe' il bot non potrebbe mai operare su `TF_H1`.
DERIVATI: dict[TF, TF] = {TF.M1: TF.D1, TF.H4: TF.H1}

# I timeframe di DEF-01 che questa fonte non offre.
NON_OFFERTI: dict[TF, str] = {
    TF.H6: "la fonte non ha barre a 6 ore",
    TF.H12: "la fonte non ha barre a 12 ore",
    TF.M3: "si costruisce dalle mensili (core/aggregazione.py)",
    TF.M6: "si costruisce dalle mensili (core/aggregazione.py)",
    TF.M12: "si costruisce dalle mensili (core/aggregazione.py)",
}

ORIGINE = "yahoo"


def verifica() -> None:
    """Ogni strumento di PRIN-08 ha un ticker, e nessun ticker e' di troppo.

    Se un giorno l'universo cambia, questo scatta subito invece di lasciare
    uno strumento senza storico e senza che nessuno se ne accorga.
    """
    attesi = set(FUTURE_A_CFD) | {DXY_FUTURE}
    if set(TICKER_FONTE) != attesi:
        mancanti = sorted(attesi - set(TICKER_FONTE))
        di_troppo = sorted(set(TICKER_FONTE) - attesi)
        raise ValueError(
            f"TICKER_FONTE non copre PRIN-08: mancano {mancanti}, di troppo {di_troppo}"
        )


verifica()


class ScaricoFallito(RuntimeError):
    """La fonte non ha risposto, o ha risposto con qualcosa di inatteso."""


def strumenti_noti() -> tuple[str, ...]:
    """I codici di PRIN-08 scaricabili: i sei operativi piu' il DXY."""
    return tuple(TICKER_FONTE)


def _numeri(quote: dict, campo: str) -> list:
    valori = quote.get(campo)
    if valori is None:
        raise ScaricoFallito(f"la risposta non contiene il campo {campo!r}")
    return valori


def in_barre(risposta: dict, intervallo: Intervallo) -> list[dict]:
    """Estrae le barre dalla risposta, con l'orario ancora di **apertura**.

    Le barre senza prezzi (giorni di chiusura, buchi della fonte) vengono
    scartate: una candela con un prezzo mancante non e' una candela.
    """
    try:
        risultato = risposta["chart"]["result"][0]
    except (KeyError, IndexError, TypeError) as errore:
        raise ScaricoFallito(f"risposta senza dati: {errore}") from errore

    orari = risultato.get("timestamp") or []
    if not orari:
        raise ScaricoFallito("la risposta non contiene nessuna barra")

    quote = risultato["indicators"]["quote"][0]
    aperture = _numeri(quote, "open")
    massimi = _numeri(quote, "high")
    minimi = _numeri(quote, "low")
    chiusure = _numeri(quote, "close")

    _verifica_passo(orari, intervallo)
    orari, aperture, massimi, minimi, chiusure = _senza_segnaposto_del_momento(
        orari, aperture, massimi, minimi, chiusure
    )

    barre: list[dict] = []
    for indice, momento in enumerate(orari):
        valori = (aperture[indice], massimi[indice], minimi[indice], chiusure[indice])
        if any(valore is None for valore in valori):
            continue
        barre.append({
            "apertura_utc": datetime.fromtimestamp(int(momento), tz=timezone.utc),
            "apertura": float(valori[0]),
            "massimo": float(valori[1]),
            "minimo": float(valori[2]),
            "chiusura": float(valori[3]),
        })
    return barre


def _senza_segnaposto_del_momento(orari: list, *serie: list) -> tuple:
    """Toglie l'ultima voce quando non e' una barra ma il prezzo di adesso.

    La fonte, sulle serie intraday, appende in coda una voce marcata con
    l'istante corrente invece che con l'inizio di un periodo: alle 10:08:51
    la serie oraria finisce con una voce "10:08:51". Non e' una barra, e'
    il prezzo in questo momento.

    Il danno e' subdolo. `in_candele` scarta sempre l'ultima voce perche' e'
    quella in formazione; se l'ultima voce e' il segnaposto, quella scartata
    e' il segnaposto e **la candela ancora in formazione passa per chiusa**,
    con un orario di chiusura che non cade nemmeno su un'ora tonda. E' un
    lookahead di un periodo intero, e i prezzi sembrerebbero giusti.

    Si riconosce dal passo: l'ultimo intervallo e' molto piu' corto degli
    altri, perche' misura "da inizio periodo a adesso" invece che un periodo.
    """
    if len(orari) < 3:
        return (orari, *serie)
    passi = [int(orari[i + 1]) - int(orari[i]) for i in range(len(orari) - 1)]
    mediano = statistics.median(passi[:-1]) if len(passi) > 1 else passi[0]
    if passi[-1] >= mediano * 0.9:
        return (orari, *serie)
    return (orari[:-1], *(valori[:-1] for valori in serie))


def _verifica_passo(orari: list, intervallo: Intervallo) -> None:
    """Le barre ricevute hanno davvero la durata che abbiamo chiesto?

    La fonte, se non puo' servire l'intervallo richiesto sul periodo chiesto,
    non protesta: cambia intervallo e risponde lo stesso. Un archivio che si
    fida finirebbe con barre mensili etichettate come orarie, e il motore
    ragionerebbe su una scala sbagliata senza che nulla lo segnali.
    """
    if len(orari) < 3:
        raise ScaricoFallito(f"troppe poche barre per verificarne il passo: {len(orari)}")
    passi = [int(orari[i + 1]) - int(orari[i]) for i in range(len(orari) - 1)]
    mediano = statistics.median(passi)
    if not intervallo.passo_minimo <= mediano <= intervallo.passo_massimo:
        raise ScaricoFallito(
            f"la fonte ha risposto con barre da {mediano:.0f} secondi invece di "
            f"{intervallo.passo_minimo:.0f}-{intervallo.passo_massimo:.0f}: "
            f"l'intervallo {intervallo.codice!r} non e' disponibile su "
            f"{intervallo.finestra!r}"
        )


def scarica(ticker: str, intervallo: Intervallo, cliente: httpx.Client) -> list[dict]:
    """Chiede una serie alla fonte e restituisce le barre, o solleva."""
    try:
        risposta = cliente.get(
            RADICE + ticker,
            params={**intervallo.richiesta, "interval": intervallo.codice},
        )
    except httpx.HTTPError as errore:
        raise ScaricoFallito(f"rete: {errore}") from errore

    if risposta.status_code != 200:
        raise ScaricoFallito(f"la fonte ha risposto {risposta.status_code}")
    try:
        corpo = risposta.json()
    except ValueError as errore:
        raise ScaricoFallito(f"risposta illeggibile: {errore}") from errore
    return in_barre(corpo, intervallo)


def deriva(strumento: str, tf: TF, cliente: httpx.Client) -> tuple[list[dict], int]:
    """Costruisce un timeframe che la fonte serve male, partendo da uno che
    serve bene: le mensili dalle giornaliere, `TF_H4` dalle orarie.
    """
    sorgente = DERIVATI[tf]
    barre = scarica(TICKER_FONTE[strumento], INTERVALLI[sorgente], cliente)
    righe, riparate = in_candele(barre, strumento, sorgente)

    if tf is TF.H4:
        quattro_ore = aggrega_orarie([_in_candela(r) for r in righe])
        return [_in_riga(c, strumento, tf) for c in quattro_ore], 0

    if tf is not TF.M1:
        raise ScaricoFallito(f"{tf.value}: non so da cosa derivarlo")

    mensili = aggrega_per_mese([_in_candela(r) for r in righe])
    # Le correzioni agli estremi sono gia' state contate quando si e'
    # scaricata la serie sorgente: riportarle anche qui le farebbe comparire
    # due volte nel totale, una per la giornaliera e una per la mensile che
    # ne deriva. Nel primo avvio vero comparivano infatti "440 con estremi
    # corretti" sia su GC TF_1D sia su GC TF_1M, che sono le stesse 440.
    return [_in_riga(c, strumento, tf) for c in mensili], 0


def _in_candela(riga: dict) -> Candela:
    momento = datetime.fromisoformat(str(riga["chiusura_utc"]).replace("Z", "+00:00"))
    return Candela(
        orario=momento.astimezone(timezone.utc),
        apertura=riga["apertura"], massimo=riga["massimo"],
        minimo=riga["minimo"], chiusura=riga["chiusura"],
    )


def _in_riga(candela: Candela, strumento: str, tf: TF) -> dict:
    return {
        "strumento": strumento,
        "tf": tf.value,
        "chiusura_utc": candela.orario.isoformat().replace("+00:00", "Z"),
        "apertura": candela.apertura,
        "massimo": candela.massimo,
        "minimo": candela.minimo,
        "chiusura": candela.chiusura,
    }


def _serie_richieste(strumento: Optional[str], timeframe: Optional[str], orari: bool) -> list:
    if strumento is not None and strumento not in TICKER_FONTE:
        raise SystemExit(
            f"strumento sconosciuto: {strumento!r}. "
            f"Quelli scaricabili sono {', '.join(strumenti_noti())}."
        )
    strumenti = [strumento] if strumento else list(TICKER_FONTE)

    if timeframe is not None:
        try:
            tf = TF(timeframe)
        except ValueError:
            raise SystemExit(f"timeframe sconosciuto: {timeframe!r}") from None
        if tf in NON_OFFERTI:
            raise SystemExit(f"{tf.value}: {NON_OFFERTI[tf]}")
        if tf not in INTERVALLI and tf not in DERIVATI:
            raise SystemExit(f"{tf.value}: non scaricabile da questa fonte")
        tempi = [tf]
    else:
        tempi = [TF.D1, TF.M1, TF.W1] + ([TF.H1, TF.H4] if orari else [])

    return [(s, t) for s in strumenti for t in tempi]


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argomenti.add_argument("strumento", nargs="?",
                           help=f"codice di PRIN-08: {', '.join(strumenti_noti())}")
    argomenti.add_argument("timeframe", nargs="?",
                           help="TF_1M, TF_1W, TF_1D, TF_H4, TF_H1")
    argomenti.add_argument("--orari", action="store_true",
                           help="scarica anche TF_H1 e TF_H4 (la fonte copre ~2 anni)")
    argomenti.add_argument("--pausa", type=float, default=1.5,
                           help="secondi fra una richiesta e l'altra (default 1.5)")
    scelte = argomenti.parse_args()

    configura_log()
    storage.inizializza()

    serie = _serie_richieste(scelte.strumento, scelte.timeframe, scelte.orari)
    print(f"Fonte gratuita, {len(serie)} serie da scaricare. "
          f"L'analisi resta sul future: si scarica il contratto, non il CFD.\n")

    totale_nuove = 0
    totale_riparate = 0
    falliti: list[str] = []
    with httpx.Client(headers=INTESTAZIONI, timeout=30.0, follow_redirects=True) as cliente:
        for indice, (strumento, tf) in enumerate(serie):
            etichetta = f"{strumento} {tf.value}"
            try:
                if tf in DERIVATI:
                    righe, riparate = deriva(strumento, tf, cliente)
                else:
                    barre = scarica(TICKER_FONTE[strumento], INTERVALLI[tf], cliente)
                    righe, riparate = in_candele(barre, strumento, tf)
                nuove, gia_viste = storage.salva_candele(righe, origine=ORIGINE)
                totale_nuove += nuove
                totale_riparate += riparate
                nota = f", {riparate} con estremi corretti" if riparate else ""
                print(f"  OK      {etichetta:<14} {len(righe):>6} candele "
                      f"({nuove} nuove, {gia_viste} gia' in archivio{nota})")
            except ScaricoFallito as errore:
                falliti.append(etichetta)
                print(f"  ERRORE  {etichetta:<14} {errore}")
            if indice < len(serie) - 1:
                time.sleep(max(0.0, scelte.pausa))

    print(f"\n{totale_nuove} candele nuove in archivio.")
    if totale_riparate:
        print(f"{totale_riparate} barre avevano un estremo incoerente (chiusura fuori "
              f"dal proprio massimo o minimo) ed e' stato riportato a norma. "
              f"E' un difetto noto delle fonti gratuite: se la percentuale ti "
              f"sembra alta, l'export da TradingView resta piu' pulito.")
    if falliti:
        print(f"Non scaricate: {', '.join(falliti)}. "
              f"Riprova piu' tardi, oppure usa importa_storico.py con un CSV.")
        return 1
    print("Ricordati che TF_H4, TF_H6 e TF_H12 questa fonte non li ha: "
          "si riempiono dagli alert di TradingView, un periodo alla volta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
