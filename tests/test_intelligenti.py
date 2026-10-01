"""La squadra riaddestrata da zero sui 17 video di Romeo: entra quando c'e' il setup, tutte le volte e
solo allora; mai senza stop; impara da ogni errore; inventa idee; il Rischio decide da solo."""

from types import SimpleNamespace as NS

from nvm.intelligenti import al_lavoro
from nvm.intelligenti.metodo import Domanda, Metodo
from nvm.intelligenti.squadra import PESO_INIZIALE, PIANO_ROMEO, PUNTATA_INIZIALE, VOLTE_IDEA, Memoria, Squadra, con_stop

OBBLIGATORIE = (("candela 3", "Cacciatore"), ("oltre l'apertura", "Grilletto"), ("Model#1 spesso", "Grilletto"),
                ("key level", "Key level"), ("direzione", "Bias"), ("ora giusta", "Orario"),
                ("50% da prendere", "Livelli"))


def _metodo(mancano=(), confluenze=("SMT", "FVG col Model#1"), **fatti) -> Metodo:
    """Un'occasione: tutte le domande di Romeo dicono si', tranne `mancano`."""
    ob = [Domanda(n, a, "V9 02:43", n not in mancano, f"risposta su {n}") for n, a in OBBLIGATORIE]
    co = [Domanda(n, "Grilletto", "V8 02:04", True, f"c'è {n}") for n in confluenze]
    f = {"strumento": "EURUSD", "coppia": "D1-H1", "verso": "acquisto", "giorno": "martedì", "ora": "03"}
    f.update(fatti)
    return Metodo(ob, co, f)


def _op(stop=1.0950, ingresso=1.1000, tp1=1.1050):
    return NS(stop=stop, ingresso=ingresso, tp1=tp1)


def test_col_setup_di_romeo_si_entra_e_ognuno_dice_la_sua(tmp_path):
    sq = Squadra(tmp_path)
    v = sq.riunione("k1", "EURUSD", _metodo(), 1_700_000_000, op=_op())
    assert v.entra and v.a_piu and v.puntata == PUNTATA_INIZIALE and all(v.lista.values())
    chi = [c for c, _ in v.voci]
    assert chi[:7] == [a for _, a in OBBLIGATORIE] and chi[-2:] == ["Capo", "Rischio"]
    assert all(t.startswith("✅") for _, t in v.voci[:7])
    assert v.voci[-2][1].startswith("Tutte e 7 le regole di Romeo dicono sì. Compriamo EURUSD")
    v2 = sq.riunione("k2", "GBPUSD", _metodo(strumento="GBPUSD", verso="vendita"), 1_700_000_100,
                     op=_op(1.1050, 1.1000, 1.0950))
    assert v2.entra and "Vendiamo GBPUSD" in v2.voci[-2][1]
    sq.salva()
    assert {"k1", "k2"} <= set(Memoria.carica(tmp_path).discusse)


def test_nessun_limite_di_operazioni_al_giorno(tmp_path):
    sq = Squadra(tmp_path)
    prese = [sq.riunione(f"g{i}", "EURUSD", _metodo(), 1_700_000_000 + i, op=_op()).entra for i in range(10)]
    assert all(prese)


def test_se_manca_una_regola_di_romeo_non_si_entra_e_si_dice_cosa_manca(tmp_path):
    sq = Squadra(tmp_path)
    for manca in [n for n, _ in OBBLIGATORIE]:
        v = sq.riunione(f"m {manca}", "EURUSD", _metodo(mancano=(manca,)), 1_700_000_000, op=_op())
        assert not v.entra and not v.a_piu and v.puntata == 0
        assert v.voci[-1][0] == "Capo" and v.voci[-1][1].startswith("Non entriamo. Romeo vuole")
        assert any(t.startswith("❌") for _, t in v.voci)


