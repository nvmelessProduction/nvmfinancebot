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
from nvm.tempo import TF, ny, utc
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
    """Martedi' 8/9/2026 (sessione): lunedi' ha DL 1.0990 e DH 1.1060; martedi' a 4 ore la candela 1 (21-1 NY)
    fa 1.0995-1.1020, la candela 2 (1-5 NY) scende a 1.0980 (prende la candela 1 e il DL) e chiude 1.1005."""
    righe = []
    lunedi = ny(2026, 9, 6, 17)          # la giornata di lunedi' apre domenica alle 17 di New York
    righe += _candela_in_ore(lunedi, 24, 1.1000, 1.1060, 1.0990, 1.1002)
    martedi = ny(2026, 9, 7, 17)
    righe += _candela_in_ore(martedi, 4, 1.1002, 1.1006, 1.0998, 1.1003)            # 17-21: niente
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
        righe = [(ny(2026, 9, 8, 1) - 8 * ORA, 1.1000, 1.1005, 1.0995, 1.1000)]
        righe += _candela_in_ore(ny(2026, 9, 8, 1) - 4 * ORA, 4, 1.1000, 1.1100, 1.1000, 1.1090)    # candela 1
        righe += _candela_in_ore(ny(2026, 9, 8, 1), 4, 1.1090, 1.1140, 1.1040, c2)                  # candela 2
        return _ore(righe)
    n3 = ny(2026, 9, 8, 5)
    for c2, crt in ((1.1100, True), (1.1101, False), (1.1060, True)):
        q = F.Quadro.da(con_chiusura(c2), n3)
        assert bool([s for s in F.trova(q, TF.H4, n3, n3) if s.verso is Verso.SHORT]) is crt, c2


def test_il_range_e_la_candela_madre_se_ci_sono_inside_bar():
    """Foto 7 della cartella 2: il TP1 e' il "range low H6", il minimo della candela madre."""
    t0 = ny(2026, 5, 11, 11)
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


def test_un_gap_gia_toccato_non_e_un_target():
    """Il proprietario, 07/10/2026 (euro-yen): *"il gap è già stato mitigato quindi non può essere un target"*. Prima
    il target era l'estremo dell'aggressione nel gap toccato (la liquidazione): ora no, si va al key level."""
    g = F.Gap(TF.W1, True, 4120.0, 4310.0, 0, toccato=1)
    s = F.Setup("XAUUSD", TF.H4, Verso.SHORT, 0, 4495.0, 4419.0, 0, 0, 10, 20, 4510.0, 4458.0, 4486.0, 4486.0, 0.3,
                4511.0, 4419.0)

    class Q:
        pass
    orig = F.gap_contro, F.fase, F.gap_di, F.kl_target
    try:
        F.gap_contro = lambda q, s, t=None: [g]
        F.fase = lambda q, g, t: F.Fase(2, False, "reazione", 4282.0)
        F.gap_di = lambda q, tf, t: [g]
        F.kl_target = lambda q, s: F.Livello(TF.D1, False, 4341.0, 0)
        ob = F.obiettivo_finale(Q(), s)
    finally:
        F.gap_contro, F.fase, F.gap_di, F.kl_target = orig
    assert ob.tipo == "key level" and ob.prezzo == 4341.0


def test_un_gap_la_cui_terza_candela_accetta_non_e_un_target():
    """Il proprietario, 07/10/2026 (euro-australiano): *"la terza candela accetta la precedente e quindi il target
    non è il gap bensì il kl"*, *"si vale per ogni gap"*."""
    giorni = [ny(2026, 9, 21 + k, 18) for k in range(4)]
    # Un gap ribassista giornaliero: candela 1 col minimo 1.1050, candela 2 grande giu', candela 3 col massimo 1.1000.
    def quadro(chiusura_3):
        c = candele("EURUSD", TF.D1, [
            (giorni[0], 1.1100, 1.1120, 1.1050, 1.1060),
            (giorni[1], 1.1060, 1.1065, 1.0980, 1.0990),
            (giorni[2], 1.0990, 1.1000, 1.0940, chiusura_3),
        ])
        q = F.Quadro("EURUSD", giorni[3], {TF.D1: c, TF.H1: candele("EURUSD", TF.H1, [(giorni[3], 1.0950, 1.0951, 1.0949, 1.0950)])})
        return F.gap_di(q, TF.D1, giorni[3])
    (accetta,) = quadro(1.0950)          # chiude sotto il minimo della candela 2: accetta
    (non_accetta,) = quadro(1.0985)      # chiude dentro la candela 2
    assert accetta.terza_accetta and not non_accetta.terza_accetta


