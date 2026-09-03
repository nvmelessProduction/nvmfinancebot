"""Collaudo di core/parametri.py.

Non verifica la strategia — quella non e' ancora scritta. Verifica che il
meccanismo dei punti aperti funzioni: che i bloccanti si rifiutino di
rispondere e che i non bloccanti restituiscano il proprio default.

E' il collaudo del guardiano, non di cio' che sorveglia.
"""

from __future__ import annotations

import pytest

from core import parametri
from core.parametri import TF, PuntoApertoError


# ---------------------------------------------------------------------------
# Coerenza interna
# ---------------------------------------------------------------------------
def test_verifica_interna_passa() -> None:
    parametri.verifica()


def test_ogni_punto_aperto_cita_le_regole() -> None:
    """Un punto aperto senza ID di regola non e' rintracciabile nei documenti."""
    for identificativo, punto in parametri.PUNTI_APERTI.items():
        assert punto.regole, f"{identificativo} non cita alcuna regola"
        for regola in punto.regole:
            prefisso = regola.split("-")[0]
            assert prefisso in {
                "DEF", "SETUP", "GEST", "RISK", "CTX", "PRIN", "ESCL", "GIUD", "PA",
            }, f"{identificativo} cita un ID di famiglia ignota: {regola}"


# ---------------------------------------------------------------------------
# Il meccanismo dei punti aperti
# ---------------------------------------------------------------------------
def test_un_bloccante_non_deciso_solleva() -> None:
    with pytest.raises(PuntoApertoError) as errore:
        parametri.richiedi("PA-62")
    messaggio = str(errore.value)
    assert "PA-62" in messaggio
    assert "DEF-47" in messaggio, "il messaggio deve dire quale regola e' coinvolta"
    assert "SCELTE" in messaggio, "il messaggio deve dire come si scioglie"


def test_un_non_bloccante_restituisce_il_default() -> None:
    assert parametri.richiedi("PA-46") == 0.0
    assert parametri.richiedi("PA-55") == "astieniti"
    assert parametri.richiedi("PA-39") == "solo_statistica"