def test_le_regole_di_romeo_non_si_disimparano_ma_si_controllano(tmp_path):
    sq = Squadra(tmp_path)
    senza = _metodo(mancano=("key level",))
    for i in range(200):
        sq.riunione(f"s{i}", "EURUSD", senza, 1_700_000_000, op=_op())
        lezioni = sq.rifletti(f"s{i}", 2.0 if i % 2 else -1.0, preso=False)
    # Anche se a volte sarebbe andata bene, senza key level non si entra mai.
    assert not sq.riunione("s", "EURUSD", senza, 1_700_000_000, op=_op()).entra
    assert sq.memoria.controprova["key level"][0] == 200
    assert lezioni and lezioni[0]["agente"] == "Key level"
    cambi = sq.riscrivi_manuali()
    assert any("senza «un key level del grafico grande»" in c for _, c, _ in cambi)


def test_ogni_errore_diventa_una_miglioria(tmp_path):
    sq = Squadra(tmp_path)
    v = sq.riunione("p0", "EURUSD", _metodo(), 1_700_000_000, op=_op())
    assert v.entra
    for i in range(1000):
        lezioni = sq.rifletti(f"p{i}", -1.0, preso=True)
        v = sq.riunione(f"p{i + 1}", "EURUSD", _metodo(), 1_700_000_000, op=_op())
        if not v.entra:
            break
    # Sempre perdite con quelle confluenze: ci credono meno, finche' il Capo impara a lasciarle.
    assert not v.entra and v.a_piu, i
    assert "occasioni così finora sono andate male" in v.voci[-1][1]
    assert sq.memoria.peso("SMT") < PESO_INIZIALE
    assert any("ci crederò un po' di meno" in l["lezione"] for l in lezioni)
    assert sq.memoria.rischio["base"] < PUNTATA_INIZIALE
    assert any(l["agente"] == "Rischio" and "puntata base passa da" in l["lezione"] for l in lezioni)
    assert Memoria.carica(tmp_path).peso("SMT") == sq.memoria.peso("SMT")


def test_il_rischio_decide_da_solo_senza_tetti(tmp_path):
    sq = Squadra(tmp_path)
    for i in range(150):
        assert sq.riunione(f"r{i}", "EURUSD", _metodo(), 1_700_000_000, op=_op()).entra
        sq.rifletti(f"r{i}", 2.0, preso=True)
    assert sq.memoria.rischio["base"] > 2 * PUNTATA_INIZIALE


def test_senza_stop_non_si_entra_mai(tmp_path):
    assert con_stop(_op()) and not con_stop(_op(stop=1.1010)) and not con_stop(_op(stop=float("nan")))
    assert not con_stop(NS(stop=None, ingresso=1.1, tp1=1.2))
    v = Squadra(tmp_path).riunione("s", "EURUSD", _metodo(), 1_700_000_000, op=_op(stop=1.1010))
    assert not v.entra and "senza uno stop" in v.voci[-1][1]


def test_inventano_idee_nuove_dagli_errori_che_si_ripetono(tmp_path):
    sq = Squadra(tmp_path)
    for i in range(2 * VOLTE_IDEA + 10):
        for giorno, erre in (("lunedì", -1.0), ("giovedì", 1.5)):
            sq.riunione(f"{giorno}{i}", "EURUSD", _metodo(giorno=giorno), 1_700_000_000, op=_op())
            sq.rifletti(f"{giorno}{i}", erre, preso=False)
    cambi = sq.riscrivi_manuali()
    k = next(k for k in sq.memoria.idee if "giorno=lunedì" in k.split("&"))
    assert sq.memoria.pesi[k] < 0
    assert any("💡 idea nuova" in cosa and "di lunedì" in cosa for _, cosa, _ in cambi)
    assert sq.stima(_metodo(giorno="lunedì")) < sq.stima(_metodo(giorno="giovedì"))


def test_livelli_impara_quale_stop_e_quale_uscita_funzionano(tmp_path):
    sq = Squadra(tmp_path)
    piani = [_op() for _ in range(9)]
    seguire = {"strumento": "EURUSD", "basso": "H1", "scadenza": 0, "piani": [None] * 9}
    assert sq.riunione("a", "EURUSD", _metodo(), 0, piani, da_seguire=seguire).piano == PIANO_ROMEO
    for i in range(30):
        sq.riunione(f"b{i}", "EURUSD", _metodo(), 0, piani, da_seguire=seguire)
        sq.impara_piani(f"b{i}", [-1.0, -1.0, -1.0, 1.0, 0.2, 0.2, 0.1, 0.1, 0.1])
    v = sq.riunione("c", "EURUSD", _metodo(), 0, piani, da_seguire=seguire)
    assert v.piano == 3 and any(chi == "Livelli" and "Stavolta" in t for chi, t in v.voci)


