"""Collaudo di calendario.py, casi.py, statistiche.py e strategy.py.

Sono i quattro moduli che stanno ai bordi del motore: cosa entra (il
calendario news), cosa esce (i casi e le statistiche), e come l'impianto
webhook lo chiama.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core import calendario as cal
from core import casi as cs
from core import statistiche as stat
from core import strategy
from core.casi import Caso
from core.definizioni import Bias, Candela, Divergenza, Gap, KeyLevel, Polarita, TipoKeyLevel
from core.models import AlertIn
from core.motore import Decisione
from core.parametri import TF
from core.statistiche import Operazione

ADESSO = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)


# ===========================================================================
# calendario.py — PA-54
# ===========================================================================
class TestCalendario:
    def scrivi(self, tmp_path: Path, contenuto: str) -> Path:
        percorso = tmp_path / "news.csv"
        percorso.write_text(contenuto, encoding="utf-8")
        return percorso

    def test_legge_un_calendario_valido(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "2026-03-10T14:30:00Z,USD,3,Non-Farm Payrolls\n"
            "2026-03-11T09:00:00Z,EUR,2,Produzione industriale\n"
        ))
        eventi = cal.leggi_calendario(percorso)
        assert len(eventi) == 2
        assert eventi[0].valuta == "USD" and eventi[0].stelle == 3
        assert eventi[0].orario_utc.tzinfo is not None

    def test_ordina_per_orario(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "2026-03-12T09:00:00Z,EUR,3,dopo\n"
            "2026-03-10T14:30:00Z,USD,3,prima\n"
        ))
        eventi = cal.leggi_calendario(percorso)
        assert eventi[0].orario_utc < eventi[1].orario_utc

    def test_tiene_anche_le_news_minori(self, tmp_path: Path) -> None:
        """Distinguere 'nessuna news importante' da 'file vuoto'."""
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "2026-03-10T14:30:00Z,USD,1,dato minore\n"
        ))
        assert len(cal.leggi_calendario(percorso)) == 1

    def test_righe_vuote_tollerate(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "\n"
            "2026-03-10T14:30:00Z,USD,3,valida\n"
            ",,,\n"
        ))
        assert len(cal.leggi_calendario(percorso)) == 1

    def test_data_illeggibile_e_un_errore(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "ieri pomeriggio,USD,3,boh\n"
        ))
        with pytest.raises(cal.CalendarioMalformato):
            cal.leggi_calendario(percorso)

    def test_colonne_mancanti(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, "data_ora_utc,descrizione\n2026-03-10T14:30:00Z,x\n")
        with pytest.raises(cal.CalendarioMalformato):
            cal.leggi_calendario(percorso)

    def test_carica_distingue_assente_da_rotto(self, tmp_path: Path) -> None:
        eventi, eta, motivo = cal.carica(tmp_path / "non_esiste.csv", ADESSO)
        assert eventi is None and "assente" in motivo

        rotto = self.scrivi(tmp_path, "questo non e' un csv valido\n")
        eventi, eta, motivo = cal.carica(rotto, ADESSO)
        assert eventi is None and "illeggibile" in motivo

    def test_carica_riuscito(self, tmp_path: Path) -> None:
        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "2026-03-10T14:30:00Z,USD,3,NFP\n"
        ))
        # L'eta' si misura sul tempo di modifica del file, che e' quello vero:
        # va confrontata con l'ora reale, non con la data finta dei dati.
        eventi, eta, motivo = cal.carica(percorso, datetime.now(timezone.utc))
        assert eventi is not None and len(eventi) == 1
        assert eta is not None and eta >= 0
        assert "1 eventi" in motivo

    def test_modello_scrivibile_e_rileggibile(self, tmp_path: Path) -> None:
        percorso = tmp_path / "dati" / "news.csv"
        cal.scrivi_modello(percorso)
        assert cal.leggi_calendario(percorso) == ()

    def test_il_calendario_alimenta_il_filtro(self, tmp_path: Path) -> None:
        """Il giro completo: file -> eventi -> CTX-02."""
        from core import contesto as ctx

        percorso = self.scrivi(tmp_path, (
            "data_ora_utc,valuta,stelle,descrizione\n"
            "2026-03-10T14:30:00Z,USD,3,NFP\n"
        ))
        eventi = cal.leggi_calendario(percorso)
        assert ctx.dentro_finestra_news(ADESSO, "EURUSD", eventi) is not None
        assert ctx.dentro_finestra_news(ADESSO, "GBPUSD", eventi) is not None
        fuori = ADESSO.replace(hour=16)
        assert ctx.dentro_finestra_news(fuori, "EURUSD", eventi) is None


# ===========================================================================
# casi.py — 07_casi.md
# ===========================================================================
class TestCasi:
    def decisione_operativa(self) -> Decisione:
        return Decisione(
            azione="SELL", strumento="EURUSD", direzione=Bias.SHORT, volume=0.25,
            livello_stop=111.0, tp1=105.0, target_finale=105.0, tf_crt=TF.H4,
            regole_applicate=("SETUP-00", "SETUP-02A", "GEST-02"),
            motivo="tutte le condizioni soddisfatte", rapporto_su_tp1=2.0,
        )

    def caso(self, **modifiche: object) -> Caso:
        argomenti: dict = {
            "numero": 2,
            "istante": ADESSO,
            "strumento_future": "6E",
            "decisione": self.decisione_operativa(),
            "tf_key_level": TF.W1,
            "tf_comando": TF.M3,
            "bias_comando": Bias.SHORT,
            "key_level_preso": KeyLevel(TF.W1, TipoKeyLevel.MAX, 110.5),
            "n1": Candela(ADESSO, 100, 110, 100, 110),
            "n2": Candela(ADESSO, 110, 111, 108, 109),
            "n3_apertura": 109.0,
            "tf_allineati": (TF.D1, TF.W1),
        }
        argomenti.update(modifiche)
        return Caso(**argomenti)

    def test_il_blocco_ha_tutti_i_campi(self) -> None:
        testo = cs.formatta(self.caso())
        for campo in ("CASO 02", "Data/ora:", "Strumento:", "TF del CRT:",
                      "TF del key level:", "DATI", "bias_comando:", "tf_comando:",
                      "key_level_preso:", "gap_attivo_tf:", "gap_zona:", "gap_fase:",
                      "N1 high/low:", "N2 high/low/close:", "N3 open:", "tf_allineati:",
                      "divergenza_rsi:", "rr_su_tp1:", "REGOLE APPLICABILI",
                      "TUA DECISIONE", "MOTIVO", "ETICHETTA", "ESITO TRADE"):
            assert campo in testo, f"manca il campo {campo}"

    def test_nessun_campo_omesso_diventa_n_d(self) -> None:
        """La sezione 1: se un dato non c'e' si scrive n/d, non si salta la riga."""
        testo = cs.formatta(self.caso(n1=None, n2=None, n3_apertura=None, key_level_preso=None))
        assert testo.count("n/d") >= 4
        assert "N1 high/low:" in testo

    def test_escl23_l_etichetta_e_di_conformita(self) -> None:
        conforme = cs.formatta(self.caso())
        assert "CONFORME alla strategia" in conforme
        assert "vinto" not in conforme.lower() and "perso" not in conforme.lower()

    def test_amm01_la_chiusura_manuale_e_non_conforme(self) -> None:
        testo = cs.formatta(self.caso(chiusura_manuale=True))
        assert "NON CONFORME alla strategia" in testo

    def test_l_esito_e_marcato_informativo(self) -> None:
        testo = cs.formatta(self.caso(esito_r=1.8))
        assert "+1.8R" in testo
        assert "NON e' l'etichetta" in testo

    def test_l_esito_non_cambia_l_etichetta(self) -> None:
        """L'errore numero 1 dell'elenco finale di 07_casi.md."""
        vinto = cs.formatta(self.caso(esito_r=3.0))
        perso = cs.formatta(self.caso(esito_r=-1.0))
        assert "CONFORME alla strategia" in vinto and "CONFORME alla strategia" in perso
        assert "NON CONFORME" not in vinto and "NON CONFORME" not in perso

    def test_caso_di_non_ingresso(self) -> None:
        """Sono i piu' informativi, e vanno inclusi (07_casi.md §1)."""
        rifiutata = Decisione(
            azione="NONE", strumento="EURUSD",
            regole_che_bloccano=("SETUP-05", "CTX-02"),
            motivo="meno di 2 timeframe allineati; news a 3 stelle",
        )
        testo = cs.formatta(self.caso(decisione=rifiutata))
        assert "NESSUN INGRESSO" in testo
        assert "SETUP-05" in testo and "CTX-02" in testo

    def test_campi_di_giud01(self) -> None:
        """§3.1: distanza, ATR e rapporto, in ogni caso di categoria A/B/C."""
        testo = cs.formatta(self.caso(distanza_kl_gap=50.0, atr_tf=20.0))
        assert "distanza_kl_gap:" in testo
        assert "atr_tf:" in testo
        assert "rapporto:" in testo and "2.5" in testo

    def test_numerazione_senza_duplicati(self) -> None:
        with pytest.raises(ValueError):
            cs.formatta_molti([self.caso(numero=2), self.caso(numero=2)])

    def test_blocco_markdown(self) -> None:
        testo = cs.blocco_markdown(self.caso())
        assert testo.startswith("```") and testo.endswith("```")


