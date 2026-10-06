"""Il Cacciatore, sugli schemi di Romeo e senza sbirciare il futuro.

Gli schemi sono in `spec/FONTI-ROMEO.md`: la candela 1 fa il range, la 2 esce
da un lato e rientra, la 3 va verso l'altro lato.
"""

import numpy as np
import pytest

from nvm.agenti.cacciatore import MAI, Motivo, Stato, Variante, Verso, armati_a, caccia
from nvm.dati.candele import costruisci
from nvm.tempo import TF, ny
from tests.aiuti import candele, passeggiata

Q = 15 * 60  # un quarto d'ora

# Tre candele a 4 ore: 2:00, 6:00, 10:00 di New York del 10/09/2026 (le 4 ore aprono alle 18, 22, 2, 6, 10, 14).
C1, C2, C3 = ny(2026, 9, 10, 2), ny(2026, 9, 10, 6), ny(2026, 9, 10, 10)


def _quarti(inizio, prezzi):
    """Sedici quarti d'ora dentro una candela a 4 ore: (massimo, minimo, chiusura)."""
    righe = []
    apertura = prezzi[0][2]
    for n, (h, l, c) in enumerate(prezzi):
        righe.append((inizio + n * Q, apertura, h, l, c))
        apertura = c
    return righe


def _schema_short(chiusura_2=1.1050, oltre=True, tocca_il_basso=True):
    """Lo schema "CRT is fractal" di Romeo, in versione short.

    Range 1.1000-1.1100. La candela 2 sale sopra 1.1100 e rientra; la 3 scende
    sotto 1.1000.
    """
    alte = candele("EURUSD", TF.H4, [
        (C1, 1.1000, 1.1100, 1.1000, 1.1090),
        (C2, 1.1090, 1.1130 if oltre else 1.1095, 1.1040, chiusura_2),
        (C3, chiusura_2, 1.1060, 1.0980 if tocca_il_basso else 1.1020, 1.1000 if tocca_il_basso else 1.1030),
    ])
    salita = [(1.1095, 1.1080, 1.1090)] * 5 + [(1.1130 if oltre else 1.1095, 1.1090, 1.1120 if oltre else 1.1092)]
    ritorno = [(1.1120 if oltre else 1.1095, 1.1040, chiusura_2)] + [(max(chiusura_2, 1.1060), 1.1040, chiusura_2)] * 9
    discesa = [(1.1060, 1.1040, 1.1050)] * 8 + [(1.1050, 1.0980 if tocca_il_basso else 1.1020, 1.1030)] * 8
    basse = candele("EURUSD", TF.M15, _quarti(C2, salita + ritorno) + _quarti(C3, discesa))
    return alte, basse


def _solo(crt, verso):
    trovati = [c for c in crt if c.verso is verso and c.range_inizio == C1]
    assert len(trovati) <= 1
    return trovati[0] if trovati else None


def test_lo_schema_di_romeo_arma_uno_short():
    alte, basse = _schema_short()
    crt = _solo(caccia(alte, basse), Verso.SHORT)
    assert crt is not None
    assert (crt.crt_high, crt.crt_low) == (1.1100, 1.1000)
    assert crt.crt_50 == pytest.approx(1.1050)
    # Si arma alla chiusura del sesto quarto d'ora, il primo sopra 1.1100.
    assert crt.manipolazione_inizio == C2 + 5 * Q
    assert crt.armato_quando == C2 + 6 * Q
    assert crt.estremo_a(crt.armato_quando) == pytest.approx(1.1130)
    # Decade quando la candela 3 tocca il lato opposto.
    assert crt.motivo is Motivo.LATO_OPPOSTO
    assert crt.decaduto_quando == C3 + 9 * Q
    assert crt.stato_a(C2 + 5 * Q) is Stato.NESSUNO
    assert crt.stato_a(C2 + 6 * Q) is Stato.ARMATO
    assert crt.stato_a(C3 + 9 * Q) is Stato.DECADUTO


