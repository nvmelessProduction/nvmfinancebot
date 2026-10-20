"""La squadra col metodo delle foto del proprietario: entra quando c'e' il setup, tutte le volte e solo
allora; mai senza stop; ogni agente impara il suo giudizio dal vivo; si confrontano e cambiano idea; il Capo
lascia un'A+ solo con le prove; i risultati veri contano piu' di quelli sulla carta."""

from types import SimpleNamespace as NS

from nvm.intelligenti import al_lavoro
from nvm.intelligenti.metodo import Domanda, Metodo
from nvm.intelligenti.pareri import VOTANO, Parere
from nvm.intelligenti.squadra import (ESPERIENZA_MINIMA, MINIMO_SIMILI, PIANO_ROMEO, PUNTATA_INIZIALE, SOGLIA_PUNTI,
                                      VOLTE_IDEA, Memoria, Squadra, con_stop)

OBBLIGATORIE = (("CRT", "Cacciatore"), ("key level", "Key level"), ("direzione", "Bias"))


def _metodo(mancano=(), confluenze=("DXY a favore", "dentro un gap a favore"), **fatti) -> Metodo:
    """Un'occasione: tutte le domande del metodo dicono si', tranne `mancano`."""
    ob = [Domanda(n, a, "le foto", n not in mancano, f"risposta su {n}") for n, a in OBBLIGATORIE]
    co = [Domanda(n, "Gap", "le foto", True, f"c'è {n}") for n in confluenze]
    f = {"strumento": "EURUSD", "coppia": "D1", "verso": "acquisto", "giorno": "martedì", "ora": "03",
         "modello": "apertura N3"}
    f.update(fatti)
    numeri = {"Gap": {"dentro un gap a favore": float("dentro un gap a favore" in confluenze), "fase 2": 0.0},
              "DXY": {"DXY a favore": float("DXY a favore" in confluenze)},
              "Orario": {"Londra": 1.0}, "Livelli": {"guadagno al TP1": 0.3},
              "Bias": {"sopra a favore": 0.5}, "Key level": {"preso D": 1.0}, "Cacciatore": {"CRT giornaliero": 1.0},
              "Grilletto": {"finta oltre il range": 0.2}}
    return Metodo(ob, co, f, numeri)


def _op(stop=1.0950, ingresso=1.1000, tp1=1.1050):
    return NS(stop=stop, ingresso=ingresso, tp1=tp1, tp2=tp1, parziale=0.5)


def test_col_setup_delle_foto_si_entra_e_ognuno_dice_la_sua(tmp_path):
    sq = Squadra(tmp_path)
    v = sq.riunione("k1", "EURUSD", _metodo(), 1_700_000_000, op=_op())
    assert v.entra and v.a_piu and v.puntata == PUNTATA_INIZIALE and all(v.lista.values())
    chi = [c for c, _ in v.voci]
    assert chi[:3] == [a for _, a in OBBLIGATORIE] and chi[-2:] == ["Capo", "Rischio"]
    assert all(t.startswith("✅") for _, t in v.voci[:3])
    # Senza esperienza lo dicono, invece di inventarsi un giudizio.
    assert all("non ho ancora un giudizio mio" in t for _, t in v.voci[:3])
    assert v.voci[-2][1].startswith("Tutte e 3 le regole del metodo dicono sì. Compriamo EURUSD")
    assert "casi simili dal vivo non ne abbiamo ancora" in v.voci[-2][1]
    v2 = sq.riunione("k2", "GBPUSD", _metodo(strumento="GBPUSD", verso="vendita", modello="dal DXY"),
                     1_700_000_100, op=_op(1.1050, 1.1000, 1.0950))
    assert v2.entra and "Vendiamo GBPUSD (il setup l'ha fatto il DXY)" in v2.voci[-2][1]
    sq.salva()
    assert {"k1", "k2"} <= set(Memoria.carica(tmp_path).discusse)


