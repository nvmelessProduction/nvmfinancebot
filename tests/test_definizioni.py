"""Collaudo di core/definizioni.py, regola per regola.

Ogni classe copre una regola di `docs/01_definizioni.md` e cita il suo ID.
I casi limite che i documenti elencano esplicitamente hanno un test proprio,
con il nome che dice quale caso e'.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import definizioni as d
from core.definizioni import Bias, Candela, Divergenza, Mitigazione, Polarita, Presa, TipoKeyLevel
from core.parametri import TF

INIZIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def c(apertura: float, massimo: float, minimo: float, chiusura: float, giorni: int = 0) -> Candela:
    """Costruttore breve. L'ordine e' OHLC, come si legge sui grafici."""
    return Candela(INIZIO + timedelta(days=giorni), apertura, massimo, minimo, chiusura)


# ===========================================================================
# DEF-04, DEF-39 — misure di base
# ===========================================================================
class TestMisure:
    def test_def04_range(self) -> None:
        assert d.intervallo(c(10, 12, 8, 11)) == 4

    def test_def04_range_nullo_e_incoerente(self) -> None:
        """Range zero impone PRIN-99 a chi chiama, non un'eccezione qui."""
        piatta = c(10, 10, 10, 10)
        assert d.intervallo(piatta) == 0
        assert d.range_coerente(piatta) is False
        assert d.range_coerente(c(10, 11, 9, 10)) is True

    def test_def39_corpo_e_ombre(self) -> None:
        rialzista = c(10, 13, 9, 12)
        assert d.corpo(rialzista) == 2
        assert d.ombra_superiore(rialzista) == 1
        assert d.ombra_inferiore(rialzista) == 1

        ribassista = c(12, 13, 9, 10)
        assert d.corpo(ribassista) == 2
        assert d.ombra_superiore(ribassista) == 1
        assert d.ombra_inferiore(ribassista) == 1

    def test_candela_incoerente_e_rifiutata(self) -> None:
        with pytest.raises(ValueError):
            Candela(INIZIO, 10, 8, 12, 10)        # massimo sotto il minimo
        with pytest.raises(ValueError):
            Candela(INIZIO, 20, 12, 8, 10)        # apertura fuori dal range


# ===========================================================================
# DEF-09 — inside bar
# ===========================================================================
class TestInsideBar:
    def test_def09_inside_bar(self) -> None:
        c1 = c(10, 15, 5, 12)
        assert d.e_inside_bar(c(11, 14, 6, 12), c1) is True

    def test_def09_estremi_uguali_sono_inside(self) -> None:
        """Confronto con <= e >=: i valori esatti contano, nessuna tolleranza."""
        c1 = c(10, 15, 5, 12)
        assert d.e_inside_bar(c(11, 15, 5, 12), c1) is True

    def test_def09_un_tick_fuori_non_e_inside(self) -> None:
        c1 = c(10, 15, 5, 12)
        assert d.e_inside_bar(c(11, 15.01, 6, 12), c1) is False
        assert d.e_inside_bar(c(11, 14, 4.99, 12), c1) is False


# ===========================================================================
# DEF-10, DEF-11, DEF-12 — formazione del gap
# ===========================================================================
class TestFormazioneGap:
    def test_def10_gap_rialzista(self) -> None:
        gap = d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(14, 18, 13, 17), TF.D1)
        assert gap is not None
        assert gap.polarita is Polarita.RIALZISTA
        assert (gap.zona_inf, gap.zona_sup) == (12, 13)   # [high P1, low P3]
        assert gap.livello_inv == 8                        # low P1

    def test_def11_gap_ribassista(self) -> None:
        gap = d.gap_ribassista(c(17, 18, 13, 14), c(13, 14, 10, 11), c(10, 12, 8, 9), TF.D1)
        assert gap is not None
        assert gap.polarita is Polarita.RIBASSISTA
        assert (gap.zona_inf, gap.zona_sup) == (12, 13)   # [high P3, low P1]
        assert gap.livello_inv == 18                       # high P1

    def test_def10_senza_separazione_nessun_gap(self) -> None:
        """P3 tocca il massimo di P1: serve `low[P3] > high[P1]`, stretto."""
        assert d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(13, 15, 12, 14), TF.D1) is None

    def test_def10_minimo_esattamente_sul_massimo_di_p1(self) -> None:
        assert d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(13, 15, 12, 14), TF.D1) is None
        assert d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(13, 15, 12.01, 14), TF.D1) is not None

    def test_def12_invalidazione_sta_fuori_dalla_zona(self) -> None:
        """Il livello di invalidazione e' sotto la zona per un gap rialzista."""
        gap = d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(14, 18, 13, 17), TF.D1)
        assert gap is not None and gap.livello_inv < gap.zona_inf
        gap_giu = d.gap_ribassista(c(17, 18, 13, 14), c(13, 14, 10, 11), c(10, 12, 8, 9), TF.D1)
        assert gap_giu is not None and gap_giu.livello_inv > gap_giu.zona_sup


