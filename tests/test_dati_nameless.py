"""I dati di Nameless (`kaggle_rete/dati.py`): le crypto di Binance e gli orari di TradingView, senza rete internet."""

import io
import zipfile
from datetime import date

from kaggle_rete import dati as D
from nvm.dati import candele
from nvm.tempo import utc


def _zip(righe: list[str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("SOLUSDT-1h-2025-03.csv", "\n".join(righe))
    return b.getvalue()


def test_le_ore_di_binance_in_millisecondi_e_microsecondi():
    t0 = utc(2025, 3, 1)
    ms = [f"{(t0 + k * 3600) * 1000},10.5,11.0,10.0,10.8,123.4,0,0,0,0,0,0" for k in range(3)]
    us = [f"{(t0 + k * 3600) * 1_000_000},10.5,11.0,10.0,10.8,123.4,0,0,0,0,0,0" for k in range(3, 5)]
    m = D.ore_binance(_zip(["open_time,open,high,low,close,volume"] + ms + us), "SOLUSD")
    assert list(m.t) == [t0 + k * 3600 for k in range(5)]
    assert (m.bid[0] * m.punto).round(8).tolist() == [10.5, 11.0, 10.0, 10.8]


def test_i_mesi_chiusi_e_gli_orari_di_tradingview():
    assert D.mesi_fino_a(date(2018, 1, 15), (2017, 11)) == [(2017, 11), (2017, 12)]
    D.imposta_orari(["EURUSD", "BTCUSD", "USDMXN"])
    assert candele.SESSIONI == {"EURUSD": "18", "BTCUSD": True, "USDMXN": "18"}
    # I 66 mercati di HistData: i 38 di prima piu' le esotiche, l'oro nelle altre valute e quattro indici.
    assert len(D.NOMI) == 66 and D.NOMI["EU50"] == "ETXEUR" and len(D.CRYPTO) == 20
