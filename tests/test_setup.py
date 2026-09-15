"""Collaudo di core/setup.py, regola per regola di `docs/03_setup.md`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import setup as s
from core.definizioni import Bias, Candela, Gap, KeyLevel, Mitigazione, Polarita, TipoKeyLevel
from core.parametri import TF

INIZIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def c(apertura: float, massimo: float, minimo: float, chiusura: float, giorni: int = 0) -> Candela:
    return Candela(INIZIO + timedelta(days=giorni), apertura, massimo, minimo, chiusura)


def kl_max(valore: float, tf: TF = TF.W1) -> KeyLevel:
    return KeyLevel(tf, TipoKeyLevel.MAX, valore)


def kl_min(valore: float, tf: TF = TF.W1) -> KeyLevel:
    return KeyLevel(tf, TipoKeyLevel.MIN, valore)


# Un CRT short da manuale, riusato in mezzo file.
#   N1 range 100-110, chiusura 105
#   N2 buca il key level a 112, arriva a 115, richiude a 103 dentro N1 e sotto 105
N1_SHORT = c(102, 110, 100, 105)
N2_SHORT = c(108, 115, 101, 103, giorni=1)

# E il suo speculare long.
N1_LONG = c(108, 110, 100, 105)
N2_LONG = c(102, 109, 95, 107, giorni=1)


# ===========================================================================
# SETUP-00, SETUP-02 — il CRT e il suo vincolo fondamentale
# ===========================================================================
class TestCrt:
    def test_setup02a_crt_short(self) -> None:
        crt = s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112))
        assert crt is not None
        assert crt.direzione is Bias.SHORT
        assert crt.tf is TF.D1
        assert crt.key_level.valore == 112

    def test_setup02b_crt_long(self) -> None:
        crt = s.crt_long(N1_LONG, N2_LONG, TF.D1, kl_min(98))
        assert crt is not None and crt.direzione is Bias.LONG

    def test_setup02a_servono_tutte_e_quattro_le_condizioni(self) -> None:
        livello = kl_max(112)
        # non prende il key level: massimo 111 sotto 112
        assert s.crt_short(N1_SHORT, c(108, 111, 101, 103, 1), TF.D1, livello) is None
        # non supera il massimo di N1: impossibile senza prendere il KL, quindi
        # abbasso il key level per isolare la seconda condizione
        assert s.crt_short(N1_SHORT, c(105, 109, 101, 103, 1), TF.D1, kl_max(108)) is None
        # non richiude dentro N1: chiusura 112 sopra il massimo di N1
        assert s.crt_short(N1_SHORT, c(108, 115, 101, 112, 1), TF.D1, livello) is None
        # chiude sopra la chiusura di N1: 106 > 105
        assert s.crt_short(N1_SHORT, c(108, 115, 101, 106, 1), TF.D1, livello) is None

    def test_setup02_terza_condizione_implicata_dalla_quarta(self) -> None:
        """REV-45: nessun test puo' distinguere `<=` da `<` nella terza.

        `close[N1] <= high[N1]` vale per costruzione, quindi da
        `close[N2] < close[N1]` segue `close[N2] < high[N1]`. La terza
        condizione di SETUP-02A non puo' mai essere l'unica a fallire.
        Questo test lo dimostra invece di lasciarlo credere, e spiega perche'
        una mutazione su quel confronto sopravvive ai test.
        """
        passo = 0.5
        valori = [x * passo for x in range(21)]
        for h1 in valori:
            for c1 in valori:
                if c1 > h1:
                    continue                       # candela impossibile
                for c2 in valori:
                    if c2 < c1:                    # quarta condizione vera
                        assert c2 <= h1, "la terza deve essere vera di conseguenza"

        # A specchio su SETUP-02B.
        for l1 in valori:
            for c1 in valori:
                if c1 < l1:
                    continue
                for c2 in valori:
                    if c2 > c1:
                        assert c2 >= l1

    def test_setup00_senza_key_level_nessun_crt(self) -> None:
        """Il vincolo fondamentale: nessuna forma di candele basta da sola."""
        assert s.cerca_crt(N1_SHORT, N2_SHORT, TF.D1, []) is None

    def test_setup02_il_tipo_di_key_level_conta(self) -> None:
        """Un CRT short reagisce a un massimo preso, non a un minimo."""
        assert s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_min(112)) is None
        assert s.crt_long(N1_LONG, N2_LONG, TF.D1, kl_max(98)) is None

    def test_setup02_key_level_deve_stare_piu_in_alto(self) -> None:
        """Un key level giornaliero non abilita un CRT giornaliero."""
        assert s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.D1)) is None
        assert s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.H4)) is None
        assert s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.M1)) is not None

    def test_cerca_crt_preferisce_il_timeframe_piu_alto(self) -> None:
        """PREC-02: fra due key level presi comanda quello piu' alto."""
        crt = s.cerca_crt(N1_SHORT, N2_SHORT, TF.D1, [kl_max(112, TF.W1), kl_max(111, TF.M3)])
        assert crt is not None and crt.key_level.tf is TF.M3


