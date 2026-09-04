"""Collaudo di core/rischio.py e core/gestione.py."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core import gestione as g
from core import rischio as r
from core.definizioni import Bias, Candela, Gap, KeyLevel, Polarita, TipoKeyLevel
from core.gestione import Posizione
from core.parametri import TF

INIZIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def posizione(**modifiche: object) -> Posizione:
    argomenti: dict = {
        "strumento": "EURUSD",
        "direzione": Bias.SHORT,
        "prezzo_ingresso": 1.1000,
        "tf_crt": TF.H4,
        "livello_stop": 1.1050,
        "tp1": 1.0950,
        "target_finale": 1.0800,
    }
    argomenti.update(modifiche)
    return Posizione(**argomenti)


# ===========================================================================
# RISK-02, REV-03 — gruppi di correlazione
# ===========================================================================
class TestGruppi:
    def test_le_coppie_forex_sono_un_gruppo_unico(self) -> None:
        aperte = {"EURUSD": 1, "GBPUSD": 2}
        assert r.posizioni_nel_gruppo("AUDUSD", aperte) == 3

    def test_l_oro_e_un_gruppo_a_se(self) -> None:
        aperte = {"EURUSD": 3, "XAUUSD": 1}
        assert r.posizioni_nel_gruppo("XAUUSD", aperte) == 1
        assert r.posizioni_nel_gruppo("EURUSD", aperte) == 3

    def test_rischio_del_prossimo_ordine_conta_anche_quello(self) -> None:
        assert r.rischio_del_prossimo_ordine("EURUSD", {}) == 0.0100
        assert r.rischio_del_prossimo_ordine("EURUSD", {"GBPUSD": 1}) == 0.0075
        assert r.rischio_del_prossimo_ordine("EURUSD", {"GBPUSD": 2}) == 0.0045

    def test_esposizione_col_ridimensionamento(self) -> None:
        """REV-42: tutte le posizioni del gruppo rischiano la stessa percentuale."""
        assert r.esposizione_del_gruppo("EURUSD", {"GBPUSD": 3}) == pytest.approx(0.018)

    def test_l_oro_si_ferma_a_1_80_e_non_arriva_a_4(self) -> None:
        """REV-03: e' la ragione per cui la scala si applica anche all'oro."""
        quattro = r.esposizione_del_gruppo("XAUUSD", {"XAUUSD": 3})
        assert quattro == pytest.approx(0.018)
        from core.parametri import LIMITE_GIORNALIERO
        assert quattro < LIMITE_GIORNALIERO

    def test_tetto_posizioni(self) -> None:
        assert r.tetto_posizioni_raggiunto(3) is False
        assert r.tetto_posizioni_raggiunto(4) is True


# ===========================================================================
# RISK-03, DEF-47 — la size
# ===========================================================================
class TestSize:
    def base(self, **modifiche: object) -> dict:
        argomenti: dict = {
            "equity": 10000.0,
            "strumento": "EURUSD",
            "chiusura_n2_future": 1.1000,
            "stop_future": 1.1055,          # 0.5% sopra
            "prezzo_cfd": 1.1000,
            "valore_punto": 10.0,           # 1 punto per 1 lotto
            "passo_broker": 0.01,
            "posizioni_aperte_per_strumento": {},
        }
        argomenti.update(modifiche)
        return argomenti

    def test_size_calcolata(self) -> None:
        esito = r.calcola_size(**self.base())
        assert esito.lotti is not None and esito.lotti > 0
        assert esito.rischio_percentuale == 0.0100
        assert esito.distanza_relativa == pytest.approx(0.005, rel=1e-3)

    def test_size_scende_se_lo_stop_e_piu_largo(self) -> None:
        stretto = r.calcola_size(**self.base(stop_future=1.1011))
        largo = r.calcola_size(**self.base(stop_future=1.1220))
        assert stretto.lotti is not None and largo.lotti is not None
        assert stretto.lotti > largo.lotti

    def test_size_scende_col_numero_di_posizioni(self) -> None:
        sola = r.calcola_size(**self.base())
        terza = r.calcola_size(**self.base(posizioni_aperte_per_strumento={"GBPUSD": 2}))
        assert sola.lotti is not None and terza.lotti is not None
        assert terza.lotti < sola.lotti

    def test_risk04_doppio_ingresso_dimezza(self) -> None:
        """Due ingressi da meta' rischio, non due a rischio pieno."""
        singolo = r.calcola_size(**self.base())
        doppio = r.calcola_size(**self.base(doppio_ingresso=True))
        assert singolo.lotti is not None and doppio.lotti is not None
        assert doppio.rischio_percentuale == pytest.approx(singolo.rischio_percentuale / 2)
        assert doppio.lotti == pytest.approx(singolo.lotti / 2, rel=0.02)

    def test_risk03_arrotondamento_sempre_per_difetto(self) -> None:
        assert r._arrotonda_per_difetto(0.239, 0.01) == pytest.approx(0.23)
        assert r._arrotonda_per_difetto(0.999, 0.01) == pytest.approx(0.99)
        assert r._arrotonda_per_difetto(0.009, 0.01) == 0.0

    def test_risk03_se_l_arrotondamento_da_zero_non_si_opera(self) -> None:
        # equity 1, rischio 1% = 0.01 EUR: bastano 0.18 lotti, il passo e' 1.
        esito = r.calcola_size(**self.base(equity=1.0, passo_broker=1.0))
        assert esito.lotti is None and "RISK-03" in esito.motivo
        assert esito.distanza_relativa is not None, "la distanza si calcola comunque"

    def test_risk03_distanza_nulla_e_incoerente(self) -> None:
        esito = r.calcola_size(**self.base(stop_future=1.1000))
        assert esito.lotti is None and "PRIN-99" in esito.motivo

    def test_dati_non_validi(self) -> None:
        assert r.calcola_size(**self.base(equity=0)).lotti is None
        assert r.calcola_size(**self.base(valore_punto=0)).lotti is None
        assert r.calcola_size(**self.base(prezzo_cfd=0)).lotti is None

    def test_pa62_funziona_sulle_scale_incomparabili(self) -> None:
        """6J quota 0.0068, USDJPY 147: nessun fattore k costante li lega.

        Con la distanza relativa la stessa percentuale di stop produce la
        stessa frazione di rischio, qualunque sia la scala del future.
        """
        su_eurusd = r.calcola_size(**self.base(
            strumento="EURUSD", chiusura_n2_future=1.1000, stop_future=1.1110, prezzo_cfd=1.1000,
        ))
        su_usdjpy = r.calcola_size(**self.base(
            strumento="USDJPY", chiusura_n2_future=0.0068, stop_future=0.0068 * 1.01,
            prezzo_cfd=147.0, valore_punto=10.0 / 147.0,
        ))
        assert su_eurusd.distanza_relativa == pytest.approx(0.01, rel=1e-3)
        assert su_usdjpy.distanza_relativa == pytest.approx(0.01, rel=1e-3)
        assert su_eurusd.lotti is not None and su_usdjpy.lotti is not None

    def test_pa63_ridimensionamento_non_eseguibile(self) -> None:
        assert r.ridimensionamento_eseguibile(0.005, 0.01) is False
        assert r.ridimensionamento_eseguibile(0.05, 0.01) is True