def test_la_candela_precedente_che_ha_accettato_contro_blocca_finche_non_prende_il_suo_livello():
    """Il proprietario, 07/10/2026 (franco-yen): *"la candela trimestrale ha accettato a ribasso quindi ci aspettiamo
    che il minimo trimestrale venga preso e solo dopo ha senso cercare buy"*; vale per giorno, settimana, 1, 3 e 12
    mesi."""
    trimestri = [ny(2026, 3, 31, 18), ny(2026, 6, 30, 18), ny(2026, 9, 30, 18)]
    c = candele("EURUSD", TF.Q3, [
        (trimestri[0], 1.10, 1.12, 1.08, 1.11),
        (trimestri[1], 1.11, 1.115, 1.06, 1.07),     # chiude sotto il minimo di prima: accetta giu', livello 1.06
    ])
    def quadro(minimo_dopo):
        ore = candele("EURUSD", TF.H1, [(trimestri[2] + k * ORA, 1.07, 1.075, minimo_dopo if k == 5 else 1.065, 1.07)
                                        for k in range(10)])
        return F.Quadro("EURUSD", trimestri[2] + 10 * ORA, {TF.Q3: c, TF.H1: ore})
    a = F.accettazione(quadro(1.065), TF.Q3, trimestri[2] + 10 * ORA)
    assert a.verso == -1 and a.livello == 1.06 and not a.preso
    assert F.accettazione(quadro(1.0590), TF.Q3, trimestri[2] + 10 * ORA).preso
    s = F.Setup("EURUSD", TF.H4, Verso.LONG, 0, 1.075, 1.065, 0, 0, trimestri[2] + 10 * ORA, 0, 1.07, 1.064, 1.068,
                1.068, 0.0001, 1.064, 1.075)
    d = F.direzione(quadro(1.065), s)
    assert not d.ok and d.comando is TF.Q3 and "prima si aspetta" in d.testo
    # Preso il minimo, il trimestre non blocca piu'; e per vendere e' dalla nostra parte.
    assert F.direzione(quadro(1.0590), s).comando is not TF.Q3
    s_short = F.Setup("EURUSD", TF.H4, Verso.SHORT, 0, 1.075, 1.065, 0, 0, trimestri[2] + 10 * ORA, 0, 1.076, 1.066,
                      1.07, 1.07, 0.0001, 1.0761, 1.065)
    assert F.direzione(quadro(1.065), s_short).ok


def test_al_tp1_si_chiude_il_25_per_cento():
    # Il proprietario, 07/10/2026: *"deve prendere il 25% dell'operazione al posto del 50%"*.
    from nvm.vivo.giro import piani_foto
    s = F.Setup("EURUSD", TF.H4, Verso.LONG, 0, 1.1020, 1.0995, 0, 0, 10, 20, 1.1015, 1.0980, 1.1005, 1.1005, 0.0001,
                1.0980, 1.1020)
    piani = piani_foto(s, F.Obiettivo(1.1060, "key level", "DH"), None, 10)
    assert piani[1].parziale == 0.25 and piani[1].pareggio and piani[1].tp2 == 1.1060
    # Tutto al TP1 renderebbe 0,54 R: sotto l'1,5 del proprietario non si usa.
    assert piani[0] is None


