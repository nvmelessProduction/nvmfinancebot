"""Le caratteristiche non possono vedere oltre l'istante di decisione.

Sbirciare anche di una barra fa sembrare perfetto ogni CRT. Il progetto ci e'
gia' cascato: `CRT-17` dava 85,7% di winrate e +15,3 sigma filtrando con le
candele SUCCESSIVE a `N2`, e guardando solo cio' che si vede davvero al
momento dell'ingresso spariva del tutto -- meno di 30 campioni per coppia.

Era il quinto falso positivo del progetto, e tutti e cinque avevano lo stesso
aspetto: **un numero troppo bello**.

Questo file e' la rete meccanica. Non basta l'intenzione di non sbirciare:
serve qualcosa che se ne accorga.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from estrazione import (                                       # noqa: E402
    LE_OTTO, caratteristiche, etichetta, verifica_niente_sbirciate,
)

from core.definizioni import Bias, Candela                     # noqa: E402
from core.parametri import TF                                  # noqa: E402
from core import setup as stp                                  # noqa: E402

QUANDO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def barra(massimo, minimo, chiusura, apertura, ore) -> Candela:
    return Candela(QUANDO + timedelta(hours=ore), apertura, massimo, minimo,
                   chiusura)


@pytest.fixture
def crt_e_storico():
    """Un CRT short formato, piu' delle barre che arrivano DOPO."""
    n1 = barra(110, 100, 109, 101, ore=0)
    # La fase: una barra spazza sopra 110 e richiude sotto.
    fase = [barra(112, 108, 109, 110, ore=1)]
    # Quello che succede dopo, e che le caratteristiche non devono vedere.
    dopo = [barra(109, 94, 95, 108, ore=2), barra(96, 90, 91, 95, ore=3)]

    crt = stp.crt_short(
        n1, fase, TF.W1,
        __import__("core.definizioni", fromlist=["KeyLevel"]).KeyLevel(
            TF.M1, __import__("core.definizioni",
                              fromlist=["TipoKeyLevel"]).TipoKeyLevel.MAX, 110.5))
    assert crt is not None, "il CRT di prova non si e' formato"
    storico = {TF.W1: (n1,), TF.H4: tuple(fase + dopo)}
    return crt, storico, fase, dopo


class TestLaReteMeccanica:

    def test_l_archivio_intero_da_lo_stesso_dell_archivio_tagliato(self, crt_e_storico):
        """Il controllo del protocollo. Se l'estrattore tronca davvero
        all'istante, le due letture coincidono."""
        crt, storico, fase, _ = crt_e_storico
        motivo = verifica_niente_sbirciate(
            crt, storico, TF.W1, TF.H4, fase[-1].orario)
        assert motivo is None, motivo

    def test_il_controllo_sa_accorgersene(self, crt_e_storico):
        """Una rete che non puo' fallire non e' una rete.

        Si passano di proposito le barre FUTURE come se fossero quelle viste
        all'ingresso: le conferme che leggono la forma delle candele devono
        rispondere diversamente.
        """
        crt, storico, fase, dopo = crt_e_storico
        istante = fase[-1].orario
        oneste, _ = caratteristiche(crt, TF.W1, fase, istante)
        sbirciate, _ = caratteristiche(crt, TF.W1, fase + dopo, istante)
        assert oneste != sbirciate, (
            "le caratteristiche non cambiano nemmeno vedendo il futuro: "
            "il controllo non potrebbe accorgersi di niente")

    def test_il_taglio_avviene_in_un_punto_solo(self):
        """L'archivio intero e l'istante si incontrano in una riga sola.
        Tutto cio' che sta a valle riceve dati gia' tagliati."""
        import inspect
        import estrazione
        corpo = inspect.getsource(estrazione.punteggi_dallo_storico)
        assert "c.orario <= istante" in corpo
        # E la funzione a valle non riceve l'archivio.
        firma = inspect.signature(estrazione.caratteristiche).parameters
        assert "storico" not in firma


class TestLaSeparazioneStrutturale:
    """La garanzia non e' una buona intenzione: e' che le due funzioni non si
    parlano."""

    def test_le_caratteristiche_non_ricevono_le_barre_successive(self):
        import inspect
        import estrazione
        firma = inspect.signature(estrazione.caratteristiche).parameters
        assert "successive" not in firma
        assert "barre_fino_a_ora" in firma
        # E nemmeno lo storico intero: senza quello in mano non puo' guardare
        # oltre nemmeno volendo.
        assert "storico" not in firma and "storici" not in firma

    def test_l_etichetta_non_riceve_le_conferme(self):
        import inspect
        import estrazione
        firma = inspect.signature(estrazione.etichetta).parameters
        for vietato in ("conferme", "responso", "caratteristiche"):
            assert vietato not in firma

    def test_l_etichetta_non_usa_il_key_level_di_SETUP_14(self):
        """Il bersaglio dell'esito e' il 50% del range (GEST-07, CRT-16). Il
        key level di SETUP-14 e' il target del 75% RESIDUO dopo il parziale:
        misurarci sopra l'esito intero confonderebbe due momenti diversi."""
        import inspect
        import estrazione
        corpo = inspect.getsource(estrazione.etichetta)
        assert "gest.tp1(" in corpo
        assert "target_iniziale" not in corpo


class TestLEtichettaPuoGuardareAvanti:
    """E' il suo mestiere: l'asimmetria e' voluta."""

    def test_usa_le_barre_successive(self, crt_e_storico):
        crt, _, _, dopo = crt_e_storico
        esito, ingresso, stop, target = etichetta(
            crt, dopo, barre_massime=10, costo_per_lato=0.0)
        assert esito is not None
        assert esito.come in ("target", "stop", "scaduto")
        assert stop > ingresso, "su uno short lo stop sta sopra"
        assert target < ingresso, "e il bersaglio sotto"

    def test_senza_barre_successive_non_c_e_etichetta(self, crt_e_storico):
        """Un CRT in fondo all'archivio non ha esito: va scartato, non
        inventato."""
        crt, _, _, _ = crt_e_storico
        esito, _, _, _ = etichetta(crt, [], 10, 0.0)
        assert esito is None