# ===========================================================================
# RISK-05 — selezione degli strumenti
# ===========================================================================
class TestSelezione:
    def test_risk05_la_bias_dxy_abilita_non_obbliga(self) -> None:
        """L'esempio del documento: DXY LONG, EURUSD con setup, GBPUSD senza."""
        assert r.strumento_eleggibile("EURUSD", "SHORT", True, "SHORT") is True
        assert r.strumento_eleggibile("GBPUSD", "SHORT", False, None) is False

    def test_risk05_setup_nella_direzione_sbagliata(self) -> None:
        assert r.strumento_eleggibile("EURUSD", "SHORT", True, "LONG") is False

    def test_risk05_oro_non_confronta_col_dxy(self) -> None:
        assert r.strumento_eleggibile("XAUUSD", None, True, "LONG") is True
        assert r.strumento_eleggibile("XAUUSD", None, False, None) is False

    def test_risk05_strumento_fuori_universo(self) -> None:
        with pytest.raises(ValueError):
            r.strumento_eleggibile("BTCUSD", "SHORT", True, "SHORT")


# ===========================================================================
# RISK-07, RISK-08, RISK-09 — limiti di perdita
# ===========================================================================
class TestLimiti:
    def base(self, **modifiche: object) -> dict:
        argomenti: dict = {
            "pnl_giornaliero": 0.0, "equity_inizio_giornata": 10000.0,
            "pnl_settimanale": 0.0, "equity_inizio_settimana": 10000.0,
            "pnl_mensile": 0.0, "equity_inizio_mese": 10000.0,
        }
        argomenti.update(modifiche)
        return argomenti

    def test_nessun_limite_in_pari(self) -> None:
        assert r.limiti_raggiunti(**self.base()) == ()

    def test_risk07_giornaliero(self) -> None:
        raggiunti = r.limiti_raggiunti(**self.base(pnl_giornaliero=-300.0))
        assert [l.regola for l in raggiunti] == ["RISK-07"]

    def test_risk07_soglia_esatta(self) -> None:
        """`<= -3.00%`: sulla soglia il limite e' raggiunto."""
        assert r.limiti_raggiunti(**self.base(pnl_giornaliero=-300.0)) != ()
        assert r.limiti_raggiunti(**self.base(pnl_giornaliero=-299.0)) == ()

    def test_tre_stop_pieni_esauriscono_la_giornata(self) -> None:
        """La nota di CTX-09: al rischio dell'1%, tre stop pieni fanno il 3%."""
        assert r.limiti_raggiunti(**self.base(pnl_giornaliero=-100.0 * 3)) != ()

    def test_limiti_multipli(self) -> None:
        raggiunti = r.limiti_raggiunti(**self.base(
            pnl_giornaliero=-400.0, pnl_settimanale=-700.0, pnl_mensile=-1100.0,
        ))
        assert {l.regola for l in raggiunti} == {"RISK-07", "RISK-08", "RISK-09"}

    def test_un_utile_non_e_un_limite(self) -> None:
        assert r.limiti_raggiunti(**self.base(pnl_giornaliero=5000.0)) == ()

    def test_risk11_stop_obbligatorio(self) -> None:
        assert r.stop_obbligatorio(None) is False
        assert r.stop_obbligatorio(1.1050) is True


