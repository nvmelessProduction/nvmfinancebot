"""Il Grilletto e Livelli, sullo schema del Model#1 di Romeo (msg 4836).

Short: una candela rialzista spessa spazza il CRT high (turtle soup), la sua
apertura e' il livello "-Ob", la prima chiusura sotto il livello e'
l'ingresso.
"""

import pytest

from nvm.agenti.cacciatore import Motivo, Verso, caccia
from nvm.agenti.grilletto import scatti, scatto
from nvm.agenti.livelli import piano, scadenza
from nvm.dati.candele import costruisci
from nvm.tempo import TF, ny
from tests.aiuti import candele, passeggiata

Q = 15 * 60
C1, C2, C3 = ny(2026, 9, 10, 1), ny(2026, 9, 10, 5), ny(2026, 9, 10, 9)
ALTE = [
    (C1, 1.1000, 1.1100, 1.1000, 1.1090),
    (C2, 1.1090, 1.1140, 1.1040, 1.1060),
    (C3, 1.1060, 1.1070, 1.1030, 1.1040),
]


def _crt(quarti, alte=ALTE):
    """Il CRT short del range C1, con le candele basse della candela 2 e 3."""
    a = candele("EURUSD", TF.H4, alte)
    b = candele("EURUSD", TF.M15, [(C2 + n * Q, *r) for n, r in enumerate(quarti)])
    crt = [c for c in caccia(a, b) if c.verso is Verso.SHORT and c.range_inizio == C1]
    return (crt[0] if crt else None), b


# (apertura, massimo, minimo, chiusura) dei quarti d'ora dentro la candela 2.
SALITA = [(1.1080, 1.1092, 1.1078, 1.1090)]
TURTLE_SOUP = (1.1090, 1.1130, 1.1088, 1.1120)  # rialzista, sopra 1.1100


def test_lo_schema_di_romeo():
    crt, b = _crt(SALITA + [TURTLE_SOUP, (1.1120, 1.1125, 1.1095, 1.1100), (1.1100, 1.1102, 1.1080, 1.1085)])
    s = scatto(crt, b)
    assert s.livello == pytest.approx(1.1090)  # l'apertura della candela del turtle soup
    assert s.turtle_soup_inizio == C2 + Q
    # La terza candela chiude a 1.1100, sopra il livello: non basta toccarlo.
    # Scatta la quarta, che chiude a 1.1085.
    assert s.quando == C2 + 4 * Q


def test_un_turtle_soup_piu_recente_sposta_il_livello():
    secondo = (1.1105, 1.1140, 1.1100, 1.1135)
    crt, b = _crt(SALITA + [TURTLE_SOUP, secondo, (1.1135, 1.1136, 1.1098, 1.1101)])
    s = scatto(crt, b)
    assert s.livello == pytest.approx(1.1105)
    assert s.quando == C2 + 4 * Q  # 1.1101 e' sotto 1.1105, anche se sopra 1.1090


def test_niente_scatto_se_il_prezzo_resta_sopra():
    crt, b = _crt(SALITA + [TURTLE_SOUP] + [(1.1120, 1.1125, 1.1095, 1.1110)] * 5)
    assert scatto(crt, b) is None


def test_una_candela_ribassista_oltre_il_range_non_e_un_turtle_soup():
    ribassista = (1.1120, 1.1130, 1.1085, 1.1095)
    crt, b = _crt(SALITA + [ribassista, (1.1095, 1.1096, 1.1080, 1.1082)])
    assert scatto(crt, b) is None


def test_troppo_tardi_se_la_candela_che_rompe_tocca_gia_il_lato_opposto():
    crollo = (1.1120, 1.1121, 1.0990, 1.1000)
    crt, b = _crt(SALITA + [TURTLE_SOUP, crollo])
    assert crt.motivo is Motivo.LATO_OPPOSTO
    assert scatto(crt, b) is None