# ===========================================================================
# DEF-30, SETUP-10 — dove puo' nascere un CRT
# ===========================================================================
class TestTimeframeCrt:
    def test_key_level_strettamente_superiore(self) -> None:
        assert s.timeframe_crt_ammesso(TF.D1, TF.W1) is True
        assert s.timeframe_crt_ammesso(TF.D1, TF.D1) is False
        assert s.timeframe_crt_ammesso(TF.W1, TF.D1) is False

    def test_col_gap_lo_stesso_timeframe_e_ammesso(self) -> None:
        """SETUP-10: per i gap si', per i key level no. Sono due regole diverse."""
        assert s.timeframe_crt_ammesso(TF.D1, TF.M1, tf_gap=TF.D1) is True
        assert s.timeframe_crt_ammesso(TF.H4, TF.M1, tf_gap=TF.D1) is True
        assert s.timeframe_crt_ammesso(TF.W1, TF.M1, tf_gap=TF.D1) is False

    def test_rev11_niente_crt_su_h12_e_h6(self) -> None:
        assert s.timeframe_crt_ammesso(TF.H12, TF.W1) is False
        assert s.timeframe_crt_ammesso(TF.H6, TF.W1, tf_gap=TF.W1) is False

    def test_crt_su_h12_non_si_forma_nemmeno(self) -> None:
        assert s.crt_short(N1_SHORT, N2_SHORT, TF.H12, kl_max(112)) is None


# ===========================================================================
# SETUP-06, SETUP-07, SETUP-08 — bias di comando e reversal
# ===========================================================================
class TestBiasComando:
    def test_setup06_primo_timeframe_utile(self) -> None:
        bias, tf = s.bias_comando(
            {TF.M12: Bias.NESSUNA, TF.M6: Bias.SHORT, TF.M1: Bias.LONG},
            {},
        )
        assert (bias, tf) == (Bias.SHORT, TF.M6)

    def test_setup06_target_raggiunto_scavalca(self) -> None:
        bias, tf = s.bias_comando(
            {TF.M12: Bias.LONG, TF.M6: Bias.SHORT},
            {TF.M12: True},
        )
        assert (bias, tf) == (Bias.SHORT, TF.M6), "il 12M ha finito, comanda il 6M"

    def test_setup06_ordine_esatto(self) -> None:
        """Il 12M comanda sempre sul 6M, anche se entrambi sono definiti."""
        bias, tf = s.bias_comando({TF.M12: Bias.LONG, TF.M6: Bias.SHORT}, {})
        assert tf is TF.M12

    def test_setup06_non_scende_sotto_il_giornaliero(self) -> None:
        """L'elenco di SETUP-06 si ferma a TF_1D."""
        bias, tf = s.bias_comando({TF.H4: Bias.LONG, TF.H1: Bias.LONG}, {})
        assert (bias, tf) == (Bias.NESSUNA, None)

    def test_setup06_nessun_timeframe_utile(self) -> None:
        assert s.bias_comando({}, {}) == (Bias.NESSUNA, None)
        assert s.bias_comando({TF.M12: Bias.LONG}, {TF.M12: True}) == (Bias.NESSUNA, None)

    def test_setup07_divieto_di_reversal(self) -> None:
        assert s.direzione_concorde(Bias.SHORT, Bias.SHORT) is True
        assert s.direzione_concorde(Bias.LONG, Bias.SHORT) is False

    def test_setup07_senza_comando_nulla_e_concorde(self) -> None:
        assert s.direzione_concorde(Bias.LONG, Bias.NESSUNA) is False

    def test_setup08_reversal_solo_dopo_il_target(self) -> None:
        assert s.reversal_ammesso(target_tf_comando_raggiunto=False) is False
        assert s.reversal_ammesso(target_tf_comando_raggiunto=True) is True


