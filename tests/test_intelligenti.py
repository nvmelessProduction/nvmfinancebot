"""La squadra di agenti intelligenti, con una mente finta (nessuna rete, nessuna chiave)."""

import json

from nvm.intelligenti.mente import Mente, MenteFinta
from nvm.intelligenti.squadra import DOMANDE, SPECIALISTI, Memoria, Squadra


def _voto(voto, fiducia=70, piano=-1):
    return {"voto": voto, "fiducia": fiducia, "regole": ["turtle soup di un CRT"], "ragionamento": f"voto {voto}",
            "piano": piano}


def _capo(entra=True, tutte=True, piano=4):
    lista = {d: True for d in DOMANDE}
    if not tutte:
        lista["key_level"] = False
    return {"entra": entra, "lista_di_romeo": lista, "piano": piano, "fiducia": 80, "discorso": "entriamo"}


def _mente(voti, capo, puntata=0.6, confronto=None):
    def specialista(t):
        for a in SPECIALISTI:
            if t.startswith(f"Sei {a},"):
                return voti[a]
        return None
    return MenteFinta({
        "Primo giro della squadra": confronto or (lambda t: {"voto": "entra", "fiducia": 60, "cambio": True,
                                                             "risposta": "avete ragione"}),
        "Sei il Capo": capo,
        "Sei il Rischio": {"puntata": puntata, "motivo": "operazione pulita"},
        "Leggi il dossier": specialista,
    })


def test_tutti_d_accordo_niente_confronto_e_si_entra(tmp_path):
    m = _mente({a: _voto("entra") for a in SPECIALISTI}, _capo())
    v = Squadra(m, tmp_path).riunione("k1", "EURUSD", "DOSSIER")
    assert v.entra and v.piano == 4 and v.puntata == 0.6
    assert not any("Primo giro della squadra" in c for c in m.chiamate)
    assert [c for c, _ in v.voci][-2:] == ["Capo", "Rischio"]
    # La decisione resta scritta, per le lezioni.
    assert "k1" in Memoria.carica(tmp_path).discusse


def test_se_non_sono_d_accordo_si_confrontano(tmp_path):
    voti = {a: _voto("entra" if i % 2 else "non entrare") for i, a in enumerate(SPECIALISTI)}
    m = _mente(voti, _capo())
    v = Squadra(m, tmp_path).riunione("k2", "EURUSD", "DOSSIER")
    assert sum("Primo giro della squadra" in c for c in m.chiamate) == len(SPECIALISTI)
    assert all("secondo" in v.pareri[a] for a in SPECIALISTI)


def test_un_solo_no_nella_lista_di_romeo_e_non_si_entra(tmp_path):
    m = _mente({a: _voto("entra") for a in SPECIALISTI}, _capo(entra=True, tutte=False))
    v = Squadra(m, tmp_path).riunione("k3", "EURUSD", "DOSSIER")
    assert not v.entra and v.puntata == 0.0
    assert not any("Sei il Rischio" in c for c in m.chiamate)


def test_la_puntata_non_supera_il_massimo(tmp_path):
    m = _mente({a: _voto("entra") for a in SPECIALISTI}, _capo(), puntata=7.0)
    assert Squadra(m, tmp_path).riunione("k4", "EURUSD", "DOSSIER").puntata == 1.0


def test_senza_risposte_decide_il_sistema_di_prima(tmp_path):
    assert Squadra(MenteFinta({}), tmp_path).riunione("k5", "EURUSD", "DOSSIER") is None


def test_dopo_l_operazione_le_lezioni_entrano_nei_pensieri(tmp_path):
    m = _mente({a: _voto("entra") for a in SPECIALISTI}, _capo())
    sq = Squadra(m, tmp_path)
    sq.riunione("k6", "GBPUSD", "DOSSIER")
    m.risposte["Revisione dell'occasione"] = {"lezioni": [
        {"agente": "Key level", "lezione": "sotto c'era un minimo intatto: il fondo era finto", "regola_di_romeo": "7"},
        {"agente": "Sconosciuto", "lezione": "x", "regola_di_romeo": "x"}]}
    fatte = sq.rifletti("k6", -1.0, preso=True)
    assert [l["agente"] for l in fatte] == ["Key level"]
    assert "k6" not in sq.memoria.discusse
    assert "fondo era finto" in Memoria.carica(tmp_path).ricordi("Key level", "GBPUSD")
    # Alla riunione dopo, Key level rilegge la sua lezione.
    sq.riunione("k7", "GBPUSD", "DOSSIER")
    assert any(c.startswith("Sei Key level,") and "fondo era finto" in c for c in m.chiamate)


