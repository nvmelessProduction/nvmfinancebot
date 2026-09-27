"""Il Rischio sul conto intero (`nvm/agenti/portafoglio.py`)."""

import numpy as np

from nvm.agenti import portafoglio
from nvm.agenti.portafoglio import Operazioni, gambe, in_comune, puntata, simula

GIORNO = 86400


def test_quello_che_due_operazioni_hanno_in_comune():
    eu, gu = gambe("EURUSD", 1), gambe("GBPUSD", 1)
    assert eu == {"EUR": 1.0, "USD": -1.0}
    assert in_comune(eu, eu) == 1 and in_comune(eu, gambe("EURUSD", -1)) == -1
    assert in_comune(eu, gu) == 0.5                        # tutte e due vendono dollari
    assert in_comune(eu, gambe("USDCHF", 1)) == -0.5       # una vende dollari, l'altra li compra
    assert in_comune(eu, gambe("AUDNZD", 1)) == 0
    assert gambe("GER40", -1) == {"GER40": -1.0, "EUR": 1.0}   # vendere il DAX e' comprare euro
    assert in_comune(gambe("SPX500", 1), gambe("NAS100", 1)) == 0.5


def test_la_puntata_si_riduce_per_le_operazioni_che_vanno_insieme():
    corr = {-1.0: -0.9, -0.5: -0.3, 0.0: 0.0, 0.5: 0.4, 1.0: 0.9}
    eu = gambe("EURUSD", 1)
    da_sola = puntata(0.05, 0.2, eu, [], corr)
    assert da_sola == 0.2 * 0.05
    # GBPUSD comprato gia' aperto all'1%: la nuova rischia meno.
    con_gu = puntata(0.05, 0.2, eu, [(gambe("GBPUSD", 1), 0.01)], corr)
    assert np.isclose(con_gu, 0.01 - 0.4 * 0.01)
    # USDCHF comprato va contro: la nuova puo' rischiare di piu'.
    assert puntata(0.05, 0.2, eu, [(gambe("USDCHF", 1), 0.01)], corr) > da_sola
    # Senza correlazioni: come prima, ognuna da sola.
    assert puntata(0.05, 0.2, eu, [(gambe("GBPUSD", 1), 0.01)], None) == da_sola
    # Troppo esposti: non si entra.
    assert puntata(0.05, 0.2, eu, [(gambe("EURUSD", 1), 0.02)], corr) == 0


def _operazioni(n, legate: bool, seme=1):
    """Coppie di operazioni aperte insieme: EURUSD e GBPUSD comprati, con risultati uguali
    (legate) o indipendenti."""
    rng = np.random.default_rng(seme)
    a = np.where(rng.random(n) < 0.45, 2.0, -1.0)
    b = a if legate else np.where(rng.random(n) < 0.45, 2.0, -1.0)
    entrata = np.repeat(np.arange(n) * 3 * GIORNO, 2) + np.tile([0, 3600], n)
    return Operazioni(entrata, entrata + 2 * GIORNO, np.tile(["EURUSD", "GBPUSD"], n), np.ones(2 * n, np.int8),
                      np.full(2 * n, 0.175), np.column_stack([a, b]).ravel())


def test_le_correlazioni_si_imparano_dalle_operazioni_aperte_insieme():
    legate = portafoglio.correlazioni(_operazioni(400, True))
    sciolte = portafoglio.correlazioni(_operazioni(400, False))
    assert legate[0.5] > 0.9 and abs(sciolte[0.5]) < 0.15
    # Classi senza abbastanza coppie: valgono quanto dice il loro nome.
    assert legate[-1.0] == -1.0 and legate[0.0] == 0.0


def test_il_conto_intero_si_brucia_meno_se_il_rischio_vede_le_operazioni_legate():
    op = _operazioni(400, True)
    corr = portafoglio.correlazioni(op)
    sole = simula(op, 1.0, None)
    insieme = simula(op, 1.0, corr)
    assert insieme.massimo_a_rischio < sole.massimo_a_rischio
    assert insieme.crescita > sole.crescita and insieme.peggior_calo < sole.peggior_calo
    # E impara la parte del Kelly che fa crescere di piu' il conto intero.
    parte, conto = portafoglio.impara(op, corr)
    assert conto.crescita >= insieme.crescita - 1e-12 and 0 < parte <= 1


def test_il_passato_senza_sbirciare():
    op = _operazioni(10, True)
    assert len(op.fino_a(int(op.chiusa[3]) + 1)) == 4