def test_livelli_del_manuale():
    crt, b = _crt(SALITA + [TURTLE_SOUP, (1.1120, 1.1125, 1.1095, 1.1100), (1.1100, 1.1102, 1.1080, 1.1085)])
    op = piano(scatto(crt, b), b)
    assert op.ingresso == pytest.approx(1.1085)
    assert op.stop == pytest.approx(1.1130)  # il tetto del turtle soup
    assert (op.tp1, op.tp2) == (pytest.approx(1.1050), pytest.approx(1.1000))
    s = scatto(crt, b)
    assert scadenza(s) == s.quando + 3 * 86400  # solo un tetto di sicurezza


def test_niente_operazione_se_il_primo_target_e_alle_spalle():
    sotto_meta = (1.1100, 1.1102, 1.1045, 1.1048)
    crt, b = _crt(SALITA + [TURTLE_SOUP, sotto_meta])
    s = scatto(crt, b)
    assert s is not None and piano(s, b) is None


def test_il_long_e_lo_specchio():
    specchio = lambda righe: [(t, 2.2 - o, 2.2 - l, 2.2 - h, 2.2 - c) for t, o, h, l, c in righe]
    quarti = SALITA + [TURTLE_SOUP, (1.1120, 1.1125, 1.1095, 1.1100), (1.1100, 1.1102, 1.1080, 1.1085)]
    a = candele("EURUSD", TF.H4, specchio(ALTE))
    b = candele("EURUSD", TF.M15, specchio([(C2 + n * Q, *r) for n, r in enumerate(quarti)]))
    crt = [c for c in caccia(a, b) if c.verso is Verso.LONG and c.range_inizio == C1][0]
    s = scatto(crt, b)
    assert s.livello == pytest.approx(2.2 - 1.1090)
    assert s.quando == C2 + 4 * Q
    op = piano(s, b)
    assert op.stop == pytest.approx(2.2 - 1.1130) and op.tp2 == pytest.approx(2.2 - 1.1000)


def test_niente_sbirciate():
    m = passeggiata("EURUSD", ny(2026, 9, 6, 17), ny(2026, 9, 11, 17), seme=11)
    alte, basse = costruisci(m, TF.H4), costruisci(m, TF.M15)
    tutti = scatti(caccia(alte, basse), basse)
    assert tutti, "la passeggiata deve produrre qualche scatto"
    for istante in range(int(basse.fine[40]), int(basse.fine[-1]), 5 * Q):
        a, b = alte.chiuse_entro(istante), basse.chiuse_entro(istante)
        allora = {(s.crt.range_inizio, s.crt.verso, s.quando, s.livello) for s in scatti(caccia(a, b), b)}
        attesi = {(s.crt.range_inizio, s.crt.verso, s.quando, s.livello) for s in tutti if s.quando <= istante}
        assert allora == attesi, istante


def test_dopo_uno_stop_si_ritenta_con_un_turtle_soup_nuovo():
    from nvm.prova.base import opera

    # Primo Model#1, poi una spinta nuova (rialzista, oltre il vecchio
    # estremo) che prende lo stop e fa da turtle soup; poi il crollo.
    quarti = SALITA + [
        TURTLE_SOUP, (1.1120, 1.1125, 1.1095, 1.1085),      # scatto 1
        (1.1085, 1.1150, 1.1084, 1.1145),                    # stop, e turtle soup nuovo
        (1.1145, 1.1146, 1.1060, 1.1070),                    # scatto 2
        (1.1070, 1.1071, 1.0990, 1.0995),                    # target
    ]
    crt, b = _crt(quarti)
    a = candele("EURUSD", TF.H4, ALTE)
    r = opera(a, b, C1, C3 + 4 * 3600)
    corti = [x for x in r if x.verso is Verso.SHORT]
    assert [x.uscita.value for x in corti] == ["stop", "target"]


def test_stop_stretto_oltre_il_livello():
    crt, b = _crt(SALITA + [TURTLE_SOUP, (1.1120, 1.1125, 1.1095, 1.1100), (1.1100, 1.1102, 1.1080, 1.1085)])
    s = scatto(crt, b)
    op = piano(s, b, stop_stretto=True)
    # Livello 1.1090 piu' il 10% dell'escursione del turtle soup (1.1130 - 1.1088).
    assert op.stop == pytest.approx(1.1090 + 0.1 * (1.1130 - 1.1088))
