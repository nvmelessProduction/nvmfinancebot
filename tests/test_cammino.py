"""La gestione a due tempi, e il numero che la sentinella puo' imparare.

La sentinella non decide se entrare. Decide dove sta lo stop nel secondo
tempo, ed e' l'unica cosa che decide: e' il suo ambito, e questi test lo
recintano.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from cammino import (                                           # noqa: E402
    FRAZIONE_PARZIALE, K_DI_OGGI, esito_gestito, stop_del_residuo,
)

from core.definizioni import Bias, Candela                      # noqa: E402

QUANDO = datetime(2020, 1, 6, tzinfo=timezone.utc)


def barra(ore, apertura, massimo, minimo, chiusura) -> Candela:
    return Candela(QUANDO + timedelta(hours=ore), apertura, massimo, minimo,
                   chiusura)


# Una long: ingresso 100, stop 98 (rischio 2), TP1 104, bersaglio 110.
LONG = dict(ingresso=100.0, stop=98.0, tp1=104.0, target_finale=110.0,
            verso=Bias.LONG)


class TestLoStopDelResiduo:

    def test_k_zero_e_il_pareggio(self):
        assert stop_del_residuo(100.0, 98.0, 0.0) == pytest.approx(100.0)

    def test_k_uno_e_lo_stop_di_partenza(self):
        assert stop_del_residuo(100.0, 98.0, 1.0) == pytest.approx(98.0)

    def test_a_meta_strada(self):
        assert stop_del_residuo(100.0, 98.0, 0.5) == pytest.approx(99.0)

    def test_vale_a_specchio_sulle_short(self):
        """Non c'e' un ramo per le long e uno per le short: due rami e' il
        posto dove il segno si inverte senza che nessuno se ne accorga."""
        assert stop_del_residuo(100.0, 102.0, 0.5) == pytest.approx(101.0)

    def test_il_predefinito_e_il_pareggio_secco(self):
        assert K_DI_OGGI == pytest.approx(0.0)


class TestIlPrimoTempo:

    def test_lo_stop_prima_di_tp1_uccide_tutto(self):
        dopo = [barra(1, 100, 101, 97, 98)]
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "stop"
        assert e.erre == pytest.approx(-1.0)
        assert not e.tp1_preso

    def test_stessa_barra_vince_lo_stop(self):
        """Non si sa in che ordine il prezzo ci sia passato, e fra due
        letture si sceglie la peggiore."""
        dopo = [barra(1, 100, 105, 97, 100)]
        assert esito_gestito(**LONG, successive=dopo,
                             barre_massime=10).come == "stop"

    def test_senza_niente_scade(self):
        dopo = [barra(i, 100, 101, 99, 100.5) for i in range(1, 4)]
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "scaduto"
        assert not e.tp1_preso
        assert e.erre == pytest.approx(0.25)     # (100,5 - 100) / 2

    def test_il_tetto_delle_barre_si_rispetta(self):
        dopo = [barra(i, 100, 101, 99, 100) for i in range(1, 20)]
        e = esito_gestito(**LONG, successive=dopo, barre_massime=5)
        assert e.barre == 5


class TestIlSecondoTempo:

    def test_parziale_poi_bersaglio(self):
        dopo = [barra(1, 100, 105, 100, 104),      # tocca TP1
                barra(2, 104, 111, 103, 110)]      # e poi il bersaglio
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "parziale+target"
        assert e.tp1_preso
        # 25% a +2R, 75% a +5R.
        assert e.erre == pytest.approx(0.25 * 2.0 + 0.75 * 5.0)

    def test_parziale_poi_pareggio(self):
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 104, 99, 100)]       # torna sull'ingresso
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "parziale+stop"
        # 25% a +2R, 75% a zero: resta solo il parziale.
        assert e.erre == pytest.approx(0.5)

    def test_il_residuo_non_si_misura_sulla_barra_di_TP1(self):
        """Prima di TP1 lo stop del residuo NON esisteva: valeva l'originale,
        e quella barra e' gia' passata dal primo tempo senza toccarlo.

        Riesaminarla sembra prudente e non lo e'. La barra che tocca TP1 ha
        quasi sempre l'estremo avverso sull'ingresso -- l'ingresso e' la
        chiusura di quella prima -- quindi con `k = 0` il residuo morirebbe
        quasi sempre per meccanica, non per mercato."""
        dopo = [barra(1, 100, 105, 100, 104)]      # il minimo tocca l'ingresso
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "parziale+scaduto"
        assert e.tp1_preso

    def test_ma_la_barra_dopo_lo_uccide_eccome(self):
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 104, 99.5, 100)]
        e = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        assert e.come == "parziale+stop"

    def test_k_piu_alto_lascia_piu_spazio(self):
        """E' la lamentela ricorrente: uno stop portato a pareggio troppo
        presto uccide le operazioni che sarebbero andate."""
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 104, 99.5, 100),     # sotto il pareggio
                barra(3, 100, 111, 100, 110)]      # e poi sarebbe andata
        stretta = esito_gestito(**LONG, successive=dopo, barre_massime=10, k=0.0)
        larga = esito_gestito(**LONG, successive=dopo, barre_massime=10, k=1.0)
        assert stretta.come == "parziale+stop"
        assert larga.come == "parziale+target"
        assert larga.erre > stretta.erre

    def test_ma_k_piu_alto_perde_di_piu_quando_va_male(self):
        """Il baratto, che e' il motivo per cui il numero va misurato e non
        scelto: piu' spazio significa anche piu' perdita quando non torna."""
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 104, 97, 97)]        # crolla
        stretta = esito_gestito(**LONG, successive=dopo, barre_massime=10, k=0.0)
        larga = esito_gestito(**LONG, successive=dopo, barre_massime=10, k=1.0)
        assert larga.erre < stretta.erre

    def test_parziale_poi_scade(self):
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 105, 103, 105)]
        e = esito_gestito(**LONG, successive=dopo, barre_massime=2)
        assert e.come == "parziale+scaduto"


class TestLeShort:
    """Lo specchio esatto: se un verso funziona e l'altro no, il difetto vive
    per mesi perche' meta' delle operazioni sembra andare bene."""

    SHORT = dict(ingresso=100.0, stop=102.0, tp1=96.0, target_finale=90.0,
                 verso=Bias.SHORT)

    def test_parziale_poi_bersaglio(self):
        dopo = [barra(1, 100, 100, 95, 96),
                barra(2, 96, 97, 89, 90)]
        e = esito_gestito(**self.SHORT, successive=dopo, barre_massime=10)
        assert e.come == "parziale+target"
        assert e.erre == pytest.approx(0.25 * 2.0 + 0.75 * 5.0)

    def test_lo_stop_sta_sopra(self):
        dopo = [barra(1, 100, 103, 99, 102)]
        assert esito_gestito(**self.SHORT, successive=dopo,
                             barre_massime=10).come == "stop"


class TestICosti:

    def test_si_pagano_due_lati_in_tutto(self):
        """Uno all'ingresso sul 100%, uno all'uscita su ciascuna frazione:
        in totale due, come nell'etichetta semplice."""
        dopo = [barra(1, 100, 105, 100, 104),
                barra(2, 104, 111, 103, 110)]
        senza = esito_gestito(**LONG, successive=dopo, barre_massime=10)
        con = esito_gestito(**LONG, successive=dopo, barre_massime=10,
                            costo_per_lato=0.1)
        # costo in R = 0,1/2 = 0,05, pagato due volte.
        assert senza.erre - con.erre == pytest.approx(0.10)

    def test_anche_lo_stop_paga_due_lati(self):
        dopo = [barra(1, 100, 101, 97, 98)]
        con = esito_gestito(**LONG, successive=dopo, barre_massime=10,
                            costo_per_lato=0.1)
        assert con.erre == pytest.approx(-1.10)


class TestLivelliIncoerenti:

    def test_un_bersaglio_dalla_parte_sbagliata_non_si_misura(self):
        dopo = [barra(1, 100, 105, 100, 104)]
        assert esito_gestito(
            ingresso=100.0, stop=98.0, tp1=104.0, target_finale=99.0,
            verso=Bias.LONG, successive=dopo, barre_massime=10) is None

    def test_rischio_nullo(self):
        dopo = [barra(1, 100, 105, 100, 104)]
        assert esito_gestito(
            ingresso=100.0, stop=100.0, tp1=104.0, target_finale=110.0,
            verso=Bias.LONG, successive=dopo, barre_massime=10) is None

    def test_senza_barre_successive(self):
        assert esito_gestito(**LONG, successive=[], barre_massime=10) is None

    def test_una_frazione_impossibile_e_un_errore(self):
        dopo = [barra(1, 100, 105, 100, 104)]
        with pytest.raises(ValueError):
            esito_gestito(**LONG, successive=dopo, barre_massime=10,
                          frazione=1.5)


class TestLaFrazione:

    def test_e_un_quarto_come_dice_GEST_04(self):
        assert FRAZIONE_PARZIALE == pytest.approx(0.25)
