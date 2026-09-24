"""Il bootstrap a blocchi: che l'intervallo si allarghi quando deve.

Assumere un'indipendenza che non c'e' **restringe** l'intervallo. Non lo
allarga: lo restringe. Cioe' produce esattamente l'errore che fa piu' danno --
dichiarare significativo un vantaggio che non lo e', e mandarlo a operare.

Questo file prova che la rete morde: sugli stessi numeri, ricampionare i
blocchi deve dare un intervallo piu' largo che ricampionare le righe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from bootstrap import (                                         # noqa: E402
    differenza, esclude_lo_zero, indici_per_blocco, intervallo,
)


class TestIBlocchi:

    def test_raggruppa_per_etichetta(self):
        gruppi = indici_per_blocco(["a", "b", "a", "c", "b"])
        assert gruppi["a"] == [0, 2]
        assert gruppi["b"] == [1, 4]
        assert gruppi["c"] == [3]


class TestLIntervallo:

    def test_contiene_il_punto(self):
        valori = [0.1, -0.2, 0.3, -0.1, 0.05] * 40
        blocchi = [f"b{i}" for i in range(len(valori))]
        punto, basso, alto = intervallo(valori, blocchi, giri=400)
        assert basso <= punto <= alto

    def test_e_ripetibile(self):
        """Un bootstrap che da' risposte diverse ad ogni giro non e' una
        misura: e' un modo di tirare finche' esce il numero che piace."""
        valori = list(np.random.default_rng(7).normal(size=200))
        blocchi = [f"b{i // 3}" for i in range(200)]
        uno = intervallo(valori, blocchi, giri=300)
        due = intervallo(valori, blocchi, giri=300)
        assert uno == due

    def test_i_blocchi_allargano_l_intervallo(self):
        """La prova che serve. Righe perfettamente correlate dentro il
        blocco: trattarle come indipendenti finge un campione dieci volte
        piu' grande di quello che c'e'."""
        caso = np.random.default_rng(11)
        per_blocco = caso.normal(size=60)
        valori = np.repeat(per_blocco, 10)          # dieci copie identiche
        veri = [f"b{i // 10}" for i in range(len(valori))]
        finti = [f"r{i}" for i in range(len(valori))]

        _, b1, a1 = intervallo(valori, veri, giri=600)
        _, b2, a2 = intervallo(valori, finti, giri=600)
        assert (a1 - b1) > 2.0 * (a2 - b2), (
            "ricampionare le righe finge un campione che non c'e'")

    def test_rifiuta_lunghezze_diverse(self):
        with pytest.raises(ValueError):
            intervallo([1.0, 2.0], ["a"], giri=10)

    def test_rifiuta_il_vuoto(self):
        with pytest.raises(ValueError):
            intervallo([], [], giri=10)

    def test_accetta_una_statistica_diversa_dalla_media(self):
        valori = [1.0] * 50 + [9.0] * 50
        blocchi = [f"b{i}" for i in range(100)]
        punto, _, _ = intervallo(valori, blocchi, giri=200,
                                 statistica=lambda v: float(np.median(v)))
        assert punto == pytest.approx(5.0)


class TestLoZero:

    def test_un_intervallo_a_cavallo_non_esclude_niente(self):
        assert not esclude_lo_zero(-0.04, 0.02)

    def test_tutto_sopra_o_tutto_sotto_esclude(self):
        assert esclude_lo_zero(0.01, 0.20)
        assert esclude_lo_zero(-0.30, -0.02)

    def test_e_piu_severo_del_centro_positivo(self):
        """"Il centro e' positivo" e "l'intervallo esclude lo zero" sono due
        cose molto diverse quando l'errore e' dello stesso ordine del
        segnale. Qui lo e': B0 vale -0,0509 con errore 0,0162."""
        centro = (0.05 + -0.01) / 2
        assert centro > 0
        assert not esclude_lo_zero(-0.01, 0.05)


class TestLaDifferenza:

    def test_misura_quanto_si_guadagna_rispetto_alla_linea(self):
        blocchi = [f"b{i}" for i in range(200)]
        base = [0.0] * 200
        meglio = [0.5] * 200
        punto, basso, alto = differenza(meglio, blocchi, base, blocchi, giri=300)
        assert punto == pytest.approx(0.5)
        assert esclude_lo_zero(basso, alto)

    def test_due_serie_uguali_non_si_distinguono(self):
        caso = np.random.default_rng(5)
        valori = list(caso.normal(size=300))
        blocchi = [f"b{i // 2}" for i in range(300)]
        _, basso, alto = differenza(valori, blocchi, valori, blocchi, giri=300)
        assert not esclude_lo_zero(basso, alto)

    def test_non_si_ottiene_sottraendo_due_intervalli(self):
        """Le due misure condividono i blocchi: sottrarre gli estremi
        darebbe un intervallo molto piu' largo del vero, e stavolta
        l'errore e' dalla parte prudente -- ma resta un errore."""
        caso = np.random.default_rng(13)
        valori_a = list(caso.normal(loc=0.4, size=300))
        valori_b = [v - 0.4 for v in valori_a]
        blocchi = [f"b{i}" for i in range(300)]
        _, ba, aa = intervallo(valori_a, blocchi, giri=300)
        _, bb, ab = intervallo(valori_b, blocchi, giri=300)
        _, bd, ad = differenza(valori_a, blocchi, valori_b, blocchi, giri=300)
        assert (ad - bd) < (aa - ba) + (ab - bb)