def test_nessun_limite_di_operazioni_al_giorno(tmp_path):
    sq = Squadra(tmp_path)
    prese = [sq.riunione(f"g{i}", "EURUSD", _metodo(), 1_700_000_000 + i, op=_op()).entra for i in range(10)]
    assert all(prese)


def test_se_manca_una_regola_non_si_entra_e_si_dice_cosa_manca(tmp_path):
    sq = Squadra(tmp_path)
    for manca in [n for n, _ in OBBLIGATORIE]:
        v = sq.riunione(f"m {manca}", "EURUSD", _metodo(mancano=(manca,)), 1_700_000_000, op=_op())
        assert not v.entra and not v.a_piu and v.puntata == 0
        assert v.voci[-1][0] == "Capo" and v.voci[-1][1].startswith("Non entriamo. Il metodo vuole")
        assert any(t.startswith("❌") for _, t in v.voci)


def test_le_regole_non_si_disimparano_ma_si_controllano(tmp_path):
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


def test_ogni_agente_impara_il_suo_giudizio_dal_vivo(tmp_path):
    sq = Squadra(tmp_path)
    # Dal vivo: dentro un gap a favore va quasi sempre bene, fuori quasi sempre male.
    for i in range(300):
        con = i % 2 == 0
        m = _metodo(confluenze=("dentro un gap a favore",) if con else ())
        sq.riunione(f"a{i}", "EURUSD", m, 0, op=_op())
        sq.rifletti(f"a{i}", 1.5 if (con and i % 10) else -1.0, preso=False)
    g_con = sq.giudizi(_metodo(confluenze=("dentro un gap a favore",)))["Gap"]
    g_senza = sq.giudizi(_metodo(confluenze=()))["Gap"]
    assert g_con["prima"] > 0.6 > 0.4 > g_senza["prima"]
    assert sq.memoria.agenti["Gap"]["n"] == 300
    # E lo dice in equipe, coi numeri veri (il Gap parla quando c'e' una sua confluenza: con la regola del Bias).
    v = sq.riunione("dopo", "EURUSD", _metodo(confluenze=("dentro un gap a favore",)), 0, op=_op())
    assert any("Dai 300 casi che ho visto dal vivo" in t for _, t in v.voci)
    # Il Capo ha imparato a fidarsi del Gap piu' di chi non vedeva differenze.
    assert sq.memoria.capo["fiducia"]["Gap"] > sq.memoria.capo["fiducia"]["Orario"]


def test_si_confrontano_e_cambiano_idea(tmp_path):
    sq = Squadra(tmp_path)
    g = sq.giudizi(_metodo(confluenze=("DXY a favore",)))
    # Il Bias sente il DXY: *"è un grafico fondamentale"* (il proprietario, 06/10/2026).
    assert g["Bias"]["dopo"] > g["Bias"]["prima"]
    assert any(da == "DXY" and cosa == "DXY a favore" for da, cosa, _ in g["Bias"]["sentiti"])
    v = sq.riunione("c", "EURUSD", _metodo(confluenze=("DXY a favore",)), 0, op=_op())
    assert "sentito DXY («DXY a favore») passo al" in dict(v.voci)["Bias"]
    # Se sentire il DXY non aiuta il Bias, il suo peso scende da solo.
    prima = sq._prior("Bias", "DXY: DXY a favore")
    for i in range(300):
        sq.riunione(f"x{i}", "EURUSD", _metodo(confluenze=("DXY a favore",)), 0, op=_op())
        sq.rifletti(f"x{i}", -1.0, preso=False)
    assert sq.memoria.agenti["Bias"]["pesi"]["DXY: DXY a favore"] < prima


