"""Le entrate di Romeo: l'ora del suo server, la lettura dei prezzi, l'esito e il confronto col bot."""

from pathlib import Path

from nvm.agenti.cacciatore import Verso
from nvm.prova.base import Risultato
from nvm.prova.campo import Uscita
from nvm.prova.romeo import Entrata, al_prezzo, confronta, esito, leggi, server_a_utc
from nvm.tempo import TF, utc
from tests.aiuti import candele

RADICE = Path(__file__).resolve().parent.parent


def entrata(verso=Verso.LONG, dal="2023-12-12 16:00", al="2023-12-12 17:00", ingresso=1.0771, stop=1.0769, target=1.0790):
    return Entrata("R000", "studio", "EURUSD", verso, "esecuzione", server_a_utc(dal), server_a_utc(al) + 60,
                   ingresso, stop, target, "M5", "", "", "", "")


def test_il_server_di_romeo_e_new_york_piu_sette():
    # Il CPI del 12/12/2023 (08:30 NY) sul suo grafico cade alle 15:30.
    assert server_a_utc("2023-12-12 15:30") == utc(2023, 12, 12, 13, 30)
    # D'estate New York e' UTC-4, quindi il server e' UTC+3.
    assert server_a_utc("2024-03-29 16:30") == utc(2024, 3, 29, 13, 30)


def test_il_catalogo_si_legge_tutto():
    tutte = leggi(RADICE / "casi" / "entrate-romeo.csv")
    assert len(tutte) >= 100
    assert {e.periodo for e in tutte} == {"studio", "sigillato"}
    assert all(e.dal < e.al for e in tutte)
    # Il periodo di studio finisce col 2023.
    assert all((e.dal < utc(2024, 1, 1, 12)) == (e.periodo == "studio") for e in tutte)


ORE = candele("EURUSD", TF.H1, [
    (utc(2023, 12, 12, 13), 1.0798, 1.0828, 1.0773, 1.0776),
    (utc(2023, 12, 12, 14), 1.0776, 1.0780, 1.0767, 1.0774),   # l'ingresso, ma anche lo stop
    (utc(2023, 12, 12, 15), 1.0774, 1.0789, 1.0770, 1.0784),
    (utc(2023, 12, 12, 16), 1.0784, 1.0795, 1.0781, 1.0792),   # il target
])


def test_la_lettura_regge_se_il_prezzo_e_passato_dall_ingresso():
    assert al_prezzo(entrata(), ORE) == utc(2023, 12, 12, 14)
    assert al_prezzo(entrata(ingresso=1.0850), ORE) is None


def test_se_nella_candela_dell_ingresso_c_e_anche_lo_stop_l_esito_e_incerto():
    assert esito(entrata(), ORE, utc(2023, 12, 12, 14)) == "incerto"
    # Entrati un'ora dopo, lo stop non si tocca piu' e il target arriva nella candela dopo.
    assert esito(entrata(), ORE, utc(2023, 12, 12, 15)) == "target"
    # Un target gia' toccato nella candela dell'ingresso non si sa se e' venuto prima.
    assert esito(entrata(target=1.0788), ORE, utc(2023, 12, 12, 15)) == "incerto"
    assert esito(entrata(stop=None), ORE, utc(2023, 12, 12, 14)) == "senza prezzi"


def _op(verso, quando, ingresso):
    return Risultato("EURUSD", TF.D1, TF.H1, verso, quando, 0.0, Uscita.STOP, False, 0.0, 1.0, ingresso=ingresso)


def test_il_bot_la_ritrova_solo_nello_stesso_verso_nella_finestra_e_vicino_al_prezzo():
    e = entrata()  # rischio 2 pip: meta' rischio e' 1 pip
    vicina = _op(Verso.LONG, utc(2023, 12, 12, 15), 1.07715)
    lontana = _op(Verso.LONG, utc(2023, 12, 12, 15), 1.0776)
    opposta = _op(Verso.SHORT, utc(2023, 12, 12, 15), 1.0771)
    fuori = _op(Verso.LONG, utc(2023, 12, 13, 15), 1.0771)
    c = confronta(e, [lontana, opposta, fuori, vicina])
    assert [x.operazione for x in c] == [vicina, lontana]
    assert c[0].ritrovata and not c[1].ritrovata


# --- Le risposte alla Romeo e il Capo che lo imita ---

import numpy as np

from nvm.agenti.cacciatore import Stato, caccia
from nvm.agenti.capo import COLONNE, Capo
from nvm.agenti.conferme import GRANDEZZA, LONDRA, NEW_YORK, Grandi, alla_romeo
from nvm.dati.candele import costruisci
from nvm.dati.minuti import CHIUSURA, MASSIMO, MINIMO
from nvm.prova.base import opera
from nvm.tempo import NEW_YORK as FUSO, ny
from tests.aiuti import passeggiata