# ===========================================================================
# DEF-14 — invalidazione. Caso limite richiesto: ombra contro chiusura.
# ===========================================================================
class TestInvalidazione:
    def gap_su(self) -> d.Gap:
        gap = d.gap_rialzista(c(10, 12, 8, 11), c(11, 14, 10, 13), c(14, 18, 13, 17), TF.D1)
        assert gap is not None
        return gap                                   # livello_inv = 8

    def test_def14_ombra_non_invalida(self) -> None:
        """CASO LIMITE: l'ombra buca il livello, la chiusura no. Gap valido."""
        gap = self.gap_su()
        perfora_con_ombra = c(10, 11, 6, 10)         # minimo 6 < 8, chiusura 10 > 8
        assert d.gap_invalidato(gap, [perfora_con_ombra]) is False

    def test_def14_chiusura_invalida(self) -> None:
        gap = self.gap_su()
        assert d.gap_invalidato(gap, [c(10, 11, 6, 7)]) is True

    def test_def14_chiusura_esatta_sul_livello_non_invalida(self) -> None:
        """Serve `close < livello_inv`, stretto: sul livello il gap resta valido."""
        assert d.gap_invalidato(self.gap_su(), [c(10, 11, 7, 8)]) is False

    def test_def14_ribassista_a_specchio(self) -> None:
        gap = d.gap_ribassista(c(17, 18, 13, 14), c(13, 14, 10, 11), c(10, 12, 8, 9), TF.D1)
        assert gap is not None                        # livello_inv = 18
        assert d.gap_invalidato(gap, [c(15, 20, 14, 17)]) is False   # ombra sopra
        assert d.gap_invalidato(gap, [c(15, 20, 14, 19)]) is True    # chiusura sopra


# ===========================================================================
# DEF-13, DEF-15bis — gap attivo e ruolo
# ===========================================================================
class TestGapAttivo:
    def gap(self, tf: TF, giorni: int, polarita: Polarita = Polarita.RIALZISTA) -> d.Gap:
        return d.Gap(polarita, 100, 110, 90, tf, INIZIO + timedelta(days=giorni))

    def test_def13_vince_il_timeframe_piu_alto(self) -> None:
        scelto = d.gap_attivo(
            {TF.D1: [self.gap(TF.D1, 10)], TF.M1: [self.gap(TF.M1, 1)]},
            Polarita.RIALZISTA,
        )
        assert scelto is not None and scelto.tf is TF.M1

    def test_def13_a_parita_di_tf_vince_il_piu_recente(self) -> None:
        scelto = d.gap_attivo(
            {TF.W1: [self.gap(TF.W1, 1), self.gap(TF.W1, 30)]}, Polarita.RIALZISTA
        )
        assert scelto is not None and scelto.orario_formazione == INIZIO + timedelta(days=30)

    def test_def13_polarita_separate(self) -> None:
        gap_per_tf = {TF.W1: [self.gap(TF.W1, 1, Polarita.RIBASSISTA)]}
        assert d.gap_attivo(gap_per_tf, Polarita.RIALZISTA) is None
        assert d.gap_attivo(gap_per_tf, Polarita.RIBASSISTA) is not None

    def test_def31_h12_e_h6_sono_nella_scansione(self) -> None:
        """REV-15: DEF-31 li fa entrare nell'ordine di DEF-13."""
        scelto = d.gap_attivo({TF.H12: [self.gap(TF.H12, 1)]}, Polarita.RIALZISTA)
        assert scelto is not None and scelto.tf is TF.H12

    def test_def13_nessun_gap(self) -> None:
        assert d.gap_attivo({}, Polarita.RIALZISTA) is None

    def test_def15bis_polarita_non_da_la_direzione(self) -> None:
        """Un gap rialzista SOTTO il prezzo e' un target ribassista."""
        rialzista_sotto = d.Gap(Polarita.RIALZISTA, 100, 110, 90, TF.W1, INIZIO)
        assert d.direzione_verso_gap(rialzista_sotto, prezzo=150) is Bias.SHORT
        ribassista_sopra = d.Gap(Polarita.RIBASSISTA, 100, 110, 120, TF.W1, INIZIO)
        assert d.direzione_verso_gap(ribassista_sopra, prezzo=50) is Bias.LONG

    def test_def15bis_prezzo_dentro_la_zona(self) -> None:
        gap = d.Gap(Polarita.RIALZISTA, 100, 110, 90, TF.W1, INIZIO)
        assert d.direzione_verso_gap(gap, prezzo=105) is Bias.NESSUNA


# ===========================================================================
# DEF-19, DEF-20 — accettazione
# ===========================================================================
class TestAccettazione:
    C1 = c(10, 15, 5, 12)

    def test_def19_livelli_sono_gli_estremi_di_c1(self) -> None:
        assert d.livelli_riferimento(self.C1) == (15, 5)

    def test_def20_accettazione(self) -> None:
        assert d.e_accettazione_rialzo(c(14, 17, 13, 16), self.C1) is True
        assert d.e_accettazione_ribasso(c(6, 7, 3, 4), self.C1) is True

    def test_def20_chiusura_sul_livello_non_accetta(self) -> None:
        """Serve `close > livello_sup`, stretto."""
        assert d.e_accettazione_rialzo(c(14, 17, 13, 15), self.C1) is False
        assert d.e_accettazione_ribasso(c(6, 7, 3, 5), self.C1) is False

    def test_def19_un_tick_basta(self) -> None:
        assert d.e_accettazione_rialzo(c(14, 17, 13, 15.01), self.C1) is True


