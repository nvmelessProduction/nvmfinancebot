"""Le due regole che mancavano fra il segnale e l'ordine.

Il 2026-09-21 il bot ha aperto le sue prime quattro operazioni sul demo. Sono
morte tutte in 5-30 secondi, e guardando i numeri il motivo era uno solo: lo
stop stava dentro il costo.

    AUDUSD+  ingresso 0.71194  stop 0.71210   8,0 spread   0,88 lotti
    XAUUSD+  ingresso 4343.64  stop 4343.40   2,0 spread   0,04 lotti
    XAUUSD+  ingresso 4343.68  stop 4343.46   1,8 spread   0,53 lotti

Non erano "stop stretti": erano stop dentro il rumore che lo spread stesso
produce. E siccome RISK-03 dimensiona sul rischio, uno stop minuscolo
produceva una size enorme -- 0,88 lotti su un conto da 1.000 EUR, cioe' ~54
volte l'equity di nozionale.
"""

import pytest

from core.parametri import COSTO_SPREAD_MASSIMO_IN_R, LEVA_MASSIMA
from core.rischio import calcola_size


class TestLoStopFuoriDalCosto:

    def test_la_soglia_e_dieci_spread(self):
        assert COSTO_SPREAD_MASSIMO_IN_R == pytest.approx(0.10)
        assert 1 / COSTO_SPREAD_MASSIMO_IN_R == pytest.approx(10.0)

    def test_sta_dalla_parte_prudente(self):
        """La misura definitiva del progetto dice che lo spread costa fra
        0,15 e 0,35 R ed e' gia' abbastanza per rendere tutto perdente."""
        assert COSTO_SPREAD_MASSIMO_IN_R < 0.15


class TestIlTettoSullaLeva:

    def _size(self, equity, prezzo, stop, valore_punto=87074.0):
        return calcola_size(
            equity=equity, strumento="EURUSD",
            chiusura_n2_future=prezzo, stop_future=stop,
            prezzo_cfd=prezzo, valore_punto=valore_punto,
            passo_broker=0.01, posizioni_aperte_per_strumento={},
        )

    def test_uno_stop_lontano_non_viene_toccato(self):
        """Con uno stop ampio il nozionale resta sotto il tetto."""
        e = self._size(equity=1000.0, prezzo=1.1000, stop=1.0900)
        assert e.lotti is not None
        nozionale = e.lotti * 87074.0 * 1.1000
        assert nozionale <= LEVA_MASSIMA * 1000.0

    def test_uno_stop_vicino_viene_ridotto(self):
        """Il caso misurato: stop a due pip, rischio sempre 1%, leva enorme."""
        e = self._size(equity=1000.0, prezzo=0.71194, stop=0.71210)
        assert e.lotti is not None
        nozionale = e.lotti * 87074.0 * 0.71194
        assert nozionale <= LEVA_MASSIMA * 1000.0 * 1.001, (
            f"{nozionale/1000.0:.0f}x l'equity")
        assert "ridotta" in e.motivo

    def test_il_motivo_dice_di_quanto_e_perche(self):
        e = self._size(equity=1000.0, prezzo=0.71194, stop=0.71210)
        assert "x l'equity" in e.motivo and "tetto" in e.motivo

    def test_il_tetto_cresce_col_conto(self):
        """E' relativo, non assoluto: e' la differenza con VOLUME_MASSIMO."""
        piccolo = self._size(equity=1000.0, prezzo=0.71194, stop=0.71210)
        grande = self._size(equity=10000.0, prezzo=0.71194, stop=0.71210)
        assert grande.lotti > piccolo.lotti

    def test_se_il_tetto_non_basta_per_un_passo_non_si_apre(self):
        """Meglio nessuna posizione che una fuori scala."""
        e = self._size(equity=1.0, prezzo=0.71194, stop=0.71210)
        assert e.lotti is None
        assert "passo del broker" in e.motivo or "zero" in e.motivo


class TestPerCheUnTp1SbagliatoUccideSubito:
    """Il meccanismo, dal lato della sentinella.

    La sentinella non ha colpe: gira ogni 5 secondi e fa cio' che le viene
    detto. Se TP1 sta dalla parte sbagliata lo trova raggiunto al primo giro,
    e da li' in poi la posizione e' gia' morta -- lo stop e' a due spread
    dall'ingresso, dentro l'oscillazione fra bid e ask.
    """

    def _posizione(self, tp1: float):
        from core.gestione import Posizione
        from core.definizioni import Bias
        from core.parametri import TF
        return Posizione(
            strumento="XAUUSD", direzione=Bias.SHORT, prezzo_ingresso=4343.64,
            tf_crt=TF.MIN5, livello_stop=4345.0, tp1=tp1, target_finale=4322.75,
        )

    def test_un_tp1_sopra_l_ingresso_e_gia_raggiunto(self):
        """Il caso vero: ticket 326841627, TP1 a 4345.505 su una SELL."""
        from core.gestione import raggiunge_tp1
        assert raggiunge_tp1(self._posizione(4345.505), 4343.70) is True

    def test_un_tp1_sotto_l_ingresso_aspetta(self):
        from core.gestione import raggiunge_tp1
        assert raggiunge_tp1(self._posizione(4340.00), 4343.70) is False

    def test_il_break_even_finisce_dentro_lo_spread(self):
        """Due spread di buffer su un oro che ne ha 0,12: 0,24 punti.

        E' il motivo per cui anche il TP1 legittimo (ticket 326844686) non
        e' sopravvissuto: il residuo muore sul primo rimbalzo.
        """
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        be = livello_break_even(4343.64, Bias.SHORT, spread=0.12)
        assert be == pytest.approx(4343.40)
        assert abs(4343.64 - be) / 0.12 == pytest.approx(2.0)


