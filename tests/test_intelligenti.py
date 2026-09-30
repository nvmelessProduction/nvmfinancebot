"""La squadra di agenti intelligenti: nostri, con le regole di Romeo, imparano solo dal vivo."""

from types import SimpleNamespace as NS

from nvm.intelligenti import al_lavoro
from nvm.intelligenti.regole import AGENTI, LISTA, REGOLE
from nvm.intelligenti.squadra import PER_SPEGNERE, SOGLIA_INIZIALE, Memoria, Squadra


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


def test_ogni_agente_ha_le_regole_di_romeo_e_la_lista_e_completa():
    assert {r.agente for r in REGOLE} == set(AGENTI)
    assert all(r.romeo and r.peso > 0 for r in REGOLE)
    # Quattro domande su cinque dalle regole; la conferma del Model#1 c'e' sempre.
    assert {r.lista for r in REGOLE if r.lista} == set(LISTA) - {"conferma_basso"}
    for r in REGOLE:
        esito, perche = r.guarda(_fatti())
        assert esito in (-1, 0, 1) and (perche or not esito)


def test_un_occasione_da_manuale_e_tutti_d_accordo_si_entra(tmp_path):
    v = Squadra(tmp_path).riunione("k1", "EURUSD", _fatti())
    assert v.entra and all(v.lista.values()) and 0.5 <= v.puntata <= 1.0
    assert [c for c, _ in v.voci][-2:] == ["Capo", "Rischio"]
    assert all(v.pareri[a]["voto"] == "entra" for a in AGENTI if v.pareri[a]["voto"] != "neutro")
    # Resta scritta, per imparare quando finisce.
    assert "k1" in Memoria.carica(tmp_path).discusse


def test_un_solo_no_nella_lista_di_romeo_e_non_si_entra(tmp_path):
    sq = Squadra(tmp_path)
    for i, f in enumerate([_fatti(**{"key level": False, "tipo di key level": "nessuno"}),
                           _fatti(**{"ore di New York": False, "ora di New York": "20:00"}),
                           _fatti(**{"bias dal grafico sopra": False}),
                           _fatti(**{"livello intatto prima del 50%": 1.1})]):
        v = sq.riunione(f"k{i}", "EURUSD", f)
        assert not v.entra and v.puntata == 0.0 and not all(v.lista.values())
        assert "lista di Romeo dice no" in v.voci[-1][1]


def test_se_non_sono_d_accordo_si_confrontano(tmp_path):
    f = _fatti(**{"candela": 2, "candela 2 chiusa dentro": None, "dentro un CRT più grande": False,
                  "candele interne": 0, "corpo della candela 1": 0.0, "spessore del turtle soup": 0.5,
                  "profondità della manipolazione": 0.01, "fvg col Model#1": False, "vera rottura di struttura": False,
                  "manipolazione a fine candela": False, "liquidità presa prima": False})
    v = Squadra(tmp_path).riunione("k", "EURUSD", f)
    assert v.pareri["Cacciatore"]["voto"] == "non entrare" and v.pareri["Key level"]["voto"] == "entra"
    assert any(t.startswith("Rispondo a") or t.startswith("Cambio idea") for _, t in v.voci)


def test_imparano_solo_dal_vivo_e_si_modificano_da_soli(tmp_path):
    sq = Squadra(tmp_path)
    # Dal vivo il gap del weekend sbaglia sempre: chi lo usava ci crede sempre meno.
    prima = sq.memoria.fiducia_regola("gap del weekend")
    for i in range(PER_SPEGNERE + 5):
        sq.riunione(f"g{i}", "EURUSD", _fatti())
        lezioni = sq.rifletti(f"g{i}", -1.0, preso=True)
        assert any(l["agente"] == "Capo" for l in lezioni)
    assert sq.memoria.fiducia_regola("gap del weekend") < prima
    assert Memoria.carica(tmp_path).credito("Gap") < 1.0
    cambi = sq.riscrivi_manuali()
    chi = {a for a, _, _ in cambi}
    assert "gap del weekend" in sq.memoria.spente and "Gap" in chi
    # La lista di Romeo non si spegne mai.
    assert not any(r.lista and r.nome in sq.memoria.spente for r in REGOLE)
    # Troppe operazioni in una settimana: il Capo diventa piu' esigente.
    assert "Capo" in chi and sq.memoria.soglia > SOGLIA_INIZIALE
    assert "spenta" in Memoria.carica(tmp_path).manuali["Gap"]


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
    assert len(sq.memoria.discusse) == len(decisioni)
    # Nel bot decide il verdetto della squadra; senza verdetto, con la squadra accesa, non si entra.
    finto = NS(_verdetti=verdetti, _decidono_i_cervelli=False, squadra=sq)
    for d in decisioni:
        assert vivo.Bot._entra(finto, d, None) is (verdetti[d.chiave].entra and verdetti[d.chiave].puntata > 0)
    finto._verdetti = {}
    assert vivo.Bot._entra(finto, decisioni[0], None) is False
    assert [v.chi for v in al_lavoro.voci(verdetti[decisioni[0].chiave])][-1] in ("Capo", "Rischio")


def test_la_memoria_della_squadra_di_prima_si_riparte_da_romeo(tmp_path):
    (tmp_path / "memoria.json").write_text('{"manuali": {"Gap": "vecchio"}, "lezioni": {}, "discusse": {}}',
                                           encoding="utf-8")
    m = Memoria.carica(tmp_path)
    assert m.manuali == {} and m.soglia == SOGLIA_INIZIALE


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
        def apri(self, d, conto, vive, pieno=None, parte=None, fiducia_minima=None):
            aperte.append((pieno, parte, fiducia_minima))
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
    # Decide la squadra, col tetto fisso e il suo Rischio.
    assert len(aperte) == len(decisioni) and all(p == 0.01 and 0.5 <= x <= 1.0 for x, p, _ in aperte)
    equipe = [t for c, t in mandati if c == "-2"]
    assert any("lista di Romeo" in t or "Le cinque domande di Romeo" in t for t in equipe)
    assert any("puntata massima" in t and "del conto" in t for t in equipe)
    assert not any("vent'anni" in t for t in equipe)
    # Finita male: la squadra impara in disparte e lo dice.
    s = bot.stato.seguite[0]
    s.esito = {"erre": -1.0, "quando": int(base.t[-1]), "tp1": False, "tp2": False, "uscita": "stop"}
    bot._finita(s, int(base.t[-1]))
    bot._diario.shutdown(wait=True)
    assert s.chiave not in bot.squadra.memoria.discusse and bot._lezioni_oggi
    assert any("Cosa impariamo" in t for c, t in mandati if c == "-2")
    # Il sabato la revisione e' della squadra, non del Capo dei vent'anni.
    prima = len(mandati)
    bot.stato.vive = []                          # quelle finte non si salvano su disco
    bot.riunione("2026-S40", int(base.t[-1]))
    assert "Revisione del sabato" in mandati[-1][1] and len(mandati) == prima + 1
