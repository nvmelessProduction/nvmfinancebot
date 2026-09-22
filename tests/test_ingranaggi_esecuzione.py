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
        """Meglio nessuna posizione che una fuori scala.

        Con un euro di equity anche il lotto minimo rischia migliaia di volte
        il conto, quindi lo ferma il tetto sul rischio del lotto minimo.
        """
        e = self._size(equity=1.0, prezzo=0.71194, stop=0.71210)
        assert e.lotti is None
        assert "oltre il tetto" in e.motivo


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
        assert "0.50 R" in motivo and "2.0 volte il costo" in motivo

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
        assert fuori == ["COSTO_SPREAD_MASSIMO_IN_R,"], fuori


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


class TestStopETargetArrivanoAlBroker:
    """Fino al 2026-09-22 l'ordine partiva nudo: su MT5 S/L e T/P vuote.

    Funzionava finche' il bot era vivo -- 281 stop e 102 target eseguiti
    dalla sentinella -- ma un processo morto lasciava la posizione aperta
    senza nessuna protezione. Adesso sono due reti.
    """

    def test_la_firma_accetta_stop_e_target(self):
        import inspect
        from core import broker
        p = inspect.signature(broker.invia_ordine).parameters
        assert "stop" in p and "target" in p
        assert p["stop"].default is None and p["target"].default is None

    def test_i_livelli_finiscono_nella_richiesta(self):
        import inspect
        from core import broker
        corpo = inspect.getsource(broker.invia_ordine)
        assert 'richiesta["sl"] = round(' in corpo
        assert 'richiesta["tp"] = round(' in corpo

    def test_al_broker_va_il_target_finale_non_tp1(self):
        """TP1 e' un parziale del 25%: il broker chiuderebbe tutto.

        Nel modello `Decision` il target finale si chiama `tp` e il parziale
        `tp1`: due campi distinti, e al broker va il primo.
        """
        import inspect
        import main
        corpo = inspect.getsource(main)
        assert "target=decisione.tp," in corpo
        assert "target=decisione.tp1" not in corpo
        from core.models import Decision
        assert {"tp", "tp1"} <= set(Decision.model_fields)

    def test_il_livello_viene_arrotondato_alla_cifra_del_simbolo(self):
        """MT5 rifiuta con 10016 uno stop non allineato al tick."""
        from core import broker
        assert broker._cifre_simbolo("QUALUNQUE", difetto=3) in (3, 5)
        # Senza connessione si usa il ripiego, non si solleva.
        assert isinstance(broker._cifre_simbolo("EURUSD+"), int)


class TestIlBrokerNonChiudeTuttoASuTP1:
    """Il dubbio giusto: se TP1 finisse sul broker, chiuderebbe TUTTO.

    TP1 e' un parziale del 25% (GEST-04): il broker non sa parzializzare, un
    `tp` raggiunto chiude l'intera posizione. Al broker va quindi il TARGET
    FINALE, e TP1 resta mestiere della sentinella.
    """

    def test_il_tp_del_broker_e_il_target_finale(self):
        import inspect
        import main
        corpo = inspect.getsource(main)
        assert "target=decisione.tp," in corpo
        assert "target=decisione.tp1" not in corpo

    def test_la_traduzione_tiene_separati_i_due_campi(self):
        """`strategy` scrive `tp` dal target finale e `tp1` dal parziale.

        E' il punto dove i due si potrebbero confondere: se `tp` prendesse
        `decisione.tp1`, il broker chiuderebbe tutta la posizione al primo
        obiettivo invece di lasciarne in vita il 75%.
        """
        import inspect
        from core import strategy
        corpo = inspect.getsource(strategy)
        assert "tp=decisione.target_finale," in corpo
        assert "tp1=decisione.tp1," in corpo


