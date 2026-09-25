"""L'autoanalisi: dopo ogni operazione finita, ogni agente si chiede dove ha sbagliato."""

import json

import numpy as np
import pytest

from nvm.agenti.capo import COLONNE
from nvm.prova.campo import simula
from nvm.tempo import TF, ny
from nvm.vivo import autoanalisi
from nvm.vivo.stato import Seguita
from tests.aiuti import candele

Q = 15 * 60
T0 = ny(2026, 9, 10, 5)


def _seguita(**k):
    """Uno short: CRT 1.1000-1.1100, manipolazione fino a 1.1105, ingresso 1.1080, stop minimo 0,25."""
    base = dict(chiave="k", strumento="EURUSD", alto="H4", basso="M15", verso="short", quando=T0,
                ingresso=1.1080, stop=1.1105, tp1=1.1050, tp2=1.0925, scadenza=T0 + 100 * Q, entrata=True,
                x=[0.0] * len(COLONNE), rr1=1.2, rr2=6.2, costi=0.0, p1=0.6, q=0.3, atteso=0.1,
                livello=1.1085, crt_alto=1.1100, crt_basso=1.1000, estremo=1.1105, stop_minimo=0.25, oltre=0.75)
    base.update(k)
    return Seguita(**base)


def _basse(righe):
    return candele("EURUSD", TF.M15, [(T0 + n * Q, *r) for n, r in enumerate(righe)])


# Sale a 1.1107 (prende lo stop a 1.1105, non uno a 1.1110), poi scende al primo obiettivo e torna su.
PREZZI = [(1.1080, 1.1107, 1.1075, 1.1082), (1.1082, 1.1085, 1.1040, 1.1045), (1.1045, 1.1090, 1.1044, 1.1088)]


def _con_esito(s, basse):
    op = autoanalisi._operazione(s, s.stop_minimo, s.oltre, s.pareggio_a, s.invalida_candele, s.tempo_candele)
    e = simula(op, basse, s.scadenza)
    s.esito = {"uscita": e.uscita.value, "erre": e.erre, "quando": e.quando, "tp1": e.tp1_preso, "tp2": False}
    return s


def test_con_le_scelte_in_uso_si_rifa_la_stessa_operazione():
    s = _seguita()
    op = autoanalisi._operazione(s, s.stop_minimo, s.oltre, s.pareggio_a, s.invalida_candele, s.tempo_candele)
    assert op.stop == pytest.approx(s.stop) and op.tp2 == pytest.approx(s.tp2) and op.tp1 == s.tp1


def test_i_livelli_scoprono_che_uno_stop_un_passo_piu_largo_l_avrebbe_salvata():
    basse = _basse(PREZZI)
    s = _con_esito(_seguita(), basse)
    assert s.esito["erre"] < -1
    alt = autoanalisi.alternative(s, basse)
    migliore = max(alt["Livelli"], key=lambda a: a[2])
    assert migliore[:2] == ("stop minimo", 0.3) and migliore[2] > 0
    # Il Grilletto (invalidazione) non l'avrebbe salvata: lo stop e' preso alla prima candela.
    assert all(r < -1 for _, _, r in alt["Grilletto"])
    testo = autoanalisi.rifletti(s, alt, [], {}, None, True, (0, 0))
    assert "🔍 Dove ho sbagliato" in testo
    assert "Livelli: con «stop almeno a 0,3 del range dall'ingresso» sarebbe finita +" in testo
    assert "Grilletto: nessuna mia scelta vicina l'avrebbe salvata" in testo


def test_il_diario_delle_alternative_arriva_alla_riunione():
    basse = _basse(PREZZI)
    diario: dict = {}
    for _ in range(2):
        s = _con_esito(_seguita(), basse)
        autoanalisi.aggiorna(diario, autoanalisi.alternative(s, basse), s.esito["erre"])
    assert autoanalisi.riassunto(diario) == []                  # due operazioni: troppo poche
    for _ in range(autoanalisi.SOLIDA - 2):
        autoanalisi.aggiorna(diario, autoanalisi.alternative(s, basse), s.esito["erre"])
    righe = autoanalisi.riassunto(diario)
    livelli = next(r for r in righe if r.startswith("• Livelli"))
    assert "su 20 operazioni" in livelli and "stop almeno a 0,3" in livelli and "solida" in livelli
    assert any(r.startswith("• Grilletto: dal vivo nessuna mia scelta") for r in righe)
    json.dumps(diario)                                          # sta nello stato.json


def test_un_agente_dei_segnali_guarda_se_quel_segnale_di_solito_funziona():
    s = _con_esito(_seguita(spinte={"Orario": 0.4, "Bias": -0.3}), _basse(PREZZI))
    storia = {"": {"": (1000, -0.05)}, "Orario": {"17–21 NY": (300, -0.2)}, "Bias": {"bias neutro": (100, -0.1)}}
    testo = autoanalisi.rifletti(s, {}, ["Orario"], {"Orario": {"17–21 NY": [1, 4]}}, storia, True, (0, 0))
    assert "Orario: avevo spinto a entrare con «17–21 NY»" in testo
    assert "qui di solito sbaglio, il Capo farà bene ad ascoltarmi meno" in testo
    assert "dal vivo 1 vinte su 4, e dal vivo va peggio" in testo


def test_il_capo_confronta_la_stima_con_le_decisioni_simili():
    basse = _basse(PREZZI)
    seguite = [_con_esito(_seguita(p1=0.6 + 0.01 * i), basse) for i in range(5)]
    n, giuste = autoanalisi.stime_simili(seguite, 0.62)
    assert (n, giuste) == (5, 0)
    testo = autoanalisi.rifletti(seguite[0], {}, ["Capo"], {}, None, False, (n, giuste))
    assert "Capo: stimavo 60% di arrivare al primo obiettivo; dal vivo, su 5 decisioni con una stima simile, è arrivato nel 0%" in testo


def test_una_decisione_vecchia_senza_il_crt_non_rompe_niente():
    s = _con_esito(_seguita(), _basse(PREZZI))
    s.crt_alto = s.crt_basso = s.estremo = s.stop_minimo = s.oltre = None
    assert autoanalisi.alternative(s, _basse(PREZZI)) == {}


def test_la_storia_dei_segnali_sui_vent_anni():
    x = np.zeros((4, len(COLONNE)))
    x[:2, COLONNE.index("ora 09-13")] = 1
    storia = autoanalisi.storia_dei_segnali(x, np.array([1.0, 0.0, -1.0, -1.0]))
    assert storia[""][""] == (4, -0.25)
    assert storia["Orario"]["09–13 NY"] == (2, 0.5) and storia["Orario"]["17–21 NY"] == (2, -1.0)
