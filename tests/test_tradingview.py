"""TradingView come fonte dei grafici e le proposte con i pulsanti Apri / Lascia, con TradingView, Telegram e MT5 finti."""

import base64
import hashlib
import json
import socket
import threading
import time
import urllib.parse
import urllib.request
from types import SimpleNamespace as NS

import numpy as np
import pytest

from nvm.tempo import utc
from nvm.vivo.ambiente import Impostazioni, impostazioni
from nvm.vivo.esecutore import Esecutore
from nvm.vivo.stato import Seguita, Stato
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import Terminale
from nvm.vivo.tradingview import (MARGINE_QUOTA, REGISTRA, TOKEN, Accesso, AccessoScaduto, Fonte, QuotaFinita,
                                  TradingView, _barre, _messaggi, fine_quota, leggi_simboli, minuti)
from tests.mt5_finto import MT5Finto
from tests.test_vivo import _una_decisione


# --- i grafici scelti nel .env ---

def test_i_grafici_si_scrivono_come_su_tradingview(tmp_path):
    simboli, sbagliati = leggi_simboli("OANDA:EURUSD, oanda:gbpusd;OANDA:US30USD=US30  FX:BOH, EURUSD")
    assert simboli == [("OANDA:EURUSD", "EURUSD"), ("OANDA:GBPUSD", "GBPUSD"), ("OANDA:US30USD", "US30")]
    assert sbagliati == ["FX:BOH", "EURUSD"]
    # Lo stesso strumento due volte vale una; nomi che il bot non conosce (US500 invece di SPX500) si segnalano.
    assert leggi_simboli("ICE:GBPNZD, ICE:GBPNZD, FXCM:SPX500=US500, FXCM:SPX500,")[0] == \
        [("ICE:GBPNZD", "GBPNZD"), ("FXCM:SPX500", "SPX500")]
    assert leggi_simboli("FXCM:SPX500=US500")[1] == ["FXCM:SPX500=US500"]
    (tmp_path / ".env").write_text("TRADINGVIEW_SIMBOLI=OANDA:EURUSD\nTRADINGVIEW_DXY=tvc:dxy,\n", encoding="utf-8")
    imp = impostazioni(tmp_path, {})
    assert imp.tradingview == (("OANDA:EURUSD", "EURUSD"),) and imp.tradingview_dxy == "TVC:DXY"
    # Senza la riga, il bot resta su MT5.
    assert impostazioni(tmp_path / "vuota", {}).tradingview == ()


# --- le candele ---

def test_le_candele_di_tradingview_diventano_quelle_del_bot():
    t0 = utc(2026, 10, 12, 8)
    barre = [{"t": t0 + i * 3600, "o": 1.1 + i / 1e4, "h": 1.1005 + i / 1e4, "l": 1.0995 + i / 1e4, "c": 1.1001 + i / 1e4,
              "v": 10} for i in range(3)]
    m = minuti("EURUSD", barre, 3600, t0 + 2 * 3600 + 60)        # l'ultima e' ancora in formazione
    assert len(m) == 2 and m.passo == 3600 and list(m.t) == [t0, t0 + 3600]
    assert m.bid[0].tolist() == [110000, 110050, 109950, 110010] and (m.ask == m.bid).all()
    # In millisecondi, se mai arrivassero cosi'.
    ms = [dict(b, t=b["t"] * 1000) for b in barre]
    assert list(minuti("EURUSD", ms, 3600, t0 + 3 * 3600).t) == [t0, t0 + 3600, t0 + 7200]


def test_le_giornaliere_aprono_alle_17_di_new_york_e_la_domenica_si_unisce_al_lunedi():
    # Lunedi' 12/10/2026: la giornata del forex apre domenica alle 17 di New York (21 UTC, ora legale).
    lunedi = utc(2026, 10, 12)
    barre = [{"t": lunedi - 86400, "o": 1.10, "h": 1.11, "l": 1.09, "c": 1.105},      # domenica: un pezzo
             {"t": lunedi, "o": 1.105, "h": 1.12, "l": 1.10, "c": 1.115},
             {"t": lunedi + 86400, "o": 1.115, "h": 1.13, "l": 1.11, "c": 1.12}]
    m = minuti("EURUSD", barre, 86400, utc(2026, 10, 13, 22))
    assert list(m.t) == [utc(2026, 10, 11, 21), utc(2026, 10, 12, 21)]
    assert m.bid[0].tolist() == [110000, 112000, 109000, 111500]


def test_la_fonte_chiede_una_candela_in_piu_e_usa_i_nomi_scelti():
    chieste = []
    tv = NS(candele=lambda simbolo, passo, quante: chieste.append((simbolo, passo, quante)) or [])
    f = Fonte(tv, [("OANDA:EURUSD", "EURUSD")], "TVC:DXY")
    assert f.esiste("EURUSD") and f.esiste("DXY") and not f.esiste("GBPUSD")
    f.orarie("EURUSD", 50)
    f.barre("DXY", 20, 900)
    f.giornaliere("EURUSD", 7000)
    assert chieste == [("OANDA:EURUSD", 3600, 51), ("TVC:DXY", 900, 21), ("OANDA:EURUSD", 86400, 7001)]


# --- il server MCP ---

def test_le_risposte_del_server_si_leggono_in_json_e_a_eventi():
    evento = b'event: message\ndata: {"jsonrpc":"2.0","id":3,"result":{"content":[]}}\n\n'
    assert _messaggi({"Content-Type": "text/event-stream"}, evento)[0]["id"] == 3
    assert _messaggi({"content-type": "application/json"}, b'{"id": 1}') == [{"id": 1}]
    barre = [{"t": 1, "o": 1, "h": 2, "l": 0, "c": 1, "v": 0}]
    assert _barre({"symbol": "X", "summary": {"n": 1}, "bars": barre}) == barre
    assert _barre({"data": {"result": barre}}) == barre and _barre({"niente": 1}) is None