def test_il_capo_lascia_un_a_piu_solo_con_le_prove(tmp_path):
    sq = Squadra(tmp_path)
    # Poche perdite non bastano: si entra lo stesso (il proprietario: "se c'e' setup bene").
    for i in range(MINIMO_SIMILI - 1):
        assert sq.riunione(f"p{i}", "EURUSD", _metodo(), 0, op=_op()).entra
        sq.rifletti(f"p{i}", -1.0, preso=True)
    assert sq.riunione("ancora", "EURUSD", _metodo(), 0, op=_op()).entra
    sq.rifletti("ancora", -1.0, preso=True)
    # Con abbastanza casi simili tutti in perdita, il Capo la lascia: "lose, journal, avoid" (V9 23:30).
    for i in range(10):
        sq.riunione(f"q{i}", "EURUSD", _metodo(), 0, op=_op())
        sq.rifletti(f"q{i}", -1.0 + 0.01 * i, preso=False)
    v = sq.riunione("lasciata", "EURUSD", _metodo(), 0, op=_op())
    assert not v.entra and v.a_piu and "lose, journal, avoid" in v.voci[-1][1] and "casi simili" in v.voci[-1][1]
    # Su un altro grafico o un'altra entrata i casi non sono simili: si entra.
    assert sq.riunione("altra", "EURUSD", _metodo(coppia="W1"), 0, op=_op()).entra
    assert sq.memoria.rischio["base"] < PUNTATA_INIZIALE


def test_il_risultato_vero_del_broker_conta_piu_di_quello_sulla_carta(tmp_path):
    sq = Squadra(tmp_path)
    sq.riunione("v", "EURUSD", _metodo(), 0, op=_op())
    sq.vero("v", 2.0)
    lezioni = sq.rifletti("v", -1.0, preso=True)
    assert sq.memoria.a_piu == [1, 2.0, 1] and sq.memoria.casi[-1]["reale"] and sq.memoria.casi[-1]["erre"] == 2.0
    assert any("risultato vero dal broker" in l["lezione"] for l in lezioni)
    assert sq.memoria.rischio["base"] > PUNTATA_INIZIALE


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
    assert sq.memoria.pesi_idee[k] < 0
    assert any("💡 idea nuova" in cosa and "di lunedì" in cosa for _, cosa, _ in cambi)
    assert sq.stima(_metodo(giorno="lunedì")) < sq.stima(_metodo(giorno="giovedì"))


def test_livelli_sceglie_fra_i_piani(tmp_path):
    sq = Squadra(tmp_path)
    piani = [_op() for _ in range(3)]
    seguire = {"strumento": "EURUSD", "basso": "H1", "scadenza": 0, "piani": [None] * 3}
    assert sq.riunione("a", "EURUSD", _metodo(), 0, piani, da_seguire=seguire).piano == PIANO_ROMEO
    for i in range(30):
        sq.riunione(f"b{i}", "EURUSD", _metodo(), 0, piani, da_seguire=seguire)
        sq.impara_piani(f"b{i}", [1.0, 0.2, 0.1])
    v = sq.riunione("c", "EURUSD", _metodo(), 0, piani, da_seguire=seguire)
    assert v.piano == 0 and any(chi == "Livelli" and "chiudo tutto al TP1" in t for chi, t in v.voci)
    # Su un'altra entrata Livelli non ha ancora visto niente: resta il piano delle foto.
    assert sq.riunione("d", "EURUSD", _metodo(modello="dal DXY"), 0, piani, da_seguire=seguire).piano == PIANO_ROMEO


def test_un_ordine_non_partito_conta_come_non_preso(tmp_path):
    sq = Squadra(tmp_path)
    assert sq.riunione("x", "EURUSD", _metodo(), 0, op=_op()).entra
    sq.annulla("x")
    lezioni = sq.rifletti("x", 1.0, preso=False)
    assert any(l["agente"] == "Capo" and "lasciata" in l["lezione"] for l in lezioni)
    assert sq.memoria.rischio["base"] == PUNTATA_INIZIALE


