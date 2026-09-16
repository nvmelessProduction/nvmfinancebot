"""Le regole di Romeo che mancavano, collaudate una per una.

`docs/BIBBIA-CRT.md` elencava 6 punti ASSENTI e 2 CONTRARI. Questo file e' il
collaudo di quello che li chiude. Ogni classe cita la regola per numero, e
dove la regola contraddice un documento del bot la contraddizione e' scritta
nel test invece che nascosta.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import contesto as ctx
from core import definizioni as d
from core import setup as stp
from core.definizioni import Bias, Candela
from core.parametri import COPPIE_CRT, COPPIE_CRT_FUORI_DEF01, TF, correlazione_positiva

O = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)


def c(massimo: float, minimo: float, chiusura: float, apertura: float, i: int = 0) -> Candela:
    return Candela(O + timedelta(hours=i), apertura, massimo, minimo, chiusura)


def salita(quante: int, da: float = 100.0, passo: float = 1.0) -> list[Candela]:
    """Una serie che sale regolarmente: l'ultima fa sempre il nuovo massimo."""
    return [
        c(massimo=da + i * passo + 1, minimo=da + i * passo - 1,
          chiusura=da + i * passo, apertura=da + i * passo, i=i)
        for i in range(quante)
    ]


# ===========================================================================
# CRT-12 — divergenza SMT
# ===========================================================================
class TestDivergenzaSmt:
    """Le fonti la dichiarano una delle tre confluenze **non negoziabili**.

    Era la lacuna piu' grave della bibbia: dichiarata indispensabile, mai
    scritta, e la piu' facile da misurare — sei strumenti correlati sono gia'
    in archivio.
    """

    def test_correlazione_dal_segno_degli_strumenti(self) -> None:
        """Non una seconda tabella: la stessa proprieta' che usa DEF-33."""
        assert correlazione_positiva("EURUSD", "GBPUSD") is True
        assert correlazione_positiva("USDJPY", "USDCHF") is True
        assert correlazione_positiva("EURUSD", "USDCHF") is False

    def test_divergenza_su_coppia_positiva(self) -> None:
        """EURUSD fa un nuovo massimo, GBPUSD no: divergenza."""
        piatta = [c(massimo=101, minimo=99, chiusura=100, apertura=100, i=i) for i in range(25)]
        assert d.divergenza_smt(
            "EURUSD", salita(25), piatta, "GBPUSD", Bias.LONG
        ) is True

    def test_nessuna_divergenza_se_vanno_insieme(self) -> None:
        assert d.divergenza_smt(
            "EURUSD", salita(25), salita(25), "GBPUSD", Bias.LONG
        ) is False

    def test_su_coppia_negativa_si_cerca_l_estremo_opposto(self) -> None:
        """EURUSD nuovo massimo; la controparte su USDCHF e' un nuovo MINIMO.

        Se USDCHF **scende** insieme, non c'e' divergenza. Sbagliare questo
        segno non produce un errore: produce un segnale che dice il contrario,
        su meta' delle coppie.
        """
        discesa = [
            c(massimo=101 - i, minimo=99 - i, chiusura=100 - i, apertura=100 - i, i=i)
            for i in range(25)
        ]
        assert d.divergenza_smt(
            "EURUSD", salita(25), discesa, "USDCHF", Bias.LONG
        ) is False

        piatta = [c(massimo=101, minimo=99, chiusura=100, apertura=100, i=i) for i in range(25)]
        assert d.divergenza_smt(
            "EURUSD", salita(25), piatta, "USDCHF", Bias.LONG
        ) is True

    def test_senza_nuovo_estremo_non_c_e_divergenza(self) -> None:
        piatta = [c(massimo=101, minimo=99, chiusura=100, apertura=100, i=i) for i in range(25)]
        assert d.divergenza_smt(
            "EURUSD", piatta, piatta, "GBPUSD", Bias.LONG
        ) is False

    def test_none_non_e_false(self) -> None:
        """Storia insufficiente e' "non l'ho potuto guardare", non "sono
        andati insieme". Chi chiama deve distinguere, altrimenti una serie
        mancante diventa silenziosamente un giudizio."""
        assert d.divergenza_smt(
            "EURUSD", salita(3), salita(3), "GBPUSD", Bias.LONG
        ) is None

    def test_il_pareggio_non_e_un_nuovo_estremo(self) -> None:
        """Fermarsi ESATTAMENTE sul massimo precedente e' il caso in cui il
        prezzo si avvicina alla liquidita' senza prenderla."""
        serie = salita(25)
        pari = serie[:-1] + [c(massimo=serie[-2].massimo, minimo=90, chiusura=95, apertura=95, i=99)]
        assert d.nuovo_estremo(pari, Bias.LONG, 20) is False


