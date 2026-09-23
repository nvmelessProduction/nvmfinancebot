"""L'archivio si rilegge solo se e' cambiato, e quando cambia si rilegge.

Rileggerlo ad ogni valutazione costava dieci secondi a valutazione e faceva
arrivare le decisioni 278 secondi dopo la chiusura della candela: oltre i 180
di `MAX_RITARDO_ALERT_SEC`, che le avrebbe rifiutate come "prezzo non piu'
attuale". Ma una memoria che non si accorge di un aggiornamento e' molto
peggio della lentezza: farebbe cercare i CRT su candele vecchie mentre
l'ordine parte al prezzo di adesso.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import storage
from core.fornitore_tradingview import FornitoreTradingView
from core.parametri import TF


@pytest.fixture
def archivio(monkeypatch):
    """Un archivio finto che conta quante volte viene letto davvero."""

    stato = {"righe": [], "letture": 0, "righe_lette": 0}

    def _candele_archiviate(strumento, tf, limite=None, dopo=None):
        stato["letture"] += 1
        if tf != TF.H1.value:
            return []
        righe = stato["righe"]
        if dopo is not None:
            righe = [r for r in righe if r["chiusura_utc"] > dopo]
        stato["righe_lette"] += len(righe)
        return list(righe)

    def _impronta(strumento):
        righe = stato["righe"]
        ultima = righe[-1]["chiusura_utc"] if righe else None
        return ((TF.H1.value, len(righe), ultima),)

    def aggiungi(quante=1):
        inizio = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
            hours=len(stato["righe"]))
        for i in range(quante):
            quando = inizio + timedelta(hours=i)
            stato["righe"].append({
                "chiusura_utc": quando.isoformat().replace("+00:00", "Z"),
                "apertura": 1.0, "massimo": 1.1, "minimo": 0.9, "chiusura": 1.0,
            })

    monkeypatch.setattr(storage, "candele_archiviate", _candele_archiviate)
    monkeypatch.setattr(storage, "impronta_candele", _impronta)
    stato["aggiungi"] = aggiungi
    aggiungi(5)
    return stato


@pytest.fixture
def fornitore():
    return FornitoreTradingView()


def test_la_prima_lettura_va_in_archivio(fornitore, archivio):
    fornitore.storico("6E")
    assert archivio["letture"] > 0


def test_la_seconda_non_ci_va(fornitore, archivio):
    fornitore.storico("6E")
    dopo_la_prima = archivio["letture"]
    for _ in range(5):
        fornitore.storico("6E")
    assert archivio["letture"] == dopo_la_prima


def test_i_dati_sono_gli_stessi(fornitore, archivio):
    primo = fornitore.storico("6E")
    secondo = fornitore.storico("6E")
    assert primo[TF.H1] == secondo[TF.H1]
    assert primo.keys() == secondo.keys()


def test_una_candela_nuova_fa_rileggere(fornitore, archivio):
    prima = fornitore.storico("6E")
    dopo_la_prima = archivio["letture"]

    archivio["aggiungi"](1)
    dopo = fornitore.storico("6E")

    assert archivio["letture"] > dopo_la_prima, "non si e' accorto della candela nuova"
    assert len(dopo[TF.H1]) == len(prima[TF.H1]) + 1


def test_una_candela_nuova_fa_leggere_solo_quella(fornitore, archivio):
    """Il punto di tutto: accorgersene senza rileggere l'archivio intero.

    La memoria sull'impronta da sola non serviva mai in funzione. Ogni giro di
    mercato porta una candela al minuto, quindi l'impronta cambiava sempre e i
    285.000 oggetti Candela di EURUSD venivano ricostruiti da zero: 2,9
    secondi per archivio, quattro archivi per valutazione. Nel log del
    2026-09-23 si vedeva come venti secondi di buco fra uno strumento e il
    successivo, e gli alert in coda al giro morivano di "alert vecchio di 28s".
    """
    fornitore.storico("6E")
    archivio["righe_lette"] = 0

    archivio["aggiungi"](1)
    fornitore.storico("6E")

    assert archivio["righe_lette"] == 1, (
        f"ha riletto {archivio['righe_lette']} righe per una candela nuova")


def test_la_coda_attaccata_da_la_stessa_serie_della_rilettura(fornitore, archivio):
    """Veloce non basta: deve dare esattamente quello che darebbe rileggendo."""
    fornitore.storico("6E")
    archivio["aggiungi"](3)
    incrementale = fornitore.storico("6E")

    pulito = FornitoreTradingView().storico("6E")
    assert incrementale[TF.H1] == pulito[TF.H1]


def test_un_buco_tappato_a_meta_serie_fa_rileggere(fornitore, archivio):
    """L'ultima chiusura non cambia, il conteggio si'.

    `_ricostruisci_superiori` riscrive i periodi mancanti in mezzo alla serie,
    non solo in coda: un'impronta fatta della sola ultima candela non se ne
    accorgerebbe.
    """
    fornitore.storico("6E")
    dopo_la_prima = archivio["letture"]

    righe = archivio["righe"]
    righe.insert(2, dict(righe[2]))          # una riga in piu', in mezzo
    fornitore.storico("6E")

    assert archivio["letture"] > dopo_la_prima


def test_strumenti_diversi_hanno_memorie_diverse(fornitore, archivio):
    fornitore.storico("6E")
    dopo_la_prima = archivio["letture"]
    fornitore.storico("GC")
    assert archivio["letture"] > dopo_la_prima


def test_chi_riceve_lo_storico_non_puo_sporcare_la_memoria(fornitore, archivio):
    """Il dizionario e' una copia: le tuple dentro non si possono toccare."""
    primo = fornitore.storico("6E")
    primo[TF.H1] = ()
    secondo = fornitore.storico("6E")
    assert len(secondo[TF.H1]) == 5