# ===========================================================================
# DEF-21 — i due gradi di rifiuto. Caso limite richiesto.
# ===========================================================================
class TestRifiuto:
    C1 = c(10, 15, 5, 12)

    def test_def21_le_tre_condizioni_del_semplice(self) -> None:
        """Servono tutte e tre: buca il livello, richiude sotto, chiude sotto C1."""
        assert d.e_rifiuto_rialzo(c(13, 16, 10, 11), self.C1) is True
        # non buca il livello
        assert d.e_rifiuto_rialzo(c(13, 14.9, 10, 11), self.C1) is False
        # buca ma NON richiude sotto: e' accettazione, non rifiuto
        assert d.e_rifiuto_rialzo(c(13, 17, 10, 16), self.C1) is False
        # richiude sotto il livello ma chiude sopra C1: manca la terza
        assert d.e_rifiuto_rialzo(c(13, 16, 10, 14), self.C1) is False

    def test_def21_semplice_si_forte_no(self) -> None:
        """CASO LIMITE: due gradi distinti, non intercambiabili.

        Corpo lungo e ombra corta: il rifiuto c'e', la spike non prevale.
        Usare il grado sbagliato qui cambierebbe il numero di CRT validi.
        """
        corpo_lungo = c(15.5, 16, 8, 9)      # corpo 6.5, ombra_sup 0.5
        assert d.corpo(corpo_lungo) == 6.5
        assert d.ombra_superiore(corpo_lungo) == 0.5
        assert d.e_rifiuto_rialzo(corpo_lungo, self.C1) is True
        assert d.e_rifiuto_forte_rialzo(corpo_lungo, self.C1) is False

    def test_def21_semplice_si_forte_si(self) -> None:
        spike = c(13, 16, 9, 11)             # corpo 2, ombra_sup 3 -> 3 > 0.5*2
        assert d.e_rifiuto_rialzo(spike, self.C1) is True
        assert d.e_rifiuto_forte_rialzo(spike, self.C1) is True

    def test_def21_soglia_della_spike_e_stretta(self) -> None:
        """`ombra > 0.5 x corpo`, non `>=`: sulla soglia esatta il forte non scatta."""
        esatta = c(14, 16, 9, 10)            # corpo 4, ombra_sup 2 = 0.5 x 4
        assert d.corpo(esatta) == 4 and d.ombra_superiore(esatta) == 2
        assert d.e_rifiuto_rialzo(esatta, self.C1) is True
        assert d.e_rifiuto_forte_rialzo(esatta, self.C1) is False

        appena_sopra = c(14, 16.01, 9, 10)   # ombra_sup 2.01 > 2
        assert d.e_rifiuto_forte_rialzo(appena_sopra, self.C1) is True

    def test_def21_corpo_nullo_qualsiasi_ombra_basta(self) -> None:
        """DEF-21 lo dice esplicitamente, ed evita una divisione per zero."""
        marubozu_piatto = c(11, 16, 11, 11)   # corpo 0, ombra_sup 5
        assert d.e_rifiuto_rialzo(marubozu_piatto, self.C1) is True
        assert d.e_rifiuto_forte_rialzo(marubozu_piatto, self.C1) is True

    def test_def21_ribasso_a_specchio(self) -> None:
        giu = c(7, 11, 4, 9)               # buca 5, richiude sopra, chiude sotto 12? 9 < 12 no
        assert d.e_rifiuto_ribasso(giu, self.C1) is False   # serve close > close[C1]
        giu2 = c(7, 14, 4, 13)             # corpo 6, ombra_inf 3 -> semplice si', forte no
        assert d.e_rifiuto_ribasso(giu2, self.C1) is True
        assert d.e_rifiuto_forte_ribasso(giu2, self.C1) is False


