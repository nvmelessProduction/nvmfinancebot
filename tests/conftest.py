"""Cose comuni a tutte le prove."""

import pytest

from nvm.dati import candele


@pytest.fixture(autouse=True)
def _orari_dei_grafici_puliti():
    """Gli orari dei grafici di TradingView (`candele.SESSIONI`) li scrive il bot dal vivo: una prova non li lascia
    alle altre."""
    prima = dict(candele.SESSIONI)
    yield
    candele.SESSIONI.clear()
    candele.SESSIONI.update(prima)


@pytest.fixture(autouse=True, scope="module")
def _orari_dei_grafici_puliti_nel_modulo():
    """Lo stesso per le preparazioni di un modulo intero (`scope="module"`): quelle partono prima della pulizia di ogni
    prova, e i loro orari restavano alle prove dei moduli dopo (cinque prove cadevano solo con tutta la serie)."""
    prima = dict(candele.SESSIONI)
    yield
    candele.SESSIONI.clear()
    candele.SESSIONI.update(prima)