# ===========================================================================
# statistiche.py
# ===========================================================================
class TestStatistiche:
    def operazioni(self) -> list[Operazione]:
        return [
            Operazione("EURUSD", TF.H4, False, 2.0, 1.2),
            Operazione("EURUSD", TF.H4, False, -1.0, 0.8),
            Operazione("XAUUSD", TF.D1, True, 3.0, 4.5),
            Operazione("XAUUSD", TF.D1, True, -1.0, 3.9),
            Operazione("GBPUSD", TF.H1, False, -1.0, None),
        ]

    def test_metriche_di_base(self) -> None:
        quadro = stat.riepilogo(self.operazioni())
        assert quadro.operazioni == 5
        assert quadro.vincenti == 2
        assert quadro.percentuale_vincenti == pytest.approx(40.0)
        assert quadro.r_totale == pytest.approx(2.0)
        assert quadro.r_medio == pytest.approx(0.4)

    def test_scomposizioni(self) -> None:
        quadro = stat.riepilogo(self.operazioni())
        assert set(quadro.per_strumento) == {"EURUSD", "XAUUSD", "GBPUSD"}
        assert set(quadro.per_timeframe) == {"TF_H4", "TF_1D", "TF_H1"}
        assert set(quadro.per_tipo_setup) == {"con gap", "senza gap"}
        assert quadro.per_strumento["XAUUSD"].operazioni == 2

    def test_drawdown(self) -> None:
        # +2, -1, -1 -> picco 2, minimo 0, drawdown 2R
        massimo, percentuale = stat.drawdown([2.0, -1.0, -1.0])
        assert massimo == pytest.approx(2.0)
        assert percentuale == pytest.approx(2.0)      # 2R all'1% = 2% di equity

    def test_drawdown_senza_perdite(self) -> None:
        assert stat.drawdown([1.0, 2.0, 3.0]) == (0.0, 0.0)

    def test_drawdown_su_serie_vuota(self) -> None:
        assert stat.drawdown([]) == (0.0, 0.0)

    def test_conteggio_filtri_conta_tutti_i_blocchi(self) -> None:
        """La statistica piu' utile: non solo il primo blocco, tutti."""
        decisioni = [
            Decisione(azione="NONE", strumento="EURUSD",
                      regole_che_bloccano=("SETUP-05", "CTX-02")),
            Decisione(azione="NONE", strumento="EURUSD",
                      regole_che_bloccano=("SETUP-05",)),
            Decisione(azione="SELL", strumento="EURUSD"),
        ]
        conteggi = stat.conteggio_filtri(decisioni)
        assert conteggi["SETUP-05"] == 2
        assert conteggi["CTX-02"] == 1

    def test_filtri_mai_scattati(self) -> None:
        decisioni = [Decisione(azione="NONE", strumento="EURUSD",
                               regole_che_bloccano=("SETUP-05",))]
        mai = stat.filtri_mai_scattati(decisioni, ["SETUP-05", "CTX-04", "GEST-01"])
        assert mai == ["CTX-04", "GEST-01"]

    def test_distribuzione_rapporto_per_pa44(self) -> None:
        distribuzione = stat.distribuzione_rapporto(self.operazioni())
        assert distribuzione.campioni == 4
        assert distribuzione.minimo == pytest.approx(0.8)
        assert distribuzione.massimo == pytest.approx(4.5)
        assert distribuzione.sufficiente_per_pa44() is False

    def test_pa44_servono_trenta_campioni(self) -> None:
        molte = [Operazione("EURUSD", TF.H4, False, 1.0, float(i)) for i in range(30)]
        assert stat.distribuzione_rapporto(molte).sufficiente_per_pa44() is True

    def test_distribuzione_vuota(self) -> None:
        vuota = stat.distribuzione_rapporto([])
        assert vuota.campioni == 0 and vuota.mediana is None

    def test_resoconto_leggibile(self) -> None:
        testo = stat.resoconto(
            self.operazioni(),
            [Decisione(azione="NONE", strumento="EURUSD", regole_che_bloccano=("CTX-04",))],
            filtri_attesi=["CTX-04", "GEST-01"],
        )
        assert "FORWARD TEST" in testo
        assert "COSA HA IMPEDITO DI OPERARE" in testo
        assert "CTX-04" in testo
        assert "GEST-01" in testo, "i filtri mai scattati vanno elencati"
        assert "PA-44" in testo

    def test_resoconto_senza_operazioni(self) -> None:
        assert "operazioni:        0" in stat.resoconto([], [])


