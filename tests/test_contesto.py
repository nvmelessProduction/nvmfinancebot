"""Collaudo di core/contesto.py e core/esclusioni.py."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from core import contesto as ctx
from core import esclusioni as esc
from core.contesto import Astensione, EventoNews
from core.definizioni import Bias
from core.esclusioni import OrdineProposto
from core.parametri import TF

ADESSO = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)   # martedi' qualsiasi


def news(ora: int, minuto: int, valuta: str = "USD", stelle: int = 3) -> EventoNews:
    return EventoNews(ADESSO.replace(hour=ora, minute=minuto), valuta, stelle)


# ===========================================================================
# CTX-02 — news
# ===========================================================================
class TestNews:
    def test_ctx02_finestra_trenta_prima_trenta_dopo(self) -> None:
        """L'esempio scritto nel documento: news alle 14:30."""
        evento = news(14, 30)
        alle_14_00 = ADESSO.replace(hour=14, minute=0)
        alle_14_05 = ADESSO.replace(hour=14, minute=5)
        alle_15_00 = ADESSO.replace(hour=15, minute=0)
        alle_15_01 = ADESSO.replace(hour=15, minute=1)

        assert ctx.dentro_finestra_news(alle_14_00, "EURUSD", [evento]) is evento, "14:00 e' il bordo"
        assert ctx.dentro_finestra_news(alle_14_05, "EURUSD", [evento]) is evento
        assert ctx.dentro_finestra_news(alle_15_00, "EURUSD", [evento]) is evento
        assert ctx.dentro_finestra_news(alle_15_01, "EURUSD", [evento]) is None

    def test_ctx02_appena_prima_della_finestra(self) -> None:
        evento = news(14, 30)
        assert ctx.dentro_finestra_news(ADESSO.replace(hour=13, minute=59), "EURUSD", [evento]) is None

    def test_ctx02_solo_tre_stelle(self) -> None:
        assert ctx.dentro_finestra_news(ADESSO, "EURUSD", [news(14, 0, stelle=2)]) is None
        assert ctx.dentro_finestra_news(ADESSO, "EURUSD", [news(14, 0, stelle=3)]) is not None

    def test_ctx02_filtro_per_strumento(self) -> None:
        """REV-18: una news sulla sterlina non ferma EURUSD."""
        sterlina = news(14, 0, valuta="GBP")
        assert ctx.dentro_finestra_news(ADESSO, "GBPUSD", [sterlina]) is not None
        assert ctx.dentro_finestra_news(ADESSO, "EURUSD", [sterlina]) is None

    def test_ctx02_il_dollaro_ferma_tutte_le_coppie_che_lo_contengono(self) -> None:
        dollaro = news(14, 0, valuta="USD")
        for coppia in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF"):
            assert ctx.dentro_finestra_news(ADESSO, coppia, [dollaro]) is not None

    def test_ctx02_oro_bloccato_da_qualsiasi_valuta(self) -> None:
        """PA-36: per l'oro il filtro non e' ristretto a una valuta."""
        for valuta in ("JPY", "CHF", "NZD", "SEK"):
            assert ctx.dentro_finestra_news(ADESSO, "XAUUSD", [news(14, 0, valuta=valuta)]) is not None

    def test_valute_di(self) -> None:
        assert ctx.valute_di("EURUSD") == frozenset({"EUR", "USD"})
        assert ctx.valute_di("USDJPY") == frozenset({"USD", "JPY"})
        assert ctx.valute_di("XAUUSD") is None
        with pytest.raises(ValueError):
            ctx.valute_di("BTCUSD")

    def test_pa55_calendario_assente_o_vecchio(self) -> None:
        assert ctx.calendario_utilizzabile(None, None) is False
        assert ctx.calendario_utilizzabile([], 1.0) is True, (
            "un calendario vuoto ma fresco significa 'nessuna news oggi', "
            "che e' informazione valida: bloccare qui fermerebbe il bot in "
            "ogni giornata tranquilla"
        )
        assert ctx.calendario_utilizzabile([news(14, 0)], 100.0) is False, "troppo vecchio"
        assert ctx.calendario_utilizzabile([news(14, 0)], 1.0) is True


