"""CRT-13 — l'ingresso di Romeo, nei suoi due tempi.

La differenza piu' grande misurata in tutto il progetto: entrando alla
chiusura della candela di range il winrate e' 30,8% e il risultato -0,0782 R;
entrando sul ritorno nell'FVG e' 62,4% e +0,3613 R.

Sono due momenti separati nel tempo, e fra loro passano minuti o ore. Questo
file collauda che lo stato sopravviva fra i due e che il secondo avvenga solo
quando tutti e tre i passi — CISD, FVG, ritorno — sono avvenuti davvero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import ingresso_ltf as ltf
from core import storage
from core.definizioni import Bias, Candela
from core.parametri import TF

O = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def archivio_pulito(tmp_path, monkeypatch):
    """Un archivio nuovo per ogni prova: lo stato armato vive su disco."""
    monkeypatch.setattr(storage, "PERCORSO", tmp_path / "prova.db", raising=False)
    from core import config
    monkeypatch.setenv("DB_PATH", str(tmp_path / "prova.db"))
    config.impostazioni.cache_clear()
    storage.inizializza()
    ltf.prepara_tabella()
    yield
    config.impostazioni.cache_clear()


def barra(ap: float, ma: float, mi: float, ch: float, i: int = 0) -> Candela:
    return Candela(O + timedelta(minutes=15 * i), ap, ma, mi, ch)


def arma_short() -> int:
    """Un CRT short: ha spazzato a 110, il range va da 100 a 110."""
    return ltf.arma(
        "EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
        estremo_sweep=110.0, eq_range=105.0, lato_opposto=100.0,
    )


def arma_short_operabile() -> int:
    """Come sopra, ma con livelli che superano GEST-01.

    `arma_short` ha uno stop a 110 e bersagli a 105/100: con l'ingresso a 102
    il rapporto vale 0,25, cioe' un setup che nessuno prenderebbe. Andava bene
    finche' `controlla` non guardava il rapporto -- serviva solo a provare la
    catena CISD/FVG/ritorno -- ma ora che GEST-01 si applica sul prezzo
    d'ingresso quei numeri fanno fallire la prova per il motivo giusto.

    Qui lo stop e' vicino e il bersaglio lontano, come in un setup vero.
    L'EQ resta SOPRA il prezzo d'ingresso perche' la prova che la usa
    verifica il ramo di CRT-16 in cui l'EQ e' gia' stato superato e il primo
    bersaglio diventa il lato opposto: con l'ingresso a 102 il rapporto sul
    lato opposto vale 1,75.
    """
    return ltf.arma(
        "EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
        estremo_sweep=106.0, eq_range=105.0, lato_opposto=95.0,
    )


class TestArmare:
    def test_un_crt_arma_e_non_ordina(self) -> None:
        id_setup = arma_short()
        assert id_setup > 0
        armati = ltf.armati("EURUSD")
        assert len(armati) == 1
        assert armati[0].direzione is Bias.SHORT
        assert armati[0].estremo_sweep == 110.0

    def test_un_crt_piu_recente_sostituisce_il_precedente(self) -> None:
        """Due CRT consecutivi nello stesso verso descrivono lo stesso
        movimento: armarli entrambi darebbe due ingressi sullo stesso setup."""
        arma_short()
        arma_short()
        assert len(ltf.armati("EURUSD")) == 1

    def test_versi_opposti_convivono(self) -> None:
        arma_short()
        ltf.arma("EURUSD", Bias.LONG, TF.H4, TF.MIN15, 95.0, 105.0, 110.0)
        assert len(ltf.armati("EURUSD")) == 2

    def test_lo_stato_sopravvive(self) -> None:
        """Un setup armato che sparisse al riavvio farebbe dimenticare al bot
        di essere in attesa proprio mentre il prezzo torna nel vuoto."""
        arma_short()
        assert len(ltf.armati("EURUSD")) == 1   # riletto dall'archivio


class TestLaCatenaDeiTrePassi:
    """CISD, poi FVG, poi ritorno. Nessuno dei tre si puo' saltare."""

    def test_senza_cisd_non_si_entra(self) -> None:
        setup = ltf.armati("EURUSD")[0] if ltf.armati("EURUSD") else None
        arma_short()
        setup = ltf.armati("EURUSD")[0]
        # Tutte ribassiste: nessuna serie CONTRARIA da rompere.
        salita = [barra(100 + i, 101 + i, 99 + i, 100.5 + i, i) for i in range(6)]
        ingresso, motivo = ltf.controlla(setup, salita)
        assert ingresso is None
        assert "consegna contraria" in motivo or "non ancora rotto" in motivo

    def test_il_livello_cisd_si_calcola_sulle_barre_precedenti(self) -> None:
        """Il bug che rendeva la regola quasi inerte: includendo la barra che
        ROMPE, la serie di consegna contraria risulta vuota — quella barra non
        e' contraria. Misurato: 16 CISD su 3622 sweep."""
        arma_short()
        setup = ltf.armati("EURUSD")[0]
        # Tre rialziste (consegna contraria a uno short), poi una che chiude
        # sotto l'apertura della prima: e' il CISD ribassista.
        serie = [
            # Ribassista: CHIUDE la serie contraria, cosi' il livello e'
            # l'apertura della barra 1 e non di questa.
            barra(101, 101.5, 99, 99.5, 0),
            barra(105, 106, 104, 105.5, 1),   # apre a 105: e' il livello
            barra(105.5, 106, 105, 105.8, 2),
            barra(105.8, 106, 105.5, 105.9, 3),
            barra(105.9, 106, 104, 104.5, 4),   # chiude SOTTO 105: CISD
        ]
        ingresso, motivo = ltf.controlla(setup, serie)
        # Il CISD e' avvenuto; manca ancora l'FVG.
        assert ingresso is None
        assert "CISD" not in motivo or "FVG" in motivo

    def test_la_sequenza_completa_produce_un_ingresso(self) -> None:
        arma_short_operabile()
        setup = ltf.armati("EURUSD")[0]

        # 1. CISD: tre rialziste poi una che chiude sotto l'apertura della prima
        serie = [
            barra(101, 101.5, 99, 99.5, 0),      # chiude la serie contraria
            barra(104, 105, 103.5, 104.8, 1),    # apre a 104: il livello
            barra(104.8, 105.2, 104.5, 105.0, 2),
            barra(105.0, 105.5, 104.8, 105.2, 3),
            barra(105.2, 105.4, 103.0, 103.2, 4),  # chiude sotto 104: CISD
        ]
        ltf.controlla(setup, serie)

        # 2. il movimento lascia un vuoto: la terza sta sotto la prima
        serie += [
            barra(103.2, 103.4, 102.8, 103.0, 5),
            barra(102.8, 102.9, 101.0, 101.2, 6),
            barra(101.2, 102.0, 100.8, 101.5, 7),   # massimo 102.0 < 102.8
        ]
        setup = ltf.armati("EURUSD")[0]
        ingresso, motivo = ltf.controlla(setup, serie)
        assert ingresso is None, "il vuoto e' appena nato, il ritorno non c'e'"
        assert "FVG" in motivo

        # 3. il prezzo torna dentro il vuoto
        setup = ltf.armati("EURUSD")[0]
        assert setup.fvg_inf is not None, "il vuoto e' stato annotato"
        serie += [barra(101.5, setup.fvg_sup, 101.0, 102.0, 8)]
        ingresso, motivo = ltf.controlla(setup, serie)

        assert ingresso is not None, motivo
        assert ingresso.direzione is Bias.SHORT
        assert ingresso.stop == 106.0, "lo stop e' l'estremo dello sweep"
        # CRT-16 dice "prima l'EQ, poi il lato opposto". Qui il prezzo e'
        # gia' sceso sotto l'EQ (105) prima dell'ingresso a 102: quel
        # bersaglio e' alle spalle, e il primo diventa il lato opposto. Un
        # bersaglio dietro il prezzo non e' un bersaglio.
        assert ingresso.bersaglio_1 == 95.0, "l'EQ e' gia' passato"
        assert ingresso.bersaglio_2 == 95.0, "il lato opposto del range"
        assert ingresso.prezzo < ingresso.stop, "su uno short si entra sotto lo stop"

    def test_l_eq_e_il_primo_bersaglio_quando_e_ancora_davanti(self) -> None:
        """L'altro ramo di CRT-16: se il prezzo non ha ancora raggiunto l'EQ,
        e' quello il primo bersaglio."""
        ltf.arma("EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
                 estremo_sweep=110.0, eq_range=95.0, lato_opposto=90.0)
        setup = ltf.armati("EURUSD")[-1]
        ltf._annota(setup.id_setup, livello_cisd=109.0, fvg_inf=107.0, fvg_sup=108.0)
        setup = ltf.armati("EURUSD")[-1]
        ingresso, motivo = ltf.controlla(setup, [barra(108.5, 108.5, 107.5, 108.0, 9)])
        assert ingresso is not None, motivo
        assert ingresso.bersaglio_1 == 95.0, "l'EQ e' ancora davanti"


