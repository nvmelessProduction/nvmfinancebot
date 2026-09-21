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


class TestVerdettoNonSiCapovolge:
    """Il difetto piu' pericoloso della giornata: un rifiuto letto come si'.

    Il 2026-09-21, in produzione, il giudizio ha risposto `ACCETTA` scrivendo
    nel motivo "Sostengo l'obiezione RISK-05". Il modello intendeva "accetto
    l'obiezione, quindi NON aprire"; il codice l'ha letta come "l'obiezione
    cade, quindi apri". Le due parole erano ambigue perche' venivano da un
    altro contesto, dove si giudicava l'ORDINE e non la REGOLA.

    Ora il campo si chiama `obiezione` e vale REGGE o CADE: parole che
    descrivono la cosa di cui parlano e non si possono capovolgere.
    """

    def test_le_due_parole_dicono_di_cosa_parlano(self):
        from core.giudizio_claude import SCHEMA_OBIEZIONE
        assert SCHEMA_OBIEZIONE["properties"]["obiezione"]["enum"] == ["REGGE", "CADE"]
        assert "obiezione" in SCHEMA_OBIEZIONE["required"]
        assert "verdetto" not in SCHEMA_OBIEZIONE["properties"]

    def test_solo_cade_apre(self, monkeypatch):
        """REGGE, una parola imprevista o un guasto: non si apre."""
        from core import giudizio_claude as g

        for risposta, apre in (("CADE", True), ("REGGE", False),
                               ("ACCETTA", False), ("", False), (None, False)):
            monkeypatch.setattr(g, "giudica",
                                lambda *a, **k: g.Verdetto(
                                    accetta=(k.get("valore_affermativo") == risposta),
                                    motivo="", fiducia="alta", modello="finto"))
            v = g.giudica_obiezione({"x": 1}, "RISK-05", "y")
            assert v.accetta is apre, f"{risposta!r} non deve dare {v.accetta}"

    def test_le_istruzioni_chiedono_le_parole_giuste(self):
        from core.giudizio_claude import ISTRUZIONI_OBIEZIONE
        assert "REGGE" in ISTRUZIONI_OBIEZIONE
        assert "CADE" in ISTRUZIONI_OBIEZIONE
        assert "In dubbio, REGGE" in ISTRUZIONI_OBIEZIONE


class TestIlRitmo:
    """Il tetto dice QUANTO, il ritmo dice QUANDO.

    Misurato il 2026-09-21 col bot vivo: sei chiamate in due minuti e mezzo,
    perche' su `M1min` e `M5` ogni chiusura di candela porta un CRT nuovo su
    sei strumenti. Il tetto di 0,27 EUR si sarebbe esaurito in cinque minuti
    e le dodici ore successive sarebbero state senza giudizio -- cioe' col
    comportamento di prima, senza che nulla lo segnalasse.
    """

    def test_il_passo_e_un_ventiquattresimo_del_tetto(self, monkeypatch):
        _prezzi(monkeypatch, tetto=0.24)
        ok, dettaglio = budget.c_e_budget()
        assert ok is True
        assert "0.0100" in dettaglio, dettaglio

    def test_speso_troppo_in_un_ora_ferma(self, monkeypatch):
        _prezzi(monkeypatch, tetto=0.24)
        # ~0,040 EUR a chiamata: la prima sfonda gia' il passo orario
        budget.registra(200, 0, 3000, 1500)
        ok, dettaglio = budget.c_e_budget()
        assert ok is False
        assert "ritmo" in dettaglio

    def test_il_tetto_giornaliero_resta_sovrano(self, monkeypatch):
        """Superato quello, il ritmo non conta piu': si e' finito e basta."""
        _prezzi(monkeypatch, tetto=0.02)
        budget.registra(200, 0, 3000, 1500)
        ok, dettaglio = budget.c_e_budget()
        assert ok is False
        assert "tetto giornaliero raggiunto" in dettaglio

    def test_le_chiamate_vecchie_non_pesano_piu(self, monkeypatch):
        """La finestra e' l'ULTIMA ora, non tutta la giornata."""
        from datetime import datetime, timedelta, timezone
        _prezzi(monkeypatch, tetto=0.24)
        budget.registra(200, 0, 3000, 1500)
        assert budget.c_e_budget()[0] is False
        vecchio = (datetime.now(timezone.utc) - timedelta(hours=2)
                   ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with storage.connessione(scrittura=True) as conn:
            conn.execute("UPDATE giudizio_chiamata SET quando_utc = ?", (vecchio,))
        assert budget.speso_nell_ultima_ora() == 0.0
        assert budget.c_e_budget()[0] is True

    def test_senza_tetto_non_c_e_nemmeno_ritmo(self, monkeypatch):
        _prezzi(monkeypatch, tetto=0.0)
        budget.registra(200, 0, 3000, 1500)
        assert budget.c_e_budget()[0] is True
