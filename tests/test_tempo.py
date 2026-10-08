"""I confini delle candele: aprono come quelle di MT5, alle 17:00 di New York (le 23 italiane); le crypto sul
calendario UTC."""

import numpy as np

from nvm.tempo import TF, fine_candela, inizio_candela, ny, sopra_a, utc


def _inizio(t, tf, weekend=False):
    return int(inizio_candela(np.array([t]), tf, weekend)[0])


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


def test_quattro_ore_aprono_a_17_21_1_5_9_13_di_new_york():
    # Come su MT5: le 23, 3, 7, 11, 15, 19 italiane (il proprietario, 08/10/2026, il CRT a 4 ore di SPX500).
    for ora_ny, attesa in [(1, 1), (4, 1), (5, 5), (8, 5), (9, 9), (12, 9), (13, 13), (16, 13), (17, 17), (20, 17),
                           (21, 21), (23, 21)]:
        assert _inizio(ny(2026, 9, 10, ora_ny, 30), TF.H4) == ny(2026, 9, 10, attesa), ora_ny
    # Le 00:30 di New York stanno nella candela aperta alle 21 del giorno prima.
    assert _inizio(ny(2026, 9, 10, 0, 30), TF.H4) == ny(2026, 9, 9, 21)


def test_quattro_ore_anche_in_inverno():
    assert _inizio(ny(2026, 1, 14, 6, 0), TF.H4) == ny(2026, 1, 14, 5)
    assert fine_candela(ny(2026, 1, 14, 5), TF.H4) == ny(2026, 1, 14, 9)


def test_sei_e_dodici_ore():
    # 6 ore alle 17, 23, 5, 11 di New York; 12 ore alle 17 e alle 5.
    assert _inizio(ny(2026, 9, 10, 4, 30), TF.H6) == ny(2026, 9, 9, 23)
    assert _inizio(ny(2026, 9, 10, 10, 30), TF.H6) == ny(2026, 9, 10, 5)
    assert fine_candela(ny(2026, 9, 10, 5), TF.H6) == ny(2026, 9, 10, 11)
    assert _inizio(ny(2026, 9, 10, 4, 30), TF.H12) == ny(2026, 9, 9, 17)
    assert _inizio(ny(2026, 9, 10, 16, 30), TF.H12) == ny(2026, 9, 10, 5)
    assert fine_candela(ny(2026, 9, 10, 5), TF.H12) == ny(2026, 9, 10, 17)


def test_settimana_da_domenica_17_a_venerdi_17():
    # Mercoledi' 9 settembre 2026.
    inizio = _inizio(ny(2026, 9, 9, 10), TF.W1)
    assert inizio == ny(2026, 9, 6, 17)  # domenica
    assert fine_candela(inizio, TF.W1) == ny(2026, 9, 11, 17)  # venerdi'
    # La domenica sera dopo le 17 e' gia' la settimana nuova.
    assert _inizio(ny(2026, 9, 13, 18), TF.W1) == ny(2026, 9, 13, 17)


def test_la_domenica_prima_delle_17_va_nella_prima_candela():
    # Il fine settimana di sessione va al lunedi': niente candele di un'ora sola la domenica.
    for tf in (TF.H4, TF.H6, TF.D1, TF.W1):
        assert _inizio(ny(2026, 9, 13, 16, 30), tf) == ny(2026, 9, 13, 17), tf
    # Le crypto tengono il loro fine settimana (e i loro orari, sotto): la domenica e' un giorno come gli altri.
    assert _inizio(ny(2026, 9, 13, 17, 30), TF.D1, weekend=True) == utc(2026, 9, 13)


def test_mese_di_trading():
    # Il 31 agosto dopo le 17 di New York e' gia' settembre.
    assert _inizio(ny(2026, 8, 31, 18), TF.MN) == ny(2026, 8, 31, 17)
    assert _inizio(ny(2026, 9, 15, 10), TF.MN) == ny(2026, 8, 31, 17)
    assert fine_candela(ny(2026, 8, 31, 17), TF.MN) == ny(2026, 9, 30, 17)


