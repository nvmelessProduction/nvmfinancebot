"""Scaricamento, candele e controlli, su dati sintetici."""

import urllib.error
from datetime import date

import numpy as np
import pytest

from nvm.dati.candele import costruisci
from nvm.dati.controlli import controlla
from nvm.dati.dukascopy import (
    Scaricatore, TroppeRichieste, giorni_del_mese, indirizzo, leggi_bi5,
    minuti_del_giorno, scarica_mese,
)
from nvm.dati.minuti import Minuti, carica_periodo
from nvm.tempo import TF, ny, utc
from tests.aiuti import bi5, minuti, minuti_piatti


# --- Dukascopy ---------------------------------------------------------------

def test_indirizzo_conta_i_mesi_da_zero():
    url = indirizzo("EURUSD", date(2024, 1, 2), "BID")
    assert url.endswith("/EURUSD/2024/00/02/BID_candles_min_1.bi5")


def test_leggi_bi5_rimette_in_ordine_le_colonne():
    tabella = leggi_bi5(bi5([(60, 110000, 110020, 109990, 110010, 1.5)]))
    assert tabella.tolist() == [[60, 110000, 110020, 109990, 110010, 1.5]]


def test_file_vuoto_vuol_dire_nessun_dato():
    assert len(leggi_bi5(b"")) == 0


def test_minuti_senza_scambi_si_scartano():
    bid = bi5([(0, 100, 100, 100, 100, 0.0), (60, 100, 105, 99, 104, 2.0)])
    ask = bi5([(0, 102, 102, 102, 102, 0.0), (60, 102, 107, 101, 106, 2.0)])
    m = minuti_del_giorno("EURUSD", date(2024, 1, 2), bid, ask)
    assert m.t.tolist() == [utc(2024, 1, 2, 0, 1)]
    assert m.bid.tolist() == [[100, 105, 99, 104]]
    assert m.ask.tolist() == [[102, 107, 101, 106]]


def test_bid_e_ask_con_minuti_diversi_sono_un_errore():
    bid = bi5([(0, 100, 100, 100, 100, 1.0)])
    ask = bi5([(60, 100, 100, 100, 100, 1.0)])
    with pytest.raises(ValueError):
        minuti_del_giorno("EURUSD", date(2024, 1, 2), bid, ask)


def test_niente_sabato_e_niente_oggi():
    giorni = giorni_del_mese(2024, 1, fino_a=date(2024, 1, 10))
    assert date(2024, 1, 6) not in giorni  # sabato
    assert date(2024, 1, 10) not in giorni
    assert date(2024, 1, 9) in giorni


def _dukascopy_finto(richieste):
    def prendi(url):
        richieste.append(url)
        giorno = int(url.split("/")[-2])
        return bi5([(600, 110000 + giorno, 110010 + giorno, 109990 + giorno, 110005 + giorno, 1.0)])
    return prendi


def test_scarica_un_mese_e_non_lo_richiede_due_volte(tmp_path):
    richieste = []
    s = Scaricatore(tmp_path / "cache", pausa=0, prendi=_dukascopy_finto(richieste), dormi=lambda _: None)
    percorso = scarica_mese(s, tmp_path / "minuti", "EURUSD", 2024, 1, oggi=date(2024, 3, 1))
    m = Minuti.carica(percorso)
    assert len(m) == 27  # 31 giorni meno 4 sabati
    assert len(richieste) == 2 * 27

    scarica_mese(s, tmp_path / "minuti", "EURUSD", 2024, 1, oggi=date(2024, 3, 1))
    assert len(richieste) == 2 * 27

    periodo = carica_periodo(tmp_path / "minuti", "EURUSD", utc(2024, 1, 2), utc(2024, 1, 4))
    assert len(periodo) == 2


def test_troppe_richieste_si_aspetta_e_si_riprova(tmp_path):
    attese = []
    tentativi = []

    def prendi(url):
        tentativi.append(url)
        if len(tentativi) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return b""

    s = Scaricatore(tmp_path, pausa=0, attese=(1, 2, 4), prendi=prendi, dormi=attese.append)
    assert s.file("EURUSD", date(2024, 1, 2), "BID") == b""
    assert len(tentativi) == 3
    assert [a for a in attese if a] == [1, 2]


def test_se_non_smette_di_rifiutare_si_ferma(tmp_path):
    def prendi(url):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    s = Scaricatore(tmp_path, pausa=0, attese=(1, 2), prendi=prendi, dormi=lambda _: None)
    with pytest.raises(TroppeRichieste):
        s.file("EURUSD", date(2024, 1, 2), "BID")