class ServerFinto:
    """Il server MCP di TradingView: apre la sessione, la fa scadere una volta, risponde a eventi."""

    def __init__(self, barre):
        self.barre, self.chiamate, self.scaduta = barre, [], False

    def __call__(self, url, dati, intestazioni):
        m = json.loads(dati)
        self.chiamate.append((m.get("method"), intestazioni.get("Mcp-Session-Id"), intestazioni["Authorization"]))
        if m["method"] == "initialize":
            return 200, {"Mcp-Session-Id": f"S{len(self.chiamate)}", "Content-Type": "application/json"}, json.dumps(
                {"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": "2025-06-18"}}).encode()
        if m["method"] == "notifications/initialized":
            return 202, {}, b""
        if not self.scaduta:
            self.scaduta = True
            return 404, {}, b""
        testo = json.dumps({"symbol": m["params"]["arguments"]["symbol"], "bars": self.barre})
        corpo = json.dumps({"jsonrpc": "2.0", "id": m["id"],
                            "result": {"content": [{"type": "text", "text": testo}]}})
        return 200, {"Content-Type": "text/event-stream"}, f"event: message\ndata: {corpo}\n\n".encode()


def _accesso(tmp_path, posta=None, adesso=1000.0):
    a = Accesso(tmp_path, posta=posta or (lambda *x: (500, {}, b"")), orologio=lambda: adesso)
    a.salva({"client_id": "c", "access_token": "AT", "refresh_token": "RT", "scade": adesso + 3600})
    return a


def test_le_candele_arrivano_dal_server_anche_se_la_sessione_scade(tmp_path):
    barre = [{"t": 3600, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 3}]
    server = ServerFinto(barre)
    tv = TradingView(_accesso(tmp_path), posta=server, intervallo=0.0)
    assert tv.candele("OANDA:EURUSD", 3600, 10) == barre
    metodi = [c[0] for c in server.chiamate]
    assert metodi == ["initialize", "notifications/initialized", "tools/call",
                      "initialize", "notifications/initialized", "tools/call"]
    assert all(c[2] == "Bearer AT" for c in server.chiamate)
    assert server.chiamate[-1][1] == "S4"           # la sessione nuova


def test_l_accesso_si_rinnova_da_solo_e_se_non_si_puo_lo_dice(tmp_path):
    chieste = []

    def posta(url, dati, intestazioni):
        chieste.append(urllib.parse.parse_qs(dati.decode()))
        return 200, {}, json.dumps({"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600}).encode()
    a = _accesso(tmp_path, posta, adesso=1000.0)
    assert a.token() == "AT" and not chieste                     # ancora buono
    a._orologio = lambda: 1000.0 + 3600
    assert a.token() == "AT2" and chieste[0]["grant_type"] == ["refresh_token"] and chieste[0]["refresh_token"] == ["RT"]
    # Il refresh token nuovo si tiene, anche nel file.
    assert json.loads((tmp_path / "tradingview.json").read_text())["refresh_token"] == "RT2"
    assert "AT2" not in repr(a) and "RT2" not in repr(a)
    a._posta = lambda *x: (400, {}, b'{"error":"invalid_grant"}')
    a._orologio = lambda: 1000.0 + 99999
    with pytest.raises(AccessoScaduto):
        a.token()
    # Senza file: si dice di fare il login.
    with pytest.raises(AccessoScaduto, match="tradingview_accesso"):
        Accesso(tmp_path / "vuota").token()


def test_il_login_rifatto_col_bot_acceso_vale_subito(tmp_path):
    a = Accesso(tmp_path)
    assert not a.pronto
    altro = Accesso(tmp_path)
    altro.salva({"client_id": "c", "access_token": "AT", "refresh_token": "RT", "scade": time.time() + 3600})
    assert a.pronto and a.token() == "AT"


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_il_primo_accesso_apre_il_browser_e_salva_le_chiavi_senza_stamparle(tmp_path):
    richieste = {}

    def posta(url, dati, intestazioni):
        if url == REGISTRA:
            richieste["registra"] = json.loads(dati)
            return 201, {}, json.dumps({"client_id": "cliente"}).encode()
        assert url == TOKEN
        richieste["token"] = urllib.parse.parse_qs(dati.decode())
        return 200, {}, json.dumps({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}).encode()

    def browser(indirizzo):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(indirizzo).query)
        richieste["sfida"] = q["code_challenge"][0]
        ritorno = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "CODICE", "state": q["state"][0]})
        threading.Thread(target=lambda: urllib.request.urlopen(ritorno, timeout=10).read(), daemon=True).start()

    stampato = []
    a = Accesso(tmp_path, posta=posta)
    a.primo_accesso(apri=browser, porta=_porta_libera(), attesa=20, stampa=stampato.append)
    assert a.pronto and a.token() == "AT"
    assert richieste["registra"]["token_endpoint_auth_method"] == "none"
    t = richieste["token"]
    assert t["code"] == ["CODICE"] and t["client_id"] == ["cliente"]
    verificatore = t["code_verifier"][0]
    assert base64.urlsafe_b64encode(hashlib.sha256(verificatore.encode()).digest()).rstrip(b"=").decode() == richieste["sfida"]
    assert not any("AT" in riga.split("?")[0] or "RT" in riga for riga in stampato if "authorize" not in riga)


# --- Telegram: i pulsanti ---

def test_telegram_manda_i_pulsanti_e_legge_chi_li_preme():
    mandati = []
    arrivi = [{"update_id": 9, "callback_query": {"id": "q1", "data": "apri:ab12", "from": {"first_name": "Marco"},
                                                  "message": {"message_id": 77, "chat": {"id": -1}, "text": "SETUP",
                                                              "date": 5}}},
              {"update_id": 10, "callback_query": {"id": "q2", "data": "apri:ab12",
                                                   "message": {"message_id": 1, "chat": {"id": 999}}}}]
    tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",)), invia=lambda c, t: None,
                  stampa=lambda _: None, prendi=lambda dal: arrivi, posta=lambda url, dati: mandati.append((url, dati)))
    tg.proposta("SETUP", [("✅ Apri", "apri:ab12"), ("❌ Lascia", "lascia:ab12")])
    url, dati = mandati[0]
    assert url.endswith("/sendMessage") and dati["chat_id"] == "-1"
    assert dati["reply_markup"]["inline_keyboard"][0][1] == {"text": "❌ Lascia", "callback_data": "lascia:ab12"}
    ricevuti, prossimo = tg.ricevi(9)
    assert prossimo == 11 and len(ricevuti) == 1                  # chi non e' nei nostri canali non conta
    r = ricevuti[0]
    assert (r.tasto, r.id_tasto, r.messaggio, r.originale, r.chi, r.testo) == ("apri:ab12", "q1", 77, "SETUP", "Marco", "")
    tg.rispondi_tasto("q1", "Aperta")
    tg.chiudi_tasti("-1", 77, "SETUP\n\nAperta")
    assert mandati[1][0].endswith("/answerCallbackQuery") and mandati[2][0].endswith("/editMessageText")
    assert mandati[2][1]["message_id"] == 77 and "reply_markup" not in mandati[2][1]


