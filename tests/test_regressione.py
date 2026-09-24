"""La logistica scritta a mano: che faccia quello che dice.

Un pezzo che decide va capito, e un pezzo che nessuno ha provato non e'
capito: e' sperato. Qui si prova su dati costruiti apposta, dove la risposta
giusta si sa in anticipo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from regressione import (                                       # noqa: E402
    LAMBDA, _logistica, adatta, brier, brier_di_riferimento, previsione,
)


@pytest.fixture
def separabile():
    """Una colonna che spiega tutto, piu' rumore."""
    caso = np.random.default_rng(20260924)
    n = 800
    x = caso.normal(size=n)
    rumore = caso.normal(size=n)
    p = 1.0 / (1.0 + np.exp(-(0.5 + 1.8 * x)))
    y = (caso.random(n) < p).astype(float)
    return np.column_stack([x, rumore]), y


class TestLaLogisticaStabile:

    def test_non_trabocca_sui_numeri_grandi(self):
        z = np.array([-1e6, -800.0, 0.0, 800.0, 1e6])
        p = _logistica(z)
        assert np.all(np.isfinite(p))
        assert np.all((p >= 0.0) & (p <= 1.0))

    def test_e_simmetrica(self):
        z = np.array([-3.0, -0.5, 0.0, 0.5, 3.0])
        assert _logistica(z) + _logistica(-z) == pytest.approx(
            np.ones_like(z), abs=1e-12)


class TestLAdattamento:

    def test_trova_il_segno_giusto(self, separabile):
        X, y = separabile
        stima = adatta(X, y, penalita=0.1)
        assert stima.converge
        assert stima.pesi[0] > 0, "la colonna che spiega ha peso positivo"
        assert abs(stima.pesi[1]) < abs(stima.pesi[0]) / 3, "il rumore pesa poco"

    def test_converge_in_poche_iterazioni(self, separabile):
        X, y = separabile
        assert adatta(X, y).iterazioni <= 15

    def test_una_colonna_costante_non_fa_esplodere_niente(self):
        """`CRT-15` risponde `None` su tutte e 16.463 le righe del campo di
        prova: le sue due colonne sono zero ovunque. Senza penalita' la
        matrice del passo di Newton e' singolare."""
        caso = np.random.default_rng(1)
        x = caso.normal(size=400)
        zero = np.zeros(400)
        y = (caso.random(400) < 1 / (1 + np.exp(-x))).astype(float)
        stima = adatta(np.column_stack([x, zero]), y, penalita=LAMBDA)
        assert np.all(np.isfinite(stima.pesi))
        assert stima.pesi[1] == pytest.approx(0.0, abs=1e-9), (
            "una costante non informa: il suo peso deve andare a zero")

    def test_la_penalita_stringe_i_pesi(self):
        caso = np.random.default_rng(2)
        x = caso.normal(size=300)
        y = (caso.random(300) < 1 / (1 + np.exp(-2 * x))).astype(float)
        X = x.reshape(-1, 1)
        leggera = adatta(X, y, penalita=0.01)
        pesante = adatta(X, y, penalita=100.0)
        assert abs(pesante.pesi[0]) < abs(leggera.pesi[0])

    def test_l_intercetta_non_e_penalizzata(self):
        """Penalizzare l'intercetta spingerebbe la probabilita' di base verso
        un mezzo anche quando i dati dicono un terzo -- e qui la base e' il
        35,9%."""
        y = np.zeros(500)
        y[:150] = 1.0                       # base 30%
        X = np.zeros((500, 1))
        stima = adatta(X, y, penalita=1000.0)
        p = previsione(stima, X)
        assert p[0] == pytest.approx(0.30, abs=0.01)

    def test_il_peso_di_riga_equivale_a_ripetere_la_riga(self):
        """E' cio' su cui poggia il ricampionamento a blocchi."""
        caso = np.random.default_rng(3)
        X = caso.normal(size=(60, 2))
        y = (caso.random(60) < 0.5).astype(float)
        doppie = adatta(np.vstack([X, X[:10]]), np.concatenate([y, y[:10]]),
                        penalita=0.5)
        pesi = np.ones(60)
        pesi[:10] = 2.0
        ripesate = adatta(X, y, penalita=0.5, peso_riga=pesi)
        assert ripesate.intercetta == pytest.approx(doppie.intercetta, abs=1e-6)
        assert np.allclose(ripesate.pesi, doppie.pesi, atol=1e-6)

    def test_rifiuta_dati_incoerenti(self):
        with pytest.raises(ValueError):
            adatta(np.zeros((3, 2)), np.zeros(4))
        with pytest.raises(ValueError):
            adatta(np.zeros((0, 2)), np.zeros(0))


class TestIlBrier:

    def test_zero_quando_si_indovina_sempre(self):
        assert brier([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(0.0)

    def test_distingue_la_sicurezza(self):
        """L'accuratezza non sa distinguere chi dice 51% da chi dice 99%, e
        qui la differenza e' tutta la decisione: `p` viene MOLTIPLICATA per
        il rapporto."""
        timido = brier([0.51, 0.49], [1.0, 0.0])
        deciso = brier([0.99, 0.01], [1.0, 0.0])
        assert deciso < timido

    def test_il_riferimento_e_chi_dice_sempre_la_base(self):
        y = [1.0] * 36 + [0.0] * 64             # la base del campo di prova
        riferimento = brier_di_riferimento(y)
        assert riferimento == pytest.approx(0.36 * 0.64, abs=1e-9)
        assert brier([0.36] * 100, y) == pytest.approx(riferimento)

    def test_un_modello_che_non_batte_la_base_non_ha_imparato(self, separabile):
        X, y = separabile
        stima = adatta(X, y, penalita=0.1)
        assert brier(previsione(stima, X), y) < brier_di_riferimento(y)
