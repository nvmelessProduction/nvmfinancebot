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
