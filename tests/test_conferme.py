"""Le Conferme: key level e orario, su candele scritte a mano e senza sbirciate."""

import numpy as np

from nvm.agenti.cacciatore import CRT, MAI, Motivo, Verso
from nvm.agenti.conferme import SOPRA, KeyLevel, key_level, orario
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele, costruisci
from nvm.prova.base import Risultato, opera
from nvm.prova.campo import Uscita
from nvm.prova.confronto import confronta
from nvm.tempo import TF, ny
from tests.aiuti import candele, passeggiata

# Sei giornate: un massimo di swing a 1.1040 (corpo fino a 1.0990) il giorno
# 2, un vuoto ribassista fra 1.0930 e 1.0970 (giorni 2-4) e uno piccolo fra
# 1.0890 e 1.0900 (giorni 3-5), poi un giorno calmo fino a 1.0920 che
# riempie il vuoto piccolo.
GIORNI = [
    (1.0900, 1.0950, 1.0880, 1.0940),
    (1.0940, 1.0990, 1.0930, 1.0980),
    (1.0980, 1.1040, 1.0970, 1.0990),
    (1.0990, 1.1000, 1.0900, 1.0910),
    (1.0910, 1.0930, 1.0850, 1.0860),
    (1.0860, 1.0890, 1.0840, 1.0880),
    (1.0880, 1.0920, 1.0880, 1.0900),
]
INIZIO = [ny(2026, 3, 1 + d, 17) for d in range(len(GIORNI) + 1)]
MANIPOLAZIONE = INIZIO[len(GIORNI)]


def _dati(specchio: bool = False, preso_dopo: float = None):
    """Le giornate e le loro candele da 4 ore; con `specchio` i prezzi rovesciati."""
    righe_d = [(INIZIO[d], *p) for d, p in enumerate(GIORNI)]
    righe_h4 = []
    for d, (o, h, l, c) in enumerate(GIORNI):
        righe_h4.append((INIZIO[d], o, h, l, c))
        righe_h4 += [(INIZIO[d] + 4 * 3600 * k, c, c, c, c) for k in range(1, 6)]
    if preso_dopo is not None:
        # Un'ora in cui il prezzo torna su, prima della manipolazione.
        righe_h4[-1] = (righe_h4[-1][0], 1.0900, preso_dopo, 1.0900, 1.0900)
    if specchio:
        righe_d = [(t, 2.2 - o, 2.2 - l, 2.2 - h, 2.2 - c) for t, o, h, l, c in righe_d]
        righe_h4 = [(t, 2.2 - o, 2.2 - l, 2.2 - h, 2.2 - c) for t, o, h, l, c in righe_h4]
    return candele("EURUSD", TF.D1, righe_d), candele("EURUSD", TF.H4, righe_h4)


def _scatto(estremo: float, verso: Verso = Verso.SHORT) -> Scatto:
    alto, basso = (1.0920, 1.0880) if verso is Verso.SHORT else (2.2 - 1.0880, 2.2 - 1.0920)
    crt = CRT(
        "EURUSD", TF.H4, TF.M15, verso, INIZIO[6], alto, basso,
        armato_quando=MANIPOLAZIONE + 900, decaduto_quando=MAI, motivo=Motivo.SCADENZA,
        manipolazione_inizio=MANIPOLAZIONE, fine_candela_3=MAI,
        estremo_istanti=np.array([MANIPOLAZIONE + 900], np.int64),
        estremo_valori=np.array([estremo]),
    )
    return Scatto(crt, MANIPOLAZIONE + 3600, 0, 1.0915, MANIPOLAZIONE, estremo, 1.0900)


def test_key_level_dice_in_quali_zone_e_entrata_la_manipolazione():
    sopra, basse = _dati()
    assert key_level(_scatto(1.0925), sopra, basse) == KeyLevel(False, False, False)
    assert key_level(_scatto(1.0950), sopra, basse) == KeyLevel(False, False, True)
    assert key_level(_scatto(1.1000), sopra, basse) == KeyLevel(False, True, True)
    assert key_level(_scatto(1.1050), sopra, basse) == KeyLevel(True, True, True)
    assert key_level(_scatto(1.1050), sopra, basse).quanti == 3
    # Il CRT e' ampio 40 pip: arrivare al massimo e' finirci entro 4 pip.
    assert key_level(_scatto(1.1042), sopra, basse) == KeyLevel(True, True, True, tocca=True)
    assert key_level(_scatto(1.1037), sopra, basse) == KeyLevel(False, True, True, tocca=True)


def test_il_long_e_lo_specchio_dello_short():
    sopra, basse = _dati(specchio=True)
    for estremo, atteso in ((1.0925, KeyLevel(False, False, False)), (1.1000, KeyLevel(False, True, True)),
                            (1.1050, KeyLevel(True, True, True)), (1.1042, KeyLevel(True, True, True, True))):
        assert key_level(_scatto(2.2 - estremo, Verso.LONG), sopra, basse) == atteso


