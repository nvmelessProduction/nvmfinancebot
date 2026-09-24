"""La base: la catena intera su una passeggiata casuale, e il bootstrap a blocchi."""

import numpy as np

from nvm.dati.candele import costruisci
from nvm.prova.base import Risultato, opera, riassumi
from nvm.agenti.cacciatore import Verso
from nvm.prova.campo import Uscita
from nvm.tempo import TF, ny
from tests.aiuti import passeggiata


def test_la_catena_gira_e_su_una_passeggiata_non_trova_miracoli():
    m = passeggiata("EURUSD", ny(2026, 1, 4, 17), ny(2026, 3, 27, 17), seme=3)
    alte, basse = costruisci(m, TF.H4), costruisci(m, TF.M15)
    r = opera(alte, basse, ny(2026, 1, 11, 17), ny(2026, 3, 27, 17))
    assert len(r) > 30
    s = riassumi(r)
    # Su un caso puro il vantaggio atteso e' zero meno i costi: l'intervallo
    # deve contenere lo zero o stare sotto.
    assert s.basso < 0.05


def test_il_bootstrap_a_blocchi_e_piu_largo_se_le_prove_sono_la_stessa():
    def risultati(erre, settimane):
        return [Risultato("EURUSD", TF.D1, TF.H1, Verso.SHORT, int(w) * 7 * 86400, float(e), Uscita.STOP, False, 0.0, 1.0)
                for e, w in zip(erre, settimane)]
    rng = np.random.default_rng(1)
    e = rng.normal(0.1, 1, 60)
    indipendenti = riassumi(risultati(np.repeat(e, 5), np.arange(300)))
    a_blocchi = riassumi(risultati(np.repeat(e, 5), np.repeat(np.arange(60), 5)))
    assert (a_blocchi.alto - a_blocchi.basso) > 1.8 * (indipendenti.alto - indipendenti.basso)