# ===========================================================================
# DEF-40, DEF-41 — confluente e indecisione
# ===========================================================================
class TestFigure:
    def test_def40_confluente(self) -> None:
        c1 = c(10, 15, 5, 12)
        assert d.e_confluente_rialzo(c(15.5, 20, 15.4, 19), c1) is True
        assert d.e_confluente_ribasso(c(4.5, 4.6, 0, 1), c1) is True

    def test_def40_corpo_deve_battere_l_ombra(self) -> None:
        c1 = c(10, 15, 5, 12)
        # chiude sopra 15 ma con ombra superiore piu' lunga del corpo
        assert d.e_confluente_rialzo(c(15.5, 25, 15.4, 16), c1) is False

    def test_def41_doji(self) -> None:
        doji = c(10, 12, 8, 10.05)          # corpo 0.05 su range 4 = 1.25%
        assert d.e_indecisione(doji) is True

    def test_def41_martello_non_e_indecisione(self) -> None:
        """Corpo piccolo ma una sola ombra lunga: la seconda condizione lo esclude."""
        martello = c(11.9, 12, 8, 11.95)    # ombra_inf lunghissima, ombra_sup quasi nulla
        assert d.e_indecisione(martello) is False

    def test_def41_soglia_del_corpo(self) -> None:
        """REV-32: la soglia decisa e' 0.05 del range."""
        appena_dentro = c(10, 12, 8, 10.2)   # corpo 0.2 = 5% di 4
        appena_fuori = c(10, 12, 8, 10.3)    # corpo 0.3 = 7.5% di 4
        assert d.e_indecisione(appena_dentro) is True
        assert d.e_indecisione(appena_fuori) is False

    def test_def41_range_nullo_non_e_indecisione(self) -> None:
        assert d.e_indecisione(c(10, 10, 10, 10)) is False

    def test_def41_grado_rafforzato(self) -> None:
        c1 = c(10, 15, 5, 12)
        dentro = c(10, 12, 8, 10.05)         # chiusura dentro [5, 15]
        fuori = c(16, 18, 15.9, 16.05)       # chiusura sopra 15
        assert d.e_indecisione_forte(dentro, c1) is True
        assert d.e_indecisione_forte(fuori, c1) is False


# ===========================================================================
# DEF-42 — aspettativa di mitigazione
# ===========================================================================
class TestMitigazione:
    C1 = c(10, 15, 5, 12)

    def test_def42_confluente_non_attende_mitigazione(self) -> None:
        confluente = c(15.5, 20, 15.4, 19)
        assert d.mitigazione_attesa(confluente, self.C1, Polarita.RIALZISTA) is Mitigazione.NON_ATTESA

    def test_def42_indecisione_attende_mitigazione(self) -> None:
        doji = c(10, 12, 8, 10.05)
        assert d.mitigazione_attesa(doji, self.C1, Polarita.RIALZISTA) is Mitigazione.ATTESA

    def test_def42_inside_bar_attende_mitigazione(self) -> None:
        inside = c(11, 14, 6, 13)
        assert d.mitigazione_attesa(inside, self.C1, Polarita.RIALZISTA) is Mitigazione.ATTESA

    def test_def42_non_determinata_comporta_astensione(self) -> None:
        """Non e' un errore: e' una condizione prevista (CTX-01 #10)."""
        # Non inside (massimo 16 oltre C1), non confluente (ombra_sup 2 > corpo 1),
        # non rifiuto forte (chiude sopra C1), non doji (corpo 20% del range).
        neutra = c(13, 16, 11, 14)
        assert d.e_inside_bar(neutra, self.C1) is False
        assert d.e_confluente_rialzo(neutra, self.C1) is False
        assert d.e_rifiuto_forte_rialzo(neutra, self.C1) is False
        assert d.e_indecisione(neutra) is False
        assert d.mitigazione_attesa(neutra, self.C1, Polarita.RIALZISTA) is Mitigazione.NON_DETERMINATA

    def test_def42_polarita_non_direzione_operativa(self) -> None:
        """REV-29: DEF-42 valuta il gap alla formazione, quando la direzione
        operativa non esiste ancora."""
        confluente_giu = c(4.5, 4.6, 0, 1)
        assert d.mitigazione_attesa(confluente_giu, self.C1, Polarita.RIBASSISTA) is Mitigazione.NON_ATTESA
        # Con la polarita' opposta la stessa candela non e' confluente.
        assert d.mitigazione_attesa(confluente_giu, self.C1, Polarita.RIALZISTA) is not Mitigazione.NON_ATTESA