def test_nessuna_uscita_dal_range_nessun_crt():
    alte, basse = _schema_short(oltre=False)
    assert _solo(caccia(alte, basse), Verso.SHORT) is None


def test_una_candela_piatta_non_e_un_range():
    alte, basse = _schema_short()
    alte.bid[0] = alte.ask[0] = [1.1100, 1.1100, 1.1100, 1.1100]
    assert _solo(caccia(alte, basse), Verso.SHORT) is None
    assert _solo(caccia(alte, basse), Verso.LONG) is None


def test_se_la_candela_2_chiude_fuori_e_una_rottura():
    alte, basse = _schema_short(chiusura_2=1.1120)
    crt = _solo(caccia(alte, basse), Verso.SHORT)
    assert crt.motivo is Motivo.ROTTURA
    assert crt.decaduto_quando == C3  # la chiusura della candela 2
    assert _solo(caccia(alte, basse, Variante.CHIUSURA_DENTRO), Verso.SHORT) is None


def test_senza_lato_opposto_scade_con_la_candela_3():
    alte, basse = _schema_short(tocca_il_basso=False)
    crt = _solo(caccia(alte, basse), Verso.SHORT)
    assert crt.motivo is Motivo.SCADENZA
    assert crt.decaduto_quando == ny(2026, 9, 10, 14)


def test_variante_chiusura_dentro_arma_alla_chiusura_della_candela_2():
    alte, basse = _schema_short()
    crt = _solo(caccia(alte, basse, Variante.CHIUSURA_DENTRO), Verso.SHORT)
    assert crt.armato_quando == C3
    assert crt.estremo_a(C3) == pytest.approx(1.1130)
    assert crt.motivo is Motivo.LATO_OPPOSTO


def test_il_long_e_lo_specchio():
    alte, basse = _schema_short()
    specchio = lambda c: c.__class__(c.strumento, c.tf, c.inizio, c.fine, 2.2 - c.bid[:, [0, 2, 1, 3]], 2.2 - c.ask[:, [0, 2, 1, 3]], c.volume)
    crt = _solo(caccia(specchio(alte), specchio(basse)), Verso.LONG)
    assert crt is not None
    assert (crt.crt_high, crt.crt_low) == (pytest.approx(1.1000), pytest.approx(1.0900))
    assert crt.armato_quando == C2 + 6 * Q
    assert crt.estremo_a(crt.armato_quando) == pytest.approx(1.0870)


def test_dal_vivo_la_candela_3_non_serve_ancora():
    """A meta' della candela 2 il CRT e' armato anche se la 3 non esiste."""
    alte, basse = _schema_short()
    istante = C2 + 8 * Q
    crt = _solo(caccia(alte.chiuse_entro(istante), basse.chiuse_entro(istante)), Verso.SHORT)
    assert crt.stato_a(istante) is Stato.ARMATO
    assert crt.decaduto_quando == MAI  # la scadenza non e' ancora nota


@pytest.mark.parametrize("variante", list(Variante))
def test_niente_sbirciate(variante):
    """La risposta a ogni istante e' quella che si avrebbe con i soli dati di allora."""
    m = passeggiata("EURUSD", ny(2026, 9, 6, 17), ny(2026, 9, 11, 17), seme=7)
    alte, basse = costruisci(m, TF.H4), costruisci(m, TF.M15)
    tutti = caccia(alte, basse, variante)
    assert tutti, "la passeggiata deve produrre qualche CRT"
    for istante in range(int(basse.fine[40]), int(basse.fine[-1]), 7 * Q):
        allora = caccia(alte.chiuse_entro(istante), basse.chiuse_entro(istante), variante)
        chiave = lambda c: (c.range_inizio, c.verso)
        attesi = {chiave(c): c.estremo_a(istante) for c in armati_a(tutti, istante)}
        visti = {chiave(c): c.estremo_a(istante) for c in armati_a(allora, istante)}
        assert visti == attesi, istante