# --- il bot: propone, e apre solo con «Apri» ---

def _bot(tmp_path, monkeypatch, d, arrivi):
    import vivo
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    bot = object.__new__(vivo.Bot)
    bot._allarmi, bot._verdetti, bot._foto_da_fare, bot._da_dire = {}, {}, [], []
    bot.proposte, bot.squadra, bot.disegni, bot.cervelli, bot.cervelli_info, bot.scelte = {}, None, None, None, {}, {}
    import queue
    bot._arrivi, bot._in_ascolto = queue.Queue(), False
    bot.fonte = NS(simbolo=lambda s: "OANDA:" + s)
    m = MT5Finto()
    m.tick[d.r.strumento] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    bot.mt5 = m
    bot.terminale = Terminale(mt5=m)
    bot.terminale.scarto = m.scarto
    bot.esecutore = Esecutore(bot.terminale)
    bot.stato = Stato()
    bot.mandati = []
    bot.tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",)),
                      invia=lambda c, t: bot.mandati.append(("messaggio", c, t)), stampa=lambda _: None,
                      prendi=lambda dal: [a for a in arrivi if a["update_id"] >= dal],
                      posta=lambda url, dati: bot.mandati.append((url.rsplit("/", 1)[-1], dati)) or
                      {"message_id": 900 + len(bot.mandati)})
    return bot


def _premi(numero, azione, ident, chi="Marco"):
    return {"update_id": numero, "callback_query": {"id": f"q{numero}", "data": f"{azione}:{ident}", "from": {"first_name": chi},
                                                    "message": {"message_id": 70 + numero, "chat": {"id": -1},
                                                                "text": "📺 SETUP", "date": 0}}}


def test_su_tradingview_il_bot_apre_da_solo(tmp_path, monkeypatch):
    """Il proprietario, 12/10/2026: *"metti tutto automatico sul bot, niente più richieste"*, col permesso di
    TradingView che riferisce. Senza la rete decide la squadra, e il bot apre sui prezzi di TradingView."""
    from tests.test_vivo import CapoFinto
    d = _una_decisione()
    bot = _bot(tmp_path, monkeypatch, d, [])
    bot.capo, bot._prove = CapoFinto(), {}
    bot._decidi([d], d.r.quando, 3600)
    (p,) = bot.mt5.posizioni.values()
    assert p.sl == round(d.op.stop, 5) and p.tp == round(d.op.tp2, 5) and not bot.proposte
    (s,) = bot.stato.seguite
    assert s.chiave == d.chiave and s.entrata


def test_con_apri_si_apre_su_mt5_con_stop_e_target_di_tradingview(tmp_path, monkeypatch):
    d = _una_decisione()
    arrivi = []
    bot = _bot(tmp_path, monkeypatch, d, arrivi)
    bot.stato.seguite = [Seguita(d.chiave, "EURUSD", "D1", "H1", d.r.verso.value, d.r.quando, d.op.ingresso, d.op.stop,
                                 d.op.tp1, d.op.tp2, d.r.quando + 86400, False, [], 1.0, 2.0, 0.0, 0.5, 0.5, 0.0)]
    monkeypatch.setattr(time, "time", lambda: d.r.quando + 60)
    bot._proponi(d, None)
    (ident,) = bot.proposte
    arrivi.append(_premi(1, "apri", ident))
    bot.ascolta()
    (p,) = bot.mt5.posizioni.values()
    assert p.sl == round(d.op.stop, 5) and p.tp == round(d.op.tp2, 5)
    assert bot.stato.vive and bot.stato.seguite[0].entrata and not bot.proposte
    risposte = [x[1] for x in bot.mandati if x[0] == "answerCallbackQuery"]
    cambiati = [x[1] for x in bot.mandati if x[0] == "editMessageText"]
    assert risposte[-1]["text"] == "Aperta" and "✅ Aperta da Marco" in cambiati[-1]["text"]
    assert cambiati[-1]["text"].startswith("📺 SETUP")
    registro = (tmp_path / "registro.jsonl").read_text(encoding="utf-8") if (tmp_path / "registro.jsonl").exists() else \
        "".join(x.read_text(encoding="utf-8") for x in tmp_path.rglob("*.jsonl"))
    assert "scelta del proprietario" in registro
    # Premuto di nuovo: non vale piu', e non si apre una seconda volta.
    arrivi.append(_premi(2, "apri", ident))
    bot.ascolta()
    assert len(bot.mt5.posizioni) == 1 and "non vale più" in [x[1] for x in bot.mandati if x[0] == "editMessageText"][-1]["text"]


def test_con_lascia_non_si_apre_niente(tmp_path, monkeypatch):
    d = _una_decisione()
    arrivi = []
    bot = _bot(tmp_path, monkeypatch, d, arrivi)
    annullate = []
    bot.squadra = NS(annulla=annullate.append)
    monkeypatch.setattr(time, "time", lambda: d.r.quando + 60)
    bot._proponi(d, NS(puntata=0.01))
    (ident,) = bot.proposte
    arrivi.append(_premi(1, "lascia", ident, chi="Luca"))
    bot.ascolta()
    assert bot.mt5.posizioni == {} and not bot.proposte and annullate == [d.chiave]
    assert "❌ Lasciata da Luca" in [x[1] for x in bot.mandati if x[0] == "editMessageText"][-1]["text"]


