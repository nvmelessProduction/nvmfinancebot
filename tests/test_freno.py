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


class ProvaSeriePronta(unittest.TestCase):
    """Il DXY gia' calcolato, che viaggia col repository.

    Esiste perche' Dukascopy limita gli indirizzi che chiedono troppo, e una
    macchina che ha gia' seminato vent'anni di storia puo' trovarsi la porta
    chiusa per ore. Senza questa strada, il bot resta fermo per un dato che
    si puo' benissimo consegnare dentro il codice.
    """

    def scrivi(self, righe: str) -> Path:
        import gzip
        import tempfile

        percorso = Path(tempfile.mkdtemp()) / "dxy.csv.gz"
        with gzip.open(percorso, "wt", encoding="utf-8") as file:
            file.write("orario_utc,apertura,massimo,minimo,chiusura\n" + righe)
        self.addCleanup(lambda: percorso.unlink(missing_ok=True))
        return percorso

    def test_legge_la_serie(self) -> None:
        from datetime import datetime, timezone

        import importa_dxy

        percorso = self.scrivi(
            "2026-09-16T21:00:00Z,103.100000,103.250000,103.050000,103.200000\n"
            "2026-09-16T22:00:00Z,103.200000,103.300000,103.150000,103.280000\n"
        )
        candele = importa_dxy.da_file(percorso)
        self.assertEqual(len(candele), 2)
        self.assertEqual(candele[0].orario,
                         datetime(2026, 9, 16, 21, tzinfo=timezone.utc))
        self.assertAlmostEqual(candele[0].massimo, 103.25, places=6)
        self.assertAlmostEqual(candele[1].chiusura, 103.28, places=6)

    def test_un_file_di_altro_genere_non_si_interpreta(self) -> None:
        """Meglio fermarsi che archiviare numeri presi da un file sbagliato."""
        import gzip
        import tempfile

        import importa_dxy

        percorso = Path(tempfile.mkdtemp()) / "altro.csv.gz"
        with gzip.open(percorso, "wt", encoding="utf-8") as file:
            file.write("data_ora_utc,valuta,stelle,descrizione\n")
        self.addCleanup(lambda: percorso.unlink(missing_ok=True))
        with self.assertRaises(SystemExit):
            importa_dxy.da_file(percorso)

    def test_le_righe_storte_si_saltano_senza_fermare_tutto(self) -> None:
        import importa_dxy

        percorso = self.scrivi(
            "2026-09-16T21:00:00Z,103.1,103.25,103.05,103.2\n"
            "\n"
            "riga rotta\n"
            "2026-09-16T22:00:00Z,103.2,103.3,103.15,103.28\n"
        )
        self.assertEqual(len(importa_dxy.da_file(percorso)), 2)
