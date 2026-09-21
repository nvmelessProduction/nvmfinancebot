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

    def test_rev48_tf_h4_ha_key_level_propri(self) -> None:
        """Senza key level su TF_H4, la riga TF_H1 di SETUP-05 e' lettera morta.

        SETUP-05 pretende che `TF_H4` abbia sbilanciato un key level perche'
        si possa operare su `TF_H1`, e PRIN-10 mette `TF_H1` fra i timeframe
        di esecuzione. DEF-36 pero' elenca solo i sei timeframe da `TF_12M` a
        `TF_1D`. Adottata la lettura che le tiene insieme (REV-48).
        """
        storico = {TF.H4: [
            c(100, 105, 95, 102, 0),
            c(102, 110, 100, 108, 1),      # <- C1
            c(108, 115, 107, 112, 2),      # <- C0, prende il massimo di C1
        ]}
        adesso = INIZIO + timedelta(days=5)
        assert any(l.tf is TF.H4 for l in st.key_level_correnti(storico, adesso))
        assert st.sbilanciamenti_per_timeframe(storico, adesso).get(TF.H4) is Bias.LONG

    def test_h6_e_h12_restano_ai_soli_gap(self) -> None:
        """DEF-31 li riserva ai gap (REV-11): niente key level, mai."""
        for tf in (TF.H6, TF.H12):
            storico = {tf: [
                c(100, 105, 95, 102, 0),
                c(102, 110, 100, 108, 1),
                c(108, 115, 107, 112, 2),
            ]}
            livelli = st.key_level_correnti(storico, INIZIO + timedelta(days=5))
            assert livelli == [], f"{tf.value} non deve produrre key level"

    def test_i_timeframe_intraday_ne_producono(self) -> None:
        """Questo collaudo pretendeva il contrario, e la sua ragione era:
        "sotto TF_H4 non c'e' nessun trigger da servire".

        Non e' piu' vero. `COPPIE_CRT` ha `H1 -> M5` e `M15 -> M1min`, quindi
        sotto `TF_H1` ci sono tre trigger. Senza key level propri quei
        timeframe non hanno niente da spazzare, e `SETUP-02` chiede che `N2`
        prenda un livello di timeframe strettamente superiore: un CRT su un
        minuto doveva andare a spazzare un livello a quattro ore.

        Misurato il 2026-09-21 sul bot vivo: 33 decisioni su 40 fermate da
        `SETUP-00`, che sembrava selettivita' della strategia ed era una
        tabella mai estesa.
        """
        for tf in (TF.H1, TF.MIN15, TF.MIN5):
            storico = {tf: [
                c(100, 105, 95, 102, 0),
                c(102, 110, 100, 108, 1),
                c(108, 115, 107, 112, 2),
            ]}
            livelli = st.key_level_correnti(storico, INIZIO + timedelta(days=5))
            assert livelli, f"{tf.value} deve produrre key level"

    def test_sotto_il_minuto_non_c_e_niente_da_servire(self) -> None:
        """`TF_M1min` resta fuori, e stavolta la ragione tiene: non esiste
        nessun trigger sotto di lui."""
        from core.parametri import TF_KEY_LEVEL
        assert TF.MIN1 not in TF_KEY_LEVEL

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