# ===========================================================================
# CTX-04 — festivita'
# ===========================================================================
class TestFestivita:
    def test_ctx04_giorni_di_chiusura(self) -> None:
        assert ctx.giorno_di_festivita(date(2026, 12, 25)) == "Natale"
        assert ctx.giorno_di_festivita(date(2026, 1, 19)) == "Martin Luther King Day"

    def test_ctx04_giorno_normale(self) -> None:
        assert ctx.giorno_di_festivita(date(2026, 3, 10)) is None

    def test_ctx04_vale_anche_negli_anni_futuri(self) -> None:
        """PA-53 chiuso: le date sono calcolate, non tabellate."""
        assert ctx.giorno_di_festivita(date(2030, 12, 25)) is not None
        assert ctx.giorno_di_festivita(date(2035, 7, 4)) is not None


# ===========================================================================
# CTX-05, GEST-01 — rapporto rischio/rendimento
# ===========================================================================
class TestRapporto:
    def test_gest01_calcolo(self) -> None:
        # short: ingresso 100, stop 110, TP1 80 -> rischio 10, rendimento 20
        assert ctx.rapporto_rischio_rendimento(100, 110, 80) == pytest.approx(2.0)

    def test_gest01_sotto_soglia_esclude_il_setup(self) -> None:
        """CASO LIMITE richiesto: rr sotto 1,5 esclude il setup."""
        # short: ingresso 100, stop 110, TP1 95 -> rischio 10, rendimento 5
        assert ctx.rapporto_rischio_rendimento(100, 110, 95) == pytest.approx(0.5)
        assert ctx.ritardo_tollerabile(100, 110, 95) is False

    def test_gest01_target_dal_lato_dello_stop_e_incoerente(self) -> None:
        """Con i soli valori assoluti darebbe 2.0 e la size verrebbe calcolata.

        Ingresso 100 e stop 110 descrivono uno short. Un target a 120 sta
        dalla parte dello stop: e' un'operazione che non puo' vincere.
        """
        assert ctx.rapporto_rischio_rendimento(100, 110, 120) is None
        assert ctx.ritardo_tollerabile(100, 110, 120) is False
        # E a specchio su un long.
        assert ctx.rapporto_rischio_rendimento(100, 90, 80) is None

    def test_gest01_target_sul_prezzo_di_ingresso(self) -> None:
        assert ctx.rapporto_rischio_rendimento(100, 110, 100) is None

    def test_gest01_soglia_esatta_passa(self) -> None:
        """`rr >= 1.5`: sulla soglia si opera."""
        assert ctx.rapporto_rischio_rendimento(100, 110, 85) == pytest.approx(1.5)
        assert ctx.ritardo_tollerabile(100, 110, 85) is True
        assert ctx.ritardo_tollerabile(100, 110, 85.5) is False, "1.45 non basta"

    def test_gest01_rischio_nullo_e_incoerente(self) -> None:
        assert ctx.rapporto_rischio_rendimento(100, 100, 120) is None
        assert ctx.ritardo_tollerabile(100, 100, 120) is False


# ===========================================================================
# CTX-03, CTX-07, CTX-08, CTX-09 — cio' che non filtra
# ===========================================================================
class TestNonFiltri:
    def test_ctx03_nessun_filtro_di_mercato(self) -> None:
        assert ctx.filtro_su_condizioni_di_mercato() is False

    def test_ctx09_nessun_blocco_per_perdite_consecutive(self) -> None:
        for perdite in (0, 3, 10, 100):
            assert ctx.blocco_per_perdite_consecutive(perdite) is False

    def test_ctx07_i_buchi_non_escludono(self) -> None:
        assert ctx.timeframe_escluso_per_buchi(50) is False

    def test_ctx08_pronto_dopo_il_ricalcolo(self) -> None:
        attesi = [TF.M12, TF.W1, TF.D1]
        assert ctx.pronto_all_avvio([TF.M12, TF.W1, TF.D1, TF.H4], attesi) is True
        assert ctx.pronto_all_avvio([TF.M12, TF.W1], attesi) is False


