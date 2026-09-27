"""I cervelli degli agenti (`nvm/cervello/`)."""

import numpy as np

from nvm.cervello.rete import Rete
from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI


def _esempi(n=4000, seme=0):
    rng = np.random.default_rng(seme)
    x = rng.normal(size=(n, 3))
    # Arriva al primo obiettivo quando il primo segnale e' alto e il terzo basso, con rumore.
    y = (x[:, 0] - x[:, 2] + rng.normal(0, 0.7, n) > 0).astype(float)
    return x, y


def test_un_cervello_impara_dagli_esempi_e_ricorda_nei_pesi():
    x, y = _esempi()
    rete = Rete.allena(x[:3000], y[:3000])
    p = rete.probabilita(x[3000:])
    assert np.mean((p > 0.5) == y[3000:]) > 0.8
    copia = Rete.da_dati(rete.come_dati())
    assert np.allclose(copia.logit(x[:5]), rete.logit(x[:5]))


def test_dal_vivo_impara_un_passo_alla_volta():
    x, y = _esempi()
    rete = Rete.allena(x, y)
    caso = np.array([[2.0, 0.0, -2.0]])
    prima = float(rete.logit(caso)[0])
    rete.aggiorna(np.repeat(caso, 50, axis=0), np.zeros(50), passi=20, passo=0.05)
    assert float(rete.logit(caso)[0]) < prima      # ha sbagliato: ci crede meno


def test_la_squadra_giudica_si_confronta_e_il_capo_decide():
    x, y = _esempi(3000)
    rng = np.random.default_rng(1)
    # Ogni agente vede solo un pezzo: due agenti vedono i segnali utili, gli altri rumore.
    v = {a: rng.normal(size=(len(y), 2)) for a in AGENTI}
    v["Grilletto"] = x[:, [0]]
    v["Bias"] = x[:, [2]]
    sq = Squadra.allena({a: m[:2500] for a, m in v.items()}, y[:2500])
    primo, dopo, p = sq.giudica({a: m[2500:] for a, m in v.items()})
    assert set(primo) == set(dopo) == set(AGENTI)
    assert np.mean((p > 0.5) == y[2500:]) > 0.8
    # Dopo il confronto l'Orario, che vede solo rumore, ha imparato ad ascoltare chi vede giusto.
    assert np.corrcoef(dopo["Orario"], y[2500:])[0, 1] > np.corrcoef(primo["Orario"], y[2500:])[0, 1]