# ===========================================================================
# DEF-43 — le quattro fasi
# ===========================================================================
class TestFasiGap:
    ZONA = d.Gap(Polarita.RIBASSISTA, 100, 110, 120, TF.W1, INIZIO)   # zona sopra il prezzo

    def test_def43_sequenza_completa_bias_short(self) -> None:
        stato = d.StatoFasi()
        # fase 1: entra in zona salendo, l'estremo si aggiorna in continuo
        stato = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 102)
        assert stato.fase == 1 and stato.estremo_fase1 == 102
        stato = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 108)
        assert stato.estremo_fase1 == 108
        stato = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 105)
        assert stato.estremo_fase1 == 108, "l'estremo non arretra"

        # fase 2: esce dal lato di entrata, cioe' sotto la zona
        stato = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 95)
        assert stato.fase == 2 and stato.estremo_fase1 == 108

        # rientro, poi superamento dell'estremo di fase 1
        stato = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 104)
        assert stato.fase == 2 and stato.dentro_zona is True
        assert d.fase_tre_raggiunta(stato, 107, Bias.SHORT) is False
        assert d.fase_tre_raggiunta(stato, 109, Bias.SHORT) is True

    def test_def43_uscita_dal_lato_sbagliato_non_apre_la_fase_2(self) -> None:
        """REV-30: la fase 2 e' una reazione, cioe' un ritorno indietro."""
        stato = d.avanza_fasi(d.StatoFasi(), self.ZONA, Bias.SHORT, 105)
        oltre = d.avanza_fasi(stato, self.ZONA, Bias.SHORT, 130)   # esce sopra
        assert oltre.fase == 1, "uscire dal lato opposto non e' automatic reaction"

    def test_def43_fase_1_non_e_operativa(self) -> None:
        """La fase 1 e' il movimento che gli appunti chiamano fake."""
        stato = d.avanza_fasi(d.StatoFasi(), self.ZONA, Bias.SHORT, 105)
        assert stato.fase == 1
        assert d.fase_tre_raggiunta(stato, 999, Bias.SHORT) is False

    def test_def43_a_specchio_bias_long(self) -> None:
        zona_sotto = d.Gap(Polarita.RIALZISTA, 100, 110, 90, TF.W1, INIZIO)
        stato = d.avanza_fasi(d.StatoFasi(), zona_sotto, Bias.LONG, 108)
        assert stato.fase == 1 and stato.estremo_fase1 == 108
        stato = d.avanza_fasi(stato, zona_sotto, Bias.LONG, 102)
        assert stato.estremo_fase1 == 102, "su bias long l'estremo e' un minimo"
        stato = d.avanza_fasi(stato, zona_sotto, Bias.LONG, 115)   # esce sopra
        assert stato.fase == 2
        stato = d.avanza_fasi(stato, zona_sotto, Bias.LONG, 105)   # rientra
        assert d.fase_tre_raggiunta(stato, 101, Bias.LONG) is True

    def test_def43_stato_immutabile(self) -> None:
        iniziale = d.StatoFasi()
        d.avanza_fasi(iniziale, self.ZONA, Bias.SHORT, 105)
        assert iniziale.fase == 0, "avanza_fasi non muta l'argomento"


# ===========================================================================
# DEF-44 — RSI e divergenza
# ===========================================================================
class TestRsi:
    def test_def44_rsi_serve_storia_sufficiente(self) -> None:
        assert d.rsi([1.0] * 14) is None
        assert d.rsi([1.0] * 15) is not None

    def test_def44_rsi_tutto_in_salita(self) -> None:
        assert d.rsi([float(i) for i in range(1, 40)]) == 100.0

    def test_def44_rsi_tutto_in_discesa(self) -> None:
        valore = d.rsi([float(i) for i in range(40, 1, -1)])
        assert valore is not None and valore == pytest.approx(0.0)

    def test_def44_rsi_dentro_i_limiti(self) -> None:
        serie = [10.0, 11, 10.5, 12, 11.5, 13, 12.5, 14, 13.5, 15, 14.5, 16, 15.5, 17, 16.5, 18]
        valore = d.rsi(serie)
        assert valore is not None and 0.0 <= valore <= 100.0

    def test_def44_divergenza_ribassista(self) -> None:
        """Prezzo piu' alto, RSI piu' basso, su un gap con bias short."""
        assert d.divergenza_rsi(100, 70, 105, 65, Bias.SHORT) is Divergenza.RIBASSISTA

    def test_def44_divergenza_rialzista(self) -> None:
        assert d.divergenza_rsi(100, 30, 95, 35, Bias.LONG) is Divergenza.RIALZISTA

    def test_def44_senza_divergenza(self) -> None:
        assert d.divergenza_rsi(100, 70, 105, 75, Bias.SHORT) is Divergenza.NESSUNA
        assert d.divergenza_rsi(100, 70, 95, 65, Bias.SHORT) is Divergenza.NESSUNA


