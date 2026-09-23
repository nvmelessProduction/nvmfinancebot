"""Quando il bot si sveglia, non quanto ci mette a pensare.

Il 2026-09-23 il bot rifiutava le operazioni con "alert vecchio di 24s (su
M1min il massimo e' 15s)". La diagnosi facile era la lentezza del calcolo, e
infatti il calcolo e' stato reso nove volte piu' rapido -- 2,7 secondi a 301
millesimi. Il problema si e' ripresentato identico il giro dopo.

La causa vera stava altrove. Il ciclo dormiva `intervallo_sec` fissi partendo
da quando finiva il giro precedente, quindi il risveglio cadeva in un punto
qualsiasi del minuto e ci restava per sempre. La candela M1 chiude a :00: se il
risveglio e' a :36, ogni alert nasce vecchio di 36 secondi qualunque cosa faccia
il motore. I 4.385 alert di quella giornata lo dicono riga per riga -- ricevuto
alle 17:12:36, ritardo 36,3s; alle 17:13:45, ritardo 45,8s -- con mediana 88,5
secondi contro un tetto di 15.

Questi test tengono fermo il risveglio sul confine. Se qualcuno rimette un
sonno a intervallo fisso, qui si rompe.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.mercato_mt5 import MercatoMT5


def _alle(minuto: int, secondo: float) -> datetime:
    interi = int(secondo)
    return datetime(2026, 9, 23, 17, minuto, interi,
                    int(round((secondo - interi) * 1_000_000)),
                    tzinfo=timezone.utc)


class RisveglioSulConfine(unittest.TestCase):

    def setUp(self) -> None:
        self.m = MercatoMT5()
        self.m.intervallo_sec = 60.0
        self.m.margine_sec = 1.5

    def _risveglio(self, adesso: datetime) -> float:
        """A che secondo del minuto il bot si risveglia partendo da qui."""
        attesa = self.m.attesa_fino_al_confine(adesso)
        return (adesso.timestamp() + attesa) % 60.0

    def test_il_risveglio_cade_sempre_subito_dopo_la_chiusura(self):
        # Da qualunque punto del minuto il giro finisca, il prossimo
        # risveglio e' sul confine piu' il margine. E' l'invariante che
        # rende raggiungibile il tetto di 15s su M1.
        for secondo in (0.0, 0.4, 1.5, 2.0, 12.7, 30.0, 36.3, 45.8, 52.5, 59.9):
            with self.subTest(secondo=secondo):
                self.assertAlmostEqual(
                    self._risveglio(_alle(12, secondo)), 1.5, places=3)

    def test_nessuna_attesa_supera_un_intervallo(self):
        # Un risveglio saltato e' una candela persa: l'attesa non deve mai
        # valere piu' di un giro intero.
        for secondo in (0.0, 0.1, 1.4, 1.5, 1.6, 30.0, 59.9):
            with self.subTest(secondo=secondo):
                attesa = self.m.attesa_fino_al_confine(_alle(12, secondo))
                self.assertGreater(attesa, 0.0)
                self.assertLessEqual(attesa, 60.0)

    def test_dentro_il_margine_si_prende_la_candela_appena_chiusa(self):
        # Giro finito a :00,4 -- la barra che ha appena chiuso forse non e'
        # ancora pubblicata. Si aspetta un secondo, non un minuto.
        self.assertAlmostEqual(
            self.m.attesa_fino_al_confine(_alle(12, 0.4)), 1.1, places=3)

    def test_il_ritardo_che_ne_esce_sta_sotto_il_tetto_di_M1(self):
        # Il tetto su M1 e' 15s (ritardo_massimo(TF.MIN1, 180)). Il ritardo
        # e' il margine piu' la durata del giro: con il giro misurato a 5,4s
        # restano quasi otto secondi di margine.
        from core.parametri import TF, ritardo_massimo
        giro_misurato = 5.4
        tetto = ritardo_massimo(TF.MIN1, 180.0)
        self.assertLess(self.m.margine_sec + giro_misurato, tetto)

    def test_senza_aggancio_il_ritardo_sarebbe_stato_quello_misurato(self):
        # La riprova del guasto: col sonno fisso, un giro partito a :36
        # ripartiva a :36 e l'alert nasceva vecchio di 36 secondi.
        partenza = _alle(12, 36.3)
        fisso = (partenza.timestamp() + self.m.intervallo_sec) % 60.0
        self.assertAlmostEqual(fisso, 36.3, places=3)
        self.assertAlmostEqual(self._risveglio(partenza), 1.5, places=3)


if __name__ == "__main__":
    unittest.main()
