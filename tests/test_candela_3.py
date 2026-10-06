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
C1, C2, C3 = ny(2026, 9, 10, 2), ny(2026, 9, 10, 6), ny(2026, 9, 10, 10)
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
        # Su Windows il comando e' una riga sola con le virgolette, altrove una lista.
        sorgente = Path(cmd[1].split(":", 1)[1] if isinstance(cmd, list) else cmd.split(' /compile:"')[1].split('"')[0])
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
    grezzo = (tmp_path / "comune" / "nvm_disegni.csv").read_bytes()
    assert grezzo.endswith(b"\r\n") and "Lunedì".encode("cp1252") in grezzo
    righe = grezzo.decode("cp1252").split("\r\n")
    assert righe[0].split(";")[1:3] == ["GBPUSD", "testo"] and righe[0].endswith("Lunedì")
    assert len(righe[0].split(";")[0]) == 10
    assert len(righe[0].split(";")) == 11
    # Ricaricati dopo un riavvio.
    assert list(Disegni(tmp_path).gruppi) == ["b"]


def test_si_vede_se_il_programma_dei_disegni_in_mt5_lavora(tmp_path):
    from nvm.vivo.disegni import Disegni, stato_in_parole
    d = Disegni(tmp_path, tmp_path / "comune")
    assert d.stato_mt5(1000) is None and "non è acceso" in stato_in_parole(None)
    (tmp_path / "comune").mkdir()
    (tmp_path / "comune" / "nvm_disegni_stato.txt").write_text("servizio;4;990;3;40;0;0\r\n", encoding="cp1252")
    s = d.stato_mt5(1000)
    assert s["eta"] == 10 and s["grafici"] == 3 and s["oggetti"] == 40 and stato_in_parole(s) is None
    assert "Stop" in stato_in_parole({**s, "versione": "3"})
    assert "errore 4101" in stato_in_parole({**s, "oggetti": 0, "errori": 5, "ultimo_errore": 4101})
    assert "non è acceso" in stato_in_parole({**s, "eta": 3600})


def test_i_crt_in_attesa_della_candela_3_si_disegnano():
    from nvm.vivo.disegni import in_attesa
    crt, _ = _crt(PICCOLE)
    segni = in_attesa(crt, 1.1060, 3)
    testi = " ".join(s.testo for s in segni)
    for parola in ("candela 1", "CRT high", "CRT low", "50%", "Candela 3", "Finta della candela 2", "per vendere"):
        assert parola in testi, parola
    assert all(s.t1 >= C1 + 3 * 3600 for s in segni if s.tipo != "testo")


