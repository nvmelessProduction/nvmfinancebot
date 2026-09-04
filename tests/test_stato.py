"""Collaudo di core/stato.py: dallo storico di candele alla Fotografia."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import motore as m
from core import stato as st
from core.definizioni import Bias, Candela, Polarita, TipoKeyLevel
from core.parametri import TF
from core.stato import Conto

INIZIO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def c(apertura: float, massimo: float, minimo: float, chiusura: float, giorni: int) -> Candela:
    return Candela(INIZIO + timedelta(days=giorni), apertura, massimo, minimo, chiusura)


# ===========================================================================
# La bias e la sua eredita'
# ===========================================================================
class TestBias:
    def test_serie_parte_da_nessuna(self) -> None:
        """Senza C1 non c'e' nulla con cui confrontare."""
        serie = st.serie_bias([c(10, 12, 8, 11, 0)])
        assert serie == (Bias.NESSUNA,)

    def test_accettazione_produce_la_bias(self) -> None:
        candele = [c(10, 15, 5, 12, 0), c(14, 17, 13, 16, 1)]
        assert st.serie_bias(candele)[-1] is Bias.LONG

    def test_def24_eredita_attraverso_una_catena_di_inside(self) -> None:
        """Il motivo per cui la bias va ricalcolata dall'inizio.

        Dopo l'accettazione arrivano cinque inside bar senza gap: la bias
        deve restare LONG fino in fondo. Guardando solo le ultime due candele
        si otterrebbe NESSUNA, e sarebbe sbagliato.
        """
        candele = [c(10, 20, 0, 18, 0), c(19, 22, 18, 21, 1)]       # accettazione: LONG
        for passo in range(5):
            candele.append(c(20, 21 - passo * 0.1, 19 + passo * 0.1, 20, 2 + passo))

        serie = st.serie_bias(candele)
        assert serie[1] is Bias.LONG
        assert serie[-1] is Bias.LONG, "l'eredita' si e' persa lungo la catena"

        # La prova che serve la storia: le sole ultime due non bastano.
        from core.definizioni import bias_timeframe
        assert bias_timeframe(candele[-1], candele[-2]) is Bias.NESSUNA

    def test_def26_pavimento_di_tre_candele(self) -> None:
        due = [c(10, 15, 5, 12, 0), c(14, 17, 13, 16, 1)]
        assert st.bias_corrente(due, INIZIO + timedelta(days=10)) is Bias.NESSUNA
        tre = due + [c(16, 19, 15, 18, 2)]
        assert st.bias_corrente(tre, INIZIO + timedelta(days=10)) is Bias.LONG

    def test_def31_niente_bias_su_h12_e_h6(self) -> None:
        storico = {TF.H12: [c(10, 15, 5, 12, i) for i in range(5)]}
        assert TF.H12 not in st.bias_per_timeframe(storico, INIZIO + timedelta(days=10))

    def test_la_bias_non_vede_il_futuro(self) -> None:
        """Serve almeno il pavimento di DEF-26: tre candele chiuse."""
        candele = [
            c(10, 15, 5, 12, 0),
            c(11, 14, 6, 13, 1),
            c(14, 17, 13, 16, 2),          # accettazione a rialzo -> LONG
            c(6, 7, 3, 4, 3),              # accettazione a ribasso -> SHORT
        ]
        assert st.bias_corrente(candele, INIZIO + timedelta(days=2, hours=12)) is Bias.LONG
        assert st.bias_corrente(candele, INIZIO + timedelta(days=3, hours=12)) is Bias.SHORT


# ===========================================================================
# Key level
# ===========================================================================
class TestKeyLevel:
    def storico(self) -> dict:
        # C1 e' la penultima chiusa: massimo 110, minimo 100.
        return {TF.W1: [
            c(100, 105, 95, 102, 0),
            c(102, 110, 100, 108, 7),      # <- C1
            c(108, 115, 107, 112, 14),     # <- C0, prende il massimo di C1
        ]}

    def test_def36_calcolati_su_c1(self) -> None:
        livelli = st.key_level_correnti(self.storico(), INIZIO + timedelta(days=20))
        valori = {l.tipo: l.valore for l in livelli}
        assert valori[TipoKeyLevel.MAX] == 110
        assert valori[TipoKeyLevel.MIN] == 100
        assert valori[TipoKeyLevel.META] == 105

    def test_def38_presa_rilevata(self) -> None:
        presi = st.key_level_presi(self.storico(), INIZIO + timedelta(days=20))
        assert any(l.tipo is TipoKeyLevel.MAX and l.valore == 110 for l in presi)

    def test_def38_senza_presa_niente(self) -> None:
        storico = {TF.W1: [
            c(100, 105, 95, 102, 0),
            c(102, 110, 100, 108, 7),
            c(105, 109, 101, 106, 14),     # resta dentro C1
        ]}
        assert st.key_level_presi(storico, INIZIO + timedelta(days=20)) == []

    def test_setup05_sbilanciamento_direzionale(self) -> None:
        sbil = st.sbilanciamenti_per_timeframe(self.storico(), INIZIO + timedelta(days=20))
        assert sbil.get(TF.W1) is Bias.LONG

    def test_chi_spazza_entrambi_i_lati_non_sbilancia(self) -> None:
        """Come DEF-16 passo 1: rompere sopra e sotto non dice nulla."""
        storico = {TF.W1: [
            c(100, 105, 95, 102, 0),
            c(102, 110, 100, 108, 7),
            c(108, 115, 95, 105, 14),      # prende sia il massimo sia il minimo
        ]}
        assert TF.W1 not in st.sbilanciamenti_per_timeframe(storico, INIZIO + timedelta(days=20))


# ===========================================================================
# Gap
# ===========================================================================
class TestGap:
    def test_gap_rilevato(self) -> None:
        candele = [c(10, 12, 8, 11, 0), c(11, 14, 10, 13, 1), c(14, 18, 13, 17, 2)]
        gap = st.gap_del_timeframe(candele, TF.D1)
        assert len(gap) == 1 and gap[0].polarita is Polarita.RIALZISTA

    def test_def14_il_gap_invalidato_sparisce(self) -> None:
        candele = [
            c(10, 12, 8, 11, 0), c(11, 14, 10, 13, 1), c(14, 18, 13, 17, 2),
            c(13, 14, 6, 7, 3),            # chiude sotto livello_inv = 8
        ]
        assert st.gap_del_timeframe(candele, TF.D1) == []

    def test_def14_l_ombra_non_invalida(self) -> None:
        candele = [
            c(10, 12, 8, 11, 0), c(11, 14, 10, 13, 1), c(14, 18, 13, 17, 2),
            c(13, 14, 6, 10, 3),           # buca con l'ombra, chiude sopra
        ]
        assert len(st.gap_del_timeframe(candele, TF.D1)) == 1

    def test_def13_il_gap_attivo_e_del_timeframe_piu_alto(self) -> None:
        terna = [c(10, 12, 8, 11, 0), c(11, 14, 10, 13, 1), c(14, 18, 13, 17, 2)]
        storico = {TF.D1: terna, TF.W1: terna}
        gap = st.gap_target(storico, INIZIO + timedelta(days=10))
        assert gap is not None and gap.tf is TF.W1

    def test_def31_i_gap_si_cercano_anche_su_h12(self) -> None:
        terna = [c(10, 12, 8, 11, 0), c(11, 14, 10, 13, 1), c(14, 18, 13, 17, 2)]
        gap = st.gap_target({TF.H12: terna}, INIZIO + timedelta(days=10))
        assert gap is not None and gap.tf is TF.H12


# ===========================================================================
# Livelli strutturali
# ===========================================================================
class TestLivelli:
    def test_def27_i_consumati_spariscono(self) -> None:
        candele = [
            c(10, 15, 5, 12, 0),           # massimo 15, minimo 5
            c(12, 20, 11, 18, 1),          # sale a 20: consuma il massimo 15
            c(18, 22, 17, 21, 2),          # continua a salire
        ]
        disponibili = st.livelli_disponibili({TF.D1: candele}, INIZIO + timedelta(days=10))
        valori = {l.valore for l in disponibili.get(TF.D1, [])}
        assert 15 not in valori, "il massimo 15 e' stato superato: consumato"
        assert 5 in valori, (
            "il minimo 5 non e' mai stato ritoccato: resta DISPONIBILE, ed e' "
            "esattamente il tipo di livello che DEF-22 cerca come target short"
        )

    def test_def27_un_livello_consumato_non_torna(self) -> None:
        """ESCL-17: il prezzo torna sopra, ma il livello resta consumato."""
        candele = [
            c(10, 15, 5, 12, 0),
            c(12, 20, 11, 18, 1),          # consuma il 15
            c(18, 19, 12, 13, 2),          # torna sotto, ma il 15 e' gia' andato
        ]
        disponibili = st.livelli_disponibili({TF.D1: candele}, INIZIO + timedelta(days=10))
        assert 15 not in {l.valore for l in disponibili.get(TF.D1, [])}

    def test_def26_lookback_di_cinque_anni(self) -> None:
        vecchia = Candela(INIZIO - timedelta(days=365 * 6), 10, 99, 5, 12)
        recenti = [c(10, 15, 5, 12, i) for i in range(5)]
        disponibili = st.livelli_disponibili(
            {TF.D1: [vecchia] + recenti}, INIZIO + timedelta(days=10)
        )
        valori = {l.valore for l in disponibili.get(TF.D1, [])}
        assert 99 not in valori, "fuori dal lookback di 5 anni"


# ===========================================================================
# La fotografia completa
# ===========================================================================
class TestFotografia:
    def storico_completo(self) -> dict:
        settimanali = [
            c(100, 105, 95, 102, 0),
            c(102, 110, 100, 108, 7),
            c(108, 111, 105, 106, 14),
        ]
        quattro_ore = [
            Candela(INIZIO + timedelta(days=14, hours=h), 100, 110, 100, 110)
            for h in (0,)
        ] + [Candela(INIZIO + timedelta(days=14, hours=4), 110, 111, 108, 109)]
        return {TF.W1: settimanali, TF.H4: quattro_ore, TF.M3: settimanali}

    def test_la_fotografia_si_costruisce(self) -> None:
        foto = st.costruisci_fotografia(
            istante=INIZIO + timedelta(days=14, hours=5),
            strumento="EURUSD",
            storico=self.storico_completo(),
            conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
            eta_calendario_ore=1.0,
        )
        assert foto.strumento == "EURUSD"
        assert isinstance(foto.bias_per_tf, dict)
        assert isinstance(foto.key_level_presi, list)

    def test_la_fotografia_alimenta_il_motore(self) -> None:
        """Il giro completo: storico -> fotografia -> decisione tracciabile."""
        foto = st.costruisci_fotografia(
            istante=INIZIO + timedelta(days=14, hours=5),
            strumento="EURUSD",
            storico=self.storico_completo(),
            conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
            eta_calendario_ore=1.0,
        )
        decisione = m.valuta(foto, TF.H4)
        assert decisione.azione in ("NONE", "BUY", "SELL")
        if decisione.azione == "NONE":
            assert decisione.regole_che_bloccano, "astensione senza regola"

    def test_ricalcolo_deterministico(self) -> None:
        """Nessuno stato si trascina: stessa storia, stessa fotografia."""
        argomenti = dict(
            istante=INIZIO + timedelta(days=14, hours=5),
            strumento="EURUSD",
            storico=self.storico_completo(),
            conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
            eta_calendario_ore=1.0,
        )
        prima = st.costruisci_fotografia(**argomenti)
        for _ in range(10):
            assert st.costruisci_fotografia(**argomenti) == prima

    def test_niente_lookahead_nella_costruzione(self) -> None:
        """Una candela futura nello storico non deve cambiare la fotografia."""
        storico = self.storico_completo()
        istante = INIZIO + timedelta(days=14, hours=5)
        pulita = st.costruisci_fotografia(
            istante=istante, strumento="EURUSD", storico=storico,
            conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
            eta_calendario_ore=1.0,
        )
        sporca_storico = dict(storico)
        sporca_storico[TF.W1] = list(storico[TF.W1]) + [
            Candela(INIZIO + timedelta(days=21), 106, 200, 105, 199)
        ]
        sporca = st.costruisci_fotografia(
            istante=istante, strumento="EURUSD", storico=sporca_storico,
            conto=Conto(equity=10000.0, prezzo_cfd=109.0, valore_punto=1.0),
            eta_calendario_ore=1.0,
        )
        assert sporca.bias_per_tf == pulita.bias_per_tf
        assert sporca.key_level_presi == pulita.key_level_presi
        assert sporca.gap_attivo == pulita.gap_attivo


class TestPurezza:
    def test_nessun_accesso_a_rete_o_disco(self) -> None:
        import ast

        albero = ast.parse(open("core/stato.py", encoding="utf-8").read())
        moduli: set[str] = set()
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                moduli.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                moduli.add(nodo.module.split(".")[0])
        vietati = {"httpx", "requests", "socket", "urllib", "sqlite3", "os", "pathlib", "csv"}
        assert not (moduli & vietati), moduli & vietati
