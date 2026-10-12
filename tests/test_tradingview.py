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
from nvm.vivo.tradingview import (REGISTRA, TOKEN, Accesso, AccessoScaduto, Fonte, TradingView, _barre, _messaggi,
                                  leggi_simboli, minuti)
from tests.mt5_finto import MT5Finto
from tests.test_vivo import _una_decisione


# --- i grafici scelti nel .env ---

def test_i_grafici_si_scrivono_come_su_tradingview(tmp_path):
    simboli, sbagliati = leggi_simboli("OANDA:EURUSD, oanda:gbpusd;OANDA:US30USD=US30  FX:BOH, EURUSD")
    assert simboli == [("OANDA:EURUSD", "EURUSD"), ("OANDA:GBPUSD", "GBPUSD"), ("OANDA:US30USD", "US30")]
    assert sbagliati == ["FX:BOH", "EURUSD"]
    (tmp_path / ".env").write_text("TRADINGVIEW_SIMBOLI=OANDA:EURUSD\nTRADINGVIEW_DXY=tvc:dxy\n", encoding="utf-8")
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
                      posta=lambda url, dati: bot.mandati.append((url.rsplit("/", 1)[-1], dati)))
    return bot


def _premi(numero, azione, ident, chi="Marco"):
    return {"update_id": numero, "callback_query": {"id": f"q{numero}", "data": f"{azione}:{ident}", "from": {"first_name": chi},
                                                    "message": {"message_id": 70 + numero, "chat": {"id": -1},
                                                                "text": "📺 SETUP", "date": 0}}}


def test_su_tradingview_il_bot_propone_e_non_apre_da_solo(tmp_path, monkeypatch):
    from tests.test_vivo import CapoFinto
    d = _una_decisione()
    bot = _bot(tmp_path, monkeypatch, d, [])
    bot.capo = CapoFinto()
    bot._decidi([d], d.r.quando, 3600)
    assert bot.mt5.posizioni == {} and not bot.stato.vive                         # niente ordini
    (ident,) = bot.proposte
    proposta = next(x for x in bot.mandati if x[0] == "sendMessage")[1]
    assert "OANDA:EURUSD" in proposta["text"] and "Senza il vostro «Apri» non apro niente" in proposta["text"]
    assert [b["callback_data"] for b in proposta["reply_markup"]["inline_keyboard"][0]] == [f"apri:{ident}", f"lascia:{ident}"]
    (s,) = bot.stato.seguite
    assert s.chiave == d.chiave and not s.entrata                              # seguita sulla carta


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
