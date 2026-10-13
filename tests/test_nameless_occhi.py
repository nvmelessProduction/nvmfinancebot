"""Gli occhi di Nameless (fase 1): le candele con gli orari di TradingView, le finestre senza futuro, la scuola."""

import numpy as np
import pytest

from nvm.dati import candele
from nvm.nameless.sensi import D1, TF_NAMELESS, Sensi, candele_di
from nvm.tempo import TF, scarti_ny, utc
from tests.aiuti import minuti


def _ore(strumento: str, dal: int, giorni: int, seme: int = 1, prezzo: float = 1.1):
    """Ore di una passeggiata casuale, senza il sabato e la domenica prima delle 22 UTC (il mercato chiuso)."""
    rng = np.random.default_rng(seme)
    t = np.arange(dal, dal + giorni * 86400, 3600, dtype=np.int64)
    giorno = (t // 86400 + 3) % 7
    t = t[(giorno < 5) | ((giorno == 6) & (t % 86400 >= 22 * 3600))]
    chiusure = prezzo + np.cumsum(rng.normal(0, 0.001, len(t)))
    aperture = np.r_[prezzo, chiusure[:-1]]
    r = np.abs(rng.normal(0, 0.0005, (len(t), 2)))
    prezzi = np.c_[aperture, np.maximum(aperture, chiusure) + r[:, 0], np.minimum(aperture, chiusure) - r[:, 1],
                   chiusure]
    m = minuti(strumento, t.tolist(), [tuple(x) for x in prezzi])
    m.passo = 3600
    return m


def _sensi():
    candele.SESSIONI.update({"EURUSD": "18", "GBPUSD": "18"})
    return Sensi.da([("EURUSD", _ore("EURUSD", utc(2018, 1, 1), 500)),
                     ("GBPUSD", _ore("GBPUSD", utc(2019, 6, 3), 200, seme=2, prezzo=1.3))])


def test_le_candele_con_gli_orari_di_tradingview():
    candele.SESSIONI["EURUSD"] = "18"
    c = candele_di(_ore("EURUSD", utc(2019, 1, 7), 120))
    assert set(c) == set(TF_NAMELESS)
    ny = lambda t: ((t + scarti_ny(t)) % 86400) // 3600
    # 0, 4, 8, 12, 16, 20 italiane: le 18, 22, 2, 6, 10, 14 di New York.
    assert set(ny(c[TF.H4].inizio).tolist()) <= {18, 22, 2, 6, 10, 14}
    assert set(ny(c[TF.D1].inizio).tolist()) == {18}
    assert set(ny(c[TF.H6].inizio).tolist()) <= {18, 0, 6, 12}
    # I 3 mesi vengono dai mesi: aprono con il primo mese del trimestre.
    assert c[TF.Q3].inizio[0] == c[TF.MN].inizio[0]


def test_ogni_ora_vede_solo_candele_gia_chiuse_del_suo_mercato():
    s = _sensi()
    assert s.nomi == ["EURUSD", "GBPUSD"]
    f_ore = s.fine[0]
    for k in range(len(TF_NAMELESS)):
        e = s.entro[k]
        p = s.chi
        dentro = e >= s.primo[p, k]
        assert (s.fine[k][e[dentro]] <= f_ore[dentro]).all()
        # La candela dopo, se e' dello stesso pezzo, chiude dopo l'ora.
        dopo = e + 1
        fine_pezzo = np.r_[s.primo[1:, k], len(s.fine[k])][p]
        ok = dopo < fine_pezzo
        assert (s.fine[k][dopo[ok]] > f_ore[ok]).all()
    # Il secondo pezzo non vede mai le candele del primo.
    j = np.flatnonzero(s.chi == 1)
    assert (s.entro[D1][j] >= s.primo[1, D1] - 1).all()


def test_gli_istanti_hanno_storia_dietro():
    s = _sensi()
    j = s.istanti(0, 2 ** 40)
    assert len(j) and (s.entro[D1][j] - s.primo[s.chi[j], D1] >= 14).all()
    assert (j - s.primo[s.chi[j], 0] >= 24).all()
    assert not len(s.istanti(0, utc(2018, 1, 10)))


def test_gli_occhi_non_vedono_niente_dopo_il_taglio():
    torch = pytest.importorskip("torch")
    from nvm.nameless.occhi import Lettore, Occhi, nascondi
    s = _sensi()
    let = Lettore(s)
    j = torch.as_tensor(s.istanti(utc(2019, 1, 1), utc(2019, 3, 1))[::97])
    taglio = j - torch.randint(1, 25, j.shape)
    contenuto, tempo, vuote, dopo = let.guarda(j, taglio)
    fine_taglio = torch.as_tensor(s.fine[0])[taglio]
    for k in range(len(TF_NAMELESS)):
        idx = torch.as_tensor(s.entro[k])[j][:, None] + let.passi
        fine = torch.as_tensor(s.fine[k])[idx.clamp(min=0)]
        viste = ~vuote[:, k] & ~dopo[:, k]
        assert (fine[viste] <= fine_taglio[:, None].expand_as(fine)[viste]).all()
        assert (fine[dopo[:, k]] > fine_taglio[:, None].expand_as(fine)[dopo[:, k]]).all()
    # I prezzi sono rispetto alla chiusura dell'ora del taglio: lei vale zero.
    h1 = dopo[:, 0].sum(1)
    righe = torch.arange(len(j))
    assert torch.allclose(contenuto[righe, 0, -1 - h1, 3], torch.zeros(len(j)), atol=1e-5)

    # Cambiare i prezzi dopo il taglio non cambia quello che la rete dice.
    torch.manual_seed(0)
    rete = Occhi(d=32, strati=1, teste=2).eval()
    with torch.no_grad():
        for p in rete.ricostruisci.parameters():
            p.normal_(0, 0.1)
    nascoste = nascondi(vuote, dopo, torch.ones(len(j), dtype=torch.bool))
    assert torch.equal(nascoste, dopo & ~vuote)
    for r in range(0, len(j), max(1, len(j) // 4)):
        uno, tu = j[r:r + 1], taglio[r:r + 1]
        let = Lettore(s)
        with torch.no_grad():
            prima = rete.indovina(*let.guarda(uno, tu)[:3], nascoste[r:r + 1])
            pezzo = int(s.chi[int(uno)])
            for k in range(len(TF_NAMELESS)):
                fine_pezzo = s.primo[pezzo + 1, k] if pezzo + 1 < len(s.primo) else len(s.fine[k])
                let.prezzi[k][int(s.entro[k][int(tu)]) + 1:fine_pezzo] += 5.0
            c2, t2, v2, d2 = let.guarda(uno, tu)
            poi = rete.indovina(c2, t2, v2, nascoste[r:r + 1])
        assert torch.equal(d2, dopo[r:r + 1])
        assert torch.allclose(prima[nascoste[r:r + 1]], poi[nascoste[r:r + 1]], atol=1e-5)
        assert not torch.allclose(c2[d2], contenuto[r:r + 1][d2])      # i prezzi dopo il taglio sono cambiati davvero


def test_chi_copia_e_la_rete_appena_nata():
    torch = pytest.importorskip("torch")
    from nvm.nameless.occhi import LUNGHEZZA, Occhi, copia, vicinato
    contenuto = torch.zeros(1, len(TF_NAMELESS), LUNGHEZZA, 5)
    contenuto[0, :, :, :4] = torch.arange(LUNGHEZZA, dtype=torch.float32)[None, :, None]
    vuote = torch.zeros(1, len(TF_NAMELESS), LUNGHEZZA, dtype=torch.bool)
    vuote[0, :, :3] = True
    nascoste = torch.zeros_like(vuote)
    nascoste[0, 0, [3, 10, 11, 39]] = True
    previsione, ok = copia(contenuto, vuote, nascoste)
    # La candela 3 non ha una candela vista prima (0-2 sono vuote); la 11 copia la 9 (la 10 e' nascosta anche lei).
    assert ok[0, 0].nonzero().flatten().tolist() == [10, 11, 39]
    assert previsione[0, 0, [10, 11, 39], 0].tolist() == [9.0, 9.0, 38.0]
    # Accanto a ogni candela la vista prima e la vista dopo: per la 10 la 9 e la 12; la 39 non ha niente dopo.
    v = vicinato(contenuto, vuote, nascoste)[0, 0]
    assert v[10].tolist() == [9.0] * 4 + [1.0] + [12.0] * 4 + [1.0]
    assert v[39].tolist() == [38.0] * 4 + [1.0] + [0.0] * 5
    assert v[3].tolist()[:5] == [0.0] * 5
    # Appena nata la rete non corregge niente: dice quello che dice chi copia.
    rete = Occhi(d=32, strati=1, teste=2).eval()
    with torch.no_grad():
        uguale = rete.indovina(contenuto, torch.zeros(1, len(TF_NAMELESS), LUNGHEZZA, 4), vuote, nascoste)
    assert torch.equal(uguale, previsione)


def test_la_scuola_si_ferma_e_da_l_esame(tmp_path):
    pytest.importorskip("torch")
    from kaggle_rete import occhi as K
    esame = {"caso": {"1h": {"rete": 0.1, "copia": 0.2, "candele": 500},
                      "12m": {"rete": 0.9, "copia": 0.2, "candele": 10}},
             "futuro": {"1h": {"rete": 0.1, "copia": 0.3, "candele": 900}}}
    # Dove ci sono poche candele non conta.
    assert K.passa(esame)
    esame["futuro"]["1h"]["rete"] = 0.31
    assert not K.passa(esame)
    assert K.voto(esame["caso"]) == pytest.approx(0.5)
    assert K.famiglia("BTCUSD") == "crypto" and K.famiglia("XAUEUR") == "metalli"
    assert K.famiglia("USDMXN") == "forex" and K.famiglia("AUS200") == "indici"
    assert K.famiglia("EURUSD dal 2002-02-18") == "forex"