def test_la_proposta_scade_e_non_si_apre_se_il_prezzo_e_scappato(tmp_path, monkeypatch):
    import vivo
    d = _una_decisione()
    arrivi = []
    bot = _bot(tmp_path, monkeypatch, d, arrivi)
    adesso = [d.r.quando + 60]
    monkeypatch.setattr(time, "time", lambda: adesso[0])
    # Il prezzo su MT5 e' corso verso il target: il target finale renderebbe meno di 1,5 volte il rischio.
    segno = 1 if d.r.verso.value == "long" else -1
    soglia = (d.op.tp2 + 1.5 * d.op.stop) / 2.5
    scappato = soglia + segno * 0.2 * abs(d.op.tp2 - soglia)
    bot.mt5.tick["EURUSD"] = NS(time=0, bid=scappato, ask=scappato)
    bot._proponi(d, None)
    (ident,) = bot.proposte
    arrivi.append(_premi(1, "apri", ident))
    bot.ascolta()
    assert bot.mt5.posizioni == {} and "si è mosso" in [x[1] for x in bot.mandati if x[0] == "editMessageText"][-1]["text"]
    # Una proposta non decisa scade da sola.
    bot.mt5.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    bot._proponi(d, None)
    adesso[0] = d.r.quando + vivo.VALIDITA_PROPOSTA + 1
    bot._scadute()
    assert not bot.proposte


def test_le_ore_mancanti_all_avvio_si_prendono_tutte_al_giro_dopo():
    import vivo
    chieste = []
    bot = object.__new__(vivo.Bot)
    bot.fonte = NS(orarie=lambda s, quante: chieste.append(quante) or vivo.Minuti.vuoti(s, 3600))
    bot.basi = {}
    bot._ore_nuove("EURUSD")
    assert chieste == [vivo.ORARIE] and "EURUSD" in bot.basi


def test_la_total_si_legge_da_tradingview_e_va_fra_i_grafici_di_confronto(tmp_path):
    import vivo
    (tmp_path / ".env").write_text("TRADINGVIEW_SIMBOLI=BINANCE:BTCUSDT=BTCUSD\nTRADINGVIEW_TOTAL=cryptocap:total\n",
                                   encoding="utf-8")
    imp = impostazioni(tmp_path, {})
    assert imp.tradingview == (("BINANCE:BTCUSDT", "BTCUSD"),) and imp.tradingview_totale == "CRYPTOCAP:TOTAL"
    chieste = []
    t0 = utc(2026, 10, 12)
    barre = [{"t": t0 + i * 3600, "o": 3.0e12, "h": 3.1e12, "l": 2.9e12, "c": 3.05e12} for i in range(3)]
    tv = NS(candele=lambda simbolo, passo, quante: chieste.append(simbolo) or barre)
    bot = object.__new__(vivo.Bot)
    bot._allarmi = {}
    bot.allarme = lambda testo: None
    bot.fonte = Fonte(tv, list(imp.tradingview), "TVC:DXY", imp.tradingview_totale, orologio=lambda: t0 + 4 * 3600)
    bot.basi, bot.dxy = {}, None
    bot.aggiorna_totale()
    assert chieste == ["CRYPTOCAP:TOTAL"] and bot.totale.strumento == "TOTAL" and len(bot.totale) == 3
    assert bot.totale.bid[0, 3] * bot.totale.punto == pytest.approx(3.05e12)
    assert "TOTAL" in bot.gemelli()
    # Senza TradingView (o senza la riga) la TOTAL non c'e'.
    bot.fonte = None
    bot.terminale = NS()
    bot.aggiorna_totale()
    assert bot.totale is None and "TOTAL" not in bot.gemelli()


def test_i_pulsanti_hanno_risposta_subito_e_si_eseguono_appena_il_bot_e_libero(tmp_path, monkeypatch):
    """Il proprietario, 12/10/2026, su «Apri»: *"apre stra tardi"*. Il bot leggeva Telegram una volta al minuto e solo
    a fine giro: adesso un filo legge sempre, risponde al pulsante subito, e il bot lo esegue appena puo'."""
    import vivo
    d = _una_decisione()
    arrivi = []
    bot = _bot(tmp_path, monkeypatch, d, arrivi)
    bot.imp = Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",))
    monkeypatch.setattr(time, "time", lambda: d.r.quando + 60)
    bot._proponi(d, None)
    (ident,) = bot.proposte
    arrivi.append(_premi(1, "apri", ident))
    chiesti = []

    def prendi(dal, attesa=0):
        chiesti.append(attesa)
        return [a for a in arrivi if a["update_id"] >= dal]
    bot.tg._prendi = prendi
    bot.stato.telegram_dal = 0
    bot.avvia_ascolto()
    fine = time.monotonic() + 5
    while bot._arrivi.empty() and time.monotonic() < fine:
        pass
    assert chiesti and chiesti[0] == 25                       # la richiesta resta aperta: niente attese di un minuto
    risposte = [x[1]["text"] for x in bot.mandati if x[0] == "answerCallbackQuery"]
    assert risposte and risposte[0].startswith("⏳")          # la risposta al pulsante arriva subito
    # Il bot e' in mezzo a un giro: fra uno strumento e l'altro esegue il pulsante.
    bot._pulsanti_subito()
    assert len(bot.mt5.posizioni) == 1 and not bot.proposte
    bot._in_ascolto = False                                   # il filo si ferma



# --- la rete neurale: decide cosa proporre, spiega, e si corregge ---

def _giudizio(entra=True):
    from nvm.vivo.rete_vivo import Giudizio
    return Giudizio(entra, -0.05 if entra else -0.4, 0.61, -0.127,
                    {"direzione D1": ("su", 0.8), "direzione W1": ("giù", 0.6), "direzione MN": ("nessuna", 0.5),
                     "crt H4": ("acquisto", 0.9), "crt D1": ("niente", 0.95)},
                    [("RR al target finale", 0.12), ("il grafico giornaliero", -0.08)],
                    ingressi=(np.zeros((1, 5, 40, 7), np.float32), np.ones((1, 5, 40), bool), np.zeros((1, 18), np.float32)))