# ===========================================================================
# GEST-02, GEST-07 — stop e TP1
# ===========================================================================
class TestStopETp1:
    N1 = Candela(INIZIO, 1.1000, 1.1100, 1.0900, 1.1050)
    N2 = Candela(INIZIO, 1.1050, 1.1150, 1.1000, 1.1020)

    def test_gest02_stop_aggressivo(self) -> None:
        assert g.stop_aggressivo(self.N2, Bias.SHORT) == 1.1150
        assert g.stop_aggressivo(self.N2, Bias.LONG) == 1.1000

    def test_gest02_stop_conservativo(self) -> None:
        gap = Gap(Polarita.RIBASSISTA, 1.1200, 1.1300, 1.1400, TF.W1, INIZIO)
        assert g.stop_conservativo(gap, Bias.SHORT) == 1.1300
        assert g.stop_conservativo(gap, Bias.LONG) == 1.1200

    def test_gest07_tp1_e_meta_di_n1(self) -> None:
        assert g.tp1(self.N1) == pytest.approx(1.1000)

    def test_gest04_raggiungimento_tp1(self) -> None:
        corta = posizione(tp1=1.0950)
        assert g.raggiunge_tp1(corta, 1.0960) is False
        assert g.raggiunge_tp1(corta, 1.0950) is True
        lunga = posizione(direzione=Bias.LONG, tp1=1.1050, livello_stop=1.0950)
        assert g.raggiunge_tp1(lunga, 1.1050) is True

    def test_gest04_tp1_non_scatta_due_volte(self) -> None:
        gia_fatto = posizione(tp1_raggiunto=True)
        assert g.raggiunge_tp1(gia_fatto, 1.0000) is False

    def test_gest04_chiude_un_quarto_e_va_a_break_even(self) -> None:
        nuova, chiusa = g.applica_tp1(posizione(), spread=0.0001)
        assert chiusa == pytest.approx(0.25)
        assert nuova.frazione_residua == pytest.approx(0.75)
        assert nuova.tp1_raggiunto is True
        assert nuova.livello_stop == pytest.approx(1.1000 - 0.0002)

    def test_pa46_il_buffer_e_un_multiplo_dello_spread(self) -> None:
        largo = g.livello_break_even(1.1000, Bias.SHORT, spread=0.0005)
        stretto = g.livello_break_even(1.1000, Bias.SHORT, spread=0.0001)
        assert largo < stretto, "piu' spread, break even piu' prudente"

    def test_break_even_dal_lato_giusto(self) -> None:
        assert g.livello_break_even(1.1000, Bias.LONG, 0.0002) > 1.1000
        assert g.livello_break_even(1.1000, Bias.SHORT, 0.0002) < 1.1000