class TestLaGuardiaValeSuEntrambeLeStrade:
    """Il controllo stava solo sull'ingresso armato, e l'altro apriva uguale.

    Misurato il 2026-09-22 sulle 53 posizioni dopo il riavvio: 36 avevano
    ancora lo stop dentro i dieci spread. Tutte passate da `valuta`, che il
    controllo non ce l'aveva.
    """

    def test_uno_stop_dentro_il_costo_viene_riconosciuto(self):
        from core.motore import _spread_troppo_caro
        # Stop a due spread: costa 0,50 R.
        motivo = _spread_troppo_caro(spread=0.12, prezzo=4343.64, stop=4343.88)
        assert motivo is not None
        assert "0.50 R" in motivo and "2.0 spread" in motivo

    def test_uno_stop_largo_passa(self):
        from core.motore import _spread_troppo_caro
        assert _spread_troppo_caro(spread=0.12, prezzo=4343.64, stop=4345.64) is None

    def test_senza_spread_non_si_giudica(self):
        from core.motore import _spread_troppo_caro
        assert _spread_troppo_caro(spread=0.0, prezzo=1.1, stop=1.09) is None

    def test_rischio_nullo_lo_ferma_RISK_03_altrove(self):
        from core.motore import _spread_troppo_caro
        assert _spread_troppo_caro(spread=0.0001, prezzo=1.1, stop=1.1) is None

    def test_le_due_strade_chiamano_la_stessa_funzione(self):
        """Due copie della stessa regola finiscono per divergere."""
        import inspect
        from core import motore
        sorgente = inspect.getsource(motore)
        assert sorgente.count("_spread_troppo_caro(") >= 3   # def + due usi
        # E la soglia non e' ricopiata altrove: ogni riga che la nomina sta
        # dentro la funzione, o e' la riga che la importa.
        corpo = inspect.getsource(motore._spread_troppo_caro)
        fuori = [r.strip() for r in sorgente.splitlines()
                 if "COSTO_SPREAD_MASSIMO_IN_R" in r and r not in corpo]
        assert fuori == ["COSTO_SPREAD_MASSIMO_IN_R, MAX_POSIZIONI_PER_STRUMENTO,"], fuori


class TestIlPnlIlleggibileNonVale_Zero:
    """RISK-07/08/09 si calcolano sul P&L chiuso letto dal broker.

    `broker.pnl_chiuso` restituisce `(ok, valore, messaggio)` e in caso di
    errore il valore e' 0.0. Uno zero qui significa "nessuna perdita", quindi
    nessun limite: il conto resterebbe scoperto proprio mentre il broker non
    risponde. L'esito va guardato.
    """

    def test_l_esito_della_lettura_non_viene_scartato(self):
        """Prova sul sorgente, e lo dice: qui non c'e' un `_conto()` da
        chiamare senza una connessione a MT5 viva, e aprirne una seconda
        mentre il bot gira e' la cosa da non fare. Cio' che si puo'
        verificare e' che l'esito sia legato e controllato."""
        import inspect
        from core import fornitore_tradingview as forn
        sorgente = inspect.getsource(forn)
        assert "_, giornaliero, _ = broker.pnl_chiuso" not in sorgente
        assert "if not (ok_g and ok_s and ok_m):" in sorgente

    def test_uno_zero_verrebbe_letto_come_nessuna_perdita(self):
        """Perche' scartare l'esito e' pericoloso: e' RISK-07 che non scatta."""
        from core.rischio import limiti_raggiunti
        assert limiti_raggiunti(0.0, 1000.0, 0.0, 1000.0, 0.0, 1000.0) == ()
        # Con la perdita vera, invece, scattano.
        assert len(limiti_raggiunti(-200.0, 1000.0, -200.0, 1000.0,
                                    -200.0, 1000.0)) == 3

    def test_lo_scarto_del_server_e_misurato_ma_non_usato(self):
        """Il campanello: `_scarto_server` esiste e nessuno lo applica.

        Il server del broker e' a UTC+3 (misurato in esercizio). Le finestre
        di RISK-07/08/09 vengono calcolate in UTC e passate a MT5, che le
        legge in ora del server: sono spostate di tre ore. Questa prova non
        corregge il difetto, lo tiene visibile finche' non si decide.
        """
        import inspect
        from core import broker
        sorgente = inspect.getsource(broker)
        assert "_scarto_server" in sorgente, "l'offset e' misurato"
        # Se un giorno qualcuno lo applicasse a pnl_chiuso, questa prova va
        # aggiornata: e' il segnale che il difetto e' stato chiuso.
        corpo = inspect.getsource(broker.pnl_chiuso)
        assert "_scarto_server" not in corpo
