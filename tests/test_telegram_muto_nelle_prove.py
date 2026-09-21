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


class TestNienteChiamateAPagamento:
    """L'altra porta che da' sul mondo e costa: l'API di Claude.

    Da quando il giudizio viene interpellato anche sui CRT rifiutati, una
    valutazione dentro una prova e' una chiamata a pagamento. Acceso il
    giudizio, questa suite e' passata da 5 secondi a 135 e ha bruciato
    credito vero -- e il tetto di spesa non se ne e' accorto, perche' le
    prove tengono il loro conto in un archivio temporaneo. Il tetto protegge
    la produzione, non le prove: le prove vanno chiuse a parte.
    """

    def test_la_porta_risulta_chiusa(self):
        from core.ambiente import in_prova
        assert in_prova()

    def test_giudica_non_chiama_l_api(self, monkeypatch):
        from core import giudizio_claude as g

        chiamate = []
        if g.anthropic is not None:
            monkeypatch.setattr(
                g.anthropic, "Anthropic",
                lambda **k: chiamate.append(k) or (_ for _ in ()).throw(
                    AssertionError("una prova ha costruito il client Anthropic")))
        verdetto = g.giudica({"prova": True})
        assert chiamate == []
        assert verdetto.accetta is False
        assert "prova" in (verdetto.errore or "")

    def test_giudica_obiezione_non_chiama_l_api(self, monkeypatch):
        from core import giudizio_claude as g

        if g.anthropic is not None:
            monkeypatch.setattr(
                g.anthropic, "Anthropic",
                lambda **k: (_ for _ in ()).throw(
                    AssertionError("una prova ha costruito il client Anthropic")))
        verdetto = g.giudica_obiezione({"prova": True}, "RISK-05", "bias contraria")
        assert verdetto.accetta is False

    def test_un_rifiuto_non_e_un_accetta(self):
        """Il fallimento chiuso vale anche qui: senza giudizio non si apre."""
        from core import giudizio_claude as g
        assert g.giudica({"prova": True}).accetta is False
