"""Ogni conferma di Romeo si calcola, si prova e si pesa da sola.

Fase 0.5 del piano, e il requisito diretto della Fase 2.

Le otto conferme stavano dentro `conferme_di_romeo`, 112 righe in un blocco
unico. Cosi' non se ne poteva misurare una sola: l'unica cosa calcolabile era
il loro AND -- che infatti, con tutte accese, su 18 CRT ne blocca 18 e fa
tacere il bot del tutto. Non si puo' pesare quello che non si puo' separare.

Questo file tiene fermo il taglio. Se qualcuno le rimette in un blocco, o se
il dispacciatore smette di coincidere con le funzioni che chiama, qui si
rompe.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core import setup as stp
from core.definizioni import Bias, Candela
from core.parametri import TF

LE_OTTO = ("CRT-06", "CRT-10", "CRT-11", "CRT-12",
           "CRT-15", "CRT-17", "CRT-18", "CRT-20")


def cand(massimo, minimo, chiusura, apertura, ore=0):
    return Candela(
        datetime(2026, 1, 1, ore, tzinfo=timezone.utc),
        apertura, massimo, minimo, chiusura)


N1 = cand(massimo=110, minimo=100, chiusura=109, apertura=101)
N2 = cand(massimo=112, minimo=99, chiusura=104, apertura=110, ore=4)


class TestEsistonoTuttEOtto:

    @pytest.mark.parametrize("nome", [
        "crt06_allineamento", "crt10_double_purge", "crt11_cisd", "crt12_smt",
        "crt15_finestra_ny", "crt17_meta_range", "crt18_meta_ombra",
        "crt20_peso_ombre",
    ])
    def test_ognuna_e_una_funzione_sua(self, nome):
        assert callable(getattr(stp, nome))

    def test_nessuna_riceve_la_fotografia(self):
        """Una conferma che vede tutto non e' separabile: tornerebbe a
        dipendere dal resto e la Fase 2 non potrebbe pesarla da sola."""
        import inspect
        for nome in ("crt06_allineamento", "crt10_double_purge", "crt11_cisd",
                     "crt12_smt", "crt15_finestra_ny", "crt17_meta_range",
                     "crt18_meta_ombra", "crt20_peso_ombre"):
            parametri = inspect.signature(getattr(stp, nome)).parameters
            assert "foto" not in parametri, nome
            assert "fotografia" not in parametri, nome


class TestOgnunaRispondeDaSola:

    def test_il_peso_delle_ombre(self):
        assert stp.crt20_peso_ombre(N2, peso_minimo=0.0) is True
        assert stp.crt20_peso_ombre(N2, peso_minimo=1.01) is False

    def test_senza_candele_di_ingresso_il_cisd_tace(self):
        assert stp.crt11_cisd([], Bias.SHORT) is None

    def test_senza_compagne_la_smt_tace(self):
        assert stp.crt12_smt("EURUSD", [N1], None, Bias.SHORT) is None
        assert stp.crt12_smt("EURUSD", None, {"GBPUSD": [N1]}, Bias.SHORT) is None

    def test_senza_double_purge_la_regola_tace(self):
        """Non e' un no: e' "non ho nulla da dire". Trasformarlo in False
        spegnerebbe il bot senza dirlo."""
        piatta = cand(massimo=105, minimo=104, chiusura=104.5, apertura=104.5)
        assert stp.crt10_double_purge(N1, [piatta], Bias.SHORT) is None
        assert stp.crt10_double_purge(N1, [], Bias.SHORT) is None

    def test_il_double_purge_si_cerca_barra_per_barra(self):
        """Le fonti: *una singola candela spazza sopra E sotto il range, e per
        essere valida chiude dentro entrambi gli estremi*.

        Fino al 24/09 la regola riceveva la candela SINTETICA, che impacchetta
        un lato solo: su 226 decisioni ha risposto `None` 226 volte.
        """
        # N1 va da 100 a 110. Una barra che spazza entrambi e richiude dentro.
        doppia = cand(massimo=112, minimo=98, chiusura=104, apertura=106)
        innocua = cand(massimo=105, minimo=104, chiusura=104.5, apertura=104.5)
        assert stp.crt10_double_purge(N1, [innocua, doppia], Bias.SHORT) is not None

    def test_senza_altri_timeframe_l_allineamento_tace(self):
        assert stp.crt06_allineamento(None, TF.H4, Bias.SHORT) is None
        assert stp.crt06_allineamento({}, TF.H4, Bias.SHORT) is None

    def test_l_allineamento_ignora_il_proprio_timeframe(self):
        class FintoCrt:
            def __init__(self, d): self.direzione = d
        per_tf = {TF.H4: FintoCrt(Bias.LONG), TF.D1: FintoCrt(Bias.SHORT)}
        # Il CRT su H4 e' il proprio: conta solo quello su D1.
        assert stp.crt06_allineamento(per_tf, TF.H4, Bias.SHORT) is True
        assert stp.crt06_allineamento(per_tf, TF.H4, Bias.LONG) is False

    def test_la_meta_dell_ombra_usa_la_barra_che_ha_spazzato(self):
        """L'ombra e' quella VERA della barra piu' estrema della fase.

        Con la candela sintetica l'ombra e' enorme per costruzione e la
        chiusura ci sta sempre dalla parte giusta: 226 `True` su 226.
        """
        assert stp.crt18_meta_ombra([], Bias.SHORT) is None
        # La barra che spazza: ombra alta da 101 a 120, punto medio 110,5.
        spazza = cand(massimo=120, minimo=99, chiusura=100, apertura=101)
        # Da sola non basta: il livello esiste ma nessuno l'ha messo alla prova.
        assert stp.crt18_meta_ombra([spazza], Bias.SHORT) is None
        # La barra dopo chiude sotto il punto medio: tiene.
        sotto = cand(massimo=108, minimo=99, chiusura=103, apertura=105)
        assert stp.crt18_meta_ombra([spazza, sotto], Bias.SHORT) is True
        # La barra dopo chiude sopra: lo attraversa.
        sopra = cand(massimo=118, minimo=105, chiusura=115, apertura=106)
        assert stp.crt18_meta_ombra([spazza, sopra], Bias.SHORT) is False

    def test_la_vecchia_versione_era_una_tautologia(self):
        """`chiusura <= meta_ombra` non puo' che essere vero: il punto medio
        sta fra il corpo e l'estremo, e la chiusura non supera mai il corpo."""
        from core.definizioni import meta_ombra
        for c in (cand(massimo=120, minimo=99, chiusura=100, apertura=101),
                  cand(massimo=120, minimo=99, chiusura=119, apertura=101),
                  cand(massimo=111, minimo=108, chiusura=110, apertura=109)):
            assert c.chiusura <= meta_ombra(c, superiore=True)