class TestLoStopNuovoArrivaAlBroker:
    """Dopo il parziale lo stop va a pareggio: anche sul broker.

    Prima finiva solo in archivio. Sul log: 58 parziali e 91 spostamenti di
    SETUP-17 in cui il broker e' rimasto allo stop di partenza -- cioe' la
    rete che sopravvive alla morte del bot era quella sbagliata.
    """

    def test_la_funzione_esiste_e_usa_SLTP(self):
        import inspect
        from core import broker
        assert hasattr(broker, "modifica_livelli")
        assert "TRADE_ACTION_SLTP" in inspect.getsource(broker.modifica_livelli)

    def test_non_tocca_il_conto_durante_le_prove(self):
        from core import broker
        esito = broker.modifica_livelli(12345, stop=1.1)
        assert esito.ok is False
        assert "prova" in esito.messaggio

    def test_senza_livelli_non_manda_niente(self, monkeypatch):
        from core import ambiente, broker
        monkeypatch.setattr(ambiente, "in_prova", lambda: False)
        monkeypatch.setattr(broker, "_assicura_connessione", lambda: (True, "ok"))
        esito = broker.modifica_livelli(12345)
        assert esito.ok is True and "niente da modificare" in esito.messaggio

    def test_la_sentinella_e_il_server_la_chiamano(self):
        import inspect
        import main
        from core import sentinella
        assert "modifica_livelli(" in inspect.getsource(sentinella)
        assert inspect.getsource(main).count("modifica_livelli(") >= 2


class TestIlBersaglioDeveStareDavanti:
    """Il broker ha fermato cio' che il motore lasciava passare.

    Il 2026-09-22 alle 13:09 e' partito un SELL su USDCHF a 0,81891 con
    target a 0,82029 -- sopra l'ingresso. MT5 ha risposto `retcode 10016
    (Invalid stops)`. Finche' gli ordini partivano nudi quello stesso ordine
    veniva ESEGUITO: l'audit ne contava 48 su 201.

    Il bersaglio nasce da un key level, cioe' da un livello della struttura,
    e col prezzo di ingresso non lo confrontava nessuno: lo stesso difetto
    che aveva TP1.
    """

    @pytest.fixture
    def diagnostico(self, monkeypatch):
        """Col modo diagnostico acceso, che e' quando questo controllo conta.

        A filtri accesi ci arriva prima `GEST-01`: il rapporto su un target
        alle spalle non esiste, quindi blocca lui. Ma `GEST-01` e'
        soppesabile e il modo diagnostico lo spegne -- ed e' esattamente la
        configurazione in cui, il 2026-09-22, l'ordine incoerente e' arrivato
        al broker.
        """
        from core.config import impostazioni
        monkeypatch.setattr(impostazioni(), "APRI_OGNI_CRT", True, raising=False)
        yield

    def _decisione(self, chiusura_n2: float):
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto, m, TF, N1, cand
        # Il bersaglio di uno short qui e' il key level a 100. Se `N2`
        # richiude SOTTO quel livello, il prezzo l'ha gia' passato e il
        # target resta alle spalle.
        n2 = cand(massimo=111, minimo=94, chiusura=chiusura_n2, apertura=110)
        return m.valuta(
            foto(candele_per_tf={TF.H4: [N1, n2]}, prezzo_cfd=chiusura_n2), TF.H4)

    def test_un_bersaglio_alle_spalle_ferma_l_ordine(self, diagnostico):
        d = self._decisione(99.0)
        assert d.azione == "NONE"
        assert "PRIN-99" in d.regole_che_bloccano
        assert "dalla parte sbagliata" in d.motivo
        assert "non potrebbe vincere" in d.motivo

    def test_non_e_un_muro_generico(self, diagnostico):
        """Col target davanti al prezzo l'ordine passa."""
        d = self._decisione(101.0)
        assert d.azione == "SELL", d.motivo
        assert d.target_finale is not None and d.target_finale < 101.0

    def test_il_modo_diagnostico_non_lo_puo_spegnere(self):
        """PRIN-99 non e' soppesabile: non e' sfortuna, e' dato incoerente."""
        from core.motore import OBIEZIONI_SOPPESABILI
        assert "PRIN-99" not in OBIEZIONI_SOPPESABILI

    def test_il_verso_e_quello_del_CFD_non_del_future(self):
        """Su USDCHF e USDJPY il future quota il reciproco.

        Confrontare col verso del future farebbe risultare "dalla parte
        sbagliata" esattamente i bersagli giusti -- ed e' lo scambio che una
        volta ha gia' mandato gli ordini dalla parte opposta del mercato.
        """
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.valuta)
        assert "verso_ordine = _verso_sul_cfd(" in corpo
        # Il confronto usa il verso dell'ordine, non `crt.direzione`.
        pezzo = corpo.split("verso_ordine = _verso_sul_cfd(")[1][:400]
        assert "verso_ordine is Bias.LONG" in pezzo


