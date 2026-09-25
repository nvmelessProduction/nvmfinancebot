"""La tabella degli strumenti (`nvm/dati/strumenti.py`)."""

from datetime import date
from types import SimpleNamespace as NS

from nvm.dati.dukascopy import indirizzo, indirizzo_ore
from nvm.dati.minuti import PUNTO
from nvm.dati.strumenti import ALTRI_NUOVI, BASE, COPPIE_NUOVE, NUOVI, STRUMENTI
from nvm.prova.campo import COMMISSIONE
from nvm.vivo.messaggi import CIFRE
from nvm.vivo.terminale import Terminale
from tests.mt5_finto import MT5Finto


def test_i_sei_di_partenza_non_cambiano():
    assert list(STRUMENTI)[:6] == list(BASE)
    assert {n: PUNTO[n] for n in BASE} == {"EURUSD": 1e-5, "GBPUSD": 1e-5, "AUDUSD": 1e-5, "USDCHF": 1e-5,
                                          "USDJPY": 1e-3, "XAUUSD": 1e-3}
    assert {n: COMMISSIONE[n] for n in BASE} == {"EURUSD": 0.00007, "GBPUSD": 0.00007, "AUDUSD": 0.00007,
                                                "USDCHF": 0.00007, "USDJPY": 0.007, "XAUUSD": 0.07}
    assert {n: CIFRE[n] for n in BASE} == {"EURUSD": 5, "GBPUSD": 5, "AUDUSD": 5, "USDCHF": 5, "USDJPY": 3, "XAUUSD": 2}


def test_ventotto_coppie_scritte_come_le_scrive_il_mercato():
    forex = [n for n, s in STRUMENTI.items() if s.famiglia == "forex"]
    assert len(forex) == 28 and len(COPPIE_NUOVE) == 23
    for n in ("EURGBP", "GBPJPY", "AUDNZD", "NZDUSD", "USDCAD", "CADJPY", "CHFJPY", "EURCHF"):
        assert n in STRUMENTI
    assert "USDEUR" not in STRUMENTI and "JPYCHF" not in STRUMENTI
    assert STRUMENTI["GBPJPY"].punto == 1e-3 and STRUMENTI["GBPJPY"].cifre == 3
    assert STRUMENTI["EURGBP"].punto == 1e-5 and STRUMENTI["EURGBP"].pip == 1e-4


def test_indici_crypto_petrolio_e_argento():
    for n in ("SPX500", "NAS100", "US30", "GER40", "UK100", "JPN225", "BTCUSD", "ETHUSD", "USOIL", "UKOIL", "XAGUSD"):
        assert n in ALTRI_NUOVI
    assert set(NUOVI) == set(COPPIE_NUOVE) | set(ALTRI_NUOVI)
    # Su Dukascopy alcuni hanno un altro nome.
    assert "/LIGHTCMDUSD/2012/02/" in indirizzo_ore("USOIL", 2012, 3, "BID")
    assert "/USA500IDXUSD/2023/00/05/" in indirizzo("SPX500", date(2023, 1, 5), "BID")
    assert "/EURUSD/" in indirizzo("EURUSD", date(2023, 1, 5), "BID")


def test_il_bot_trova_il_nome_che_usa_il_broker():
    m = MT5Finto()
    m.tick = {"US500.cash": NS(time=0, bid=1, ask=1), "EURUSD.a": NS(time=0, bid=1, ask=1)}
    t = Terminale(suffisso=".a", mt5=m)
    assert t.esiste("SPX500") and t.simbolo("SPX500") == "US500.cash"
    assert t.esiste("EURUSD") and t.simbolo("EURUSD") == "EURUSD.a"
    assert not t.esiste("BTCUSD")


def test_le_crypto_si_scaricano_anche_il_sabato():
    from nvm.dati.dukascopy import giorni_del_mese
    forex = giorni_del_mese(2024, 1, fino_a=date(2024, 1, 10))
    crypto = giorni_del_mese(2024, 1, fino_a=date(2024, 1, 10), sabato=True)
    assert date(2024, 1, 6) not in forex and date(2024, 1, 6) in crypto and len(crypto) == len(forex) + 1
