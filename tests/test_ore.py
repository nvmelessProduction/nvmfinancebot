"""Il bid del vecchio archivio, lo spread misurato e il completamento con l'ask."""

import gzip
from datetime import date

import numpy as np

from nvm.dati.dukascopy import Scaricatore, completa_con_ask, mesi_a_campione
from nvm.dati.minuti import Minuti, file_del_mese
from nvm.dati.ore import carica
from nvm.dati.spread import ModelloSpread
from nvm.dati.vecchio import leggi, salva_per_mese
from nvm.tempo import utc
from tests.aiuti import bi5


def _csv(percorso, righe):
    with gzip.open(percorso, "wt") as f:
        f.write("strumento,tf,chiusura_utc,apertura,massimo,minimo,chiusura,origine,ricevuta_utc\n")
        for r in righe:
            f.write(",".join(map(str, r)) + "\n")


def test_dal_vecchio_archivio_solo_le_righe_dukascopy(tmp_path):
    p = tmp_path / "EURUSD_TF_H1.csv.gz"
    _csv(p, [
        ("EURUSD", "TF_H1", "2024-01-02T01:00:00Z", 1.1, 1.2, 1.0, 1.15, "dukascopy", "x"),
        ("EURUSD", "TF_H1", "2024-01-02T01:00:00Z", 9.9, 9.9, 9.9, 9.9, "mt5", "x"),
        ("EURUSD", "TF_H1", "2024-01-02T02:00:00Z", 1.15, 1.16, 1.14, 1.155, "dukascopy", "x"),
    ])
    ore = leggi(p, "EURUSD")
    assert ore.t.tolist() == [utc(2024, 1, 2, 0), utc(2024, 1, 2, 1)]  # chiusura meno un'ora
    assert ore.bid[0].tolist() == [110000, 120000, 100000, 115000]
    assert salva_per_mese(ore, tmp_path / "ore_bid") == 1


def _mese(strumento, anno, mese, spread):
    t = np.arange(utc(anno, mese, 2), utc(anno, mese, 3), 3600, dtype=np.int64)
    bid = np.full((len(t), 4), 110000, np.int32)
    return Minuti(strumento, t, bid, bid + spread, np.ones(len(t), np.float32), np.ones(len(t), np.float32), 3600)


def test_lo_spread_si_prende_dallo_stesso_anno_e_ora():
    modello = ModelloSpread.da([_mese("EURUSD", 2010, 1, 12), _mese("EURUSD", 2020, 1, 3)])
    assert modello.spread(2010, 5) == 12
    assert modello.spread(2020, 5) == 3
    assert modello.spread(2012, 5) == 12  # l'anno piu' vicino
    stimato = modello.applica(_mese("EURUSD", 2019, 3, 0))
    assert np.all(stimato.ask - stimato.bid == 3)


def test_carica_preferisce_i_mesi_esatti(tmp_path):
    _mese("EURUSD", 2010, 1, 12).salva(file_del_mese(tmp_path / "ore", "EURUSD", 2010, 1))
    solo_bid = _mese("EURUSD", 2010, 2, 0)
    solo_bid.salva(file_del_mese(tmp_path / "ore_bid", "EURUSD", 2010, 2))
    ore, conti = carica(tmp_path, "EURUSD", utc(2010, 1, 1), utc(2010, 4, 1))
    assert (conti.esatti, conti.stimati, conti.mancanti) == (1, 1, 1)
    febbraio = ore.fra(utc(2010, 2, 1), utc(2010, 3, 1))
    assert np.all(febbraio.ask - febbraio.bid == 12)


def test_completare_con_l_ask(tmp_path):
    bid = _mese("EURUSD", 2024, 1, 0)
    bid.salva(file_del_mese(tmp_path / "ore_bid", "EURUSD", 2024, 1))
    inizio = utc(2024, 1, 1)
    righe = [(int(t - inizio), 110005, 110010, 110000, 110008, 2.0) for t in bid.t]
    s = Scaricatore(tmp_path / "cache", pausa=0, prendi=lambda url: bi5(righe), dormi=lambda _: None)
    percorso = completa_con_ask(s, tmp_path, "EURUSD", 2024, 1)
    esatto = Minuti.carica(percorso)
    assert np.all(esatto.bid == bid.bid)
    assert esatto.ask[0].tolist() == [110005, 110010, 110000, 110008]


def test_se_all_ask_manca_un_ora_il_mese_resta_stimato(tmp_path):
    bid = _mese("EURUSD", 2024, 1, 0)
    bid.salva(file_del_mese(tmp_path / "ore_bid", "EURUSD", 2024, 1))
    inizio = utc(2024, 1, 1)
    righe = [(int(t - inizio), 110005, 110010, 110000, 110008, 2.0) for t in bid.t[1:]]
    s = Scaricatore(tmp_path / "cache", pausa=0, prendi=lambda url: bi5(righe), dormi=lambda _: None)
    assert completa_con_ask(s, tmp_path, "EURUSD", 2024, 1) is None


def test_prima_un_gennaio_per_ogni_anno():
    ordine = mesi_a_campione("2006-01", "2008-12")
    assert ordine[:3] == [(2006, 1), (2007, 1), (2008, 1)]
    assert ordine[3:6] == [(2006, 7), (2007, 7), (2008, 7)]
