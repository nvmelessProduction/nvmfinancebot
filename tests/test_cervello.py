"""I cervelli degli agenti (`nvm/cervello/`)."""

import numpy as np

from nvm.cervello.rete import Rete
from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI


def _esempi(n=4000, seme=0):
    rng = np.random.default_rng(seme)
    x = rng.normal(size=(n, 3))
    # Arriva al primo obiettivo quando il primo segnale e' alto e il terzo basso, con rumore.
    y = (x[:, 0] - x[:, 2] + rng.normal(0, 0.7, n) > 0).astype(float)
    return x, y


def test_un_cervello_impara_dagli_esempi_e_ricorda_nei_pesi():
    x, y = _esempi()
    rete = Rete.allena(x[:3000], y[:3000])
    p = rete.probabilita(x[3000:])
    assert np.mean((p > 0.5) == y[3000:]) > 0.8
    copia = Rete.da_dati(rete.come_dati())
    assert np.allclose(copia.logit(x[:5]), rete.logit(x[:5]))


def test_dal_vivo_impara_un_passo_alla_volta():
    x, y = _esempi()
    rete = Rete.allena(x, y)
    caso = np.array([[2.0, 0.0, -2.0]])
    prima = float(rete.logit(caso)[0])
    rete.aggiorna(np.repeat(caso, 50, axis=0), np.zeros(50), passi=20, passo=0.05)
    assert float(rete.logit(caso)[0]) < prima      # ha sbagliato: ci crede meno


def test_la_squadra_giudica_si_confronta_e_il_capo_decide():
    x, y = _esempi(3000)
    rng = np.random.default_rng(1)
    # Ogni agente vede solo un pezzo: due agenti vedono i segnali utili, gli altri rumore.
    v = {a: rng.normal(size=(len(y), 2)) for a in AGENTI}
    v["Grilletto"] = x[:, [0]]
    v["Bias"] = x[:, [2]]
    sq = Squadra.allena({a: m[:2500] for a, m in v.items()}, y[:2500])
    primo, dopo, p = sq.giudica({a: m[2500:] for a, m in v.items()})
    assert set(primo) == set(dopo) == set(AGENTI)
    assert np.mean((p > 0.5) == y[2500:]) > 0.8
    # Dopo il confronto l'Orario, che vede solo rumore, ha imparato ad ascoltare chi vede giusto.
    assert np.corrcoef(dopo["Orario"], y[2500:])[0, 1] > np.corrcoef(primo["Orario"], y[2500:])[0, 1]