# ===========================================================================
# strategy.py — il ponte con l'impianto
# ===========================================================================
class TestPonte:
    def alert(self) -> AlertIn:
        return AlertIn.model_validate({
            "secret": "s", "symbol": "EURUSD", "tf": "15",
            "candle_close_time_utc": "2026-03-10T14:00:00Z",
            "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15,
        })

    def test_senza_fornitore_non_si_opera_e_lo_si_dice(self) -> None:
        strategy.registra_fornitore(None)
        decisione = strategy.valuta(self.alert())
        assert decisione.azione == "NONE"
        assert "livello dati non collegato" in decisione.motivo

    def test_fornitore_che_non_sa_costruire(self) -> None:
        strategy.registra_fornitore(lambda alert: None)
        try:
            decisione = strategy.valuta(self.alert())
            assert decisione.azione == "NONE" and "PRIN-99" in decisione.motivo
        finally:
            strategy.registra_fornitore(None)

    def test_con_fornitore_il_motore_decide(self) -> None:
        """Il giro completo: alert -> fotografia -> motore -> Decision."""
        from core import stato as st
        from core.stato import Conto

        inizio = datetime(2026, 1, 1, tzinfo=timezone.utc)
        storico = {
            TF.W1: [
                Candela(inizio, 100, 105, 95, 102),
                Candela(inizio + timedelta(days=7), 102, 110, 100, 108),
                Candela(inizio + timedelta(days=14), 108, 111, 105, 106),
            ],
            TF.H4: [
                Candela(inizio + timedelta(days=14), 100, 110, 100, 110),
                Candela(inizio + timedelta(days=14, hours=4), 110, 111, 108, 109),
            ],
        }

        def fornitore(alert):
            foto = st.costruisci_fotografia(
                istante=inizio + timedelta(days=14, hours=5),
                strumento="EURUSD",
                storico=storico,
                conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
                eta_calendario_ore=1.0,
            )
            return foto, TF.H4

        strategy.registra_fornitore(fornitore)
        try:
            decisione = strategy.valuta(self.alert())
            assert decisione.azione in ("NONE", "BUY", "SELL")
            assert decisione.motivo, "il motivo non e' mai vuoto"
            assert "[" in decisione.motivo, "le regole finiscono nel motivo"
        finally:
            strategy.registra_fornitore(None)

    def test_la_traduzione_porta_le_regole_nel_motivo(self) -> None:
        """Perderle significherebbe tornare a un bot che non sa spiegarsi."""
        bloccata = Decisione(
            azione="NONE", strumento="EURUSD",
            regole_che_bloccano=("SETUP-05", "CTX-02"), motivo="non allineato",
        )
        tradotta = strategy.traduci(bloccata)
        assert tradotta.azione == "NONE"
        assert "SETUP-05" in tradotta.motivo and "CTX-02" in tradotta.motivo

    def test_la_traduzione_porta_i_livelli(self) -> None:
        operativa = Decisione(
            azione="SELL", strumento="EURUSD", direzione=Bias.SHORT, volume=0.25,
            livello_stop=111.0, target_finale=105.0,
            regole_applicate=("SETUP-03",), motivo="ok",
        )
        tradotta = strategy.traduci(operativa)
        assert tradotta.azione == "SELL"
        assert tradotta.volume == 0.25
        assert tradotta.sl == 111.0 and tradotta.tp == 105.0