class TestSenzaSpreadNonSiApre:
    """Uno spread a zero non e' "gratis": e' un costo che non si conosce.

    `RISK-03` non puo' misurare se lo stop stia dentro il costo, e infatti il
    2026-09-22 e' passato un SELL con lo stop a 0,9 spread. Succedeva spesso:
    8 posizioni su 66 avevano `spread_ingresso` a zero.

    L'astensione sta dove il dato nasce -- nel fornitore, insieme alle altre
    letture mancanti -- non dentro la regola, che resta una funzione pura sul
    costo e si puo' provare senza un broker.
    """

    def test_la_regola_resta_pura_e_non_giudica_senza_spread(self):
        from core.motore import _spread_troppo_caro
        assert _spread_troppo_caro(spread=0.0, prezzo=1.1, stop=1.0999) is None

    def test_uno_spread_a_zero_NON_fa_astenere(self):
        """Su un conto RAW `bid == ask` e' la norma, non un guasto.

        Qui c'era un'astensione, ed era sbagliata: misurato il 2026-09-22,
        scattava 64 volte in mezz'ora su EURUSD e USDCHF e spegneva due
        strumenti su sei. Il costo su quei conti sta nella commissione.
        """
        import inspect
        from core import fornitore_tradingview as forn
        corpo = inspect.getsource(forn)
        assert 'if tick["ask"] - tick["bid"] <= 0:' not in corpo
        assert "costo_commissione=" in corpo

    def test_la_commissione_entra_nel_costo_del_giro(self):
        from core.motore import _costo_del_giro
        # Conto RAW: spread zero, ma il giro costa lo stesso.
        assert _costo_del_giro(0.0, 0.00005) == pytest.approx(0.00005)
        # Conto standard: spread pieno, nessuna commissione.
        assert _costo_del_giro(0.00008, 0.0) == pytest.approx(0.00008)
        # E si sommano, perche' si pagano tutti e due.
        assert _costo_del_giro(0.00005, 0.00005) == pytest.approx(0.00010)


class TestIlPareggioNonPuoStareOltreIlPrezzo:
    """`livello_break_even` e' `ingresso -/+ due spread`, e non guarda il prezzo.

    Se a TP1 il prezzo si e' mosso MENO di due spread, il pareggio cade dalla
    parte gia' superata: e' uno stop gia' toccato. Misurato il 2026-09-22 sul
    ticket 327995073, AUDUSD SELL -- prezzo 0,71113, pareggio 0,71107, cioe'
    sotto. MT5 rifiutava con `10016`, l'archivio se lo scriveva lo stesso, e
    al giro dopo il residuo veniva chiuso. Nove volte in un'ora e mezza.
    """

    def test_il_caso_misurato(self):
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        # Ingresso 0,71127, spread 1 pip: il pareggio finisce a 0,71107.
        be = livello_break_even(0.71127, Bias.SHORT, spread=0.0001)
        assert be == pytest.approx(0.71107)
        prezzo_a_tp1 = 0.71113
        assert be < prezzo_a_tp1, "per una SELL lo stop finisce SOTTO il prezzo"

    def test_con_abbastanza_movimento_il_pareggio_e_valido(self):
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        be = livello_break_even(0.71127, Bias.SHORT, spread=0.0001)
        prezzo_a_tp1 = 0.71000          # sceso ben oltre i due spread
        assert be > prezzo_a_tp1, "qui lo stop sta sopra il prezzo, come deve"

    def test_la_sentinella_confronta_col_prezzo(self):
        import inspect
        from core import sentinella
        corpo = inspect.getsource(sentinella)
        assert "ancora_davanti" in corpo
        assert "lo stop resta a" in corpo
        # E il confronto usa il prezzo di USCITA, non il bid o l'ask a caso:
        # una posizione lunga si chiude in bid, una corta in ask.
        assert "prezzo_di_uscita(direzione, tick" in corpo