class TestLaScadenza:
    def test_oltre_le_barre_massime_decade(self) -> None:
        """SETUP-04 — un CRT non eseguito decade. Un'attesa senza fine
        trasformerebbe il setup in un ordine in ritardo."""
        arma_short()
        for _ in range(ltf.ATTESA_MASSIMA_BARRE):
            ltf.avanza_attesa(ltf.armati("EURUSD")[0].id_setup)
        setup = ltf.armati("EURUSD")[0]
        ingresso, motivo = ltf.controlla(setup, [barra(100, 101, 99, 100, 0)])
        assert ingresso is None
        assert "SETUP-04" in motivo

    def test_un_setup_eseguito_non_si_ripresenta(self) -> None:
        id_setup = arma_short()
        ltf.chiudi(id_setup, "eseguito", "collaudo")
        assert ltf.armati("EURUSD") == []


class TestFvg:
    def test_il_vuoto_ribassista(self) -> None:
        b = [barra(100, 101, 99, 100, 0), barra(99, 99.5, 97, 97.5, 1),
             barra(97, 98, 96, 96.5, 2)]
        assert ltf.fvg(b, Bias.SHORT) == (98, 99)

    def test_nessun_vuoto_se_le_barre_si_toccano(self) -> None:
        b = [barra(100, 101, 99, 100, 0), barra(100, 100.5, 99.5, 99.8, 1),
             barra(99.8, 100.2, 99, 99.5, 2)]
        assert ltf.fvg(b, Bias.SHORT) is None

    def test_si_prende_l_ultimo_vuoto_non_il_primo(self) -> None:
        """E' quello piu' vicino al prezzo, quindi il primo che il ritorno
        incontrera'."""
        b = [barra(110, 111, 109, 110, 0), barra(108, 108.5, 106, 106.5, 1),
             barra(106, 107, 105, 105.5, 2), barra(105, 105.5, 103, 103.5, 3),
             barra(103, 104, 102, 102.5, 4)]
        vuoto = ltf.fvg(b, Bias.SHORT)
        assert vuoto is not None and vuoto[1] < 109, "l'ultimo, non il primo"