def test_dal_vivo_giudicano_si_confrontano_imparano_e_ricordano(tmp_path):
    import json
    from types import SimpleNamespace as NS
    from nvm.cervello import dal_vivo
    rng = np.random.default_rng(2)
    n = 1500
    y = (rng.random(n) < 0.4).astype(float)
    v = {a: rng.normal(size=(n, 3)) + y[:, None] * (0.8 if a == "Orario" else 0.0) for a in AGENTI}
    sq = Squadra.allena(v, y)
    file = tmp_path / "cervelli.json"
    file.write_text(json.dumps({"squadra": sq.come_dati(), "decidono": False, "soglia": 0.5}))
    from nvm.cervello.esperienza import Memoria
    Memoria(v, y, np.ones(n)).salva(tmp_path / dal_vivo.RICORDI)       # i ricordi di scuola da ripassare
    cartella = tmp_path / "vivo"
    squadra, info = dal_vivo.carica(file, cartella)
    assert info["decidono"] is False
    # Un caso su cui la squadra e' sicura che guadagni: poi va male.
    k = int(np.argmax(squadra.giudica({a: v[a][:300] for a in AGENTI})[2]))
    caso = {a: v[a][k] for a in AGENTI}
    g = dal_vivo.giudica(squadra, caso)
    assert set(g["primo"]) == set(AGENTI) and 0 <= g["fiducia"] <= 1
    testo = dal_vivo.voce(g, 0.5, False)
    assert "Quanto ci crediamo" in testo and "Siamo in prova" in testo
    # Impara da un risultato vero e lo ricorda: ricaricata, la squadra ha gia' imparato.
    prima = dal_vivo.giudica(squadra, caso)["fiducia"]
    tenute = 0
    for _ in range(5):
        lezione = dal_vivo.impara(squadra, cartella, g, -1.0, info)
        assert lezione["dopo"] <= lezione["prima"] + 1e-9      # una lezione tenuta o niente: mai peggio
        tenute += lezione["tenuta"]
    # Chi decide resta com'era finche' i fatti non danno ragione a chi impara; chi impara si e' mosso.
    assert abs(dal_vivo.giudica(squadra, caso)["fiducia"] - prima) < 1e-9
    dopo = dal_vivo.giudica(info["memoria"]["impara"], caso)["fiducia"]
    assert tenute >= 1 and dopo < prima
    # Ricaricata riparte da com'era diventata; e senza il salvataggio rivive le esperienze una per una.
    ricaricata, info2 = dal_vivo.carica(file, cartella)
    assert abs(dal_vivo.giudica(info2["memoria"]["impara"], caso)["fiducia"] - dopo) < 1e-6
    assert len(info2["memoria"]["vissute"]) == 5
    (cartella / dal_vivo.VIVI).unlink()
    rivissuta, info3 = dal_vivo.carica(file, cartella)
    assert abs(dal_vivo.giudica(info3["memoria"]["impara"], caso)["fiducia"] - dopo) < 1e-6
    # La gara della sera: cervelli contro Capo sulle occasioni finite.
    s = NS(esito={"erre": 1.5, "quando": 100}, cervelli={"fiducia": 0.7}, presa_dal_capo=False)
    assert "i cervelli ne avrebbero prese 1 (+1,50 volte il rischio), il Capo 0" in dal_vivo.gara([s], 0, 200, 0.5)


def test_livelli_scelgono_il_piano_migliore_fra_quelli_possibili():
    from nvm.cervello import dal_vivo
    from nvm.cervello.piani import PIANI
    from nvm.cervello.rete import ReteValori
    rng = np.random.default_rng(3)
    n = 2000
    v = {a: rng.normal(size=(n, 2)) for a in AGENTI}
    valori = np.tile(np.linspace(-0.5, 0.3, len(PIANI)), (n, 1)) + rng.normal(0, 0.1, (n, len(PIANI)))
    rete = ReteValori.allena(np.hstack([v[a] for a in AGENTI]), valori)
    caso = {a: v[a][0] for a in AGENTI}
    j, stime = dal_vivo.scegli_piano(rete, caso, [object()] * len(PIANI))
    assert j == len(PIANI) - 1
    # L'ultimo piano non si puo' fare: sceglie il migliore fra gli altri.
    j, _ = dal_vivo.scegli_piano(rete, caso, [object()] * (len(PIANI) - 1) + [None])
    assert j == len(PIANI) - 2
    assert "Scelgo" in dal_vivo.voce_livelli(j, stime)


def test_ogni_cervello_puo_cambiare_la_sua_forma():
    from nvm.cervello.genoma import BLOCCHI, Genoma, da_dati, come_dati, modifiche
    from nvm.cervello.viste import dimensioni
    for a, blocchi in BLOCCHI.items():
        assert max(b for _, b in blocchi.values()) == dimensioni()[a]      # i blocchi coprono tutta la vista
    g = Genoma()
    mosse = modifiche("Grilletto", g)
    testi = [t for t, _ in mosse]
    assert "più neuroni (16 → 24)" in testi and "smette di guardare «candele piccole»" in testi
    senza = dict(mosse)["smette di guardare «candele piccole»"]
    assert len(senza.colonne("Grilletto")) == 8 + 13
    assert any(t == "torna a guardare «candele piccole»" for t, _ in modifiche("Grilletto", senza))
    assert da_dati(come_dati({"Grilletto": senza}))["Grilletto"] == senza


def test_una_modifica_resta_solo_se_la_squadra_va_meglio_negli_anni():
    from nvm.cervello.scuola import _passa
    vecchia = (0.01, {a: 0.01 for a in range(2010, 2024)})
    meglio = (0.03, {a: 0.03 for a in range(2010, 2024)})
    fortuna = (0.02, {a: (0.2 if a == 2010 else 0.0) for a in range(2010, 2024)})
    assert _passa(meglio, vecchia)[0] and not _passa(fortuna, vecchia)[0]