# ===========================================================================
# DEF-16, DEF-23, DEF-24 — bias. Tre casi limite richiesti.
# ===========================================================================
class TestBias:
    C1 = c(10, 15, 5, 12)

    def test_def16_passo1_rompe_entrambi_e_chiude_in_mezzo(self) -> None:
        """CASO LIMITE: rifiuto a rialzo e a ribasso sarebbero simultanei."""
        spazza_tutto = c(10, 16, 4, 10)
        assert d.bias_timeframe(spazza_tutto, self.C1) is Bias.NESSUNA

    def test_def16_passo1_precede_ogni_altro(self) -> None:
        """Il passo 1 vince anche se la candela sarebbe un rifiuto."""
        candela = c(10, 16, 4, 11)         # rompe sopra e sotto, chiude dentro
        assert d.e_rifiuto_rialzo(candela, self.C1) is True
        assert d.bias_timeframe(candela, self.C1) is Bias.NESSUNA

    def test_def16_accettazione(self) -> None:
        assert d.bias_timeframe(c(14, 17, 13, 16), self.C1) is Bias.LONG
        assert d.bias_timeframe(c(6, 7, 3, 4), self.C1) is Bias.SHORT

    def test_def16_rifiuto_inverte(self) -> None:
        """Un rifiuto a rialzo produce bias SHORT, non LONG."""
        assert d.bias_timeframe(c(13, 16, 9, 11), self.C1) is Bias.SHORT
        assert d.bias_timeframe(c(7, 14, 4, 13), self.C1) is Bias.LONG

    def test_def23_inside_bar_che_forma_un_gap(self) -> None:
        """CASO LIMITE: inside bar rispetto a C1 e gap rispetto a C2."""
        c2 = c(1, 2, 0.5, 1.5)             # P1: massimo 2
        c1 = c(2, 20, 1.8, 18)             # P2: candelone
        c0 = c(15, 19, 3, 16)              # inside di C1, e minimo 3 > massimo C2 = 2
        assert d.e_inside_bar(c0, c1) is True
        assert d.gap_rialzista(c2, c1, c0, TF.D1) is not None
        assert d.bias_timeframe(c0, c1, c2) is Bias.LONG

    def test_def23_inside_bar_senza_gap_eredita(self) -> None:
        c1 = c(10, 15, 5, 12)
        c2 = c(9, 16, 4, 10)               # massimo 16 > minimo di c0: nessun gap
        inside = c(11, 14, 6, 13)
        assert d.bias_timeframe(inside, c1, c2, bias_precedente=Bias.SHORT) is Bias.SHORT

    def test_def24_eredita_ricorsiva_su_serie_di_inside(self) -> None:
        """CASO LIMITE: una serie consecutiva di inside bar mantiene la bias."""
        madre = c(10, 20, 0, 18)
        bias = d.bias_timeframe(c(19, 22, 18, 21), madre)      # accettazione: LONG
        assert bias is Bias.LONG

        precedente = madre
        for passo in range(5):
            inside = c(11, 19 - passo, 1 + passo, 12)
            bias = d.bias_timeframe(inside, precedente, bias_precedente=bias)
            assert bias is Bias.LONG, f"persa all'inside numero {passo + 1}"
            precedente = inside

    def test_def24_senza_bias_precedente_nessuna(self) -> None:
        """Avvio del sistema o storico insufficiente."""
        assert d.bias_timeframe(c(11, 14, 6, 13), self.C1) is Bias.NESSUNA

    def test_def17_timeframe_opposto_al_12m_non_opera(self) -> None:
        assert d.timeframe_operabile(Bias.SHORT, Bias.LONG) is False
        assert d.timeframe_operabile(Bias.LONG, Bias.LONG) is True
        assert d.timeframe_operabile(Bias.NESSUNA, Bias.LONG) is True
        assert d.timeframe_operabile(Bias.SHORT, Bias.NESSUNA) is True


# ===========================================================================
# DEF-36, DEF-37, DEF-38, DEF-30 — key level
# ===========================================================================
class TestKeyLevel:
    def test_def36_tre_livelli_su_c1(self) -> None:
        massimo, minimo, meta = d.key_levels(c(10, 20, 10, 15), TF.W1)
        assert (massimo.valore, minimo.valore, meta.valore) == (20, 10, 15)
        assert massimo.tipo is TipoKeyLevel.MAX

    def test_def36_liv50_su_qualsiasi_candela(self) -> None:
        """Aggiunta in v1.9: TP1 la usa su N1, anche su TF_H4 e TF_H1."""
        assert d.liv_50(c(10, 20, 10, 15)) == 15
        assert d.liv_50(c(1.1, 1.2, 1.0, 1.15)) == pytest.approx(1.1)

    def test_def37_key_level_coincidenti(self) -> None:
        """CASO LIMITE: il minimo mensile e' per costruzione identico a quello
        di una delle sue settimanali. Sono lo stesso prezzo, non due vicini."""
        mensile = d.KeyLevel(TF.M1, TipoKeyLevel.MIN, 1234.5)
        settimanale = d.KeyLevel(TF.W1, TipoKeyLevel.MIN, 1234.5)
        rimasti = d.assorbi_key_level([settimanale, mensile])
        assert len(rimasti) == 1
        assert rimasti[0].tf is TF.M1, "vince il timeframe piu' alto"

    def test_def37_valori_diversi_restano_entrambi(self) -> None:
        rimasti = d.assorbi_key_level([
            d.KeyLevel(TF.M1, TipoKeyLevel.MIN, 1234.5),
            d.KeyLevel(TF.W1, TipoKeyLevel.MIN, 1234.6),
        ])
        assert len(rimasti) == 2

    def test_def37_nessuna_tolleranza(self) -> None:
        """Uguaglianza esatta: un tick di differenza e sono due livelli."""
        rimasti = d.assorbi_key_level([
            d.KeyLevel(TF.M1, TipoKeyLevel.MAX, 100.00),
            d.KeyLevel(TF.W1, TipoKeyLevel.MAX, 100.00001),
        ])
        assert len(rimasti) == 2

    def test_def38_presa_a_candela_chiusa(self) -> None:
        livello = d.KeyLevel(TF.W1, TipoKeyLevel.MAX, 100.0)
        assert d.presa_key_level(c(98, 101, 97, 99), livello) is Presa.RIALZO
        assert d.presa_key_level(c(98, 99.9, 97, 99), livello) is Presa.NESSUNA

    def test_def38_sul_livello_non_e_presa(self) -> None:
        livello = d.KeyLevel(TF.W1, TipoKeyLevel.MAX, 100.0)
        assert d.presa_key_level(c(98, 100.0, 97, 99), livello) is Presa.NESSUNA

    def test_def38_ribasso(self) -> None:
        livello = d.KeyLevel(TF.W1, TipoKeyLevel.MIN, 100.0)
        assert d.presa_key_level(c(102, 103, 99, 101), livello) is Presa.RIBASSO

    def test_def30_trigger_strettamente_inferiori(self) -> None:
        ammessi = d.timeframe_trigger_ammessi(TF.W1)
        assert TF.W1 not in ammessi
        assert TF.D1 in ammessi and TF.H4 in ammessi and TF.H1 in ammessi
        assert TF.M1 not in ammessi

    def test_def30_h12_e_h6_esclusi_dai_trigger(self) -> None:
        """REV-11: servono ai gap, non possono ospitare un CRT."""
        ammessi = d.timeframe_trigger_ammessi(TF.D1)
        assert TF.H12 not in ammessi and TF.H6 not in ammessi
        # Dai timeframe di CRT-04 in giu': un key level giornaliero puo'
        # essere spazzato da un CRT a quattro ore come da uno a 15 minuti.
        # E' cio' che rende praticabili le coppie intraday.
        assert ammessi == (TF.H4, TF.H1, TF.MIN15, TF.MIN5, TF.MIN1)

    def test_def30_sotto_l_ora_restano_i_trigger_intraday(self) -> None:
        """Un key level orario puo' essere spazzato da un CRT a 15, 5 o 1
        minuto: sono le coppie `1h -> 5m` e `15m -> 1m` di CRT-04.

        Prima della loro introduzione questo caso dava la tupla vuota,
        perche' sotto l'ora non c'era nulla."""
        assert d.timeframe_trigger_ammessi(TF.H1) == (TF.MIN15, TF.MIN5, TF.MIN1)

    def test_def30_dal_piu_basso_in_assoluto_nessun_trigger(self) -> None:
        """Sotto il minuto non c'e' niente: nessun timeframe puo' spazzare
        un key level del minuto."""
        assert d.timeframe_trigger_ammessi(TF.MIN1) == ()


