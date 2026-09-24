"""La memoria da cui si impara. Fase 0 del piano.

Il motore calcolava gia' per ogni CRT il verdetto di tutte e otto le conferme
di Romeo -- `responso_romeo` -- lo mandava su Telegram e lo buttava via. In
archivio non esisteva **un solo esempio** che collegasse "quali conferme
c'erano" a "com'e' finita", quindi non c'era niente da cui imparare quanto
ciascuna pesi davvero. Non mancava l'intelligenza: mancava il dato.

Stessa cosa per lo spread. L'unico registrato era `posizione.spread_ingresso`,
cioe' misurato SOLO negli istanti in cui il bot aveva deciso di operare --
plausibilmente i piu' stretti. Un percentile calcolato li' descrive il momento
dell'apertura, non l'ora del giorno, e moltiplicarlo per un fattore di
sicurezza non raddrizza una distorsione: la scala soltanto.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from core.models import AlertIn, Decision


@pytest.fixture
def archivio(monkeypatch):
    """Un archivio vero, in un file temporaneo."""
    percorso = os.path.join(tempfile.mkdtemp(), "prova.db")
    monkeypatch.setenv("DB_PATH", percorso)
    from core.config import impostazioni
    if hasattr(impostazioni, "cache_clear"):
        impostazioni.cache_clear()
    from core import storage
    storage.inizializza()
    yield storage, percorso
    if hasattr(impostazioni, "cache_clear"):
        impostazioni.cache_clear()


def _alert(storage):
    a = AlertIn(simbolo="6E1!", tf="TF_M5", chiusura=1.1, apertura=1.1,
                massimo=1.1, minimo=1.1,
                chiusura_candela_utc="2026-09-23T17:30:00Z", secret="x")
    id_alert, _ = storage.salva_alert(a)
    return id_alert


def _righe(percorso, sql):
    conn = sqlite3.connect(percorso)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestIlRespondoDelleConfermeSiConserva:

    def test_viene_scritto_e_rileggibile(self, archivio):
        storage, percorso = archivio
        storage.salva_decisione(
            _alert(storage),
            Decision(azione="BUY", simbolo="EURUSD", tf_crt="TF_H1",
                     responso_romeo={"CRT-20": True, "CRT-12": None,
                                     "CRT-06": False}),
            "eseguito")
        (testo, tf), = _righe(
            percorso, "SELECT responso_romeo, tf_crt FROM decisione")
        assert json.loads(testo) == {"CRT-20": True, "CRT-12": None,
                                     "CRT-06": False}
        assert tf == "TF_H1"

    def test_non_calcolato_e_diverso_da_non_si_sapeva(self, archivio):
        """Due cose opposte, per chi dovra' imparare da questi dati.

        `NULL` = il responso non e' stato calcolato (l'astensione e' arrivata
        prima delle conferme). Un responso di soli `None` = e' stato calcolato
        e non si sapeva. Confonderle insegnerebbe il falso.
        """
        storage, percorso = archivio
        id_alert = _alert(storage)
        storage.salva_decisione(id_alert, Decision(azione="NONE"), "nessuna_azione")
        storage.salva_decisione(
            id_alert,
            Decision(azione="NONE", responso_romeo={"CRT-20": None}),
            "nessuna_azione")
        righe = _righe(percorso, "SELECT responso_romeo FROM decisione ORDER BY id")
        assert righe[0][0] is None, "non calcolato deve restare NULL"
        assert json.loads(righe[1][0]) == {"CRT-20": None}

    def test_si_scrive_anche_per_le_astensioni(self, archivio):
        """Sapere quali conferme c'erano quando NON si e' operato vale quanto
        saperlo quando si e' operato: un modello addestrato sui soli ingressi
        impara da meta' del mondo."""
        storage, percorso = archivio
        storage.salva_decisione(
            _alert(storage),
            Decision(azione="NONE", responso_romeo={"CRT-06": False}),
            "nessuna_azione")
        (testo,), = _righe(percorso, "SELECT responso_romeo FROM decisione")
        assert json.loads(testo) == {"CRT-06": False}

    def test_le_chiavi_sono_ordinate(self, archivio):
        """Due decisioni identiche danno la stessa stringa, quindi si possono
        confrontare senza rileggerle come JSON."""
        storage, percorso = archivio
        id_alert = _alert(storage)
        for responso in ({"B": True, "A": False}, {"A": False, "B": True}):
            storage.salva_decisione(
                id_alert, Decision(azione="NONE", responso_romeo=responso),
                "nessuna_azione")
        (uno,), (due,) = _righe(
            percorso, "SELECT responso_romeo FROM decisione ORDER BY id")
        assert uno == due

    def test_un_responso_non_serializzabile_non_fa_cadere_la_decisione(self, archivio):
        """La decisione va salvata comunque: e' il dato principale.

        Il modello `Decision` valida gia' i tipi, quindi questo caso non puo'
        arrivare da li' — ed e' una garanzia piu' forte della difesa. La rete
        resta per chi costruisse il responso per altre vie.
        """
        storage, _ = archivio
        assert storage._responso_in_json({"CRT-06": {1, 2}}) is None
        assert storage._responso_in_json(None) is None
        assert storage._responso_in_json({}) is None