def test_la_squadra_si_allena_con_la_forma_di_ognuno():
    from nvm.cervello.genoma import Genoma
    x, y = _esempi(1500)
    rng = np.random.default_rng(4)
    v = {a: rng.normal(size=(len(y), 3)) for a in AGENTI}
    v["Livelli"] = np.c_[x[:, [0]], rng.normal(size=(len(y), 5))]
    genomi = {a: Genoma() for a in AGENTI}
    genomi["Livelli"] = Genoma(neuroni=8, freno=1e-2, spenti=("stop",))      # guarda solo obiettivi e costi
    sq = Squadra.allena(v, y, genomi=genomi)
    assert sq.primi["Livelli"].w1.shape == (4, 8) and sq.primi["Livelli"].penalita == 1e-2
    assert sq.secondi["Livelli"].w1.shape[0] == 4 + len(AGENTI) - 1      # e nel confronto i giudizi dei colleghi
    copia = Squadra.da_dati(sq.come_dati())
    caso = {a: m[:3] for a, m in v.items()}
    assert np.allclose(copia.giudica(caso)[2], sq.giudica(caso)[2])


def test_la_sera_si_vede_perche_i_cervelli_sono_stati_fermi():
    from types import SimpleNamespace as NS
    from nvm.cervello import dal_vivo
    seguite = [NS(cervelli={"fiducia": 0.58}, quando=100, strumento="EURUSD", verso="long"),
               NS(cervelli={"fiducia": 0.41}, quando=150, strumento="GBPUSD", verso="short")]
    testo = dal_vivo.la_migliore(seguite, 0, 200, 0.25)
    assert "EURUSD in acquisto, ci credevano 58 su 100; per rischiare ne serve almeno 62: non abbastanza" in testo


def test_occhi_nuovi_in_fondo_non_rompono_i_cervelli_nati_prima():
    rng = np.random.default_rng(5)
    n = 800
    y = (rng.random(n) < 0.5).astype(float)
    v = {a: rng.normal(size=(n, 3)) + y[:, None] * 0.5 for a in AGENTI}
    sq = Squadra.allena(v, y)
    caso = {a: v[a][:5] for a in AGENTI}
    _, _, p = sq.giudica(caso)
    # Una vista piu' lunga (occhi nuovi in fondo): i cervelli guardano solo i numeri che conoscono.
    lunga = dict(caso, Grilletto=np.c_[caso["Grilletto"], rng.normal(size=(5, 4))])
    assert np.allclose(sq.giudica(lunga)[2], p)
    # Un esempio salvato prima, piu' corto: quello che manca vale zero.
    corta = dict(caso, Grilletto=caso["Grilletto"][:, :2])
    zero = dict(caso, Grilletto=np.c_[caso["Grilletto"][:, :2], np.zeros(5)])
    assert np.allclose(sq.giudica(corta)[2], sq.giudica(zero)[2])
    assert sq.larghezza("Grilletto") == 3


