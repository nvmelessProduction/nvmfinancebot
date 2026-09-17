"""Collaudo di core/parametri.py.

Verifica tre cose:

1. che il meccanismo dei punti aperti funzioni ancora — se domani si aggiunge
   un punto e non lo si decide, il motore deve fermarsi, non tirare a indovinare;
2. che le decisioni prese il 2026-09-03 siano tutte presenti e coerenti con
   le letture ammesse;
3. che i valori calcolati (festivita', distanza relativa, scala del rischio)
   diano i numeri giusti, compresi i casi limite.
"""

from __future__ import annotations

from datetime import date

import pytest

from core import parametri
from core.parametri import TF, PuntoApertoError


# ---------------------------------------------------------------------------
# Coerenza interna
# ---------------------------------------------------------------------------
def test_verifica_interna_passa() -> None:
    parametri.verifica()


def test_ogni_punto_aperto_cita_le_regole() -> None:
    for identificativo, punto in parametri.PUNTI_APERTI.items():
        assert punto.regole, f"{identificativo} non cita alcuna regola"
        for regola in punto.regole:
            prefisso = regola.split("-")[0]
            assert prefisso in {
                "DEF", "SETUP", "GEST", "RISK", "CTX", "PRIN", "ESCL", "GIUD", "PA",
            }, f"{identificativo} cita un ID di famiglia ignota: {regola}"


def test_nessun_bloccante_resta_aperto() -> None:
    """Dopo le decisioni del 2026-09-03 il motore non ha piu' punti fermi."""
    assert parametri.bloccanti_non_decisi() == []


def test_ogni_scelta_corrisponde_a_un_punto_noto() -> None:
    """Una scelta senza punto aperto sarebbe una decisione presa di nascosto."""
    for identificativo in parametri.SCELTE:
        assert identificativo in parametri.PUNTI_APERTI, identificativo


def test_ogni_scelta_e_una_lettura_ammessa() -> None:
    """Se un punto dichiara le letture possibili, la scelta dev'essere una di quelle."""
    for identificativo, valore in parametri.SCELTE.items():
        letture = parametri.PUNTI_APERTI[identificativo].letture
        if letture:
            assert valore in letture, f"{identificativo}: {valore!r} non e' fra {letture}"


