"""Le foto del grafico per Telegram, disegnate dal bot (il proprietario: *"quando manda le foto non si legge"*)."""

from types import SimpleNamespace as NS

import pytest

pytest.importorskip("matplotlib")

from nvm.dati.candele import costruisci
from nvm.tempo import TF
from nvm.vivo import foto_grafico
from nvm.vivo.giro import giro
from tests.test_vivo import CapoFinto, ore_finte

PNG = b"\x89PNG\r\n\x1a\n"


def _decisione():
    # Su EURUSD si entra solo col pattern del DXY (20/10/2026): un DXY che va al contrario dell'euro.
    from tests.test_intelligenti import _dxy_specchio
    base = ore_finte(giorni=400)
    return giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto(),
                gemelli={"EURUSD": base, "DXY": _dxy_specchio(base)})[-1]


def test_la_foto_di_un_operazione_e_un_png_grande_e_chiaro():
    d = _decisione()
    png = foto_grafico.operazione_foto(d)
    assert png.startswith(PNG) and len(png) > 20_000
    # Grande abbastanza per il telefono: 1280 x 1000.
    larghezza, altezza = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    assert (larghezza, altezza) == (1280, 1000)


def test_un_target_lontano_si_scrive_al_bordo_senza_schiacciare_le_candele():
    base = ore_finte(giorni=30)
    c = costruisci(base, TF.H4)
    vicino = float(c.bid[-1, 3])
    q = foto_grafico.Quadro("prova", linee=[foto_grafico.Linea(vicino * 1.002, "TP1", foto_grafico.VERDE),
                                            foto_grafico.Linea(vicino * 0.5, "Target finale", foto_grafico.VERDE)])
    assert foto_grafico.disegna(c, q).startswith(PNG)


def test_le_etichette_a_destra_non_si_coprono():
    ys = foto_grafico._distanzia([1.0, 1.001, 1.0015, 2.0], 0.01)
    ordinate = sorted(ys)
    assert all(b - a >= 0.01 - 1e-12 for a, b in zip(ordinate, ordinate[1:]))


def test_il_comando_grafico_con_le_operazioni_aperte():
    base = ore_finte(giorni=30)
    c = costruisci(base, TF.H1)
    p = float(c.bid[-1, 3])
    v = NS(verso="short", quando=int(c.inizio[-5]), ingresso=p, stop=p * 1.002, tp1=p * 0.998, tp2=p * 0.995)
    assert foto_grafico.grafico(c, "EURUSD", [v]).startswith(PNG)
