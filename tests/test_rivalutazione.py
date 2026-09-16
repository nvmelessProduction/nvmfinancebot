"""Collaudo di core/rivalutazione.py — le regole che agiscono a candela chiusa.

Tre regole non parlano di prezzi ma di candele chiuse, e per questo non
possono vivere nella sentinella: `GEST-08` (estensione del target), `SETUP-17`
(bias invertita) e `GEST-10` (target di comando raggiunto). Fino a REV-55
nessuna delle tre veniva mai chiamata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import rivalutazione as riv
from core.definizioni import Bias, Candela, KeyLevel, TipoKeyLevel
from core.motore import Fotografia
from core.parametri import TF

ADESSO = datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc)


def cand(massimo: float, minimo: float, chiusura: float, apertura: float, ore: int = 0) -> Candela:
    return Candela(ADESSO - timedelta(hours=ore), apertura, massimo, minimo, chiusura)


# Lo stesso CRT short di test_motore: N2 prende il key level a 110.5 e
# richiude dentro il range di N1.
N1 = cand(massimo=110, minimo=100, chiusura=110, apertura=100, ore=4)
N2 = cand(massimo=111, minimo=108, chiusura=109, apertura=110, ore=0)
KL_SETTIMANALE = KeyLevel(TF.W1, TipoKeyLevel.MAX, 110.5)
KL_H4_MIN = KeyLevel(TF.H4, TipoKeyLevel.MIN, 100.0)
KL_H4_MAX = KeyLevel(TF.H4, TipoKeyLevel.MAX, 110.0)


def foto(**modifiche: object) -> Fotografia:
    argomenti: dict = {
        "istante": ADESSO,
        "strumento": "EURUSD",
        "candele_per_tf": {TF.H4: [N1, N2]},
        "bias_per_tf": {TF.M3: Bias.SHORT},
        "target_raggiunto_per_tf": {},
        "key_level_presi": [KL_SETTIMANALE],
        "key_level_correnti": [KL_SETTIMANALE, KL_H4_MAX, KL_H4_MIN],
        "sbilanciamenti": {TF.D1: Bias.LONG, TF.W1: Bias.LONG},
        "prezzo_cfd": 109.0,
        "spread": 0.0002,
        "eventi_news": [],
        "eta_calendario_ore": 1.0,
    }
    argomenti.update(modifiche)
    return Fotografia(**argomenti)


def posizione(**modifiche: object) -> dict:
    """Una riga di `storage.posizioni_aperte()`.

    Aperta su H1, cioe' su un timeframe INFERIORE a quello di questa
    fotografia: e' la condizione perche' GEST-08 possa estendere.
    """
    riga = {
        "id": 1,
        "ticket": 1001,
        "simbolo": "EURUSD",
        "direzione": "SELL",
        "volume": 0.4,
        "volume_iniziale": 0.4,
        "prezzo_ingresso": 109.0,
        "sl": 111.0,
        "tp": 105.0,
        "tp1": 106.0,
        "tf_crt": "TF_H1",
        "tp1_raggiunto": 0,
        "spread_ingresso": 0.0002,
        "stato": "aperta",
    }
    riga.update(modifiche)
    return riga


class TestEstensioneDelTarget:
    """GEST-08 — alla chiusura di un timeframe superiore che conferma."""

    def test_estende_al_key_level_del_timeframe_che_conferma(self) -> None:
        azioni = riv.rivaluta(foto(), TF.H4, [posizione()])
        assert len(azioni) == 1
        azione = azioni[0]
        assert azione.tipo == "estendi_target"
        assert azione.regola == "GEST-08"
        # KL_H4_MIN e' a 100 sul future, ancorato a N2 (109) e riportato sul
        # CFD (prezzo 109): resta 100. E' piu' lontano del target attuale.
        assert azione.valore < 105.0

    def test_non_estende_verso_il_prezzo(self) -> None:
        """A senso unico: un target gia' oltre il key level non si accorcia."""
        azioni = riv.rivaluta(foto(), TF.H4, [posizione(tp=95.0)])
        assert azioni == ()

    def test_un_timeframe_pari_o_inferiore_non_estende(self) -> None:
        """La posizione nasce su TF_H4: la chiusura di TF_H4 non la estende."""
        azioni = riv.rivaluta(foto(), TF.H4, [posizione(tf_crt="TF_H4")])
        assert azioni == ()

    def test_senza_crt_non_si_estende(self) -> None:
        """"Conferma il pattern" significa che un CRT si e' formato (REV-26)."""
        piatte = {TF.H4: [N1, cand(massimo=109, minimo=108, chiusura=108.5, apertura=109)]}
        azioni = riv.rivaluta(foto(candele_per_tf=piatte), TF.H4, [posizione()])
        assert azioni == ()

    def test_un_crt_nella_direzione_opposta_non_conferma(self) -> None:
        azioni = riv.rivaluta(foto(), TF.H4, [posizione(direzione="BUY")])
        assert all(a.tipo != "estendi_target" for a in azioni)

    def test_una_posizione_su_un_altro_strumento_non_si_tocca(self) -> None:
        """GEST-13 — ogni posizione si gestisce per conto proprio."""
        assert riv.rivaluta(foto(), TF.H4, [posizione(simbolo="XAUUSD")]) == ()


