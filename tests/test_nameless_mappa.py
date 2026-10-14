"""La mappa di Nameless (fase 2b): a ogni ora i livelli e i gap che dicono le regole delle foto, senza futuro."""

import numpy as np
import pytest

from nvm.agenti import foto
from nvm.dati import candele
from nvm.nameless.mappa import CAMPI, ELEMENTI, TF_ACCETTA, TF_GAP, TF_KL, tavole
from nvm.nameless.sensi import Sensi
from nvm.tempo import utc
from tests.test_nameless_occhi import _ore


@pytest.fixture(scope="module")
def mondo():
    torch = pytest.importorskip("torch")
    from nvm.nameless.lettore_mappa import LettoreMappa
    from nvm.nameless.occhi import Lettore
    candele.SESSIONI["EURUSD"] = "18"
    ore = _ore("EURUSD", utc(2016, 1, 4), 1400, seme=21)
    s = Sensi.da([("EURUSD", ore)])
    let = Lettore(s)
    lm = LettoreMappa(s, {"EURUSD": tavole(ore)}, let)
    rng = np.random.default_rng(4)
    j = np.sort(rng.choice(s.istanti(utc(2017, 6, 1), 2 ** 62), size=60, replace=False))
    jt = torch.as_tensor(j)
    rif, scala = let.scala(jt)
    m = lm.leggi(jt, rif, scala).numpy()
    return ore, s, j, m, rif.numpy(), scala.numpy()


def _rel(x, rif, scala):
    return np.arcsinh((x - rif) / scala)


def test_la_mappa_e_quella_delle_regole(mondo):
    ore, s, j, m, rif, scala = mondo
    assert m.shape == (len(j), len(ELEMENTI), CAMPI)
    visti = {"gap": 0, "toccati": 0, "fasi 2": 0}
    for n, jj in enumerate(j):
        t = int(s.prossimo[jj])
        q = foto.Quadro.da(ore.fra(0, t), t)
        e = 0
        # I key level e se il prezzo li ha gia' presi dopo la fine del loro periodo.
        for liv in foto.livelli_prima(q, t, TF_KL):
            fine = foto.fine_candela(liv.inizio, liv.tf, foto.calendario("EURUSD"))
            a = int(np.searchsorted(q.ore.inizio, fine))
            dopo = q.ore.bid[a:, 1] if liv.alto else q.ore.bid[a:, 2]
            preso = bool(len(dopo)) and bool((dopo.max() > liv.prezzo) if liv.alto else (dopo.min() < liv.prezzo))
            riga = m[n, ELEMENTI.index(f"{liv.tf.value} {'massimo' if liv.alto else 'minimo'}")]
            assert riga[0] == pytest.approx(_rel(liv.prezzo, rif[n], scala[n]), abs=1e-4)
            assert bool(riga[2]) == preso and riga[5] == 1
        # Le accettazioni.
        for tf in TF_ACCETTA:
            a = foto.accettazione(q, tf, t)
            riga = m[n, ELEMENTI.index(f"accettazione {tf.value}")]
            if a is None:
                assert riga[5] == 0
                continue
            assert riga[5] == 1 and riga[2] == (a.verso > 0) and riga[3] == (a.verso < 0)
            assert riga[0] == pytest.approx(_rel(a.livello, rif[n], scala[n]), abs=1e-4)
            assert bool(riga[4]) == a.preso
        # I gap: il piu' vicino di ogni tipo, come lo vedono le regole a quell'ora.
        for tf in TF_GAP:
            gaps = foto.gap_di(q, tf, t)
            for quale in ("rialzista muro", "rialzista target", "ribassista muro", "ribassista target",
                          "rialzista toccato", "ribassista toccato"):
                rialz = quale.startswith("rialzista")
                if quale.endswith("toccato"):
                    scelti = [g for g in gaps if g.rialzista == rialz and g.toccato is not None and g.riempito is None]
                else:
                    scelti = [g for g in gaps if g.rialzista == rialz and g.toccato is None and
                              g.terza_accetta == quale.endswith("muro")]
                riga = m[n, ELEMENTI.index(f"gap {tf.value} {quale}")]
                if not scelti:
                    assert riga[5] == 0, (tf, quale, jj)
                    continue
                g = min(scelti, key=lambda g: abs(g.bordo - rif[n]))
                visti["gap"] += 1
                assert riga[5] == 1
                assert riga[0] == pytest.approx(_rel(g.bordo, rif[n], scala[n]), abs=1e-3), (tf, quale, jj)
                if quale.endswith("toccato"):
                    visti["toccati"] += 1
                    f = foto.fase(q, g, t)
                    assert bool(riga[2]) == (f.numero >= 2) and bool(riga[3]) == (f.numero >= 3), (tf, quale, jj)
                    if f.numero >= 2:
                        visti["fasi 2"] += 1
                        assert riga[1] == pytest.approx(_rel(f.estremo, rif[n], scala[n]), abs=1e-3)
        e += 1
    # Abbastanza casi per essere una prova vera.
    assert visti["gap"] > 100 and visti["toccati"] > 20 and visti["fasi 2"] > 5, visti