def test_sotto_1_a_1_e_mezzo_non_si_entra():
    # Il proprietario, 12/10/2026, su un US30 col target quasi raggiunto dalla candela 2: *"1/1,5"*.
    from nvm.vivo.giro import piani_foto
    s = F.Setup("EURUSD", TF.H4, Verso.LONG, 0, 1.1020, 1.0995, 0, 0, 10, 20, 1.1015, 1.0980, 1.1005, 1.1005, 0.0001,
                1.0980, 1.1020)
    rischio = s.ingresso - s.stop
    sotto = F.Obiettivo(s.ingresso + 1.4 * rischio, "key level", "DH")
    assert piani_foto(s, sotto, None, 10) == [None, None, None]
    giusto = F.Obiettivo(s.ingresso + 1.5 * rischio, "key level", "DH")
    piani = piani_foto(s, sotto, giusto, 10)
    assert piani[0] is None and piani[1] is None and piani[2].tp2 == giusto.prezzo
    tutto_al_tp1 = F.Setup("EURUSD", TF.H4, Verso.LONG, 0, 1.1060, 1.0995, 0, 0, 10, 20, 1.1015, 1.0980, 1.1005, 1.1005,
                           0.0001, 1.0980, 1.1060)
    piani = piani_foto(tutto_al_tp1, F.Obiettivo(tutto_al_tp1.tp1, "range", "l'altro lato del range"), None, 10)
    assert piani[0].tp2 == tutto_al_tp1.tp1 and piani[1] is None


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
# Con le regole del 07/10/2026 ("valgono per tutto") questi esempi non si prendono piu' o cambiano target. Il
# proprietario lo sa (`registro/tentativi.md`, 07/10/2026): se una regola va ristretta lo dice lui.
# id -> (timeframe che blocca, o None; target nuovo, o None se resta quello della foto)
CAMBIATI = {
    "2/1": (TF.MN, None),          # il mensile di gennaio 2026 ha accettato al rialzo e non ha preso il suo massimo
    "3/4": (TF.MN, 4418.915),      # il mensile ha accettato al rialzo; il gap toccato non e' piu' un target
    "4/1": (TF.MN, 1.15662),       # come 2/1 (agosto 2026); la liquidazione nel gap dei 3 mesi non e' piu' un target
    "4/6": (TF.MN, 4340.965),      # il mensile; target il DL (il gap settimanale toccato non e' piu' un target)
    "5/8": (TF.Q3, None),          # il 3 mesi (dati dell'oro di marzo 2026 mancanti: puo' essere un errore dei dati)
    "CASO-009": (TF.Q3, None),     # il 3 mesi di luglio-settembre 2022 ha accettato al ribasso, minimo non preso
}


# Con le candele di MT5 (dalle 17 di New York, dall'08/10/2026) questo esempio non e' piu' un CRT: era uno dei tre
# sull'oro a 4 ore che lo erano solo con le candele del future (e il 3 mesi lo bloccava comunque, sopra).
NON_CRT_MT5 = {"5/8"}


@pytest.mark.skipif(not (DATI / "ore" / "EURUSD").exists(), reason="servono i dati di Dukascopy in dati/grezzi")
@pytest.mark.parametrize("nome,strumento,tf,quando,verso,finale", ESEMPI)
def test_gli_esempi_del_proprietario(nome, strumento, tf, quando, verso, finale):
    from nvm.dati.ore import carica
    from nvm.vivo.giro import setup_buono
    U = dt.timezone.utc
    n3 = int(dt.datetime.strptime(quando, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA).timestamp())
    # Le ore delle foto sono quelle delle candele dei future (mezzanotte italiana); dall'08/10/2026 le candele sono
    # quelle di MT5, che aprono un'ora prima (le 23 italiane). Le orarie non cambiano.
    if tf is not TF.H1:
        n3 -= 3600
    m, _ = carica(DATI, strumento, int(dt.datetime(2010, 1, 1, tzinfo=U).timestamp()), n3 + 1, solo_bid=True)
    q = F.Quadro.da(m, n3)
    trovati = [x for x in F.trova(q, tf, n3, n3) if x.verso is (Verso.SHORT if verso == "S" else Verso.LONG)]
    if nome in NON_CRT_MT5:
        assert not trovati, nome
        return
    s = trovati[0]
    assert s.presi and setup_buono(s), nome
    blocca, nuovo = CAMBIATI.get(nome, (None, None))
    d = F.direzione(q, s)
    if blocca is None:
        assert d.ok, nome
    else:
        assert not d.ok and d.comando is blocca, (nome, d.testo)
    ob = F.obiettivo_finale(q, s)
    if nuovo is not None:
        assert ob.prezzo == pytest.approx(nuovo, rel=1e-6), (nome, ob)
        return
    # Il target del proprietario sta sul future: si confronta entro mezzo range.
    assert abs(ob.prezzo - finale) <= 0.5 * (s.range_alto - s.range_basso) + 0.004 * finale, (nome, ob)