class TestLoSpreadSiCampionaARitmoRegolare:

    def test_registra_le_misure_buone(self, archivio):
        storage, percorso = archivio
        quante = storage.campiona_spread(
            [("EURUSD+", 1.1389, 1.1390), ("XAUUSD+", 4290.72, 4290.84)])
        assert quante == 2
        righe = _righe(percorso,
                       "SELECT simbolo, ROUND(spread, 6) FROM spread ORDER BY simbolo")
        assert righe == [("EURUSD+", 0.0001), ("XAUUSD+", 0.12)]

    def test_scarta_i_tick_incoerenti(self, archivio):
        """Un ask sotto il bid o un prezzo a zero non e' una misura: e' un
        guasto del feed, e archiviarlo sporcherebbe la stima dei costi."""
        storage, percorso = archivio
        quante = storage.campiona_spread(
            [("A", 0.0, 1.0), ("B", 1.5, 1.4), ("C", 1.0, None)])
        assert quante == 0
        assert _righe(percorso, "SELECT COUNT(*) FROM spread") == [(0,)]

    def test_bid_uguale_ask_e_una_misura_valida(self, archivio):
        """Su conto RAW lo spread nullo e' normale, non un dato mancante: e'
        gia' costato mezza giornata scambiarlo per un guasto."""
        storage, percorso = archivio
        assert storage.campiona_spread([("EURUSD+", 1.1389, 1.1389)]) == 1

    def test_un_guasto_non_solleva(self, archivio, monkeypatch):
        """Il campionamento serve fra settimane: un suo guasto non deve far
        cadere il giro di mercato, che e' quello che fa operare il bot."""
        storage, _ = archivio

        def esplode(*a, **k):
            raise RuntimeError("archivio irraggiungibile")

        monkeypatch.setattr(storage, "connessione", esplode)
        assert storage.campiona_spread([("EURUSD+", 1.0, 1.1)]) == 0


class TestIlCampionamentoNonRallentaGliOrdini:

    def test_sta_in_fondo_al_giro(self):
        """Su M1min il tetto e' 15 secondi: il campionamento dello spread non
        puo' stare fra l'aggiornamento e la valutazione."""
        import inspect
        from core.mercato_mt5 import MercatoMT5
        corpo = inspect.getsource(MercatoMT5.giro)
        assert corpo.index("self._valuta(") < corpo.index("self._campiona_spread()"), (
            "il campionamento precede le valutazioni: ritarderebbe gli ordini")


class TestIlResponsoSopravviveAOgniAstensione:
    """Il buco della Fase 0, trovato in produzione il 24/09.

    Sette minuti dopo un riavvio: **66 decisioni, ZERO col responso**. Lo
    conservavano tre percorsi su nove -- l'ordine, l'astensione delle conferme
    stesse e l'armamento -- e tutti gli altri lo buttavano via: spread, bias
    DXY, filtri uniti, size, divieti permanenti, guardie sui livelli.

    Il piano della Fase 0 lo dice: *"Si scrive anche per le ASTENSIONI. Un
    modello addestrato sui soli ingressi impara da meta' del mondo"* -- e le
    astensioni sono la maggioranza. Il test che avevo scritto provava
    `storage.salva_decisione`, cioe' l'archivio, non il motore che lo riempie.
    """

    def test_l_aiutante_delle_astensioni_lo_porta(self):
        import inspect
        from core import motore
        corpo = inspect.getsource(motore.valuta)
        aiutante = corpo[corpo.index("def ferma(regole"):]
        aiutante = aiutante[:aiutante.index("# --- 4bis-ter")]
        assert "responso_romeo=responso_romeo" in aiutante, (
            "le astensioni dopo le conferme perdono di nuovo il responso")

    def test_tutte_le_uscite_del_motore_lo_portano(self):
        """Ogni `_non_operare` che sta DOPO le conferme deve passare da
        `ferma`, o tornare a perderlo di nuovo."""
        import inspect
        from core import motore
        for funzione in (motore.valuta, motore._decidi_sul_candidato):
            corpo = inspect.getsource(funzione)
            dopo = corpo[corpo.index("conferme = interroga_conferme")
                         if "conferme = interroga_conferme" in corpo else 0:]
            nude = dopo.count("return _non_operare(")
            portanti = dopo.count("responso_romeo=responso_romeo")
            assert nude <= portanti, (
                f"{funzione.__name__}: {nude} astensioni nude dopo le conferme, "
                f"solo {portanti} portano il responso")
