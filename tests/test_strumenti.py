"""La tabella degli strumenti (`nvm/dati/strumenti.py`)."""

from nvm.dati.minuti import PUNTO
from nvm.dati.strumenti import BASE, NUOVI, STRUMENTI
from nvm.prova.campo import COMMISSIONE
from nvm.vivo.messaggi import CIFRE


def test_i_sei_di_partenza_non_cambiano():
    assert list(STRUMENTI)[:6] == list(BASE)
    assert {n: PUNTO[n] for n in BASE} == {"EURUSD": 1e-5, "GBPUSD": 1e-5, "AUDUSD": 1e-5, "USDCHF": 1e-5,
                                          "USDJPY": 1e-3, "XAUUSD": 1e-3}
    assert {n: COMMISSIONE[n] for n in BASE} == {"EURUSD": 0.00007, "GBPUSD": 0.00007, "AUDUSD": 0.00007,
                                                "USDCHF": 0.00007, "USDJPY": 0.007, "XAUUSD": 0.07}
    assert {n: CIFRE[n] for n in BASE} == {"EURUSD": 5, "GBPUSD": 5, "AUDUSD": 5, "USDCHF": 5, "USDJPY": 3, "XAUUSD": 2}


def test_ventotto_coppie_scritte_come_le_scrive_il_mercato_e_l_oro():
    forex = [n for n in STRUMENTI if n != "XAUUSD"]
    assert len(forex) == 28 and len(NUOVI) == 23
    for n in ("EURGBP", "GBPJPY", "AUDNZD", "NZDUSD", "USDCAD", "CADJPY", "CHFJPY", "EURCHF"):
        assert n in STRUMENTI
    assert "USDEUR" not in STRUMENTI and "JPYCHF" not in STRUMENTI
    assert STRUMENTI["GBPJPY"].punto == 1e-3 and STRUMENTI["GBPJPY"].cifre == 3
    assert STRUMENTI["EURGBP"].punto == 1e-5 and STRUMENTI["EURGBP"].pip == 1e-4