# --- Le crypto con gli orari crypto: BTC la notte del 7-8 ottobre 2026 ------------------------------------

# Le orarie di BTC-USD (Yahoo, arrotondate al dollaro): (giorno, ora UTC, apertura, massimo, minimo, chiusura).
_BTC_7_8_OTTOBRE = [
    (7, 12, 83700, 83734, 83382, 83464), (7, 13, 83464, 83523, 82733, 83140), (7, 14, 83162, 83254, 82877, 82971),
    (7, 15, 82907, 83421, 82765, 83417), (7, 16, 83406, 83645, 83317, 83347), (7, 17, 83340, 83581, 82999, 83116),
    (7, 18, 83099, 83434, 83099, 83373), (7, 19, 83392, 83482, 83254, 83392), (7, 20, 83398, 83568, 83280, 83379),
    (7, 21, 83384, 83410, 83071, 83110), (7, 22, 83118, 83288, 83088, 83197), (7, 23, 83188, 83371, 83082, 83275),
    (8, 0, 83276, 83391, 83164, 83324), (8, 1, 83319, 83471, 83042, 83057), (8, 2, 83064, 83234, 82876, 83116),
    (8, 3, 83116, 83154, 82593, 82696), (8, 4, 82711, 82874, 82215, 82593), (8, 5, 82594, 82971, 82522, 82625),
    (8, 6, 82618, 82903, 82439, 82814), (8, 7, 82814, 83230, 82654, 82939), (8, 8, 82935, 82999, 82726, 82812),
    (8, 9, 82820, 83113, 82766, 83060),
]


def test_le_crypto_si_leggono_con_gli_orari_crypto():
    """Il proprietario, 08/10/2026: il bot ha comprato BTC a 6 ore alle 6 di New York con le candele dalle 18 di New
    York, ma *"nel tf h6 non abbiamo avuto una presa liquidita' ma bensi' il prezzo ha accettato a ribasso"*. Con
    gli orari crypto (6 ore alle 2, 8, 14, 20 italiane) la candela 2 delle 2-8 chiude sotto il range: niente CRT.
    A 4 ore invece (2-6 e 6-10 italiane) c'e' il CRT rialzista con entrata alle 10 italiane."""
    righe = [(utc(2026, 10, g, h), o, a, b, c) for g, h, o, a, b, c in _BTC_7_8_OTTOBRE]
    q = F.Quadro.da(_ore(righe, "BTCUSD", spread=10.0), utc(2026, 10, 8, 10))
    assert all(int(x) % (6 * ORA) == 0 for x in q.candele[TF.H6].inizio)
    assert not [s for s in F.trova(q, TF.H6, utc(2026, 10, 8, 0), utc(2026, 10, 8, 10)) if s.verso is Verso.LONG]
    a4 = F.trova(q, TF.H4, utc(2026, 10, 8, 8), utc(2026, 10, 8, 8))
    assert len(a4) == 1 and a4[0].verso is Verso.LONG
    s = a4[0]
    assert (s.range_basso, s.range_alto, s.stop, s.tp1, s.entrata) == (82593, 83471, 82215, 83471, 82935)


# --- Il DXY dal grafico del broker (USDX su FP Markets), non piu' calcolato ----------------------------------

