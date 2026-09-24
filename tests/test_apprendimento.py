"""Il cancello fra cio' che si e' imparato e cio' che opera.

La proprieta' che questo file difende e' una sola, e vale piu' di tutte le
altre: **un modello assente, scaduto o bocciato fa comportare il bot come si
comporta oggi.** Non in modo strano, non in modo prudente-ma-diverso: come
oggi.

E' cio' che rende sicuro accendere l'apprendimento un agente per volta. Senza,
ogni agente che impara e' un agente che puo' rompersi in un modo nuovo.
"""

from __future__ import annotations

import json

import pytest

from core import apprendimento as app
from core.apprendimento import Appreso, Competenza, valore_da_usare

PROVA = Competenza(
    agente="sentinella.pareggio",
    domanda="a che punto del cammino conviene spostare lo stop a pareggio",
    bersaglio="R medio dell'operazione",
    fonte="i 16.463 cammini del campo di prova",
    predefinito=1.0,
    campioni_minimi=300,
    guadagno_minimo=0.05,
)


def appreso(valore=1.6, campioni=900, guadagno=0.08,
            intervallo=(0.02, 0.14), stabilita=0.9) -> Appreso:
    return Appreso(competenza=PROVA.agente, valore=valore, campioni=campioni,
                   guadagno=guadagno, intervallo=intervallo,
                   stabilita=stabilita)


class TestIlPredefinitoELaRegolaDiOggi:

    def test_senza_modello_si_usa_il_predefinito(self):
        valore, perche = valore_da_usare(PROVA, None)
        assert valore == PROVA.predefinito
        assert "nessun modello" in perche

    def test_un_candidato_bocciato_non_entra_mai(self):
        """Se un agente leggesse `Appreso.valore` da solo, un bocciato
        finirebbe in produzione per distrazione e nessuno se ne accorgerebbe
        finche' i soldi non sono gia' andati."""
        valore, perche = valore_da_usare(PROVA, appreso(campioni=10))
        assert valore == PROVA.predefinito
        assert "bocciato" in perche

    def test_un_candidato_promosso_entra(self):
        valore, perche = valore_da_usare(PROVA, appreso(valore=1.6))
        assert valore == pytest.approx(1.6)
        assert "appreso su 900 casi" in perche

    def test_la_provenienza_torna_sempre(self):
        """Una decisione presa con un numero appreso e una presa col
        predefinito devono restare distinguibili a mesi di distanza."""
        for candidato in (None, appreso(), appreso(campioni=1)):
            _, perche = valore_da_usare(PROVA, candidato)
            assert perche


class TestIlCancello:

    def test_servono_TUTTI_i_criteri(self):
        """`and` e non "la maggioranza": ogni criterio copre un modo diverso
        di sbagliarsi, e passarne tre su quattro significa essere esposti al
        quarto."""
        assert appreso().promosso(PROVA)
        assert not appreso(campioni=299).promosso(PROVA)
        assert not appreso(guadagno=0.04).promosso(PROVA)
        assert not appreso(intervallo=(-0.01, 0.20)).promosso(PROVA)
        assert not appreso(stabilita=0.79).promosso(PROVA)

    def test_l_intervallo_deve_escludere_lo_zero(self):
        assert appreso(intervallo=(0.01, 0.2)).esclude_lo_zero()
        assert appreso(intervallo=(-0.2, -0.01)).esclude_lo_zero()
        assert not appreso(intervallo=(-0.01, 0.2)).esclude_lo_zero()

    def test_dice_QUALE_criterio_lo_ferma(self):
        """Un candidato bocciato senza motivo scritto diventa, dopo una
        settimana, un candidato che "non ha funzionato"."""
        motivi = appreso(campioni=5, stabilita=0.3).perche_no(PROVA)
        assert len(motivi) == 2
        assert any("fuori campione" in m for m in motivi)
        assert any("stabilita" in m for m in motivi)

    def test_un_promosso_non_ha_motivi(self):
        assert appreso().perche_no(PROVA) == []


class TestLaCompetenza:

    def test_un_cancello_a_zero_non_e_un_cancello(self):
        with pytest.raises(ValueError):
            Competenza(agente="x", domanda="", bersaglio="", fonte="",
                       predefinito=0.0, campioni_minimi=10,
                       guadagno_minimo=0.0)

    def test_serve_almeno_un_campione(self):
        with pytest.raises(ValueError):
            Competenza(agente="x", domanda="", bersaglio="", fonte="",
                       predefinito=0.0, campioni_minimi=0,
                       guadagno_minimo=0.1)


class TestIlRegistro:

    def test_due_agenti_non_possono_imparare_la_stessa_cosa(self, monkeypatch):
        """Due copie della stessa competenza divergono nel punto che muove i
        soldi. E' la famiglia di difetti piu' costosa di questo progetto."""
        monkeypatch.setattr(app, "REGISTRO", {})
        app.dichiara(PROVA)
        with pytest.raises(ValueError):
            app.dichiara(PROVA)

    def test_il_riepilogo_dice_cosa_sa_il_bot(self, monkeypatch):
        monkeypatch.setattr(app, "REGISTRO", {})
        app.dichiara(PROVA)
        testo = app.riepilogo({PROVA.agente: appreso(valore=1.6)})
        assert "sentinella.pareggio" in testo
        assert "1.6" in testo
        assert "appreso" in testo

    def test_il_riepilogo_dice_anche_quando_usa_il_predefinito(self, monkeypatch):
        monkeypatch.setattr(app, "REGISTRO", {})
        app.dichiara(PROVA)
        testo = app.riepilogo({})
        assert "predefinito" in testo


class TestIlFile:

    def test_andata_e_ritorno(self, tmp_path):
        percorso = tmp_path / "appresi.json"
        app.salva({PROVA.agente: appreso(valore=1.6)}, percorso)
        tornati = app.carica(percorso)
        assert tornati[PROVA.agente].valore == pytest.approx(1.6)
        assert tornati[PROVA.agente].intervallo == (0.02, 0.14)

    def test_un_file_assente_non_ferma_niente(self, tmp_path):
        assert app.carica(tmp_path / "manca.json") == {}

    def test_un_file_rotto_non_ferma_niente(self, tmp_path):
        """Un errore di lettura non deve poter cambiare come si opera: torna
        vuoto, e ogni agente usa la regola di oggi."""
        percorso = tmp_path / "rotto.json"
        percorso.write_text("{ questo non e' json", encoding="utf-8")
        assert app.carica(percorso) == {}

    def test_una_voce_storta_non_invalida_le_altre(self, tmp_path):
        percorso = tmp_path / "misto.json"
        percorso.write_text(json.dumps({"appresi": {
            "buono": {"valore": 1.5, "campioni": 400, "guadagno": 0.1,
                      "intervallo": [0.01, 0.2], "stabilita": 0.9},
            "storto": {"valore": "non un numero"},
        }}), encoding="utf-8")
        tornati = app.carica(percorso)
        assert "buono" in tornati
        assert "storto" not in tornati