def test_vera_rottura_di_struttura_e_tempo_della_finta():
    from types import SimpleNamespace as NS
    from nvm.cervello.viste import _rottura, _tempo_della_finta
    from nvm.dati.candele import Candele
    from nvm.tempo import TF

    def fatte(tf, passo, righe, t0=1_704_700_000):
        inizi = np.arange(len(righe), dtype=np.int64) * passo + t0
        p = np.array(righe, float)
        return Candele("EURUSD", tf, inizi, inizi + passo, p, p.copy(), np.ones(len(righe)))

    # Un minimo, un massimo, un minimo piu' basso (la manipolazione), poi una chiusura sopra quel massimo.
    righe = [(1.1000, 1.1010, 1.0990, 1.1005), (1.1005, 1.1008, 1.0980, 1.0985), (1.0985, 1.1050, 1.0984, 1.1040),
             (1.1040, 1.1042, 1.0990, 1.0995), (1.0995, 1.0998, 1.0950, 1.0960), (1.0960, 1.1030, 1.0958, 1.1020),
             (1.1020, 1.1070, 1.1015, 1.1060)]
    basse = fatte(TF.M15, 900, righe)
    da = int(basse.inizio[3])
    assert np.allclose(_rottura(basse, da, +1, 0.01), (1.0, 0.1))
    senza = fatte(TF.M15, 900, righe[:-1])
    assert np.allclose(_rottura(senza, da, +1, 0.01), (0.0, -0.3))
    # Per la vendita e' lo specchio.
    specchio = fatte(TF.M15, 900, [(2.2 - o, 2.2 - l, 2.2 - h, 2.2 - c) for o, h, l, c in righe])
    assert np.allclose(_rottura(specchio, da, -1, 0.01), (1.0, 0.1))

    # La finta fatta a 3,5 ore della candela di 4 ore: tardi; si entra nella candela dopo.
    t0 = 1_704_700_000
    alte = fatte(TF.H4, 14400, [(1.1, 1.11, 1.09, 1.1)])
    crt = NS(estremo_istanti=np.array([t0 + 3600, t0 + 12600, t0 + 16200]), estremo_valori=np.array([1.2, 1.3, 1.3]))
    frazione, dopo = _tempo_della_finta(crt, alte, t0 + 18000)
    assert abs(frazione - 12600 / 14400) < 1e-9 and dopo == 1.0
    # L'estremo nella candela ancora aperta: si entra nella stessa candela.
    crt = NS(estremo_istanti=np.array([t0 + 3600, t0 + 16200]), estremo_valori=np.array([1.2, 1.3]))
    frazione, dopo = _tempo_della_finta(crt, alte, t0 + 18000)
    assert abs(frazione - 1800 / 14400) < 1e-9 and dopo == 0.0


def test_una_sfidante_migliore_prende_il_posto_dal_vivo(tmp_path):
    import json
    from nvm.cervello import dal_vivo, esperienza
    rng = np.random.default_rng(11)
    n = 1600
    x = rng.normal(size=(n, 3))
    y = (x[:, 0] + rng.normal(0, 0.5, n) > 0).astype(float)
    v = {a: x.copy() for a in AGENTI}
    scuola = {a: m[:1500] for a, m in v.items()}
    squadra = Squadra.allena(scuola, y[:1500])
    altra = Squadra.allena({a: m[:, ::-1] for a, m in scuola.items()}, y[:1500])
    file = tmp_path / "cervelli.json"
    file.write_text(json.dumps({"squadra": squadra.come_dati(), "decidono": False, "soglia": 0.5,
                                "sfidanti": [{"agente": "Grilletto", "modifica": "smette di guardare «x»",
                                              "genomi": {"Grilletto": {"neuroni": 8, "freno": 0.01, "spenti": []}},
                                              "squadra": altra.come_dati()}]}))
    esperienza.Memoria(scuola, y[:1500], np.ones(1500)).salva(tmp_path / dal_vivo.RICORDI)
    cartella = tmp_path / "vivo"
    squadra, info = dal_vivo.carica(file, cartella)
    # Le sfidanti giudicano e imparano a ogni esperienza, e si ricordano chi ha sbagliato meno.
    for k in range(1500, 1520):
        dal_vivo.impara(squadra, cartella, dal_vivo.giudica(squadra, {a: v[a][k] for a in AGENTI}), 1.0 if y[k] else -1.0, info)
    assert len(info["sfidanti"][0]["confronto"]) == 20
    ricaricata, info2 = dal_vivo.carica(file, cartella)
    assert info2["sfidanti"][0]["confronto"] == info["sfidanti"][0]["confronto"]
    # Quando le esperienze dicono chiaramente che la sfidante sbaglia meno, prende il posto.
    s = info["sfidanti"][0]
    s["confronto"] = list(rng.normal(0.05, 0.1, dal_vivo.SFIDA_MINIMO + 20))
    caso = {a: v[a][1520:] for a in AGENTI}
    p_sfidante = s["squadra"].giudica(caso)[2]
    cambio = dal_vivo._chi_vince(squadra, info)
    assert cambio and cambio["agente"] == "Grilletto" and cambio["genoma"]["neuroni"] == 8
    assert info["sfidanti"] == [] and len(info["cambi"]) == 1 and np.allclose(squadra.giudica(caso)[2], p_sfidante)
    assert "ha cambiato se stesso" in dal_vivo.voce_del_cambio(cambio)
    # Con una differenza che e' solo caso, nessuno cambia.
    info = {"sfidanti": [{"agente": "Bias", "modifica": "m", "genomi": None, "squadra": altra,
                          "confronto": list(rng.normal(0.0, 0.1, 400))}]}
    assert dal_vivo._chi_vince(squadra, info) is None