def test_l_agente_dxy_legge_il_grafico_usdx_e_non_lo_calcola_piu():
    """Il proprietario, 08/10/2026: *"il dxy non dovrà più essere generato ma bisognerà far sì che l'agente dxy
    analizzi il grafico che su fptrading si chiama USDX"*. Il DXY fa il CRT rialzista della foto base (prende il DL e
    rientra): l'euro, che gli va contro, vende e l'agente DXY ha il suo setup. Senza il grafico, niente DXY, anche se
    ci sono tutte le coppie da cui prima lo si calcolava."""
    from nvm.vivo import giro as G
    from tests.test_vivo import CapoFinto
    ore, n3 = _foto_base()
    righe = [(int(t), *(float(x) * ore.punto for x in b)) for t, b in zip(ore.t, ore.bid)]
    prima = [(int(ore.t[0]) - k * ORA, 1.1000, 1.1003, 1.0997, 1.1000) for k in range(240, 0, -1)]
    righe = prima + righe
    dxy = _ore([(t, 90 * o, 90 * h, 90 * l, 90 * c) for t, o, h, l, c in righe], "DXY", spread=0.0)
    euro = _ore([(t, 1.21 / o, 1.21 / l, 1.21 / h, 1.21 / c) for t, o, h, l, c in righe], "EURUSD")
    coppie = {k: euro for k in F.PESI_DXY}
    assert G._dxy(coppie, n3) is None
    assert G._dxy({**coppie, "DXY": dxy}, n3).strumento == "DXY"
    con = [d for d in G.occasioni_foto("EURUSD", euro, n3, n3, CapoFinto(), {**coppie, "DXY": dxy})
           if d.r.verso is Verso.SHORT]
    senza = [d for d in G.occasioni_foto("EURUSD", euro, n3, n3, CapoFinto(), coppie) if d.r.verso is Verso.SHORT]
    assert con and con[0].foto["dxy"] is not None and con[0].foto["dxy"].verso is Verso.LONG
    assert senza and senza[0].foto["dxy"] is None


def test_lo_stoppino_del_rollover_non_e_una_presa():
    # Il proprietario, 12/10/2026, GBPCAD del 9/10: *"il dl non è stato sbilanciato"*. Su FP il minimo era uno
    # stoppino dell'ora del rollover (le 17 di New York): lo spread si allarga, il mercato non ci e' andato.
    t0 = ny(2026, 9, 8, 17)
    righe = [(t0 + k * ORA, 1.1000, 1.1050 if k == 0 else 1.1010, 1.0950 if k == 0 else 1.0990, 1.1000)
             for k in range(6)]
    q = F.Quadro.da(_ore(righe), t0 + 6 * ORA)
    assert F._senza_rollover(q, t0, t0 + 6 * ORA) == pytest.approx((1.1010, 1.0990))
    assert F._senza_rollover(q, t0, t0 + ORA) is None


def test_lo_stop_troppo_vicino_si_allarga_non_si_scarta():
    # Il proprietario, 12/10/2026: *"aumenta di poco lo stop ... da un minimo di 5 o 10 pips ... non lo levare"*.
    for meta, atteso in ((0.0050, 0.07 * 0.0100), (0.0010, 5 * 0.0001)):
        t0 = ny(2026, 9, 1, 17)
        righe = [(t0 + k * ORA, 1.1000, 1.1000 + meta, 1.1000 - meta, 1.1000) for k in range(24 * 20)]
        q = F.Quadro.da(_ore(righe), t0 + 24 * 20 * ORA)
        assert F.stop_minimo(q, t0 + 24 * 20 * ORA) == pytest.approx(atteso)


# --- La TOTAL per le crypto ------------------------------------------------------------------------------

