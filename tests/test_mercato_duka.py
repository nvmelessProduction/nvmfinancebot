"""Il ciclo dal vivo: chiedere poco, e chiedere le cose giuste.

Due guasti veri stanno dietro a questo file.

Il primo: il ciclo richiedeva a Dukascopy tre mesi di candele orarie per sei
strumenti **a ogni giro di sessanta secondi**, senza mai guardare cosa avesse
gia' in archivio. Diciotto file al minuto. Sulla VPS ha prodotto prima 503 a
raffica, poi connessioni che non rispondevano piu'.

Il secondo, piu' grave perche' silenzioso: il ciclo non scaricava affatto i
minuti. Quattro delle sei coppie di `CRT-04` entrano sotto l'ora, quindi il
motore armava setup che nessuno poteva far scattare — e nessun log protestava.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from core import mercato_duka as md
from core.definizioni import Candela
from core.duka_minuti import aggrega
from core.parametri import TF

UTC = timezone.utc


def minuti_finti(inizio: datetime, quanti: int) -> list[Candela]:
    """Candele al minuto consecutive; l'orario e' la CHIUSURA."""
    return [
        Candela(inizio + timedelta(minutes=n + 1), 1.0, 1.1, 0.9, 1.0)
        for n in range(quanti)
    ]


class ProvaCancello(unittest.TestCase):
    """`serie_da_chiedere`: non chiedere cio' che non puo' essere cambiato."""

    def setUp(self) -> None:
        self.ciclo = md.MercatoDukascopy()
        self.archivio: dict[tuple[str, TF], datetime] = {}
        self._vera = md.ultima_archiviata
        md.ultima_archiviata = lambda s, tf: self.archivio.get((s, tf))

    def tearDown(self) -> None:
        md.ultima_archiviata = self._vera

    def test_archivio_vuoto_si_chiede(self) -> None:
        adesso = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        self.assertTrue(self.ciclo.serie_da_chiedere("EURUSD", TF.H1, adesso))

    def test_ora_non_ancora_chiusa_non_si_chiede(self) -> None:
        adesso = datetime(2026, 9, 16, 12, 30, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        self.assertFalse(self.ciclo.serie_da_chiedere("EURUSD", TF.H1, adesso))

    def test_ora_chiusa_si_chiede(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 1, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        self.assertTrue(self.ciclo.serie_da_chiedere("EURUSD", TF.H1, adesso))

    def test_ogni_timeframe_ha_una_durata(self) -> None:
        """Un timeframe fuori da DURATA farebbe saltare il cancello con KeyError."""
        from core.mercato import TF_INGRESSO_OPERATIVI, TF_OPERATIVI

        for tf in set(TF_OPERATIVI) | set(TF_INGRESSO_OPERATIVI):
            self.assertIn(tf, md.DURATA, f"{tf.value} non ha una durata")


class ProvaMesiEGiorni(unittest.TestCase):
    """Quali file chiedere: di norma il mese in corso e il giorno in corso."""

    def setUp(self) -> None:
        self.ciclo = md.MercatoDukascopy()
        self.archivio: dict[tuple[str, TF], datetime] = {}
        self._vera = md.ultima_archiviata
        md.ultima_archiviata = lambda s, tf: self.archivio.get((s, tf))

    def tearDown(self) -> None:
        md.ultima_archiviata = self._vera

    def test_archivio_aggiornato_chiede_solo_il_mese_in_corso(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        self.assertEqual(self.ciclo._mesi_da_chiedere("EURUSD", adesso),
                         [(2026, 9)])

    def test_archivio_indietro_di_un_mese_ne_chiede_due(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
        self.assertEqual(self.ciclo._mesi_da_chiedere("EURUSD", adesso),
                         [(2026, 8), (2026, 9)])

    def test_il_recupero_ha_un_tetto(self) -> None:
        """Dieci anni di buco non si riempiono un file alla volta dentro al ciclo."""
        adesso = datetime(2026, 9, 16, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2016, 1, 1, tzinfo=UTC)
        mesi = self.ciclo._mesi_da_chiedere("EURUSD", adesso)
        self.assertEqual(len(mesi), md.MESI_ORARIE_MASSIMI + 1)

    def test_il_confine_di_anno_non_produce_mese_zero(self) -> None:
        adesso = datetime(2026, 1, 3, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.H1)] = datetime(2025, 11, 30, tzinfo=UTC)
        self.assertEqual(self.ciclo._mesi_da_chiedere("EURUSD", adesso),
                         [(2025, 11), (2025, 12), (2026, 1)])

    def test_minuti_aggiornati_chiede_solo_oggi(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.MIN1)] = datetime(2026, 9, 16, 13, 0, tzinfo=UTC)
        self.assertEqual(self.ciclo._giorni_da_chiedere("EURUSD", adesso),
                         [date(2026, 9, 16)])

    def test_minuti_indietro_recupera_fino_al_tetto(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 5, tzinfo=UTC)
        self.archivio[("EURUSD", TF.MIN1)] = datetime(2026, 1, 2, tzinfo=UTC)
        giorni = self.ciclo._giorni_da_chiedere("EURUSD", adesso)
        self.assertEqual(len(giorni), md.GIORNI_MINUTI_MASSIMI + 1)
        self.assertEqual(giorni[-1], date(2026, 9, 16))
        self.assertEqual(giorni, sorted(giorni))


class ProvaRiposo(unittest.TestCase):
    """Quando la fonte non risponde, il cancello sull'archivio non basta."""

    def setUp(self) -> None:
        self.ciclo = md.MercatoDukascopy()

    def test_dopo_un_guasto_non_si_riprova_subito(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 0, tzinfo=UTC)
        chiave = ("EURUSD", "ore")
        self.ciclo._guasto(chiave, adesso)
        self.assertTrue(self.ciclo._in_riposo(chiave, adesso + timedelta(minutes=1)))
        self.assertFalse(self.ciclo._in_riposo(chiave, adesso + timedelta(minutes=6)))

    def test_l_attesa_cresce_e_ha_un_tetto(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 0, tzinfo=UTC)
        chiave = ("EURUSD", "ore")
        for _ in range(20):
            self.ciclo._guasto(chiave, adesso)
        self.assertLessEqual(self.ciclo._attesa[chiave], md.RIPOSO_MASSIMO)
        self.assertGreater(self.ciclo._attesa[chiave], md.RIPOSO_INIZIALE)

    def test_un_giro_riuscito_azzera_l_attesa(self) -> None:
        adesso = datetime(2026, 9, 16, 13, 0, tzinfo=UTC)
        chiave = ("EURUSD", "ore")
        self.ciclo._guasto(chiave, adesso)
        self.ciclo._riuscito(chiave)
        self.assertFalse(self.ciclo._in_riposo(chiave, adesso))