def test_dal_telefono_il_grafico_arriva_in_foto_su_telegram(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    import vivo
    from nvm.vivo import disegni
    from nvm.vivo.ambiente import Impostazioni
    from nvm.vivo.telegram import Ricevuto, Telegram
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    testi, foto = [], []
    bot = object.__new__(vivo.Bot)
    bot.imp = Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",))
    bot.tg = Telegram(bot.imp, invia=lambda c, t: testi.append((c, t)), stampa=lambda _: None,
                      invia_foto=lambda c, dati, didascalia: foto.append((c, dati, didascalia)))
    bot.terminale = NS(simbolo=lambda s: s + "+", scarto=3)
    bot.strumenti, bot.basi, bot.stato = ["EURUSD"], {}, NS(vive=[])
    bot.disegni = disegni.Disegni(tmp_path, tmp_path / "comune")
    bot._cartella_foto, bot._foto, bot._avviso_disegni = tmp_path / "MQL5" / "Files", [], 0.0
    bot._cartella_foto.mkdir(parents=True)
    bot._grafico(Ricevuto(1, "-2", "/grafico eurusd+ H4", 0))
    richiesta = next((tmp_path / "comune").glob("nvm_foto_*.req"))
    assert richiesta.read_bytes() == b"EURUSD+;H4\r\n"
    numero = richiesta.stem.split("_")[-1]
    # MT5 fa la foto: il bot la manda sul canale da cui e' arrivata la richiesta.
    png = bot._cartella_foto / f"nvm_foto_{numero}.png"
    png.write_bytes(b"\x89PNG finto")
    import os, time
    os.utime(png, (time.time() - 10, time.time() - 10))
    bot.consegna_foto()
    assert foto and foto[0][0] == "-2" and foto[0][1] == b"\x89PNG finto" and "EURUSD" in foto[0][2]
    assert not png.exists() and not bot._foto
    # Un simbolo che non c'e', e una foto che non arriva mai.
    bot._grafico(Ricevuto(2, "-1", "/grafico PIPPO", 0))
    assert "Non conosco" in testi[-1][1] and testi[-1][0] == "-1"
    bot._grafico(Ricevuto(3, "-1", "/grafico EURUSD", 0))
    assert "Ricevuto" in testi[-1][1]
    bot._foto[0]["entro"] = 0
    bot.consegna_foto()
    assert "Non sono riuscito a fotografare" in testi[-1][1] and "NvmDisegni" in testi[-1][1] and not bot._foto
    # MT5 dice perche' non ce la fa: il bot lo riferisce subito.
    bot._grafico(Ricevuto(4, "-1", "/grafico EURUSD D1", 0))
    numero = bot._foto[0]["numero"]
    (tmp_path / "comune" / f"nvm_foto_{numero}.esito").write_bytes(b"non posso aprire un grafico (errore 4111)\r\n")
    bot.consegna_foto()
    assert "errore 4111" in testi[-1][1] and not bot._foto


# --- Le regole dei video, una per una (spec/metodo_romeo.md) ---

def test_l_apertura_di_romeo_e_a_mezzanotte_di_new_york():
    from types import SimpleNamespace as NS
    from nvm.agenti.grilletto import apertura_romeo
    ore = candele("EURUSD", TF.H1, [(ny(2026, 9, 9, 17) + h * 3600, 1.10 + h / 10000, 1.11, 1.09, 1.10)
                                    for h in range(30)])
    # Il giorno: la nostra candela apre alle 17, quella di Romeo a mezzanotte (V1 21:31).
    giorno = NS(alto_tf=TF.D1, armato_quando=ny(2026, 9, 9, 17), fine_candela_3=ny(2026, 9, 10, 17))
    assert apertura_romeo(giorno, ore, ore) == (ny(2026, 9, 10, 0), pytest.approx(1.1007))
    # La settimana: lunedi' a mezzanotte, non domenica sera (V8 14:30). Il 13/09/2026 e' domenica.
    ore_s = candele("EURUSD", TF.H1, [(ny(2026, 9, 13, 17) + h * 3600, 1.20 + h / 10000, 1.21, 1.19, 1.20)
                                      for h in range(30)])
    settimana = NS(alto_tf=TF.W1, armato_quando=ny(2026, 9, 13, 17), fine_candela_3=ny(2026, 9, 18, 17))
    assert apertura_romeo(settimana, ore_s, ore_s) == (ny(2026, 9, 14, 0), pytest.approx(1.2007))
    # La candela a 4 ore apre quando apre.
    quattro = NS(alto_tf=TF.H4, armato_quando=ny(2026, 9, 9, 21), fine_candela_3=ny(2026, 9, 10, 1))
    assert apertura_romeo(quattro, ore)[0] == ny(2026, 9, 9, 21)


def test_il_model1_deve_infilarsi_in_un_vecchio_massimo():
    # Spessa e sopra l'apertura, ma il suo massimo (1.1087) resta sotto il vecchio massimo della candela 2
    # (1.1088): non ha preso niente, non e' il Model#1 di Romeo (V3 10:00).
    corta = (1.1066, 1.1087, 1.1064, 1.1086)
    crt, b = _crt(PICCOLE + [corta, SOTTO])
    assert scatto_candela_3(crt, b) is None


def test_la_seconda_entrata_vera_rottura_e_ritorno_nella_zona():
    from nvm.agenti.grilletto import scatto_vera_rottura
    candela_3 = [
        (1.1060, 1.1068, 1.1058, 1.1065), (1.1065, 1.1072, 1.1062, 1.1070), (1.1070, 1.1071, 1.1063, 1.1064),
        (1.1064, 1.1066, 1.1060, 1.1061),
        (1.1061, 1.1092, 1.1061, 1.1090),     # il turtle soup: prende il vecchio massimo (1.1088)
        (1.1090, 1.1091, 1.1070, 1.1072),
        (1.1072, 1.1073, 1.1053, 1.1055),     # chiude sotto il minimo da rompere (1.1058): rottura vera
        (1.1055, 1.1078, 1.1054, 1.1070),     # torna nella zona e richiude sotto la meta' (1.1075): si vende
    ]
    crt, b = _crt(candela_3)
    s = scatto_vera_rottura(crt, b)
    assert s is not None and s.modello == "vera rottura" and s.quando == C3 + 8 * Q
    assert s.livello == pytest.approx(1.1075) and s.punta == pytest.approx(1.1092)
    op = piano(s, b)
    # Stop al turtle soup (V11 16:30), obiettivi il 50% e il lato opposto.
    assert op.stop == pytest.approx(1.1092 + 0.1 * (1.1092 - 1.1061)) and op.tp1 == pytest.approx(1.1050)
    # Se il turtle soup viene superato prima del ritorno, l'idea non vale piu'.
    rotta = candela_3[:7] + [(1.1055, 1.1095, 1.1054, 1.1070)]
    crt, b = _crt(rotta)
    assert scatto_vera_rottura(crt, b) is None


KOD = [
    (1.1060, 1.1062, 1.1048, 1.1049),         # prende il 50% (1.1050)
    (1.1049, 1.1049, 1.1030, 1.1032), (1.1032, 1.1034, 1.1030, 1.1033), (1.1033, 1.1035, 1.1031, 1.1034),
    (1.1034, 1.1041, 1.1033, 1.1036),         # un massimo (1.1041)
    (1.1036, 1.1037, 1.1029, 1.1030), (1.1030, 1.1032, 1.1027, 1.1029),
    (1.1029, 1.1046, 1.1028, 1.1045),         # l'ultima finta: spessa, prende 1.1041, sotto il 50%
    (1.1045, 1.1046, 1.1026, 1.1028),         # chiude sotto il suo corpo: il kiss of death
]


def test_il_kiss_of_death_dopo_il_50_verso_il_lato_opposto():
    from nvm.agenti.grilletto import scatti_romeo, scatto_kod
    crt, b = _crt(KOD)
    # Il Model#1 non c'e' (il 50% e' gia' preso), il kiss of death si' (V4 06:30, V16 07:31).
    assert scatto_candela_3(crt, b) is None
    s = scatto_kod(crt, b)
    assert s is not None and s.modello == "kiss of death" and s.quando == C3 + 9 * Q
    assert [x.modello for x in scatti_romeo(crt, b)] == ["kiss of death"]
    op = piano(s, b)
    assert op.tp1 == op.tp2 == pytest.approx(1.1000) and op.parziale == 1.0
    assert op.stop == pytest.approx(1.1046 + 0.1 * (1.1046 - 1.1028))


def test_dopo_il_primo_obiettivo_il_kod_non_va_superato():
    from nvm.agenti.grilletto import kod_superato
    righe = [(1.1050, 1.1051, 1.1040, 1.1042),    # minimo nuovo
             (1.1042, 1.1048, 1.1041, 1.1047),    # il rimbalzo
             (1.1047, 1.1046, 1.1043, 1.1044)]    # massimo piu' basso e chiusura ribassista: il KOD e' 1.1048
    sopra = (1.1044, 1.1052, 1.1043, 1.1050)      # chiude sopra il KOD (V16 17:31)
    c = lambda rr: candele("EURUSD", TF.M15, [(C3 + n * Q, *r) for n, r in enumerate(rr)])
    assert kod_superato(c(righe), short=True) is None
    assert kod_superato(c(righe + [sopra]), short=True) == pytest.approx(1.1048)
    # Un minimo nuovo azzera: il KOD vecchio non conta piu'.
    assert kod_superato(c(righe + [(1.1044, 1.1045, 1.1030, 1.1031), sopra]), short=True) is None


def test_i_piani_di_livelli_prendono_sempre_qualcosa_al_50():
    from nvm.agenti.livelli import PIANI_ROMEO, PIANO_ROMEO, piani_romeo
    crt, b = _crt(PICCOLE + [SPESSA, SOPRA, SOTTO])
    piani = piani_romeo(scatto_candela_3(crt, b), b)
    assert len(piani) == len(PIANI_ROMEO) and all(p is not None for p in piani)
    # Tutti con lo stop alla punta, tutti con almeno meta' al 50% (V1 18:32).
    assert len({p.stop for p in piani}) == 1 and all(p.tp1 == pytest.approx(1.1050) and p.parziale >= 0.5 for p in piani)
    assert piani[PIANO_ROMEO].tp2 == pytest.approx(1.1000) and piani[0].parziale == 1.0
    assert piani[2].tp2 == pytest.approx(1.1000 - 0.5 * 0.0100)
