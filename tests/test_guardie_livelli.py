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


class TestCalcolaLivelli:
    """Il secondo agente uscito da `valuta()`: i tre livelli di un CRT.

    Sessanta righe che stavano in mezzo a tutto il resto. Qui si provano le
    due cose che quel blocco deve garantire: che i livelli escano sulla scala
    del CFD, e che quando non si sanno leggere ci si astenga invece di
    mandare un ordine con numeri di cui non si risponde (PRIN-99, ESCL-12).
    """

    def test_restituisce_un_errore_invece_di_sollevare(self):
        """Chi chiama deve poter dichiarare l'astensione con la sua regola,
        non ricevere un'eccezione da tradurre."""
        import inspect
        from core.motore import calcola_livelli
        firma = inspect.signature(calcola_livelli)
        assert "tuple" in str(firma.return_annotation)
        corpo = inspect.getsource(calcola_livelli)
        assert "except ValueError" in corpo
        assert "raise" not in corpo

    def test_i_livelli_del_future_restano_disponibili(self):
        """`calcola_size` lavora sulla scala del FUTURE, dove la distanza e'
        gia' adimensionale: convertirla sarebbe un giro a vuoto con un
        arrotondamento in piu'. Se `stop_future` sparisse, la size verrebbe
        calcolata su una scala diversa da quella su cui e' tarata."""
        from core.motore import Livelli
        campi = set(Livelli.__dataclass_fields__)
        assert "stop_future" in campi and "bersaglio_future" in campi
        assert "stop" in campi and "bersaglio" in campi


class TestFiltroDxy:
    """Il terzo agente: SETUP-19 + RISK-05, la bias del dollaro.

    La REGOLA e' qui; l'inoltro al giudizio resta a chi chiama, perche'
    dipende dal timeframe e dal modo diagnostico e non dalla bias.
    """

    def test_restituisce_il_motivo_non_una_decisione(self):
        """Separare la regola dall'inoltro e' il punto: una regola che
        costruisce astensioni non si puo' provare senza il motore."""
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.filtro_dxy)
        assert "_non_operare" not in corpo
        assert "_giudizio_lascia_cadere" not in corpo
        assert "_apri_ogni_crt" not in corpo

    def test_usa_il_verso_del_cfd_non_quello_del_crt(self):
        """SETUP-19 e' scritta in direzioni CFD, il CRT e' rilevato sul
        future: si confrontano solo dopo DEF-33."""
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.filtro_dxy)
        assert "_verso_sul_cfd(foto, crt.direzione)" in corpo
        # E il verso passato a `strumento_eleggibile` e' quello convertito.
        assert "direzione_del_setup=verso_del_setup.value" in corpo


class TestIDivietiDiContestoSonoUnoSolo:
    """Le due strade avevano due elenchi, e non coincidevano.

    L'ordine diretto e l'ingresso armato di CRT-13 controllavano entrambi
    limiti di perdita, news, posizioni aperte e coerenza dei dati. Ma alla
    strada ARMATA mancavano `PRIN-13` (domenica) e `CTX-04` (festivita'):
    un setup armato poteva scattare di domenica o in un giorno di festivita'
    mentre lo stesso setup per via diretta non poteva.

    E il commento di quella strada dice l'opposto -- che PREC-01 mette il
    rischio sopra il setup e "un setup armato non e' un lasciapassare".

    Non erano gate morti: sull'archivio `CTX-04` ha bloccato 1.038 volte e
    `PRIN-13` 976.
    """

    def test_esiste_un_solo_elenco(self):
        import inspect
        from core import motore
        sorgente = inspect.getsource(motore)
        # I nomi delle regole compaiono una volta sola, dentro l'agente.
        agente = inspect.getsource(motore.blocchi_indipendenti)
        for regola in ('"PRIN-13"', '"CTX-04"', '"RISK-06"'):
            assert sorgente.count(regola) == 1, f"{regola} e' scritta in due posti"
            assert regola in agente

    def test_tutte_e_sei_le_regole_ci_sono(self):
        import inspect
        from core import motore
        agente = inspect.getsource(motore.blocchi_indipendenti)
        for regola in ("PRIN-13", "CTX-02", "CTX-04", "RISK-06", "PRIN-99"):
            assert f'"{regola}"' in agente, f"manca {regola}"
        assert "limiti_raggiunti" in agente, "mancano i limiti di perdita (PREC-01)"

    def test_l_agente_restituisce_anche_i_fatti_che_calcola(self):
        """`limiti`, `evento_news` e `posizioni_qui` servono al dossier del
        giudizio. Ricalcolarli fuori vorrebbe dire due verita' sullo stesso
        fatto, e una chiamata in piu' a `dentro_finestra_news` per giro."""
        from core.motore import ContestoIndipendente
        campi = set(ContestoIndipendente.__dataclass_fields__)
        assert campi == {"blocchi", "limiti", "evento_news", "posizioni_qui"}