# ===========================================================================
# importa_storico.py — semina dell'archivio da TradingView
# ===========================================================================
class TestImportazione:
    """La stessa trappola del fornitore: TradingView esporta l'orario di
    APERTURA, l'archivio vuole quello di CHIUSURA."""

    def csv(self, tmp_path, righe: str):
        percorso = tmp_path / "export.csv"
        percorso.write_text("time,open,high,low,close\n" + righe, encoding="utf-8")
        return percorso

    def test_legge_un_export(self, tmp_path) -> None:
        import importa_storico as imp

        percorso = self.csv(tmp_path, (
            "2026-03-10T00:00:00Z,100,110,95,105\n"
            "2026-03-11T00:00:00Z,105,115,104,112\n"
        ))
        barre = imp.leggi_csv(percorso)
        assert len(barre) == 2
        assert barre[0]["apertura"] == 100

    def test_accetta_anche_il_tempo_unix(self, tmp_path) -> None:
        import importa_storico as imp

        percorso = self.csv(tmp_path, "1772928000,100,110,95,105\n")
        assert len(imp.leggi_csv(percorso)) == 1

    def test_l_orario_diventa_la_chiusura(self, tmp_path) -> None:
        """La barra aperta il 10 chiude l'11, non il 10."""
        import importa_storico as imp
        from core.parametri import TF

        percorso = self.csv(tmp_path, (
            "2026-03-10T00:00:00Z,100,110,95,105\n"
            "2026-03-11T00:00:00Z,105,115,104,112\n"
            "2026-03-12T00:00:00Z,112,120,110,118\n"
        ))
        righe = imp.in_candele(imp.leggi_csv(percorso), "GC", TF.D1)
        assert righe[0]["chiusura_utc"].startswith("2026-03-11")
        assert righe[0]["apertura"] == 100

    def test_l_ultima_barra_viene_scartata(self, tmp_path) -> None:
        """E' quella in corso: tre barre danno due candele chiuse."""
        import importa_storico as imp
        from core.parametri import TF

        percorso = self.csv(tmp_path, (
            "2026-03-10T00:00:00Z,100,110,95,105\n"
            "2026-03-11T00:00:00Z,105,115,104,112\n"
            "2026-03-12T00:00:00Z,112,120,110,118\n"
        ))
        righe = imp.in_candele(imp.leggi_csv(percorso), "GC", TF.D1)
        assert len(righe) == 2

    def test_una_sola_barra_non_da_candele(self, tmp_path) -> None:
        import importa_storico as imp
        from core.parametri import TF

        percorso = self.csv(tmp_path, "2026-03-10T00:00:00Z,100,110,95,105\n")
        assert imp.in_candele(imp.leggi_csv(percorso), "GC", TF.D1) == []

    def test_colonne_mancanti(self, tmp_path) -> None:
        import importa_storico as imp

        percorso = tmp_path / "rotto.csv"
        percorso.write_text("time,open\n2026-03-10T00:00:00Z,100\n", encoding="utf-8")
        with pytest.raises(imp.CsvNonValido):
            imp.leggi_csv(percorso)

    def test_le_barre_si_ordinano(self, tmp_path) -> None:
        import importa_storico as imp

        percorso = self.csv(tmp_path, (
            "2026-03-12T00:00:00Z,112,120,110,118\n"
            "2026-03-10T00:00:00Z,100,110,95,105\n"
        ))
        barre = imp.leggi_csv(percorso)
        assert barre[0]["apertura_utc"] < barre[1]["apertura_utc"]

    def test_barra_incoerente_scartata(self, tmp_path) -> None:
        import importa_storico as imp
        from core.parametri import TF

        percorso = self.csv(tmp_path, (
            "2026-03-10T00:00:00Z,100,90,110,105\n"      # massimo sotto il minimo
            "2026-03-11T00:00:00Z,105,115,104,112\n"
            "2026-03-12T00:00:00Z,112,120,110,118\n"
        ))
        righe = imp.in_candele(imp.leggi_csv(percorso), "GC", TF.D1)
        assert len(righe) == 1, "la barra rotta sparisce, le altre restano"
