"""Gli agenti nuovi: Allineamento e Gap (`nvm/agenti/panorama.py`)."""

import numpy as np

from nvm.agenti import panorama
from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import Bias
from nvm.tempo import TF, ny
from tests.aiuti import candele

H = 3600
T0 = ny(2026, 9, 7, 0)      # un lunedi'


def _ore(righe, dal=T0):
    return candele("EURUSD", TF.H1, [(dal + i * H, *r) for i, r in enumerate(righe)])


def test_un_fvg_rialzista_resta_aperto_finche_il_prezzo_non_torna_al_fondo():
    c = _ore([(1.1000, 1.1010, 1.0995, 1.1008),     # 0: massimo 1.1010
              (1.1008, 1.1040, 1.1006, 1.1038),     # 1: la spinta
              (1.1038, 1.1050, 1.1020, 1.1045),     # 2: minimo 1.1020 > 1.1010: buco 1.1010-1.1020
              (1.1045, 1.1048, 1.1015, 1.1030),     # 3: entra nel buco, non lo chiude
              (1.1030, 1.1032, 1.1009, 1.1012)])    # 4: arriva sotto 1.1010: chiuso
    b = panorama.buchi(c)
    assert len(b.basso) == 1 and b.rialzista[0]
    assert (b.basso[0], b.alto[0]) == (1.1010, 1.1020)
    assert b.nato[0] == c.fine[2] and b.chiuso[0] == c.fine[4]
    # A candela 3 chiusa il buco e' aperto e sta fra 1.1030 e 1.1000; a candela 4 chiusa no.
    assert len(panorama.aperti(b, c, int(c.fine[3]), 50, 1.1030, 1.1000)) == 1
    assert len(panorama.aperti(b, c, int(c.fine[4]), 50, 1.1030, 1.1000)) == 0
    # Prima che la terza candela chiuda non si sa ancora che c'e'.
    assert len(panorama.aperti(b, c, int(c.fine[1]), 50, 1.1030, 1.1000)) == 0
    # Fuori dai prezzi guardati, o troppo vecchio, non conta.
    assert len(panorama.aperti(b, c, int(c.fine[3]), 50, 1.1030, 1.1025)) == 0
    assert len(panorama.aperti(b, c, int(c.fine[3]), 1, 1.1030, 1.1000)) == 0


def test_un_fvg_ribassista():
    c = _ore([(1.1050, 1.1055, 1.1040, 1.1042), (1.1042, 1.1043, 1.1010, 1.1012), (1.1012, 1.1030, 1.1005, 1.1008)])
    b = panorama.buchi(c)
    assert len(b.basso) == 1 and not b.rialzista[0]
    assert (b.basso[0], b.alto[0]) == (1.1030, 1.1040) and b.chiuso[0] == panorama.MAI


def test_il_gap_del_weekend_e_quando_si_chiude():
    venerdi = ny(2026, 9, 4, 14)
    ore = candele("EURUSD", TF.H1, [(venerdi, 1.1000, 1.1005, 1.0995, 1.1000),
                                    (T0 - 7 * H, 1.1030, 1.1035, 1.1025, 1.1030),   # domenica sera, apre 30 pip sopra
                                    (T0 - 6 * H, 1.1030, 1.1032, 1.1010, 1.1015),
                                    (T0 - 5 * H, 1.1015, 1.1016, 1.0998, 1.1000)])  # torna a 1.1000: chiuso
    giorni = candele("EURUSD", TF.D1, [(ny(2026, 8, 1, 17) + i * 86400, 1.1, 1.1010, 1.0990, 1.1) for i in range(25)])
    a = panorama.aperture(ore, giorni)
    assert len(a.inizio) == 1 and a.prima[0] == 1.1000 and a.apertura[0] == 1.1030
    assert a.chiuso[0] == ore.fine[3] and abs(a.giorno_medio[0] - 0.0020) < 1e-9
    assert panorama.gap_della_settimana(a, int(ore.fine[2])) == 0
    assert panorama.gap_della_settimana(a, venerdi) is None


def test_il_bias_di_romeo_su_ogni_timeframe():
    # La seconda candela chiude sopra il massimo della prima: prezzi piu' alti.
    c = _ore([(1.1, 1.1010, 1.0990, 1.1005), (1.1005, 1.1020, 1.1000, 1.1015)])
    assert panorama.bias_a(c, int(c.fine[1])) is Bias.RIALZISTA
    assert panorama.bias_a(c, int(c.fine[0])) is Bias.NEUTRO           # una candela sola: non si sa
    assert panorama.a_favore(Bias.RIALZISTA, Verso.LONG) is True
    assert panorama.a_favore(Bias.RIALZISTA, Verso.SHORT) is False
    assert panorama.a_favore(Bias.NEUTRO, Verso.SHORT) is None


def test_le_domande_nuove_hanno_senso_e_un_nome():
    from nvm.agenti import inventate
    rng = np.random.default_rng(0)
    for agente in ("Allineamento", "Gap"):
        tutte = inventate.inventa(agente, rng, set(), quante=30)
        assert tutte and all(inventate.valida(d) for d in tutte)
        assert all(d.nome and d.nome != d.famiglia for d in tutte)
        assert all(inventate.Domanda.da_dati(d.come_dati()) == d for d in tutte)
    assert not inventate.valida(inventate._d("Allineamento", "concordi", da="D1", quanti=4, verso="a favore"))
    assert not inventate.valida(inventate._d("Allineamento", "coppia", primo="W1", secondo="D1", verso="contro"))


def test_la_palestra_fa_provare_prima_il_mestiere_agli_agenti_nuovi():
    from nvm.agenti import inventate
    from nvm.prova.allenamento import idee_della_settimana
    rng = np.random.default_rng(0)
    idee = idee_della_settimana(["Orario", "Gap"], set(), rng)
    assert [d for d in idee if d.agente == "Gap"] == inventate.PRIME["Gap"]
    assert len([d for d in idee if d.agente == "Orario"]) == 2
    provate = {d.chiave for d in inventate.PRIME["Gap"]}
    assert len(idee_della_settimana(["Gap"], provate, rng)) == 2      # poi inventa


def test_un_idea_quasi_riuscita_si_affina_di_un_passo():
    from nvm.agenti import inventate
    from nvm.prova.allenamento import idee_della_settimana
    quasi = inventate._d("Gap", "fvg", tf="H4", candele=50, dove="verso l'obiettivo", tipo="qualunque")
    vicine = inventate.vicine(quasi)
    assert inventate._d("Gap", "fvg", tf="H1", candele=50, dove="verso l'obiettivo", tipo="qualunque") in vicine
    assert inventate._d("Gap", "fvg", tf="H4", candele=100, dove="verso l'obiettivo", tipo="qualunque") in vicine
    assert all(sum(a != b for a, b in zip(v.parametri, quasi.parametri)) == 1 for v in vicine)
    provate = {d.chiave for d in inventate.PRIME["Gap"]}
    memoria = [{"agente": "Gap", "chiave": quasi.chiave, "esito": "scartata", "qualita": 0.01}]
    idee = idee_della_settimana(["Gap"], provate, np.random.default_rng(0), memoria)
    assert len(idee) == 2 and idee[0] in vicine
    # Un'idea che peggiorava non si affina.
    from nvm.prova.allenamento import quasi_riuscite
    memoria[0]["qualita"] = -0.01
    assert quasi_riuscite(memoria, "Gap") == []