# ---------------------------------------------------------------------------
# Il meccanismo, che deve restare vivo
# ---------------------------------------------------------------------------
def test_un_bloccante_non_deciso_solleva(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulo di aver cancellato una decisione: il motore deve fermarsi."""
    monkeypatch.delitem(parametri.SCELTE, "REV-10")
    with pytest.raises(PuntoApertoError) as errore:
        parametri.richiedi("REV-10")
    messaggio = str(errore.value)
    assert "REV-10" in messaggio
    assert "DEF-01" in messaggio, "deve dire quale regola e' coinvolta"
    assert "SCELTE" in messaggio, "deve dire come si scioglie"
    assert "completa" in messaggio, "deve elencare le letture possibili"


def test_una_lettura_inventata_viene_rifiutata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(parametri.SCELTE, "REV-10", "media_delle_due")
    with pytest.raises(PuntoApertoError):
        parametri.gerarchia()


def test_punto_sconosciuto() -> None:
    with pytest.raises(KeyError):
        parametri.richiedi("PA-999")


def test_un_non_bloccante_ha_comunque_il_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(parametri.SCELTE, "PA-46")
    monkeypatch.delitem(parametri.SCELTE, "PA-55")
    assert parametri.richiedi("PA-46") == 0.0
    assert parametri.richiedi("PA-55") == "astieniti"     # PRIN-99


def test_pa55_e_deciso_opera() -> None:
    """La lettura in vigore si scosta dal default, e non per sbaglio.

    Decisa dall'autore il 2026-09-17: il bot lavora anche senza calendario.
    Il prezzo e' che CTX-02, il divieto di aprire dentro la finestra di una
    news a tre stelle, senza calendario non ha piu' nulla contro cui
    confrontare l'orario -- quindi non blocca piu' niente.
    """
    assert parametri.richiedi("PA-55") == "opera"
    assert "opera" in parametri.PUNTI_APERTI["PA-55"].letture
    assert parametri.PUNTI_APERTI["PA-55"].default == "astieniti"


# ---------------------------------------------------------------------------
# Le decisioni, una per una
# ---------------------------------------------------------------------------
def test_rev10_gerarchia_completa() -> None:
    assert parametri.gerarchia() == parametri.GERARCHIA_COMPLETA
    # Dieci di DEF-01 piu' i tre intraday di CRT-04. Questi ultimi stanno
    # nella gerarchia per essere ORDINATI — `_piu_alto` e
    # `timeframe_crt_ammesso` li confrontano — non perche' abbiano i ruoli
    # dei timeframe alti: TF_BIAS e TARGET_DI li escludono entrambi.
    assert len(parametri.gerarchia()) == 13
    assert parametri.gerarchia()[-3:] == parametri.TF_INTRADAY
    assert TF.H12 in parametri.gerarchia()


def test_rev15_gap_scansiona_anche_h12_h6() -> None:
    ordine = parametri.ordine_scansione_gap()
    assert ordine[-2:] == (TF.H12, TF.H6)
    assert ordine[0] is TF.M12


def test_rev32_soglia_indecisione() -> None:
    assert parametri.soglia_corpo_indecisione() == 0.05


def test_rev42_ridimensionamento_attivo() -> None:
    assert parametri.posizioni_ridimensionate() is True


def test_rev14_nessun_ritardo() -> None:
    assert parametri.RITARDO_ESECUZIONE_MINUTI == 0
    assert parametri.LATENZA_DXY_MINUTI == 10          # CTX-06 lo conserva


# ---------------------------------------------------------------------------
# Rischio, per gruppo di correlazione (REV-03)
# ---------------------------------------------------------------------------
def test_gruppi_di_correlazione() -> None:
    assert parametri.gruppo_di("EURUSD") == "forex_dxy"
    assert parametri.gruppo_di("USDJPY") == "forex_dxy"
    assert parametri.gruppo_di("XAUUSD") == "oro"
    with pytest.raises(ValueError):
        parametri.gruppo_di("BTCUSD")                   # ESCL-05


def test_scala_del_rischio() -> None:
    assert parametri.rischio_per_posizione(1, "EURUSD") == 0.0100
    assert parametri.rischio_per_posizione(2, "EURUSD") == 0.0075
    assert parametri.rischio_per_posizione(3, "EURUSD") == 0.0045
    assert parametri.rischio_per_posizione(9, "EURUSD") == 0.0045


def test_oro_segue_la_scala_come_il_forex() -> None:
    """REV-03: quattro posizioni sull'oro devono valere 1,80%, non 4,00%."""
    for n in (1, 2, 3, 4):
        assert parametri.rischio_per_posizione(n, "XAUUSD") == \
               parametri.rischio_per_posizione(n, "EURUSD")
    quattro = 4 * parametri.rischio_per_posizione(4, "XAUUSD")
    assert quattro == pytest.approx(0.018)
    assert quattro < parametri.LIMITE_GIORNALIERO, "non deve sfondare RISK-07 a freddo"


def test_lettura_letterale_di_risk01_sull_oro(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'alternativa resta raggiungibile in una riga, e mostra perche' l'ho scartata."""
    monkeypatch.setitem(parametri.SCELTE, "REV-03", "rischio_pieno_risk01")
    assert parametri.rischio_per_posizione(4, "XAUUSD") == 0.0100
    quattro = 4 * parametri.rischio_per_posizione(4, "XAUUSD")
    assert quattro > parametri.LIMITE_GIORNALIERO, "quattro posizioni al 4% sfondano RISK-07"
    # Il forex resta invariato: la lettura riguarda il solo oro.
    assert parametri.rischio_per_posizione(4, "EURUSD") == 0.0045


def test_n_non_valido() -> None:
    with pytest.raises(ValueError):
        parametri.rischio_per_posizione(0, "EURUSD")
    with pytest.raises(ValueError):
        parametri.rischio_per_posizione(1, "BTCUSD")


# ---------------------------------------------------------------------------
# Size: distanza relativa invece del fattore k (PA-62)
# ---------------------------------------------------------------------------
def test_distanza_relativa_e_adimensionale() -> None:
    """Uno stop dell'1% resta l'1% su qualsiasi scala di prezzo.

    E' il motivo per cui il metodo funziona su 6J e 6S, dove un fattore k
    costante non esisterebbe.
    """
    assert parametri.distanza_relativa_stop(100.0, 99.0) == pytest.approx(0.01)
    assert parametri.distanza_relativa_stop(1.0850, 1.0850 * 0.99) == pytest.approx(0.01)
    # 6J quota circa 0.0068, USDJPY circa 147: scale incomparabili, stessa r.
    assert parametri.distanza_relativa_stop(0.0068, 0.0068 * 0.99) == pytest.approx(0.01)


def test_distanza_relativa_simmetrica() -> None:
    """Sopra o sotto il prezzo, la distanza e' la stessa: e' un valore assoluto."""
    sopra = parametri.distanza_relativa_stop(100.0, 102.0)
    sotto = parametri.distanza_relativa_stop(100.0, 98.0)
    assert sopra == sotto == pytest.approx(0.02)


def test_distanza_nulla_e_incoerente() -> None:
    """RISK-03: distanza zero significa PRIN-99, non size infinita."""
    with pytest.raises(ValueError):
        parametri.distanza_relativa_stop(100.0, 100.0)
    with pytest.raises(ValueError):
        parametri.distanza_relativa_stop(0.0, 1.0)


def test_reciproco_conserva_la_distanza_relativa() -> None:
    """La prova del nove del metodo, sul caso che rompeva DEF-47.

    6J e USDJPY sono reciproci. Una variazione relativa r sul future produce
    una variazione relativa di circa r sul CFD, con segno opposto. E' cio' che
    permette di non convertire mai un prezzo nell'altro.
    """
    prezzo_6j = 0.0068
    stop_6j = prezzo_6j * 1.01                     # stop 1% sopra, short su 6J
    r = parametri.distanza_relativa_stop(prezzo_6j, stop_6j)

    usdjpy = 1 / prezzo_6j                          # circa 147
    usdjpy_allo_stop = 1 / stop_6j
    r_cfd = abs(usdjpy - usdjpy_allo_stop) / usdjpy

    assert r == pytest.approx(0.01)
    assert r_cfd == pytest.approx(r, rel=0.02), "coincidono al primo ordine"


# ---------------------------------------------------------------------------
# Calendario calcolato (PA-53)
# ---------------------------------------------------------------------------
def test_festivita_2026_coincidono_con_ctx04() -> None:
    """Le dodici date scritte a mano in CTX-04 devono uscire dal calcolo."""
    attese = {
        (1, 1), (1, 19), (2, 16), (4, 3), (5, 25), (6, 19),
        (7, 3), (9, 7), (11, 26), (11, 27), (12, 24), (12, 25),
    }
    calcolate = parametri.calendario_festivita_valido_per(2026)
    assert {(g.month, g.day) for g in calcolate} == attese


def test_festivita_mobili_si_spostano() -> None:
    """Se non si spostassero, la tabella fissa sarebbe bastata."""
    assert parametri.calendario_festivita_valido_per(2027)[date(2027, 1, 18)] \
        == "Martin Luther King Day"
    assert date(2027, 3, 26) in parametri.calendario_festivita_valido_per(2027)  # Venerdi' Santo
    assert date(2026, 4, 3) in parametri.calendario_festivita_valido_per(2026)


def test_natale_di_sabato_collide_con_la_vigilia() -> None:
    """2027: Natale cade di sabato, l'osservanza scivola sul 24."""
    calendario = parametri.calendario_festivita_valido_per(2027)
    assert date(2027, 12, 25) not in calendario
    assert "Natale" in calendario[date(2027, 12, 24)]
    assert "Vigilia" in calendario[date(2027, 12, 24)], "nessuna delle due si perde"


def test_capodanno_di_sabato_ricade_nell_anno_prima() -> None:
    """2028: il 1 gennaio e' sabato, si osserva il 31 dicembre 2027."""
    assert date(2027, 12, 31) in parametri.calendario_festivita_valido_per(2028)
    assert parametri.e_festivita(date(2027, 12, 31)) == "Capodanno"


def test_giorni_normali_non_sono_festivi() -> None:
    assert parametri.e_festivita(date(2026, 3, 10)) is None
    assert parametri.e_festivita(date(2026, 8, 14)) is None


def test_calendario_regge_vent_anni() -> None:
    for anno in range(2020, 2041):
        calendario = parametri.calendario_festivita_valido_per(anno)
        assert 11 <= len(calendario) <= 12, (anno, len(calendario))
        etichette = sum(len(n.split(" / ")) for n in calendario.values())
        assert etichette == 12, (anno, etichette)


# ---------------------------------------------------------------------------
# I valori che i documenti hanno gia' deciso
# ---------------------------------------------------------------------------
def test_valori_certi_dai_documenti() -> None:
    assert parametri.RR_MINIMO == 1.5                    # GEST-01
    assert parametri.RISCHIO_BASE == 0.0100              # RISK-01
    assert parametri.MAX_POSIZIONI_PER_STRUMENTO == 4    # RISK-06
    assert parametri.LOOKBACK_ANNI == 5                  # DEF-26
    assert parametri.MINIMO_CANDELE_CHIUSE_PER_TF == 3   # DEF-26
    assert parametri.RSI_PERIODO == 14                   # DEF-44
    assert parametri.SOGLIA_SPIKE_RIFIUTO_FORTE == 0.5   # DEF-21
    assert parametri.FRAZIONE_CHIUSA_A_TP1 == 0.25       # SETUP-13
    assert parametri.TOLLERANZA_CONFRONTO_PREZZI == 0.0  # DEF-19, DEF-37
    assert parametri.LIMITE_GIORNALIERO == 0.03          # RISK-07


def test_universo_conforme_a_prin08() -> None:
    assert set(parametri.UNIVERSO) == {
        "XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY",
    }
    assert parametri.UNIVERSO["USDJPY"].future == "6J"
    assert parametri.UNIVERSO["USDJPY"].segno_invertito is True   # DEF-33
    assert parametri.UNIVERSO["EURUSD"].segno_invertito is False
    assert parametri.UNIVERSO["XAUUSD"].deriva_direzione_dal_dxy is False  # PRIN-09


def test_setup19_e_speculare() -> None:
    opposto = {"BUY": "SELL", "SELL": "BUY"}
    for coppia, direzione in parametri.DIREZIONE_DA_BIAS_DXY["LONG"].items():
        assert parametri.DIREZIONE_DA_BIAS_DXY["SHORT"][coppia] == opposto[direzione]
    assert parametri.DIREZIONE_DA_BIAS_DXY["NESSUNA"] == {}
    assert "XAUUSD" not in parametri.DIREZIONE_DA_BIAS_DXY["LONG"]   # PRIN-09, PA-05


def test_def46_target_di_ogni_timeframe() -> None:
    assert parametri.TARGET_DI[TF.H1] is TF.H4
    assert parametri.TARGET_DI[TF.D1] is TF.W1
    assert parametri.TARGET_DI[TF.M6] is TF.M12
    assert parametri.TARGET_DI[TF.M12] is None       # rimanda a DEF-22
    assert TF.H12 not in parametri.TARGET_DI         # solo gap (DEF-31)
    assert TF.H6 not in parametri.TARGET_DI


def test_setup05_niente_allineamento_su_h12_h6() -> None:
    """REV-11: e' la ragione per cui un CRT su quei due TF non e' eseguibile."""
    assert TF.H12 not in parametri.DUE_TF_SUPERIORI
    assert TF.H6 not in parametri.DUE_TF_SUPERIORI
    assert parametri.DUE_TF_SUPERIORI[TF.H1] == (TF.H4, TF.D1)
