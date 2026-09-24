"""I confini delle candele: la giornata chiude alle 17:00 di New York."""

import numpy as np

from nvm.tempo import TF, fine_candela, inizio_candela, ny, utc


def _inizio(t, tf):
    return int(inizio_candela(np.array([t]), tf)[0])


def test_giornaliera_estate_apre_alle_21_utc():
    # 10 settembre 2026, ora legale: 17:00 NY = 21:00 UTC.
    t = utc(2026, 9, 10, 12, 30)
    assert _inizio(t, TF.D1) == utc(2026, 9, 9, 21)
    assert fine_candela(utc(2026, 9, 9, 21), TF.D1) == utc(2026, 9, 10, 21)


def test_giornaliera_inverno_apre_alle_22_utc():
    t = utc(2026, 1, 14, 12, 30)
    assert _inizio(t, TF.D1) == utc(2026, 1, 13, 22)


def test_dopo_le_17_di_new_york_e_gia_il_giorno_dopo():
    t = ny(2026, 9, 10, 17, 1)
    assert _inizio(t, TF.D1) == ny(2026, 9, 10, 17)


def test_quattro_ore_aprono_a_1_5_9_13_17_21_di_new_york():
    for ora_ny, attesa in [(1, 1), (4, 1), (5, 5), (8, 5), (9, 9), (12, 9), (13, 13), (17, 17), (20, 17), (21, 21), (23, 21)]:
        t = ny(2026, 9, 10, ora_ny, 30)
        giorno = 10
        assert _inizio(t, TF.H4) == ny(2026, 9, giorno, attesa), ora_ny
    # Le 00:30 di New York stanno nella candela aperta alle 21 del giorno prima.
    assert _inizio(ny(2026, 9, 10, 0, 30), TF.H4) == ny(2026, 9, 9, 21)


def test_quattro_ore_anche_in_inverno():
    assert _inizio(ny(2026, 1, 14, 6, 0), TF.H4) == ny(2026, 1, 14, 5)
    assert fine_candela(ny(2026, 1, 14, 5), TF.H4) == ny(2026, 1, 14, 9)


def test_settimana_da_domenica_17_a_venerdi_17():
    # Mercoledi' 9 settembre 2026.
    inizio = _inizio(ny(2026, 9, 9, 10), TF.W1)
    assert inizio == ny(2026, 9, 6, 17)  # domenica
    assert fine_candela(inizio, TF.W1) == ny(2026, 9, 11, 17)  # venerdi'
    # La domenica sera dopo le 17 e' gia' la settimana nuova.
    assert _inizio(ny(2026, 9, 13, 18), TF.W1) == ny(2026, 9, 13, 17)


def test_mese_di_trading():
    # Il 31 agosto dopo le 17 di New York e' gia' settembre.
    assert _inizio(ny(2026, 8, 31, 18), TF.MN) == ny(2026, 8, 31, 17)
    assert _inizio(ny(2026, 9, 15, 10), TF.MN) == ny(2026, 8, 31, 17)
    assert fine_candela(ny(2026, 8, 31, 17), TF.MN) == ny(2026, 9, 30, 17)


def test_cambio_d_ora_non_sposta_le_17():
    # Domenica 1 novembre 2026 finisce l'ora legale: la settimana apre alle
    # 17:00 di New York, che ora sono le 22:00 UTC.
    assert _inizio(utc(2026, 11, 2, 12), TF.W1) == utc(2026, 11, 1, 22)
    assert _inizio(utc(2026, 11, 2, 12), TF.D1) == utc(2026, 11, 1, 22)


def test_minuti_e_ore_restano_allineati_all_utc():
    t = utc(2026, 9, 10, 13, 47)
    assert _inizio(t, TF.M1) == utc(2026, 9, 10, 13, 47)
    assert _inizio(t, TF.M5) == utc(2026, 9, 10, 13, 45)
    assert _inizio(t, TF.M15) == utc(2026, 9, 10, 13, 45)
    assert _inizio(t, TF.H1) == utc(2026, 9, 10, 13)