class ProvaBloccoInFormazione(unittest.TestCase):
    """ESCL-13 sui minuti aggregati: il blocco ancora aperto non e' una candela."""

    def test_il_quarto_d_ora_incompleto_non_esce(self) -> None:
        # Minuti dalle 10:00 alle 10:07 (chiusure 10:01..10:07).
        minuti = minuti_finti(datetime(2026, 9, 16, 10, 0, tzinfo=UTC), 7)
        quarti = aggrega(minuti, 15, fino_a=minuti[-1].orario)
        self.assertEqual(quarti, [], "un blocco di 7 minuti non e' un quarto d'ora")

    def test_il_quarto_d_ora_completo_esce(self) -> None:
        minuti = minuti_finti(datetime(2026, 9, 16, 10, 0, tzinfo=UTC), 20)
        quarti = aggrega(minuti, 15, fino_a=minuti[-1].orario)
        self.assertEqual(len(quarti), 1)
        self.assertEqual(quarti[0].orario, datetime(2026, 9, 16, 10, 15, tzinfo=UTC))

    def test_senza_limite_il_blocco_aperto_uscirebbe(self) -> None:
        """La forma vecchia resta disponibile, ma non e' quella del ciclo."""
        minuti = minuti_finti(datetime(2026, 9, 16, 10, 0, tzinfo=UTC), 7)
        self.assertEqual(len(aggrega(minuti, 15)), 1)

    def test_i_buchi_non_impediscono_la_chiusura(self) -> None:
        """Un minuto senza scambi manca: il blocco resta chiuso lo stesso."""
        minuti = minuti_finti(datetime(2026, 9, 16, 10, 0, tzinfo=UTC), 30)
        del minuti[3]
        quarti = aggrega(minuti, 15, fino_a=minuti[-1].orario)
        self.assertEqual(len(quarti), 2)