def test_le_risposte_alla_romeo_sono_quelle_che_si_contano_a_mano():
    from datetime import datetime
    m = passeggiata("EURUSD", ny(2026, 1, 4, 17), ny(2026, 4, 26, 17), seme=5)
    tutti = []
    for alto, basso in ((TF.W1, TF.H4), (TF.D1, TF.H1)):
        tutti += caccia(costruisci(m, alto), costruisci(m, basso))
    grandi = Grandi.da(tutti)
    settimane = costruisci(m, TF.W1)
    alte, basse = costruisci(m, TF.H4), costruisci(m, TF.M15)
    operazioni = opera(alte, basse, ny(2026, 2, 1, 17), ny(2026, 4, 26, 17))
    assert len(operazioni) > 20
    for r in operazioni:
        s = r.scatto
        a = alla_romeo(s, basse, settimane, grandi)
        ora = datetime.fromtimestamp(int(basse.inizio[s.indice]), tz=FUSO).hour
        assert a.londra == (LONDRA[0] <= ora < LONDRA[1])
        assert a.new_york == (NEW_YORK[0] <= ora < NEW_YORK[1])
        armato = [c for c in tutti if c.verso is r.verso and GRANDEZZA[c.alto_tf] > GRANDEZZA[TF.H4]
                  and c.stato_a(s.quando) is Stato.ARMATO]
        assert a.annidato == bool(armato)
        k = int(np.searchsorted(settimane.fine, s.quando, side="right")) - 1
        dove = (basse.bid[s.indice, CHIUSURA] - settimane.bid[k, MINIMO]) / (settimane.bid[k, MASSIMO] - settimane.bid[k, MINIMO])
        assert a.sconto == (dove < 0.5 if r.verso is Verso.LONG else dove > 0.5)


def _capo_con_romeo(seme=0, n=3000):
    rng = np.random.default_rng(seme)
    x = rng.integers(0, 2, size=(n, len(COLONNE))).astype(float)
    x[:, COLONNE.index("RR1")] = rng.uniform(0.5, 4, n)
    x[:, COLONNE.index("RR2")] = rng.uniform(1, 8, n)
    tp1 = rng.random(n) < 0.4
    tp2 = tp1 & (rng.random(n) < 0.4)
    capo = Capo.allena(x, tp1, tp2)
    # Romeo sceglie quasi solo le operazioni nell'ora di New York.
    y = (x[:, COLONNE.index("ora di Romeo: New York")] == 1) & (rng.random(n) < 0.05)
    rr1, rr2, costi = x[:, COLONNE.index("RR1")], x[:, COLONNE.index("RR2")], np.full(n, 0.05)
    return capo.impara_romeo(x, y), x, rr1, rr2, costi


def test_il_capo_impara_cosa_sceglie_romeo():
    capo, x, rr1, rr2, costi = _capo_con_romeo()
    pesi = dict(capo.fiducia_romeo())
    assert max(pesi, key=pesi.get) == "ora di Romeo: New York"
    simili = capo.somiglianza(x)
    ny_ = x[:, COLONNE.index("ora di Romeo: New York")] == 1
    assert simili[ny_].mean() > 2 * simili[~ny_].mean()


def test_la_somiglianza_e_un_parere_non_un_obbligo():
    """Addestrare non vuol dire imporre (decisione dell'utente, 24/09/2026):
    il Capo decide col guadagno atteso, la somiglianza a Romeo non lo blocca."""
    capo, x, rr1, rr2, costi = _capo_con_romeo(seme=3)
    assert (capo.entra(x, rr1, rr2, costi) == (capo.valore_atteso(x, rr1, rr2, costi) > 0)).all()


def test_il_capo_salvato_ricorda_romeo():
    capo, x, rr1, rr2, costi = _capo_con_romeo(seme=1)
    di_nuovo = Capo.da_dati(capo.come_dati())
    assert np.allclose(di_nuovo.somiglianza(x), capo.somiglianza(x))
    assert (di_nuovo.entra(x, rr1, rr2, costi) == capo.entra(x, rr1, rr2, costi)).all()


def test_senza_romeo_la_somiglianza_non_si_sa():
    capo, x, rr1, rr2, costi = _capo_con_romeo(seme=2)
    senza = Capo(capo.media, capo.scala, capo.primo, capo.secondo)
    assert (senza.somiglianza(x) == 1).all()
    assert (senza.entra(x, rr1, rr2, costi) == capo.entra(x, rr1, rr2, costi)).all()


def test_la_fiducia_in_romeo_si_impara_dai_risultati():
    rng = np.random.default_rng(7)
    n = 4000
    x = rng.integers(0, 2, size=(n, len(COLONNE))).astype(float)
    y_romeo = (x[:, COLONNE.index("ora di Romeo: Londra")] == 1) & (rng.random(n) < 0.05)
    capo = Capo.allena(x, rng.random(n) < 0.35, rng.random(n) < 0.1).impara_romeo(x, y_romeo)
    londra = x[:, COLONNE.index("ora di Romeo: Londra")] == 1
    vincono = rng.random(n) < np.where(londra, 0.55, 0.30)     # le operazioni alla Romeo vincono di piu'
    perdono = rng.random(n) < np.where(londra, 0.20, 0.40)     # ...oppure di meno
    a_caso = rng.random(n) < 0.35
    assert capo.impara_fiducia(x, vincono).fiducia_in_romeo > 0.2
    assert capo.impara_fiducia(x, perdono).fiducia_in_romeo < -0.1
    assert abs(capo.impara_fiducia(x, a_caso).fiducia_in_romeo) < 0.1
    fidato = capo.impara_fiducia(x, vincono)
    p_con, _ = fidato.probabilita(x)
    p_senza, _ = capo.probabilita(x)
    assert p_con[londra].mean() > p_senza[londra].mean()
    di_nuovo = Capo.da_dati(fidato.come_dati())
    assert np.allclose(di_nuovo.probabilita(x)[0], p_con)


def test_l_auc_del_banco_di_prova_conta_i_pari_merito_a_meta():
    from banco import auc
    y = np.array([True, False, True, False])
    assert auc(np.array([0.9, 0.1, 0.8, 0.2]), y) == 1.0
    assert auc(np.array([0.1, 0.9, 0.2, 0.8]), y) == 0.0
    assert auc(np.array([0.5, 0.5, 0.5, 0.5]), y) == 0.5
