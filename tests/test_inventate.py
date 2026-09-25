"""Gli agenti inventano domande: nuove, mai ripetute, giuste, e tenute solo se servono."""

from types import SimpleNamespace as NS

import numpy as np

from nvm.agenti import inventate
from nvm.agenti.cacciatore import CRT, MAI, Motivo, Verso
from nvm.agenti.capo import COLONNE, COLONNE_BASE
from nvm.agenti.inventate import Contesto, Domanda, inventa, rispondi
from nvm.tempo import TF, ny, utc
from tests.aiuti import candele


def test_ogni_agente_inventa_domande_nuove_e_non_le_ripete():
    rng = np.random.default_rng(0)
    prime = inventa("Key level", rng, set(), quante=3)
    assert len(prime) == 3 and len({d.chiave for d in prime}) == 3
    assert all(d.agente == "Key level" and d.famiglia in ("livello", "sessione") for d in prime)
    dopo = inventa("Key level", np.random.default_rng(0), {d.chiave for d in prime}, quante=3)
    assert not {d.chiave for d in prime} & {d.chiave for d in dopo}
    assert inventa("Nessuno", rng, set()) == []


def test_le_domande_tenute_si_salvano_e_diventano_colonne(tmp_path):
    d = Domanda("Orario", "giorno", (("giorno", 1),))
    assert d.nome == "scatta di martedì"
    inventate.salva([d], tmp_path / "domande.json")
    assert inventate.tenute(tmp_path / "domande.json") == [d]
    assert COLONNE[:len(COLONNE_BASE)] == COLONNE_BASE


def _ore():
    """Due giorni di ore: il primo giorno sale, il secondo scende."""
    t0 = ny(2026, 3, 2, 17)        # lunedi' sera: la candela giornaliera di martedi'
    righe = []
    for h in range(48):
        p = 1.10 + (0.0005 * h if h < 24 else 0.012 - 0.0005 * (h - 24))
        righe.append((t0 + h * 3600, p, p + 0.0003, p - 0.0003, p + 0.0002))
    return candele("EURUSD", TF.H1, righe), t0


def _operazione(verso, quando, estremo, ts):
    crt = CRT("EURUSD", TF.D1, TF.H1, verso, ts - 86400, 1.12, 1.10, armato_quando=ts, decaduto_quando=MAI,
              motivo=Motivo.SCADENZA, manipolazione_inizio=ts - 3600, fine_candela_3=MAI,
              estremo_istanti=np.array([quando], np.int64), estremo_valori=np.array([estremo]))
    s = NS(crt=crt, quando=quando, turtle_soup_inizio=ts)
    return NS(scatto=s, ingresso=1.105, rischio=0.002, basso_tf=TF.H1)


def test_le_risposte_guardano_solo_il_passato():
    ore, t0 = _ore()
    # Il contesto come se fossimo alla fine del secondo giorno.
    ctx = Contesto(ore, {TF.D1: _giornaliere(ore)})
    quando = t0 + 47 * 3600
    ts = t0 + 46 * 3600
    # Il giorno prima (il primo) e' salito: per un long e' "a favore", per uno short "contro".
    su = Domanda("Bias", "direzione", (("tf", "D1"), ("verso", "a favore")))
    assert rispondi(su, _operazione(Verso.LONG, quando, 1.10, ts), ctx) == 1.0
    assert rispondi(su, _operazione(Verso.SHORT, quando, 1.13, ts), ctx) == 0.0
    # Lo short che ha superato il massimo del giorno prima ha "preso l'estremo del giorno prima".
    presa = Domanda("Key level", "livello", (("tf", "D1"), ("indietro", 1)))
    massimo = float(ore.bid[:24, 1].max())
    assert rispondi(presa, _operazione(Verso.SHORT, quando, massimo + 0.0001, ts), ctx) == 1.0
    assert rispondi(presa, _operazione(Verso.SHORT, quando, massimo - 0.0001, ts), ctx) == 0.0
    # Il Model#1 un'ora dopo il turtle soup e' "entro 1 candela".
    veloce = Domanda("Grilletto", "velocità", (("candele", 1),))
    assert rispondi(veloce, _operazione(Verso.LONG, quando, 1.10, ts), ctx) == 1.0
    assert rispondi(veloce, _operazione(Verso.LONG, quando + 5 * 3600, 1.10, ts), ctx) == 0.0


def _giornaliere(ore):
    from nvm.dati.candele import Candele
    return Candele("EURUSD", TF.D1, ore.inizio[[0, 24]], ore.inizio[[0, 24]] + 86400,
                   np.array([[ore.bid[0, 0], ore.bid[:24, 1].max(), ore.bid[:24, 2].min(), ore.bid[23, 3]],
                             [ore.bid[24, 0], ore.bid[24:, 1].max(), ore.bid[24:, 2].min(), ore.bid[47, 3]]]),
                   np.zeros((2, 4)), np.ones(2))


def test_la_palestra_riconosce_un_idea_che_serve():
    """Un'idea che separa le operazioni buone dalle cattive migliora la qualita': si tiene.
    Una a caso no."""
    from nvm.prova import allenamento as al
    from nvm.prova.cammino import Tabella
    rng = np.random.default_rng(5)
    n = 8000
    quando = np.sort(rng.integers(utc(2006, 1, 1), utc(2023, 12, 1), n))
    buona = rng.random(n) < 0.3
    tp1 = np.where(buona, rng.random(n) < 0.8, rng.random(n) < 0.3)
    tp2 = tp1 & (rng.random(n) < 0.5)
    erre = np.where(tp2, 2.0, np.where(tp1, 0.5, -1.0))
    x = np.zeros((n, len(COLONNE)))
    x[:, COLONNE.index("RR1")] = 1.0
    x[:, COLONNE.index("RR2")] = 2.0
    t = Tabella(x, quando, quando + 86400, erre, tp1, tp2, np.ones(n), np.full(n, 2.0), np.zeros(n), np.zeros(n, bool))
    colonne = np.c_[buona.astype(float), (rng.random(n) < 0.3).astype(float)]
    oggi = al.misura(t, {}, 2008, 2023)
    utile, a_caso = al.prova_idee(t, colonne, 2008, 2023, processi=1)
    assert al.esame(oggi, utile, prove=12).passa
    assert not al.esame(oggi, a_caso, prove=12).passa


def test_il_cervello_ad_alberi_trova_le_combinazioni_e_si_salva():
    from nvm.agenti.alberi import Alberi
    rng = np.random.default_rng(0)
    n = 12000
    x = rng.integers(0, 2, (n, 6)).astype(float)
    insieme = (x[:, 0] == 1) & (x[:, 3] == 1)
    y = rng.random(n) < np.where(insieme, 0.6, 0.3)
    m = Alberi(alberi=60, foglia=200).allena(x, y)
    p = m.probabilita(x)
    assert p[insieme].mean() > p[~insieme].mean() + 0.2
    assert np.allclose(Alberi.da_dati(m.come_dati()).probabilita(x[:20]), p[:20])