class ProvaAlert(unittest.TestCase):
    """L'alert che il ciclo costruisce deve essere leggibile da chi lo riceve.

    Non lo era: `AlertIn` alzava `ValidationError` a ogni singola candela, la
    riga di log finiva in un `except` generico e il contatore `valutazioni` di
    `/salute` cresceva lo stesso. Il bot sembrava al lavoro e non aveva mai
    passato una candela al motore.
    """

    def setUp(self) -> None:
        self.candela = Candela(
            datetime(2026, 9, 16, 10, 15, tzinfo=UTC), 1.10, 1.15, 1.05, 1.12)

    def test_porta_tutti_e_quattro_i_prezzi(self) -> None:
        alert = md._alert("EURUSD", TF.MIN15, self.candela, "s")
        self.assertEqual(alert.apertura, 1.10)
        self.assertEqual(alert.massimo, 1.15)
        self.assertEqual(alert.minimo, 1.05)
        self.assertEqual(alert.chiusura, 1.12)

    def test_il_simbolo_e_il_ticker_del_future(self) -> None:
        """Chi riceve applica `future_da_ticker`, e su `EURUSD` risponde None."""
        from core.simboli import future_da_ticker

        alert = md._alert("EURUSD", TF.MIN15, self.candela, "s")
        self.assertEqual(future_da_ticker(alert.simbolo), "6E")

    def test_il_timeframe_e_riconoscibile(self) -> None:
        from core.simboli import timeframe_da_intervallo

        for tf in md.DURATA:
            alert = md._alert("EURUSD", tf, self.candela, "s")
            self.assertEqual(timeframe_da_intervallo(alert.tf), tf,
                             f"{tf.value} non torna indietro dall'alert")

    def test_ogni_strumento_dell_universo_si_traduce(self) -> None:
        from core.parametri import UNIVERSO
        from core.simboli import cfd_di, future_da_ticker

        for cfd in UNIVERSO:
            alert = md._alert(cfd, TF.H4, self.candela, "s")
            self.assertEqual(cfd_di(future_da_ticker(alert.simbolo)), cfd)


class ProvaGruppoInFormazione(unittest.TestCase):
    """La giornata in corso non e' una candela giornaliera.

    `salva_candele` fa `INSERT OR IGNORE`: la prima versione scritta vince e
    non viene piu' corretta. Archiviare il gruppo in formazione significava
    congelare una giornata a com'era mezz'ora dopo la sua apertura.
    """

    def orarie(self, da: datetime, quante: int) -> list[Candela]:
        return [
            Candela(da + timedelta(hours=n + 1), 1.0, 1.0 + n / 100, 0.9, 1.0)
            for n in range(quante)
        ]

    def test_la_giornata_in_corso_non_entra(self) -> None:
        # Da mercoledi' 22:00 (chiusura della giornata di martedi') in avanti:
        # due giornate intere e tre ore della terza.
        orarie = self.orarie(datetime(2026, 9, 15, 22, 0, tzinfo=UTC), 51)
        serie = md.costruisci(orarie)
        giorni = serie[TF.D1]
        self.assertEqual(len(giorni), 2, "la terza giornata e' ancora aperta")

    def test_il_massimo_della_giornata_e_quello_intero(self) -> None:
        orarie = self.orarie(datetime(2026, 9, 15, 22, 0, tzinfo=UTC), 51)
        giorni = md.costruisci(orarie)[TF.D1]
        # La prima giornata sono le 24 ore da 22:00 a 22:00: il massimo e'
        # quello dell'ultima delle sue ore, non della prima.
        self.assertAlmostEqual(giorni[0].massimo, 1.0 + 23 / 100, places=9)

    def test_stessa_regola_della_semina(self) -> None:
        """Se le due aggregazioni divergessero, archivio e vivo non coinciderebbero."""
        import importa_dukascopy as semina

        orarie = self.orarie(datetime(2026, 9, 15, 22, 0, tzinfo=UTC), 51)
        dal_vivo = md.costruisci(orarie)[TF.D1]
        seminate = semina.costruisci(orarie)[TF.D1]
        self.assertEqual([c.orario for c in dal_vivo], [c.orario for c in seminate])
        self.assertEqual([c.massimo for c in dal_vivo], [c.massimo for c in seminate])