def test_la_rete_decide_cosa_proporre_e_spiega_perche(tmp_path, monkeypatch):
    from tests.test_vivo import CapoFinto
    d = _una_decisione()
    d = __import__("dataclasses").replace(d, foto={"setup": None})      # una decisione del metodo delle foto
    bot = _bot(tmp_path, monkeypatch, d, [])
    bot.capo = CapoFinto()
    bot.rete = NS(giudica=lambda x: _giudizio(entra=False))
    monkeypatch.setattr("nvm.vivo.messaggi.proposta", lambda d, scade, grafico, rete=None, tv=True, lasciata=False: "SETUP\n" + "\n".join(rete or []))
    bot._decidi([d], d.r.quando, 3600)
    # La rete lo lascerebbe: niente sul canale operativo, in équipe con «Apri lo stesso» e «Correggi».
    (proposta,) = [x[1] for x in bot.mandati if x[0] == "sendMessage"]
    assert proposta["chat_id"] == "-2" and "LA RETE: LASCEREI" in proposta["text"] and "la frena" in proposta["text"]
    assert [b["text"] for b in proposta["reply_markup"]["inline_keyboard"][0]] == ["✅ Apri lo stesso", "✏️ Correggi"]
    assert bot.stato.seguite[0].rete["entra"] is False and bot.mt5.posizioni == {}
    # Se la prenderebbe: apre da solo e spiega perché, con «Correggi».
    bot.rete = NS(giudica=lambda x: _giudizio(entra=True))
    bot.stato.seguite, bot._prove = [], {}
    bot._decidi([__import__("dataclasses").replace(d, r=__import__("dataclasses").replace(d.r, quando=d.r.quando + 7))],
                d.r.quando + 7, 3600)
    assert len(bot.mt5.posizioni) == 1
    ultima = [x[1] for x in bot.mandati if x[0] == "sendMessage"][-1]
    assert ultima["chat_id"] == "-1" and "PERCHÉ HO APERTO · OANDA:EURUSD" in ultima["text"] and "ENTREREI" not in ultima["text"]
    assert [b["text"] for b in ultima["reply_markup"]["inline_keyboard"][0]] == ["✏️ Correggi"]


def test_con_correggi_si_dice_alla_rete_cosa_ha_visto_male_e_perche(tmp_path, monkeypatch):
    d = _una_decisione()
    arrivi = []
    bot = _bot(tmp_path, monkeypatch, d, arrivi)
    monkeypatch.setattr(time, "time", lambda: d.r.quando + 60)
    bot._proponi(d, None, _giudizio(entra=True))
    (ident,) = bot.proposte
    assert (tmp_path / "rete" / "analisi" / f"{ident}.npz").exists()      # quello che ha visto, per riallenarla
    arrivi.append(_premi(1, "correggi", ident))
    bot.ascolta()
    correggi = [x[1] for x in bot.mandati if x[0] == "sendMessage"][-1]
    assert "CORREGGI LA RETE" in correggi["text"] and correggi["reply_to_message_id"] == 71
    righe = correggi["reply_markup"]["inline_keyboard"]
    assert [b["text"] for b in righe[0]] == ["Il trade: lasciare", "• Il trade: entrare"]
    assert [b["text"] for b in righe[1]] == ["Giorno: giù", "Giorno: nessuna", "• Giorno: su"]
    n_correggi = 900 + [i for i, x in enumerate(bot.mandati, 1) if x[0] == "sendMessage"][-1]
    # Il giorno era ribassista: si preme «Giorno: giù».
    arrivi.append({"update_id": 2, "callback_query": {"id": "q2", "data": righe[1][0]["callback_data"],
                                                      "from": {"first_name": "Marco"},
                                                      "message": {"message_id": n_correggi, "chat": {"id": -1},
                                                                  "text": correggi["text"], "date": 0}}})
    bot.ascolta()
    cambiato = [x[1] for x in bot.mandati if x[0] == "editMessageText"][-1]
    assert "✔ Giorno: giù (la rete diceva «su») — Marco" in cambiato["text"] and cambiato["reply_markup"]
    # E il perché, scritto in risposta al messaggio di «Correggi».
    arrivi.append({"update_id": 3, "message": {"chat": {"id": -1}, "text": "il giorno ha chiuso sotto il DL",
                                               "date": 0, "from": {"first_name": "Marco"},
                                               "reply_to_message": {"message_id": n_correggi}}})
    bot.ascolta()
    assert "Annotato" in [x[1] for x in bot.mandati if x[0] == "sendMessage"][-1]["text"]
    righe_file = [json.loads(r) for r in (tmp_path / "rete" / "correzioni.jsonl").read_text().splitlines()]
    assert righe_file[0]["domanda"] == "direzione D1" and righe_file[0]["giusta"] == "giù" and righe_file[0]["rete"] == "su"
    assert righe_file[1]["spiegazione"] == "il giorno ha chiuso sotto il DL" and righe_file[1]["ident"] == ident


def test_la_sera_si_vede_come_va_la_rete(tmp_path, monkeypatch):
    import vivo
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    bot = object.__new__(vivo.Bot)
    bot.stato = Stato()
    def seguita(erre, entra):
        s = Seguita("k", "EURUSD", "D1", "H1", "long", 0, 1.0, 0.9, 1.1, 1.2, 0, False, [], 1, 2, 0, 0.5, 0.5, 0,
                    rete={"entra": entra})
        s.esito = {"erre": erre, "quando": 500}
        return s
    bot.stato.seguite = [seguita(1.5, True), seguita(-1.0, True), seguita(-1.0, False), seguita(2.0, False)]
    testo = bot._pagella_rete(0, 1000)
    assert "4 setup finiti, ci ha preso 2 volte" in testo and "2 trade, +0.50 R" in testo
    assert bot._pagella_rete(1000, 2000) == ""