# ===========================================================================
# CRT-10 — Double Purge Sweep
# ===========================================================================
class TestDoublePurge:
    """La forma piu' forte del pattern: il codice non la riconosceva affatto."""

    N1 = c(massimo=110, minimo=100, chiusura=110, apertura=100)

    def test_rompe_entrambi_i_lati_e_richiude(self) -> None:
        assert d.double_purge(self.N1, c(massimo=115, minimo=95, chiusura=103, apertura=105))

    def test_un_lato_solo_non_basta(self) -> None:
        assert not d.double_purge(self.N1, c(massimo=115, minimo=101, chiusura=103, apertura=105))
        assert not d.double_purge(self.N1, c(massimo=109, minimo=95, chiusura=103, apertura=105))

    def test_chiudere_fuori_non_e_richiudere(self) -> None:
        """Rompe sopra e sotto ma chiude oltre: non ha richiuso niente, ha
        solo un range grande."""
        assert not d.double_purge(self.N1, c(massimo=115, minimo=95, chiusura=114, apertura=105))

    def test_il_verso_lo_da_il_lato_piu_respinto(self) -> None:
        """La spinta piu' lunga e poi restituita e' quella dove stavano gli
        stop veri: il prezzo va dall'altra parte."""
        respinta_sopra = c(massimo=120, minimo=95, chiusura=100, apertura=105)
        assert d.verso_del_double_purge(respinta_sopra) is Bias.SHORT

        respinta_sotto = c(massimo=112, minimo=80, chiusura=110, apertura=105)
        assert d.verso_del_double_purge(respinta_sotto) is Bias.LONG

    def test_a_parita_non_si_decide(self) -> None:
        simmetrica = c(massimo=110, minimo=90, chiusura=100, apertura=100)
        assert d.verso_del_double_purge(simmetrica) is Bias.NESSUNA


# ===========================================================================
# CRT-18, CRT-19, CRT-20 — le ombre
# ===========================================================================
class TestOmbre:
    """Il blocco piu' trascurato, e quello col sospetto peggiore.

    Il CRT **e'** mean-reversion. Se CRT-20 e' vera — ombre grandi favoriscono
    la mean-reversion — allora le ombre GRANDI dovrebbero dare i CRT
    migliori, e il filtro "sweep efficiente" che teneva le piccole misurava il
    contrario di quello che serviva.
    """

    def test_il_punto_medio_dell_ombra(self) -> None:
        candela = c(massimo=120, minimo=90, chiusura=110, apertura=100)
        assert d.meta_ombra(candela, superiore=True) == pytest.approx(115.0)
        assert d.meta_ombra(candela, superiore=False) == pytest.approx(95.0)

    def test_senza_ombra_non_c_e_punto_medio(self) -> None:
        """Un livello a meta' di niente non e' un livello."""
        marubozu = c(massimo=110, minimo=100, chiusura=110, apertura=100)
        assert d.meta_ombra(marubozu, superiore=True) is None
        assert d.meta_ombra(marubozu, superiore=False) is None

    def test_peso_zero_sul_marubozu(self) -> None:
        assert d.peso_ombre(c(massimo=110, minimo=100, chiusura=110, apertura=100)) == 0.0

    def test_peso_uno_sul_doji(self) -> None:
        assert d.peso_ombre(c(massimo=110, minimo=100, chiusura=105, apertura=105)) == 1.0

    def test_la_funzione_non_dice_quale_verso_sia_buono(self) -> None:
        """Restituisce il numero e basta: quale estremo sia favorevole lo
        decide la misura, non questa funzione."""
        grandi = d.peso_ombre(c(massimo=120, minimo=80, chiusura=101, apertura=100))
        piccole = d.peso_ombre(c(massimo=111, minimo=99, chiusura=110, apertura=100))
        assert grandi is not None and piccole is not None
        assert grandi > piccole


