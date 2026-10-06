"""I confini delle candele: aprono come quelle dei future, alle 18:00 di New York (mezzanotte italiana)."""

import numpy as np

from nvm.tempo import TF, fine_candela, inizio_candela, ny, sopra_a, utc


def _inizio(t, tf, weekend=False):
    return int(inizio_candela(np.array([t]), tf, weekend)[0])


def test_giornaliera_estate_apre_alle_22_utc():
    # 10 settembre 2026, ora legale: 18:00 NY = 22:00 UTC = mezzanotte italiana.
    t = utc(2026, 9, 10, 12, 30)
    assert _inizio(t, TF.D1) == utc(2026, 9, 9, 22)
    assert fine_candela(utc(2026, 9, 9, 22), TF.D1) == utc(2026, 9, 10, 22)


def test_giornaliera_inverno_apre_alle_23_utc():
    t = utc(2026, 1, 14, 12, 30)
    assert _inizio(t, TF.D1) == utc(2026, 1, 13, 23)


def test_dopo_le_18_di_new_york_e_gia_il_giorno_dopo():
    assert _inizio(ny(2026, 9, 10, 18, 1), TF.D1) == ny(2026, 9, 10, 18)
    # Le 17:30 sono ancora il giorno prima (sui future e' la pausa).
    assert _inizio(ny(2026, 9, 10, 17, 30), TF.D1) == ny(2026, 9, 9, 18)


def test_quattro_ore_aprono_a_18_22_2_6_10_14_di_new_york():
    for ora_ny, attesa in [(2, 2), (5, 2), (6, 6), (9, 6), (10, 10), (13, 10), (14, 14), (17, 14), (18, 18), (21, 18),
                           (22, 22), (23, 22)]:
        assert _inizio(ny(2026, 9, 10, ora_ny, 30), TF.H4) == ny(2026, 9, 10, attesa), ora_ny
    # Le 00:30 di New York stanno nella candela aperta alle 22 del giorno prima.
    assert _inizio(ny(2026, 9, 10, 0, 30), TF.H4) == ny(2026, 9, 9, 22)


def test_quattro_ore_anche_in_inverno():
    assert _inizio(ny(2026, 1, 14, 7, 0), TF.H4) == ny(2026, 1, 14, 6)
    assert fine_candela(ny(2026, 1, 14, 6), TF.H4) == ny(2026, 1, 14, 10)


def test_sei_e_dodici_ore():
    # 6 ore: 18, 0, 6, 12 di New York (mezzanotte, 6, 12, 18 italiane).
    assert _inizio(ny(2026, 5, 12, 1), TF.H6) == ny(2026, 5, 12, 0)
    assert _inizio(ny(2026, 5, 12, 13), TF.H6) == ny(2026, 5, 12, 12)
    assert fine_candela(ny(2026, 5, 12, 12), TF.H6) == ny(2026, 5, 12, 18)
    # 12 ore: 18 e 6.
    assert _inizio(ny(2026, 5, 12, 5), TF.H12) == ny(2026, 5, 11, 18)
    assert _inizio(ny(2026, 5, 12, 7), TF.H12) == ny(2026, 5, 12, 6)


def test_settimana_da_domenica_18_a_venerdi():
    # Mercoledi' 9 settembre 2026.
    inizio = _inizio(ny(2026, 9, 9, 10), TF.W1)
    assert inizio == ny(2026, 9, 6, 18)  # domenica
    assert fine_candela(inizio, TF.W1) == ny(2026, 9, 11, 18)  # venerdi'
    # La domenica sera dopo le 18 e' gia' la settimana nuova.
    assert _inizio(ny(2026, 9, 13, 18, 30), TF.W1) == ny(2026, 9, 13, 18)


def test_l_ora_della_domenica_prima_delle_18_va_nella_prima_candela():
    # Il forex riapre la domenica alle 17 di New York, un'ora prima dei future: quell'ora non fa una candela da sola.
    for tf in (TF.H4, TF.H6, TF.D1, TF.W1):
        assert _inizio(ny(2026, 9, 13, 17, 30), tf) == ny(2026, 9, 13, 18), tf
    # Le crypto tengono il loro fine settimana.
    assert _inizio(ny(2026, 9, 13, 17, 30), TF.D1, weekend=True) == ny(2026, 9, 12, 18)


def test_mese_di_trading():
    # Il 31 agosto dopo le 18 di New York e' gia' settembre.
    assert _inizio(ny(2026, 8, 31, 18, 30), TF.MN) == ny(2026, 8, 31, 18)
    assert _inizio(ny(2026, 9, 15, 10), TF.MN) == ny(2026, 8, 31, 18)
    assert fine_candela(ny(2026, 8, 31, 18), TF.MN) == ny(2026, 9, 30, 18)


def test_tre_sei_e_dodici_mesi():
    # Il trimestre di luglio-settembre 2026, il semestre luglio-dicembre, l'anno 2026.
    assert _inizio(ny(2026, 8, 20, 10), TF.Q3) == ny(2026, 6, 30, 18)
    assert fine_candela(ny(2026, 6, 30, 18), TF.Q3) == ny(2026, 9, 30, 18)
    assert _inizio(ny(2026, 8, 20, 10), TF.S6) == ny(2026, 6, 30, 18)
    assert _inizio(ny(2026, 8, 20, 10), TF.Y1) == ny(2025, 12, 31, 18)
    assert fine_candela(ny(2025, 12, 31, 18), TF.Y1) == ny(2026, 12, 31, 18)
    assert sopra_a(TF.MN) == (TF.Q3, TF.S6, TF.Y1)


def test_cambio_d_ora_non_sposta_le_18():
    # Domenica 1 novembre 2026 finisce l'ora legale: la settimana apre alle
    # 18:00 di New York, che ora sono le 23:00 UTC.
    assert _inizio(utc(2026, 11, 2, 12), TF.W1) == utc(2026, 11, 1, 23)
    assert _inizio(utc(2026, 11, 2, 12), TF.D1) == utc(2026, 11, 1, 23)


def test_minuti_e_ore_restano_allineati_all_utc():
    t = utc(2026, 9, 10, 13, 47)
    assert _inizio(t, TF.M1) == utc(2026, 9, 10, 13, 47)
    assert _inizio(t, TF.M5) == utc(2026, 9, 10, 13, 45)
    assert _inizio(t, TF.M15) == utc(2026, 9, 10, 13, 45)
    assert _inizio(t, TF.H1) == utc(2026, 9, 10, 13)
