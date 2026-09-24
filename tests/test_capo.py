"""Il Capo: la logistica, il guadagno atteso, e il cammino che non guarda avanti."""

from datetime import datetime, timezone

import numpy as np

from nvm.agenti.capo import COLONNE, Capo, Logistica
from nvm.prova.cammino import Tabella, cammino, giudica


def test_la_logistica_ritrova_i_pesi():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(20000, 2))
    p = 1 / (1 + np.exp(-(0.5 + 1.5 * x[:, 0] - 1.0 * x[:, 1])))
    y = (rng.random(20000) < p).astype(float)
    w = Logistica(penalita=0.0).allena(x, y).pesi
    assert np.allclose(w, [0.5, 1.5, -1.0], atol=0.08)


def test_il_guadagno_atteso_segue_la_formula():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(3000, len(COLONNE)))
    tp1 = rng.random(3000) < 0.4
    tp2 = tp1 & (rng.random(3000) < 0.5)
    capo = Capo.allena(x, tp1, tp2)
    rr1, rr2, costi = np.full(3000, 1.0), np.full(3000, 3.0), np.full(3000, 0.05)
    e = capo.valore_atteso(x, rr1, rr2, costi)
    # Colonne a caso: il Capo non sa niente in piu', e stima circa 0.4 e 0.5.
    atteso = 0.4 * (0.5 * 1 + 0.5 * 0.5 * 3) - 0.6 - 0.05
    assert abs(np.median(e) - atteso) < 0.05


def _tabella(seme: int) -> Tabella:
    rng = np.random.default_rng(seme)
    n = 6000
    t0, t1 = datetime(2006, 1, 1, tzinfo=timezone.utc).timestamp(), datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp()
    quando = np.sort(rng.integers(int(t0), int(t1), n))
    x = rng.integers(0, 2, size=(n, len(COLONNE))).astype(float)
    x[:, -3:] = rng.normal(1, 0.2, size=(n, 3))
    # Una colonna conta davvero: col si' il primo target arriva piu' spesso.
    tp1 = rng.random(n) < np.where(x[:, 3] == 1, 0.6, 0.3)
    tp2 = tp1 & (rng.random(n) < 0.4)
    rr1, rr2 = np.full(n, 1.0), np.full(n, 2.0)
    erre = np.where(tp2, 1.5, np.where(tp1, 0.5, -1.0)) - 0.05
    return Tabella(x, quando, quando + 5 * 86400, erre, tp1, tp2, rr1, rr2, np.full(n, 0.05))


def test_il_cammino_non_guarda_avanti():
    t = _tabella(2)
    c = cammino(t, 2008, 2013)
    # Si cambia il futuro dal 2010 in poi: le scelte fino al 2010 compreso non cambiano.
    t2 = _tabella(2)
    dopo = t2.chiusa >= datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp()
    rng = np.random.default_rng(9)
    t2.tp1[dopo] = rng.random(dopo.sum()) < 0.5
    t2.tp2[dopo] = t2.tp1[dopo] & (rng.random(dopo.sum()) < 0.5)
    c2 = cammino(t2, 2008, 2013)
    fino_al_2010 = t.anno <= 2010
    assert np.array_equal(c.atteso[fino_al_2010], c2.atteso[fino_al_2010], equal_nan=True)
    assert not np.array_equal(c.atteso[t.anno == 2012], c2.atteso[t.anno == 2012])


def test_il_capo_sceglie_la_colonna_che_conta_e_il_giudizio_lo_vede():
    t = _tabella(3)
    c = cammino(t, 2008, 2013)
    scelte = c.scelte
    assert scelte.any()
    assert t.x[scelte, 3].mean() > 0.9
    g = giudica(t.quando[scelte], t.erre[scelte], t.quando[c.giudicati], t.erre[c.giudicati], k=4)
    assert g.differenza > 0.2 and g.basso > 0 and g.anni_concordi == 1.0