# ===========================================================================
# CRT-11 — CISD invece di MSS
# ===========================================================================
class TestCisd:
    """Avevo implementato l'MSS dove le fonti chiedono il CISD.

    Lo swing strutturale sta piu' lontano della serie di consegna, quindi
    l'MSS arriva **sempre dopo** il CISD. Su un ingresso che vive dentro una
    candela di timeframe superiore, "dopo" significa a prezzo peggiore, e a
    volte significa mai.
    """

    @staticmethod
    def barra(apertura: float, chiusura: float, i: int = 0) -> Candela:
        return Candela(O + timedelta(hours=i), apertura,
                       max(apertura, chiusura) + 1, min(apertura, chiusura) - 1, chiusura)

    def test_il_livello_e_l_apertura_della_prima_contraria(self) -> None:
        serie = [self.barra(100, 101, 0), self.barra(105, 103, 1),
                 self.barra(103, 101, 2), self.barra(101, 99, 3)]
        assert d.cisd(serie, Bias.LONG) == pytest.approx(105.0)

    def test_senza_serie_contraria_non_c_e_cambio_da_attendere(self) -> None:
        """Il mercato consegna gia' nella direzione cercata."""
        serie = [self.barra(100, 101, 0), self.barra(101, 103, 1)]
        assert d.cisd(serie, Bias.LONG) is None

    def test_il_verso_opposto(self) -> None:
        serie = [self.barra(105, 103, 0), self.barra(100, 102, 1), self.barra(102, 104, 2)]
        assert d.cisd(serie, Bias.SHORT) == pytest.approx(100.0)

    def test_il_cisd_precede_lo_swing(self) -> None:
        """La proprieta' che distingue le due regole, resa esplicita.

        Dopo tre ribassiste, il CISD rialzista sta all'apertura della prima
        della serie; lo swing da rompere per un MSS sta al massimo formato
        **prima** di quella serie, che e' piu' in alto.
        """
        prima_della_serie = self.barra(100, 108, 0)      # massimo 109
        serie = [prima_della_serie, self.barra(107, 105, 1),
                 self.barra(105, 103, 2), self.barra(103, 101, 3)]
        livello_cisd = d.cisd(serie, Bias.LONG)
        swing = max(x.massimo for x in serie)
        assert livello_cisd is not None
        assert livello_cisd < swing, "il CISD si raggiunge prima dello swing"


# ===========================================================================
# CRT-17 — espansione nella meta' del range
# ===========================================================================
class TestMetaDelRange:
    RANGE = c(massimo=110, minimo=100, chiusura=110, apertura=100)   # 50% = 105

    def test_tutte_sopra_espande_in_alto(self) -> None:
        sopra = [c(massimo=109, minimo=106, chiusura=108, apertura=107, i=1),
                 c(massimo=110, minimo=107, chiusura=109, apertura=108, i=2)]
        assert d.meta_tenuta(self.RANGE, sopra) is Bias.LONG

    def test_tutte_sotto_espande_in_basso(self) -> None:
        sotto = [c(massimo=104, minimo=101, chiusura=102, apertura=103, i=1),
                 c(massimo=103, minimo=100, chiusura=101, apertura=102, i=2)]
        assert d.meta_tenuta(self.RANGE, sotto) is Bias.SHORT

    def test_attraversata_significa_bias_ribaltata(self) -> None:
        """*"Se la meta' cede, la bias si ribalta"*: non c'e' piu' una tenuta
        da seguire, ed e' diverso da "non lo so"."""
        miste = [c(massimo=109, minimo=106, chiusura=108, apertura=107, i=1),
                 c(massimo=104, minimo=101, chiusura=102, apertura=103, i=2)]
        assert d.meta_tenuta(self.RANGE, miste) is Bias.NESSUNA

    def test_senza_candele_successive_il_range_non_ha_ancora_detto_nulla(self) -> None:
        assert d.meta_tenuta(self.RANGE, []) is None