# ===========================================================================
# Aggregazione dei timeframe che MT5 non ha
# ===========================================================================
class TestAggregazione:
    """`TF_3M`, `TF_6M` e `TF_12M` si costruiscono dalle mensili.

    Il test che conta e' quello sui periodi incompleti: un trimestre in corso
    non e' una candela, e' una candela in formazione. Emetterlo creerebbe un
    lookahead di mesi, non di minuti, e sarebbe invisibile perche' i numeri
    sembrerebbero giusti.
    """

    def mensili(self, quanti: int = 12, anno: int = 2026) -> list[Candela]:
        return [
            Candela(datetime(anno, mese, 28, tzinfo=timezone.utc),
                    100 + mese, 110 + mese, 90 + mese, 105 + mese)
            for mese in range(1, quanti + 1)
        ]

    def test_trimestrali_da_un_anno_completo(self) -> None:
        from core.aggregazione import aggrega

        trimestri = aggrega(self.mensili(), 3)
        assert len(trimestri) == 4

    def test_ohlc_del_gruppo(self) -> None:
        """Apertura del primo, chiusura dell'ultimo, estremi di tutti."""
        from core.aggregazione import aggrega

        q1 = aggrega(self.mensili(3), 3)[0]
        assert q1.apertura == 101          # gennaio
        assert q1.chiusura == 108          # marzo
        assert q1.massimo == 113           # massimo di marzo
        assert q1.minimo == 91             # minimo di gennaio

    def test_il_periodo_incompleto_non_esiste(self) -> None:
        """CASO CRITICO: con undici mensili l'ultimo trimestre e' in corso."""
        from core.aggregazione import aggrega

        assert len(aggrega(self.mensili(11), 3)) == 3, (
            "il quarto trimestre ha due mensili su tre: e' in formazione, "
            "e una candela in formazione non va mai valutata (ESCL-13)"
        )
        assert len(aggrega(self.mensili(5), 3)) == 1
        assert len(aggrega(self.mensili(2), 3)) == 0

    def test_semestrali_e_annuale(self) -> None:
        from core.aggregazione import aggrega

        assert len(aggrega(self.mensili(12), 6)) == 2
        assert len(aggrega(self.mensili(12), 12)) == 1
        assert len(aggrega(self.mensili(11), 12)) == 0, "l'anno non e' finito"

    def test_allineamento_al_calendario(self) -> None:
        """I trimestri sono gennaio-marzo, non tre mesi qualsiasi."""
        from core.aggregazione import aggrega

        # Partendo da febbraio, il primo trimestre completo e' aprile-giugno.
        da_febbraio = [
            Candela(datetime(2026, mese, 28, tzinfo=timezone.utc),
                    100 + mese, 110 + mese, 90 + mese, 105 + mese)
            for mese in range(2, 13)
        ]
        trimestri = aggrega(da_febbraio, 3)
        assert len(trimestri) == 3, "gennaio manca: il primo trimestre e' incompleto"
        assert trimestri[0].apertura == 104, "il primo completo parte da aprile"

    def test_la_chiusura_al_primo_del_mese_appartiene_al_mese_prima(self) -> None:
        """CASO CRITICO, e per un anno intero e' passato inosservato.

        Chi costruisce le candele dagli orari di apertura — l'importatore, lo
        scaricatore, il fornitore — marca la mensile di gennaio con la
        chiusura "1 febbraio 00:00", perche' la chiusura di una barra e'
        l'apertura della successiva. Leggendo `.month` di quell'orario si
        ottiene *febbraio*: i gruppi si sfasano di un mese, quasi ogni
        trimestre finisce con due mesi o con quattro, e viene scartato come
        incompleto. Il sintomo non e' un errore, e' un `TF_12M` sempre vuoto.
        """
        from core.aggregazione import aggrega

        # Dodici mensili del 2025, marcate come le marca l'importatore:
        # la mensile di gennaio chiude il primo febbraio.
        mensili = [
            Candela(datetime(2025 + (mese == 12), (mese % 12) + 1, 1, tzinfo=timezone.utc),
                    100 + mese, 110 + mese, 90 + mese, 105 + mese)
            for mese in range(1, 13)
        ]
        assert len(aggrega(mensili, 3)) == 4, "quattro trimestri, non zero"
        assert len(aggrega(mensili, 6)) == 2
        assert len(aggrega(mensili, 12)) == 1, "l'anno c'e' tutto"

        anno = aggrega(mensili, 12)[0]
        assert anno.apertura == 101, "l'anno apre con gennaio"
        assert anno.chiusura == 117, "e chiude con dicembre"

    # -- mensili costruite dalle giornaliere --------------------------------
    def giornaliere(self, mese: int, giorni: tuple[int, ...], anno: int = 2026):
        """Sessioni di un mese, con la chiusura marcata come la marca
        l'importatore: l'apertura della sessione successiva."""
        return [
            Candela(datetime(anno, mese, giorno, tzinfo=timezone.utc),
                    100 + giorno, 110 + giorno, 90 + giorno, 105 + giorno)
            for giorno in giorni
        ]

    def test_mensile_costruita_dalle_sessioni(self) -> None:
        from core.aggregazione import aggrega_per_mese

        sessioni = (self.giornaliere(1, (5, 15, 25))
                    + self.giornaliere(2, (4, 14, 24)))
        mensili = aggrega_per_mese(sessioni)
        assert len(mensili) == 1, "febbraio e' in corso: resta fuori"
        gennaio = mensili[0]
        assert gennaio.apertura == 105, "apre con la prima sessione"
        assert gennaio.chiusura == 130, "chiude con l'ultima"
        assert gennaio.massimo == 135, "il piu' alto di tutte"
        assert gennaio.minimo == 95, "il piu' basso di tutte"

    def test_l_ultimo_mese_e_in_formazione(self) -> None:
        """Un mese e' finito quando esiste una sessione successiva."""
        from core.aggregazione import aggrega_per_mese

        assert len(aggrega_per_mese(self.giornaliere(1, (5, 15)))) == 0
        tre_mesi = (self.giornaliere(1, (5,)) + self.giornaliere(2, (5,))
                    + self.giornaliere(3, (5,)))
        assert len(aggrega_per_mese(tre_mesi)) == 2

    def test_un_mese_con_sessioni_mancanti_esiste_lo_stesso(self) -> None:
        """Differenza voluta rispetto ad `aggrega`.

        Un trimestre senza uno dei suoi tre mesi e' incompleto e non esiste.
        Un mese con meno sessioni del solito e' invece normale: festivita',
        mezze giornate, chiusure dell'exchange. Pretendere un numero fisso di
        sessioni cancellerebbe dicembre di ogni anno.
        """
        from core.aggregazione import aggrega_per_mese

        scarso = self.giornaliere(1, (7,)) + self.giornaliere(2, (3, 13))
        assert len(aggrega_per_mese(scarso)) == 1

    def test_la_chiusura_al_primo_del_mese_finisce_nel_mese_giusto(self) -> None:
        """Stessa trappola di `aggrega`, un piano piu' in basso."""
        from core.aggregazione import aggrega_per_mese

        sessioni = [
            Candela(datetime(2026, 1, 30, tzinfo=timezone.utc), 100, 110, 90, 105),
            # l'ultima sessione di gennaio chiude quando apre la prima di febbraio
            Candela(datetime(2026, 2, 1, tzinfo=timezone.utc), 105, 115, 95, 112),
            Candela(datetime(2026, 2, 10, tzinfo=timezone.utc), 112, 120, 108, 118),
            Candela(datetime(2026, 3, 1, tzinfo=timezone.utc), 118, 125, 115, 120),
            # marzo serve solo a provare che febbraio e' finito
            Candela(datetime(2026, 3, 15, tzinfo=timezone.utc), 120, 128, 118, 124),
        ]
        mensili = aggrega_per_mese(sessioni)
        assert len(mensili) == 2
        gennaio, febbraio = mensili
        assert gennaio.chiusura == 112, (
            "la sessione marcata 1 febbraio e' l'ultima di GENNAIO: "
            "e' la sua chiusura, non l'apertura di febbraio"
        )
        assert febbraio.apertura == 112

    def test_costruisci_superiori(self) -> None:
        from core.aggregazione import costruisci_superiori

        superiori = costruisci_superiori(self.mensili())
        assert set(superiori) == {TF.M3, TF.M6, TF.M12}
        assert len(superiori[TF.M3]) == 4
        assert len(superiori[TF.M6]) == 2
        assert len(superiori[TF.M12]) == 1

    def test_gruppo_non_valido(self) -> None:
        from core.aggregazione import aggrega

        with pytest.raises(ValueError):
            aggrega(self.mensili(), 0)

    def test_orari_di_chiusura_scarta_l_ultima(self) -> None:
        """La chiusura della barra i e' l'apertura della i+1.

        L'ultima non ha successore, quindi non ha chiusura nota: e' quella in
        formazione, e sparisce.
        """
        from core.aggregazione import orari_di_chiusura

        assert orari_di_chiusura([10, 11, 12, 13]) == (11, 12, 13)
        assert orari_di_chiusura([10]) == ()
        assert orari_di_chiusura([]) == ()