class TestFiltriEEsclusioni:
    """L'unione di tre elenchi, e nessuno e' normativo da solo (REV-17).

    `contesto.filtri_attivi` porta la meta' di CTX-01, `setup.
    esclusioni_setup` quella di SETUP-15, e le due NON coincidono. A queste si
    aggiunge SETUP-09 quando l'ingresso e' da gap, piu' i divieti di contesto.
    """

    def test_riceve_il_modo_diagnostico_invece_di_leggerlo(self):
        """Stesso criterio di `divieti_permanenti`: una regola che legge la
        configurazione da sola non si prova nei due modi senza cambiarla
        sotto ai piedi del resto del processo."""
        import inspect
        from core import motore
        parametri = inspect.signature(motore.filtri_e_esclusioni).parameters
        assert "diagnostico" in parametri
        assert "_apri_ogni_crt" not in inspect.getsource(motore.filtri_e_esclusioni)

    def test_il_modo_diagnostico_toglie_anche_GEST_01(self):
        """Il rapporto su TP1 e' un giudizio sul valore dell'operazione, non
        una salvaguardia del conto.

        Questa riga era andata persa estraendo l'agente: senza, `GEST-01`
        tornava a bloccare col modo acceso. L'hanno presa i test.
        """
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.filtri_e_esclusioni)
        assert 'OBIEZIONI_SOPPESABILI | {"GEST-01"}' in corpo

    def test_le_morbide_cadono_dai_blocchi_E_dai_filtri(self):
        """Se restassero fra i filtri, il motivo nominerebbe una regola che
        non sta fermando niente."""
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.filtri_e_esclusioni)
        i = corpo.index("if diagnostico:")
        pezzo = corpo[i:corpo.index("motivo =", i)]
        assert "filtri = tuple(" in pezzo
        assert "blocchi = [b for b in blocchi" in pezzo

    def test_tutte_e_tre_le_famiglie_entrano_nei_blocchi(self):
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.filtri_e_esclusioni)
        for pezzo in ("ctx.filtri_attivi(", "stp.esclusioni_setup(",
                      "stp.ingresso_da_gap_ammesso(", "contesto.blocchi"):
            assert pezzo in corpo, f"manca {pezzo}"


class TestTrovaCrt:
    """La ricerca del CRT, e il perche' quando non c'e'.

    `tf_trigger` e' il timeframe di ESECUZIONE; il RANGE e' la candela di
    riferimento del timeframe alto della coppia. Prima si prendevano le ultime
    due candele di `tf_trigger` qualunque fosse: con un alert su M1 il range
    era un minuto e l'ingresso lo stesso minuto, cioe' tre candele dello
    stesso timeframe -- l'errore che REV-50 ha corretto in SETUP-01.

    Misurato il 2026-09-22 su 458 ordini: 317 da M1min e 141 da M5, **zero da
    un timeframe di range valido**.
    """

    def test_un_timeframe_senza_coppia_e_CRT_04(self):
        """`TF_1W` e' un RANGE di CRT-04, non un'esecuzione: non c'e' una
        coppia in cui faccia da timeframe basso.

        `M1min` invece una coppia ce l'ha -- e' l'esecuzione di `15m -> 1m` --
        ed e' l'errore che questo test faceva nella prima stesura.
        """
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto
        from core.motore import trova_crt
        from core.parametri import TF
        esito = trova_crt(foto(), TF.W1)
        assert esito.crt is None
        assert esito.regola == "CRT-04"
        # E un timeframe che una coppia ce l'ha non finisce qui.
        assert trova_crt(foto(), TF.MIN1).regola != "CRT-04"

    def test_senza_candela_di_riferimento_e_DEF_26(self):
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto, N2
        from core.motore import trova_crt
        from core.parametri import TF
        # H4 c'e', ma il suo range (W1) e' vuoto.
        esito = trova_crt(foto(candele_per_tf={TF.H4: [N2]}), TF.H4)
        assert esito.crt is None
        assert esito.regola == "DEF-26"

    def test_restituisce_le_barre_che_servono_a_valle(self):
        """Il CISD e la divergenza SMT si leggono su quelle: se l'agente non
        le restituisse, chi chiama dovrebbe ricalcolarle -- e ricalcolarle
        diversamente e' come nasce una seconda verita'."""
        import sys
        if "tests" not in sys.path:
            sys.path.insert(0, "tests")
        from test_motore import foto
        from core.motore import trova_crt
        from core.parametri import TF
        esito = trova_crt(foto(), TF.H4)
        assert esito.crt is not None
        assert esito.barre, "le barre di esecuzione non tornano indietro"

    def test_SETUP_00_si_dichiara_solo_se_valutata(self):
        """Con CRT-04 o DEF-26 ci si ferma prima. Dichiararla direbbe che e'
        stata valutata quando non lo e' stata, e la statistica "quante volte
        ciascuna regola ha deciso" si regge su questa distinzione."""
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.valuta)
        assert 'if ricerca.regola in (None, "SETUP-00"):' in corpo
