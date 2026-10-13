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