class ProvaDXY(unittest.TestCase):
    """SETUP-19 senza DXY non abilita nulla, e `USDIDX` di Dukascopy e' inerte."""

    def tassi(self) -> dict:
        return {"EURUSD": 1.0850, "USDJPY": 148.20, "GBPUSD": 1.2700,
                "USDCAD": 1.3550, "USDSEK": 10.40, "USDCHF": 0.8800}

    def test_la_formula_da_un_valore_plausibile(self) -> None:
        from core.duka_dxy import indice

        self.assertAlmostEqual(indice(self.tassi()), 103.613, places=2)

    def test_il_dollaro_forte_alza_l_indice(self) -> None:
        """Il segno dei pesi: EURUSD giu' e USDJPY su spingono entrambi in alto."""
        from core.duka_dxy import indice

        base = indice(self.tassi())
        euro_giu = dict(self.tassi(), EURUSD=1.0500)
        yen_su = dict(self.tassi(), USDJPY=152.00)
        self.assertGreater(indice(euro_giu), base)
        self.assertGreater(indice(yen_su), base)

    def test_l_involucro_contiene_apertura_e_chiusura(self) -> None:
        from core.duka_dxy import candela_dxy, indice

        pezzi = {
            s: Candela(datetime(2026, 9, 16, 10, tzinfo=UTC),
                       v, v * 1.002, v * 0.998, v * 1.001)
            for s, v in self.tassi().items()
        }
        c = candela_dxy(pezzi)
        self.assertIsNotNone(c)
        self.assertGreaterEqual(c.massimo, max(c.apertura, c.chiusura))
        self.assertLessEqual(c.minimo, min(c.apertura, c.chiusura))
        self.assertAlmostEqual(c.apertura, indice(self.tassi()), places=9)

    def test_senza_un_costituente_non_si_inventa_nulla(self) -> None:
        from core.duka_dxy import candela_dxy

        pezzi = {
            s: Candela(datetime(2026, 9, 16, 10, tzinfo=UTC), v, v, v, v)
            for s, v in self.tassi().items() if s != "USDSEK"
        }
        self.assertIsNone(candela_dxy(pezzi))

    def test_componi_tiene_solo_le_ore_comuni(self) -> None:
        from core.duka_dxy import PESI, componi

        t0 = datetime(2026, 9, 16, 10, tzinfo=UTC)
        t1 = datetime(2026, 9, 16, 11, tzinfo=UTC)
        serie = {}
        for s, v in self.tassi().items():
            ore = [Candela(t0, v, v, v, v)]
            if s != "USDSEK":                    # a USDSEK manca l'ora delle 11
                ore.append(Candela(t1, v, v, v, v))
            serie[s] = ore
        self.assertEqual(len(componi(serie)), 1)
        self.assertEqual(set(serie), set(PESI))


class ProvaValutazione(unittest.TestCase):
    """Il secondo tempo di CRT-04 deve essere valutato, non solo archiviato."""

    def test_valuta_anche_i_timeframe_di_ingresso(self) -> None:
        from core.mercato import TF_INGRESSO_OPERATIVI

        visti: list[str] = []
        ciclo = md.MercatoDukascopy(su_candela=lambda a: visti.append(a.tf))
        candela = Candela(datetime(2026, 9, 16, 10, 15, tzinfo=UTC),
                          1.0, 1.1, 0.9, 1.0)
        ciclo._valuta("EURUSD", {TF.MIN15: candela, TF.H4: candela})
        self.assertIn("M15", visti)
        self.assertIn(TF.MIN15, TF_INGRESSO_OPERATIVI)

    def test_l_ordine_e_quello_della_gerarchia(self) -> None:
        """CTX-10: il superiore si ricalcola prima che si operi sotto."""
        visti: list[str] = []
        ciclo = md.MercatoDukascopy(su_candela=lambda a: visti.append(a.tf))
        candela = Candela(datetime(2026, 9, 16, 10, 15, tzinfo=UTC),
                          1.0, 1.1, 0.9, 1.0)
        ciclo._valuta("EURUSD", {
            TF.MIN5: candela, TF.D1: candela, TF.H1: candela, TF.MIN15: candela,
        })
        self.assertEqual(visti, ["1D", "H1", "M15", "M5"])


if __name__ == "__main__":
    unittest.main()
