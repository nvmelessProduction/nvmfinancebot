"""Lo storico di HistData per la scuola su Kaggle (`kaggle_rete/histdata.py`): orari, prezzi scritti male, pezzi buoni."""

import io
import zipfile

import numpy as np

from kaggle_rete.histdata import ore_da_zip, pezzi_buoni
from nvm.dati.minuti import Minuti
from nvm.tempo import utc


def _zip(righe: list[str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("DAT_ASCII_EURUSD_M1_2019.csv", "\n".join(righe) + "\n")
    return b.getvalue()


def test_orari_con_l_ora_legale_europea_e_prezzi_con_spazi():
    # Inverno: UTC = ora di HistData + 5. Estate europea (dall'ultima domenica di marzo): + 4. Negli anni vecchi i
    # prezzi hanno spazi dopo ("1.2397    ").
    righe = ["20190115 100000;1.1400;1.1410;1.1395;1.1405;0",
             "20190115 105900;1.1405;1.1420;1.1401;1.1410;0",
             "20190715 100000;1.1200    ;1.1210    ;1.1190    ;1.1205    ;0"]
    ore = ore_da_zip(_zip(righe), "EURUSD")
    assert list(ore.t) == [utc(2019, 1, 15, 15), utc(2019, 7, 15, 14)]
    p = ore.bid * ore.punto
    np.testing.assert_allclose(p[0], [1.1400, 1.1420, 1.1395, 1.1410])
    np.testing.assert_allclose(p[1], [1.1200, 1.1210, 1.1190, 1.1205])
    assert ore.passo == 3600


def _ore(t: np.ndarray, prezzi: np.ndarray) -> Minuti:
    punti = np.rint(np.repeat(prezzi[:, None], 4, axis=1) / 1e-5).astype(np.int64)
    zero = np.zeros(len(t), np.float32)
    return Minuti("EURUSD", t.astype(np.int64), punti, punti.copy(), zero, zero.copy(), 3600)


def test_i_pezzi_si_tagliano_ai_salti_impossibili_e_ai_buchi():
    ore = np.arange(utc(2005, 1, 1), utc(2020, 1, 1), 3600)
    prezzi = np.full(len(ore), 1.10)
    prezzi[ore >= utc(2012, 1, 1)] = 110.0          # un'altra serie: salto impossibile
    tieni = (ore < utc(2016, 1, 1)) | (ore >= utc(2016, 3, 1))   # due mesi di buco
    pezzi, nota = pezzi_buoni(_ore(ore[tieni], prezzi[tieni]))
    assert [(int(p.t[0]), int(p.t[-1])) for p in pezzi] == [(utc(2005, 1, 1), utc(2011, 12, 31, 23))]
    assert "1 salti impossibili e 1 buchi" in nota and "troppo corto" in nota
    # Il franco svizzero del 2015 (-15% fra due chiusure) non e' un taglio.
    prezzi = np.full(len(ore), 1.20)
    prezzi[ore >= utc(2015, 1, 15)] = 1.02
    pezzi, nota = pezzi_buoni(_ore(ore, prezzi))
    assert len(pezzi) == 1 and nota == ""