def test_una_zona_gia_presa_non_conta():
    # Prima della manipolazione il prezzo e' gia' tornato a 1.1045: il
    # massimo e' preso e il vuoto e' riempito.
    sopra, basse = _dati(preso_dopo=1.1045)
    assert key_level(_scatto(1.1050), sopra, basse) == KeyLevel(False, False, False)


def test_senza_abbastanza_candele_non_sa():
    sopra, basse = _dati()
    assert key_level(_scatto(1.1050), sopra.prime(5), basse) is not None  # ne bastano 5
    corte = Candele(sopra.strumento, sopra.tf, sopra.inizio[3:], sopra.fine[3:], sopra.bid[3:], sopra.ask[3:], sopra.volume[3:])
    assert key_level(_scatto(1.1050), corte, basse) is None


def test_il_key_level_non_sbircia_il_futuro():
    m = passeggiata("EURUSD", ny(2026, 1, 4, 17), ny(2026, 5, 29, 17), seme=5)
    alte, basse = costruisci(m, TF.D1), costruisci(m, TF.H1)
    sopra = costruisci(m, SOPRA[TF.D1])
    risultati = opera(alte, basse, ny(2026, 3, 1, 17), ny(2026, 5, 29, 17))
    assert len(risultati) > 20
    risposte = []
    for r in risultati:
        s = r.scatto
        tutto = key_level(s, sopra, basse)
        allora = key_level(s, sopra.chiuse_entro(s.quando), basse.chiuse_entro(s.quando))
        assert tutto == allora
        risposte.append(tutto)
    assert any(k is not None and k.quanti for k in risposte)


def test_orario_in_ora_di_new_york():
    s = _scatto(1.0950)
    ore = candele("EURUSD", TF.H1, [(ny(2026, 3, 10, 9), 1, 1, 1, 1), (ny(2026, 3, 10, 13), 1, 1, 1, 1)])
    s.indice = 0
    o = orario(s, ore)
    assert (o.ora_scatto, o.ora_manipolazione, o.gct) == (9, 17, True)
    s.indice = 1
    assert not orario(s, ore).gct


def test_il_confronto_vede_una_conferma_che_separa():
    rng = np.random.default_rng(2)
    si = rng.random(2000) < 0.3
    erre = rng.normal(0, 1, 2000) + np.where(si, 0.3, -0.1)
    risultati = [Risultato("EURUSD", TF.D1, TF.H1, Verso.SHORT, int(i) * 86400, float(e), Uscita.STOP, False, 0.0, 1.0)
                 for i, e in enumerate(erre)]
    c = confronta(risultati, si)
    assert c.basso > 0.2 and c.alto < 0.6
    assert abs(c.differenza - (erre[si].mean() - erre[~si].mean())) < 1e-12
    casuale = confronta(risultati, rng.random(2000) < 0.3)
    assert casuale.basso < 0 < casuale.alto or abs(casuale.differenza) < 0.15


def test_il_bias_del_foglio_di_romeo():
    from nvm.agenti.conferme import Bias, bias

    prima = np.array([1.10, 1.12, 1.09, 1.11])
    riga = lambda o, h, l, c: np.array([o, h, l, c])
    assert bias(prima, riga(1.11, 1.13, 1.10, 1.125)) is Bias.RIALZISTA   # chiude sopra
    assert bias(prima, riga(1.10, 1.10, 1.08, 1.085)) is Bias.RIBASSISTA  # chiude sotto
    assert bias(prima, riga(1.11, 1.13, 1.10, 1.115)) is Bias.RIBASSISTA  # ombra sopra
    assert bias(prima, riga(1.10, 1.11, 1.08, 1.095)) is Bias.RIALZISTA   # ombra sotto
    assert bias(prima, riga(1.10, 1.13, 1.08, 1.10)) is Bias.NEUTRO       # tutte e due le ombre
    assert bias(prima, riga(1.10, 1.11, 1.095, 1.105)) is Bias.NEUTRO     # dentro


def test_il_contesto_non_sbircia_il_futuro():
    from nvm.agenti.conferme import contesto

    m = passeggiata("EURUSD", ny(2026, 1, 4, 17), ny(2026, 5, 29, 17), seme=7)
    alte, basse, sopra = costruisci(m, TF.D1), costruisci(m, TF.H1), costruisci(m, TF.W1)
    risultati = opera(alte, basse, ny(2026, 3, 1, 17), ny(2026, 5, 29, 17))
    assert len(risultati) > 20
    for r in risultati:
        q = r.scatto.quando
        assert contesto(r.scatto, alte, sopra) == contesto(r.scatto, alte.chiuse_entro(q), sopra.chiuse_entro(q))
