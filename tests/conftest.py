"""Preparazione comune a tutte le prove.

La cosa piu' importante che fa questo file e' impedire che una prova mandi
un messaggio vero su Telegram.

Non e' un'ipotesi: `ingresso_ltf.arma()` notifica, e la suite lo chiama una
dozzina di volte con i valori inventati del suo fixture. Per mesi ogni
`pytest tests/` ha spedito sul telefono dell'utente una fila di "EURUSD:
setup ribassista armato su 4 ore, spazzato 110,000" -- numeri che non
somigliano nemmeno a un cambio euro-dollaro, perche' infatti non lo sono.
Sommate su tutte le esecuzioni sono diventate migliaia di notifiche, e
hanno sepolto quelle vere: il riepilogo partiva regolarmente e non si
vedeva, in mezzo agli avvisi finti.

`core.notifier` ha la sua chiusura propria, che guarda questa variabile e
anche `PYTEST_CURRENT_TEST`. Qui la si valorizza comunque, perche' una
protezione che si legge dove stanno le prove e' una protezione che chi
scrive la prossima prova ha qualche speranza di notare.
"""

import os

import pytest

from core import notifier


@pytest.fixture(autouse=True, scope="session")
def niente_telegram_nelle_prove():
    os.environ[notifier.VARIABILE_SILENZIO] = "1"
    yield


@pytest.fixture(autouse=True)
def archivio_isolato(tmp_path, monkeypatch):
    """Nessuna prova scrive nell'archivio vero.

    `storage.connessione()` apre `impostazioni().DB_PATH`, e `impostazioni()`
    e' `lru_cache`: la PRIMA chiamata della sessione fissa il percorso per
    tutte. Una prova che valorizzi `DB_PATH` senza svuotare la cache isola
    quindi solo se stessa -- e solo se e' la prima a girare. Tutte le altre
    finiscono sullo stesso archivio, o sul `bot.db` di produzione se qualcosa
    ha gia' letto le impostazioni.

    I due esiti si somigliano molto finche' non si guarda: le prove passano
    uguale, e intanto scrivono nell'archivio su cui il bot sta decidendo.
    """
    from core.config import impostazioni

    monkeypatch.setenv("DB_PATH", str(tmp_path / "archivio-prova.db"))
    impostazioni.cache_clear()
    yield
    impostazioni.cache_clear()


@pytest.fixture(autouse=True)
def telegram_chiuso(monkeypatch):
    """Doppia mandata, per ogni singola prova.

    Se qualcuno togliesse la variabile d'ambiente -- o la sovrascrivesse
    provando la configurazione -- qui la porta resta chiusa lo stesso.
    """
    def _vietato(*_args, **_kwargs):
        raise AssertionError(
            "una prova ha provato a mandare un messaggio vero su Telegram: "
            "simula `notifier.invia_appena_possibile` se vuoi controllarne il testo"
        )

    monkeypatch.setattr(notifier, "_invia_a", _vietato)
