"""Il giudizio costa soldi veri: due freni, e devono tenere.

Il primo e' la deduplica. Un CRT vive finche' vive la sua candela di range, e
il motore lo ritrova identico a ogni chiusura del timeframe basso. Misurato il
2026-09-21 su sei ore: 46 rifiuti da una regola sola erano 14 CRT distinti, e
due comparivano undici volte ciascuno. Senza freno si paga tre volte lo stesso
giudizio per ottenere la stessa risposta.

Il secondo e' il tetto di spesa, e si misura sul consumo dichiarato dall'API:
`giudica` usa thinking adattivo, quindi i token di ragionamento non si sanno
prima e una stima sarebbe un tetto finto.
"""

import pytest

from core import budget_giudizio as budget
from core import storage


@pytest.fixture(autouse=True)
def archivio(tmp_path, monkeypatch):
    """Un archivio nuovo per ogni prova, e per costruzione, non per fortuna.

    `impostazioni()` e' `lru_cache`, quindi la PRIMA chiamata della sessione
    vince: valorizzare `DB_PATH` senza svuotare la cache isola solo il primo
    test e lascia tutti gli altri sullo stesso archivio -- oppure, se qualcosa
    ha gia' letto le impostazioni, li manda tutti sul `bot.db` vero. Le due
    cose si somigliano molto finche' non si guarda.
    """
    from core.config import impostazioni

    monkeypatch.setenv("DB_PATH", str(tmp_path / "prova.db"))
    impostazioni.cache_clear()
    monkeypatch.setattr(impostazioni(), "GIUDIZIO_EURO_AL_GIORNO", 0.0,
                        raising=False)
    assert impostazioni().DB_PATH == str(tmp_path / "prova.db")
    storage.inizializza()
    budget.prepara_tabelle()
    yield
    impostazioni.cache_clear()


def _prezzi(monkeypatch, ingresso=5.0, scritta=6.25, letta=0.50,
            uscita=25.0, tetto=1.0):
    """I prezzi veri di Claude Opus 5, presi dal listino Anthropic."""
    from core.config import impostazioni
    cfg = impostazioni()
    monkeypatch.setattr(cfg, "PREZZO_INGRESSO_PER_MILIONE", ingresso, raising=False)
    monkeypatch.setattr(cfg, "PREZZO_CACHE_SCRITTA_PER_MILIONE", scritta, raising=False)
    monkeypatch.setattr(cfg, "PREZZO_CACHE_LETTA_PER_MILIONE", letta, raising=False)
    monkeypatch.setattr(cfg, "PREZZO_USCITA_PER_MILIONE", uscita, raising=False)
    monkeypatch.setattr(cfg, "GIUDIZIO_EURO_AL_GIORNO", tetto, raising=False)


class TestDeduplica:

    def test_lo_stesso_crt_ha_la_stessa_impronta(self):
        a = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.10500, "RISK-05")
        b = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.10500, "RISK-05")
        assert a == b

    def test_un_estremo_diverso_e_un_crt_diverso(self):
        a = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.10500, "RISK-05")
        b = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.10600, "RISK-05")
        assert a != b

    def test_obiezioni_diverse_sono_domande_diverse(self):
        a = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.105, "RISK-05")
        b = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.105, "CRT-20")
        assert a != b

    def test_il_verdetto_si_ricorda(self):
        imp = budget.impronta_crt("EURUSD", "SHORT", "TF_H4", 1.105, "RISK-05")
        assert budget.gia_giudicato(imp) is None
        budget.ricorda(imp, "EURUSD", "RISK-05", "ACCETTA", "il CISD c'e'")
        assert budget.gia_giudicato(imp) == ("ACCETTA", "il CISD c'e'")

    def test_anche_un_rifiuto_si_ricorda(self):
        """Senza questo si ripagherebbe ogni "no" ad ogni candela."""
        imp = budget.impronta_crt("USDCHF", "SHORT", "TF_M5", 0.82, "RISK-05")
        budget.ricorda(imp, "USDCHF", "RISK-05", "RIFIUTA", "niente CISD")
        assert budget.gia_giudicato(imp)[0] == "RIFIUTA"


class TestTetto:

    def test_senza_tetto_si_puo_sempre(self, monkeypatch):
        _prezzi(monkeypatch, tetto=0.0)
        ok, _ = budget.c_e_budget()
        assert ok is True

    def test_il_conto_parte_da_zero(self, monkeypatch):
        _prezzi(monkeypatch)
        s = budget.speso_oggi()
        assert (s.chiamate, s.euro) == (0, 0.0)

    def test_una_chiamata_si_somma(self, monkeypatch):
        _prezzi(monkeypatch)
        euro = budget.registra(200, 0, 3000, 1500)
        atteso = (200 * 5.0 + 3000 * 0.50 + 1500 * 25.0) / 1e6
        assert euro == pytest.approx(atteso)
        s = budget.speso_oggi()
        assert s.chiamate == 1
        assert s.euro == pytest.approx(atteso)

    def test_le_chiamate_si_accumulano(self, monkeypatch):
        _prezzi(monkeypatch)
        for _ in range(3):
            budget.registra(200, 0, 3000, 1500)
        assert budget.speso_oggi().chiamate == 3

    def test_superato_il_tetto_non_si_spende_piu(self, monkeypatch):
        _prezzi(monkeypatch, tetto=0.27)
        ok, _ = budget.c_e_budget()
        assert ok is True
        # ~0,040 EUR a chiamata coi prezzi di Opus 5: alla settima si sfonda
        for _ in range(7):
            budget.registra(200, 0, 3000, 1500)
        ok, dettaglio = budget.c_e_budget()
        assert ok is False
        assert "tetto giornaliero raggiunto" in dettaglio

    def test_i_token_di_ragionamento_pesano(self, monkeypatch):
        """L'uscita domina: e' li' che finiscono i token di thinking."""
        _prezzi(monkeypatch)
        poco = budget.costo(200, 0, 3000, 100)
        molto = budget.costo(200, 0, 3000, 4000)
        assert molto > poco * 5

    def test_senza_prezzi_il_tetto_non_puo_fermare_nulla(self, monkeypatch):
        """Va detto: con i prezzi a zero il freno e' spento di fatto."""
        _prezzi(monkeypatch, ingresso=0.0, scritta=0.0, letta=0.0,
                uscita=0.0, tetto=0.27)
        budget.registra(999_999, 999_999, 999_999, 999_999)
        ok, _ = budget.c_e_budget()
        assert ok is True, "senza prezzi configurati non si puo' misurare la spesa"


def test_la_scrittura_della_cache_costa_piu_della_lettura(monkeypatch):
    """Su Opus 5 dodici volte tanto: accorparle falsa tutto il conto.

    La prima chiamata scrive le istruzioni in cache, tutte le altre le
    rileggono. Con un prezzo solo o si sovrastima ogni chiamata dopo la
    prima, o si sottostima la prima.
    """
    _prezzi(monkeypatch)
    scrive = budget.costo(200, 3000, 0, 500)
    rilegge = budget.costo(200, 0, 3000, 500)
    assert scrive > rilegge
    assert (scrive - rilegge) == pytest.approx(3000 * (6.25 - 0.50) / 1e6)
