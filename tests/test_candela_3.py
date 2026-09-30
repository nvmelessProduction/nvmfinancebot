"""L'entrata dei video nella candela 3 (`spec/metodo_romeo.md`), i disegni e il fine settimana."""

import numpy as np
import pytest

from nvm.agenti.cacciatore import Variante, Verso, caccia
from nvm.agenti.grilletto import scatto_candela_3
from nvm.agenti.livelli import piano
from nvm.intelligenti.fine_settimana import forma
from nvm.tempo import TF, ny
from tests.aiuti import candele

Q = 15 * 60
C1, C2, C3 = ny(2026, 9, 10, 1), ny(2026, 9, 10, 5), ny(2026, 9, 10, 9)
# Candela 1 rialzista, candela 2 prende il massimo (1.1140) e richiude dentro (1.1060).
ALTE = [(C1, 1.1000, 1.1100, 1.1000, 1.1090), (C2, 1.1090, 1.1140, 1.1040, 1.1060)]
CANDELA_2 = [(1.1080, 1.1086, 1.1078, 1.1084), (1.1084, 1.1088, 1.1080, 1.1081)] * 8
PICCOLE = [(1.1060, 1.1068, 1.1058, 1.1065), (1.1065, 1.1070, 1.1062, 1.1066)]
SPESSA = (1.1066, 1.1095, 1.1064, 1.1092)      # rialzista, massimo nuovo, sopra l'apertura (1.1060)
SOPRA = (1.1092, 1.1094, 1.1070, 1.1075)       # chiude sopra la sua apertura: non ancora
SOTTO = (1.1075, 1.1076, 1.1058, 1.1060)       # chiude sotto 1.1066: si vende


def _crt(candela_3):
    a = candele("EURUSD", TF.H4, ALTE)
    b = candele("EURUSD", TF.M15, [(C2 + n * Q, *r) for n, r in enumerate(CANDELA_2)]
                + [(C3 + n * Q, *r) for n, r in enumerate(candela_3)])
    crt = [c for c in caccia(a, b, Variante.CHIUSURA_DENTRO) if c.verso is Verso.SHORT and c.range_inizio == C1]
    return crt[0], b


def test_candela_3_come_nei_video():
    crt, b = _crt(PICCOLE + [SPESSA, SOPRA, SOTTO])
    s = scatto_candela_3(crt, b)
    assert s.modello == "candela 3" and s.quando == C3 + 5 * Q
    assert s.livello == pytest.approx(1.1066) and s.apertura_3 == pytest.approx(1.1060)
    assert s.punta == pytest.approx(1.1095) and s.spessore > 3
    op = piano(s, b)
    # Stop appena sopra la punta della candela spessa, primo obiettivo il 50%, poi il lato opposto.
    assert op.ingresso == pytest.approx(1.1060)
    assert op.stop == pytest.approx(1.1095 + 0.1 * (1.1095 - 1.1064))
    assert op.tp1 == pytest.approx(1.1050) and op.tp2 == pytest.approx(1.1000 - 0.5 * 0.0100)


def test_una_candela_sottile_non_e_il_model1():
    sottile = (1.1066, 1.1071, 1.1064, 1.1069)
    crt, b = _crt(PICCOLE + [sottile, (1.1069, 1.1070, 1.1060, 1.1062)])
    assert scatto_candela_3(crt, b) is None


def test_la_finta_sotto_l_apertura_non_conta_per_vendere():
    # La candela spessa parte sotto l'apertura della candela 3 (1.1060): non e' "vendere caro".
    bassa = [(1.1060, 1.1061, 1.1040, 1.1042), (1.1042, 1.1046, 1.1040, 1.1045)]
    spessa_bassa = (1.1045, 1.1064, 1.1044, 1.1063)
    crt, b = _crt(bassa + [spessa_bassa, (1.1063, 1.1064, 1.1040, 1.1041)])
    assert scatto_candela_3(crt, b) is None


