"""L'avviso di storia corta deve smettere di ripetersi, non di esistere.

Ripetuto ad ogni valutazione ha gia' nascosto un guasto vero: il log scorreva
troppo in fretta per leggerlo. Ma la prima versione del rimedio teneva un
insieme di chiavi che cresceva e basta, e allora una serie che si rompe, viene
riparata e si rompe di nuovo resta muta per sempre -- il che e' il modo
peggiore di risolvere un problema di rumore.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.definizioni import Candela
from core.fornitore_tradingview import FornitoreTradingView
from core.parametri import TF


def _candele(quante: int, anni_fa: float) -> list[Candela]:
    inizio = datetime.now(timezone.utc) - timedelta(days=365 * anni_fa)
    return [
        Candela(orario=inizio + timedelta(hours=i),
                apertura=1.0, massimo=1.1, minimo=0.9, chiusura=1.0)
        for i in range(quante)
    ]


@pytest.fixture
def fornitore():
    return FornitoreTradingView()


def _avvisi(caplog) -> int:
    return len([r for r in caplog.records if "DEF-26" in r.getMessage()])


class TestAvvisoStoriaCorta:

    def test_non_si_ripete(self, fornitore, caplog):
        caplog.set_level("INFO")
        storico = {TF.H1: _candele(2, 1)}
        for _ in range(5):
            fornitore._segnala_storia_corta("6E", storico)
        assert _avvisi(caplog) == 1

    def test_si_riarma_quando_la_serie_guarisce(self, fornitore, caplog):
        """Il caso che l'insieme-che-cresce sbagliava."""
        caplog.set_level("INFO")
        rotta = {TF.H1: _candele(2, 1)}
        sana = {TF.H1: _candele(100, 10)}

        fornitore._segnala_storia_corta("6E", rotta)
        fornitore._segnala_storia_corta("6E", sana)     # guarita: nessun avviso
        fornitore._segnala_storia_corta("6E", rotta)    # si rompe di nuovo

        assert _avvisi(caplog) == 2

    def test_un_peggioramento_si_vede(self, fornitore, caplog):
        """Da "corta" a "vuoto" e' uno stato nuovo, va detto."""
        caplog.set_level("INFO")
        corta = {TF.H1: _candele(50, 1)}
        vuota = {TF.H1: _candele(1, 1)}

        fornitore._segnala_storia_corta("6E", corta)
        fornitore._segnala_storia_corta("6E", vuota)

        assert _avvisi(caplog) == 2

    def test_una_serie_sana_non_dice_niente(self, fornitore, caplog):
        caplog.set_level("INFO")
        fornitore._segnala_storia_corta("6E", {TF.H1: _candele(100, 10)})
        assert _avvisi(caplog) == 0

    def test_strumenti_diversi_parlano_ognuno_per_se(self, fornitore, caplog):
        caplog.set_level("INFO")
        storico = {TF.H1: _candele(2, 1)}
        fornitore._segnala_storia_corta("6E", storico)
        fornitore._segnala_storia_corta("GC", storico)
        assert _avvisi(caplog) == 2