class TestIlDispacciatoreNonAggiungeNulla:
    """`conferme_di_romeo` raccoglie e basta: la regola vive nelle funzioni.

    E' la proprieta' su cui la Fase 2 si regge. Se il dispacciatore calcolasse
    qualcosa per conto suo, pesare le funzioni una per una darebbe numeri
    diversi da quelli che il bot usa davvero.
    """

    def test_il_responso_coincide_con_le_funzioni_chiamate_a_mano(self):
        istante = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)
        _, _, responso = stp.conferme_di_romeo(
            N1, N2, [], Bias.SHORT, istante, TF.H4)
        a_mano = {
            "CRT-20": stp.crt20_peso_ombre(N2),
            "CRT-11": stp.crt11_cisd([], Bias.SHORT),
            "CRT-12": stp.crt12_smt("", None, None, Bias.SHORT),
            "CRT-10": stp.crt10_double_purge(N1, (), Bias.SHORT),
            "CRT-15": stp.crt15_finestra_ny(istante, TF.H4),
            "CRT-17": stp.crt17_meta_range(N1, [], Bias.SHORT),
            "CRT-18": stp.crt18_meta_ombra((), Bias.SHORT),
            "CRT-06": stp.crt06_allineamento(None, TF.H4, Bias.SHORT),
        }
        assert responso == a_mano

    def test_il_responso_e_sempre_completo(self):
        """Anche per le conferme spente: e' il quadro su cui si decide quali
        valga la pena pesare."""
        _, _, responso = stp.conferme_di_romeo(
            N1, N2, [], Bias.SHORT,
            datetime(2026, 1, 1, 14, tzinfo=timezone.utc), TF.H4)
        assert set(responso) == set(LE_OTTO)

    def test_none_non_blocca_mai(self):
        """Trasformare "non lo so" in "no" spegnerebbe il bot senza dirlo."""
        _, blocchi, responso = stp.conferme_di_romeo(
            N1, N2, [], Bias.SHORT,
            datetime(2026, 1, 1, 14, tzinfo=timezone.utc), TF.H4)
        muti = {k for k, v in responso.items() if v is None}
        assert not (muti & set(blocchi))


