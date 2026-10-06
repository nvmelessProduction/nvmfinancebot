"""Il metodo delle foto del proprietario (`spec/metodo_foto.md`, `casi/ESEMPI-PROPRIETARIO.md`).

Le prove con i dati scritti a mano rifanno la struttura delle foto; quelle in fondo rifanno gli esempi veri
sui dati di Dukascopy, se ci sono (stanno in `dati/`, che non va nel repository)."""

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from nvm.agenti import foto as F
from nvm.agenti.cacciatore import Verso
from nvm.dati.minuti import Minuti
from nvm.tempo import TF, ny
from tests.aiuti import candele

ORA = 3600


def _ore(righe, strumento="EURUSD", spread=0.0001):
    """Orarie scritte a mano: (inizio, apertura, massimo, minimo, chiusura)."""
    punto = Minuti.vuoti(strumento).punto
    t = np.array([r[0] for r in righe], np.int64)
    bid = np.rint(np.array([r[1:] for r in righe]) / punto).astype(np.int64)
    v = np.ones(len(t), np.float32)
    return Minuti(strumento, t, bid, bid + int(round(spread / punto)), v, v.copy(), passo=ORA)


def _candela_in_ore(t0, ore, o, h, l, c):
    """Una candela di `ore` ore fatta di orarie: sale al massimo, scende al minimo, chiude."""
    terzo = max(ore // 3, 1)
    righe, p = [], o
    for k in range(ore):
        if k < terzo:
            q = o + (h - o) * (k + 1) / terzo
            righe.append((t0 + k * ORA, p, max(p, q), min(p, q), q))
        elif k < 2 * terzo:
            q = h + (l - h) * (k - terzo + 1) / terzo
            righe.append((t0 + k * ORA, p, max(p, q), min(p, q), q))
        else:
            q = l + (c - l) * (k - 2 * terzo + 1) / max(ore - 2 * terzo, 1)
            righe.append((t0 + k * ORA, p, max(p, q), min(p, q), q))
        p = righe[-1][4]
    # Il massimo e il minimo esatti.
    righe = [(t, o_, min(h_, h), max(l_, l), c_) for t, o_, h_, l_, c_ in righe]
    return righe


# --- Il CRT della foto base (CASO-009): 4 ore, la candela 2 prende il DL e rientra ----------------------

def _foto_base():
    """Martedi' 8/9/2026 (sessione): lunedi' ha DL 1.0990 e DH 1.1060; martedi' a 4 ore la candela 1 (22-2 NY)
    fa 1.0995-1.1020, la candela 2 (2-6 NY) scende a 1.0980 (prende la candela 1 e il DL) e chiude 1.1005."""
    righe = []
    lunedi = ny(2026, 9, 6, 18)          # la giornata di lunedi' apre domenica alle 18 di New York
    righe += _candela_in_ore(lunedi, 24, 1.1000, 1.1060, 1.0990, 1.1002)
    martedi = ny(2026, 9, 7, 18)
    righe += _candela_in_ore(martedi, 4, 1.1002, 1.1006, 1.0998, 1.1003)            # 18-22: niente
    righe += _candela_in_ore(martedi + 4 * ORA, 4, 1.1003, 1.1020, 1.0995, 1.1010)  # candela 1
    righe += _candela_in_ore(martedi + 8 * ORA, 4, 1.1010, 1.1015, 1.0980, 1.1005)  # candela 2
    righe += _candela_in_ore(martedi + 12 * ORA, 4, 1.1005, 1.1040, 1.1001, 1.1030)  # candela 3
    return _ore(righe), martedi + 12 * ORA


def test_il_crt_base_si_entra_all_apertura_della_candela_3():
    ore, n3 = _foto_base()
    q = F.Quadro.da(ore, n3)
    trovati = [s for s in F.trova(q, TF.H4, n3, n3) if s.verso is Verso.LONG]
    assert len(trovati) == 1
    s = trovati[0]
    assert s.n3_inizio == n3 and (s.range_basso, s.range_alto) == pytest.approx((1.0995, 1.1020))
    # Entrata all'apertura della candela 3 (la chiusura della 2, finche' la prima ora non e' chiusa).
    assert s.entrata == pytest.approx(1.1005)
    # Stop sotto il minimo della candela 2; TP1 l'altro lato del range.
    assert s.stop == pytest.approx(1.0980) and s.tp1 == pytest.approx(1.1020)
    # Il key level preso: il minimo di ieri (DL).
    assert [l.nome for l in s.presi] == ["DL"] and s.presi[0].prezzo == pytest.approx(1.0990)
    # Il target finale: senza gap, l'altro lato del giorno di cui ha preso il minimo, il DH.
    ob = F.obiettivo_finale(q, s)
    assert ob.tipo == "key level" and ob.nome == "DH" and ob.prezzo == pytest.approx(1.1060)


def test_la_candela_2_che_chiude_fuori_non_e_un_crt():
    ore, n3 = _foto_base()
    # Chiusura della candela 2 sotto il range (1.0995): ha accettato sotto, niente CRT.
    k = int(np.flatnonzero(ore.t == n3 - ORA)[0])
    ore.bid[k, 3] = ore.bid[k, 2] = round(1.0988 / ore.punto)
    q = F.Quadro.da(ore, n3)
    assert not [s for s in F.trova(q, TF.H4, n3, n3) if s.verso is Verso.LONG]


def test_la_candela_2_non_deve_sforare():
    """Il proprietario, 07/10/2026: *"non deve sforare"*. La chiusura sul lato e' ancora dentro, un filo oltre no
    (la foto 6 della cartella 5 chiudeva 0,1 sopra: non e' un CRT)."""
    def con_chiusura(c2):
        righe = [(ny(2026, 9, 8, 2) - 8 * ORA, 1.1000, 1.1005, 1.0995, 1.1000)]
        righe += _candela_in_ore(ny(2026, 9, 8, 2) - 4 * ORA, 4, 1.1000, 1.1100, 1.1000, 1.1090)    # candela 1
        righe += _candela_in_ore(ny(2026, 9, 8, 2), 4, 1.1090, 1.1140, 1.1040, c2)                  # candela 2
        return _ore(righe)
    n3 = ny(2026, 9, 8, 6)
    for c2, crt in ((1.1100, True), (1.1101, False), (1.1060, True)):
        q = F.Quadro.da(con_chiusura(c2), n3)
        assert bool([s for s in F.trova(q, TF.H4, n3, n3) if s.verso is Verso.SHORT]) is crt, c2


def test_il_range_e_la_candela_madre_se_ci_sono_inside_bar():
    """Foto 7 della cartella 2: il TP1 e' il "range low H6", il minimo della candela madre."""
    t0 = ny(2026, 5, 11, 12)
    righe = []
    righe += _candela_in_ore(t0 - 6 * ORA, 6, 4700.0, 4705.0, 4695.0, 4700.0)
    righe += _candela_in_ore(t0, 6, 4700.0, 4758.0, 4664.0, 4740.0)            # la madre
    righe += _candela_in_ore(t0 + 6 * ORA, 6, 4740.0, 4748.5, 4717.0, 4729.0)  # inside bar (la "N1" della foto)
    righe += _candela_in_ore(t0 + 12 * ORA, 6, 4729.0, 4783.0, 4726.0, 4729.5)  # candela 2: prende 4758, rientra
    ore = _ore(righe, "XAUUSD", spread=0.3)
    n3 = t0 + 18 * ORA
    q = F.Quadro.da(ore, n3)
    s = next(s for s in F.trova(q, TF.H6, n3, n3) if s.verso is Verso.SHORT)
    assert s.dentro == 1 and s.range_alto == pytest.approx(4758.0) and s.tp1 == pytest.approx(4664.0)


def test_il_crt_a_un_ora_vuole_il_key_level_del_giorno_e_il_massimo_a_4_ore():
    """La foto 6 della cartella 4 e la risposta 9: *"se il prezzo prende kl daily e sbilancia un max minimo h4 e
    si forma un crt h1 noi entriamo sulla terza candela h1"*."""
    from nvm.vivo.giro import setup_buono
    righe = []
    ieri = ny(2026, 9, 9, 18)
    righe += _candela_in_ore(ieri - 24 * ORA, 24, 4440.0, 4475.0, 4400.0, 4450.0)   # DH 4475
    righe += _candela_in_ore(ieri, 4, 4450.0, 4466.0, 4448.0, 4460.0)               # H4: massimo 4466
    righe += [(ieri + 4 * ORA + k * ORA, 4460.0, 4462.0, 4455.0, 4458.0) for k in range(4)]
    righe += [(ieri + 8 * ORA, 4458.0, 4475.0 - 0.0, 4451.0, 4470.0),               # candela 1 a 1 ora
              (ieri + 9 * ORA, 4470.0, 4480.2, 4454.3, 4469.2)]                     # candela 2: prende DH e H4
    ore = _ore(righe, "XAUUSD", spread=0.3)
    n3 = ieri + 10 * ORA
    q = F.Quadro.da(ore, n3)
    s = next(s for s in F.trova(q, TF.H1, n3, n3) if s.verso is Verso.SHORT)
    assert any(l.nome == "DH" for l in s.presi) and s.h4_preso is not None and setup_buono(s)
    # Senza il key level del giorno il CRT a 1 ora non vale.
    s.presi = []
    assert not setup_buono(s)


# --- Le fasi del gap, l'RSI e la liquidazione --------------------------------------------------------

def test_le_fasi_del_gap_aggressione_reazione_liquidazione_continuazione():
    """La risposta 7: aggressione (entra nel gap con forza), reazione automatica (reagisce nel verso del gap),
    liquidazione (prende il minimo dell'aggressione), continuazione (fatte le tre, l'RSI fa minimi crescenti
    mentre il prezzo li fa decrescenti)."""
    t0 = ny(2026, 3, 2, 18)
    p = 1.1300
    righe = []
    for k in range(40):                                  # sopra il gap
        righe.append((t0 + k * ORA, p, p + 0.0005, p - 0.0005, p))
    t = t0 + 40 * ORA
    for k in range(10):                                  # aggressione: giu' forte fino a 1.1170
        q_ = p - 0.0013
        righe.append((t, p, p, q_, q_))
        p, t = q_, t + ORA
    for k in range(6):                                   # reazione automatica: su
        q_ = p + 0.0012
        righe.append((t, p, q_, p, q_))
        p, t = q_, t + ORA
    ore = _ore(righe)
    # Il gap giornaliero rialzista 1.1100-1.1250: il primo tocco e' l'ora in cui il prezzo scende sotto 1.1250.
    g = F.Gap(TF.D1, True, 1.1100, 1.1250, t0 + ORA)
    g.toccato = int(ore.t[np.flatnonzero(ore.bid[:, 2] * ore.punto <= 1.1250)[0]])
    q = F.Quadro.da(ore, t)
    f = F.fase(q, g, t)
    assert f.numero == 2 and f.estremo == pytest.approx(p - 6 * 0.0012, abs=2e-4)
    minimo_aggr = f.estremo
    for k in range(12):                                  # liquidazione lenta: un filo sotto il minimo
        q_ = p - (p - (minimo_aggr - 0.0003)) / (12 - k)
        righe.append((t, p, p, q_, q_))
        p, t = q_, t + ORA
    q = F.Quadro.da(_ore(righe), t)
    f = F.fase(q, g, t)
    # Il minimo nuovo e' arrivato piano: l'RSI non scende come prima, e' la continuazione.
    assert f.numero == 4 and f.divergenza


def test_davanti_a_un_gap_che_ha_appena_reagito_il_target_e_la_liquidazione():
    """Foto 1 della cartella 4 e 4 della cartella 3: il gap toccato ha reagito contro di noi; il target del short
    e' il minimo dell'aggressione (la liquidazione), non oltre."""
    g = F.Gap(TF.W1, True, 4120.0, 4310.0, 0, toccato=1)
    s = F.Setup("XAUUSD", TF.H4, Verso.SHORT, 0, 4495.0, 4419.0, 0, 0, 10, 20, 4510.0, 4458.0, 4486.0, 4486.0, 0.3,
                4511.0, 4419.0)

    class Q:
        pass
    orig_contro, orig_fase, orig_target = F.gap_contro, F.fase, F.gap_target
    try:
        F.gap_contro = lambda q, s, t=None: [g]
        F.fase = lambda q, g, t: F.Fase(2, False, "reazione", 4282.0)
        F.gap_target = lambda q, s, t=None: []
        ob = F.obiettivo_finale(Q(), s)
    finally:
        F.gap_contro, F.fase, F.gap_target = orig_contro, orig_fase, orig_target
    assert ob.tipo == "liquidazione" and ob.prezzo == 4282.0


# --- La direzione di una candela -------------------------------------------------------------------

def test_la_candela_che_non_accetta():
    c = candele("EURUSD", TF.MN, [
        (ny(2026, 1, 1), 1.10, 1.12, 1.08, 1.11),
        (ny(2026, 2, 1), 1.11, 1.13, 1.09, 1.10),   # prende il massimo e chiude dentro: non accetta, giu'
        (ny(2026, 3, 1), 1.10, 1.12, 1.095, 1.11),  # inside bar: non accetta, resta giu'
        (ny(2026, 4, 1), 1.11, 1.15, 1.10, 1.14),   # chiude sopra il massimo: accetta, su
        (ny(2026, 5, 1), 1.14, 1.145, 1.09, 1.12),  # prende il minimo e chiude dentro: su
        (ny(2026, 6, 1), 1.12, 1.16, 1.08, 1.12),   # prende tutti e due i lati: niente
    ])
    assert [F.bias_candela(c, k)[0] for k in range(1, 6)] == [-1, -1, 1, 1, 0]


# --- Il DXY ---------------------------------------------------------------------------------------

def test_il_dxy_si_calcola_dalle_coppie_e_vale_per_tutte_le_coppie_col_dollaro():
    t = [ny(2026, 9, 8, 2) + k * ORA for k in range(3)]
    prezzi = {"EURUSD": 1.10, "USDJPY": 150.0, "GBPUSD": 1.30, "USDCAD": 1.37, "USDCHF": 0.80}
    basi = {k: _ore([(x, p, p, p, p) for x in t], k, spread=0.0) for k, p in prezzi.items()}
    m = F.dxy(basi)
    atteso = F.COSTANTE_DXY * np.prod([prezzi[k] ** w for k, w in F.PESI_DXY.items()])
    assert m.strumento == "DXY" and m.bid[0, 3] * m.punto == pytest.approx(atteso, rel=1e-4)
    assert 90 < atteso < 115
    # L'euro scende: il dollaro sale.
    basi["EURUSD"] = _ore([(x, 1.10, 1.10, 1.08, 1.08) for x in t], "EURUSD", spread=0.0)
    assert F.dxy(basi).bid[0, 3] > m.bid[0, 3]
    # Un setup rialzista del DXY vende le coppie col dollaro sotto e compra quelle col dollaro sopra.
    assert F.verso_dal_dxy("EURUSD", Verso.LONG) is Verso.SHORT
    assert F.verso_dal_dxy("XAUUSD", Verso.LONG) is Verso.SHORT
    assert F.verso_dal_dxy("USDJPY", Verso.LONG) is Verso.LONG
    assert F.verso_dal_dxy("EURJPY", Verso.LONG) is None
    # Senza tutte le coppie il DXY non c'e'.
    del basi["USDCAD"]
    assert F.dxy(basi) is None


# --- Gli esempi veri del proprietario, sui dati di Dukascopy ---------------------------------------

DATI = Path(__file__).resolve().parent.parent / "dati" / "grezzi"
ROMA = ZoneInfo("Europe/Rome")
# id, strumento, timeframe, apertura della candela 3 (ora italiana), verso, target finale sullo spot (il
# target del proprietario sul future, meno la differenza fra future e spot sul TP1). Le quattro foto dell'oro
# di aprile-giugno 2026 mancano: nei nostri dati non c'e' marzo 2026, e il gap dei 3 mesi esce sbagliato.
ESEMPI = [
    ("2/1", "EURUSD", TF.W1, "2026-02-16 00:00", "S", 1.1404),
    ("2/2", "EURUSD", TF.MN, "2026-05-01 00:00", "S", 1.1373),
    ("2/3", "EURUSD", TF.W1, "2026-06-01 00:00", "S", 1.1412),
    ("2/6", "XAUUSD", TF.D1, "2026-08-26 00:00", "S", 4308.6),
    ("3/1", "EURUSD", TF.MN, "2025-12-01 00:00", "L", 1.1779),
    ("3/2", "EURUSD", TF.W1, "2025-11-10 00:00", "L", 1.1798),
    ("3/3", "EURUSD", TF.D1, "2025-11-06 00:00", "L", 1.1803),
    ("3/4", "XAUUSD", TF.H4, "2026-09-03 20:00", "S", 4283.1),
    ("4/1", "EURUSD", TF.W1, "2026-09-14 00:00", "S", 1.1358),
    ("4/6", "XAUUSD", TF.H1, "2026-09-10 09:00", "S", 4285.4),
    ("5/1", "GBPUSD", TF.MN, "2025-12-01 00:00", "L", 1.3793),
    ("5/2", "GBPUSD", TF.W1, "2025-11-10 00:00", "L", 1.3794),
    ("5/8", "XAUUSD", TF.H4, "2026-09-02 08:00", "L", 4475.6),
    ("CASO-009", "XAUUSD", TF.H4, "2022-11-08 12:00", "L", 1683.7),
]


@pytest.mark.skipif(not (DATI / "ore" / "EURUSD").exists(), reason="servono i dati di Dukascopy in dati/grezzi")
@pytest.mark.parametrize("nome,strumento,tf,quando,verso,finale", ESEMPI)
def test_gli_esempi_del_proprietario(nome, strumento, tf, quando, verso, finale):
    from nvm.dati.ore import carica
    from nvm.vivo.giro import setup_buono
    U = dt.timezone.utc
    n3 = int(dt.datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA).timestamp())
    m, _ = carica(DATI, strumento, int(dt.datetime(2010, 1, 1, tzinfo=U).timestamp()), n3 + 1, solo_bid=True)
    q = F.Quadro.da(m, n3)
    s = next(x for x in F.trova(q, tf, n3, n3) if x.verso is (Verso.SHORT if verso == "S" else Verso.LONG))
    assert s.presi and setup_buono(s), nome
    assert F.direzione(q, s).ok, nome
    ob = F.obiettivo_finale(q, s)
    # Il target del proprietario sta sul future: si confronta entro mezzo range.
    assert abs(ob.prezzo - finale) <= 0.5 * (s.range_alto - s.range_basso) + 0.004 * finale, (nome, ob)