def test_ogni_settimana_riscrivono_il_loro_manuale(tmp_path):
    sq = Squadra(MenteFinta({"revisione del fine settimana": {
        "manuale": "Guardo sempre i minimi intatti sotto la manipolazione." * 100,
        "cosa_ho_cambiato": "aggiunta la regola del fondo finto", "proposta_al_sistema": "mostrare i minimi intatti"}}),
        tmp_path)
    sq.memoria.impara("Key level", {"lezione": "fondo finto", "esito": "-1 R"})
    cambi = sq.riscrivi_manuali()
    assert cambi == [("Key level", "aggiunta la regola del fondo finto", "mostrare i minimi intatti")]
    mem = Memoria.carica(tmp_path)
    assert len(mem.manuali["Key level"]) == 1500 and mem.proposte[0]["agente"] == "Key level"
    assert mem.storia_manuali[0]["prima"] == ""


def test_la_chiave_viene_solo_dal_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not Mente.dal_env(tmp_path).disponibile()
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=abc\n", encoding="utf-8")
    m = Mente.dal_env(tmp_path)
    assert m.chiave == "abc" and "abc" not in repr(m)


def test_la_squadra_si_riunisce_sulle_occasioni_vere_del_giro(tmp_path):
    from types import SimpleNamespace as NS
    from nvm.intelligenti import al_lavoro
    from nvm.vivo.giro import giro
    from tests.test_vivo import CapoFinto, ore_finte
    import vivo
    base = ore_finte()
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto())[:3]
    assert decisioni
    voti = {a: _voto("entra") for a in SPECIALISTI}
    m = _mente(voti, _capo(piano=1), puntata=0.4)
    sq = Squadra(m, tmp_path)
    conto = NS(saldo=10000.0, valuta="EUR")
    verdetti = al_lavoro.riunioni(sq, decisioni, {"EURUSD": base}, {}, {}, conto, [], filtro_romeo=False)
    assert set(verdetti) == {d.chiave for d in decisioni}
    # Ognuno ha letto il dossier con le candele vere e l'ora di New York.
    letti = [pezzi[0] for pezzi in m.messaggi if pezzi[-1].startswith("Sei ")]
    assert letti and all("=== OCCASIONE ===" in t and "Candela 1 (il range)" in t and "(New York)" in t for t in letti)
    assert len(sq.memoria.discusse) == len(decisioni)
    # Nel bot: decide il verdetto della squadra, col piano scelto dal Capo.
    finto = NS(_verdetti=verdetti, _decidono_i_cervelli=False)
    d = decisioni[0]
    assert vivo.Bot._entra(finto, d, None) is True
    scelto = vivo.Bot._con_piano(finto, d, None)
    assert scelto.op is d.piani[1]
    voci = al_lavoro.voci(verdetti[d.chiave])
    assert [v.chi for v in voci][-2:] == ["Capo", "Rischio"]


def test_senza_key_level_o_fuori_orario_non_si_riunisce_nemmeno(tmp_path):
    from types import SimpleNamespace as NS
    from nvm.agenti.conferme import AllaRomeo, KeyLevel
    from nvm.intelligenti import al_lavoro
    kl = KeyLevel(massimo=True, rejection_block=False, fvg=False)
    ore = AllaRomeo(londra=False, new_york=True, annidato=False, sconto=None)
    assert al_lavoro.manca_a_romeo(NS(key_level=kl, alla_romeo=ore)) == ""
    assert "key level" in al_lavoro.manca_a_romeo(NS(key_level=None, alla_romeo=ore))
    fuori = AllaRomeo(londra=False, new_york=False, annidato=False, sconto=None)
    assert "ore" in al_lavoro.manca_a_romeo(NS(key_level=kl, alla_romeo=fuori))
    m = MenteFinta({})
    d = NS(chiave="k", key_level=None, alla_romeo=ore, r=NS(strumento="EURUSD"))
    v = al_lavoro.riunioni(Squadra(m, tmp_path), [d], {}, {}, {})
    assert not v["k"].entra and v["k"].chiamate == 0 and m.chiamate == []