# ===========================================================================
# CRT-15 — le finestre orarie di Romeo
# ===========================================================================
class TestFinestreOrarie:
    """Le killzone che avevo misurato sono un ALTRO insieme di finestre.

    Quelle erano letteratura ICT generale (Londra 3-6, New York 8:30-11:30).
    Queste sono di Romeo, e non erano mai state provate.
    """

    def test_ora_di_new_york_non_utc(self) -> None:
        """Il fuso cambia due volte l'anno: una tabella in UTC sarebbe
        sbagliata per meta' anno.

        13:00 UTC e' 09:00 a New York in marzo (ora legale) e 08:00 in
        gennaio. La finestra 8-10 li contiene entrambi; la 7-9 solo il
        secondo.
        """
        marzo = datetime(2026, 3, 20, 13, 0, tzinfo=timezone.utc)      # 09 NY
        gennaio = datetime(2026, 1, 20, 13, 0, tzinfo=timezone.utc)    # 08 NY
        assert ctx.dentro_finestra_crt(marzo, TF.H1) is True
        assert ctx.dentro_finestra_crt(gennaio, TF.H1) is True

        # 03 UTC in marzo sono le 23 di New York: fuori da tutte.
        notte = datetime(2026, 3, 20, 3, 0, tzinfo=timezone.utc)
        assert ctx.dentro_finestra_crt(notte, TF.H1) is False

    def test_le_finestre_a_quattro_ore_sono_altre(self) -> None:
        nove_ny = datetime(2026, 3, 20, 13, 0, tzinfo=timezone.utc)
        assert ctx.dentro_finestra_crt(nove_ny, TF.H4) is False, "1-9 esclude le 9"
        otto_ny = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert ctx.dentro_finestra_crt(otto_ny, TF.H4) is True

    def test_none_dove_le_fonti_non_danno_finestre(self) -> None:
        """`None` non e' "fuori finestra": e' "non c'e' una finestra da
        rispettare". Confonderli bloccherebbe per sempre un timeframe che non
        ha regola."""
        quando = datetime(2026, 3, 20, 13, 0, tzinfo=timezone.utc)
        assert ctx.dentro_finestra_crt(quando, TF.D1) is None


# ===========================================================================
# CRT-04 e CRT-06 — coppie e modelli allineati
# ===========================================================================
class TestCoppieEAllineamento:
    def test_la_coppia_di_romeo_e_w1_h4(self) -> None:
        """Il risultato migliore che avevo riportato era su `W1 -> D1`, che
        NON e' una coppia delle fonti."""
        assert COPPIE_CRT[TF.W1] is TF.H4
        assert COPPIE_CRT.get(TF.W1) is not TF.D1

    def test_le_coppie_fuori_da_def01_sono_dichiarate_non_nascoste(self) -> None:
        """DEF-01 ammette dieci timeframe e dice che nessun altro puo' essere
        citato. Quattro coppie delle fonti ne nominano altri: stanno come
        stringhe, che e' cio' che sono finche' qualcuno non decide."""
        assert ("4h", "15m") in COPPIE_CRT_FUORI_DEF01
        assert ("1h", "5m") in COPPIE_CRT_FUORI_DEF01
        assert len(COPPIE_CRT) + len(COPPIE_CRT_FUORI_DEF01) == 7

    def test_tutte_le_coppie_ammesse_usano_timeframe_di_def01(self) -> None:
        for alto, basso in COPPIE_CRT.items():
            assert isinstance(alto, TF) and isinstance(basso, TF)

    def test_modelli_concordi_si_contano(self) -> None:
        class Finto:
            def __init__(self, direzione: Bias) -> None:
                self.direzione = direzione

        assert stp.modelli_allineati(
            {TF.D1: Finto(Bias.SHORT), TF.W1: Finto(Bias.SHORT), TF.M1: Finto(Bias.SHORT)}
        ) == (Bias.SHORT, 3)

    def test_un_disaccordo_non_e_una_direzione_debole(self) -> None:
        class Finto:
            def __init__(self, direzione: Bias) -> None:
                self.direzione = direzione

        assert stp.modelli_allineati(
            {TF.D1: Finto(Bias.SHORT), TF.W1: Finto(Bias.LONG)}
        ) == (Bias.NESSUNA, 0)

    def test_nessun_crt_non_e_un_disaccordo(self) -> None:
        assert stp.modelli_allineati({TF.D1: None, TF.W1: None}) == (Bias.NESSUNA, 0)
