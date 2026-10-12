"""La strategia del libro del socio (`documenti/spec/metodo_libro.md`): struttura, inducement, EPA, MSU."""

import numpy as np

from nvm.agenti import struttura as S
from nvm.dati.candele import Candele
from nvm.tempo import TF
from tests.aiuti import candele

ORA = 3600
INIZIO = 1_700_000_000 - 1_700_000_000 % ORA

# Una gamba rialzista scritta a mano (apertura, massimo, minimo, chiusura), con massimi e minimi di 1 candela per
# parte: nasce la struttura (4), B sale col prezzo, l'inducement (il minimo 6) viene preso (10), la chiusura oltre
# B rompe (13) e il minimo del ritracciamento diventa il nuovo A, la chiusura sotto A cambia la struttura (14).
GAMBA = [
    (10.0, 10.5, 9.5, 10.2),
    (10.2, 11.0, 10.0, 10.8),   # 1: massimo piccolo
    (10.8, 10.9, 9.0, 9.2),     # 2: minimo piccolo, candela ribassista (la EPA)
    (9.2, 10.6, 9.1, 10.5),
    (10.5, 11.2, 10.4, 11.1),   # 4: chiude sopra il massimo 1: struttura rialzista, A = 9,0
    (11.1, 11.3, 10.7, 10.8),
    (10.8, 10.9, 10.5, 10.85),  # 6: minimo piccolo: l'inducement
    (10.85, 11.8, 10.8, 11.7),
    (11.7, 12.0, 11.6, 11.9),   # 8: B = 12,0
    (11.9, 11.95, 11.0, 11.1),
    (11.1, 11.2, 10.4, 10.6),   # 10: sotto 10,5: inducement preso, B resta fermo
    (10.6, 10.7, 10.1, 10.3),   # 11: il fondo del ritracciamento
    (10.3, 11.5, 10.2, 11.4),
    (11.4, 12.3, 11.3, 12.2),   # 13: chiude sopra B: rottura, A = 10,1
    (12.2, 12.25, 9.9, 10.0),   # 14: chiude sotto A: struttura ribassista, A = 12,3
]


def _gamba() -> Candele:
    return candele("EURUSD", TF.H1, [(INIZIO + i * ORA, *r) for i, r in enumerate(GAMBA)])


def test_i_massimi_e_minimi_battono_le_candele_vicine():
    alti = np.array([1, 3, 2, 2, 5, 4], float)
    bassi = np.array([0, 2, 1, 1.5, 3, 3], float)
    mx, mn = S.punti(alti, bassi, lato=1)
    assert list(np.where(mx)[0]) == [1, 4]
    assert list(np.where(mn)[0]) == [2]


def test_la_struttura_segue_inducement_rottura_e_cambio():
    s = S.struttura(_gamba(), lato=1)
    assert s.verso[3] == 0
    assert s.cambio[4] == S.CAMBIO_SU and s.verso[4] == 1
    assert s.a[4] == 9.0 and s.a_i[4] == 2
    assert s.epa_alto[4] == 10.9  # l'ultimo sell prima del buy: la candela 2
    # Prima dell'inducement B segue il prezzo; l'inducement e' l'ultimo minimo piccolo fra A e B.
    assert s.b[7] == 11.8 and s.b[8] == 12.0
    assert s.idm[8] == 10.5
    assert not s.idm_preso[9] and s.idm_preso[10]
    # Preso l'inducement B resta fermo anche se il prezzo scende.
    assert s.b[12] == 12.0
    # La chiusura oltre B rompe: il nuovo A e' il fondo del ritracciamento.
    assert s.cambio[13] == S.ROTTURA_SU and s.rotture[13] == 2
    assert s.a[13] == 10.1 and s.a_i[13] == 11
    # La chiusura sotto A cambia la struttura; il nuovo A e' l'estremo da cui si e' girati.
    assert s.cambio[14] == S.CAMBIO_GIU and s.verso[14] == -1
    assert s.a[14] == 12.3


def _passeggiata(n: int, seme: int) -> Candele:
    rng = np.random.default_rng(seme)
    chiusure = 1.1 + np.cumsum(rng.normal(0, 0.001, n))
    aperture = np.r_[1.1, chiusure[:-1]]
    alti = np.maximum(aperture, chiusure) + rng.uniform(0, 0.0008, n)
    bassi = np.minimum(aperture, chiusure) - rng.uniform(0, 0.0008, n)
    return candele("EURUSD", TF.H1, [(INIZIO + i * ORA, aperture[i], alti[i], bassi[i], chiusure[i])
                                      for i in range(n)])


def _quattro_ore(ore: Candele) -> Candele:
    n = len(ore) // 4
    p = ore.bid[:n * 4].reshape(n, 4, 4)
    righe = np.c_[p[:, 0, 0], p[:, :, 1].max(1), p[:, :, 2].min(1), p[:, -1, 3]]
    return candele("EURUSD", TF.H4, [(int(ore.inizio[i * 4]), *righe[i]) for i in range(n)])


def test_le_occasioni_rispettano_le_tre_regole_e_non_guardano_il_futuro():
    ore = _passeggiata(4000, seme=5)
    alte = _quattro_ore(ore)
    tutte = S.occasioni(alte, ore)
    assert tutte, "su 4000 ore qualche occasione deve esserci"
    for o in tutte:
        assert (o.ingresso - o.stop) * o.verso > 0
        assert (o.obiettivo - o.ingresso) * o.verso > 0
        assert 0 < o.sconto < 1
    # Tagliate le candele a meta', le occasioni prima del taglio sono le stesse: niente futuro.
    taglio = int(ore.inizio[2000])
    prima = S.occasioni(alte.chiuse_entro(taglio), ore.chiuse_entro(taglio))
    assert prima == [o for o in tutte if o.quando < taglio]