class TestIlPareggioRecuperaLeCommissioni:
    """GEST-04 vuole un pareggio REALE, cioe' al netto dei costi.

    PA-46 aveva risolto la commissione moltiplicando lo spread per due, e il
    documento di decisione lo ammette: *"il fattore 2 e' mio"*. Nel codice la
    commissione non entrava in nessun calcolo.

    Misurato il 2026-09-22 su 17 posizioni e 8,06 lotti: il saldo e' sceso di
    47,81 EUR mentre il movimento di prezzo ne spiegava 15,11. Gli altri
    32,70 erano costi -- 4,06 EUR per lotto, piu' del doppio della perdita
    sul prezzo.
    """

    def test_senza_costi_si_comporta_come_prima(self):
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        assert livello_break_even(1.1000, Bias.LONG, spread=0.0001) == pytest.approx(1.1002)

    def test_il_costo_alza_il_buffer_quando_lo_spread_non_basta(self):
        """USDJPY: spread piccolo in proporzione alla commissione."""
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        # Due spread valgono 0,004; il costo da recuperare e' 0,010.
        be = livello_break_even(157.400, Bias.LONG, spread=0.002, costo_in_prezzo=0.010)
        assert be == pytest.approx(157.410), "vince il costo, non lo spread"

    def test_lo_spread_vince_quando_e_lui_il_piu_grande(self):
        """Oro: due spread coprono la commissione e avanzano."""
        from core.gestione import livello_break_even
        from core.definizioni import Bias
        be = livello_break_even(4330.0, Bias.SHORT, spread=0.12, costo_in_prezzo=0.05)
        assert be == pytest.approx(4329.76), "due spread, che qui bastano"

    def test_il_costo_si_legge_dal_broker_non_si_stima(self):
        import inspect
        from core import broker, sentinella
        assert hasattr(broker, "costi_posizione")
        corpo = inspect.getsource(broker.costi_posizione)
        assert "history_deals_get(position=" in corpo
        assert "commission" in corpo and "swap" in corpo
        # E la sentinella lo converte in distanza di prezzo per QUELLA size.
        s = inspect.getsource(sentinella)
        assert "costi / (valore_punto * volume_attuale)" in s

    def test_se_il_broker_tace_non_si_peggiora(self):
        """Senza il dato si resta al solo multiplo dello spread."""
        import inspect
        from core import sentinella
        s = inspect.getsource(sentinella)
        assert "costo_in_prezzo = 0.0" in s
        assert "il pareggio copre il solo" in s


class TestISottoSogliaNonHaLimitiDiPerdita:
    """Sotto una certa equity i tre limiti non si applicano. Nessuno dei tre.

    I limiti sono percentuali e `RISK-01` rischia l'1% per operazione: il
    giornaliero al 3% scatta sempre dopo TRE operazioni perse, a cento euro
    come a cinquemila. Su un conto di prova piccolo quel freno si tira nella
    prima ora -- misurato il 2026-09-22: 287 decisioni fermate da RISK-07 --
    e non protegge niente che valga la pena proteggere.
    """

    PERDITA = dict(pnl_giornaliero=-50.0, equity_inizio_giornata=100.0,
                   pnl_settimanale=-50.0, equity_inizio_settimana=100.0,
                   pnl_mensile=-50.0, equity_inizio_mese=100.0)

    def test_sotto_soglia_nessun_limite(self):
        from core.rischio import limiti_raggiunti
        assert limiti_raggiunti(**self.PERDITA, equity_corrente=100.0) == ()

    def test_sopra_soglia_scattano_tutti_e_tre(self):
        from core.rischio import limiti_raggiunti
        regole = {l.regola for l in limiti_raggiunti(**self.PERDITA, equity_corrente=500.0)}
        assert regole == {"RISK-07", "RISK-08", "RISK-09"}

    def test_esattamente_alla_soglia_sono_attivi(self):
        """La soglia e' il punto in cui si accendono, non quello dopo."""
        from core.rischio import limiti_raggiunti
        from core.parametri import LIMITI_PERDITA_SOPRA_EQUITY
        assert limiti_raggiunti(**self.PERDITA,
                                equity_corrente=LIMITI_PERDITA_SOPRA_EQUITY)

    def test_senza_equity_si_comportano_come_prima(self):
        """Chi non passa l'equity ottiene il comportamento prudente."""
        from core.rischio import limiti_raggiunti
        assert len(limiti_raggiunti(**self.PERDITA)) == 3

    def test_il_motore_passa_l_equity_a_entrambe_le_strade(self):
        import inspect
        from core import motore
        assert inspect.getsource(motore).count("equity_corrente=foto.equity") == 2


