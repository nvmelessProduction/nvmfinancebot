"""L'allenamento degli agenti: manopole, esame, paletti, memoria, rapporto."""

import numpy as np

from nvm.agenti import manopole
from nvm.prova import allenamento as al
from nvm.prova.allenamento import Prova, esame, proposte


def _settimane():
    w0, w1 = al._settimane(2008, 2023)
    return w1 - w0


def _prova(operazioni, scadute=0.01, durata=1.0, romeo=None, segnali=None):
    """Una prova da una lista, per settimana, degli R delle operazioni scelte."""
    serie = np.array([sum(o) for o in operazioni], float)
    quadrati = np.array([sum(x * x for x in o) for o in operazioni], float)
    conteggi = np.array([len(o) for o in operazioni], float)
    cumulata = np.cumsum(serie)
    dd = float((np.maximum.accumulate(cumulata) - cumulata).max())
    w0, _ = al._settimane(2008, 2023)
    tutte = [x for o in operazioni for x in o]
    return Prova({}, serie, w0, quadrati, conteggi, len(tutte), float(np.mean(tutte)) if tutte else 0.0,
                 scadute, durata, dd, segnali or {}, romeo)


def _operazioni(rng, media, oscillazione, per_settimana=2):
    return [list(rng.normal(media, oscillazione, per_settimana)) for _ in range(_settimane())]


def test_le_manopole_si_leggono_si_cambiano_senza_recinti(tmp_path):
    prima = manopole.attuali()
    try:
        manopole.applica({"Livelli": {"stop minimo": 0.33}, "Orario": {"ora di New York": [9, 12]}})
        from nvm.agenti import conferme, livelli
        assert livelli.STOP_MINIMO == 0.33 and conferme.NEW_YORK == (9, 12)
        # Nessun recinto: anche uno stop minimo di 5 range si puo' provare.
        manopole.applica({"Livelli": {"stop minimo": 5.0}})
        assert livelli.STOP_MINIMO == 5.0
        # Solo quello che non ha senso si ignora: uno stop negativo, un'ora 25, una manopola che non c'e'.
        manopole.applica({"Livelli": {"stop minimo": -1}, "Orario": {"ora di New York": [9, 25]}, "Nessuno": {"x": 1}})
        assert livelli.STOP_MINIMO == 5.0 and conferme.NEW_YORK == (9, 12)
        manopole.salva(manopole.attuali(), tmp_path / "agenti.json")
        manopole.applica(prima)
        assert livelli.STOP_MINIMO == prima["Livelli"]["stop minimo"]
        assert manopole.leggi(tmp_path / "agenti.json")["Livelli"]["stop minimo"] == 5.0
        assert manopole.impronta() != manopole.impronta(manopole.leggi(tmp_path / "agenti.json"))
    finally:
        manopole.applica(prima)


def test_si_cresce_un_passo_alla_volta_e_non_si_ripete_una_prova_scartata():
    assert manopole.trova("Livelli", "stop minimo").vicini(0.25) == [0.2, 0.3]
    assert manopole.trova("Orario", "ora di Londra").vicini([1, 5]) == [[0, 5], [2, 5], [1, 4], [1, 6]]
    assert manopole.trova("Grilletto", "colpi").vicini(1) == [2]
    valori = manopole.attuali()
    tutte = proposte(valori, [], 100)
    assert ("Livelli", "stop minimo", 0.25, 0.3) in tutte
    scartata = {"chiave": al._chiave("Livelli", "stop minimo", 0.25, 0.3), "esito": "scartata", "numero": 98}
    assert ("Livelli", "stop minimo", 0.25, 0.3) not in proposte(valori, [scartata], 100)
    # Dopo il riposo si puo' riprovare: i dati sono cresciuti.
    assert ("Livelli", "stop minimo", 0.25, 0.3) in proposte(valori, [scartata], 98 + al.RIPOSO)


def test_resta_solo_quello_che_migliora_la_qualita_con_certezza():
    rng = np.random.default_rng(0)
    oggi = _prova(_operazioni(rng, 0.05, 1.0))
    meglio = _prova(_operazioni(rng, 0.25, 1.0))
    uguale = _prova(_operazioni(rng, 0.05, 1.0))
    assert esame(oggi, meglio, prove=20).passa
    assert not esame(oggi, uguale, prove=20).passa


def test_guadagnare_di_piu_non_e_migliorare():
    """L'utente: una modifica resta se migliora le prestazioni, non se fa guadagnare di piu'."""
    rng = np.random.default_rng(1)
    base = _operazioni(rng, 0.05, 1.0)
    oggi = _prova(base)
    # Puntare il doppio: guadagna il doppio, ma la qualita' e' la stessa.
    assert not esame(oggi, _prova([[2 * x for x in o] for o in base]), prove=5).passa
    # Aprire il doppio delle operazioni, tutte uguali: guadagna di piu', stessa qualita'.
    assert not esame(oggi, _prova([o + list(rng.normal(0.05, 1.0, len(o))) for o in base]), prove=5).passa


def test_lo_stop_infinito_peggiora_le_prestazioni_da_solo():
    """Senza divieti: uno stop enorme porta ogni operazione verso zero, e la qualita' scende."""
    rng = np.random.default_rng(2)
    oggi = _prova(_operazioni(rng, 0.1, 1.0), scadute=0.008, durata=0.8)
    infinito = _prova(_operazioni(rng, 0.002, 0.2), scadute=0.17, durata=5.2)
    e = esame(oggi, infinito, prove=10)
    assert not e.passa and e.media < 0
    assert any("scadute" in n for n in e.note) and any("durata" in n for n in e.note)


def test_romeo_e_le_altre_misure_si_scrivono_ma_non_decidono():
    rng = np.random.default_rng(3)
    base = _operazioni(rng, 0.05, 1.0)
    e = esame(_prova(base, romeo=6), _prova(_operazioni(rng, 0.3, 1.0), romeo=4), prove=5)
    assert e.passa and any("Romeo ritrovate 6 → 4" in n for n in e.note)


def test_la_diagnosi_e_gli_effetti_parlano_dei_segnali():
    oggi = _prova([[] for _ in range(_settimane())], segnali={
        "Orario": {"ora di Londra di Romeo": [400, 40.0], "fuori dalle ore di Romeo": [900, -45.0]},
        "Bias": {"range a favore": [500, 10.0]}})
    assert "meglio con «ora di Londra di Romeo»" in al.diagnosi("Orario", oggi)
    assert "peggio con «fuori dalle ore di Romeo»" in al.diagnosi("Orario", oggi)
    assert al.diagnosi("Bias", oggi) == "pochi casi per dire dove sbaglio"
    nuova = _prova([[] for _ in range(_settimane())], segnali={
        "Orario": {"ora di Londra di Romeo": [400, 60.0], "fuori dalle ore di Romeo": [900, -45.0]},
        "Bias": {"range a favore": [500, -5.0]}})
    su, giu = al.effetti(oggi, nuova, escluso="Livelli")
    assert su.startswith("Orario con «ora di Londra di Romeo»") and giu.startswith("Bias con «range a favore»")


def test_la_memoria_si_salva_e_si_rilegge(tmp_path):
    p = tmp_path / "allenamento.json"
    assert al.leggi_memoria(p) == {"prove": [], "idee": [], "ultimo": {}}
    al.salva_memoria({"prove": [{"agente": "Livelli", "media": np.float64(0.1)}], "ultimo": {"settimana": "2026-S39"}}, p)
    assert al.leggi_memoria(p)["prove"][0]["media"] == 0.1
