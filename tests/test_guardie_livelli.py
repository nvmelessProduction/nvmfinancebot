"""I quattro controlli sui livelli, provati uno per uno.

Fase 0.5 del piano: `valuta()` faceva 686 righe, e questi quattro controlli
stavano dentro insieme a tutto il resto -- cercare il CRT, calcolare i
livelli, chiedere la size, applicare le esclusioni. In 686 righe nessuno vede
che il lato dello stop e' confrontato col prezzo sbagliato, ed e' esattamente
quello che e' successo: tutti e quattro i difetti che questi controlli
fermano sono vissuti indisturbati li' dentro fino al 2026-09-23.

Adesso sono un agente puro -- quattro numeri e un verso -- e si provano senza
costruire una `Fotografia`. Questo file e' la prova che ora si puo'.
"""

from __future__ import annotations

import pytest

from core.definizioni import Bias
from core.motore import guardie_sui_livelli
from core.parametri import RAPPORTO_MINIMO, TF


def _corto(bersaglio=157.000, stop=158.400, ingresso=158.204):
    return guardie_sui_livelli(bersaglio, stop, ingresso, Bias.SHORT, TF.H1)


def _lungo(bersaglio=1.1500, stop=1.1300, ingresso=1.1389):
    return guardie_sui_livelli(bersaglio, stop, ingresso, Bias.LONG, TF.H1)


class TestQuandoITreLivelliReggono:

    def test_uno_short_ben_messo_passa(self):
        assert _corto() is None

    def test_un_long_ben_messo_passa(self):
        assert _lungo() is None


class TestUnBersaglioDeveEsistere:
    """SETUP-14: senza, il 75% residuo non ha dove andare."""

    def test_senza_bersaglio_non_si_opera(self):
        regole, motivo = _corto(bersaglio=None)
        assert regole == ["PRIN-99"]
        assert "SETUP-14" in motivo and "TF_H1" in motivo


class TestIlBersaglioStaDavantiAlPrezzo:
    """PRIN-99. Nasce da un key level e col prezzo non lo confrontava nessuno.

    Il 2026-09-22 un SELL su USDCHF a 0,81891 e' partito con target 0,82029 --
    SOPRA l'ingresso. L'ha fermato MT5 con `10016`; finche' gli ordini
    partivano nudi veniva ESEGUITO, e l'audit ne contava 48 su 201.
    """

    def test_su_uno_short_il_bersaglio_sopra_e_alle_spalle(self):
        regole, motivo = _corto(bersaglio=158.900)
        assert regole == ["PRIN-99"]
        assert "non potrebbe vincere" in motivo and "SELL" in motivo

    def test_su_un_long_il_bersaglio_sotto_e_alle_spalle(self):
        regole, motivo = _lungo(bersaglio=1.1300)
        assert regole == ["PRIN-99"]
        assert "non potrebbe vincere" in motivo and "BUY" in motivo

    def test_un_bersaglio_esattamente_sull_ingresso_non_vale(self):
        """Zero guadagno non e' un bersaglio."""
        assert _corto(bersaglio=158.204) is not None


class TestLoStopStaDallAltraParte:
    """PRIN-99, lo stesso difetto sull'altro livello.

    Il 2026-09-23: `USDJPY SELL ingresso 158.204 stop 158.196`. Lo stop sotto
    l'ingresso su uno short, cioe' dalla parte del bersaglio: il prezzo lo
    tocca andando nella direzione GIUSTA. Vissuta 4 secondi.
    """

    def test_il_caso_misurato(self):
        regole, motivo = _corto(bersaglio=158.167, stop=158.196)
        assert regole == ["PRIN-99"]
        assert "sarebbe gia' toccato" in motivo

    def test_su_un_long_lo_stop_sopra_e_gia_toccato(self):
        regole, motivo = _lungo(stop=1.1400)
        assert regole == ["PRIN-99"]
        assert "sarebbe gia' toccato" in motivo

    def test_uno_stop_sull_ingresso_non_vale(self):
        assert _corto(stop=158.204) is not None


class TestIlGiocoDeveValereLaCandela:
    """SETUP-02C. Il documento non scrive una soglia, descrive la costruzione:

    *"Lo stop e' l'ombra dello sweep, quindi STRETTO; il bersaglio e' il lato
    opposto di un range di timeframe superiore, quindi LARGO. Rapporto
    misurato: da 1,85 a 3,92 R."*

    Sotto 1 quella costruzione non regge piu'. Il 2026-09-23 `AUDUSD BUY
    0.70412 stop 0.70257 target 0.70475`: 155 pip rischiati per farne 63,
    perdente anche vincendo sei volte su dieci.
    """

    def test_il_caso_audusd_misurato(self):
        regole, motivo = guardie_sui_livelli(
            0.70475, 0.70257, 0.70412, Bias.LONG, TF.H1)
        assert regole == ["SETUP-02C"]
        assert "0.41 a 1" in motivo

    def test_il_caso_eurusd_misurato(self):
        regole, motivo = guardie_sui_livelli(
            1.14029, 1.13701, 1.13897, Bias.LONG, TF.H1)
        assert regole == ["SETUP-02C"]
        assert "0.67 a 1" in motivo

    def test_esattamente_uno_a_uno_non_basta(self):
        """La soglia e' il confine del perdente per costruzione: `<` non `<=`
        lascerebbe passare l'operazione che non guadagna nulla al netto."""
        assert RAPPORTO_MINIMO == pytest.approx(1.0)
        # rischio 0.010, rendimento 0.010 -> esattamente 1,00
        assert guardie_sui_livelli(1.1489, 1.1289, 1.1389, Bias.LONG, TF.H1) is None
        # appena sotto
        assert guardie_sui_livelli(1.1488, 1.1289, 1.1389, Bias.LONG, TF.H1) is not None

    def test_uno_stop_a_distanza_zero_non_fa_dividere_per_zero(self):
        """Lo ferma il controllo sul lato, prima di arrivare al rapporto."""
        esito = guardie_sui_livelli(157.0, 158.204, 158.204, Bias.SHORT, TF.H1)
        assert esito is not None
        assert esito[0] == ["PRIN-99"]


class TestIlVersoEQuelloDelCfd:
    """`6S` e `6J` quotano il reciproco: un CRT LONG li' e' un ordine SHORT.

    L'agente riceve il verso dell'ORDINE e non conosce il CRT, quindi non puo'
    sbagliarsi. E' lo scambio che una volta ha gia' mandato gli ordini dalla
    parte opposta del mercato.
    """

    def test_gli_stessi_numeri_cambiano_esito_col_verso(self):
        numeri = dict(bersaglio=157.000, stop=158.400, prezzo_ingresso=158.204,
                      tf_crt=TF.H1)
        assert guardie_sui_livelli(verso_ordine=Bias.SHORT, **numeri) is None
        assert guardie_sui_livelli(verso_ordine=Bias.LONG, **numeri) is not None

    def test_l_agente_non_riceve_il_crt(self):
        import inspect
        from core import motore
        parametri = inspect.signature(motore.guardie_sui_livelli).parameters
        assert "crt" not in parametri and "foto" not in parametri
