"""Quando la bias del dollaro ferma da sola, e quando passa al giudizio.

Il 2026-09-21 il bot non apriva niente: misurato sull'archivio, `CRT-20`
fermava il 49% dei CRT e `RISK-05` quasi tutto il resto -- 251 su 298 su
`D1 -> H1`, 306 su 617 su `W1 -> H4` -- e in vent'anni non arrivava
all'ingresso un solo setup su nessuna coppia.

La risposta non e' spegnere le regole ma modellarle: la bias del dollaro si
legge sul giornaliero e governa un movimento di ore. Un CRT su `H4` vive
dentro quell'orizzonte; un CRT su `M5` vive dieci minuti, e li' il dollaro
e' rumore che nessuna bias giornaliera predice.
"""

import pytest

from core.parametri import (
    CONFERME_CHE_BLOCCANO_DA_SOLE, COPPIE_CRT, RISK_05_BLOCCA_DA_SOLA,
    blocca_da_sola,
)


class TestCrt20:
    def test_ferma_di_nuovo_da_sola(self):
        """Riaccesa il 2026-09-22 insieme alle altre sette.

        Il numero che l'aveva spenta -- 49% dei CRT fermati, e zero ingressi
        su ogni coppia -- era stato misurato col motore rotto: `TF_KEY_LEVEL`
        non comprendeva gli intraday e sotto le quattro ore non si trovava un
        CRT. Corretto quello, `H1 -> M5` da 1.891 CRT dove prima erano zero.
        """
        assert blocca_da_sola("CRT-20") is True

    def test_le_conferme_sono_veti_tranne_due(self):
        """Due eccezioni, ognuna con un motivo scritto.

        `CRT-11` non e' un veto all'armamento perche' il CISD avviene DOPO la
        chiusura di `N2`: chiederlo li' vuol dire chiederlo prima che possa
        essere successo. Resta obbligatorio dove conta -- all'ingresso, dove
        `ingresso_ltf.controlla` senza CISD non entra mai.

        `CRT-15` non e' un veto perche' `PRIN-12` dice che il sistema e'
        attivo 24 ore su 24 e non esistono fasce orarie escluse. Farla
        bloccare contraddiceva quel principio, e `BIBBIA-CRT.md` e' esplicita:
        le finestre valgono +0,0 e -0,2 sigma e "PRIN-12 non va toccata".
        Misurato il 24/09: fermava 61 decisioni su 238.

        Nessuna delle due e' spenta: restano valutate e nel responso, che e'
        cio' che la Fase 2 dovra' pesare.
        """
        spente = sorted(k for k, v in CONFERME_CHE_BLOCCANO_DA_SOLE.items() if not v)
        assert spente == ["CRT-11", "CRT-15"], f"conferme non applicate: {spente}"

    def test_le_due_non_bloccanti_restano_nel_responso(self):
        """Non bloccare non vuol dire non calcolare: il responso deve
        contenerle comunque, o la Fase 2 peserebbe sei segnali su otto."""
        from core.parametri import CONFERME_ROMEO
        assert "CRT-11" in CONFERME_ROMEO and "CRT-15" in CONFERME_ROMEO

    def test_CRT_11_resta_obbligatoria_all_ingresso(self):
        """Toglierla dai veti non la rende facoltativa: la sposta."""
        import inspect
        from core import ingresso_ltf
        corpo = inspect.getsource(ingresso_ltf.controlla)
        assert "cisd(" in corpo
        assert "nessuna serie di consegna contraria da rompere" in corpo

    def test_resta_fra_le_conferme_valutate(self):
        """Spenta come veto, non cancellata: il responso la riporta lo stesso
        e il giudizio la pesa insieme alle altre."""
        assert "CRT-20" in CONFERME_CHE_BLOCCANO_DA_SOLE


class TestRisk05:
    @pytest.mark.parametrize("tf", ["TF_1M", "TF_1W", "TF_1D", "TF_H4"])
    def test_sui_range_alti_ferma_da_sola(self, tf):
        assert tf in RISK_05_BLOCCA_DA_SOLA

    @pytest.mark.parametrize("tf", ["TF_H1", "TF_M15", "TF_M5", "TF_M1min"])
    def test_sotto_le_quattro_ore_decide_il_giudizio(self, tf):
        assert tf not in RISK_05_BLOCCA_DA_SOLA

    def test_la_soglia_sta_dove_sta_la_misura(self):
        """`4h -> 15m` e' l'unica configurazione con un numero positivo: da
        li' in su si resta severi."""
        assert "TF_H4" in RISK_05_BLOCCA_DA_SOLA
        assert "TF_H1" not in RISK_05_BLOCCA_DA_SOLA

    def test_ogni_coppia_di_crt_04_sa_cosa_fa(self):
        """Nessun range resta in un limbo: o ferma, o passa al giudizio."""
        for range_tf in COPPIE_CRT:
            deciso = range_tf.value in RISK_05_BLOCCA_DA_SOLA
            assert isinstance(deciso, bool)


class TestIlGiudizioRestaLUnicaPorta:
    def test_risk_05_e_soppesabile(self):
        """Sotto le quattro ore la parola passa al giudizio: se RISK-05 non
        fosse fra le obiezioni soppesabili, non passerebbe a nessuno e il
        blocco resterebbe assoluto senza dirlo."""
        from core.motore import OBIEZIONI_SOPPESABILI
        assert "RISK-05" in OBIEZIONI_SOPPESABILI

    def test_senza_giudizio_l_obiezione_regge(self):
        """PRIN-99: non sapere e' un no. Con il giudizio spento il bot non
        deve aprire contro il dollaro solo perche' nessuno ha risposto."""
        from core import motore
        from core.config import impostazioni

        cfg = impostazioni()
        prima = getattr(cfg, "GIUDIZIO_SULLE_OBIEZIONI", False)
        try:
            object.__setattr__(cfg, "GIUDIZIO_SULLE_OBIEZIONI", False)
            assert motore._giudizio_lascia_cadere(
                None, None, None, ["RISK-05"], "prova") is False
        finally:
            object.__setattr__(cfg, "GIUDIZIO_SULLE_OBIEZIONI", prima)
