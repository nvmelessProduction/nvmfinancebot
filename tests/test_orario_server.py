"""Lo scarto fra l'orologio del server MT5 e UTC, e le candele aggregate.

Due meccanismi che non avevano prove e che hanno gia' sbagliato una volta
ciascuno, con lo stesso effetto: candele con l'orario sbagliato archiviate
come se fossero nuove, senza un errore da nessuna parte.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import broker
from core.aggregazione import (
    CONFINE_GIORNO_UTC,
    aggrega_giornaliere,
    aggrega_mensili,
    aggrega_settimanali,
)
from core.definizioni import Candela


class FintoTick:
    """Quel poco di `symbol_info_tick` che serve: l'orario."""

    def __init__(self, quando: datetime) -> None:
        self.time = int(quando.timestamp())


def _server(quando_utc: datetime, scarto_ore: int) -> FintoTick:
    """Il tick come lo manda MT5: l'ora del SERVER spacciata per UTC."""
    return FintoTick(quando_utc + timedelta(hours=scarto_ore))


def _azzera() -> None:
    broker._scarto_server = None
    broker._ultimo_tick.clear()


def _misura(quando: datetime, scarto_ore: int, simbolo: str = "EURUSD"):
    """Un tick che AVANZA: e' il solo caso in cui si accetta una misura."""
    broker._scarto_del_server(simbolo, _server(quando, scarto_ore), quando)
    dopo = quando + timedelta(seconds=30)
    return broker._scarto_del_server(simbolo, _server(dopo, scarto_ore), dopo)


# ---------------------------------------------------------------- lo scarto
def test_scarto_misurato_da_un_tick_che_avanza():
    _azzera()
    adesso = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    assert _misura(adesso, 3) == timedelta(hours=3)


def test_un_solo_avvistamento_non_basta():
    """Al primo giro non si sa ancora se il tick stia avanzando."""
    _azzera()
    adesso = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    assert broker._scarto_del_server("EURUSD", _server(adesso, 3), adesso) is None


def test_tick_congelato_non_sposta_la_misura():
    """Il guasto vero: a mercato chiuso il tick si ferma e lo scarto derivava.

    Venerdi' alle 21:00 il mercato chiude e il tick resta li'. Sabato alle
    05:00 la vecchia formula calcolava -5 ore invece di +3, e ogni barra
    finiva timbrata otto ore piu' avanti del dovuto.
    """
    _azzera()
    venerdi = datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc)
    assert _misura(venerdi, 3) == timedelta(hours=3)

    tick_fermo = _server(venerdi + timedelta(seconds=30), 3)   # non avanza piu'
    for ore in (1, 5, 30, 50):
        dopo = venerdi + timedelta(hours=ore)
        assert broker._scarto_del_server("EURUSD", tick_fermo, dopo) == timedelta(hours=3), (
            f"lo scarto e' cambiato dopo {ore}h di mercato fermo")


def test_senza_misura_precedente_un_tick_vecchio_non_viene_creduto():
    """All'avvio a mercato chiuso non si inventa uno scarto: si restituisce None."""
    _azzera()
    adesso = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)
    congelato = adesso - timedelta(hours=13)
    # Anche se il tick "cambia" fra due letture, un valore fermo da tredici
    # ore da' uno scarto implausibile e non viene creduto.
    broker._scarto_del_server("EURUSD", _server(congelato, 3), adesso)
    fuori = broker._scarto_del_server(
        "EURUSD", _server(congelato + timedelta(seconds=1), 3), adesso)
    assert fuori is None


def test_tick_assente_restituisce_l_ultima_misura():
    _azzera()
    adesso = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    _misura(adesso, 2)
    assert broker._scarto_del_server("EURUSD", None, adesso) == timedelta(hours=2)


def test_senza_tick_e_senza_misura_non_si_inventa_nulla():
    _azzera()
    adesso = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    assert broker._scarto_del_server("EURUSD", None, adesso) is None


def test_lo_scarto_segue_l_ora_legale():
    """Da +3 a +2 quando il broker cambia ora: la misura deve seguirlo."""
    _azzera()
    estate = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    assert _misura(estate, 3) == timedelta(hours=3)
    inverno = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    assert _misura(inverno, 2) == timedelta(hours=2)


# ------------------------------------------------------------ le aggregate
def _orarie(prima: datetime, quante: int) -> list[Candela]:
    """Orarie consecutive, una per ora, con prezzi che salgono."""
    return [
        Candela(prima + timedelta(hours=i), 1.0 + i, 1.5 + i, 0.5 + i, 1.2 + i)
        for i in range(quante)
    ]


def test_le_giornaliere_chiudono_al_confine_misurato():
    # Tre giorni pieni a partire dalla chiusura delle 22:00.
    inizio = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
    giornaliere = aggrega_giornaliere(_orarie(inizio, 24 * 3))
    assert giornaliere, "nessuna giornaliera costruita"
    for candela in giornaliere:
        assert candela.orario.hour == CONFINE_GIORNO_UTC


def test_la_giornaliera_in_formazione_non_esce():
    """L'ultimo gruppo e' sempre incompleto finche' non ne comincia un altro."""
    inizio = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
    complete = aggrega_giornaliere(_orarie(inizio, 24 * 2))
    # Due giornate intere nei dati, ma la seconda e' ancora l'ultima: esce solo
    # quella che ha gia' un successore.
    assert len(complete) == 1


def test_apertura_e_chiusura_vengono_dagli_estremi_del_gruppo():
    inizio = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
    orarie = _orarie(inizio, 24 * 2)
    giorno = aggrega_giornaliere(orarie)[0]
    dentro = [c for c in orarie if c.orario <= giorno.orario]
    assert giorno.apertura == dentro[0].apertura
    assert giorno.chiusura == dentro[-1].chiusura
    assert giorno.massimo == max(c.massimo for c in dentro)
    assert giorno.minimo == min(c.minimo for c in dentro)


def test_la_settimana_chiude_di_domenica():
    inizio = datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc)
    giornaliere = aggrega_giornaliere(_orarie(inizio, 24 * 21))
    settimanali = aggrega_settimanali(giornaliere)
    assert settimanali, "nessuna settimanale costruita"
    for candela in settimanali:
        assert candela.orario.weekday() == 6, f"{candela.orario} non e' domenica"
        assert candela.orario.hour == CONFINE_GIORNO_UTC


def test_il_mese_chiude_l_ultimo_giorno():
    inizio = datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc)
    giornaliere = aggrega_giornaliere(_orarie(inizio, 24 * 70))
    mensili = aggrega_mensili(giornaliere)
    assert mensili, "nessuna mensile costruita"
    for candela in mensili:
        dopo = candela.orario + timedelta(days=1)
        assert dopo.month != candela.orario.month, (
            f"{candela.orario} non e' l'ultimo giorno del mese")


def test_nessuna_aggregata_da_una_serie_troppo_corta():
    inizio = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
    assert aggrega_giornaliere(_orarie(inizio, 3)) == ()
