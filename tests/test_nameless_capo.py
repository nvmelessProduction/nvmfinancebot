"""Il Capo di Nameless (fase 3): gli esiti dei setup come li gestisce il bot, coi costi, e il bilancio dell'esame."""

import numpy as np
import pytest

from nvm.agenti.cacciatore import Verso
from nvm.dati import candele
from nvm.dati.candele import costruisci
from nvm.nameless import esiti as E
from nvm.nameless import materie as M
from nvm.prova.campo import Operazione
from nvm.tempo import TF, utc
from tests.test_nameless_occhi import _ore


@pytest.fixture(scope="module")
def pezzo():
    candele.SESSIONI["EURUSD"] = "18"
    ore = _ore("EURUSD", utc(2018, 1, 1), 400, seme=11)
    m = M.Materie.da(ore)
    return ore, m, E.esiti(ore, m)


def test_ogni_esito_e_quello_del_simulatore_del_bot(pezzo):
    ore, m, e = pezzo
    assert len(e["erre"]) > 50
    h1 = costruisci(ore, TF.H1)
    fine_g, spread_g = E.spread_a(ore)
    for n in range(0, len(e["erre"]), max(1, len(e["erre"]) // 25)):
        tf = M.TF_CRT[int(e["tf"][n])]
        r, k = m.crt[tf], int(e["riga"][n])
        assert r["entra"][k]
        corto = r["verso"][k] == M.CORTO
        s = float(spread_g[int(np.searchsorted(fine_g, r["n3"][k], side="right")) - 1])
        assert e["spread"][n] == pytest.approx(s)
        ob, tp1, ingresso = float(r["obiettivo"][k]), float(r["tp1"][k]), float(r["ingresso"][k])
        rischio = abs(ingresso - float(r["stop"][k]))
        segno = -1 if corto else 1
        al_finale = ob != tp1 and segno * (ob - tp1) >= 0 and abs(ob - ingresso) >= rischio - 1e-12
        op = Operazione("EURUSD", Verso.SHORT if corto else Verso.LONG, int(r["n3"][k]),
                        ingresso + (0.0 if corto else s), float(r["stop"][k]), tp1, ob if al_finale else tp1,
                        parziale=0.25 if al_finale else 1.0, pareggio=al_finale)
        atteso = E.esito(op, h1, s, int(r["n3"][k]) + E.TETTO[tf])
        assert e["erre"][n] == pytest.approx(atteso.erre, abs=1e-5)


def test_i_costi_doppi_non_aiutano_e_le_aperte_non_contano(pezzo):
    ore, m, e = pezzo
    # In media i costi doppi peggiorano. Una per una no sempre: lo stop resta allo stesso prezzo e il rischio si
    # allarga, quindi un'uscita oltre lo stop pesa un po' meno in R (il bot dimensiona cosi').
    assert e["erre_doppi"].mean() < e["erre"].mean()
    vinte = e["erre"] > 0.5
    assert (e["erre_doppi"][vinte] <= e["erre"][vinte] + 1e-6).all()
    # Le ultime operazioni restano aperte quando finiscono i dati: segnate, non contano.
    fine = int(ore.t[-1]) + 3600
    for n in np.flatnonzero(~e["finita"]):
        tf = M.TF_CRT[int(e["tf"][n])]
        assert m.crt[tf]["n3"][int(e["riga"][n])] + E.TETTO[tf] > fine
        assert E.USCITE[int(e["uscita"][n])] == "scaduta"


def test_le_caratteristiche_del_setup(pezzo):
    from nvm.nameless.capo import SETUP, setup
    _, m, e = pezzo
    i = int(e["tf"][0])
    sel = np.flatnonzero(e["tf"] == i)
    x = setup(m.crt[M.TF_CRT[i]], e["riga"][sel], i, e["spread"][sel], E.SPREAD_RANGE)
    assert x.shape == (len(sel), len(SETUP)) and np.isfinite(x).all()
    assert (x[:, i] == 1).all() and x[:, :len(M.TF_CRT)].sum(1).max() == 1


def test_il_bilancio_per_settimane():
    pytest.importorskip("torch")
    from kaggle_rete.capo import bilancio
    rng = np.random.default_rng(0)
    b = bilancio(np.ones(100), np.arange(100) // 10, rng)
    assert b["media"] == 1.0 and b["sicura"] == pytest.approx(1.0) and b["totale"] == 100
    # Una sola settimana fortunata non basta: la sicurezza scende sotto la media.
    erre = np.r_[np.full(10, 20.0), np.full(90, -1.0)]
    b = bilancio(erre, np.r_[np.zeros(10), np.arange(1, 91)], rng)
    assert b["media"] > 0 and b["sicura"] < b["media"]
    assert bilancio(np.zeros(0), np.zeros(0), rng)["operazioni"] == 0


def test_quanti_prenderne_si_sceglie_sul_controllo():
    pytest.importorskip("torch")
    from kaggle_rete.capo import MINIMO_PRESI, migliore_soglia
    rng = np.random.default_rng(1)
    voto = rng.normal(size=2000)
    # I setup col voto piu' alto guadagnano, gli altri perdono: si prende la cima.
    erre = np.where(voto > np.quantile(voto, 0.9), 1.0, -0.5)
    m = migliore_soglia(voto, erre)
    assert m["quota"] == 0.1 and m["presi"] >= MINIMO_PRESI and m["totale"] > 0
    # Se perdono tutti non si prende niente.
    m = migliore_soglia(voto, -np.ones(2000))
    assert m["presi"] == 0 and m["soglia"] == float("inf")
