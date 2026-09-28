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
    cartella = tmp_path / "vivo"
    squadra, info = dal_vivo.carica(file, cartella)
    assert info["decidono"] is False
    caso = {a: v[a][0] for a in AGENTI}
    g = dal_vivo.giudica(squadra, caso)
    assert set(g["primo"]) == set(AGENTI) and 0 <= g["fiducia"] <= 1
    testo = dal_vivo.voce(g, 0.5, False)
    assert "Quanto ci crediamo" in testo and "Siamo in prova" in testo
    # Impara da un risultato vero e lo ricorda: ricaricata, la squadra ha gia' imparato.
    prima = dal_vivo.giudica(squadra, caso)["fiducia"]
    for _ in range(30):
        dal_vivo.impara(squadra, cartella, g, -1.0)
    dopo = dal_vivo.giudica(squadra, caso)["fiducia"]
    assert dopo < prima
    ricaricata, _ = dal_vivo.carica(file, cartella)
    assert abs(dal_vivo.giudica(ricaricata, caso)["fiducia"] - dopo) < 1e-6
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
    assert len(senza.colonne("Grilletto")) == 8
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
    assert sq.secondi["Livelli"].w1.shape[0] == 4 + 5          # e nel confronto i giudizi dei 5 colleghi
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