class TestLeConfermeSiValutanoSuOgniCoppia:
    """Il guasto piu' silenzioso trovato finora, e non dava errori.

    La riscrittura del CRT secondo SETUP-02 ha reso `tf_trigger` il timeframe
    di ESECUZIONE. Le conferme pero' restavano legate a
    `COPPIE_CRT.get(tf_trigger)`, cioe' un gradino PIU' SOTTO -- e per `M5` e
    `M1min`, che non sono chiavi di `COPPIE_CRT` perche' le chiavi sono i
    range, quella lettura dava `None` e il blocco veniva saltato in silenzio.

    Risultato: le otto conferme non venivano valutate proprio sulle coppie su
    cui il bot opera. Nessun errore, nessun avviso: il responso restava vuoto
    e basta. Si e' visto solo dopo aver iniziato a salvarlo in archivio --
    zero decisioni con le conferme registrate su un'intera giornata.
    """

    def test_ogni_timeframe_di_esecuzione_produce_un_responso(self):
        """Per ognuna delle sei coppie di CRT-04, non solo per quelle alte."""
        from core.parametri import COPPIE_CRT
        for tf_range, tf_esecuzione in COPPIE_CRT.items():
            _, _, responso = stp.conferme_di_romeo(
                N1, N2, [N2], Bias.SHORT,
                datetime(2026, 1, 1, 14, tzinfo=timezone.utc), tf_range)
            assert set(responso) == set(LE_OTTO), (
                f"responso incompleto sulla coppia {tf_range.value} -> "
                f"{tf_esecuzione.value}")

    def test_il_motore_non_lega_le_conferme_al_timeframe_sotto(self):
        """`tf_ingresso` serve all'ARMAMENTO di CRT-13, non alle conferme.

        Sono due timeframe diversi: le conferme si leggono sull'esecuzione,
        il ritorno nell'FVG si aspetta un gradino sotto. Confonderli e' il
        guasto descritto qui sopra -- e rifarlo al contrario sposterebbe
        l'armamento, che e' l'errore commesso mentre lo si correggeva.
        """
        import inspect
        from core import motore
        # La chiamata vive nell'agente: riceve le barre di esecuzione e non
        # sa nulla del timeframe dell'armamento.
        agente = inspect.getsource(motore.interroga_conferme)
        assert "tf_ingresso" not in agente, (
            "le conferme sono tornate a dipendere dal timeframe dell'armamento")
        assert "candele_ingresso=basse[-12:]" in agente, (
            "vanno lette sulle barre di esecuzione")
        parametri = inspect.signature(motore.interroga_conferme).parameters
        assert "tf_ingresso" not in parametri and "tf_trigger" not in parametri
        # E l'armamento continua a usare il timeframe sotto.
        assert "tf_ingresso = COPPIE_CRT.get(tf_trigger)" in inspect.getsource(
            motore.valuta)

    def test_un_cisd_che_non_si_puo_cercare_non_e_un_cisd_che_manca(self):
        """`False` su CRT-11 fa ARMARE il setup; `None` lo lascia proseguire.

        Con una candela sola il CISD non e' cercabile, e rispondere `False`
        cambiava il comportamento del bot su un dato che non c'era.
        """
        assert stp.crt11_cisd([N2], Bias.SHORT) is None
        assert stp.crt11_cisd([], Bias.SHORT) is None


class TestCrt11RilevaIlCisdAvvenuto:
    """Non "esiste una serie da rompere": "e' stata rotta".

    Le fonti: il CISD e' la chiusura oltre l'apertura della precedente
    consegna -- apertura/chiusura, e stampa prima dell'MSS che rompe uno
    swing su massimi e minimi.

    Fino al 24/09 la conferma faceva `cisd(...) is not None`, cioe' una
    domanda diversa e quasi sempre vera: bastava una candela contraria in
    coda. Il ramo armato lo faceva gia' giusto (`ingresso_ltf.controlla`
    verifica `ultima.chiusura > candidato`): due implementazioni della stessa
    regola che rispondevano a due domande.
    """

    def _serie(self, chiusura_finale):
        """Due candele ribassiste (consegna al ribasso) e una che le rompe."""
        return [
            cand(massimo=110, minimo=104, chiusura=105, apertura=109),
            cand(massimo=106, minimo=101, chiusura=102, apertura=105),
            cand(massimo=112, minimo=101, chiusura=chiusura_finale, apertura=102),
        ]

    def test_rotto_verso_l_alto_e_un_cisd(self):
        """Il livello e' l'apertura della PRIMA contraria: 109."""
        assert stp.crt11_cisd(self._serie(110), Bias.LONG) is True

    def test_non_rotto_non_e_un_cisd(self):
        """La serie c'e' ma nessuno l'ha superata: e' `False`, non `True`."""
        assert stp.crt11_cisd(self._serie(106), Bias.LONG) is False

    def test_senza_serie_contraria_non_c_e_nulla_da_rompere(self):
        salgono = [cand(massimo=110, minimo=100, chiusura=109, apertura=101),
                   cand(massimo=112, minimo=108, chiusura=111, apertura=109)]
        assert stp.crt11_cisd(salgono, Bias.LONG) is None

    def test_con_una_candela_sola_non_si_puo_dire(self):
        assert stp.crt11_cisd([cand(110, 100, 105, 109)], Bias.LONG) is None
        assert stp.crt11_cisd([], Bias.LONG) is None

    def test_le_due_strade_fanno_la_stessa_domanda(self):
        """Il ramo armato e la conferma devono chiedere la stessa cosa."""
        import inspect
        from core import ingresso_ltf
        armato = inspect.getsource(ingresso_ltf.controlla)
        conferma = inspect.getsource(stp.crt11_cisd)
        for corpo in (armato, conferma):
            assert "cisd(" in corpo
            assert "chiusura >" in corpo or "chiusura <" in corpo, (
                "una delle due non verifica la ROTTURA")
