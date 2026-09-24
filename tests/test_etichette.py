"""L'etichetta e' la meta' del dataset che conta.

Le caratteristiche dicono cosa si vedeva; l'etichetta dice cosa e' successo,
ed e' il numero che il modello della Fase 2 imparera' a predire. Sbagliarla
non produce un errore: produce un modello che impara benissimo la cosa
sbagliata.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from etichette import esito_del_crt                          # noqa: E402

from core.definizioni import Bias, Candela                   # noqa: E402

QUANDO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def barra(massimo, minimo, chiusura, apertura=None, ore=0) -> Candela:
    return Candela(QUANDO + timedelta(hours=ore),
                   apertura if apertura is not None else chiusura,
                   massimo, minimo, chiusura)


class TestUnoShortCheVaAlTarget:
    """Ingresso 100, stop 102, target 94: rischio 2, rendimento 6, 3 R."""

    def test_tre_erre_senza_costi(self):
        e = esito_del_crt(100, 102, 94, Bias.SHORT,
                          [barra(101, 93, 95)], barre_massime=10)
        assert e.come == "target"
        assert e.erre == pytest.approx(3.0)
        assert e.barre == 1

    def test_i_costi_si_pagano_due_volte(self):
        """All'entrata e all'uscita: e' la differenza fra un vantaggio e una
        perdita su stop stretti, e il progetto ha gia' misurato che lo spread
        da solo costa fra 0,15 e 0,35 R."""
        e = esito_del_crt(100, 102, 94, Bias.SHORT,
                          [barra(101, 93, 95)], barre_massime=10,
                          costo_per_lato=0.1)
        assert e.erre == pytest.approx((6 - 0.2) / 2)


class TestLaStessaBarraViceLoStop:
    """Non si sa in che ordine il prezzo abbia toccato i due livelli.

    Fra due letture possibili si sceglie la peggiore: e' la stessa prudenza
    che la sentinella applica dal vivo in `livello_toccato`.
    """

    def test_una_barra_che_tocca_entrambi(self):
        e = esito_del_crt(100, 102, 94, Bias.SHORT,
                          [barra(103, 93, 95)], barre_massime=10)
        assert e.come == "stop"
        assert e.erre == pytest.approx(-1.0)

    def test_lo_stop_paga_anche_i_costi(self):
        """Una perdita piena non e' esattamente -1 R: e' -1 R meno il giro."""
        e = esito_del_crt(100, 102, 94, Bias.SHORT, [barra(103, 93, 95)],
                          barre_massime=10, costo_per_lato=0.1)
        assert e.erre == pytest.approx(-(2 + 0.2) / 2)
        assert e.erre < -1.0


class TestLoScaduto:
    """Il terzo esito, senza il quale il campione mente.

    Scartare le operazioni che non si risolvono e' gia' una scelta: tiene solo
    i casi netti e fa sembrare la strategia piu' decisa di quanto sia.
    """

    def test_vale_l_erre_alla_chiusura(self):
        piatte = [barra(101, 99, 99.5, ore=i) for i in range(5)]
        e = esito_del_crt(100, 102, 94, Bias.SHORT, piatte, barre_massime=3)
        assert e.come == "scaduto"
        assert e.barre == 3
        assert e.erre == pytest.approx(0.5 / 2)

    def test_puo_essere_negativo(self):
        """Scaduto non vuol dire pari: vuol dire non risolto."""
        contro = [barra(101.5, 99, 101, ore=i) for i in range(3)]
        e = esito_del_crt(100, 102, 94, Bias.SHORT, contro, barre_massime=2)
        assert e.come == "scaduto"
        assert e.erre < 0

    def test_il_tetto_conta_davvero(self):
        """Con piu' barre disponibili si guarda solo fino a `barre_massime`:
        altrimenti ogni operazione finirebbe prima o poi da qualche parte, e
        il tetto non sarebbe un tetto."""
        tardi = [barra(101, 99, 99.5, ore=i) for i in range(5)]
        tardi.append(barra(101, 93, 94, ore=6))       # target, ma alla sesta
        e = esito_del_crt(100, 102, 94, Bias.SHORT, tardi, barre_massime=3)
        assert e.come == "scaduto"


class TestUnLongSimmetrico:
    def test_target(self):
        e = esito_del_crt(100, 98, 106, Bias.LONG,
                          [barra(107, 99, 105)], barre_massime=10)
        assert e.come == "target"
        assert e.erre == pytest.approx(3.0)

    def test_stop(self):
        e = esito_del_crt(100, 98, 106, Bias.LONG,
                          [barra(101, 97, 99)], barre_massime=10)
        assert e.come == "stop"
        assert e.erre == pytest.approx(-1.0)


class TestQuandoNonSiPuoEtichettare:
    """Un'etichetta inventata e' peggio di un'etichetta assente."""

    def test_senza_rischio_non_esiste_un_erre(self):
        assert esito_del_crt(100, 100, 94, Bias.SHORT,
                             [barra(101, 93, 95)], barre_massime=10) is None

    def test_senza_barre_successive(self):
        assert esito_del_crt(100, 102, 94, Bias.SHORT, [], barre_massime=10) is None

    def test_livelli_incoerenti(self):
        """Target dalla parte dello stop: non descrive l'operazione che si
        dice di misurare."""
        assert esito_del_crt(100, 102, 106, Bias.SHORT,
                             [barra(101, 93, 95)], barre_massime=10) is None
        assert esito_del_crt(100, 94, 106, Bias.SHORT,
                             [barra(101, 93, 95)], barre_massime=10) is None


class TestLaSeparazioneDalleCaratteristiche:
    def test_l_etichetta_non_sa_nulla_del_bot(self):
        """Puo' guardare il futuro -- e' il suo mestiere -- mentre le
        caratteristiche non possono mai. Tenerle separate e' il modo di non
        confondere le due cose."""
        import inspect
        import etichette
        corpo = inspect.getsource(etichette)
        for vietato in ("conferme_di_romeo", "cerca_crt", "motore", "valuta"):
            assert vietato not in corpo, (
                f"l'etichetta conosce {vietato}: sta guardando le "
                "caratteristiche invece del solo esito")
