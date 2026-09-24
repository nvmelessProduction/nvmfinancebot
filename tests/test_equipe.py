"""Il verbale dell'equipe: che si capisca senza sapere cosa sia un CISD.

Per venti giorni la domanda e' stata "perche' il bot ha aperto quella?", e la
risposta stava in un archivio che leggeva una persona sola. Un sistema che
decide e non sa raccontare perche' non e' controllabile, e uno che nessuno
controlla non merita di operare.
"""

from __future__ import annotations

import pytest

from core import equipe as eq
from core.apprendimento import Appreso, Competenza

RESPONSO = {"CRT-06": True, "CRT-10": None, "CRT-11": False, "CRT-12": True,
            "CRT-15": None, "CRT-17": False, "CRT-18": None, "CRT-20": True}


class TestLeConferme:

    def test_ci_sono_tutte_anche_quelle_mute(self):
        """Un ordine partito con tre pareri favorevoli e uno partito con
        sette sono due fatti molto diversi, e finche' il messaggio diceva
        solo "aperto" erano indistinguibili."""
        righe = eq.righe_conferme(RESPONSO)
        assert len(righe) == 2 + len(RESPONSO)

    def test_il_conteggio_e_in_testa(self):
        righe = eq.righe_conferme(RESPONSO)
        assert "3 a favore" in righe[1]
        assert "2 contro" in righe[1]
        assert "3 non lo so" in righe[1]

    def test_non_lo_so_non_diventa_no(self):
        """E' la stessa distinzione che regge tutta la codifica: se sparisce
        qui, sparisce nella testa di chi legge."""
        righe = eq.righe_conferme({"CRT-10": None})
        assert "non ha potuto dirlo" in "\n".join(righe)
        assert "❌" not in "\n".join(righe)

    def test_parla_italiano_non_sigle(self):
        """Chi legge sul telefono non deve sapere cosa sia un CISD."""
        testo = "\n".join(eq.righe_conferme({"CRT-11": True}))
        assert "la spinta ha cambiato verso" in testo

    def test_la_tabella_e_quella_del_notifier(self):
        """Ricopiarla significherebbe descrivere la stessa conferma in due
        modi diversi, e scoprirlo il giorno in cui le due si contraddicono."""
        from core.notifier import _IN_PAROLE
        assert eq._IN_PAROLE is _IN_PAROLE

    def test_senza_responso_lo_dice(self):
        assert "nessun parere" in "\n".join(eq.righe_conferme({}))


class TestIlModello:

    def test_mostra_l_aritmetica_non_solo_il_verdetto(self):
        """"Il modello dice di no" e' un oracolo, e da un oracolo non ci si
        difende. Chi legge deve poter rifare il conto a mano."""
        testo = "\n".join(eq.righe_modello(0.40, 2.50, 0.05, None))
        assert "0.40" in testo and "2.50" in testo
        assert "0.60" in testo, "manca (1 - p)"
        assert "0.05" in testo, "mancano i costi"

    def test_il_verdetto_segue_il_conto(self):
        buono = "\n".join(eq.righe_modello(0.40, 2.50, 0.05, None))
        cattivo = "\n".join(eq.righe_modello(0.40, 0.50, 0.05, None))
        assert "conviene" in buono and "non conviene" not in buono
        assert "non conviene" in cattivo

    def test_senza_pesi_lo_dice_e_non_inventa(self):
        testo = "\n".join(eq.righe_modello(None, None, None, None))
        assert "nessun peso stimato" in testo
        assert "decidono le regole" in testo


class TestILivelli:

    def test_il_rapporto_si_calcola_dai_livelli(self):
        testo = "\n".join(eq.righe_livelli(100.0, 98.0, 104.0, 110.0))
        assert "rapporto" in testo and "5.0" in testo

    def test_senza_livelli_lo_dice(self):
        assert "non calcolati" in "\n".join(eq.righe_livelli(None, None, None, None))

    def test_un_rischio_nullo_non_fa_dividere_per_zero(self):
        testo = "\n".join(eq.righe_livelli(100.0, 100.0, 104.0, 110.0))
        assert "rapporto" not in testo


class TestLaCarriera:

    def _competenza(self):
        return Competenza(
            agente="sentinella.pareggio", domanda="dove mettere lo stop",
            bersaglio="R", fonte="cammini", predefinito=0.0,
            campioni_minimi=300, guadagno_minimo=0.05)

    def test_dice_con_che_numero_sta_lavorando(self):
        """Senza questa riga, un bot che applica il manuale e uno che ha
        imparato qualcosa sono indistinguibili da fuori -- che e' lo stato in
        cui il progetto ha passato venti giorni."""
        registro = {"sentinella.pareggio": self._competenza()}
        righe = eq.righe_carriera({}, registro)
        assert any("sentinella.pareggio" in r for r in righe)
        assert any("predefinito" in r for r in righe)

    def test_distingue_un_promosso(self):
        registro = {"sentinella.pareggio": self._competenza()}
        promosso = Appreso(competenza="sentinella.pareggio", valore=0.75,
                           campioni=900, guadagno=0.08,
                           intervallo=(0.02, 0.14), stabilita=0.9)
        righe = eq.righe_carriera({"sentinella.pareggio": promosso}, registro)
        testo = "\n".join(righe)
        assert "0.75" in testo
        assert "appreso" in testo

    def test_senza_registro_non_dice_niente(self):
        assert eq.righe_carriera({}, {}) == []


class TestIlVerbale:

    def test_mette_tutti_gli_agenti(self):
        testo = eq.verbale(
            titolo="prova", responso=RESPONSO, ingresso=100.0, stop=98.0,
            target=110.0, probabilita=0.4, rapporto=5.0, costo_in_erre=0.05,
            volume=0.1, conclusione="aperta")
        for atteso in ("ricerca", "conferme", "livelli", "modello", "rischio"):
            assert atteso in testo
        assert "aperta" in testo

    def test_regge_un_verbale_tutto_vuoto(self):
        """Una decisione di astensione ha pochi dati, e il verbale deve
        uscire lo stesso: e' proprio quello il caso in cui serve capire."""
        testo = eq.verbale(titolo="niente")
        assert "niente" in testo
        assert "nessun CRT nella forma" in testo


class TestIlCanaleSeparato:

    def test_l_equipe_ha_una_chat_sua(self):
        from core.config import Impostazioni
        assert hasattr(Impostazioni, "model_fields")
        assert "TELEGRAM_CHAT_EQUIPE" in Impostazioni.model_fields

    def test_senza_configurazione_non_ripiega_sull_operativo(self, monkeypatch):
        """Un ripiego silenzioso riempirebbe di verbali da venti righe
        proprio il canale che si voleva tenere pulito."""
        from core.config import Impostazioni
        cfg = Impostazioni(TELEGRAM_TOKEN="x", TELEGRAM_CHAT_ID="123",
                           TELEGRAM_CHAT_EQUIPE="")
        assert cfg.telegram_configurato
        assert not cfg.equipe_configurata
        assert cfg.destinatari_equipe() == ()

    def test_accetta_piu_di_una_chat(self):
        from core.config import Impostazioni
        cfg = Impostazioni(TELEGRAM_TOKEN="x", TELEGRAM_CHAT_EQUIPE="1, 2;3")
        assert cfg.destinatari_equipe() == ("1", "2", "3")