# ===========================================================================
# DEF-25, DEF-26, DEF-27, DEF-22, DEF-29 — livelli e target
# ===========================================================================
class TestTarget:
    def test_def25_ogni_estremo_e_un_livello(self) -> None:
        livelli = d.livelli_strutturali([c(10, 15, 5, 12), c(12, 18, 11, 17)], TF.D1)
        assert len(livelli) == 4
        assert {l.valore for l in livelli} == {15, 5, 18, 11}

    def test_def26_pavimento_di_tre_candele(self) -> None:
        assert d.timeframe_utilizzabile(2) is False
        assert d.timeframe_utilizzabile(3) is True

    def test_def27_consumo_al_tocco(self) -> None:
        rialzista = d.LivelloStrutturale(TF.D1, 100.0, INIZIO, True)
        assert d.livello_consumato(rialzista, 99.99) is False
        assert d.livello_consumato(rialzista, 100.0) is True, "al tocco, non oltre"
        ribassista = d.LivelloStrutturale(TF.D1, 100.0, INIZIO, False)
        assert d.livello_consumato(ribassista, 100.0) is True

    def test_def22_parte_sempre_dal_12m(self) -> None:
        """Anche con livelli piu' vicini su timeframe bassi, vince il piu' alto."""
        target = d.target_direzionale(
            {
                TF.M12: [d.LivelloStrutturale(TF.M12, 200.0, INIZIO, True)],
                TF.D1: [d.LivelloStrutturale(TF.D1, 105.0, INIZIO, True)],
            },
            prezzo=100.0,
            direzione=Bias.LONG,
        )
        assert target is not None and target.tf is TF.M12 and target.valore == 200.0

    def test_def22_il_piu_vicino_dentro_il_timeframe(self) -> None:
        target = d.target_direzionale(
            {TF.W1: [
                d.LivelloStrutturale(TF.W1, 150.0, INIZIO, True),
                d.LivelloStrutturale(TF.W1, 120.0, INIZIO, True),
            ]},
            prezzo=100.0,
            direzione=Bias.LONG,
        )
        assert target is not None and target.valore == 120.0

    def test_def22_solo_livelli_oltre_il_prezzo(self) -> None:
        target = d.target_direzionale(
            {TF.W1: [d.LivelloStrutturale(TF.W1, 90.0, INIZIO, True)]},
            prezzo=100.0,
            direzione=Bias.LONG,
        )
        assert target is None, "un livello sotto il prezzo non e' un target long"

    def test_def22_short_a_specchio(self) -> None:
        target = d.target_direzionale(
            {TF.W1: [
                d.LivelloStrutturale(TF.W1, 50.0, INIZIO, False),
                d.LivelloStrutturale(TF.W1, 80.0, INIZIO, False),
            ]},
            prezzo=100.0,
            direzione=Bias.SHORT,
        )
        assert target is not None and target.valore == 80.0

    def test_def22_nessun_target_impone_prin99(self) -> None:
        assert d.target_direzionale({}, 100.0, Bias.LONG) is None
        assert d.target_direzionale({}, 100.0, Bias.NESSUNA) is None

    def test_def29_raggiungimento_al_tocco(self) -> None:
        target = d.LivelloStrutturale(TF.W1, 120.0, INIZIO, True)
        assert d.target_raggiunto(target, 119.99) is False
        assert d.target_raggiunto(target, 120.0) is True