# ===========================================================================
# GEST-03, GEST-05, ESCL-07/08/09 — lo stop non si muove
# ===========================================================================
class TestStopImmobile:
    def test_gest03_niente_spostamenti_prima_di_tp1(self) -> None:
        ammesso, motivo = g.spostamento_stop_ammesso(posizione(), 1.1020)
        assert ammesso is False and "GEST-03" in motivo

    def test_escl07_mai_allargare(self) -> None:
        corta = posizione(tp1_raggiunto=True, livello_stop=1.1000)
        ammesso, motivo = g.spostamento_stop_ammesso(corta, 1.1100)
        assert ammesso is False and "ESCL-07" in motivo
        lunga = posizione(direzione=Bias.LONG, tp1_raggiunto=True, livello_stop=1.1000)
        ammesso, motivo = g.spostamento_stop_ammesso(lunga, 1.0900)
        assert ammesso is False and "ESCL-07" in motivo

    def test_gest05_niente_trailing_dopo_il_break_even(self) -> None:
        corta = posizione(tp1_raggiunto=True, livello_stop=1.1000)
        ammesso, motivo = g.spostamento_stop_ammesso(corta, 1.0990)
        assert ammesso is False and "GEST-05" in motivo

    def test_gest14_niente_mediazione(self) -> None:
        assert g.mediazione_ammessa() is False


# ===========================================================================
# GEST-08, GEST-09 — target
# ===========================================================================
class TestTarget:
    def test_gest08_estende_solo_verso_l_alto(self) -> None:
        pos = posizione(tf_crt=TF.H4, target_finale=1.0800)
        kl = KeyLevel(TF.D1, TipoKeyLevel.MIN, 1.0700)
        esteso = g.estendi_target(pos, TF.D1, kl, crt_formato_su_quel_tf=True)
        assert esteso.target_finale == 1.0700

    def test_gest08_un_timeframe_inferiore_non_estende(self) -> None:
        pos = posizione(tf_crt=TF.D1, target_finale=1.0800)
        kl = KeyLevel(TF.H4, TipoKeyLevel.MIN, 1.0700)
        assert g.estendi_target(pos, TF.H4, kl, True).target_finale == 1.0800

    def test_gest08_lo_stesso_timeframe_non_estende(self) -> None:
        pos = posizione(tf_crt=TF.H4, target_finale=1.0800)
        kl = KeyLevel(TF.H4, TipoKeyLevel.MIN, 1.0700)
        assert g.estendi_target(pos, TF.H4, kl, True).target_finale == 1.0800

    def test_rev26_serve_un_crt_non_una_bias(self) -> None:
        """"conferma il pattern" significa CRT formato (REV-26)."""
        pos = posizione(tf_crt=TF.H4, target_finale=1.0800)
        kl = KeyLevel(TF.D1, TipoKeyLevel.MIN, 1.0700)
        assert g.estendi_target(pos, TF.D1, kl, crt_formato_su_quel_tf=False).target_finale == 1.0800

    def test_pa48_target_consumato_prima_di_tp1(self) -> None:
        pos = posizione(tp1_raggiunto=False)
        nuova, motivo = g.target_consumato_prima_di_tp1(pos, 1.0700)
        assert nuova.target_finale == 1.0700 and "DEF-29" in motivo

    def test_pa48_senza_target_successivo_si_chiude(self) -> None:
        _, motivo = g.target_consumato_prima_di_tp1(posizione(), None)
        assert "PRIN-99" in motivo