def _crypto(minimo_2, alto_1=1.1020, scala=1.0):
    """Un CRT a 4 ore con gli orari crypto (candele dalla mezzanotte UTC): ieri DL 1.0990; la candela 1 (4-8 UTC)
    fa 1.0995-`alto_1`, la candela 2 (8-12) scende a `minimo_2` e chiude 1.1005; la candela 3 apre alle 12 UTC."""
    giorno = utc(2026, 9, 7)
    righe = [(giorno - 24 * ORA - k * ORA, 1.1000, 1.1003, 1.0997, 1.1000) for k in range(240, 0, -1)]
    righe += _candela_in_ore(giorno - 24 * ORA, 24, 1.1000, 1.1060, 1.0990, 1.1002)
    righe += _candela_in_ore(giorno, 4, 1.1002, 1.1006, 1.0998, 1.1003)
    righe += _candela_in_ore(giorno + 4 * ORA, 4, 1.1003, alto_1, 1.0995, 1.1010)
    righe += _candela_in_ore(giorno + 8 * ORA, 4, 1.1010, 1.1015, minimo_2, 1.1005)
    righe += _candela_in_ore(giorno + 12 * ORA, 4, 1.1005, 1.1040, 1.1001, 1.1030)
    return [(t, scala * o, scala * h, scala * l, scala * c) for t, o, h, l, c in righe], giorno + 12 * ORA


def test_un_setup_della_total_fa_entrare_le_crypto_dalla_stessa_parte():
    """Il proprietario, 12/10/2026: la TOTAL guida BTC ed ETH come il DXY le coppie, ma nello stesso verso (*"B,
    esatto"*). Qui la TOTAL prende il DL e rientra (CRT rialzista); BTC da solo non fa il CRT, ma si compra lo stesso."""
    from nvm.dati.candele import weekend
    from nvm.vivo import giro as G
    from tests.test_vivo import CapoFinto
    assert weekend("TOTAL")                        # gli orari delle crypto
    assert F.verso_dal_totale("BTCUSD", Verso.LONG) is Verso.LONG and F.verso_dal_totale("EURUSD", Verso.LONG) is None
    righe_t, n3 = _crypto(1.0980, scala=3e12)
    righe_b, _ = _crypto(1.0996, alto_1=1.1030, scala=6e4)
    totale = _ore(righe_t, "TOTAL", spread=0.0)
    btc = _ore(righe_b, "BTCUSD", spread=5.0)
    (st,) = F.trova(F.Quadro.da(totale, n3), TF.H4, n3, n3)
    assert st.verso is Verso.LONG and st.presi
    assert not F.trova(F.Quadro.da(btc, n3), TF.H4, n3, n3)
    con = G.occasioni_foto("BTCUSD", btc, n3, n3, CapoFinto(), {"TOTAL": totale})
    assert len(con) == 1 and con[0].r.verso is Verso.LONG and con[0].foto["setup"].dal_totale
    # La TOTAL fa il CRT anche a 6 ore: l'occasione e' quella del timeframe piu' grande, col suo setup della TOTAL.
    d = con[0]
    assert d.r.scatto.modello == "dalla TOTAL" and d.foto["totale"].tf is d.r.alto_tf
    assert d.foto["totale"].verso is Verso.LONG and d.foto["totale"].strumento == "TOTAL"
    # I prezzi sono quelli di BTC: stop sul minimo della sua candela 2 a 6 ore (6-12 UTC).
    assert d.op.stop == pytest.approx(1.0995 * 6e4) and d.op.stop < d.op.ingresso < d.op.tp1
    # La squadra lo racconta come un setup della TOTAL, e il key level e' quello preso dalla TOTAL.
    from nvm.intelligenti import metodo, pareri
    m = metodo.valuta_foto(d)
    assert m.fatti["modello"] == "dalla TOTAL" and "la TOTAL" in m.obbligatorie[0].perche
    assert "il minimo" in m.obbligatorie[0].perche and m.obbligatorie[1].si
    voto = next(x for x in pareri.tutti(d, pareri.Contesto(), None) if x.agente == "DXY")
    assert voto.voto > 0 and "TOTAL" in voto.ragioni[0]
    # Senza la TOTAL niente; e sull'oro la TOTAL non conta.
    assert not G.occasioni_foto("BTCUSD", btc, n3, n3, CapoFinto(), {})
    oro = _ore(righe_b, "XAUUSD", spread=0.3)
    assert not [d for d in G.occasioni_foto("XAUUSD", oro, n3, n3, CapoFinto(), {"TOTAL": totale})
                if d.foto["setup"].dal_totale]