# ===========================================================================
# SETUP-05 — allineamento
# ===========================================================================
class TestAllineamento:
    """SETUP-05, con la direzione dello SPAZZAMENTO (REV-46).

    Una short nasce da un massimo preso verso l'alto: i due timeframe
    superiori devono aver sbilanciato LONG, e l'operazione e' la reazione
    contraria. Le fixture di queste prove prima costruivano lo stato opposto,
    che la catena reale non puo' produrre — ed e' per questo che passavano
    mentre il motore, sui prezzi veri, non operava mai.
    """

    def test_setup05_servono_entrambi_i_superiori(self) -> None:
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: Bias.LONG, TF.D1: Bias.LONG}, Bias.SHORT
        ) is True, "massimi spazzati in alto da entrambi: si cerca la short"
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: Bias.LONG}, Bias.SHORT
        ) is False, "uno solo non basta"

    def test_setup05_devono_essere_nella_stessa_direzione(self) -> None:
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: Bias.LONG, TF.D1: Bias.SHORT}, Bias.SHORT
        ) is False

    def test_setup05_lo_sbilanciamento_concorde_all_operazione_non_vale(self) -> None:
        """CASO CRITICO: e' la lettura che ha tenuto fermo il motore.

        Chiedere che lo sbilanciamento coincida con la direzione
        dell'operazione e' autocontraddittorio, perche' il timeframe che
        genera il key level lo spazza sempre nel verso opposto. Misurato sui
        prezzi reali: zero occorrenze su 298 candidati in ventisei anni.
        """
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: Bias.SHORT, TF.D1: Bias.SHORT}, Bias.SHORT
        ) is False
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: Bias.LONG, TF.D1: Bias.LONG}, Bias.LONG
        ) is False

    def test_setup05_lo_spazzamento_e_sempre_l_opposto(self) -> None:
        assert s.direzione_dello_spazzamento(Bias.SHORT) is Bias.LONG
        assert s.direzione_dello_spazzamento(Bias.LONG) is Bias.SHORT

    def test_setup05_il_crt_produce_davvero_lo_stato_richiesto(self) -> None:
        """La prova che le fixture da sole non davano: si parte dal CRT.

        Si costruisce un CRT short vero, si guarda in che direzione DEF-38
        registra la presa del suo key level, e si verifica che quello sia
        esattamente lo stato che SETUP-05 pretende. E' il collegamento fra le
        due regole che mancava.
        """
        from core.definizioni import Candela, KeyLevel, Presa, TipoKeyLevel, presa_key_level
        from datetime import datetime, timezone

        def c(o, a, b, ch, giorno):
            return Candela(datetime(2026, 3, giorno, tzinfo=timezone.utc), o, a, b, ch)

        livello = KeyLevel(TF.D1, TipoKeyLevel.MAX, 100.0)
        n1 = c(95.0, 99.0, 94.0, 98.0, 10)
        n2 = c(98.0, 101.0, 95.0, 96.0, 11)          # spazza 100, richiude sotto
        crt = s.crt_short(n1, n2, TF.H1, livello)
        assert crt is not None, "il CRT deve formarsi, altrimenti la prova non dice nulla"

        presa = presa_key_level(n2, livello)
        assert presa is Presa.RIALZO, "il massimo e' stato preso verso l'alto"
        sbilanciamento = Bias.LONG if presa is Presa.RIALZO else Bias.SHORT
        assert sbilanciamento is not crt.direzione, (
            "lo sbilanciamento e' l'opposto dell'operazione: e' il motivo per cui "
            "la lettura letterale di SETUP-05 non puo' mai essere vera"
        )
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H4: sbilanciamento, TF.D1: sbilanciamento}, crt.direzione
        ) is True

    def test_setup05_salta_h12_e_h6(self) -> None:
        """Sopra TF_H1 stanno TF_H4 e TF_1D, non TF_H6 e TF_H12."""
        assert s.allineamento_soddisfatto(
            TF.H1, {TF.H6: Bias.SHORT, TF.H12: Bias.SHORT}, Bias.SHORT
        ) is False

    def test_setup05_non_definito_per_h12_h6_e_12m(self) -> None:
        """REV-11: e' la ragione tecnica per cui li' non nasce un CRT."""
        assert s.allineamento_soddisfatto(TF.H12, {}, Bias.SHORT) is False
        assert s.allineamento_soddisfatto(TF.M12, {}, Bias.SHORT) is False

    def test_setup05_catena_completa(self) -> None:
        assert s.allineamento_soddisfatto(
            TF.D1, {TF.W1: Bias.SHORT, TF.M1: Bias.SHORT}, Bias.LONG
        ) is True, "minimi spazzati in basso da entrambi: si cerca la long"