def test_un_ordine_non_partito_conta_come_non_preso(tmp_path):
    sq = Squadra(tmp_path)
    assert sq.riunione("x", "EURUSD", _metodo(), 0, op=_op()).entra
    sq.annulla("x")
    lezioni = sq.rifletti("x", 1.0, preso=False)
    assert any(l["agente"] == "Capo" and "lasciata" in l["lezione"] for l in lezioni)
    assert sq.memoria.rischio["base"] == PUNTATA_INIZIALE


def test_la_memoria_di_prima_si_butta_si_riparte_dai_video(tmp_path):
    (tmp_path / "memoria.json").write_text('{"pesi": {"Orario": {"ore di Romeo": 9}}, "capo": {"prudenza": -5}}',
                                           encoding="utf-8")
    m = Memoria.carica(tmp_path)
    assert m.rischio["base"] == PUNTATA_INIZIALE and m.capo["prudenza"] == 0.0 and not m.pesi


def test_nessuna_ai_esterna():
    import pathlib
    for f in pathlib.Path("nvm/intelligenti").glob("*.py"):
        testo = f.read_text(encoding="utf-8").lower()
        assert "anthropic" not in testo and "openai" not in testo


def test_la_squadra_si_riunisce_sulle_occasioni_della_candela_3(tmp_path):
    from nvm.vivo.giro import giro
    from tests.test_vivo import CapoFinto, ore_finte
    import vivo
    base = ore_finte(giorni=400)
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto())
    assert decisioni and all(d.r.scatto.modello == "candela 3" for d in decisioni)
    sq = Squadra(tmp_path)
    verdetti = al_lavoro.riunioni(sq, decisioni, {"EURUSD": base}, {})
    assert not sq.ultimo_errore and set(verdetti) == {d.chiave for d in decisioni}
    for d in decisioni:
        m = verdetti[d.chiave].metodo
        assert [x.nome for x in m.obbligatorie] == [n for n, _ in OBBLIGATORIE]
        assert all(x.perche for x in m.obbligatorie + m.confluenze)
        # La candela 3, la finta oltre l'apertura e la candela spessa ci sono per costruzione.
        assert all(x.si for x in m.obbligatorie[:3])
        assert verdetti[d.chiave].entra == (m.a_piu and verdetti[d.chiave].puntata > 0)
    al_lavoro.valuta_piani(sq, {"EURUSD": base}, {}, max(d.scadenza for d in decisioni) + 1)
    assert not sq.ultimo_errore and not sq.memoria.da_vedere
    finto = NS(_verdetti=verdetti, _decidono_i_cervelli=False, squadra=sq)
    for d in decisioni:
        assert vivo.Bot._entra(finto, d, None) is (verdetti[d.chiave].entra and verdetti[d.chiave].puntata > 0)