def test_la_palestra_tiene_i_cambi_fatti_dal_vivo(tmp_path):
    import json
    from capo import cambi_dal_vivo
    registro = tmp_path / "registro.jsonl"
    nuovo = {"neuroni": 24, "freno": 0.001, "spenti": []}
    registro.write_text(json.dumps({"evento": "lezione", "prima": 0.5}) + "\n" +
                        json.dumps({"evento": "cambio", "agente": "Bias", "modifica": "più neuroni (16 → 24)",
                                    "esperienze": 120, "meglio": 0.01, "genoma": nuovo}) + "\n")
    memoria = cambi_dal_vivo({"provate": []}, registro)
    assert memoria["attuali"]["Bias"] == nuovo and memoria["cambi_dal_vivo"] == 1
    assert cambi_dal_vivo(memoria, registro) == memoria          # lo stesso cambio non si applica due volte


def test_i_cervelli_dicono_cosa_hanno_imparato():
    from nvm.cervello.dal_vivo import voce_della_lezione
    assert "adesso siamo al 64%" in voce_della_lezione({"prima": 0.8, "dopo": 0.64, "tenuta": True}, -1.0)
    assert "è andata bene" in voce_della_lezione({"prima": 0.7, "dopo": 0.702, "tenuta": True}, 2.0)
    assert "solo come esperienza" in voce_della_lezione({"prima": 0.8, "dopo": 0.8, "tenuta": False}, -1.0)


def test_chi_impara_prende_il_comando_solo_quando_i_fatti_gli_danno_ragione():
    from nvm.cervello import dal_vivo
    rng = np.random.default_rng(5)
    x = rng.normal(size=(900, 3))
    y = (x[:, 0] > 0).astype(float)
    v = {a: x.copy() for a in AGENTI}
    buona = Squadra.allena(v, y)
    confusa = Squadra.allena(v, rng.permutation(y))
    caso = {a: v[a][:50] for a in AGENTI}
    # Chi impara sbaglia chiaramente meno di chi comanda: prende il comando.
    comando = Squadra.da_dati(confusa.come_dati())
    m = {"impara": buona, "ritmo": 1.0, "contro_scuola": list(rng.normal(0.05, 0.1, dal_vivo.PRUDENZA))}
    assert dal_vivo._chi_comanda(comando, m) == "promozione"
    assert np.allclose(comando.giudica(caso)[2], buona.giudica(caso)[2]) and m["contro_scuola"] == []
    # Chi impara sbaglia chiaramente di piu': torna come chi comanda e impara piu' piano.
    comando = Squadra.da_dati(buona.come_dati())
    m = {"impara": confusa, "ritmo": 1.0, "contro_scuola": list(rng.normal(-0.05, 0.1, dal_vivo.PRUDENZA))}
    assert dal_vivo._chi_comanda(comando, m) == "prudenza"
    assert m["ritmo"] == 0.5 and np.allclose(m["impara"].giudica(caso)[2], buona.giudica(caso)[2])
    assert "impariamo più piano" in dal_vivo.voce_della_prudenza({"ritmo": 0.5})
    assert "Da adesso decidiamo così" in dal_vivo.voce_della_promozione({"esperienze": 150})
    # Una differenza che e' solo caso non cambia niente.
    m = {"impara": confusa, "ritmo": 1.0, "contro_scuola": list(rng.normal(0.0, 0.1, dal_vivo.PRUDENZA))}
    assert dal_vivo._chi_comanda(comando, m) is None