# ===========================================================================
# GEST-06, SETUP-17, GEST-10 — eventi sulla posizione
# ===========================================================================
class TestEventi:
    def test_gest06_stop_conservativo_gia_colpito(self) -> None:
        chiudere, motivo = g.gap_invalidato_con_posizione_aperta(posizione(ancorata_al_gap=True))
        assert chiudere is True and "coincide" in motivo

    def test_pa47_stop_aggressivo_nessuna_azione(self) -> None:
        chiudere, motivo = g.gap_invalidato_con_posizione_aperta(posizione(ancorata_al_gap=False))
        assert chiudere is False and "nessuna azione" in motivo

    def test_setup17_bias_invertita_protegge_senza_chiudere(self) -> None:
        pos = posizione(direzione=Bias.SHORT, prezzo_ingresso=1.1000, livello_stop=1.1050)
        nuova, motivo = g.cambio_bias_su_posizione_aperta(pos, Bias.LONG, spread=0.0001)
        assert nuova.livello_stop < pos.livello_stop, "protetta, non chiusa"
        assert "senza chiudere" in motivo

    def test_setup17_bias_invariata_nessuna_azione(self) -> None:
        pos = posizione(direzione=Bias.SHORT)
        nuova, _ = g.cambio_bias_su_posizione_aperta(pos, Bias.SHORT, 0.0001)
        assert nuova == pos

    def test_gest10_chiude_solo_le_posizioni_della_vecchia_bias(self) -> None:
        corta = posizione(direzione=Bias.SHORT)
        lunga = posizione(direzione=Bias.LONG)
        assert g.chiudere_al_target_di_comando(corta, Bias.SHORT, True) is True
        assert g.chiudere_al_target_di_comando(lunga, Bias.SHORT, True) is False
        assert g.chiudere_al_target_di_comando(corta, Bias.SHORT, False) is False

    def test_gest11_gest13(self) -> None:
        assert g.chiusura_ha_soglia_di_tolleranza() is False
        assert g.posizioni_si_gestiscono_a_blocco() is False

    def test_gest12_lo_stato_e_ricostruibile(self) -> None:
        """I campi che GEST-12 elenca come stato da ricostruire dopo un riavvio."""
        pos = posizione()
        for campo in ("strumento", "direzione", "prezzo_ingresso", "tf_crt",
                      "livello_stop", "tp1", "target_finale", "tp1_raggiunto"):
            assert hasattr(pos, campo), campo


class TestPurezza:
    def test_nessun_accesso_a_rete_o_disco(self) -> None:
        import ast

        for modulo in ("core/rischio.py", "core/gestione.py"):
            albero = ast.parse(open(modulo, encoding="utf-8").read())
            moduli: set[str] = set()
            for nodo in ast.walk(albero):
                if isinstance(nodo, ast.Import):
                    moduli.update(a.name.split(".")[0] for a in nodo.names)
                elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                    moduli.add(nodo.module.split(".")[0])
            vietati = {"httpx", "requests", "socket", "urllib", "sqlite3", "os", "pathlib"}
            assert not (moduli & vietati), (modulo, moduli & vietati)

    def test_la_posizione_e_immutabile(self) -> None:
        pos = posizione()
        with pytest.raises(Exception):
            pos.livello_stop = 0.0     # type: ignore[misc]
