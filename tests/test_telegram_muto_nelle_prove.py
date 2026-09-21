"""Nessuna prova deve poter mandare un messaggio vero.

Questa non e' una cautela teorica. `ingresso_ltf.arma()` notifica, la suite
lo chiama una dozzina di volte, e il risultato e' arrivato sul telefono
dell'utente: "EURUSD: setup ribassista armato su 4 ore, spazzato 110,000,
primo bersaglio 105,000" -- i valori del fixture di `test_ingresso_ltf`,
ripetuti ad ogni esecuzione della suite finche' non hanno sepolto i
messaggi veri.

La prova sta qui e non altrove perche' la regola riguarda TUTTE le prove,
non un modulo.
"""

import os

import pytest

from core import notifier
from core.definizioni import Bias
from core.parametri import TF


def test_la_porta_risulta_chiusa():
    assert notifier.in_prova(), (
        "girando sotto pytest il notificatore deve sapere di essere in prova")


def test_invia_non_parla_con_la_rete(monkeypatch):
    chiamate = []
    monkeypatch.setattr(notifier.httpx, "post",
                        lambda *a, **k: chiamate.append(a) or None)
    inviato, dettaglio = notifier.invia("un messaggio qualunque")
    assert chiamate == [], "ha provato a chiamare Telegram durante una prova"
    assert inviato is False
    assert "prova" in dettaglio


def test_invia_appena_possibile_non_parla_con_la_rete(monkeypatch):
    chiamate = []
    monkeypatch.setattr(notifier.httpx, "post",
                        lambda *a, **k: chiamate.append(a) or None)
    notifier.invia_appena_possibile("un messaggio qualunque")
    for thread in list(__import__("threading").enumerate()):
        if thread.name == "telegram":
            thread.join(timeout=5)
    assert chiamate == []


def test_armare_un_setup_non_manda_niente(monkeypatch, tmp_path):
    """Il percorso esatto da cui sono partiti i messaggi veri."""
    from core import storage
    from core import ingresso_ltf as ltf

    monkeypatch.setenv("DB_PATH", str(tmp_path / "prova.db"))
    monkeypatch.setattr(storage, "PERCORSO", tmp_path / "prova.db", raising=False)
    storage.inizializza()

    chiamate = []
    monkeypatch.setattr(notifier.httpx, "post",
                        lambda *a, **k: chiamate.append(a) or None)
    ltf.arma("EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
             estremo_sweep=110.0, eq_range=105.0, lato_opposto=100.0)
    for thread in list(__import__("threading").enumerate()):
        if thread.name == "telegram":
            thread.join(timeout=5)
    assert chiamate == [], "armare un setup ha mandato un messaggio vero"


def test_senza_variabile_ma_sotto_pytest_resta_chiusa(monkeypatch):
    """La rete di sicurezza: pytest valorizza `PYTEST_CURRENT_TEST` da solo.

    Se qualcuno cancellasse la variabile nostra -- o scrivesse un file di
    prove che non passa dal conftest -- la porta deve restare chiusa.
    """
    monkeypatch.delenv(notifier.VARIABILE_SILENZIO, raising=False)
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert notifier.in_prova()