def test_la_memoria_di_prima_si_butta(tmp_path):
    (tmp_path / "memoria.json").write_text('{"versione": "video-2", "capo": {"prudenza": -5}}', encoding="utf-8")
    m = Memoria.carica(tmp_path)
    assert m.rischio["base"] == PUNTATA_INIZIALE and all(g["n"] == 0 for g in m.agenti.values())


def test_nessuna_ai_esterna():
    import pathlib
    for f in pathlib.Path("nvm/intelligenti").glob("*.py"):
        testo = f.read_text(encoding="utf-8").lower()
        assert "anthropic" not in testo and "openai" not in testo


def _dxy_specchio(base):
    """Il DXY che va al contrario di EURUSD: dal 20/10/2026 su EURUSD si entra solo coi suoi setup."""
    from tests.test_foto import _ore
    righe = [(int(t), *(float(x) * base.punto for x in b)) for t, b in zip(base.t, base.bid)]
    return _ore([(t, 100 / o, 100 / l, 100 / h, 100 / c) for t, o, h, l, c in righe], "DXY", spread=0.0)


def test_la_squadra_si_riunisce_sulle_occasioni_delle_foto(tmp_path):
    from nvm.vivo.giro import giro
    from nvm.intelligenti.squadra import AGENTI
    from tests.test_vivo import CapoFinto, ore_finte
    import vivo
    base = ore_finte(giorni=400)
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto(),
                     gemelli={"EURUSD": base, "DXY": _dxy_specchio(base)})
    assert decisioni and all(d.foto and d.r.scatto.modello == "dal DXY" for d in decisioni)
    assert all(d.piani_romeo is not None and len(d.piani_romeo) == 3 for d in decisioni)
    # Si entra all'apertura della candela 3, con lo stop oltre la candela 2 e il TP1 all'altro lato del range.
    for d in decisioni:
        s = d.foto["setup"]
        assert d.r.quando == s.n3_inizio and d.op.stop == s.stop and d.op.tp1 == s.tp1
        assert (s.stop > s.n2_alto - 1e-9) if s.short else (s.stop <= s.n2_basso + 1e-9)
    sq = Squadra(tmp_path)
    verdetti = al_lavoro.riunioni(sq, decisioni, {"EURUSD": base}, {})
    assert not sq.ultimo_errore and set(verdetti) == {d.chiave for d in decisioni}
    for d in decisioni:
        m = verdetti[d.chiave].metodo
        assert [x.nome for x in m.obbligatorie] == [n for n, _ in OBBLIGATORIE]
        assert all(x.perche for x in m.obbligatorie + m.confluenze)
        # Il CRT c'e' per costruzione.
        assert m.obbligatorie[0].si
        assert set(m.numeri) == set(AGENTI)
        v = verdetti[d.chiave]
        # Entra con tutte le regole del metodo, senza un no delle regole, se il Capo la sceglie nel giro: dal
        # 12/10/2026 i punti della squadra sono un parere, non bloccano.
        veto = v.pareri.get("Capo", {}).get("veto", "")
        assert v.entra == (m.a_piu and v.puntata > 0 and not veto and not v.lasciata)
        assert [x.agente for x in v.pareri_squadra] == list(VOTANO)
    assert any(verdetti[d.chiave].entra for d in decisioni) and not all(verdetti[d.chiave].entra for d in decisioni)
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
    vero = metodo.valuta_foto

    def tutto_si(d):
        m = vero(d)
        for x in m.obbligatorie:
            x.si = True
        return m
    monkeypatch.setattr(metodo, "valuta_foto", tutto_si)
    # La squadra e' d'accordo (qui si prova il bot, non i voti: quelli sono in `test_pareri.py`).
    monkeypatch.setattr(al_lavoro.P, "tutti", lambda d, ctx, prev, *altro: [Parere(a, 1, ["prova"]) for a in VOTANO])
    base = ore_finte(giorni=400)
    tutte = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto(),
                 gemelli={"EURUSD": base, "DXY": _dxy_specchio(base)})
    decisioni, tardiva = tutte[-2:], tutte[-3]
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
    bot._decidi(decisioni[:1], int(decisioni[0].r.quando), 10**12)
    assert len(aperte) == 1 and all(x > 0 and p == 1.0 and not riduci for x, p, riduci in aperte)
    # Lo stesso CRT una volta sola, anche se il giro si ripete.
    bot._decidi(decisioni[:1], int(decisioni[0].r.quando), 10**12)
    assert len(aperte) == 1
    # In ritardo (il bot ripartito 40 minuti dopo l'apertura della candela 3) non si entra: si segue sulla carta.
    vive, bot.stato.vive = bot.stato.vive, []
    bot._decidi([tardiva], int(tardiva.r.quando) + 40 * 60, vivo.RITARDO_MASSIMO)
    assert len(aperte) == 1 and bot.stato.saltate.get("arrivato tardi") == 1
    assert any(s.chiave == tardiva.chiave for s in bot.stato.seguite)
    bot.stato.vive = vive
    # La foto per il telefono la disegna il bot, a fine giro (dopo tutti gli ordini), e il messaggio d'apertura ne e'
    # la didascalia: arrivano insieme (il proprietario, 07/10/2026: *"mi si sfasa tutto tra foto e messaggio"*).
    assert not any(t == "aperta" for c, t in mandati if c == "-1")
    foto = []
    bot.tg.foto = lambda canale, dati, didascalia: foto.append((canale, dati, didascalia))
    bot.manda_foto_operazioni()
    assert len(foto) == 1 and foto[0][0] == "operativo" and foto[0][1].startswith(b"\x89PNG")
    assert foto[0][2] == "aperta"
    # Con un'operazione gia' aperta sullo stesso strumento non se ne apre un'altra (il proprietario, 07/10/2026:
    # "Max 1 aperta per strumento"): il Capo la lascia e lo dice, l'occasione si segue sulla carta.
    bot.stato.vive = [NS(chiave="un altro CRT", strumento="EURUSD", pareggio_fatto=False, rischio=10.0)]
    bot._decidi(decisioni[1:], int(decisioni[1].r.quando), 10**12)
    assert len(aperte) == 1
    assert any(s.chiave == decisioni[1].chiave for s in bot.stato.seguite)
    bot.stato.vive = []
    equipe = [t for c, t in mandati if c == "-2"]
    assert any("su EURUSD c'è già un'operazione aperta" in t and t.startswith("👔 Capo: Giro delle") for t in equipe)
    # La discussione sull'operazione aperta: ognuno dice la sua, il Capo decide e se ne prende la responsabilita',
    # e ogni messaggio dice di quale asset si parla.
    discussione = [t for t in equipe if t.startswith("📌 EURUSD · ")]
    assert any("Ho sentito tutti" in t and "la responsabilità è mia" in t for t in discussione)
    assert any("Metto in gioco" in t and "EUR" in t for t in discussione)
    # Sul grafico: il range, la finta, l'entrata all'apertura della candela 3, lo stop, il TP1, il target finale.
    csv = (tmp_path / "comune" / disegni.FILE).read_text(encoding="cp1252")
    for parola in ("Range", "Finta della candela 2", "all'apertura della candela 3", "Stop (oltre la candela 2)",
                   "TP1: chiusura del CRT", "EURUSD.x"):
        assert parola in csv, parola
    # A ogni giro: le operazioni aperte e la settimana; e il controllo del programma in MT5.
    bot._avviso_disegni = 0.0
    bot.aggiorna_disegni(int(decisioni[-1].r.quando))
    assert any(g.startswith("settimana ") for g in bot.disegni.gruppi)
    bot.controlla_disegni(float(decisioni[-1].r.quando))
    assert any("NvmDisegni" in t and "Start" in t for c, t in mandati if c == "-1")
    s = bot.stato.seguite[0]
    s.esito = {"erre": -1.0, "quando": int(base.t[-1]), "tp1": False, "tp2": False, "uscita": "stop"}
    bot.stato.vive = [NS(chiave=s.chiave, strumento="EURUSD")]
    bot._finita(s, int(base.t[-1]))
    # Sulla carta e' finita, ma sul conto e' ancora aperta: la squadra aspetta il risultato vero.
    assert bot.squadra.memoria.discusse[s.chiave]["aspetta_vero"]
    bot._risultato_vero(s.chiave, 1.8, "EURUSD", s.verso)
    bot._diario.shutdown(wait=True)
    assert s.chiave not in bot.squadra.memoria.discusse
    assert bot.squadra.memoria.casi[-1]["reale"] and bot.squadra.memoria.casi[-1]["erre"] == 1.8
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


