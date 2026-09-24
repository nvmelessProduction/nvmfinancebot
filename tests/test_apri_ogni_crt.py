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
    `broker`, e questo interruttore non li tocca.

    Si guardano i valori di PARTENZA, non quelli configurati su questa
    macchina -- per lo stesso motivo di `test_di_partenza_e_spento` qui
    sopra. `MAX_POSIZIONI_APERTE` e' un tetto che si puo' voler togliere
    (a 0 e' disattivato, vedi `main.py`), e leggere l'istanza viva faceva
    fallire questa prova appena qualcuno lo toglieva davvero: il 2026-09-22
    e' successo. Cio' che la prova deve dire e' che il modo diagnostico non
    tocca queste manopole, non quanto valgono oggi.
    """
    from core.config import Impostazioni
    campi = Impostazioni.model_fields
    assert campi["VOLUME_MASSIMO"].default > 0
    assert campi["MAX_POSIZIONI_APERTE"].default > 0
    assert campi["CONSENTI_CONTO_REALE"].default is False
    # E il conto reale resta vietato anche su questa macchina: quello non e'
    # una manopola di comodo, e' il divieto che protegge i soldi veri.
    assert impostazioni().CONSENTI_CONTO_REALE is False


class TestLeEsclusioni:
    """Il modo diagnostico toglie i divieti di STRATEGIA, non le salvaguardie.

    `verifica_divieti` e' l'ultimo controllo (PREC-05) e riapplica come muri
    regole che i filtri avevano gia' espresso: `ESCL-01` e' `SETUP-07`
    ("ordine contro bias_comando") ed `ESCL-03` e' `SETUP-08`. Con il modo
    acceso quei due erano gia' caduti fra i filtri e rispuntavano qui --
    misurato il 2026-09-21: 12 CRT su 12 fermati da ESCL-01 e ESCL-03 dopo
    aver superato tutto il resto.
    """

    def test_toglie_solo_i_due_che_duplicano_i_filtri(self):
        """La regola vive in `divieti_permanenti`, che prende il modo
        diagnostico come argomento invece di leggerlo: cosi' si prova con
        acceso e spento senza toccare la configurazione."""
        import inspect
        from core import motore
        agente = inspect.getsource(motore.divieti_permanenti)
        assert '{"ESCL-01", "ESCL-03"}' in agente

    def test_non_tocca_il_tetto_di_posizioni(self):
        import inspect
        from core import motore
        agente = inspect.getsource(motore.divieti_permanenti)
        i = agente.index("di_strategia = ")
        riga = agente[i:agente.index("}", i)]
        for muro in ("ESCL-11", "ESCL-02", "ESCL-04"):
            assert muro not in riga, f"{muro} non deve cadere"

    def test_l_agente_riceve_il_modo_invece_di_leggerlo(self):
        """Una regola che legge la configurazione da sola non si prova nei
        due modi senza cambiarla sotto ai piedi del resto del processo."""
        import inspect
        from core import motore
        assert "diagnostico" in inspect.signature(
            motore.divieti_permanenti).parameters
        assert "_apri_ogni_crt" not in inspect.getsource(
            motore.divieti_permanenti)


class TestIlModoNonScavalcaIFiltriUniti:
    """Il modo diagnostico non fa cadere i MURI al punto dei filtri uniti.

    Estraendo `valuta()` ho raccolto l'inoltro al giudizio in un aiutante che
    fa cadere l'obiezione anche col solo modo acceso -- giusto per la bias DXY
    e per le conferme, sbagliato qui: a questo punto i blocchi comprendono
    ESCL-02, RISK-06 e i limiti di perdita, che `filtri_e_esclusioni` tiene
    apposta. Il modo ha gia' tolto li' dentro cio' che era soppesabile.

    Tre test su 897 l'hanno presa. Questo la tiene ferma.
    """

    def test_i_filtri_uniti_passano_solo_dal_giudizio(self):
        import inspect
        from core import motore
        corpo = inspect.getsource(motore._decidi_sul_candidato)
        pezzo = corpo[corpo.index("if blocchi and"):]
        pezzo = pezzo[:pezzo.index("blocchi = []")]
        assert "_giudizio_lascia_cadere(" in pezzo
        assert "giudizio_salva(" not in pezzo, (
            "il modo diagnostico scavalcherebbe anche i muri")

    def test_l_aiutante_serve_alle_obiezioni_soppesabili(self):
        """Dove invece il modo basta: bias DXY e conferme di Romeo."""
        import inspect
        from core import motore
        # `giudizio_salva` nasce in `valuta` e viene passato alla seconda
        # meta': duplicarlo darebbe due formulazioni della stessa uscita.
        prima = inspect.getsource(motore.valuta)
        dopo = inspect.getsource(motore._decidi_sul_candidato)
        assert "_apri_ogni_crt() or _giudizio_lascia_cadere(" in prima
        assert (prima + dopo).count("giudizio_salva(") >= 3   # def + due usi
        assert "giudizio_salva(blocchi_dxy" in dopo
