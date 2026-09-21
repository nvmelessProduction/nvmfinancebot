"""Stop e bersagli devono uscire dove li mette la struttura.

DEF-32 fa analizzare sul future ed eseguire sul CFD, e quando le candele
arrivano da TradingView la conversione di DEF-33 serve davvero: `6J` quota
0,0067 e `USDJPY` 157. Ma con Dukascopy o MT5 l'archivio contiene gia'
`USDJPY`, perche' quei motori leggono il book del broker. Convertire una
seconda volta sposta i livelli di quanto il mercato si e' mosso da quando
`N2` ha chiuso, e su `USDCHF`/`USDJPY` -- che portano `segno_invertito` --
li ribalta proprio di verso.
"""

import pytest

from core.definizioni import livello_cfd
from core.motore import Fotografia, _coppia_per_la_size, _sulla_scala_del_cfd


def _foto(strumento: str, prezzo_cfd: float, in_scala_cfd: bool) -> Fotografia:
    from datetime import datetime, timezone
    return Fotografia(
        istante=datetime(2026, 9, 21, tzinfo=timezone.utc),
        strumento=strumento,
        candele_per_tf={},
        prezzo_cfd=prezzo_cfd,
        analisi_in_scala_cfd=in_scala_cfd,
    )


class TestCandeleGiaInScalaCfd:
    """Il caso di questo impianto: FORNITORE_DATI = mt5."""

    def test_il_livello_resta_dov_e(self):
        foto = _foto("XAUUSD", prezzo_cfd=4352.94, in_scala_cfd=True)
        assert _sulla_scala_del_cfd(foto, 4354.88, ancora=4351.68) == 4354.88

    def test_prima_veniva_spostato_di_quanto_si_era_mosso_il_mercato(self):
        """Il difetto misurato su XAUUSD il 2026-09-21."""
        spostato = livello_cfd(4354.88, 4351.68, 4352.94, "XAUUSD")
        assert spostato == pytest.approx(4356.14, abs=0.01)
        # e lo scarto e' esattamente prezzo di adesso - chiusura di N2
        assert spostato - 4354.88 == pytest.approx(4352.94 - 4351.68, abs=0.01)

    def test_su_usdchf_il_verso_non_si_ribalta_piu(self):
        """Il caso che rendeva USDCHF incapace di aprire qualunque cosa.

        Un livello SOPRA la chiusura di N2 deve restare sopra. Con
        `segno_invertito` applicato a candele gia' del CFD finiva sotto, e
        allora stop e bersaglio cadevano dalla stessa parte dell'ingresso.
        """
        foto = _foto("USDCHF", prezzo_cfd=0.82336, in_scala_cfd=True)
        sopra = _sulla_scala_del_cfd(foto, 0.82500, ancora=0.82300)
        assert sopra > foto.prezzo_cfd

        ribaltato = livello_cfd(0.82500, 0.82300, 0.82336, "USDCHF")
        assert ribaltato < 0.82336, "il difetto: il livello di sopra finiva sotto"

    def test_la_size_misura_il_rischio_dall_ingresso(self):
        foto = _foto("EURUSD", prezzo_cfd=1.0850, in_scala_cfd=True)
        ancora, stop = _coppia_per_la_size(
            foto, ancora=1.0800, stop_analisi=1.0780, stop_cfd=1.0780)
        assert (ancora, stop) == (1.0850, 1.0780)
        # distanza relativa x prezzo_cfd == |prezzo_cfd - stop|
        relativa = abs(ancora - stop) / ancora
        assert relativa * foto.prezzo_cfd == pytest.approx(abs(1.0850 - 1.0780))


class TestCandeleDelFuture:
    """La via TradingView non cambia: li' la conversione serve."""

    def test_il_livello_viene_convertito(self):
        foto = _foto("XAUUSD", prezzo_cfd=4352.94, in_scala_cfd=False)
        assert _sulla_scala_del_cfd(foto, 4354.88, ancora=4351.68) == \
            livello_cfd(4354.88, 4351.68, 4352.94, "XAUUSD")

    def test_la_size_resta_misurata_sui_livelli_del_future(self):
        foto = _foto("USDJPY", prezzo_cfd=157.24, in_scala_cfd=False)
        assert _coppia_per_la_size(
            foto, ancora=0.006700, stop_analisi=0.006690, stop_cfd=157.0
        ) == (0.006700, 0.006690)

    def test_su_6j_la_conversione_porta_dalla_scala_del_future_a_quella_del_cfd(self):
        """0,0067 non puo' finire al broker come stop su USDJPY."""
        foto = _foto("USDJPY", prezzo_cfd=157.24, in_scala_cfd=False)
        stop = _sulla_scala_del_cfd(foto, 0.006690, ancora=0.006700)
        assert 150 < stop < 165


class TestDirezioneDiEsecuzione:
    """Il verso dell'ordine, che e' la cosa che si paga se e' sbagliata."""

    def test_su_candele_del_cfd_il_verso_non_si_ribalta(self):
        from core.definizioni import Bias, direzione_di_esecuzione
        for s in ("EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "XAUUSD"):
            assert direzione_di_esecuzione(Bias.LONG, s, True) is Bias.LONG
            assert direzione_di_esecuzione(Bias.SHORT, s, True) is Bias.SHORT

    def test_su_candele_del_future_usdchf_e_usdjpy_si_ribaltano(self):
        from core.definizioni import Bias, direzione_di_esecuzione
        assert direzione_di_esecuzione(Bias.LONG, "USDCHF", False) is Bias.SHORT
        assert direzione_di_esecuzione(Bias.LONG, "USDJPY", False) is Bias.SHORT
        assert direzione_di_esecuzione(Bias.LONG, "EURUSD", False) is Bias.LONG

    def test_col_dollaro_forte_usdchf_e_usdjpy_vanno_comprate(self):
        """La cosa che l'utente ha fatto notare, verificata capo a capo.

        USDCHF e USDJPY quotano il dollaro contro l'altra valuta: se il
        dollaro sale, salgono. SETUP-19 lo dice gia' nella sua tabella, ma il
        verso del CRT arrivava al confronto ribaltato, e allora le due coppie
        trascinate su dal dollaro forte sembravano sempre contrarie.
        """
        from core.definizioni import Bias, direzione_di_esecuzione
        from core.setup import direzione_da_dxy

        for strumento in ("USDCHF", "USDJPY"):
            voluto = direzione_da_dxy(Bias.LONG, strumento)
            assert voluto is Bias.LONG
            passa = direzione_di_esecuzione(Bias.LONG, strumento, True)
            assert passa is voluto, "un CRT rialzista qui deve poter passare"

        voluto = direzione_da_dxy(Bias.LONG, "EURUSD")
        assert voluto is Bias.SHORT
        assert direzione_di_esecuzione(Bias.SHORT, "EURUSD", True) is voluto
