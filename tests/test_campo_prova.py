"""Il campo di prova: il CRT si forma quando si forma, non a fine finestra.

Due cose vengono provate qui, e sono la stessa cosa vista da due lati.

**La correttezza.** Il CRT nasce alla chiusura della barra bassa che rientra
(`SETUP-02A/B`). Chi guarda la finestra intera in un colpo solo, e calcola i
key level alla sua fine, sbircia fino a una candela alta intera -- su `W -> 4h`
una settimana. `backtest/resa_crt.py` lo fa, ed e' corretto per CONTARE i CRT;
per etichettarli no.

**La velocita', che qui e' una questione di correttezza.** Avanzare barra per
barra su vent'anni vuol dire chiamare `key_level_presi` 129.000 volte per
strumento. A venti millisecondi l'una sono cinque ore e mezza, e un campo di
prova che si misura in ore non si rifa' mai: si finisce per tenersi il primo
numero uscito. Le due riduzioni qui sotto -- la memoria dell'ordine e il
taglio sui timeframe inutili -- non cambiano nessun risultato, e sono cio' che
rende la misura ripetibile.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

from core import motore as mot                                 # noqa: E402
from core import setup as stp                                  # noqa: E402
from core import stato                                         # noqa: E402
from core.definizioni import Candela                           # noqa: E402
from core.parametri import TF, TF_KEY_LEVEL                    # noqa: E402

QUANDO = datetime(2020, 1, 6, tzinfo=timezone.utc)


def barra(ore: int, apertura, massimo, minimo, chiusura) -> Candela:
    return Candela(QUANDO + timedelta(hours=ore), apertura, massimo, minimo,
                   chiusura)


class TestIlTaglioSuiTimeframeInutili:
    """`SETUP-02`: il key level dev'essere di timeframe STRETTAMENTE
    superiore. Calcolare gli altri e' lavoro che `cerca_crt` buttera'."""

    def test_e_derivata_dalla_regola_non_riscritta(self):
        """Due copie della stessa regola divergono nel punto che muove i
        soldi. Qui non ci sono due copie: c'e' una funzione interrogata."""
        for tf_crt in (TF.W1, TF.D1, TF.H4, TF.H1):
            attesi = tuple(tf for tf in TF_KEY_LEVEL
                           if stp.timeframe_crt_ammesso(tf_crt, tf))
            assert stp.tf_key_level_utili(tf_crt) == attesi

    def test_su_settimanale_restano_i_mensili_e_oltre(self):
        utili = stp.tf_key_level_utili(TF.W1)
        assert TF.M1 in utili and TF.M3 in utili
        assert TF.W1 not in utili, "non e' strettamente superiore a se stesso"
        assert TF.D1 not in utili and TF.H4 not in utili

    def test_restringere_non_cambia_il_risultato(self):
        """L'assorbimento tiene sempre il timeframe piu' ALTO, quindi un
        livello alto non puo' essere tolto da uno basso: il risultato
        ristretto e' il risultato pieno limitato a quei timeframe.

        E' l'unica ragione per cui il taglio e' lecito. Se l'assorbimento
        tenesse il piu' basso, restringere cambierebbe le risposte."""
        mensili = [Candela(datetime(2020, m, 1, tzinfo=timezone.utc),
                           100 + m, 110 + m, 90 + m, 105 + m)
                   for m in range(1, 8)]
        giornaliere = [Candela(datetime(2020, 7, g, tzinfo=timezone.utc),
                               100, 130, 80, 120) for g in range(1, 20)]
        storico = {TF.M1: tuple(mensili), TF.D1: tuple(giornaliere)}
        istante = datetime(2020, 7, 19, tzinfo=timezone.utc)

        utili = stp.tf_key_level_utili(TF.W1)
        pieno = [k for k in stato.key_level_presi(storico, istante)
                 if k.tf in utili]
        ristretto = stato.key_level_presi(storico, istante, utili)
        assert pieno == ristretto

    def test_il_pieno_resta_il_comportamento_predefinito(self):
        """Il bot non passa `solo_tf`: deve vedere tutto come prima."""
        import inspect
        firma = inspect.signature(stato.key_level_presi).parameters
        assert firma["solo_tf"].default is None


class TestLaMemoriaDellOrdine:
    """`_ordinata` costava 1,39 secondi su 2,10 di `key_level_presi`: due
    terzi del tempo a riscoprire che l'archivio e' ordinato come lo era un
    millisecondo prima."""

    def test_una_serie_disordinata_resta_disordinata(self):
        serie = [barra(2, 1, 2, 0.5, 1.5), barra(0, 1, 2, 0.5, 1.5)]
        assert mot._ordinata(serie) is False
        assert mot._ordinata(serie) is False, "la memoria non deve mentire"

    def test_una_serie_ordinata_resta_ordinata(self):
        serie = [barra(0, 1, 2, 0.5, 1.5), barra(1, 1, 2, 0.5, 1.5)]
        assert mot._ordinata(serie) is True
        assert mot._ordinata(serie) is True

    def test_la_serie_che_cresce_viene_riesaminata(self):
        """L'archivio cresce in coda: una serie allungata e' una serie nuova.
        Se la lunghezza non fosse nella chiave, una coda fuori ordine
        passerebbe inosservata per sempre."""
        serie = [barra(0, 1, 2, 0.5, 1.5), barra(5, 1, 2, 0.5, 1.5)]
        assert mot._ordinata(serie) is True
        serie.append(barra(1, 1, 2, 0.5, 1.5))      # indietro nel tempo
        assert mot._ordinata(serie) is False

    def test_la_memoria_non_cresce_senza_fine(self):
        """Ogni voce tiene in vita la serie a cui si riferisce: senza tetto
        sarebbe una perdita di memoria nel processo che gira sempre."""
        mot._MEMORIA_ORDINE.clear()
        for i in range(mot._MEMORIA_ORDINE_MASSIMA + 50):
            mot._ordinata([barra(i, 1, 2, 0.5, 1.5)])
        assert len(mot._MEMORIA_ORDINE) <= mot._MEMORIA_ORDINE_MASSIMA + 1

    def test_candele_visibili_taglia_ancora(self):
        """La barriera vale piu' della velocita': si controlla che tagli."""
        serie = [barra(o, 1, 2, 0.5, 1.5) for o in range(6)]
        visibili = mot.candele_visibili(serie, QUANDO + timedelta(hours=3))
        assert [c.orario for c in visibili] == [c.orario for c in serie[:4]]


class TestUnCrtPerCandellaDiRiferimento:

    def test_si_prende_il_primo_istante_in_cui_appare(self):
        """Dentro la stessa candela alta il CRT, una volta formato, resta
        formato: le barre dopo lo ritroverebbero identico. Contarlo ogni
        volta gonfierebbe il campione con la stessa operazione ripetuta."""
        import campo_prova
        import inspect
        corpo = inspect.getsource(campo_prova.crt_della_coppia)
        assert "break" in corpo, "senza uscita si conta lo stesso CRT n volte"

    def test_i_key_level_si_calcolano_alla_barra_non_a_fine_finestra(self):
        import campo_prova
        import inspect
        corpo = inspect.getsource(campo_prova.crt_della_coppia)
        assert "stato.key_level_presi(storico, istante, utili)" in corpo
        assert "basse[fine - 1].orario" not in corpo

    def test_l_holdout_e_chiuso_per_difetto(self):
        import campo_prova
        assert campo_prova.HOLDOUT.year == 2024
