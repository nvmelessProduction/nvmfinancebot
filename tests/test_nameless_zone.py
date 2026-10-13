"""Le materie e le zone di Nameless (fase 2): le risposte delle regole delle foto, all'ora giusta, senza futuro."""

from types import SimpleNamespace

import numpy as np
import pytest

from nvm.agenti import foto
from nvm.agenti.cacciatore import Verso
from nvm.dati import candele
from nvm.nameless import materie as M
from nvm.nameless.sensi import TF_NAMELESS, Sensi
from nvm.tempo import TF, utc
from tests.test_nameless_occhi import _ore


def test_le_foto_sono_quelle_dello_strumento_delle_foto():
    from strumenti.foto import FOTO
    assert tuple(tuple(f) for f in FOTO) == M.FOTO


def test_il_piano_e_quello_del_bot():
    from nvm.vivo import giro
    rng = np.random.default_rng(3)
    for _ in range(400):
        corto = bool(rng.integers(2))
        segno = -1 if corto else 1
        ingresso = 1.1
        stop = ingresso - segno * rng.uniform(0.0005, 0.003)
        tp1 = ingresso + segno * rng.uniform(-0.001, 0.006)
        ob = SimpleNamespace(prezzo=float(rng.choice([tp1, tp1 + segno * rng.uniform(-0.002, 0.01)])))
        s = SimpleNamespace(strumento="EURUSD", verso=Verso.SHORT if corto else Verso.LONG, short=corto,
                            ingresso=ingresso, stop=stop, tp1=tp1)
        piani = giro.piani_foto(s, ob, None, 0)
        assert M.piano(s, ob) == ((piani[1] or piani[0]) is not None)


def _pezzo():
    candele.SESSIONI.update({"EURUSD": "18"})
    return _ore("EURUSD", utc(2017, 1, 2), 900, seme=5)


def test_le_materie_stanno_all_ora_della_candela_2_e_non_guardano_il_futuro():
    torch = pytest.importorskip("torch")  # noqa: F841
    from kaggle_rete.zone import Etichette
    ore = _pezzo()
    s = Sensi.da([("EURUSD", ore)])
    m = M.Materie.da(ore)
    et = Etichette(s, {"EURUSD": m}, scrivi=lambda t: None)
    assert et.scarti == {"crt": 0, "candele": 0}
    # Ogni CRT sta all'ultima ora della sua candela 2, dove la candela 2 e' l'ultima chiusa.
    for i, tf in enumerate(M.TF_CRT):
        k = TF_NAMELESS.index(tf)
        r = m.crt[tf]
        assert len(r["ora"]) > 0
        assert (s.entro[k][r["ora"]] == r["k2"]).all()
        assert (et.crt["crt"][r["ora"], i] == r["verso"]).all()
        assert (et.crt["entra"][r["ora"], i] == np.where(r["entra"], r["verso"], 0)).all()
        # La candela 3 apre dopo l'ultima ora della candela 2. A 1 ora, sull'ultima ora del venerdi', la candela 3 delle
        # regole e' l'ora dopo, a mercato chiuso: la prossima ora vera arriva la domenica.
        if tf is not TF.H1:
            assert (s.prossimo[r["ora"]] <= r["n3"]).all()
    # Le risposte sulle candele a un'ora: quelle delle regole col quadro tagliato a quell'ora (niente futuro).
    rng = np.random.default_rng(1)
    j = np.sort(rng.choice(s.istanti(0, 2 ** 62), size=40, replace=False))
    y = et.candele(s, j)
    for n, jj in enumerate(j):
        t = int(s.prossimo[jj])
        q = foto.Quadro.da(ore.fra(0, t), t)
        for i, tf in enumerate(M.TF_CANDELA):
            c = q.candele[tf]
            kk = int(np.searchsorted(c.fine, t, side="right")) - 1
            if kk < 1:
                continue
            assert y["direzione"][n, i] == foto.bias_candela(c, kk)[0] + 1
            a = foto.accettazione(q, tf, t)
            atteso = 0 if a is None or a.preso else (1 if a.verso > 0 else 2)
            assert y["accetta"][n, i] == atteso, (tf, jj)


def test_le_zone_rispondono_a_ogni_materia():
    torch = pytest.importorskip("torch")
    from nvm.nameless.occhi import LUNGHEZZA, Occhi
    from nvm.nameless.zone import USCITE_CANDELA, USCITE_CRT, Zone, parte
    rete = Zone(Occhi(d=32, strati=1, teste=2)).eval()
    b = 3
    contenuto = torch.zeros(b, len(TF_NAMELESS), LUNGHEZZA, 5)
    tempo = torch.zeros(b, len(TF_NAMELESS), LUNGHEZZA, 4)
    vuote = torch.zeros(b, len(TF_NAMELESS), LUNGHEZZA, dtype=torch.bool)
    with torch.no_grad():
        crt, candela = rete(contenuto, tempo, vuote)
    assert crt.shape == (b, len(M.TF_CRT), 15) and candela.shape == (b, len(M.TF_CANDELA), 6)
    assert parte(crt, "entra", USCITE_CRT).shape[-1] == 3 and parte(candela, "accetta", USCITE_CANDELA).shape[-1] == 3


def test_le_metriche_non_si_fanno_ingannare_dal_niente():
    pytest.importorskip("torch")
    from kaggle_rete.zone import metriche
    veri = np.r_[np.zeros(980, np.int8), np.ones(20, np.int8)]
    sempre_niente = np.zeros(1000, np.int64)
    m = metriche(sempre_niente, veri, 3)
    assert m["giuste"] == pytest.approx(0.98)
    assert m["media dei richiami"] == pytest.approx(0.5)