# ===========================================================================
# CTX-01 — l'elenco completo
# ===========================================================================
class TestFiltri:
    def base(self, **modifiche: object) -> dict:
        argomenti: dict = {
            "adesso": ADESSO,
            "strumento": "EURUSD",
            "key_level_preso": True,
            "comando": Bias.SHORT,
            "direzione_crt": Bias.SHORT,
            "allineamento_ok": True,
            "rapporto_su_tp1": 2.0,
            "posizioni_aperte_strumento": 0,
            "limite_rischio_raggiunto": False,
            "eventi_news": [],
            "mitigazione_non_determinata": False,
            "dati_coerenti": True,
        }
        argomenti.update(modifiche)
        return argomenti

    def regole(self, **modifiche: object) -> set[str]:
        return {a.regola for a in ctx.filtri_attivi(**self.base(**modifiche))}

    def test_contesto_pulito(self) -> None:
        assert ctx.filtri_attivi(**self.base()) == ()

    def test_le_undici_condizioni(self) -> None:
        assert "SETUP-00" in self.regole(key_level_preso=False)
        assert "SETUP-06" in self.regole(comando=Bias.NESSUNA)
        assert "SETUP-07" in self.regole(direzione_crt=Bias.LONG)
        assert "SETUP-05" in self.regole(allineamento_ok=False)
        assert "GEST-01" in self.regole(rapporto_su_tp1=1.4)
        assert "RISK-06" in self.regole(posizioni_aperte_strumento=4)
        assert "RISK-07" in self.regole(limite_rischio_raggiunto=True)
        assert "CTX-02" in self.regole(eventi_news=[news(14, 0)])
        assert "DEF-42" in self.regole(mitigazione_non_determinata=True)
        assert "PRIN-99" in self.regole(dati_coerenti=False)

    def test_ctx04_festivita_e_una_condizione_di_ctx01(self) -> None:
        natale = datetime(2026, 12, 25, 14, 0, tzinfo=timezone.utc)
        assert "CTX-04" in self.regole(adesso=natale)

    def test_le_due_condizioni_che_solo_ctx01_porta(self) -> None:
        """REV-17: sono quelle che si perderebbero usando il solo SETUP-15."""
        from core import setup as s

        natale = datetime(2026, 12, 25, 14, 0, tzinfo=timezone.utc)
        assert "CTX-04" in self.regole(adesso=natale)
        assert "GEST-01" in self.regole(rapporto_su_tp1=1.0)
        # SETUP-15 non le conosce nemmeno.
        violate_setup = s.esclusioni_setup(
            crt=None, comando=Bias.SHORT, key_level_preso=True, sbilanciamenti={},
            posizioni_aperte_strumento=0, limite_rischio_raggiunto=False,
            dentro_finestra_news=False, dati_coerenti=True,
        )
        assert "CTX-04" not in violate_setup and "GEST-01" not in violate_setup

    def test_rapporto_mancante_blocca(self) -> None:
        assert "GEST-01" in self.regole(rapporto_su_tp1=None)

    def test_ogni_astensione_dice_il_motivo(self) -> None:
        for astensione in ctx.filtri_attivi(**self.base(key_level_preso=False, dati_coerenti=False)):
            assert isinstance(astensione, Astensione)
            assert astensione.regola and astensione.motivo


