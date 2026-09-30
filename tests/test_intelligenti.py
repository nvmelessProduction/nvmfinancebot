"""La squadra di agenti intelligenti: nostri, nascono con Romeo, nessun limite ne' obbligo tranne lo
stop, imparano da ogni errore dal vivo, inventano idee nuove."""

from types import SimpleNamespace as NS

from nvm.intelligenti import al_lavoro
from nvm.intelligenti.regole import AGENTI, LISTA, REGOLE, atomi
from nvm.intelligenti.squadra import PIANO_ROMEO, PUNTATA_INIZIALE, VOLTE_IDEA, Memoria, Squadra, con_stop


def _fatti(**cambi):
    """Un'occasione da manuale di Romeo: tutte le domande a favore."""
    f = {"strumento": "EURUSD", "verso": "acquisto", "colpo": 1, "coppia": "D1-H1", "candela": 3,
         "candela 2 chiusa dentro": True, "candele interne": 2, "corpo della candela 1": -0.8,
         "dentro un CRT più grande": True, "profondità della manipolazione": 0.3, "spessore del turtle soup": 2.0,
         "fvg col Model#1": True, "vera rottura di struttura": True, "dalla parte giusta dell'apertura": True,
         "smt col gemello": True, "manipolazione a fine candela": True, "liquidità presa prima": True,
         "rr1": 1.5, "rr2": 4.0, "costi in R": 0.05, "key level": True, "tipo di key level": "FVG",
         "si ferma sul livello": True, "livello intatto oltre l'estremo": None, "livello intatto prima del 50%": None,
         "apertura della candela contraria toccata": True, "ore di Londra": False, "ore di New York": True,
         "golden candle time": True, "giorno": "martedì", "ora di New York": "09:30",
         "ora della manipolazione": "martedì 08:00", "posizione nella settimana": 0.2,
         "estremo della settimana fra lunedì e mercoledì": True, "bias dalla candela del range": True,
         "bias dal grafico sopra": True, "CRT grandi nello stesso verso": 1, "CRT grandi contro": 0,
         "a sconto nella settimana": True, "timeframe grandi a favore": 3, "timeframe grandi contro": 0,
         "settimana e mese": (True, True), "FVG davanti": True, "FVG alle spalle vicino": False,
         "gap del weekend": True}
    f.update(cambi)
    return f


GERGO = ("Model#1", "FVG", "turtle", "CRT", "key level", "orderflow", " R ", "SMT", "range")


def _op(stop=1.0950, ingresso=1.1000, tp1=1.1050):
    return NS(stop=stop, ingresso=ingresso, tp1=tp1)


def test_ogni_agente_nasce_con_le_regole_di_romeo_dette_in_parole_semplici():
    assert {r.agente for r in REGOLE} == set(AGENTI)
    assert all(r.romeo and r.peso > 0 for r in REGOLE)
    assert {r.lista for r in REGOLE if r.lista} == set(LISTA) - {"conferma_basso"}
    for f in (_fatti(), _fatti(verso="vendita", **{"key level": False, "ore di New York": False, "candela": 2,
                                                   "bias dal grafico sopra": False, "gap del weekend": False})):
        for r in REGOLE:
            esito, perche = r.guarda(f)
            assert esito in (-1, 0, 1) and (perche or not esito)
            assert not any(g.lower() in perche.lower() for g in GERGO), perche


def test_un_occasione_da_manuale_si_entra_e_la_squadra_lo_spiega(tmp_path):
    v = Squadra(tmp_path).riunione("k1", "EURUSD", _fatti(), op=_op())
    assert v.entra and all(v.lista.values()) and v.puntata > 0
    chi = [c for c, _ in v.voci]
    assert chi[-2:] == ["Capo", "Rischio"] and len(chi) <= 6
    assert v.voci[-2][1].startswith("Compriamo EURUSD")
    testo = " ".join(t for _, t in v.voci)
    assert not any(g.lower() in testo.lower() for g in GERGO), testo
    sq = Squadra(tmp_path)
    v2 = sq.riunione("k2", "EURUSD", _fatti(verso="vendita"), op=_op(1.1050, 1.1000, 1.0950))
    assert v2.entra and v2.voci[-2][1].startswith("Vendiamo EURUSD")
    # Resta scritta, per imparare quando finisce.
    sq.salva()
    assert "k2" in Memoria.carica(tmp_path).discusse


def test_la_lista_di_romeo_e_una_convinzione_non_un_obbligo(tmp_path):
    sq = Squadra(tmp_path)
    senza = _fatti(**{"key level": False, "tipo di key level": "nessuno"})
    v = sq.riunione("k0", "EURUSD", senza, op=_op())
    assert not v.entra and "zona importante" in v.voci[-1][1]
    # Dal vivo, in casi cosi', si guadagna sempre: il Capo impara che qui Romeo sbaglia, ed entra.
    for i in range(400):
        sq.rifletti(f"k{i}", 2.0, preso=False)
        v = sq.riunione(f"k{i + 1}", "EURUSD", senza, op=_op())
        if v.entra:
            break
    assert v.entra, i
    assert any("Romeo qui non entrerebbe" in t for _, t in v.voci)
    assert sq.memoria.capo["no"]["key_level"] > -1.0