# ===========================================================================
# SETUP-19 — direzione dal DXY
# ===========================================================================
class TestDirezioneDxy:
    def test_setup19_dxy_long_vende_le_coppie_dirette(self) -> None:
        assert s.direzione_da_dxy(Bias.LONG, "EURUSD") is Bias.SHORT
        assert s.direzione_da_dxy(Bias.LONG, "GBPUSD") is Bias.SHORT
        assert s.direzione_da_dxy(Bias.LONG, "AUDUSD") is Bias.SHORT

    def test_setup19_dxy_long_compra_le_coppie_col_dollaro_davanti(self) -> None:
        assert s.direzione_da_dxy(Bias.LONG, "USDJPY") is Bias.LONG
        assert s.direzione_da_dxy(Bias.LONG, "USDCHF") is Bias.LONG

    def test_setup19_speculare(self) -> None:
        for coppia in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF"):
            su = s.direzione_da_dxy(Bias.LONG, coppia)
            giu = s.direzione_da_dxy(Bias.SHORT, coppia)
            assert su is not None and giu is not None and su is not giu

    def test_setup19_oro_non_deriva_dal_dxy(self) -> None:
        """PRIN-09 e PA-05: l'oro ha bias propria via SETUP-06 su GC."""
        assert s.direzione_da_dxy(Bias.LONG, "XAUUSD") is None
        assert s.direzione_da_dxy(Bias.SHORT, "XAUUSD") is None

    def test_setup19_dxy_senza_bias_nessuna_operazione(self) -> None:
        assert s.direzione_da_dxy(Bias.NESSUNA, "EURUSD") is None

    def test_setup19_strumento_fuori_universo(self) -> None:
        with pytest.raises(ValueError):
            s.direzione_da_dxy(Bias.LONG, "BTCUSD")

    def test_doppia_trasformazione_su_usdjpy(self) -> None:
        """SETUP-19 piu' DEF-33: l'esempio scritto nel documento.

        DXY LONG -> USDJPY va BUY. Sul future 6J, che ha segno invertito, il
        CRT da cercare e' short. Sono due trasformazioni indipendenti.
        """
        from core.definizioni import direzione_cfd

        ordine_cfd = s.direzione_da_dxy(Bias.LONG, "USDJPY")
        assert ordine_cfd is Bias.LONG
        crt_sul_future = Bias.SHORT
        assert direzione_cfd(crt_sul_future, "USDJPY") is ordine_cfd