def test_nel_bot_la_squadra_decide_apre_disegna_impara_e_fa_il_fine_settimana(tmp_path, monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    import vivo
    from nvm.agenti.capo import Capo
    from nvm.intelligenti import metodo
    from nvm.vivo import disegni
    from nvm.vivo.giro import giro
    from nvm.vivo.stato import Stato
    from nvm.vivo.telegram import Telegram
    from nvm.vivo.ambiente import Impostazioni
    from tests.test_vivo import CapoFinto, ore_finte
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    vero = metodo.valuta

    def tutto_si(d, ore, quarti=None, gemello=None):
        m = vero(d, ore, quarti, gemello)
        for x in m.obbligatorie:
            x.si = True
        return m
    monkeypatch.setattr(metodo, "valuta", tutto_si)
    base = ore_finte(giorni=400)
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto())[-2:]
    assert decisioni
    mandati, aperte = [], []

    class Esecutore:
        def apri(self, d, conto, vive, pieno=None, parte=None, fiducia_minima=None, riduci=True):
            assert con_stop(d.op)
            aperte.append((pieno, parte, riduci))
            viva = NS(chiave=d.chiave, strumento="EURUSD", verso=d.r.verso.value, tickets=[1], volume=0.1,
                      ingresso=d.op.ingresso, stop=d.op.stop, tp1=d.op.tp1, tp2=d.op.tp2, rischio=pieno * parte * 10000,
                      valuta="EUR", da_sola=pieno * parte, legate=[], pareggio_fatto=False)
            return viva, NS(saltata=None, equipe=False, testo="aperta")

    bot = object.__new__(vivo.Bot)
    bot.tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",)),
                      invia=lambda c, t: mandati.append((c, t)), stampa=lambda _: None)
    bot.terminale = NS(conto=lambda: NS(saldo=10000.0, valuta="EUR", demo=True), simbolo=lambda s: s + ".x", scarto=3)
    bot.esecutore = Esecutore()
    bot.stato = Stato()
    bot.capo = Capo.da_dati(json.loads(Path("nvm/vivo/capo.json").read_text(encoding="utf-8")))
    bot.cervelli, bot.cervelli_info, bot.scelte = None, {}, {"squadra_intelligente": True}
    bot.squadra = al_lavoro.crea(tmp_path, bot.scelte)
    bot.basi, bot.fini, bot._verdetti, bot._da_dire, bot._allarmi = {"EURUSD": base}, {}, {}, [], {}
    bot._lezioni_oggi, bot._diario, bot._prove = [], ThreadPoolExecutor(1), None
    bot.strumenti = ["EURUSD"]
    bot.disegni = disegni.Disegni(tmp_path, tmp_path / "comune")
    bot._decidi(decisioni, int(decisioni[-1].r.quando), 10**12)
    assert len(aperte) == len(decisioni) and all(x > 0 and p == 1.0 and not riduci for x, p, riduci in aperte)
    equipe = [t for c, t in mandati if c == "-2"]
    assert any("Tutte e 7 le regole di Romeo dicono sì" in t for t in equipe)
    assert any("Metto in gioco" in t and "EUR" in t for t in equipe)
    # Sul grafico: la candela 1, il 50%, la finta, il Model#1, l'entrata, lo stop, gli obiettivi.
    csv = (tmp_path / "comune" / disegni.FILE).read_text(encoding="cp1252")
    for parola in ("Candela 1", "Finta della candela 2", "Model#1", "Stop", "Obiettivo 1 (50%)", "Obiettivo 2", "EURUSD.x"):
        assert parola in csv, parola
    # A ogni giro: i CRT guardati, le operazioni aperte e la settimana; e il controllo del programma in MT5.
    bot.terminale.simbolo = lambda s: s + ".x"
    bot._avviso_disegni = 0.0
    bot.aggiorna_disegni(int(decisioni[-1].r.quando))
    assert any(g.startswith("aperta ") or g in bot.disegni.gruppi for g in bot.disegni.gruppi)
    assert any(g.startswith("settimana ") for g in bot.disegni.gruppi)
    bot.controlla_disegni(float(decisioni[-1].r.quando))
    assert any("NvmDisegni" in t and "Start" in t for c, t in mandati if c == "-1")
    s = bot.stato.seguite[0]
    s.esito = {"erre": -1.0, "quando": int(base.t[-1]), "tp1": False, "tp2": False, "uscita": "stop"}
    bot._finita(s, int(base.t[-1]))
    bot._diario.shutdown(wait=True)
    assert s.chiave not in bot.squadra.memoria.discusse
    # La domenica e il sabato di Romeo (V14).
    bot.stato.vive = []
    bot.domenica("2026-S40", int(base.t[-1]))
    assert any("La domenica di Romeo" in t for c, t in mandati if c == "-2")
    assert "Massimo della settimana scorsa" in (tmp_path / "comune" / disegni.FILE).read_text(encoding="cp1252")
    prima = len(mandati)
    bot.riunione("2026-S40", int(base.t[-1]))
    nuovi = [t for _, t in mandati[prima:]]
    assert any("Il sabato di Romeo" in t and "Gli errori di esecuzione" in t for t in nuovi)
    assert any("Revisione della settimana" in t for t in nuovi)