def test_ogni_errore_diventa_una_miglioria(tmp_path):
    sq = Squadra(tmp_path)
    prima = dict(sq.memoria.pesi["Orario"])
    v = sq.riunione("p0", "EURUSD", _fatti(), op=_op())
    assert v.entra
    for i in range(600):
        lezioni = sq.rifletti(f"p{i}", -1.0, preso=True)
        v = sq.riunione(f"p{i + 1}", "EURUSD", _fatti(), op=_op())
        if not v.entra:
            break
    # Sempre perdite nello stesso caso: ci credono meno, finche' non entrano piu'.
    assert not v.entra, i
    assert sq.memoria.pesi["Orario"]["ore di Romeo"] < prima["ore di Romeo"]
    assert any(l["agente"] == "Orario" and "ci crederò un po' di meno" in l["lezione"] for l in lezioni)
    assert any(l["agente"] == "Capo" and "più prudente" in l["lezione"] for l in lezioni)
    # Il Rischio, dopo tante perdite, punta meno.
    assert sq.memoria.rischio["base"] < PUNTATA_INIZIALE
    assert any(l["agente"] == "Rischio" and "puntata base passa da" in l["lezione"] for l in lezioni)
    # Tutto resta scritto: la squadra ricaricata sa quello che ha imparato.
    assert Memoria.carica(tmp_path).pesi["Orario"]["ore di Romeo"] == sq.memoria.pesi["Orario"]["ore di Romeo"]


def test_il_rischio_decide_da_solo_senza_tetti(tmp_path):
    sq = Squadra(tmp_path)
    for i in range(150):
        v = sq.riunione(f"r{i}", "EURUSD", _fatti(), op=_op())
        assert v.entra
        sq.rifletti(f"r{i}", 2.0, preso=True)
    # Vince sempre: punta sempre di piu', nessuno lo ferma all'1%.
    assert sq.memoria.rischio["base"] > 2 * PUNTATA_INIZIALE
    assert sq.riunione("r", "EURUSD", _fatti(), op=_op()).puntata > 2 * PUNTATA_INIZIALE


def test_senza_stop_non_si_entra_mai(tmp_path):
    assert con_stop(_op()) and not con_stop(_op(stop=1.1010)) and not con_stop(_op(stop=float("nan")))
    assert not con_stop(NS(stop=None, ingresso=1.1, tp1=1.2))
    v = Squadra(tmp_path).riunione("s", "EURUSD", _fatti(), op=_op(stop=1.1010))
    assert not v.entra and "senza uno stop" in v.voci[-1][1]


def test_inventano_idee_nuove_dagli_errori_che_si_ripetono(tmp_path):
    sq = Squadra(tmp_path)
    # Di lunedi' va sempre male, di giovedi' sempre bene: le regole di Romeo non lo sanno.
    for i in range(2 * VOLTE_IDEA + 10):
        for giorno, erre in (("lunedì", -1.0), ("giovedì", 1.5)):
            sq.riunione(f"{giorno}{i}", "EURUSD", _fatti(giorno=giorno), op=_op())
            sq.rifletti(f"{giorno}{i}", erre, preso=False)
    cambi = sq.riscrivi_manuali()
    assert any("giorno=lunedì" in k.split("&") for k in sq.memoria.idee), sq.memoria.idee
    assert any("💡 idea nuova" in cosa and "di lunedì" in cosa for _, cosa, _ in cambi)
    k = next(k for k in sq.memoria.idee if "giorno=lunedì" in k.split("&"))
    chi = sq.memoria.idee[k]["agente"]
    assert sq.memoria.pesi[chi][k] < 0
    # L'idea entra nei suoi pensieri: di lunedi' la vede, di giovedi' no.
    assert k in sq.riunione("l", "EURUSD", _fatti(giorno="lunedì"), op=_op()).pareri[chi]["x"]
    assert "giorno=lunedì" in atomi(_fatti(giorno="lunedì"))


def test_livelli_impara_quale_stop_e_quale_uscita_funzionano(tmp_path):
    sq = Squadra(tmp_path)
    piani = [_op() for _ in range(9)]
    seguire = {"strumento": "EURUSD", "basso": "H1", "scadenza": 0, "piani": [None] * 9}
    assert sq.riunione("a", "EURUSD", _fatti(), piani, da_seguire=seguire).piano == PIANO_ROMEO
    for i in range(30):
        sq.riunione(f"b{i}", "EURUSD", _fatti(), piani, da_seguire=seguire)
        sq.impara_piani(f"b{i}", [-1.0, -1.0, -1.0, 1.0, 0.2, 0.2, 0.1, 0.1, 0.1])
    v = sq.riunione("c", "EURUSD", _fatti(), piani, da_seguire=seguire)
    assert v.piano == 3
    if v.entra:
        assert any(chi == "Livelli" and "stop" in t for chi, t in v.voci)