def test_l_ora_giusta_come_nei_video():
    from nvm.intelligenti.metodo import GEMELLI, _ora_giusta
    from nvm.tempo import TF, ny
    r = lambda alto, basso: NS(alto_tf=alto, basso_tf=basso)
    finta = lambda t: NS(turtle_soup_inizio=t, quando=t)
    # Giornaliero: la finta nella sessione di Londra o la mattina di New York (V11 10:32, V17 14:00).
    assert _ora_giusta(r(TF.D1, TF.H1), finta(ny(2026, 9, 15, 3)), False)[0]
    assert _ora_giusta(r(TF.D1, TF.H1), finta(ny(2026, 9, 15, 9)), False)[0]
    assert not _ora_giusta(r(TF.D1, TF.H1), finta(ny(2026, 9, 15, 14)), False)[0]
    # Settimanale: l'estremo fra lunedi' e mercoledi' (V3 24:31). Il 15/09/2026 e' martedi', il 17 giovedi'.
    assert _ora_giusta(r(TF.W1, TF.H4), finta(ny(2026, 9, 15, 5)), False)[0]
    ok, perche = _ora_giusta(r(TF.W1, TF.H4), finta(ny(2026, 9, 17, 5)), False)
    assert not ok and "fra lunedì e mercoledì" in perche
    # Il kiss of death arriva verso fine settimana: giovedi' va bene.
    assert _ora_giusta(r(TF.W1, TF.H4), finta(ny(2026, 9, 17, 5)), True)[0]
    # Mensile: la manipolazione nelle prime due settimane (V1 16:00).
    assert _ora_giusta(r(TF.MN, TF.D1), finta(ny(2026, 9, 8, 3)), False)[0]
    assert not _ora_giusta(r(TF.MN, TF.D1), finta(ny(2026, 9, 22, 3)), False)[0]
    # L'SMT solo sulle coppie che dice Romeo (V8 22:00).
    assert GEMELLI["EURUSD"] == ("GBPUSD", 1) and GEMELLI["XAUUSD"] == ("XAGUSD", 1) and "USDJPY" not in GEMELLI