class TestBiasInvertita:
    """SETUP-17 — non si chiude, si protegge."""

    def test_bias_opposta_porta_a_pareggio(self) -> None:
        azioni = riv.rivaluta(foto(bias_per_tf={TF.M3: Bias.LONG}), TF.H4, [posizione()])
        assert len(azioni) == 1
        azione = azioni[0]
        assert azione.tipo == "break_even"
        assert azione.regola == "SETUP-17"
        # Short: il pareggio sta SOTTO l'ingresso, per coprire i costi.
        assert azione.valore is not None and azione.valore < 109.0

    def test_non_si_chiude_mai(self) -> None:
        azioni = riv.rivaluta(foto(bias_per_tf={TF.M3: Bias.LONG}), TF.H4, [posizione()])
        assert all(a.tipo != "chiudi" for a in azioni)

    def test_dopo_tp1_lo_stop_non_si_muove_piu(self) -> None:
        """GEST-05 — lo stop si muove una volta sola."""
        azioni = riv.rivaluta(
            foto(bias_per_tf={TF.M3: Bias.LONG}), TF.H4, [posizione(tp1_raggiunto=1)]
        )
        assert all(a.tipo != "break_even" for a in azioni)

    def test_bias_concorde_non_fa_nulla(self) -> None:
        azioni = riv.rivaluta(foto(), TF.H4, [posizione()])
        assert all(a.tipo != "break_even" for a in azioni)


class TestSegnoInvertito:
    """DEF-33 — su USDJPY il CRT e l'ordine hanno segno opposto.

    Una posizione BUY su `USDJPY` corrisponde a un CRT **short** su `6J`.
    Confrontare la bias di comando del future con la direzione del CFD senza
    passare da DEF-33 inverte ogni giudizio: SETUP-17 proteggerebbe le
    posizioni concordi e lascerebbe correre quelle contrarie.
    """

    def test_bias_short_e_posizione_buy_sono_concordi(self) -> None:
        azioni = riv.rivaluta(
            foto(strumento="USDJPY"), TF.H4, [posizione(direzione="BUY", simbolo="USDJPY")]
        )
        assert all(a.tipo != "break_even" for a in azioni), "short sul future = BUY sul CFD"

    def test_bias_long_e_posizione_buy_sono_opposte(self) -> None:
        azioni = riv.rivaluta(
            foto(strumento="USDJPY", bias_per_tf={TF.M3: Bias.LONG}),
            TF.H4,
            [posizione(direzione="BUY", simbolo="USDJPY")],
        )
        assert any(a.tipo == "break_even" for a in azioni)


class TestTargetDiComando:
    """GEST-10 — al target di tf_comando si chiude tutto."""

    def test_chiude_le_posizioni_nella_direzione_della_vecchia_bias(self) -> None:
        azioni = riv.rivaluta(
            foto(target_raggiunto_per_tf={TF.M3: True}), TF.H4, [posizione()]
        )
        assert len(azioni) == 1
        assert azioni[0].tipo == "chiudi"
        assert azioni[0].regola == "GEST-10"

    def test_non_chiude_quelle_nella_direzione_opposta(self) -> None:
        """*"Si chiudono a mercato quelle nella direzione della vecchia bias,
        non le altre."*"""
        azioni = riv.rivaluta(
            foto(target_raggiunto_per_tf={TF.M3: True}), TF.H4, [posizione(direzione="BUY")]
        )
        assert all(a.tipo != "chiudi" for a in azioni)

    def test_la_vecchia_bias_non_e_quella_corrente(self) -> None:
        """SETUP-06 scarta il timeframe il cui target e' raggiunto.

        Quindi `tf_comando` non e' MAI il timeframe di cui GEST-10 parla, e
        leggerlo li' darebbe sempre False: la regola non scatterebbe mai.
        La vecchia bias e' quella calcolata ignorando i target raggiunti.
        """
        istantanea = foto(
            bias_per_tf={TF.M3: Bias.SHORT, TF.D1: Bias.LONG},
            target_raggiunto_per_tf={TF.M3: True},
        )
        # La bias corrente e' scesa su TF_1D (LONG); la vecchia era TF_3M
        # (SHORT), ed e' la direzione delle posizioni da chiudere.
        azioni = riv.rivaluta(istantanea, TF.H4, [posizione(direzione="SELL")])
        assert any(a.regola == "GEST-10" and a.tipo == "chiudi" for a in azioni)

    def test_oggi_in_produzione_non_scatta_mai(self) -> None:
        """`target_raggiunto_per_tf` resta vuoto: il target direzionale di
        DEF-46 non e' calcolato da nessuno. Il ramo e' scritto e collaudato
        perche' il giorno in cui quel dato arrivera' GEST-10 sia gia' al suo
        posto, non l'ennesima regola implementata e mai chiamata."""
        assert riv.rivaluta(foto(), TF.H4, [posizione()])[0].regola == "GEST-08"


class TestNienteDaFare:
    def test_nessuna_posizione(self) -> None:
        assert riv.rivaluta(foto(), TF.H4, []) == ()

    def test_posizione_gia_chiusa(self) -> None:
        assert riv.rivaluta(foto(), TF.H4, [posizione(stato="chiusa")]) == ()

    def test_posizione_senza_tf_di_origine(self) -> None:
        """Le posizioni aperte prima della migrazione non hanno `tf_crt`:
        restano alla vecchia gestione invece di sparire."""
        assert riv.rivaluta(foto(), TF.H4, [posizione(tf_crt=None)]) == ()