def test_un_giorno_recente_senza_file_non_si_ricorda_vuoto(tmp_path):
    def prendi(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    s = Scaricatore(tmp_path, pausa=0, prendi=prendi, dormi=lambda _: None)
    s.file("EURUSD", date(2024, 1, 2), "BID", recente=True)
    assert not list(tmp_path.rglob("*.bi5"))
    s.file("EURUSD", date(2024, 1, 2), "BID", recente=False)
    assert len(list(tmp_path.rglob("*.bi5"))) == 1


# --- Candele -----------------------------------------------------------------

def test_candela_a_quattro_ore_dalle_5_alle_9_di_new_york():
    t = [ny(2026, 9, 10, 4, 59), ny(2026, 9, 10, 5, 0), ny(2026, 9, 10, 6, 30), ny(2026, 9, 10, 8, 59), ny(2026, 9, 10, 9, 0)]
    prezzi = [(1.0, 1.0, 1.0, 1.0), (1.1, 1.2, 1.05, 1.15), (1.15, 1.3, 1.1, 1.2), (1.2, 1.25, 1.0, 1.02), (2.0, 2.0, 2.0, 2.0)]
    c = costruisci(minuti("EURUSD", t, prezzi, spread=0.0002), TF.H4)
    assert c.inizio.tolist() == [ny(2026, 9, 10, 1), ny(2026, 9, 10, 5), ny(2026, 9, 10, 9)]
    assert c.fine[1] == ny(2026, 9, 10, 9)
    np.testing.assert_allclose(c.bid[1], [1.1, 1.3, 1.0, 1.02])
    np.testing.assert_allclose(c.ask[1], [1.1002, 1.3002, 1.0002, 1.0202])


def test_giornaliera_dalle_17_alle_17():
    m = minuti_piatti("EURUSD", ny(2026, 9, 9, 16), ny(2026, 9, 10, 18))
    c = costruisci(m, TF.D1)
    assert c.inizio.tolist() == [ny(2026, 9, 8, 17), ny(2026, 9, 9, 17), ny(2026, 9, 10, 17)]


def test_le_candele_chiuse_non_guardano_il_futuro():
    m = minuti_piatti("EURUSD", ny(2026, 9, 10, 1), ny(2026, 9, 10, 12))
    c = costruisci(m, TF.H4)
    assert len(c.chiuse_entro(ny(2026, 9, 10, 8, 59))) == 1  # solo quella delle 1
    assert len(c.chiuse_entro(ny(2026, 9, 10, 9))) == 2


# --- Controlli ---------------------------------------------------------------

def test_dati_puliti_nessuna_anomalia():
    m = minuti_piatti("EURUSD", ny(2026, 9, 9, 3), ny(2026, 9, 9, 6))
    assert controlla(m).pulito()


def test_i_controlli_trovano_buchi_salti_e_spread():
    t = [ny(2026, 9, 9, 3), ny(2026, 9, 9, 3, 1), ny(2026, 9, 9, 4, 30), ny(2026, 9, 9, 4, 31)]
    prezzi = [(1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1), (1.5, 1.5, 1.5, 1.5)]
    m = minuti("EURUSD", t, prezzi)
    m.ask[0] = m.bid[0] - 5  # ask sotto il bid
    tipi = controlla(m).conteggi
    assert tipi["buco"] == 1 and tipi["salto"] == 1 and tipi["spread"] == 1


def test_la_pausa_dell_oro_non_e_un_buco():
    # Pausa di mercoledi', e riapertura della domenica alle 18.
    for t in ([ny(2026, 9, 9, 16, 59), ny(2026, 9, 9, 18, 0)], [ny(2026, 9, 11, 16, 59), ny(2026, 9, 13, 18, 0)]):
        m = minuti("XAUUSD", t, [(2500.0,) * 4] * 2)
        assert controlla(m).pulito()
    # Per un cambio la stessa ora e' un buco vero.
    m = minuti("EURUSD", t[:2], [(1.1,) * 4] * 2)
    assert controlla(m).conteggi["buco"] == 1


def test_il_fine_settimana_non_e_un_buco():
    t = [ny(2026, 9, 11, 16, 59), ny(2026, 9, 13, 17, 0)]
    m = minuti("EURUSD", t, [(1.1, 1.1, 1.1, 1.1)] * 2)
    assert controlla(m).pulito()


# --- Un giorno vero ----------------------------------------------------------

def test_un_giorno_vero_di_dukascopy():
    """EURUSD del 10/09/2026, i due file come li da' Dukascopy."""
    from pathlib import Path

    cartella = Path(__file__).parent / "dati"
    m = minuti_del_giorno(
        "EURUSD", date(2026, 9, 10),
        (cartella / "EURUSD-2026-09-10_BID.bi5").read_bytes(),
        (cartella / "EURUSD-2026-09-10_ASK.bi5").read_bytes(),
    )
    assert len(m) == 1435
    assert controlla(m).pulito()
    spread = (m.ask[:, 3] - m.bid[:, 3]) * m.punto
    assert 0 < np.median(spread) < 0.0001  # meno di un pip
    h4 = costruisci(m, TF.H4)
    # Il giorno UTC va dalle 20:00 alle 20:00 di New York: la prima candela a
    # 4 ore completa e' quella delle 21:00.
    assert ny(2026, 9, 9, 21) in h4.inizio.tolist()
    assert ny(2026, 9, 10, 5) in h4.inizio.tolist()
