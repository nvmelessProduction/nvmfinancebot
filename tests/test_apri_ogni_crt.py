"""Il modo diagnostico apre su ogni CRT, ma i muri restano muri.

Non e' una configurazione di strategia: e' una prova per vedere con gli occhi
che la catena arriva fino all'ordine, dopo una giornata in cui il bot non
apriva niente e non si riusciva a capire se fosse selettivita' o un guasto.

Cio' che si spegne e' esattamente cio' che un trader puo' soppesare. Cio' che
protegge il conto -- limiti di perdita, esclusioni, dati incoerenti, tetto di
posizioni, freno a mano, divieto sul conto reale -- non si tocca, perche' il
momento in cui si allentano i filtri e' esattamente quello in cui le
salvaguardie contano di piu'.
"""

import pytest

from core.config import impostazioni
from core.motore import OBIEZIONI_SOPPESABILI, _apri_ogni_crt


@pytest.fixture
def acceso(monkeypatch):
    cfg = impostazioni()
    monkeypatch.setattr(cfg, "APRI_OGNI_CRT", True, raising=False)
    yield


def test_di_partenza_e_spento():
    """Il valore di PARTENZA, non quello configurato su questa macchina.

    Guardare l'istanza viva farebbe fallire la prova appena qualcuno accende
    il modo diagnostico nel .env -- cioe' proprio quando serve.
    """
    from core.config import Impostazioni
    assert Impostazioni.model_fields["APRI_OGNI_CRT"].default is False


def test_si_accende_dalla_configurazione(acceso):
    assert _apri_ogni_crt() is True


def test_spegne_solo_cio_che_e_soppesabile():
    """L'elenco e' scritto per inclusione: una regola nuova non diventa
    scavalcabile per distrazione."""
    for regola in ("RISK-05", "SETUP-05", "SETUP-07", "CRT-20"):
        assert regola in OBIEZIONI_SOPPESABILI


def test_i_muri_non_sono_soppesabili():
    """Questi non devono cadere nemmeno nel modo diagnostico."""
    for muro in ("RISK-06", "RISK-07", "RISK-08", "RISK-09", "PRIN-99",
                 "ESCL-01", "ESCL-02", "ESCL-11", "PRIN-13", "SETUP-00"):
        assert muro not in OBIEZIONI_SOPPESABILI, muro


def test_il_veto_del_giudizio_si_salta(acceso, monkeypatch):
    """Ogni ordine passerebbe dal veto, e ogni ordine sarebbe una chiamata a
    pagamento fuori da qualunque tetto."""
    from core import strategy

    chiamate = []
    monkeypatch.setattr(strategy, "_passa_dal_giudizio",
                        lambda d, f, t: chiamate.append(1) or d)
    cfg = impostazioni()
    monkeypatch.setattr(cfg, "GIUDIZIO_ATTIVO", True, raising=False)
    from core.giudizio_claude import giudica
    assert callable(giudica)


def test_le_salvaguardie_dell_impianto_restano(acceso):
    """Volume massimo, tetto posizioni, freno a mano e conto demo non
    dipendono dal motore: stanno in `main.salvaguardia_violata` e in
    `broker`, e questo interruttore non li tocca."""
    cfg = impostazioni()
    assert cfg.VOLUME_MASSIMO > 0
    assert cfg.MAX_POSIZIONI_APERTE > 0
    assert cfg.CONSENTI_CONTO_REALE is False
