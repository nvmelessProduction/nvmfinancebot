"""Il costo che entra negli R della Fase 1.

Senza un costo credibile un backtest dice quello che si vuole. Su questa
strategia pesa piu' che altrove: gli stop sono stretti, e su uno stop stretto
il costo di un giro vale una frazione grande del rischio.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from costi_misurati import (                                   # noqa: E402
    PERCENTILE, TabellaSpread, _percentile, costo_per_lato, costruisci,
)


@pytest.fixture
def archivio(tmp_path):
    """Un archivio con misure di spread costruite apposta."""
    percorso = tmp_path / "prova.db"
    conn = sqlite3.connect(percorso)
    conn.execute("CREATE TABLE spread (simbolo TEXT, misurato_utc TEXT, "
                 "bid REAL, ask REAL, spread REAL)")
    righe = []
    # XAUUSD alle 10: stretto. Alle 22: largo. E' la differenza che una media
    # nasconderebbe e che il percentile per ora esiste per vedere.
    for i in range(50):
        righe.append(("XAUUSD+", f"2026-09-24T10:{i % 60:02d}:00+00:00", 0, 0, 0.12))
    for i in range(50):
        righe.append(("XAUUSD+", f"2026-09-24T22:{i % 60:02d}:00+00:00", 0, 0, 0.40))
    # Un'ora con pochi campioni: non deve avere un percentile suo.
    for i in range(3):
        righe.append(("XAUUSD+", f"2026-09-24T03:{i:02d}:00+00:00", 0, 0, 9.99))
    conn.executemany("INSERT INTO spread VALUES (?,?,?,?,?)", righe)
    conn.commit()
    conn.close()
    return str(percorso)


class TestIlPercentile:

    def test_e_il_novantesimo(self):
        assert PERCENTILE == pytest.approx(0.90)

    def test_interpola(self):
        assert _percentile([0.0, 10.0], 0.5) == pytest.approx(5.0)
        assert _percentile([1.0], 0.9) == pytest.approx(1.0)

    def test_non_e_la_media(self):
        """L'oro si allarga al rollover: una media nasconde proprio i momenti
        in cui si perde."""
        valori = [0.1] * 90 + [5.0] * 10
        assert _percentile(valori, 0.90) > sum(valori) / len(valori)


class TestLaTabella:

    def test_distingue_le_ore(self, archivio):
        t = costruisci(archivio)
        assert t.spread("XAUUSD+", 10) == pytest.approx(0.12)
        assert t.spread("XAUUSD+", 22) == pytest.approx(0.40)

    def test_un_ora_povera_ripiega_sullo_strumento(self, archivio):
        """Tre campioni non fanno un percentile. Il ripiego non usa il 9,99
        di quei tre: prende il percentile di tutto lo strumento."""
        t = costruisci(archivio)
        assert ("XAUUSD+", 3) not in t.per_ora
        assert t.spread("XAUUSD+", 3) == t.per_strumento["XAUUSD+"]
        assert t.spread("XAUUSD+", 3) < 9.99

    def test_uno_strumento_ignoto_prende_il_piu_largo(self, archivio):
        """Il ripiego va sempre verso il costo PIU' ALTO: sbagliare per
        eccesso scarta un setup buono, sbagliare per difetto valida una
        strategia che dal vivo non regge."""
        t = costruisci(archivio)
        assert t.spread("MAIVISTO+", 12) == t.il_piu_largo
        assert t.il_piu_largo == max(t.per_strumento.values())

    def test_senza_misure_non_inventa(self, tmp_path):
        percorso = tmp_path / "vuoto.db"
        conn = sqlite3.connect(percorso)
        conn.execute("CREATE TABLE spread (simbolo TEXT, misurato_utc TEXT, "
                     "bid REAL, ask REAL, spread REAL)")
        conn.commit()
        conn.close()
        t = costruisci(str(percorso))
        assert t.campioni == 0
        assert t.spread("XAUUSD+", 10) == 0.0


class TestIlCostoCompleto:
    """Lo spread da solo non basta, e su un conto RAW e' il pezzo piccolo."""

    def test_su_conto_RAW_la_commissione_domina(self):
        """`bid == ask` e' normale qui: il 90esimo percentile di EURUSD vale
        ZERO, e fermarsi allo spread direbbe che operare e' gratis."""
        vuota = TabellaSpread(per_strumento={"EURUSD+": 0.0}, campioni=1)
        c = costo_per_lato(vuota, "EURUSD", "EURUSD+", prezzo=1.139, ora=10)
        assert c > 0, "senza commissione il costo risulterebbe nullo"
        # Quattro pip circa a giro completo, come misurato sul conto.
        assert 0.00003 < 2 * c < 0.00006

    def test_il_giro_costa_il_doppio_di_un_lato(self):
        """Le etichette lo pagano all'entrata E all'uscita."""
        t = TabellaSpread(per_strumento={"XAUUSD+": 0.12}, campioni=1)
        uno = costo_per_lato(t, "XAUUSD", "XAUUSD+", prezzo=4290.0, ora=10)
        assert 2 * uno == pytest.approx(
            0.12 + (4.06 / (100.0 * 4290.0)) * 4290.0, rel=1e-6)

    def test_il_fattore_di_robustezza_scala_tutto(self):
        """Il risultato della Fase 2 deve reggere anche a 1,5: se regge solo
        col costo nominale, non e' un si'."""
        t = TabellaSpread(per_strumento={"XAUUSD+": 0.12}, campioni=1)
        base = costo_per_lato(t, "XAUUSD", "XAUUSD+", 4290.0, 10)
        largo = costo_per_lato(t, "XAUUSD", "XAUUSD+", 4290.0, 10, fattore=1.5)
        assert largo == pytest.approx(base * 1.5)

    def test_lo_slippage_si_somma_e_non_si_inventa(self):
        """Il valore predefinito e' zero: qui non si mette un numero che
        nessuno ha misurato. Chi ne ha uno lo passa."""
        t = TabellaSpread(per_strumento={"XAUUSD+": 0.12}, campioni=1)
        senza = costo_per_lato(t, "XAUUSD", "XAUUSD+", 4290.0, 10)
        con = costo_per_lato(t, "XAUUSD", "XAUUSD+", 4290.0, 10, slippage=0.5)
        assert con == pytest.approx(senza + 0.25)

    def test_le_coppie_col_contratto_in_dollari(self):
        """`USDCHF` e `USDJPY` hanno il contratto gia' in dollari: 100.000 USD
        contro franchi o yen. Convertirlo una seconda volta sbaglierebbe la
        commissione di due ordini di grandezza."""
        t = TabellaSpread(per_strumento={"USDJPY+": 0.005}, campioni=1)
        c = costo_per_lato(t, "USDJPY", "USDJPY+", prezzo=158.0, ora=10)
        commissione = 2 * c - 0.005
        assert commissione == pytest.approx((4.06 / 100_000.0) * 158.0, rel=1e-6)