def test_la_rete_vera_giudica_un_setup_e_spiega_cosa_vede():
    pytest.importorskip("torch")
    from nvm.vivo.rete_vivo import Rete
    from nvm.vivo import giro as G
    from tests.test_foto import ORA as ORA_F, _foto_base, _ore
    from tests.test_vivo import CapoFinto
    ore, n3 = _foto_base()
    righe = [(int(t), *(float(x) * ore.punto for x in b)) for t, b in zip(ore.t, ore.bid)]
    prima = [(int(ore.t[0]) - k * ORA_F, 1.1000, 1.1003, 1.0997, 1.1000) for k in range(240, 0, -1)]
    euro = _ore(prima + righe, "EURUSD")
    # Su EURUSD si entra solo col pattern del DXY (20/10/2026): il DXY e' lo specchio dell'euro, prende il DH e rientra.
    dxy = _ore([(t, 100 / o, 100 / l, 100 / h, 100 / c) for t, o, h, l, c in prima + righe], "DXY", spread=0.0)
    (d,) = G.occasioni_foto("EURUSD", euro, n3, n3, CapoFinto(), {"EURUSD": euro, "DXY": dxy})
    assert d.foto["setup"].dal_dxy and d.foto["dxy"].presi
    rete, perche = Rete.carica()
    assert rete is not None, perche
    g = rete.giudica(d)
    # Sui setup con tutte le regole delle foto entra sempre; sugli altri decide la sua stima.
    assert set(g.occhi) >= {"direzione D1", "crt H4"} and 0 <= g.vince <= 1 and g.entra == (g.regole or g.erre >= g.soglia)
    # Nato dal CRT del DXY: le regole le da' lui, la rete non lo lascia (21/10/2026).
    assert g.regole and g.entra
    # Sul CRT a 4 ore della foto base gli occhi vedono il CRT d'acquisto.
    assert g.occhi["crt H4"][0] == "acquisto"
    testo = "\n".join(g.righe())
    assert "LA RETE:" in testo and "Gli occhi vedono" in testo and g.ingressi[0].shape == (1, 5, 40, 7)



def test_se_pytorch_non_parte_il_bot_va_avanti_senza_rete(monkeypatch):
    """Sulla VPS, 12/10/2026: PyTorch installato ma Windows non lo avvia (WinError 1114 su c10.dll). La rete non deve
    fermare il bot: si spegne e si dice perche'."""
    import builtins
    from nvm.vivo.rete_vivo import Rete
    vera = builtins.__import__

    def finta(nome, *a, **k):
        if nome == "torch":
            raise OSError("[WinError 1114] A dynamic link library (DLL) initialization routine failed")
        return vera(nome, *a, **k)
    monkeypatch.setattr(builtins, "__import__", finta)
    monkeypatch.delitem(__import__("sys").modules, "torch", raising=False)
    rete, perche = Rete.carica()
    assert rete is None and "vc_redist" in perche


def test_in_automatico_sui_prezzi_del_broker_decide_la_rete(tmp_path, monkeypatch):
    """Il proprietario, 12/10/2026: *"metti tutto automatico sul bot, niente più richieste"*. Sui prezzi del broker
    (senza TradingView) il bot apre da solo quello che la rete prenderebbe, con la spiegazione e «Correggi»; quello che
    la rete lascia va in équipe con «Apri lo stesso»."""
    import dataclasses
    from tests.test_vivo import CapoFinto
    d = _una_decisione()
    bot = _bot(tmp_path, monkeypatch, d, [])
    bot.fonte = None                                          # prezzi del broker: si apre in automatico
    bot.capo = CapoFinto()
    bot.rete = NS(giudica=lambda x: _giudizio(entra=True))
    bot._prove = {}
    bot._giudica = lambda x: _giudizio(entra=True)
    bot._decidi([d], d.r.quando, 3600)
    assert len(bot.mt5.posizioni) == 1                        # aperto da solo
    spiegazione = [x[1] for x in bot.mandati if x[0] == "sendMessage"][-1]
    assert "PERCHÉ HO APERTO" in spiegazione["text"] and \
        spiegazione["reply_markup"]["inline_keyboard"][0][0]["text"] == "✏️ Correggi"
    # La rete lo lascerebbe: niente ordine, in équipe con «Apri lo stesso».
    bot2 = _bot(tmp_path / "2", monkeypatch, d, [])
    bot2.fonte, bot2.capo, bot2._prove = None, CapoFinto(), {}
    bot2._giudica = lambda x: _giudizio(entra=False)
    d2 = dataclasses.replace(d, r=dataclasses.replace(d.r, quando=d.r.quando + 7))
    bot2._decidi([d2], d2.r.quando, 3600)
    assert bot2.mt5.posizioni == {}
    lasciata = [x[1] for x in bot2.mandati if x[0] == "sendMessage"][-1]
    assert lasciata["chat_id"] == "-2" and "📊 SETUP" in lasciata["text"] and "Apri lo stesso" in lasciata["text"]
    assert bot2.stato.saltate.get("la rete neurale lo lascia") == 1



def test_se_tradingview_chiede_di_rallentare_si_aspetta_e_si_riprova(tmp_path):
    """23:01 del 12/10/2026: "TradingView chiede di rallentare (troppe richieste)" con 35 grafici."""
    barre = [{"t": 3600, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 3}]
    server = ServerFinto(barre)
    server.scaduta = True                                    # la sessione non scade
    risposte = iter([429, 429])
    vero = server.__call__

    def con_rallenta(url, dati, intestazioni):
        if json.loads(dati).get("method") == "tools/call":
            codice = next(risposte, None)
            if codice:
                return codice, {}, b""
        return vero(url, dati, intestazioni)
    dormite = []
    tv = TradingView(_accesso(tmp_path), posta=con_rallenta, intervallo=0.0, dormi=dormite.append)
    assert tv.candele("FX_IDC:EURUSD", 3600, 10) == barre and dormite == [20, 60]
    tv2 = TradingView(_accesso(tmp_path / "2"), posta=lambda u, d, i: (429, {}, b"") if "tools/call" in d.decode()
                      else vero(u, d, i), intervallo=0.0, dormi=lambda s: None)
    with pytest.raises(Exception, match="rallentare"):
        tv2.candele("FX_IDC:EURUSD", 3600, 10)