def test_la_squadra_si_riunisce_sulle_occasioni_vere_del_giro(tmp_path):
    from nvm.vivo.giro import giro
    from tests.test_vivo import CapoFinto, ore_finte
    import vivo
    base = ore_finte()
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto())[:3]
    assert decisioni
    sq = Squadra(tmp_path)
    verdetti = al_lavoro.riunioni(sq, decisioni, {"EURUSD": base}, {})
    assert not sq.ultimo_errore
    assert set(verdetti) == {d.chiave for d in decisioni}
    assert len(sq.memoria.discusse) == len(decisioni) and len(sq.memoria.da_vedere) == len(decisioni)
    # Livelli rivede tutti i piani quando sono finiti.
    al_lavoro.valuta_piani(sq, {"EURUSD": base}, {}, max(d.scadenza for d in decisioni) + 1)
    assert not sq.ultimo_errore and not sq.memoria.da_vedere and sq.memoria.piani
    # Nel bot decide il verdetto della squadra; senza verdetto, con la squadra accesa, non si entra.
    finto = NS(_verdetti=verdetti, _decidono_i_cervelli=False, squadra=sq)
    for d in decisioni:
        assert vivo.Bot._entra(finto, d, None) is (verdetti[d.chiave].entra and verdetti[d.chiave].puntata > 0)
    finto._verdetti = {}
    assert vivo.Bot._entra(finto, decisioni[0], None) is False


def test_la_memoria_della_squadra_di_prima_si_riparte_da_romeo(tmp_path):
    (tmp_path / "memoria.json").write_text('{"regole": {}, "agenti": {}, "soglia": 0.6, "discusse": {}}',
                                           encoding="utf-8")
    m = Memoria.carica(tmp_path)
    assert m.rischio["base"] == PUNTATA_INIZIALE and m.capo["no"]["key_level"] == -1.0


def test_nessuna_ai_esterna():
    import pathlib
    for f in pathlib.Path("nvm/intelligenti").glob("*.py"):
        testo = f.read_text(encoding="utf-8")
        assert "anthropic" not in testo.lower() and "openai" not in testo.lower()


def test_nel_bot_la_squadra_decide_apre_col_suo_rischio_impara_e_fa_la_revisione(tmp_path, monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    import vivo
    from nvm.agenti.capo import Capo
    from nvm.vivo.giro import giro
    from nvm.vivo.stato import Stato
    from nvm.vivo.telegram import Telegram
    from nvm.vivo.ambiente import Impostazioni
    from tests.test_vivo import CapoFinto, ore_finte
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    # Tutte le occasioni come da manuale di Romeo: la squadra le vuole tutte.
    monkeypatch.setattr(al_lavoro, "fatti", lambda d, ore, quarti=None: _fatti())
    base = ore_finte()
    decisioni = giro({"EURUSD": base}, int(base.t[0]) + 150 * 86400, int(base.t[-1]), CapoFinto())[:2]
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
    bot.terminale = NS(conto=lambda: NS(saldo=10000.0, valuta="EUR", demo=True))
    bot.esecutore = Esecutore()
    bot.stato = Stato()
    bot.capo = Capo.da_dati(json.loads(Path("nvm/vivo/capo.json").read_text(encoding="utf-8")))
    bot.cervelli, bot.cervelli_info, bot.scelte = None, {}, {"squadra_intelligente": True}
    bot.squadra = al_lavoro.crea(tmp_path, bot.scelte)
    bot.basi, bot.fini, bot._verdetti, bot._da_dire, bot._allarmi = {"EURUSD": base}, {}, {}, [], {}
    bot._lezioni_oggi, bot._diario, bot._prove = [], ThreadPoolExecutor(1), None
    bot._decidi(decisioni, int(base.t[-1]), 10**12)
    # Decide la squadra; quanto puntare lo decide il Rischio da solo, e nessuno lo riduce.
    assert len(aperte) == len(decisioni) and all(x > 0 and p == 1.0 and not riduci for x, p, riduci in aperte)
    equipe = [t for c, t in mandati if c == "-2"]
    assert any("Compriamo EURUSD" in t or "Vendiamo EURUSD" in t for t in equipe)
    assert any("Metto in gioco" in t and "EUR" in t and "del conto" in t for t in equipe)
    assert not any("vent'anni" in t or " R " in t for t in equipe)
    # Finita male: la squadra impara in disparte e lo dice.
    s = bot.stato.seguite[0]
    s.esito = {"erre": -1.0, "quando": int(base.t[-1]), "tp1": False, "tp2": False, "uscita": "stop"}
    bot._finita(s, int(base.t[-1]))
    bot._diario.shutdown(wait=True)
    assert s.chiave not in bot.squadra.memoria.discusse and bot._lezioni_oggi
    assert any("Cosa impariamo" in t and "EURUSD" in t for c, t in mandati if c == "-2")
    # Il sabato la revisione e' della squadra, non del Capo dei vent'anni.
    prima = len(mandati)
    bot.stato.vive = []                          # quelle finte non si salvano su disco
    bot.riunione("2026-S40", int(base.t[-1]))
    assert "Revisione della settimana" in mandati[-1][1] and len(mandati) == prima + 1