def test_con_l_smt_confermato_contro_si_chiude_prima_dell_obiettivo(tmp_path, monkeypatch):
    import vivo
    from nvm.agenti.cacciatore import Verso
    from nvm.vivo.ambiente import Impostazioni
    from nvm.vivo.telegram import Telegram
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    mandati, chiuse = [], []
    bot = object.__new__(vivo.Bot)
    bot.tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",)),
                      invia=lambda c, t: mandati.append((c, t)), stampa=lambda _: None)
    bot._da_dire = []
    viva = NS(chiave="k", strumento="EURUSD", verso="long", pareggio_fatto=False, uscita_anticipata="")
    bot.stato = NS(vive=[viva])
    bot.esecutore = NS(chiudi=lambda v, motivo: chiuse.append((v.chiave, motivo)) or NS(testo="chiusa: " + motivo))
    smt = Domanda("SMT", "Grilletto", "V8", True, "gemello")
    contro = NS(chiave="c", r=NS(strumento="EURUSD", verso=Verso.SHORT))
    stessa = NS(chiave="s", r=NS(strumento="EURUSD", verso=Verso.LONG))
    bot._verdetti = {"c": NS(metodo=Metodo([], [Domanda("SMT", "Grilletto", "V8", False, "no")], {})),
                     "s": NS(metodo=Metodo([], [smt], {}))}
    bot._smt_contro([contro, stessa])
    assert not chiuse          # l'SMT nel nostro verso, o non confermato, non chiude niente
    bot._verdetti["c"] = NS(metodo=Metodo([], [smt], {}))
    bot._smt_contro([contro])
    assert chiuse == [("k", chiuse[0][1])] and "V10" in chiuse[0][1]
    assert any("SMT" in t for _, t in mandati) and any("Grilletto" in t for t in bot._da_dire)


