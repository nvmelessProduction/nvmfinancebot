"""Il freno condiviso, e la cache dei mesi chiusi.

Due volte in questo progetto una raffica di richieste in parallelo ha fatto
smettere Dukascopy di rispondere: prima nel ciclo dal vivo, poi -- dopo aver
corretto quello -- nel seminatore, che era rimasto a dodici lavoratori.

L'attesa crescente del singolo tentativo non basta, ed e' aritmetica: con
dodici richieste in volo, quando la fonte protesta ognuna raddoppia la
PROPRIA attesa mentre le altre undici continuano. La pressione complessiva
non cala. Quel che si vede e' un muro di 503 in cui ogni singolo tentativo
sta facendo la cosa giusta.
"""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path

from core.fonte_dukascopy import Freno


class ProvaFreno(unittest.TestCase):
    def test_a_riposo_non_rallenta_nulla(self) -> None:
        freno = Freno()
        inizio = time.monotonic()
        for _ in range(5):
            freno.aspetta()
        self.assertLess(time.monotonic() - inizio, 0.1,
                        "senza proteste il freno non deve costare nulla")

    def test_una_protesta_rallenta_TUTTI(self) -> None:
        """Il punto dell'intero file: l'attesa e' condivisa, non per richiesta."""
        freno = Freno()
        freno.protesta()
        self.assertGreater(freno.attesa, 0.0)

        inizio = time.monotonic()
        fatti: list[float] = []

        def chiedi() -> None:
            freno.aspetta()
            fatti.append(time.monotonic() - inizio)

        fili = [threading.Thread(target=chiedi) for _ in range(3)]
        for f in fili:
            f.start()
        for f in fili:
            f.join()

        fatti.sort()
        self.assertGreater(
            fatti[-1], 0.5,
            "tre richieste dopo una protesta non devono partire insieme")

    def test_l_attesa_ha_un_tetto(self) -> None:
        freno = Freno(attesa_massima=3.0)
        for _ in range(30):
            freno.protesta()
        self.assertLessEqual(freno.attesa, 3.0)

    def test_i_successi_riaccelerano(self) -> None:
        freno = Freno()
        for _ in range(4):
            freno.protesta()
        carico = freno.attesa
        for _ in range(10):
            freno.contento()
        self.assertLess(freno.attesa, carico)

    def test_non_scende_sotto_il_minimo(self) -> None:
        freno = Freno(attesa_minima=0.2)
        for _ in range(50):
            freno.contento()
        self.assertGreaterEqual(freno.attesa, 0.2)


class ProvaCacheMensile(unittest.TestCase):
    """Un mese chiuso non cambia piu': richiederlo e' solo carico inutile.

    Ma soprattutto: senza cache, "rilancia finche' il messaggio non sparisce"
    e' un consiglio che puo' non finire mai, perche' ogni giro rimette sotto
    sforzo anche i mesi gia' riusciti.
    """

    def test_il_mese_in_corso_non_si_mette_in_cache(self) -> None:
        """Cresce mentre lo si guarda: congelarlo lo troncherebbe per sempre."""
        from datetime import datetime, timezone

        from core import fonte_dukascopy as fd

        adesso = datetime.now(timezone.utc)
        chiamate: list[str] = []

        def finto(percorso, etichetta, tentativi=5):
            chiamate.append(percorso)
            return None                     # 404: non esiste

        vero = fd._con_tentativi
        fd._con_tentativi = finto
        try:
            fd.orarie_del_mese("EURUSD", adesso.year, adesso.month)
            fd.orarie_del_mese("EURUSD", adesso.year, adesso.month)
        finally:
            fd._con_tentativi = vero

        self.assertEqual(len(chiamate), 2,
                         "il mese in corso va richiesto ogni volta")

    def test_il_404_di_un_mese_chiuso_non_e_un_guasto(self) -> None:
        """Ricordato come 'non esiste', non come 'non e' arrivato'.

        Se la cache vuota fosse riletta come un fallimento, `severo` alzerebbe
        `MeseNonScaricato` a ogni rilancio su mesi che semplicemente non
        esistono -- e il seminatore direbbe per sempre ARCHIVIO INCOMPLETO.
        """
        from core import fonte_dukascopy as fd

        def quattrocentoquattro(percorso, etichetta, tentativi=5):
            fd._e_mancante[percorso] = True     # cio' che fa il vero su un 404
            return None

        vero = fd._con_tentativi
        fd._con_tentativi = quattrocentoquattro
        try:
            # Un anno prima che qualunque cosa esistesse.
            fd.orarie_del_mese("EURUSD", 1990, 1, severo=True)
            # Il secondo giro legge la cache vuota: deve restare un "non
            # esiste", non diventare un "non e' arrivato".
            fd._e_mancante.clear()
            self.assertEqual(
                fd.orarie_del_mese("EURUSD", 1990, 1, severo=True), (),
                "un mese che non esiste non deve far dire ARCHIVIO INCOMPLETO "
                "a ogni rilancio")
        finally:
            fd._con_tentativi = vero
            (fd.DEPOSITO_ORE / "EURUSD_1990_00_BID_candles_hour_1.bi5").unlink(
                missing_ok=True)


if __name__ == "__main__":
    unittest.main()