# ===========================================================================
# DEF-33 — strumenti a segno invertito
# ===========================================================================
class TestStrumenti:
    def test_def33_segno_diretto(self) -> None:
        assert d.direzione_cfd(Bias.LONG, "EURUSD") is Bias.LONG
        assert d.direzione_cfd(Bias.SHORT, "XAUUSD") is Bias.SHORT

    def test_def33_segno_invertito(self) -> None:
        """Un CRT short su 6J produce un ordine BUY su USDJPY."""
        assert d.direzione_cfd(Bias.SHORT, "USDJPY") is Bias.LONG
        assert d.direzione_cfd(Bias.LONG, "USDCHF") is Bias.SHORT

    def test_def33_strumento_fuori_universo(self) -> None:
        with pytest.raises(ValueError):
            d.direzione_cfd(Bias.LONG, "BTCUSD")       # ESCL-05


# ===========================================================================
# Purezza: nessuna funzione tiene stato fra una chiamata e l'altra
# ===========================================================================
class TestPurezza:
    def test_stessi_argomenti_stesso_risultato(self) -> None:
        c1 = c(10, 15, 5, 12)
        c0 = c(13, 16, 9, 11)
        risultati = {d.bias_timeframe(c0, c1) for _ in range(50)}
        assert len(risultati) == 1

    def test_le_candele_sono_immutabili(self) -> None:
        candela = c(10, 15, 5, 12)
        with pytest.raises(Exception):
            candela.chiusura = 99          # type: ignore[misc]

    def test_nessun_accesso_a_rete_o_disco(self) -> None:
        """definizioni.py non deve importare nulla che tocchi il mondo esterno."""
        import ast

        albero = ast.parse(open("core/definizioni.py", encoding="utf-8").read())
        moduli: set[str] = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                moduli.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                moduli.add(nodo.module.split(".")[0])
        vietati = {"httpx", "requests", "socket", "urllib", "sqlite3", "os", "pathlib", "time"}
        assert not (moduli & vietati), moduli & vietati


# ===========================================================================
# ESCL-15 b — ATR, unita' di misura e nient'altro
# ===========================================================================
class TestAtr:
    """*"ATR(14), ammesso ESCLUSIVAMENTE come unita' di misura per
    normalizzare distanze. L'ATR non puo' mai generare un segnale, filtrare un
    ingresso, determinare uno stop ne' dimensionare una posizione."*

    Il divieto lo fa rispettare il posto da cui si chiama, non questa
    funzione. Oggi la chiamata di produzione e' una sola: il `rapporto` di
    07_casi.md §3.1, che finisce in archivio e non tocca alcuna decisione.
    """

    @staticmethod
    def serie(quante: int, alto: float = 102.0, basso: float = 98.0):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            Candela(base + timedelta(hours=i), 100.0, alto, basso, 100.0)
            for i in range(quante)
        ]

    def test_su_candele_identiche_e_l_escursione(self) -> None:
        assert d.atr(self.serie(20)) == pytest.approx(4.0)

    def test_storia_insufficiente_da_none(self) -> None:
        """Servono periodo + 1 candele: il primo True Range ha bisogno della
        chiusura precedente. Un ATR su meno storia di quella dichiarata
        sarebbe un numero diverso col nome di questo."""
        assert d.atr(self.serie(14)) is None
        assert d.atr(self.serie(15)) is not None

    def test_il_gap_di_apertura_entra_nel_true_range(self) -> None:
        """E' la ragione per cui Wilder usa il True Range e non il range:
        una candela stretta che apre lontano ha comunque escursione vera."""
        candele = self.serie(15)
        base = candele[-1].orario + timedelta(hours=1)
        # Candela stretta (range 1) ma 20 punti sopra la chiusura precedente.
        candele.append(Candela(base, 120.0, 121.0, 120.0, 120.5))
        stretta = d.atr(candele[-15:])
        assert stretta is not None and stretta > 4.0

    def test_non_dipende_da_quanta_storia_le_si_da(self) -> None:
        """Media semplice, non esponenziale: due archivi di lunghezza diversa
        danno lo stesso numero sullo stesso periodo finale. Per un
        denominatore che deve rendere confrontabili strumenti e timeframe
        diversi e' la proprieta' che conta di piu'."""
        lunga = self.serie(200)
        assert d.atr(lunga) == pytest.approx(d.atr(lunga[-15:]))
