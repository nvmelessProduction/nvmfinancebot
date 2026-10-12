"""La scuola dell'esperienza (`kaggle_rete/esperienza.py`): i casi del bot con il loro trade simulato."""

import numpy as np

from kaggle_rete.esperienza import SCHEDA, SPREAD, casi, con_spread
from nvm.agenti import foto as F
from nvm.agenti.cacciatore import Verso
from nvm.prova.campo import Operazione, simula
from nvm.tempo import TF
from nvm.vivo.giro import setup_buono
from tests.test_rete import _storia_lunga


def test_l_ask_e_il_bid_piu_lo_spread():
    ore, _ = _storia_lunga()
    a = con_spread(ore)
    np.testing.assert_array_equal(a.bid, ore.bid)
    assert np.all((a.ask - a.bid) * ore.punto == np.round(SPREAD["EURUSD"] / ore.punto) * ore.punto)


def test_il_caso_del_crt_a_4_ore_e_il_trade_del_bot():
    ore, n3 = _storia_lunga()
    c = casi(ore, n3 - 86400, n3 + 1, scrivi=lambda _: None)
    k = int(np.flatnonzero(c.t == n3)[0])
    riga = dict(zip(SCHEDA, c.scheda[k]))
    # Alla stessa apertura c'e' anche un CRT a 6 ore nello stesso verso: come dal vivo, vale il timeframe piu' grande.
    assert riga["tf H6"] == 1 and riga["tf H4"] == 0 and riga["vendita"] == 0
    # Il risultato e' quello del trade che il bot apre: il 25% al TP1 col pareggio e il resto al target finale.
    q = F.Quadro.da(ore, int(ore.t[-1]) + 3600)
    s = next(x for x in F.trova(q, TF.H6, n3, n3) if x.verso is Verso.LONG and setup_buono(x))
    qq = q.taglia(n3)
    ob = F.obiettivo_finale(qq, s)
    tutto = ob.prezzo == s.tp1
    op = Operazione(s.strumento, s.verso, n3, s.ingresso, s.stop, s.tp1, ob.prezzo,
                    parziale=1.0 if tutto else F.PARZIALE, pareggio=not tutto)
    assert c.erre[k] == np.float32(simula(op, q.candele[TF.H1], n3 + 40 * 86400).erre)
    assert riga["rr target"] == np.float32(abs(ob.prezzo - op.ingresso) / op.rischio)