# ===========================================================================
# SETUP-09, SETUP-10 — gap
# ===========================================================================
class TestGap:
    def test_setup09_solo_in_fase_3(self) -> None:
        for fase in (0, 1, 2, 4):
            ammesso, blocchi = s.ingresso_da_gap_ammesso(fase, Mitigazione.ATTESA)
            assert ammesso is False and "SETUP-09" in blocchi
        assert s.ingresso_da_gap_ammesso(3, Mitigazione.ATTESA)[0] is True

    def test_setup09_mitigazione_non_determinata_blocca(self) -> None:
        ammesso, blocchi = s.ingresso_da_gap_ammesso(3, Mitigazione.NON_DETERMINATA)
        assert ammesso is False and "DEF-42" in blocchi

    def test_setup09_entrambi_i_motivi_riportati(self) -> None:
        _, blocchi = s.ingresso_da_gap_ammesso(1, Mitigazione.NON_DETERMINATA)
        assert set(blocchi) == {"SETUP-09", "DEF-42"}

    def test_setup10_doppio_ingresso(self) -> None:
        crt = s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.M1))
        assert crt is not None
        gap_pari = Gap(Polarita.RIBASSISTA, 100, 110, 120, TF.D1, INIZIO)
        gap_sopra = Gap(Polarita.RIBASSISTA, 100, 110, 120, TF.W1, INIZIO)
        gap_sotto = Gap(Polarita.RIBASSISTA, 100, 110, 120, TF.H4, INIZIO)
        assert s.doppio_ingresso(crt, gap_pari) is True
        assert s.doppio_ingresso(crt, gap_sopra) is True
        assert s.doppio_ingresso(crt, gap_sotto) is False, "il CRT sta sopra il gap"

    def test_setup10_senza_gap_ingresso_unico(self) -> None:
        crt = s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.M1))
        assert crt is not None
        assert s.doppio_ingresso(crt, None) is False


# ===========================================================================
# SETUP-15 — esclusioni
# ===========================================================================
class TestEsclusioni:
    def base(self, **modifiche: object) -> dict:
        crt = s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.M1))
        argomenti: dict = {
            "crt": crt,
            "comando": Bias.SHORT,
            "key_level_preso": True,
            # Il CRT di base e' short, quindi nasce da massimi spazzati verso
            # l'alto: i due superiori devono risultare LONG (REV-46).
            "sbilanciamenti": {TF.W1: Bias.LONG, TF.M1: Bias.LONG},
            "posizioni_aperte_strumento": 0,
            "limite_rischio_raggiunto": False,
            "dentro_finestra_news": False,
            "dati_coerenti": True,
        }
        argomenti.update(modifiche)
        return argomenti

    def test_setup_pulito_non_viola_nulla(self) -> None:
        assert s.esclusioni_setup(**self.base()) == ()

    def test_senza_key_level(self) -> None:
        assert "SETUP-00" in s.esclusioni_setup(**self.base(key_level_preso=False))

    def test_senza_bias_comando(self) -> None:
        violate = s.esclusioni_setup(**self.base(comando=Bias.NESSUNA))
        assert "SETUP-06" in violate and "SETUP-07" in violate

    def test_direzione_opposta_al_comando(self) -> None:
        assert "SETUP-07" in s.esclusioni_setup(**self.base(comando=Bias.LONG))

    def test_allineamento_mancante(self) -> None:
        assert "SETUP-05" in s.esclusioni_setup(**self.base(sbilanciamenti={}))

    def test_quattro_posizioni_gia_aperte(self) -> None:
        assert "RISK-06" in s.esclusioni_setup(**self.base(posizioni_aperte_strumento=4))
        assert "RISK-06" not in s.esclusioni_setup(**self.base(posizioni_aperte_strumento=3))

    def test_limite_di_rischio(self) -> None:
        assert "RISK-07" in s.esclusioni_setup(**self.base(limite_rischio_raggiunto=True))

    def test_finestra_news(self) -> None:
        assert "RISK-13" in s.esclusioni_setup(**self.base(dentro_finestra_news=True))

    def test_dato_incoerente(self) -> None:
        assert "PRIN-99" in s.esclusioni_setup(**self.base(dati_coerenti=False))

    def test_mitigazione_solo_sugli_ingressi_da_gap(self) -> None:
        senza_gap = s.esclusioni_setup(
            **self.base(da_gap=False, mitigazione=Mitigazione.NON_DETERMINATA)
        )
        assert "DEF-42" not in senza_gap
        con_gap = s.esclusioni_setup(
            **self.base(da_gap=True, mitigazione=Mitigazione.NON_DETERMINATA)
        )
        assert "DEF-42" in con_gap

    def test_piu_violazioni_tutte_riportate(self) -> None:
        """Quando non si opera si deve poter dire quali regole l'hanno impedito."""
        violate = s.esclusioni_setup(
            **self.base(
                key_level_preso=False,
                limite_rischio_raggiunto=True,
                dentro_finestra_news=True,
            )
        )
        assert {"SETUP-00", "RISK-07", "RISK-13"} <= set(violate)


