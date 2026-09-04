"""Collaudo di integrazione su core/motore.py.

Le due cose che questo file deve dimostrare, oltre al funzionamento:

1. **nessun lookahead** — al momento `t` il motore vede solo candele chiuse
   entro `t`, anche e soprattutto sui timeframe superiori;
2. **ogni astensione ha una regola** — il motore non dice mai "non si opera"
   senza dire quale regola glielo impone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import motore as m
from core.contesto import EventoNews
from core.definizioni import Bias, Candela, Gap, KeyLevel, Mitigazione, Polarita, TipoKeyLevel
from core.motore import Fotografia
from core.parametri import TF

# Un martedi' qualunque, lontano da festivita'.
ADESSO = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)


def cand(massimo: float, minimo: float, chiusura: float, apertura: float, ore: int = 0) -> Candela:
    return Candela(ADESSO - timedelta(hours=ore), apertura, massimo, minimo, chiusura)


# Un CRT short conforme su TF_H4, costruito sull'esempio numerico di GEST-01.
#
#   N1 range 100-110, quindi TP1 = 105 (meta' del range).
#   N2 prende il key level a 110.5 spingendosi a 111, e richiude a 109.
#   Ingresso a 109: rischio |109-111| = 2, rendimento |105-109| = 4, rr = 2.0.
#
# La spike di N2 deve restare stretta rispetto al range di N1, altrimenti
# GEST-01 esclude il setup: e' proprio il filtro che quella regola descrive.
N1 = cand(massimo=110, minimo=100, chiusura=110, apertura=100, ore=4)
N2 = cand(massimo=111, minimo=108, chiusura=109, apertura=110, ore=0)
KL_SETTIMANALE = KeyLevel(TF.W1, TipoKeyLevel.MAX, 110.5)


def foto(**modifiche: object) -> Fotografia:
    argomenti: dict = {
        "istante": ADESSO,
        "strumento": "EURUSD",
        "candele_per_tf": {TF.H4: [N1, N2]},
        "bias_per_tf": {TF.M3: Bias.SHORT},
        "target_raggiunto_per_tf": {},
        "key_level_presi": [KL_SETTIMANALE],
        "sbilanciamenti": {TF.D1: Bias.SHORT, TF.W1: Bias.SHORT},
        "equity": 10000.0,
        "prezzo_cfd": 109.0,
        "valore_punto": 1.0,
        "passo_broker": 0.01,
        "posizioni_aperte_per_strumento": {},
        "equity_inizio_giornata": 10000.0,
        "equity_inizio_settimana": 10000.0,
        "equity_inizio_mese": 10000.0,
        "eventi_news": [],
        "eta_calendario_ore": 1.0,
    }
    argomenti.update(modifiche)
    return Fotografia(**argomenti)


# ===========================================================================
# Nessun lookahead
# ===========================================================================
class TestNienteLookahead:
    def test_candele_visibili_taglia_il_futuro(self) -> None:
        passata = cand(10, 5, 8, 6, ore=1)
        adesso = cand(11, 6, 9, 8, ore=0)
        futura = Candela(ADESSO + timedelta(hours=1), 9, 12, 8, 11)
        visibili = m.candele_visibili([passata, adesso, futura], ADESSO)
        assert visibili == (passata, adesso)

    def test_la_candela_che_chiude_adesso_e_visibile(self) -> None:
        """`orario` e' l'istante di chiusura: `<=`, non `<`."""
        assert m.candele_visibili([cand(11, 6, 9, 8, ore=0)], ADESSO) != ()

    def test_candele_visibili_ordina(self) -> None:
        a = cand(10, 5, 8, 6, ore=3)
        b = cand(11, 6, 9, 8, ore=1)
        assert m.candele_visibili([b, a], ADESSO) == (a, b)

    def test_la_settimanale_in_corso_non_esiste(self) -> None:
        """Il punto in cui i backtest multi-timeframe sbagliano piu' spesso.

        Mercoledi' alle 14:00 la candela settimanale non e' chiusa. Se il
        motore la vedesse, l'allineamento userebbe un dato che al momento `t`
        nessuno poteva conoscere, e il risultato sembrerebbe ottimo.
        """
        chiusa = Candela(ADESSO - timedelta(days=3), 100, 120, 90, 110)
        in_corso = Candela(ADESSO + timedelta(days=4), 110, 130, 100, 125)
        visibili = m.candele_visibili([chiusa, in_corso], ADESSO)
        assert visibili == (chiusa,)
        assert in_corso not in visibili

    def test_il_motore_rifiltra_anche_se_gli_arriva_gia_pulito(self) -> None:
        """Fidarsi di chi costruisce la fotografia costerebbe un lookahead muto."""
        futura = Candela(ADESSO + timedelta(hours=4), 109, 130, 108, 129)
        decisione = m.valuta(foto(candele_per_tf={TF.H4: [N1, N2, futura]}), TF.H4)
        # Con la futura come N2 il CRT sarebbe diverso: verifico che non venga usata.
        assert decisione.tf_crt is TF.H4
        assert decisione.livello_stop == N2.massimo, "N2 e' l'ultima candela CHIUSA"


# ===========================================================================
# Il percorso completo
# ===========================================================================
class TestPercorsoCompleto:
    def test_setup_conforme_produce_un_ordine(self) -> None:
        decisione = m.valuta(foto(), TF.H4)
        assert decisione.azione == "SELL"
        assert decisione.direzione is Bias.SHORT
        assert decisione.volume is not None and decisione.volume > 0
        assert decisione.livello_stop == 111.0        # estremo di N2
        assert decisione.tp1 == pytest.approx(105.0)  # meta' del range di N1
        assert decisione.rapporto_su_tp1 == pytest.approx(2.0)  # l'esempio di GEST-01
        assert decisione.regole_che_bloccano == ()

    def test_la_decisione_elenca_le_regole_che_l_hanno_prodotta(self) -> None:
        decisione = m.valuta(foto(), TF.H4)
        for regola in ("SETUP-06", "SETUP-00", "SETUP-02A", "GEST-02", "GEST-07",
                       "RISK-03", "DEF-47", "PREC-05", "SETUP-03"):
            assert regola in decisione.regole_applicate, regola

    def test_la_spiegazione_e_leggibile(self) -> None:
        assert "SELL" in m.valuta(foto(), TF.H4).spiegazione()
        senza = m.valuta(foto(bias_per_tf={}), TF.H4)
        assert "nessuna operazione" in senza.spiegazione()


# ===========================================================================
# Ogni astensione ha una regola
# ===========================================================================
class TestAstensioni:
    def blocchi(self, **modifiche: object) -> set[str]:
        return set(m.valuta(foto(**modifiche), TF.H4).regole_che_bloccano)

    def test_mai_astenersi_senza_dire_perche(self) -> None:
        casi: list[dict] = [
            {"bias_per_tf": {}},
            {"key_level_presi": []},
            {"sbilanciamenti": {}},
            {"posizioni_aperte_per_strumento": {"EURUSD": 4}},
            {"dati_coerenti": False},
            {"eventi_news": [EventoNews(ADESSO, "EUR", 3)]},
            {"pnl_giornaliero": -500.0},
            {"equity": 1.0, "passo_broker": 1.0},
            {"strumento": "BTCUSD"},
            {"eta_calendario_ore": None},
            {"candele_per_tf": {TF.H4: []}},
        ]
        for caso in casi:
            decisione = m.valuta(foto(**caso), TF.H4)
            assert decisione.azione == "NONE", caso
            assert decisione.regole_che_bloccano, f"astensione muta su {caso}"
            assert decisione.motivo, f"astensione senza motivo su {caso}"

    def test_setup06_senza_bias_di_comando(self) -> None:
        assert "SETUP-06" in self.blocchi(bias_per_tf={})

    def test_setup00_senza_key_level(self) -> None:
        assert "SETUP-00" in self.blocchi(key_level_presi=[])

    def test_setup05_senza_allineamento(self) -> None:
        assert "SETUP-05" in self.blocchi(sbilanciamenti={})

    def test_setup07_direzione_contraria_al_comando(self) -> None:
        assert "SETUP-07" in self.blocchi(bias_per_tf={TF.M3: Bias.LONG})

    def test_risk06_quattro_posizioni(self) -> None:
        assert "RISK-06" in self.blocchi(posizioni_aperte_per_strumento={"EURUSD": 4})

    def test_ctx02_finestra_news(self) -> None:
        assert "CTX-02" in self.blocchi(eventi_news=[EventoNews(ADESSO, "USD", 3)])

    def test_ctx04_festivita(self) -> None:
        natale = datetime(2026, 12, 25, 14, 0, tzinfo=timezone.utc)
        candele = {TF.H4: [
            Candela(natale - timedelta(hours=4), 100, 110, 100, 110),
            Candela(natale, 110, 111, 108, 109),
        ]}
        assert "CTX-04" in self.blocchi(istante=natale, candele_per_tf=candele)

    def test_escl05_strumento_fuori_universo(self) -> None:
        assert "ESCL-05" in self.blocchi(strumento="BTCUSD")

    def test_pa55_calendario_assente(self) -> None:
        assert "PRIN-99" in self.blocchi(eta_calendario_ore=None)

    def test_gest01_rapporto_sotto_soglia(self) -> None:
        """Ingresso vicino allo stop: il rendimento su TP1 non copre il rischio.

        Entrare a 106 invece che a 109 porta il rischio a 5 e il rendimento a
        1: rr 0.2, sotto la soglia di 1,5. E' il ritardo che CTX-05 misura col
        rapporto invece che col cronometro.
        """
        assert "GEST-01" in self.blocchi(prezzo_cfd=106.0)

    def test_piu_blocchi_tutti_riportati(self) -> None:
        blocchi = self.blocchi(
            key_level_presi=[], sbilanciamenti={}, pnl_giornaliero=-500.0,
        )
        assert len(blocchi) >= 2


# ===========================================================================
# Precedenze
# ===========================================================================
class TestPrecedenze:
    def test_prec01_il_rischio_batte_il_setup(self) -> None:
        """Setup perfetto, limite giornaliero raggiunto: non si opera."""
        buono = m.valuta(foto(), TF.H4)
        assert buono.azione == "SELL"
        bloccato = m.valuta(foto(pnl_giornaliero=-400.0), TF.H4)
        assert bloccato.azione == "NONE"
        assert "RISK-07" in bloccato.regole_che_bloccano

    def test_prec04_il_contesto_batte_il_setup(self) -> None:
        natale = datetime(2026, 12, 25, 14, 0, tzinfo=timezone.utc)
        candele = {TF.H4: [
            Candela(natale - timedelta(hours=4), 100, 110, 100, 110),
            Candela(natale, 110, 111, 108, 109),
        ]}
        bloccato = m.valuta(foto(istante=natale, candele_per_tf=candele), TF.H4)
        assert bloccato.azione == "NONE" and "CTX-04" in bloccato.regole_che_bloccano

    def test_prec02_il_timeframe_piu_alto_comanda(self) -> None:
        """Con 3M short e 1D long, comanda il 3M e il CRT short passa."""
        decisione = m.valuta(foto(bias_per_tf={TF.M3: Bias.SHORT, TF.D1: Bias.LONG}), TF.H4)
        assert decisione.azione == "SELL"

    def test_prec05_le_esclusioni_battono_tutto(self) -> None:
        """Anche col setup migliore, uno strumento fuori universo non passa."""
        assert m.valuta(foto(strumento="BTCUSD"), TF.H4).azione == "NONE"


# ===========================================================================
# L'ultima riga di difesa
# ===========================================================================
class TestUltimaRigaDiDifesa:
    """PREC-05 — verifica_divieti() gira su un ordine gia' validato da tutto
    il resto. In funzionamento normale non scatta mai: e' il suo scopo.

    Questi test simulano un guasto a monte e verificano che venga fermato
    comunque. Senza di loro quel controllo non sarebbe collaudato da nulla,
    e resterebbe codice che nessuno ha mai visto funzionare.
    """

    def test_ferma_un_ordine_contro_la_bias_di_comando(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulo un errore in setup.py che lascia passare la direzione opposta."""
        monkeypatch.setattr(m.stp, "direzione_concorde", lambda *a, **k: True)
        monkeypatch.setattr(m.ctx, "filtri_attivi", lambda **k: ())
        decisione = m.valuta(foto(bias_per_tf={TF.M3: Bias.LONG}), TF.H4)
        assert decisione.azione == "NONE"
        assert "ESCL-01" in decisione.regole_che_bloccano

    def test_ferma_un_ordine_con_lo_stop_sul_prezzo_di_ingresso(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Uno stop a distanza nulla dall'ingresso e' una posizione senza stop.

        Normalmente lo ferma GEST-01, perche' il rischio nullo rende il
        rapporto incalcolabile. Qui zittisco anche quel filtro per arrivare
        fino in fondo e verificare che ESCL-10 regga da sola.
        """
        monkeypatch.setattr(m.gest, "stop_aggressivo", lambda n2, direzione: 110.0)
        monkeypatch.setattr(m.ctx, "filtri_attivi", lambda **k: ())
        decisione = m.valuta(foto(prezzo_cfd=110.0), TF.H4)
        assert decisione.azione == "NONE"
        assert "ESCL-10" in decisione.regole_che_bloccano

    def test_ferma_un_crt_nato_su_un_timeframe_da_soli_gap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulo un errore che fa nascere un CRT su TF_H12, vietato da ESCL-04."""
        vero = m.stp.cerca_crt

        def falso(n1, n2, tf, livelli):
            crt = vero(n1, n2, TF.H4, livelli)
            if crt is None:
                return None
            from dataclasses import replace
            return replace(crt, tf=TF.H12)

        monkeypatch.setattr(m.stp, "cerca_crt", falso)
        monkeypatch.setattr(m.stp, "allineamento_soddisfatto", lambda *a, **k: True)
        monkeypatch.setattr(m.ctx, "filtri_attivi", lambda **k: ())
        decisione = m.valuta(foto(), TF.H4)
        assert decisione.azione == "NONE"
        assert "ESCL-04" in decisione.regole_che_bloccano


# ===========================================================================
# Gap
# ===========================================================================
class TestGap:
    GAP = Gap(Polarita.RIBASSISTA, 112.0, 118.0, 125.0, TF.W1, ADESSO - timedelta(days=7))


    def test_ingresso_da_gap_solo_in_fase_tre(self) -> None:
        for fase in (1, 2):
            decisione = m.valuta(foto(gap_attivo=self.GAP, gap_fase=fase), TF.H4)
            assert decisione.azione == "NONE"
            assert "SETUP-09" in decisione.regole_che_bloccano

    def test_fase_tre_passa(self) -> None:
        decisione = m.valuta(foto(gap_attivo=self.GAP, gap_fase=3), TF.H4)
        assert decisione.azione == "SELL" and decisione.doppio_ingresso is True

    def test_def42_non_determinata_blocca_l_ingresso_da_gap(self) -> None:
        decisione = m.valuta(
            foto(gap_attivo=self.GAP, gap_fase=3, mitigazione=Mitigazione.NON_DETERMINATA), TF.H4
        )
        assert decisione.azione == "NONE" and "DEF-42" in decisione.regole_che_bloccano

    def test_risk04_il_doppio_ingresso_dimezza_la_size(self) -> None:
        singolo = m.valuta(foto(), TF.H4)
        doppio = m.valuta(foto(gap_attivo=self.GAP, gap_fase=3), TF.H4)
        assert singolo.volume is not None and doppio.volume is not None
        assert doppio.volume < singolo.volume


# ===========================================================================
# Coerenza generale
# ===========================================================================
class TestCoerenza:
    def test_un_ordine_ha_sempre_uno_stop(self) -> None:
        """ESCL-10 e RISK-11: nessuna posizione senza stop."""
        decisione = m.valuta(foto(), TF.H4)
        assert decisione.azione != "NONE"
        assert decisione.livello_stop is not None
        assert decisione.livello_stop != decisione.tp1

    def test_lo_stop_sta_dalla_parte_giusta(self) -> None:
        corta = m.valuta(foto(), TF.H4)
        assert corta.livello_stop is not None and corta.tp1 is not None
        assert corta.livello_stop > corta.tp1, "su uno short lo stop sta sopra il target"

    def test_astenersi_senza_regola_e_un_errore_del_motore(self) -> None:
        """Una decisione di non operare senza regola sarebbe PRIN-99 non
        dichiarato: il motore preferisce rompersi piuttosto che tacere."""
        with pytest.raises(ValueError):
            m._non_operare("EURUSD", [], "nessun motivo")

    def test_la_decisione_e_immutabile(self) -> None:
        decisione = m.valuta(foto(), TF.H4)
        with pytest.raises(Exception):
            decisione.volume = 99.0        # type: ignore[misc]

    def test_stessa_fotografia_stessa_decisione(self) -> None:
        istantanea = foto()
        prima = m.valuta(istantanea, TF.H4)
        for _ in range(20):
            assert m.valuta(istantanea, TF.H4) == prima


class TestOperativitaDomenicale:
    DOMENICA = datetime(2026, 3, 8, 23, 0, tzinfo=timezone.utc)

    def candele_domenicali(self) -> dict:
        return {
            TF.H4: [
                Candela(self.DOMENICA - timedelta(hours=4), 100, 110, 100, 110),
                Candela(self.DOMENICA, 110, 111, 108, 109),
            ],
            TF.W1: [
                Candela(self.DOMENICA - timedelta(days=7), 100, 110, 100, 110),
                Candela(self.DOMENICA, 110, 111, 108, 109),
            ],
        }

    def test_prin13_domenica_su_h4_non_si_opera(self) -> None:
        decisione = m.valuta(
            foto(istante=self.DOMENICA, candele_per_tf=self.candele_domenicali()), TF.H4
        )
        assert decisione.azione == "NONE"
        assert "PRIN-13" in decisione.regole_che_bloccano

    def test_prin13_domenica_sul_settimanale_si_opera(self) -> None:
        decisione = m.valuta(
            foto(
                istante=self.DOMENICA,
                candele_per_tf=self.candele_domenicali(),
                key_level_presi=[KeyLevel(TF.M1, TipoKeyLevel.MAX, 110.5)],
                sbilanciamenti={TF.M1: Bias.SHORT, TF.M3: Bias.SHORT},
            ),
            TF.W1,
        )
        assert "PRIN-13" not in decisione.regole_che_bloccano
