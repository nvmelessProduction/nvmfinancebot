"""Il walk-forward e i criteri: che nessuna riga sia giudicata da chi l'ha vista.

Un modello che decide su righe che ha gia' visto non sbaglia: indovina. E'
l'errore piu' facile da commettere nel codice e il piu' difficile da vedere
nei numeri, perche' produce esattamente l'aspetto che un buon risultato
avrebbe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from addestra import (                                          # noqa: E402
    ANNI_POSITIVI_MINIMI, GUADAGNO_MINIMO, OPERAZIONI_MINIME,
    STABILITA_MINIMA, b1_il_filtro_di_oggi, cammina, matrice,
    stabilita_dei_segni,
)

from core.parametri import CONFERME_CHE_BLOCCANO_DA_SOLE        # noqa: E402
from core.pesi import LE_OTTO, nomi_delle_colonne               # noqa: E402


def riga(anno, mese=1, giorno=1, esito="target", erre=1.0, rapporto=2.0,
         costo=0.05, allineati="", **conferme) -> dict:
    d = {r: conferme.get(r.replace("-", "_"), "") for r in LE_OTTO}
    d.update({
        "strumento": "EURUSD", "coppia": "TF_1D->TF_H1",
        "quando": f"{anno}-{mese:02d}-{giorno:02d}T00:00:00+00:00",
        "verso": "LONG", "ingresso": "1.0", "stop": "0.99", "target": "1.02",
        "rapporto": str(rapporto), "costo_erre": str(costo),
        "allineati": allineati, "esito": esito, "erre": str(erre),
        "barre": "3",
    })
    return d


class TestLaCodificaVieneDaUnPostoSolo:

    def test_la_matrice_usa_le_colonne_di_core_pesi(self):
        X, y = matrice([riga(2010)])
        assert X.shape[1] == len(nomi_delle_colonne())

    def test_none_resta_none(self):
        """Nel CSV "non lo so" e' la cella vuota. Leggerla come `False`
        spegnerebbe la distinzione su cui poggia tutta la codifica."""
        vuota = matrice([riga(2010)])[0]
        negata = matrice([riga(2010, CRT_11="0")])[0]
        assert not np.array_equal(vuota, negata)

    def test_l_etichetta_e_il_bersaglio_raggiunto(self):
        assert matrice([riga(2010, esito="target")])[1][0] == 1.0
        assert matrice([riga(2010, esito="stop")])[1][0] == 0.0
        assert matrice([riga(2010, esito="scaduto")])[1][0] == 0.0


class TestB1:
    """La linea del bot di oggi, letta dal bot e non ricopiata."""

    def test_legge_la_tabella_del_bot(self):
        attive = [r for r, blocca in CONFERME_CHE_BLOCCANO_DA_SOLE.items()
                  if blocca]
        assert attive, "se nessuna bloccasse, B1 coinciderebbe con B0"
        una = attive[0].replace("-", "_")
        assert not b1_il_filtro_di_oggi(riga(2010, **{una: "0"}))

    def test_non_lo_so_non_blocca_mai(self):
        """Trasformare "non lo so" in "no" spegnerebbe il bot senza dirlo,
        ed e' esattamente la regola che il motore applica."""
        assert b1_il_filtro_di_oggi(riga(2010))

    def test_una_conferma_spenta_non_ferma_niente(self):
        spente = [r for r, blocca in CONFERME_CHE_BLOCCANO_DA_SOLE.items()
                  if not blocca]
        if not spente:
            pytest.skip("oggi bloccano tutte")
        una = spente[0].replace("-", "_")
        assert b1_il_filtro_di_oggi(riga(2010, **{una: "0"}))