# ===========================================================================
# SETUP-04, SETUP-11, SETUP-16 — vita del setup
# ===========================================================================
class TestVitaDelSetup:
    def test_setup16_un_setup_saltato_non_torna(self) -> None:
        assert s.setup_recuperabile() is False

    def test_setup11_lo_stop_non_brucia_i_timeframe(self) -> None:
        assert s.nuovo_ingresso_dopo_stop(TF.D1, TF.H1) is True
        assert s.nuovo_ingresso_dopo_stop(TF.H1, TF.H1) is True, "AMM-02"


# ===========================================================================
# GIUD-01 — punto di giudizio
# ===========================================================================
class TestGiudizio:
    def test_giud01_e_sempre_ambiguo_finche_manca_pa44(self) -> None:
        categoria, motivo = s.giud01_scelta_target(distanza_kl_gap=50.0, atr_tf=20.0)
        assert categoria == s.CategoriaGiudizio.AMBIGUO
        assert "PA-44" in motivo

    def test_giud01_non_cambia_coi_dati(self) -> None:
        """Nessuna soglia inventata: vicino o lontano, la risposta e' la stessa."""
        vicino = s.giud01_scelta_target(distanza_kl_gap=1.0, atr_tf=100.0)
        lontano = s.giud01_scelta_target(distanza_kl_gap=1000.0, atr_tf=1.0)
        assert vicino[0] == lontano[0] == s.CategoriaGiudizio.AMBIGUO

    def test_rapporto_registrato_per_chiudere_pa44(self) -> None:
        assert s.rapporto_giud01(50.0, 20.0) == pytest.approx(2.5)

    def test_rapporto_senza_atr_e_none(self) -> None:
        """Un rapporto inventato inquinerebbe i dati che servono a PA-44."""
        assert s.rapporto_giud01(50.0, 0.0) is None


# ===========================================================================
# Purezza
# ===========================================================================
class TestPurezza:
    def test_nessun_accesso_a_rete_o_disco(self) -> None:
        import ast

        albero = ast.parse(open("core/setup.py", encoding="utf-8").read())
        moduli: set[str] = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                moduli.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                moduli.add(nodo.module.split(".")[0])
        vietati = {"httpx", "requests", "socket", "urllib", "sqlite3", "os", "pathlib", "time"}
        assert not (moduli & vietati), moduli & vietati

    def test_il_crt_e_immutabile(self) -> None:
        crt = s.crt_short(N1_SHORT, N2_SHORT, TF.D1, kl_max(112, TF.M1))
        assert crt is not None
        with pytest.raises(Exception):
            crt.direzione = Bias.LONG      # type: ignore[misc]
