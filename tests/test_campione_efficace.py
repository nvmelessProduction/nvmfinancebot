"""Due CRT che vivono lo stesso movimento sono una prova, non due.

Contarli come due gonfia il campione, e un campione gonfiato **restringe**
l'intervallo di confidenza: si dichiara significativo un risultato che non lo
e'. E' il modo piu' comune di prendersi in giro con un backtest, e il
protocollo lo affronta con due cose che qui si provano insieme -- il campione
efficace e il blocco da ricampionare.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from campione_efficace import blocchi, durata_esecuzione        # noqa: E402

from core.mercato_duka import DURATA                            # noqa: E402
from core.parametri import TF                                   # noqa: E402


def riga(strumento, quando, barre, coppia="TF_1W->TF_H4") -> dict:
    return {"strumento": strumento, "coppia": coppia,
            "quando": quando, "barre": str(barre)}


class TestLaDurataVieneDallaStessaTabellaDelBot:

    def test_legge_il_timeframe_di_esecuzione(self):
        assert durata_esecuzione("TF_1W->TF_H4") == timedelta(hours=4)
        assert durata_esecuzione("TF_1D->TF_H1") == timedelta(hours=1)

    def test_non_e_una_seconda_tabella(self):
        """Se `DURATA` cambiasse, qui cambierebbe da solo."""
        assert durata_esecuzione("TF_1D->TF_H1") == DURATA[TF.H1]


class TestIBlocchi:

    def test_due_finestre_sovrapposte_sono_un_blocco(self):
        """Il secondo CRT parte dopo quattro ore, il primo dura ventiquattro:
        vivono lo stesso movimento."""
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 6),
                 riga("EURUSD", "2020-01-06T04:00:00+00:00", 6)]
        assert len(set(blocchi(righe))) == 1

    def test_due_finestre_lontane_sono_due_blocchi(self):
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 2),
                 riga("EURUSD", "2020-01-09T00:00:00+00:00", 2)]
        assert len(set(blocchi(righe))) == 2

    def test_due_cambi_contro_dollaro_nella_stessa_ora_sono_UNA_prova(self):
        """Il test che c'era prima diceva il contrario -- "lo stesso istante
        su due strumenti resta due prove" -- ed era sbagliato.

        `EURUSD` e `GBPUSD` salgono e scendono insieme: un CRT long sulla
        stessa ora e' una scommessa sul dollaro fatta due volte. Contarle come
        due prove e' lo stesso errore che il bootstrap a blocchi esiste per
        evitare, commesso lungo l'altro asse -- e gonfiava il campione
        efficace dichiarato (90,2% delle righe)."""
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 6),
                 riga("GBPUSD", "2020-01-06T00:00:00+00:00", 6)]
        assert len(set(blocchi(righe))) == 1

    def test_gruppi_diversi_restano_due_prove(self):
        """L'oro non e' un cambio contro dollaro: quella e' un'altra
        scommessa, e va contata."""
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 6),
                 riga("XAUUSD", "2020-01-06T00:00:00+00:00", 6)]
        assert len(set(blocchi(righe))) == 2

    def test_il_gruppo_si_legge_dal_bot(self):
        """`GRUPPI_CORRELAZIONE` e' la stessa tabella con cui RISK-02 decide
        quante posizioni correlate tollerare. Una seconda copia qui
        divergerebbe proprio dove si dichiara cosa si muove insieme."""
        from core.parametri import GRUPPI_CORRELAZIONE
        from campione_efficace import gruppo_di
        for nome, membri in GRUPPI_CORRELAZIONE.items():
            for strumento in membri:
                assert gruppo_di(strumento) == nome

    def test_uno_strumento_ignoto_fa_gruppo_per_se(self):
        """Accorpare a caso restringerebbe il campione efficace per un motivo
        inventato: prudente, ma falso."""
        from campione_efficace import gruppo_di
        assert gruppo_di("MAIVISTO").startswith("solo:")

    def test_la_catena_e_un_blocco_solo(self):
        """A tocca B e B tocca C: A e C condividono comunque il movimento che
        li attraversa. Spezzare la catena rimetterebbe dentro la dipendenza
        che si sta togliendo."""
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 2),
                 riga("EURUSD", "2020-01-06T04:00:00+00:00", 2),
                 riga("EURUSD", "2020-01-06T08:00:00+00:00", 2)]
        assert len(set(blocchi(righe))) == 1

    def test_l_etichetta_torna_nell_ordine_di_arrivo(self):
        """Le righe non si riordinano: il blocco e' una colonna in piu',
        allineata alla riga a cui appartiene."""
        righe = [riga("EURUSD", "2020-01-20T00:00:00+00:00", 1),
                 riga("EURUSD", "2020-01-06T00:00:00+00:00", 1),
                 riga("XAUUSD", "2020-01-06T00:00:00+00:00", 1)]
        etichette = blocchi(righe)
        assert len(etichette) == 3
        assert etichette[0].startswith("forex_dxy")
        assert etichette[2].startswith("oro")
        # Due settimane di distanza: blocchi diversi, nell'ordine d'arrivo.
        assert etichette[0] != etichette[1]

    def test_nessuna_riga_resta_senza_blocco(self):
        righe = [riga("XAUUSD", "2020-01-06T00:00:00+00:00", 0)]
        assert "?" not in blocchi(righe)

    def test_non_butta_via_nessuna_riga(self):
        """Le righe servono tutte a stimare i pesi. Il blocco dice solo di
        quante prove distinte si dispone per dichiarare una confidenza."""
        righe = [riga("EURUSD", "2020-01-06T00:00:00+00:00", 6)] * 5
        assert len(blocchi(righe)) == 5