# ===========================================================================
# TF_H4 costruito dalle orarie (REV-48)
# ===========================================================================
class TestQuattroOre:
    """`aggrega_orarie` esiste perche' SETUP-05 non puo' autorizzare un
    ingresso su `TF_H1` senza sapere cosa ha fatto `TF_H4`."""

    def orarie(self, ore: tuple[int, ...], giorno: int = 5):
        """Barre orarie marcate sulla CHIUSURA, come vuole DEF-02."""
        return [
            Candela(datetime(2026, 1, giorno, ora, tzinfo=timezone.utc),
                    100 + ora, 110 + ora, 90 + ora, 105 + ora)
            for ora in ore
        ]

    def test_quattro_orarie_fanno_una_candela(self) -> None:
        from core.aggregazione import aggrega_orarie

        blocchi = aggrega_orarie(self.orarie((1, 2, 3, 4)))
        assert len(blocchi) == 1
        blocco = blocchi[0]
        assert blocco.apertura == 101, "apre con la prima oraria"
        assert blocco.chiusura == 109, "chiude con l'ultima"
        assert blocco.massimo == 114 and blocco.minimo == 91
        assert blocco.orario.hour == 4, "l'orario e' la chiusura dell'ultima"

    def test_il_confine_e_la_chiusura_non_l_apertura(self) -> None:
        """La barra che chiude alle 04:00 appartiene al blocco 01-04, non al
        successivo: e' l'errore che sposterebbe ogni candela di un blocco."""
        from core.aggregazione import aggrega_orarie

        blocchi = aggrega_orarie(self.orarie((1, 2, 3, 4, 5, 6, 7, 8)))
        assert len(blocchi) == 2
        assert [b.orario.hour for b in blocchi] == [4, 8]

    def test_il_blocco_incompleto_non_e_una_candela(self) -> None:
        """ESCL-13: tre orarie su quattro sono una candela in formazione."""
        from core.aggregazione import aggrega_orarie

        assert aggrega_orarie(self.orarie((1, 2, 3))) == ()
        assert len(aggrega_orarie(self.orarie((1, 2, 3, 4, 5)))) == 1

    def test_un_buco_nei_dati_non_inventa_una_candela(self) -> None:
        from core.aggregazione import aggrega_orarie

        assert aggrega_orarie(self.orarie((1, 2, 4))) == ()

    def test_non_mescola_due_giorni(self) -> None:
        from core.aggregazione import aggrega_orarie

        blocchi = aggrega_orarie(self.orarie((1, 2, 3, 4), giorno=5)
                                 + self.orarie((1, 2, 3, 4), giorno=6))
        assert len(blocchi) == 2
        assert {b.orario.day for b in blocchi} == {5, 6}