class TestNonRiarmareLoStessoCrt:
    """Il CRT identico non e' un CRT nuovo.

    Un CRT vive finche' vive la sua candela di range, e il motore lo ritrova
    uguale ad ogni valutazione. Ri-armarlo ogni volta mandava un messaggio
    Telegram ogni volta -- l'utente riceveva una fila di avvisi identici per
    un solo setup -- e azzerava `barre_attesa`, quindi SETUP-04 non lo faceva
    decadere mai.
    """

    def test_lo_stesso_crt_non_manda_due_messaggi(self, monkeypatch) -> None:
        mandati: list[str] = []
        monkeypatch.setattr(ltf.notifier, "invia_appena_possibile", mandati.append)
        for _ in range(5):
            arma_short()
        assert len(mandati) == 1
        assert len(ltf.armati("EURUSD")) == 1

    def test_lo_stesso_crt_restituisce_lo_stesso_setup(self) -> None:
        assert arma_short() == arma_short()

    def test_un_crt_davvero_nuovo_riarma_e_avvisa(self, monkeypatch) -> None:
        """Estremo spazzato diverso = un'altra candela di range."""
        mandati: list[str] = []
        monkeypatch.setattr(ltf.notifier, "invia_appena_possibile", mandati.append)
        arma_short()
        ltf.arma("EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
                 estremo_sweep=112.0, eq_range=106.0, lato_opposto=100.0)
        assert len(mandati) == 2
        assert len(ltf.armati("EURUSD")) == 1, "il precedente va sostituito"

    def test_le_barre_di_attesa_non_si_azzerano(self) -> None:
        """SETUP-04 deve poter far decadere il setup."""
        id_setup = arma_short()
        ltf.avanza_attesa(id_setup)
        ltf.avanza_attesa(id_setup)
        arma_short()
        assert ltf.armati("EURUSD")[0].barre_attesa == 2