def test_una_scelta_scioglie_il_blocco(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(parametri.SCELTE, "REV-10", "ridotta")
    assert parametri.gerarchia() == parametri.GERARCHIA_RIDOTTA
    monkeypatch.setitem(parametri.SCELTE, "REV-10", "completa")
    assert parametri.gerarchia() == parametri.GERARCHIA_COMPLETA


def test_una_lettura_inventata_viene_rifiutata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrivere qualcosa in SCELTE non basta: deve essere una lettura prevista."""
    monkeypatch.setitem(parametri.SCELTE, "REV-10", "media_delle_due")
    with pytest.raises(PuntoApertoError):
        parametri.gerarchia()


def test_punto_sconosciuto() -> None:
    with pytest.raises(KeyError):
        parametri.richiedi("PA-999")


def test_elenco_bloccanti_coerente() -> None:
    bloccanti = parametri.bloccanti_non_decisi()
    assert bloccanti, "oggi ci sono ancora punti bloccanti aperti"
    for identificativo in bloccanti:
        assert not parametri.deciso(identificativo)
        with pytest.raises(PuntoApertoError):
            parametri.richiedi(identificativo)


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


def test_universo_conforme_a_prin08() -> None:
    assert set(parametri.UNIVERSO) == {
        "XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY",
    }
    assert parametri.UNIVERSO["USDJPY"].future == "6J"
    assert parametri.UNIVERSO["USDJPY"].segno_invertito is True   # DEF-33
    assert parametri.UNIVERSO["EURUSD"].segno_invertito is False
    assert parametri.UNIVERSO["XAUUSD"].deriva_direzione_dal_dxy is False  # PRIN-09


def test_setup19_e_speculare() -> None:
    """La tabella DXY deve essere l'una l'opposta dell'altra, senza eccezioni."""
    opposto = {"BUY": "SELL", "SELL": "BUY"}
    for coppia, direzione in parametri.DIREZIONE_DA_BIAS_DXY["LONG"].items():
        assert parametri.DIREZIONE_DA_BIAS_DXY["SHORT"][coppia] == opposto[direzione]
    assert parametri.DIREZIONE_DA_BIAS_DXY["NESSUNA"] == {}


def test_def46_target_di_ogni_timeframe() -> None:
    assert parametri.TARGET_DI[TF.H1] is TF.H4
    assert parametri.TARGET_DI[TF.D1] is TF.W1
    assert parametri.TARGET_DI[TF.M6] is TF.M12
    assert parametri.TARGET_DI[TF.M12] is None       # rimanda a DEF-22
    assert TF.H12 not in parametri.TARGET_DI         # solo gap (DEF-31)
    assert TF.H6 not in parametri.TARGET_DI


# ---------------------------------------------------------------------------
# I due punti che toccano i soldi
# ---------------------------------------------------------------------------
def test_size_non_calcolabile_senza_pa62() -> None:
    """Senza il fattore k nessuna size e' calcolabile: e' giusto che si fermi."""
    with pytest.raises(PuntoApertoError):
        parametri.fattore_conversione_punto("EURUSD")


def test_pa62_parziale_non_basta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compilare k per alcuni strumenti non sblocca gli altri."""
    monkeypatch.setitem(parametri.SCELTE, "PA-62", {"EURUSD": 1.0})
    assert parametri.fattore_conversione_punto("EURUSD") == 1.0
    with pytest.raises(PuntoApertoError) as errore:
        parametri.fattore_conversione_punto("USDJPY")
    assert "USDJPY" in str(errore.value)


def test_rischio_richiede_rev42(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il rischio per posizione non si calcola finche' non si sa se le
    posizioni aperte vengano ridimensionate: cambia l'esposizione totale."""
    with pytest.raises(PuntoApertoError):
        parametri.rischio_per_posizione(1, "EURUSD")

    monkeypatch.setitem(parametri.SCELTE, "REV-42", "ridimensiona")
    assert parametri.rischio_per_posizione(1, "EURUSD") == 0.0100
    assert parametri.rischio_per_posizione(2, "EURUSD") == 0.0075
    assert parametri.rischio_per_posizione(3, "EURUSD") == 0.0045
    assert parametri.rischio_per_posizione(9, "EURUSD") == 0.0045


def test_xauusd_richiede_rev03(monkeypatch: pytest.MonkeyPatch) -> None:
    """RISK-02 esclude l'oro, RISK-06 lo include: va deciso prima di operarci."""
    monkeypatch.setitem(parametri.SCELTE, "REV-42", "ridimensiona")
    with pytest.raises(PuntoApertoError):
        parametri.rischio_per_posizione(2, "XAUUSD")

    monkeypatch.setitem(parametri.SCELTE, "REV-03", "rischio_pieno_risk01")
    assert parametri.rischio_per_posizione(2, "XAUUSD") == 0.0100

    monkeypatch.setitem(parametri.SCELTE, "REV-03", "scala_risk02")
    assert parametri.rischio_per_posizione(2, "XAUUSD") == 0.0075


def test_strumento_fuori_universo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(parametri.SCELTE, "REV-42", "ridimensiona")
    with pytest.raises(ValueError):
        parametri.rischio_per_posizione(1, "BTCUSD")   # ESCL-05, PRIN-08


# ---------------------------------------------------------------------------
# Calendario
# ---------------------------------------------------------------------------
def test_festivita_solo_per_anno_di_validita() -> None:
    festivita = parametri.calendario_festivita_valido_per(2026)
    assert (12, 25) in festivita
    assert (1, 19) in festivita          # MLK 2026
    with pytest.raises(PuntoApertoError) as errore:
        parametri.calendario_festivita_valido_per(2027)
    assert "PA-53" in str(errore.value)


def test_finestra_news() -> None:
    assert parametri.FINESTRA_NEWS_MINUTI_PRIMA == 30    # CTX-02, RISK-13
    assert parametri.FINESTRA_NEWS_MINUTI_DOPO == 30
    assert parametri.NEWS_IMPATTO_MINIMO_STELLE == 3