def test_dopo_il_primo_obiettivo_si_esce_se_il_kod_e_superato(tmp_path, monkeypatch):
    """Il metodo dei video (col metodo delle foto si esce solo a stop, pareggio o target)."""
    import vivo
    from nvm.tempo import ny
    from nvm.vivo import giro
    from tests.aiuti import minuti
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    monkeypatch.setattr(giro, "METODO", "candela 3")
    t0 = ny(2026, 9, 15, 3)
    righe = [(1.1060, 1.1061, 1.1049, 1.1050),     # il primo obiettivo
             (1.1050, 1.1051, 1.1040, 1.1042), (1.1042, 1.1048, 1.1041, 1.1047),
             (1.1047, 1.1046, 1.1043, 1.1044), (1.1044, 1.1052, 1.1043, 1.1050)]
    base = minuti("EURUSD", [t0 + h * 3600 for h in range(len(righe))], righe)
    base.passo = 3600
    chiuse, mandati = [], []
    bot = object.__new__(vivo.Bot)
    bot.basi, bot.fini = {"EURUSD": base}, {}
    bot.tg = NS(operativo=lambda t: mandati.append(t))
    bot._equipe = lambda t: None
    viva = NS(chiave="k", strumento="EURUSD", verso="short", short=True, pareggio_fatto=True, primo_quando=t0,
              basso="H1", uscita_anticipata="", tickets=[1, 2], chiusi=[1], invalida_candele=0, tempo_candele=0)
    bot.stato = NS(vive=[viva])
    bot.esecutore = NS(chiudi=lambda v, motivo: chiuse.append(motivo) or NS(testo=motivo),
                       uscita_anticipata=lambda v, b: None)
    bot.uscite(t0 + 4 * 3600)
    assert not chiuse          # l'ultima candela non e' ancora chiusa
    bot.uscite(t0 + 5 * 3600)
    assert len(chiuse) == 1 and "kiss of death" in chiuse[0] and "V16" in chiuse[0]


def test_sullo_stesso_strumento_decide_il_rischio(tmp_path):
    """Il proprietario, 07/10/2026: un'operazione alla volta per strumento? *"lo gestisce l'agente rischio.
    decisione sua"*. Con un'operazione gia' aperta sullo stesso strumento il Rischio punta meno, lo dice, e
    quanto ridurre lo impara dai risultati."""
    sq = Squadra(tmp_path)
    sola = sq.riunione("a", "EURUSD", _metodo(), 0, op=_op())
    stesso = sq.riunione("b", "EURUSD", _metodo(), 0, op=_op(), stesso=0.01)
    assert sola.entra and stesso.entra and 0 < stesso.puntata < sola.puntata
    assert "su EURUSD c'è già un'operazione aperta" in dict(stesso.voci)["Rischio"]
    # Se anche le seconde operazioni sullo stesso strumento vanno bene, il Rischio riduce di meno.
    prima = sq.memoria.rischio["stesso"]
    for i in range(30):
        sq.riunione(f"s{i}", "EURUSD", _metodo(), 0, op=_op(), stesso=0.01)
        sq.rifletti(f"s{i}", 2.0, preso=True)
    assert sq.memoria.rischio["stesso"] < prima