class TestGest01SulPrezzoDiIngresso:
    """GEST-01 si verifica dove l'ordine parte, non dove il CRT si arma.

    Con CRT-13 fra i due momenti passano minuti o ore, e fra i due il prezzo
    torna INDIETRO verso lo sweep: si avvicina allo stop e si allontana dal
    bersaglio, quindi il rapporto vero e' molto migliore di quello stimato
    all'armamento. Misurato il 2026-09-21 su `D1 -> H1`, sei strumenti: alla
    chiusura di N2 il rapporto risultava incalcolabile nel 68% dei casi --
    il prezzo aveva gia' passato la meta' del range -- e GEST-01 fermava 292
    CRT su 298. Non per la soglia: perche' il numero non esisteva.
    """

    def _con_livelli(self, estremo, eq, opposto):
        ltf.arma("EURUSD", Bias.SHORT, TF.H4, TF.MIN15,
                 estremo_sweep=estremo, eq_range=eq, lato_opposto=opposto)
        setup = ltf.armati("EURUSD")[-1]
        ltf._annota(setup.id_setup, livello_cisd=109.0, fvg_inf=107.0, fvg_sup=108.0)
        return ltf.armati("EURUSD")[-1]

    def test_un_rapporto_basso_ferma_l_ingresso(self) -> None:
        # ingresso a 107, stop a 110 -> rischio 3; bersaglio a 105 -> 0,67
        setup = self._con_livelli(110.0, 105.0, 100.0)
        ingresso, motivo = ltf.controlla(setup, [barra(108.5, 108.5, 107.5, 108.0, 9)])
        assert ingresso is None
        assert "GEST-01" in motivo and "0.67" in motivo

    def test_un_rapporto_buono_lo_lascia_passare(self) -> None:
        # stesso ingresso e stesso stop, bersaglio a 95 -> 4,00
        setup = self._con_livelli(110.0, 95.0, 90.0)
        ingresso, motivo = ltf.controlla(setup, [barra(108.5, 108.5, 107.5, 108.0, 9)])
        assert ingresso is not None, motivo
        assert "rapporto 4.00" in motivo

    def test_il_motivo_dice_su_quale_prezzo(self) -> None:
        """Senza il prezzo nel motivo non si puo' capire perche' ha rifiutato."""
        setup = self._con_livelli(110.0, 105.0, 100.0)
        _, motivo = ltf.controlla(setup, [barra(108.5, 108.5, 107.5, 108.0, 9)])
        assert "107.00000" in motivo
