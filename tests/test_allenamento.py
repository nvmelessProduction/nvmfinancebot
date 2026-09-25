"""L'allenamento degli agenti: manopole, esame, paletti, memoria, rapporto."""

import numpy as np

from nvm.agenti import manopole
from nvm.prova import allenamento as al
from nvm.prova.allenamento import Prova, esame, proposte


def _prova(serie, scadute=0.01, durata=1.0, drawdown=None, romeo=None, segnali=None):
    serie = np.asarray(serie, float)
    cumulata = np.cumsum(serie)
    dd = float((np.maximum.accumulate(cumulata) - cumulata).max()) if drawdown is None else drawdown
    # 2008-2023: la prima settimana giudicata come nel cammino.
    w0, _ = al._settimane(2008, 2023)
    return Prova({}, serie, w0, 100, float(serie.mean()), scadute, durata, dd, segnali or {}, romeo)


def _settimane():
    w0, w1 = al._settimane(2008, 2023)
    return w1 - w0


def test_le_manopole_si_leggono_si_cambiano_e_restano_nel_mansionario(tmp_path):
    prima = manopole.attuali()
    try:
        manopole.applica({"Livelli": {"stop minimo": 0.33}, "Orario": {"ora di New York": [9, 12]}})
        from nvm.agenti import conferme, livelli
        assert livelli.STOP_MINIMO == 0.33 and conferme.NEW_YORK == (9, 12)
        # Fuori dal mansionario non si va: uno stop di 5 range non si applica.
        manopole.applica({"Livelli": {"stop minimo": 5.0}, "Nessuno": {"x": 1}})
        assert livelli.STOP_MINIMO == 0.33
        manopole.salva(manopole.attuali(), tmp_path / "agenti.json")
        manopole.applica(prima)
        assert livelli.STOP_MINIMO == prima["Livelli"]["stop minimo"]
        assert manopole.leggi(tmp_path / "agenti.json")["Livelli"]["stop minimo"] == 0.33
        assert manopole.impronta() != manopole.impronta(manopole.leggi(tmp_path / "agenti.json"))
    finally:
        manopole.applica(prima)


def test_si_cresce_un_passo_alla_volta_e_non_si_ripete_una_prova_scartata():
    m = manopole.trova("Livelli", "stop minimo")
    assert m.vicini(0.25) == [0.2, 0.33] and m.vicini(0.5) == [0.33]
    valori = manopole.attuali()
    tutte = proposte(valori, [], 100)
    assert ("Livelli", "stop minimo", 0.25, 0.33) in tutte
    scartata = {"chiave": al._chiave("Livelli", "stop minimo", 0.25, 0.33), "esito": "scartata", "numero": 98}
    assert ("Livelli", "stop minimo", 0.25, 0.33) not in proposte(valori, [scartata], 100)
    # Dopo il riposo si puo' riprovare: i dati sono cresciuti.
    assert ("Livelli", "stop minimo", 0.25, 0.33) in proposte(valori, [scartata], 98 + al.RIPOSO)


def test_una_modifica_resta_solo_se_vince_con_certezza():
    rng = np.random.default_rng(0)
    n = _settimane()
    oggi = rng.normal(0.1, 2.0, n)
    meglio = _prova(oggi + 0.3 + rng.normal(0, 0.2, n))     # tutte le settimane un po' meglio
    rumore = _prova(oggi + rng.normal(0, 2.0, n))           # diversa, ma a caso
    assert esame(_prova(oggi), meglio, prove=20).passa
    assert not esame(_prova(oggi), rumore, prove=20).passa
    # Con tante prove l'asticella sale: un vantaggio piccolo non basta piu'.
    poco = _prova(oggi + 0.03 + rng.normal(0, 0.4, n))
    assert esame(_prova(oggi), poco, prove=1).basso > esame(_prova(oggi), poco, prove=200).basso


def test_lo_stop_infinito_non_passa_i_paletti():
    """Allargare lo stop avvicina il risultato a zero facendo scadere le operazioni: non vale."""
    rng = np.random.default_rng(1)
    n = _settimane()
    oggi = rng.normal(-0.1, 1.0, n)
    infinito = _prova(oggi + 0.1 + rng.normal(0, 0.1, n), scadute=0.17, durata=5.2)
    e = esame(_prova(oggi, scadute=0.008, durata=0.8), infinito, prove=10)
    assert e.basso > 0 and not e.passa
    assert any("scadute" in p for p in e.paletti) and any("lunghe" in p for p in e.paletti)


def test_non_si_tiene_una_modifica_che_ci_allontana_da_romeo():
    rng = np.random.default_rng(2)
    n = _settimane()
    oggi = rng.normal(0.1, 1.0, n)
    e = esame(_prova(oggi, romeo=6), _prova(oggi + 0.3, romeo=4), prove=5)
    assert not e.passa and any("Romeo" in p for p in e.paletti)
    assert esame(_prova(oggi, romeo=6), _prova(oggi + 0.3, romeo=5), prove=5).passa


def test_la_diagnosi_e_gli_effetti_parlano_dei_segnali():
    oggi = _prova([0.0] * _settimane(), segnali={
        "Orario": {"ora di Londra di Romeo": [400, 40.0], "fuori dalle ore di Romeo": [900, -45.0]},
        "Bias": {"range a favore": [500, 10.0]}})
    assert "meglio con «ora di Londra di Romeo»" in al.diagnosi("Orario", oggi)
    assert "peggio con «fuori dalle ore di Romeo»" in al.diagnosi("Orario", oggi)
    assert al.diagnosi("Bias", oggi) == "pochi casi per dire dove sbaglio"
    nuova = _prova([0.0] * _settimane(), segnali={
        "Orario": {"ora di Londra di Romeo": [400, 60.0], "fuori dalle ore di Romeo": [900, -45.0]},
        "Bias": {"range a favore": [500, -5.0]}})
    su, giu = al.effetti(oggi, nuova, escluso="Livelli")
    assert su.startswith("Orario con «ora di Londra di Romeo»") and giu.startswith("Bias con «range a favore»")


def test_la_memoria_si_salva_e_si_rilegge(tmp_path):
    p = tmp_path / "allenamento.json"
    assert al.leggi_memoria(p) == {"prove": [], "ultimo": {}}
    al.salva_memoria({"prove": [{"agente": "Livelli", "media": np.float64(0.1)}], "ultimo": {"settimana": "2026-S39"}}, p)
    assert al.leggi_memoria(p)["prove"][0]["media"] == 0.1