class TestIlWalkForward:

    @pytest.fixture
    def righe(self):
        """Dieci anni, duecentocinquanta CRT l'anno."""
        caso = np.random.default_rng(42)
        fuori = []
        for anno in range(2006, 2016):
            for i in range(250):
                vince = caso.random() < 0.4
                fuori.append(riga(
                    anno, mese=1 + i % 12, giorno=1 + i % 28,
                    esito="target" if vince else "stop",
                    erre=2.0 if vince else -1.0,
                    CRT_11="1" if vince and caso.random() < 0.8 else "0"))
        return fuori

    def test_ogni_finestra_si_allena_solo_sul_passato(self, righe):
        blocchi = [f"b{i}" for i in range(len(righe))]
        finestre = cammina(righe, blocchi, 1.0, 2010, 2015, 0.0)
        assert finestre
        for f in finestre:
            # Allenata su tutto cio' che precede, e su nient'altro.
            attese = 250 * (f.anno - 2006)
            assert f.allenata_su == attese, (
                f"{f.anno} allenata su {f.allenata_su}, attese {attese}")

    def test_non_decide_prima_di_aver_visto_abbastanza(self, righe):
        blocchi = [f"b{i}" for i in range(len(righe))]
        finestre = cammina(righe, blocchi, 1.0, 2006, 2015, 0.0)
        assert all(f.allenata_su >= 200 for f in finestre)
        assert 2006 not in {f.anno for f in finestre}

    def test_le_prese_sono_un_sottoinsieme_delle_candidate(self, righe):
        blocchi = [f"b{i}" for i in range(len(righe))]
        for f in cammina(righe, blocchi, 1.0, 2010, 2015, 0.0):
            assert f.prese <= f.candidate
            assert len(f.erre_prese) == f.prese
            assert len(f.blocchi_presi) == f.prese

    def test_un_margine_alto_prende_di_meno(self, righe):
        blocchi = [f"b{i}" for i in range(len(righe))]
        larghe = cammina(righe, blocchi, 1.0, 2010, 2015, 0.0)
        strette = cammina(righe, blocchi, 1.0, 2010, 2015, 5.0)
        assert sum(f.prese for f in strette) < sum(f.prese for f in larghe)

    def test_l_holdout_non_entra_mai(self, righe):
        """Il walk-forward si ferma al 2023. Qui i dati finiscono prima, ma
        il limite dev'essere quello dichiarato, non quello dei dati."""
        import addestra
        assert addestra.ULTIMO_ANNO == 2023


class TestLaStabilitaDeiSegni:

    def _finta(self, pesi_per_finestra):
        from addestra import Finestra
        return [Finestra(anno=2010 + i, allenata_su=0, candidate=0, prese=0,
                         erre_prese=[], blocchi_presi=[], erre_tutte=[],
                         blocchi_tutte=[], brier_modello=0.0, brier_base=0.0,
                         pesi=p)
                for i, p in enumerate(pesi_per_finestra)]

    def test_un_segno_sempre_uguale_vale_uno(self):
        nome = nomi_delle_colonne()[0]
        finestre = self._finta([{nome: 0.5}, {nome: 0.3}, {nome: 0.9}])
        assert stabilita_dei_segni(finestre)[nome] == pytest.approx(1.0)

    def test_un_peso_che_si_ribalta_scende(self):
        """Un peso che cambia segno fra le finestre non misura una proprieta'
        del mercato: insegue il rumore di quella finestra."""
        nome = nomi_delle_colonne()[0]
        finestre = self._finta([{nome: 0.5}, {nome: -0.3}, {nome: 0.9},
                                {nome: -0.2}])
        assert stabilita_dei_segni(finestre)[nome] == pytest.approx(0.5)

    def test_un_peso_sempre_nullo_non_e_stabile(self):
        """Una colonna costante -- `CRT-15` lo e' su tutte e 16.463 le righe
        -- non ha un segno da stabilizzare, e dire che e' stabile al 100%
        la farebbe sembrare la colonna piu' affidabile di tutte."""
        nome = nomi_delle_colonne()[0]
        finestre = self._finta([{nome: 0.0}, {nome: 0.0}])
        assert stabilita_dei_segni(finestre)[nome] == 0.0


class TestICriteri:
    """Stanno in chiaro in cima al file: un criterio che si puo' cambiare
    mentre si guarda il risultato non e' un criterio."""

    def test_sono_quelli_del_protocollo(self):
        assert GUADAGNO_MINIMO == pytest.approx(0.10)
        assert ANNI_POSITIVI_MINIMI == pytest.approx(0.70)
        assert OPERAZIONI_MINIME == 300
        assert STABILITA_MINIMA == pytest.approx(0.80)