# ===========================================================================
# 06_esclusioni.md — i divieti permanenti
# ===========================================================================
class TestDivieti:
    def ordine(self, **modifiche: object) -> OrdineProposto:
        argomenti: dict = {
            "strumento": "EURUSD",
            "direzione": Bias.SHORT,
            "bias_comando": Bias.SHORT,
            "tf_crt": TF.H4,
            "key_level_preso": True,
            "livello_stop": 1.1050,
            "prezzo_ingresso": 1.1000,
            "posizioni_aperte_strumento": 0,
            "target_comando_raggiunto": False,
        }
        argomenti.update(modifiche)
        return OrdineProposto(**argomenti)

    def regole(self, **modifiche: object) -> set[str]:
        return {v.regola for v in esc.verifica_divieti(self.ordine(**modifiche))}

    def test_ordine_conforme_non_viola_nulla(self) -> None:
        assert esc.verifica_divieti(self.ordine()) == ()

    def test_escl01_mai_contro_la_bias_di_comando(self) -> None:
        assert "ESCL-01" in self.regole(direzione=Bias.LONG)

    def test_escl03_reversal_prima_del_target(self) -> None:
        violate = self.regole(direzione=Bias.LONG, target_comando_raggiunto=False)
        assert {"ESCL-01", "ESCL-03"} <= violate
        # Dopo il target resta la violazione di ESCL-01, ma non quella di ESCL-03:
        # e' SETUP-08 a dover ricalcolare bias_comando prima di invertire.
        assert "ESCL-03" not in self.regole(direzione=Bias.LONG, target_comando_raggiunto=True)

    def test_escl02_mai_senza_key_level(self) -> None:
        assert "ESCL-02" in self.regole(key_level_preso=False)

    def test_escl04_mai_sotto_h1_ne_sui_timeframe_da_gap(self) -> None:
        assert "ESCL-04" in self.regole(tf_crt=TF.H12)
        assert "ESCL-04" in self.regole(tf_crt=TF.H6)
        assert "ESCL-04" not in self.regole(tf_crt=TF.H1)

    def test_escl05_universo_chiuso(self) -> None:
        assert "ESCL-05" in self.regole(strumento="BTCUSD")

    def test_escl10_mai_senza_stop(self) -> None:
        assert "ESCL-10" in self.regole(livello_stop=None)

    def test_escl10_stop_a_distanza_nulla(self) -> None:
        assert "ESCL-10" in self.regole(livello_stop=1.1000)

    def test_escl11_mai_oltre_quattro_posizioni(self) -> None:
        assert "ESCL-11" in self.regole(posizioni_aperte_strumento=4)
        assert "ESCL-11" not in self.regole(posizioni_aperte_strumento=3)

    def test_divieti_sulla_gestione(self) -> None:
        assert "ESCL-06" in self.regole(su_posizione_in_perdita=True)
        assert "ESCL-07" in self.regole(stop_allargato=True)
        assert "ESCL-08" in self.regole(stop_spostato_prima_di_tp1=True)
        assert "ESCL-09" in self.regole(usa_trailing=True)

    def test_divieti_sui_dati(self) -> None:
        assert "ESCL-12" in self.regole(prezzi_future_e_cfd_confrontati=True)
        assert "ESCL-13" in self.regole(candela_in_formazione=True)

    def test_escl15_solo_rsi_e_atr(self) -> None:
        assert "ESCL-15" in self.regole(indicatori_usati=("MACD",))
        assert "ESCL-15" in self.regole(indicatori_usati=("RSI", "EMA"))
        assert "ESCL-15" not in self.regole(indicatori_usati=("RSI", "ATR"))

    def test_e_l_ultima_riga_di_difesa(self) -> None:
        """Un ordine sbagliato in tutti i modi viene fermato comunque."""
        violate = self.regole(
            strumento="BTCUSD",
            direzione=Bias.LONG,
            key_level_preso=False,
            livello_stop=None,
            tf_crt=TF.H12,
            usa_trailing=True,
        )
        assert len(violate) >= 6

    def test_escl16_escl17_irreversibilita(self) -> None:
        assert esc.gap_puo_tornare_valido() is False
        assert esc.livello_puo_tornare_disponibile() is False

    def test_escl18_id_mai_riciclati(self) -> None:
        assert esc.id_riciclabile("DEF-05") is False
        assert "DEF-05" in esc.ID_RITIRATI and "DEF-15" in esc.ID_RITIRATI


class TestPermessi:
    def test_amm_sono_permessi_non_vincoli(self) -> None:
        assert esc.chiusura_manuale_ammessa() is True
        assert esc.riapertura_dopo_stop_ammessa() is True
        assert esc.direzioni_opposte_su_strumenti_diversi_ammesse() is True
        assert esc.mantenimento_nel_fine_settimana_ammesso() is True
        assert esc.operativita_durante_rollover_ammessa() is True


class TestPurezza:
    def test_nessun_accesso_a_rete_o_disco(self) -> None:
        import ast

        for modulo in ("core/contesto.py", "core/esclusioni.py"):
            albero = ast.parse(open(modulo, encoding="utf-8").read())
            moduli: set[str] = set()
            for nodo in ast.walk(albero):
                if isinstance(nodo, ast.Import):
                    moduli.update(a.name.split(".")[0] for a in nodo.names)
                elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                    moduli.add(nodo.module.split(".")[0])
            vietati = {"httpx", "requests", "socket", "urllib", "sqlite3", "os", "pathlib"}
            assert not (moduli & vietati), (modulo, moduli & vietati)