def test_tre_sei_e_dodici_mesi():
    # Il trimestre di luglio-settembre 2026, il semestre luglio-dicembre, l'anno 2026.
    assert _inizio(ny(2026, 8, 20, 10), TF.Q3) == ny(2026, 6, 30, 17)
    assert fine_candela(ny(2026, 6, 30, 17), TF.Q3) == ny(2026, 9, 30, 17)
    assert _inizio(ny(2026, 8, 20, 10), TF.S6) == ny(2026, 6, 30, 17)
    assert _inizio(ny(2026, 8, 20, 10), TF.Y1) == ny(2025, 12, 31, 17)
    assert fine_candela(ny(2025, 12, 31, 17), TF.Y1) == ny(2026, 12, 31, 17)
    assert sopra_a(TF.MN) == (TF.Q3, TF.S6, TF.Y1)


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


def test_le_crypto_hanno_gli_orari_crypto():
    # Il proprietario, 08/10/2026: la giornata crypto apre alle 2 italiane (mezzanotte UTC), le 4 ore alle 2, 6, 10,
    # 14, le 6 ore alle 2, 8, 14, 20, le 12 ore alle 2 e alle 14. Il resto alle 17 di New York, come MT5.
    t = utc(2026, 10, 8, 5, 30)          # giovedi', le 7:30 italiane
    assert _inizio(t, TF.D1, weekend=True) == utc(2026, 10, 8)
    assert fine_candela(utc(2026, 10, 8), TF.D1, weekend=True) == utc(2026, 10, 9)
    assert _inizio(t, TF.H4, weekend=True) == utc(2026, 10, 8, 4)
    assert fine_candela(utc(2026, 10, 8, 4), TF.H4, weekend=True) == utc(2026, 10, 8, 8)
    assert _inizio(t, TF.H6, weekend=True) == utc(2026, 10, 8, 0)
    assert _inizio(utc(2026, 10, 8, 7), TF.H6, weekend=True) == utc(2026, 10, 8, 6)
    assert fine_candela(utc(2026, 10, 8, 0), TF.H6, weekend=True) == utc(2026, 10, 8, 6)
    assert _inizio(utc(2026, 10, 8, 13), TF.H12, weekend=True) == utc(2026, 10, 8, 12)
    assert fine_candela(utc(2026, 10, 8, 12), TF.H12, weekend=True) == utc(2026, 10, 9)
    # La settimana da lunedi' a mezzanotte UTC, sette giorni: la domenica sera e' ancora la stessa settimana.
    assert _inizio(t, TF.W1, weekend=True) == utc(2026, 10, 5)
    assert _inizio(utc(2026, 10, 11, 23), TF.W1, weekend=True) == utc(2026, 10, 5)
    assert fine_candela(utc(2026, 10, 5), TF.W1, weekend=True) == utc(2026, 10, 12)
    # Mese, 3, 6 e 12 mesi dal giorno 1 a mezzanotte UTC.
    assert _inizio(t, TF.MN, weekend=True) == utc(2026, 10, 1)
    assert fine_candela(utc(2026, 10, 1), TF.MN, weekend=True) == utc(2026, 11, 1)
    assert _inizio(utc(2026, 8, 20), TF.Q3, weekend=True) == utc(2026, 7, 1)
    assert fine_candela(utc(2026, 7, 1), TF.Q3, weekend=True) == utc(2026, 10, 1)
    assert _inizio(utc(2026, 8, 20), TF.S6, weekend=True) == utc(2026, 7, 1)
    assert _inizio(utc(2026, 8, 20), TF.Y1, weekend=True) == utc(2026, 1, 1)
    assert fine_candela(utc(2026, 1, 1), TF.Y1, weekend=True) == utc(2027, 1, 1)
    # L'ora solare non le sposta: restano a mezzanotte UTC (l'1 italiana d'inverno).
    assert _inizio(utc(2026, 11, 2, 12), TF.D1, weekend=True) == utc(2026, 11, 2)
    # Il resto no: 6 ore alle 17, 23, 5, 11 di New York (l'1:30 di New York sta in quella delle 23).
    assert _inizio(t, TF.H6) == ny(2026, 10, 7, 23)
