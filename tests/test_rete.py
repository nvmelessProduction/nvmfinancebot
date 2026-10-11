"""La rete neurale (`nvm/rete/`): quello che vede, le risposte degli agenti con cui impara, la sua forma."""

import numpy as np
import pytest

from nvm.agenti import foto as F
from nvm.agenti.cacciatore import Verso
from nvm.rete.etichette import DOMANDE, etichette
from nvm.rete.finestre import CARATTERISTICHE, LUNGHEZZA, TF_RETE, Storia, finestre
from nvm.tempo import TF
from tests.test_foto import ORA, _foto_base, _ore


def _storia_lunga():
    """La foto base dei test delle foto, con due anni di ore tranquille prima."""
    ore, n3 = _foto_base()
    righe = [(int(t), *(float(x) * ore.punto for x in b)) for t, b in zip(ore.t, ore.bid)]
    prima = [(int(ore.t[0]) - k * ORA, 1.10, 1.1003 + 0.0001 * (k % 7), 1.0997 - 0.0001 * (k % 5), 1.10)
             for k in range(24 * 500, 0, -1)]
    return _ore(prima + righe), n3


def test_le_finestre_non_guardano_il_futuro():
    ore, n3 = _storia_lunga()
    st = Storia.da(ore)
    x, vuote = finestre(st, np.array([n3]))
    assert x.shape == (1, len(TF_RETE), LUNGHEZZA, CARATTERISTICHE) and vuote.shape == (1, len(TF_RETE), LUNGHEZZA)
    # L'ultima candela a 4 ore e' la candela 2, chiusa proprio a n3; quella dopo non c'e'.
    h4 = st.candele[TF.H4]
    k = int(np.searchsorted(h4.fine, n3, side="right")) - 1
    assert int(h4.fine[k]) == n3
    # Cambiare le ore dopo n3 non cambia niente.
    dopo = ore.t >= n3
    ore.bid[dopo] += 500
    x2, _ = finestre(Storia.da(ore), np.array([n3]))
    np.testing.assert_array_equal(x, x2)
    # I prezzi sono rispetto all'ultima chiusura a 1 ora: lei vale zero.
    assert x[0, TF_RETE.index(TF.H1), -1, 3] == pytest.approx(0.0, abs=1e-6)
    assert not vuote[0, TF_RETE.index(TF.H1)].any()


def test_le_risposte_sono_quelle_degli_agenti():
    ore, n3 = _storia_lunga()
    st = Storia.da(ore)
    t = st.istanti(n3 - 30 * 86400, n3 + 1)
    assert t[-1] == n3
    e = etichette(ore, t)
    assert set(e) == {nome for nome, _ in DOMANDE}
    # Il CRT a 4 ore della foto base: acquisto (classe 1), col DL preso.
    assert e["crt H4"][-1] == 1
    q = F.Quadro.da(ore, n3 + 1)
    s = next(x for x in F.trova(q, TF.H4, n3, n3) if x.verso is Verso.LONG)
    assert e["setup H4"][-1] == (1 if s.presi and F.direzione(q, s).ok else 0)
    # La direzione del giorno: la candela appena chiusa rispetto a quella prima, come la legge il Bias.
    c = q.candele[TF.D1]
    k = int(np.searchsorted(c.fine, n3, side="right")) - 1
    assert e["direzione D1"][-1] == F.bias_candela(c, k)[0] + 1


def test_la_rete_risponde_a_ogni_domanda():
    torch = pytest.importorskip("torch")
    from nvm.rete.modello import Occhi
    ore, n3 = _storia_lunga()
    x, v = finestre(Storia.da(ore), np.array([n3, n3 - 4 * ORA]))
    rete = Occhi()
    riassunto, candele = rete(torch.from_numpy(x), torch.from_numpy(v))
    risposte = rete.rispondi(riassunto, candele)
    assert len(risposte) == len(DOMANDE) and all(r.shape == (2, 3) for r in risposte)
    assert rete.ricostruisci(candele).shape == (2, len(TF_RETE), LUNGHEZZA, 4)