def test_se_il_50_e_gia_preso_il_crt_ha_gia_funzionato():
    giu = (1.1060, 1.1062, 1.1045, 1.1058)      # tocca 1.1050 prima della finta
    crt, b = _crt([giu, (1.1058, 1.1066, 1.1057, 1.1065), SPESSA, SOTTO])
    assert scatto_candela_3(crt, b) is None


def test_la_candela_2_ancora_aperta_niente_candela_3():
    a = candele("EURUSD", TF.H4, ALTE[:1])
    b = candele("EURUSD", TF.M15, [(C2 + n * Q, *r) for n, r in enumerate(CANDELA_2[:6])])
    assert not [c for c in caccia(a, b, Variante.CHIUSURA_DENTRO) if c.range_inizio == C1]


def test_le_sei_forme_della_candela_settimanale():
    c = lambda o, h, l, cl: np.array([o, h, l, cl], float)
    assert forma(c(100, 111, 99, 110)) == "piena rialzista"
    assert forma(c(110, 111, 99, 100)) == "piena ribassista"
    assert forma(c(108, 110, 90, 109)).startswith("giù e poi su")
    assert forma(c(92, 110, 90, 91)).startswith("su e poi giù")
    assert forma(c(100, 104, 96, 100.5)) == "indecisa"
    assert forma(c(100, 104, 96, 101), prima=c(100, 110, 90, 105)).startswith("interna")


def test_i_programmi_dei_disegni_si_installano_e_si_compilano_una_volta(tmp_path):
    from pathlib import Path
    from nvm.vivo import disegni
    programma = tmp_path / "mt5"
    programma.mkdir()
    chiamate = []
    editor = programma / "MetaEditor64.exe"
    editor.write_text("finto")
    import subprocess

    def compila(cmd, **_):
        chiamate.append(cmd)
        sorgente = Path(cmd[1].split(":", 1)[1])
        sorgente.with_suffix(".ex5").write_text("compilato")
        return subprocess.CompletedProcess(cmd, 0)
    vero = subprocess.run
    subprocess.run = compila
    try:
        radice = Path(__file__).resolve().parent.parent
        assert disegni.installa(radice, tmp_path / "dati", programma) == (True, "")
        assert len(chiamate) == 2
        assert (tmp_path / "dati" / "MQL5" / "Services" / "NVM" / "NvmDisegni.mq5").exists()
        assert (tmp_path / "dati" / "MQL5" / "Indicators" / "NVM" / "NvmDisegni.mqh").exists()
        # La seconda volta, se niente e' cambiato, non ricompila.
        assert disegni.installa(radice, tmp_path / "dati", programma) == (True, "")
        assert len(chiamate) == 2
    finally:
        subprocess.run = vero
    # Senza MetaEditor il bot lavora lo stesso, e lo dice.
    fatto, perche = disegni.installa(Path(__file__).resolve().parent.parent, tmp_path / "altri", tmp_path / "vuota")
    assert not fatto and "senza disegni" in perche


def test_i_disegni_scadono_e_il_file_e_leggibile_da_mt5(tmp_path):
    from nvm.vivo.disegni import Disegni, Segno
    d = Disegni(tmp_path, tmp_path / "comune")
    d.metti("a", "EURUSD", [Segno("linea", 10, 1.1, 20, 1.1, testo="Obiettivo 1 (50%); più giù")], fino=100)
    d.metti("b", "GBPUSD", [Segno("testo", 10, 1.2, testo="Lunedì")], fino=1000)
    d.scrivi(500)
    righe = (tmp_path / "comune" / "nvm_disegni.csv").read_text(encoding="cp1252").split("\n")
    assert righe[0].split(";")[:3] == ["b", "GBPUSD", "testo"] and righe[0].endswith("Lunedì")
    assert len(righe[0].split(";")) == 11
    # Ricaricati dopo un riavvio.
    assert list(Disegni(tmp_path).gruppi) == ["b"]