def test_la_quota_giornaliera_finita_ferma_le_richieste_fino_a_mezzanotte_utc(tmp_path):
    """Il server, 20/10/2026 alle 16:07 UTC: *"TOOL_QUOTA_EXCEEDED - Tool call quota exceeded (Daily tool-call quota
    for this user is exhausted. It resets at 00:00 UTC, in about 7h 53m; do not retry"*."""
    adesso = [float(utc(2026, 10, 20, 16, 7))]
    barre = [{"t": 3600, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 3}]
    server = ServerFinto(barre)
    server.scaduta = True
    finita = [True]
    vero = server.__call__
    testo = ("tool_pre_invoke blocked by plugin ToolQuotaPlugin: TOOL_QUOTA_EXCEEDED - Tool call quota exceeded "
             "(Daily tool-call quota for this user is exhausted. It resets at 00:00 UTC, in about 7h 53m; do not retry)")

    def con_quota(url, dati, intestazioni):
        m = json.loads(dati)
        if m.get("method") == "tools/call" and finita[0]:
            corpo = json.dumps({"jsonrpc": "2.0", "id": m["id"],
                                "result": {"isError": True, "content": [{"type": "text", "text": testo}]}})
            return 200, {"Content-Type": "application/json"}, corpo.encode()
        return vero(url, dati, intestazioni)
    tv = TradingView(_accesso(tmp_path), posta=con_quota, intervallo=0.0, orologio=lambda: adesso[0])
    with pytest.raises(QuotaFinita) as preso:
        tv.candele("FX_IDC:USDJPY", 3600, 10)
    assert preso.value.fino_a == utc(2026, 10, 21) + MARGINE_QUOTA and tv.ferma and tv.chiamate_oggi == 1
    # Fino ad allora nessuna richiesta parte (*"do not retry"*).
    prima = len(server.chiamate)
    for simbolo in ("FX_IDC:USDCAD", "FX_IDC:AUDCAD"):
        with pytest.raises(QuotaFinita):
            tv.candele(simbolo, 3600, 10)
    assert len(server.chiamate) == prima
    # Dopo la mezzanotte UTC (e il margine) si riparte, e il conto del giorno ricomincia.
    finita[0] = False
    adesso[0] = utc(2026, 10, 21) + MARGINE_QUOTA + 1
    assert tv.candele("FX_IDC:USDJPY", 3600, 10) == barre and not tv.ferma and tv.chiamate_oggi == 1
    # Gli altri errori non sono la quota.
    assert fine_quota("get_ohlcv: symbol not found", adesso[0]) is None
    assert fine_quota("Tool call quota exceeded", float(utc(2026, 10, 20, 23, 0))) == utc(2026, 10, 21) + MARGINE_QUOTA


def test_su_tradingview_i_quarti_d_ora_si_chiedono_a_turno(monkeypatch):
    import vivo
    from nvm.vivo import giro as il_giro
    monkeypatch.setattr(il_giro, "METODO", "candela 3")      # col metodo delle foto arrivano da MT5
    monkeypatch.setattr(vivo, "giro_orario", lambda *a, **k: [])
    chieste = []
    bot = object.__new__(vivo.Bot)
    bot.fonte = NS(barre=lambda s, quante, passo: chieste.append((s, quante)) or vivo.Minuti.vuoti(s, 900))
    bot.strumenti = [f"S{i}" for i in range(8)]
    bot.fini = {s: vivo.Minuti.vuoti(s, 900) for s in bot.strumenti}
    bot.stato = Stato()
    bot.stato.ultimo_quarto = 0
    bot.terminale = NS(barre=lambda *a: pytest.fail("non da MT5"))
    bot.basi = {s: vivo.Minuti.vuoti(s, 3600) for s in bot.strumenti}
    bot.capo = None
    for nome in ("uscite", "parla", "_decidi", "gemelli"):
        setattr(bot, nome, lambda *a: None)
    bot.giro_veloce(900 * 5)                                 # turno 1: gli strumenti 1 e 5
    assert chieste == [("S1", 12), ("S5", 12)]


# --- le candele di TradingView cosi' come sono (13/10/2026) ---

def _ora_italiana(anno, mese, giorno, ora):
    import datetime as dt
    from zoneinfo import ZoneInfo
    return int(dt.datetime(anno, mese, giorno, ora, tzinfo=ZoneInfo("Europe/Rome")).timestamp())


def test_l_orario_del_grafico_si_legge_dalle_sue_candele_a_4_ore():
    """Il proprietario, 13/10/2026: *"i grafici che noi abbiamo collegato già vanno 0, 4, 8, 12, 16, 20"*."""
    from nvm.vivo.tradingview import ora_di_sessione
    mezzanotte = _ora_italiana(2026, 10, 5, 0)
    assert ora_di_sessione([mezzanotte + k * 4 * 3600 for k in range(60)]) == "18"       # 0-4-8 italiane
    assert ora_di_sessione([mezzanotte - 3600 + k * 4 * 3600 for k in range(60)]) == "17"  # 23-3-7, come MT5
    assert ora_di_sessione([utc(2026, 10, 20) + k * 4 * 3600 for k in range(80)]) is True  # UTC, anche col cambio d'ora
    assert ora_di_sessione([mezzanotte + k * 4 * 3600 + 1800 for k in range(60)]) is None  # alle mezze: non si capisce


def test_le_candele_di_tradingview_restano_come_sono():
    from nvm.dati import candele as C
    from nvm.tempo import TF
    from nvm.vivo.tradingview import candele_tv
    C.SESSIONI["EURUSD"] = "18"
    t0 = _ora_italiana(2026, 10, 5, 0)
    barre = [{"t": t0 + k * 4 * 3600, "o": 1.10 + k / 1000, "h": 1.12, "l": 1.09, "c": 1.11} for k in range(7)]
    c = candele_tv("EURUSD", TF.H4, barre, t0 + 6 * 4 * 3600 + 60)
    # Le 4 ore alle 0, 4, 8, 12, 16, 20 italiane, coi prezzi di TradingView; l'ultima (in formazione) no.
    assert list(c.inizio) == [t0 + k * 4 * 3600 for k in range(6)] and list(c.fine) == [t0 + k * 4 * 3600 for k in range(1, 7)]
    assert c.bid[3].tolist() == [1.103, 1.12, 1.09, 1.11]
    # Le giornaliere segnate con la data (mezzanotte UTC) stanno nella loro giornata, che apre alle 0 italiane.
    giorni = [{"t": utc(2026, 10, 5 + k), "o": 1, "h": 2, "l": 0.5, "c": 1.5} for k in range(3)]
    g = candele_tv("EURUSD", TF.D1, giorni, utc(2026, 10, 9))
    assert list(g.inizio) == [_ora_italiana(2026, 10, 5 + k, 0) for k in range(3)]