class TestIlLottoMinimoSottoSoglia:
    """Su un conto piccolo la size esatta arrotonda a zero e non si opera.

    `RISK-03` arrotonda per difetto, e a cento euro 0,005742 lotti diventano
    niente. Non e' prudenza: e' il pezzo piu' piccolo in vendita che e' piu'
    grosso della fetta che si voleva comprare. Sotto la soglia dei limiti di
    perdita si compra il minimo lo stesso, entro un tetto sul rischio.
    """

    def _size(self, equity, prezzo, stop, vp):
        from core.rischio import calcola_size
        return calcola_size(equity=equity, strumento="EURUSD",
                            chiusura_n2_future=prezzo, stop_future=stop,
                            prezzo_cfd=prezzo, valore_punto=vp,
                            passo_broker=0.01, posizioni_aperte_per_strumento={})

    def test_sotto_soglia_si_compra_il_minimo(self):
        e = self._size(100.0, 1.1450, 1.1470, 87074.0)
        assert e.lotti == 0.01
        assert "lotto minimo" in e.motivo
        # E il rischio VERO viene detto, non nascosto.
        assert e.rischio_percentuale > 0.01, "e' salito sopra l'1%"
        assert "1.74%" in e.motivo

    def test_uno_stop_troppo_largo_resta_rifiutato(self):
        """Il tetto e' l'unico freno che resta sotto i 500 euro."""
        from core.parametri import RISCHIO_MASSIMO_LOTTO_MINIMO
        e = self._size(100.0, 4330.0, 4360.0, 87.0)     # oro, stop 30 punti
        assert e.lotti is None
        assert "oltre il tetto" in e.motivo
        assert RISCHIO_MASSIMO_LOTTO_MINIMO == pytest.approx(0.05)

    def test_sopra_soglia_niente_e_cambiato(self):
        """A conto grande la size si calcola come sempre, per difetto."""
        e = self._size(1000.0, 1.1450, 1.1470, 87074.0)
        assert e.lotti == 0.05
        assert e.motivo == "size calcolata"

    def test_il_rischio_dichiarato_e_quello_vero(self):
        """Non si dichiara l'1% mentre se ne rischia il doppio."""
        e = self._size(100.0, 1.1450, 1.1470, 87074.0)
        atteso = 0.01 * (1.1470 - 1.1450) / 1.1450 * 1.1450 * 87074.0 / 100.0
        assert e.rischio_percentuale == pytest.approx(atteso, rel=1e-6)


class TestIlRangeStaSuUnTimeframeDiRange:
    """CRT-04: il CRT e' una COPPIA -- range sull'alto, ingresso sul basso.

    `valuta` prendeva le ultime due candele di `tf_trigger` qualunque esso
    fosse. Con un alert su `M1` il range era un minuto e l'ingresso lo stesso
    minuto: tre candele dello stesso timeframe, cioe' l'errore che REV-50 ha
    corretto in SETUP-01 -- "che e' un'altra strategia".

    Misurato il 2026-09-22 su 458 ordini: 317 da `M1min`, 141 da `M5`, ZERO
    da un timeframe di range valido. Il motivo e' meccanico: sui timeframe di
    range `INGRESSO_ROMEO` fa armare il setup e l'ordine parte dopo; su `M1`
    e `M5` non si puo' armare, quindi si cadeva dritti sull'ordine a mercato.
    """

    def test_i_timeframe_di_solo_ingresso_non_fanno_range(self):
        from core.parametri import COPPIE_CRT, TF
        solo_ingresso = set(COPPIE_CRT.values()) - set(COPPIE_CRT)
        assert solo_ingresso == {TF.MIN1, TF.MIN5}

    def test_su_M1_non_si_cerca_un_CRT_nuovo(self):
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto, m, TF
        d = m.valuta(foto(), TF.MIN1)
        assert d.azione == "NONE"
        assert "CRT-04" in d.regole_che_bloccano
        assert "solo INGRESSO" in d.motivo

    def test_su_M5_nemmeno(self):
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto, m, TF
        assert "CRT-04" in m.valuta(foto(), TF.MIN5).regole_che_bloccano

    def test_sui_timeframe_di_range_si_opera_come_prima(self):
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto, m, TF
        from core.parametri import COPPIE_CRT
        assert TF.H4 in COPPIE_CRT
        assert "CRT-04" not in m.valuta(foto(), TF.H4).regole_che_bloccano

    def test_quegli_alert_servono_all_altra_strada(self):
        """Non si buttano: sono il secondo tempo di CRT-13."""
        import inspect
        from core import strategy
        corpo = inspect.getsource(strategy)
        assert "valuta_ingresso_armato(fotografia, tf_trigger)" in corpo
