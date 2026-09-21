"""Quando il riepilogo deve gridare "serie indietro" e quando deve tacere.

L'allarme di freschezza aveva una soglia sola, 26 ore, per tutti i timeframe
e a qualunque ora. Due conseguenze, tutte e due brutte: ogni fine settimana
il messaggio diceva "ATTENZIONE: 24 serie indietro" quando il mercato era
semplicemente chiuso, e un 5 minuti fermo da un'ora -- che e' un guasto --
non lo diceva nessuno. Un allarme che suona sempre e un allarme che non suona
mai sono lo stesso allarme.
"""

from datetime import datetime, timezone

import pytest

from core import riepilogo


def _ora(giorno: int, ora: int) -> datetime:
    """Settembre 2026: il 21 e' un lunedi', quindi 19=sabato, 20=domenica."""
    return datetime(2026, 9, giorno, ora, 0, tzinfo=timezone.utc)


class TestMercatoAperto:
    """Domenica 22:00 -> venerdi' 22:00, misurato sull'archivio."""

    @pytest.mark.parametrize("giorno, ora", [
        (19, 3), (19, 12), (19, 23),    # sabato, tutto il giorno
        (20, 0), (20, 21),              # domenica prima della riapertura
        (25, 23),                       # venerdi' dopo la chiusura
    ])
    def test_chiuso(self, giorno, ora):
        assert riepilogo.mercato_aperto(_ora(giorno, ora)) is False

    @pytest.mark.parametrize("giorno, ora", [
        (20, 22), (20, 23),             # domenica sera, riapertura
        (21, 0), (23, 14),              # settimana piena
        (25, 21), (25, 22),             # venerdi' fino alla chiusura
    ])
    def test_aperto(self, giorno, ora):
        assert riepilogo.mercato_aperto(_ora(giorno, ora)) is True


class TestInRitardo:
    """La soglia dipende dal timeframe, e a mercato chiuso non c'e' soglia."""

    def test_a_mercato_chiuso_non_e_mai_in_ritardo(self, monkeypatch):
        monkeypatch.setattr(riepilogo, "mercato_aperto", lambda _: False)
        # Un giornaliero fermo da una settimana: di sabato e' normale.
        assert riepilogo._in_ritardo("EURUSD giornaliero", 170) is False
        assert riepilogo._in_ritardo("EURUSD 5 min", 60) is False

    def test_un_cinque_minuti_fermo_da_un_ora_e_un_guasto(self, monkeypatch):
        monkeypatch.setattr(riepilogo, "mercato_aperto", lambda _: True)
        assert riepilogo._in_ritardo("EURUSD 5 min", 1.0) is True

    def test_un_giornaliero_fermo_da_un_giorno_e_normale(self, monkeypatch):
        """Il caso che la soglia unica sbagliava in modo piu' evidente."""
        monkeypatch.setattr(riepilogo, "mercato_aperto", lambda _: True)
        assert riepilogo._in_ritardo("EURUSD giornaliero", 27) is False
        assert riepilogo._in_ritardo("EURUSD giornaliero", 100) is True

    def test_un_buco_solo_non_fa_allarme(self, monkeypatch):
        """Una candela che manca capita; tre di fila no."""
        monkeypatch.setattr(riepilogo, "mercato_aperto", lambda _: True)
        assert riepilogo._in_ritardo("EURUSD 1 ora", 2.0) is False
        assert riepilogo._in_ritardo("EURUSD 1 ora", 5.0) is True

    def test_timeframe_sconosciuto_ricade_sulla_soglia_vecchia(self, monkeypatch):
        monkeypatch.setattr(riepilogo, "mercato_aperto", lambda _: True)
        assert riepilogo._in_ritardo("EURUSD 4 ore", 20) is False
        assert riepilogo._in_ritardo("EURUSD 4 ore", 30) is True


class TestCadenza:
    """`forse_manda` e' del riepilogo, non di un motore di mercato."""

    @pytest.fixture(autouse=True)
    def _azzera(self):
        riepilogo._ultimo = None
        yield
        riepilogo._ultimo = None

    def test_il_primo_parte_subito(self, monkeypatch):
        mandati = []
        monkeypatch.setattr(riepilogo, "manda", lambda ore: mandati.append(ore) or True)
        assert riepilogo.forse_manda(6) is True
        assert mandati == [6]

    def test_il_secondo_aspetta(self, monkeypatch):
        mandati = []
        monkeypatch.setattr(riepilogo, "manda", lambda ore: mandati.append(ore) or True)
        riepilogo.forse_manda(6)
        assert riepilogo.forse_manda(6) is False
        assert len(mandati) == 1

    def test_due_motori_insieme_non_mandano_due_messaggi(self, monkeypatch):
        """Il motivo per cui il contatore e' del modulo e non dell'oggetto."""
        mandati = []
        monkeypatch.setattr(riepilogo, "manda", lambda ore: mandati.append(ore) or True)
        # Dukascopy e MT5 chiamano nello stesso minuto.
        riepilogo.forse_manda(6)
        riepilogo.forse_manda(6)
        assert len(mandati) == 1

    def test_un_riepilogo_che_esplode_non_propaga(self, monkeypatch):
        def _scoppia(ore):
            raise RuntimeError("archivio irraggiungibile")

        monkeypatch.setattr(riepilogo, "manda", _scoppia)
        assert riepilogo.forse_manda(6) is False
