"""Il campo di prova: spread, stop prima del target, pareggio dalla candela dopo."""

import pytest

from nvm.agenti.cacciatore import Verso
from nvm.prova.campo import COMMISSIONE, Operazione, Uscita, simula
from nvm.tempo import TF, ny
from tests.aiuti import candele

Q = 15 * 60
T0 = ny(2026, 9, 10, 5)


def _basse(righe, spread=0.0):
    c = candele("EURUSD", TF.M15, [(T0 + n * Q, *r) for n, r in enumerate(righe)])
    c.ask = c.bid + spread
    return c


def _short(**k):
    base = dict(strumento="EURUSD", verso=Verso.SHORT, quando=T0, ingresso=1.1080, stop=1.1100, tp1=1.1050, tp2=1.1000)
    base.update(k)
    return Operazione(**base)


def test_short_che_arriva_al_target():
    esito = simula(_short(), _basse([(1.108, 1.109, 1.104, 1.105), (1.105, 1.106, 1.0995, 1.100)]))
    assert esito.uscita is Uscita.TARGET and esito.tp1_preso
    # Meta' a 1,5 R e meta' a 4 R, meno la commissione.
    assert esito.erre == pytest.approx(0.5 * 1.5 + 0.5 * 4.0 - COMMISSIONE["EURUSD"] / 0.002)


def test_stop_e_target_nella_stessa_candela_vince_lo_stop():
    esito = simula(_short(), _basse([(1.108, 1.1105, 1.0990, 1.100)]))
    assert esito.uscita is Uscita.STOP
    assert esito.erre == pytest.approx(-1 - esito.costo_erre)


def test_lo_stop_dello_short_scatta_sull_ask():
    # Il bid arriva a 1.1098, l'ask a 1.11005: lo short e' stoppato.
    esito = simula(_short(), _basse([(1.108, 1.1098, 1.107, 1.108)], spread=0.00025))
    assert esito.uscita is Uscita.STOP


def test_dopo_il_primo_target_il_pareggio_vale_dalla_candela_dopo():
    # La candela del primo target torna sopra l'ingresso: non conta.
    righe = [(1.108, 1.1085, 1.1045, 1.1078), (1.1078, 1.1079, 1.1060, 1.1070)]
    esito = simula(_short(), _basse(righe), scadenza=T0 + 2 * Q)
    assert esito.tp1_preso and esito.uscita is Uscita.SCADUTA
    righe.append((1.107, 1.1085, 1.106, 1.108))
    esito = simula(_short(), _basse(righe))
    assert esito.uscita is Uscita.PAREGGIO
    assert esito.erre == pytest.approx(0.5 * 1.5 - esito.costo_erre)


def test_il_long_compra_in_ask_e_chiude_in_bid():
    op = Operazione("EURUSD", Verso.LONG, T0, ingresso=1.1002, stop=1.0990, tp1=1.1030, tp2=1.1060, parziale=0.0)
    # Il bid tocca 1.1060: target.
    esito = simula(op, _basse([(1.100, 1.1060, 1.0995, 1.105)], spread=0.0002))
    assert esito.uscita is Uscita.TARGET
    assert esito.erre == pytest.approx((1.1060 - 1.1002) / 0.0012 - esito.costo_erre)


def test_livelli_dalla_parte_sbagliata_sono_rifiutati():
    with pytest.raises(ValueError):
        _short(stop=1.1070)
    with pytest.raises(ValueError):
        _short(tp1=1.1090)