def test_bot_e_rete_vedono_le_candele_di_tradingview_e_non_quelle_costruite():
    """Il proprietario, 13/10/2026: un CRT a 4 ore di EURUSD aperto con gli orari di MT5, che su TradingView non era
    ancora finito. Con le candele di TradingView il quadro (del bot e della rete) ha le sue, anche nei prezzi."""
    from nvm.agenti import foto
    from nvm.dati import candele as C
    from nvm.tempo import TF
    from nvm.vivo.tradingview import candele_tv
    C.SESSIONI["EURUSD"] = "18"
    t0 = _ora_italiana(2026, 10, 5, 0)
    ore = minuti("EURUSD", [{"t": t0 + k * 3600, "o": 1.1, "h": 1.101, "l": 1.099, "c": 1.1} for k in range(48)], 3600,
                 t0 + 48 * 3600)
    quattro = candele_tv("EURUSD", TF.H4, [{"t": t0 + k * 4 * 3600, "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15}
                                           for k in range(13)], t0 + 48 * 3600)
    mesi = candele_tv("EURUSD", TF.MN, [{"t": utc(2026, m, 1), "o": 1.0 + m / 100, "h": 1.3, "l": 0.9, "c": 1.1}
                                        for m in range(1, 10)], t0)
    q = foto.Quadro.da(ore, t0 + 48 * 3600, {TF.H4: quattro, TF.MN: mesi})
    assert list(q.candele[TF.H4].inizio) == list(quattro.inizio) and q.candele[TF.H4].bid[0, 1] == 1.2
    assert q.candele[TF.H1].inizio[0] == t0
    # I 3 mesi, che TradingView non da' sempre, sono i suoi mesi messi insieme: gennaio-marzo, aprile-giugno.
    trimestri = q.candele[TF.Q3]
    assert trimestri.bid[0].tolist() == [1.01, 1.3, 0.9, 1.1] and len(trimestri) == 3


def test_il_bot_prende_ogni_timeframe_da_tradingview_e_lo_riprende_quando_chiude(tmp_path, monkeypatch):
    import vivo
    from nvm.dati import candele as C
    from nvm.tempo import TF
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    t0 = _ora_italiana(2026, 10, 5, 0)
    adesso = [t0 + 20 * 4 * 3600 + 60]       # giovedi alle 8 italiane
    chieste = []

    def grezze(s, tf, quante):
        chieste.append((s, tf, quante))
        if tf is TF.H6:
            raise vivo.RispostaRifiutata("OANDA:EURUSD 6h: intervallo sconosciuto")
        passo = vivo.DURATE[tf]
        ultima = adesso[0] - adesso[0] % 3600
        return [{"t": ultima - k * passo, "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15}
                for k in range(min(quante, 40) - 1, -1, -1)] if tf is not TF.H4 else \
            [{"t": t0 + k * 4 * 3600, "o": 1.1, "h": 1.2, "l": 1.0, "c": 1.15}
             for k in range(int((adesso[0] - t0) // (4 * 3600)) + 1)]
    allarmi = []
    bot = object.__new__(vivo.Bot)
    bot.fonte = NS(grezze=grezze, esiste=lambda s: False, simboli={"EURUSD": "OANDA:EURUSD"})
    bot.strumenti, bot.lunghe = ["EURUSD"], {}
    bot.allarme = allarmi.append
    C.SESSIONI["EURUSD"] = "17"           # come MT5: le candele di TradingView dicono un'altra cosa
    bot._candele_tradingview(adesso[0])
    assert C.SESSIONI["EURUSD"] == "18"
    d = bot.lunghe["EURUSD"]
    assert set(d) == set(vivo.DIRETTE) - {TF.H6} and TF.H6 in bot._tf_rifiutati
    assert any("non dà le candele 6h" in a for a in allarmi)
    assert all(int(x) % (4 * 3600) == (t0 % (4 * 3600)) for x in d[TF.H4].inizio)
    # Nella stessa candela non si richiede niente; chiusa la 4 ore, si riprendono solo le ultime.
    chieste.clear()
    bot._candele_tradingview(adesso[0] + 600)
    assert chieste == []
    bot._candele_tradingview(adesso[0] + 4 * 3600)          # alle 12 chiudono la 4 ore e la 12 ore
    assert [(tf, q) for _, tf, q in chieste] == [(TF.H4, 5), (TF.H12, 5)]
    # Dopo un riavvio le candele e gli orari si ritrovano su disco.
    C.SESSIONI.clear()
    bot2 = object.__new__(vivo.Bot)
    bot2.fonte, bot2.lunghe = bot.fonte, {}
    bot2._leggi_candele_tradingview()
    assert C.SESSIONI["EURUSD"] == "18" and len(bot2.lunghe["EURUSD"][TF.H4]) == len(bot.lunghe["EURUSD"][TF.H4])


def test_l_orario_del_dxy_si_legge_anche_con_la_candela_della_domenica_fuori_griglia():
    """23/10/2026: sul DXY di Capital.com la settimana apre la domenica sera con una candela a 4 ore fuori griglia (una
    ogni 30 circa). Col 98% richiesto l'orario non si capiva, il bot usava le 18 di New York (0-4-8 italiane, gli orari
    delle coppie) e alle 00:00 ha visto un "CRT a 6 ore del DXY", che apre alle 2."""
    from nvm.vivo.tradingview import ora_di_sessione
    t = []
    for w in range(100):
        domenica = utc(2024, 10, 20) + w * 7 * 86400
        t.append(domenica + 22 * 3600)                                         # l'apertura della settimana
        t += [domenica + g * 86400 + h * 3600 for g in range(1, 6) for h in range(0, 24, 4)]
    assert ora_di_sessione(t[-3000:]) is True
    # Le coppie dalle 18 di New York restano "18" anche con qualche candela storta.
    mezzanotte = _ora_italiana(2026, 10, 5, 0)
    coppia = [mezzanotte + k * 4 * 3600 for k in range(60)] + [mezzanotte + 3600]
    assert ora_di_sessione(coppia) == "18"
