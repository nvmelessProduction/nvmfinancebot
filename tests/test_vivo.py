"""Il bot dal vivo, con un MT5 finto e Telegram muto."""

from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from nvm.agenti.cacciatore import Verso
from nvm.agenti.capo import COLONNE, Capo
from nvm.agenti.rischio import esiti, kelly
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import opera
from nvm.tempo import utc
from nvm.vivo.ambiente import Impostazioni, impostazioni
from nvm.vivo.esecutore import MAGIC, Esecutore
from nvm.vivo.giro import COPPIE, giro
from nvm.vivo.messaggi import pareri
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.stato import Seguita
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import Terminale
from tests.mt5_finto import BARRA, MT5Finto

ORA = 3600


def ore_finte(strumento="EURUSD", dal=utc(2025, 1, 1), giorni=200, seme=3) -> Minuti:
    """Orarie di una passeggiata casuale, in punti, con 1 pip di spread."""
    rng = np.random.default_rng(seme)
    t = np.arange(dal, dal + giorni * 86400, ORA, dtype=np.int64)
    chiusure = 110000 + np.cumsum(rng.normal(0, 60, len(t)))
    aperture = np.r_[110000, chiusure[:-1]]
    rumore = np.abs(rng.normal(0, 30, (len(t), 2)))
    bid = np.rint(np.c_[aperture, np.maximum(aperture, chiusure) + rumore[:, 0],
                        np.minimum(aperture, chiusure) - rumore[:, 1], chiusure]).astype(np.int64)
    v = np.ones(len(t), np.float32)
    return Minuti(strumento, t, bid, bid + 10, v, v.copy(), passo=ORA)


class CapoFinto:
    """Un Capo che dice sempre le stesse probabilita'."""

    def __init__(self, p1=0.6, q=0.5):
        self.p1, self.q = p1, q

    def probabilita(self, x):
        return np.full(len(x), self.p1), np.full(len(x), self.q)

    def valore_atteso(self, x, rr1, rr2, costi):
        return self.p1 * (0.5 * rr1 + 0.5 * self.q * rr2) - (1 - self.p1) - costi

    # Nessuna somiglianza a Romeo imparata.
    romeo = None

    def somiglianza(self, x):
        return np.ones(len(np.atleast_2d(x)))


# --- impostazioni e Telegram ---

def test_il_token_non_si_vede_mai(tmp_path):
    (tmp_path / ".env").write_text('TELEGRAM_TOKEN="123:segreto"\nTELEGRAM_CHAT_ID=-100a, -100b\nTELEGRAM_CHAT_EQUIPE=-100c\n# commento\n')
    imp = impostazioni(tmp_path, ambiente={})
    assert imp.token == "123:segreto" and imp.chat_operativo == ("-100a", "-100b") and imp.chat_equipe == ("-100c",)
    assert "segreto" not in repr(imp)


def test_senza_token_telegram_stampa_soltanto():
    mandati, stampati = [], []
    tg = Telegram(Impostazioni(chat_operativo=("1",)), invia=lambda c, t: mandati.append(t), stampa=stampati.append)
    tg.operativo("ciao")
    assert mandati == [] and stampati == ["[operativo] ciao"]


def test_con_token_ogni_canale_va_alle_sue_chat():
    mandati = []
    imp = Impostazioni(token="x", chat_operativo=("op",), chat_equipe=("eq1", "eq2"))
    tg = Telegram(imp, invia=lambda c, t: mandati.append((c, t)), stampa=lambda _: None)
    tg.operativo("a")
    tg.equipe("b")
    assert mandati == [("op", "a"), ("eq1", "b"), ("eq2", "b")]


def test_i_certificati_si_controllano_sempre():
    import ssl
    from nvm.vivo.telegram import contesto
    c = contesto()
    assert c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname


# --- MT5: l'ora del server e le orarie ---

def _terminale_con_barre(adesso, scarto=3):
    m = MT5Finto(scarto=scarto)
    ora = adesso // ORA * ORA
    t_server = np.arange(ora - 5 * ORA, ora + ORA, ORA) + scarto * ORA  # l'ultima e' quella in formazione
    b = np.zeros(len(t_server), BARRA)
    b["time"] = t_server
    b["open"], b["high"], b["low"], b["close"] = 1.1, 1.102, 1.099, 1.101
    b["spread"] = 12
    m.barre["EURUSD"] = b
    orologio = [float(adesso)]
    m.tick["EURUSD"] = NS(time=adesso + scarto * ORA - 5, bid=1.1, ask=1.1001)
    return m, orologio


def test_lo_scarto_si_misura_solo_col_tick_che_avanza():
    adesso = utc(2026, 9, 24, 10, 30)
    m, orologio = _terminale_con_barre(adesso)
    t = Terminale(mt5=m, orologio=lambda: orologio[0], dormi=lambda s: None)
    t._scarto_dal_tick("EURUSD")
    assert t.scarto is None  # primo sguardo
    t._scarto_dal_tick("EURUSD")
    assert t.scarto is None  # tick fermo: mercato chiuso
    m.tick["EURUSD"] = NS(time=adesso + 3 * ORA - 1, bid=1.1, ask=1.1001)
    t._scarto_dal_tick("EURUSD")
    assert t.scarto == 3


def test_le_orarie_arrivano_in_utc_e_senza_quella_in_formazione():
    adesso = utc(2026, 9, 24, 10, 30)
    m, orologio = _terminale_con_barre(adesso)
    t = Terminale(mt5=m, orologio=lambda: orologio[0])
    t.scarto = 3
    o = t.orarie("EURUSD", 100)
    assert int(o.t[-1]) == utc(2026, 9, 24, 9)  # la 10:00-11:00 e' ancora aperta
    assert o.passo == 3600 and int(o.bid[-1, 3]) == 110100 and int(o.ask[-1, 3]) == 110112


# --- il giro fa quello che fa lo storico ---

def test_il_giro_decide_come_lo_storico():
    base = ore_finte()
    capo = CapoFinto()
    inizio, fine = int(base.t[0]) + 150 * 86400, int(base.t[-1])
    attese = set()
    for alto, basso in COPPIE:
        alte, basse = costruisci(base, alto).chiuse_entro(fine + ORA), costruisci(base, basso).chiuse_entro(fine + ORA)
        attese |= {(r.alto_tf, r.verso, r.quando, r.colpo) for r in opera(alte, basse, inizio + 1, fine + 1)}
    viste, dal = set(), inizio + 1
    for adesso in range(inizio + 12 * ORA, fine + 1, 12 * ORA):
        viste |= {(d.r.alto_tf, d.r.verso, d.r.quando, d.r.colpo) for d in giro({"EURUSD": base}, dal, adesso, capo)}
        dal = adesso + 1
    fuori = {a for a in attese if a[2] < dal}
    assert fuori, "la passeggiata deve dare qualche decisione"
    assert viste == fuori


# --- il Rischio ---

def test_kelly_di_una_scommessa_semplice():
    # 50% di vincere 2 R, 50% di perdere 1 R: Kelly = 0,5 - 0,5/2 = 0,25.
    e = esiti(0.5, 1.0, 2.0, 2.0, 0.0, "primo target")
    assert kelly(e) == pytest.approx(0.25, abs=0.002)
    assert kelly(esiti(0.2, 0.0, 1.0, 2.0, 0.0)) == 0.0


# --- l'Esecutore ---

def _una_decisione():
    base = ore_finte()
    d = giro({"EURUSD": base}, int(base.t[0]) + 100 * 86400, int(base.t[-1]), CapoFinto())
    return next(x for x in d if x.entra)


def test_la_prova_del_collegamento_non_manda_ordini_e_spiega_i_rifiuti():
    from nvm.vivo import messaggi
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=1.1, ask=1.1001)
    t = Terminale(mt5=m)
    e = t.prova_ordine("EURUSD", 1)
    assert e.ok and m.richieste == [] and m.posizioni == {}
    assert not t.prova_ordine("GBPUSD", 1).ok        # simbolo che il conto non ha
    m.order_check = lambda r: NS(retcode=10027, comment="AutoTrading disabled by client")
    rifiuto = t.prova_ordine("EURUSD", 1)
    assert not rifiuto.ok and "Algo Trading" in rifiuto.messaggio
    testo = messaggi.collegamento([("EURUSD", True, e.messaggio), ("GBPUSD", False, rifiuto.messaggio)], 2)
    assert "✅ EURUSD" in testo and "❌ GBPUSD" in testo and "aperte adesso: 2" in testo
    tutto_bene = messaggi.collegamento([("EURUSD", True, e.messaggio), ("GBPUSD", True, e.messaggio)], 0)
    assert "tutti e 2 gli strumenti" in tutto_bene


def test_apre_due_meta_sposta_a_pareggio_e_chiude():
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, fatto = e.apri(d, t.conto())
    assert viva is not None and len(viva.tickets) == 2, fatto.testo
    a, b = viva.tickets
    assert m.posizioni[a].tp == round(d.op.tp1, 5) and m.posizioni[b].tp == round(d.op.tp2, 5)
    assert m.posizioni[a].sl == m.posizioni[b].sl == round(d.op.stop, 5)
    assert ("COMPRO" in fatto.testo or "VENDO" in fatto.testo) and "Perché" in fatto.testo

    m.chiudi(a, d.op.tp1)  # il broker incassa il primo target
    vive, fatti = e.sorveglia([viva])
    assert vive and vive[0].pareggio_fatto
    assert m.posizioni[b].sl == round(viva.ingresso, 5)
    assert "primo obiettivo" in fatti[0].testo

    m.chiudi(b, viva.ingresso)  # il resto torna a pareggio
    vive, fatti = e.sorveglia(vive)
    assert vive == [] and "chiusa" in fatti[0].testo


def test_su_un_conto_reale_non_apre():
    d = _una_decisione()
    m = MT5Finto(demo=False)
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso)
    t = Terminale(mt5=m)
    viva, fatto = Esecutore(t).apri(d, t.conto())
    assert viva is None and m.richieste == [] and "non è un demo" in fatto.testo


def test_se_il_prezzo_e_gia_oltre_lo_stop_non_apre():
    d = _una_decisione()
    m = MT5Finto()
    oltre = d.op.stop + (0.001 if d.r.verso is Verso.SHORT else -0.001)
    m.tick["EURUSD"] = NS(time=0, bid=oltre, ask=oltre)
    t = Terminale(mt5=m)
    viva, fatto = Esecutore(t).apri(d, t.conto())
    assert viva is None and m.richieste == [] and fatto.equipe


# --- l'equipe e la riunione ---

def test_ogni_agente_dice_la_sua():
    testo = pareri(_una_decisione())
    for agente in ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Capo"):
        assert agente in testo


def test_il_capo_salvato_da_le_stesse_stime():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(500, len(COLONNE)))
    tp1 = rng.random(500) < 0.5
    tp2 = tp1 & (rng.random(500) < 0.4)
    capo = Capo.allena(x, tp1, tp2)
    copia = Capo.da_dati(capo.come_dati())
    assert np.allclose(capo.probabilita(x[:10])[0], copia.probabilita(x[:10])[0])


def test_la_riunione_riaddestra_il_capo_con_i_dati_dal_vivo():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(400, len(COLONNE)))
    storico = Storico(x, rng.random(400) < 0.5, rng.random(400) < 0.2)
    capo = Capo.allena(storico.x, storico.tp1, storico.tp2)
    seguite = [
        Seguita("k", "EURUSD", "D1", "H1", "short", 100 + i, 1.1, 1.101, 1.099, 1.098, 10**9, bool(i % 2),
                list(rng.normal(size=len(COLONNE))), 1.0, 2.0, 0.01, 0.5, 0.4, 0.1,
                esito={"uscita": "stop", "erre": -1.0, "quando": 200 + i, "tp1": False, "tp2": False})
        for i in range(30)
    ]
    testo, nuovo, parte = riunione(seguite, capo, storico, 0, "2026-S39")
    assert "Riunione" in testo and "30 dal vivo" in testo
    assert not np.allclose(nuovo.primo.pesi, capo.primo.pesi)
    assert 0 < parte <= 1


def test_la_riunione_rifa_anche_la_somiglianza_a_romeo_e_le_decisioni_vecchie_non_la_rompono():
    rng = np.random.default_rng(2)
    n = 600
    x = rng.integers(0, 2, size=(n, len(COLONNE))).astype(float)
    storico = Storico(x, rng.random(n) < 0.4, rng.random(n) < 0.15)
    storico.romeo_x, storico.romeo_y = x, (x[:, COLONNE.index("ora di Romeo: Londra")] == 1) & (rng.random(n) < 0.1)
    capo = Capo.allena(storico.x, storico.tp1, storico.tp2)
    # Una decisione registrata prima delle colonne alla Romeo: 22 colonne invece di 26.
    vecchia = Seguita("k", "EURUSD", "D1", "H1", "short", 100, 1.1, 1.101, 1.099, 1.098, 10**9, False,
                      [0.0] * 22, 1.0, 2.0, 0.01, 0.5, 0.4, 0.1,
                      esito={"uscita": "stop", "erre": -1.0, "quando": 200, "tp1": False, "tp2": False})
    testo, nuovo, _ = riunione([vecchia], capo, storico, 0, "2026-S39")
    assert nuovo.romeo is not None
    assert "Romeo" in testo
    pesi = dict(nuovo.fiducia_romeo())
    assert max(pesi, key=pesi.get) == "ora di Romeo: Londra"


def test_il_rischio_impara_a_fidarsi_meno_se_il_capo_sbaglia():
    from nvm.agenti.rischio import impara_parte
    f = np.full(200, 0.3)
    buone = np.tile([2.0, -1.0], 100)       # vince davvero: si fida molto
    cattive = np.tile([1.2, -1.0], 100)     # vince poco: si fida meno
    assert impara_parte(f, buone) > impara_parte(f, cattive)


def test_il_diario_parla_come_una_persona():
    from nvm.vivo.dialogo import firma
    x = np.zeros(len(COLONNE))
    x[COLONNE.index("coppia D1-H1")] = 1
    x[COLONNE.index("ora 09-13")] = 1
    x[COLONNE.index("key level: fvg")] = 1
    x[COLONNE.index("RR1")] = 2.4
    assert firma("Cacciatore", x) == "giornaliero → 1 ora"
    assert firma("Orario", x) == "09–13 NY"
    assert firma("Key level", x) == "FVG"
    assert firma("Livelli", x) == "primo target fra 2 e 3 R"
    assert firma("Grilletto", x) == "primo colpo, senza liquidità presa"


def test_con_codice_nuovo_su_github_il_bot_si_fa_riavviare(tmp_path, monkeypatch):
    import pytest
    import vivo
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    bot = object.__new__(vivo.Bot)
    bot.versione, bot._allarmi = "abc", {}
    monkeypatch.setattr(vivo, "_versione_nuova", lambda partito_da: "")
    bot.aggiorna_se_serve()                      # niente di nuovo: continua
    monkeypatch.setattr(vivo, "_versione_nuova", lambda partito_da: "Romeo nell'equipe")
    with pytest.raises(SystemExit) as uscita:
        bot.aggiorna_se_serve()
    assert uscita.value.code == vivo.AGGIORNATO
    assert (tmp_path / "riavvio").read_text(encoding="utf-8") == "Romeo nell'equipe"
    assert vivo.CONTROLLO_VERSIONE <= 120


# --- Romeo dal vivo: il comando /romeo ---

from nvm.vivo.romeo_vivo import EntrataDiRomeo, confronta as confronta_romeo, etichette, leggi_comando


def test_il_comando_romeo_si_legge_anche_scritto_in_modi_diversi():
    e = leggi_comando("/romeo EURUSD compra 1.0765 stop 1.0760 target 1.0800", 10)
    assert (e.strumento, e.verso, e.ingresso, e.stop, e.target, e.quando) == ("EURUSD", "long", 1.0765, 1.076, 1.08, 10)
    e = leggi_comando("/romeo@nvm_bot gbpusd vendo a 1,2541 sl 1,2546", 10)
    assert (e.strumento, e.verso, e.ingresso, e.stop, e.target) == ("GBPUSD", "short", 1.2541, 1.2546, None)
    assert leggi_comando("/romeo oro buy 2450 sl 2445", 0).strumento == "XAUUSD"
    # Quello che non torna non si indovina: si spiega.
    assert "sbagliata" in leggi_comando("/romeo EURUSD compra 1.0765 stop 1.0770", 0)
    assert "compra o vende" in leggi_comando("/romeo EURUSD 1.0765", 0)
    assert "troppo" in leggi_comando("/romeo EURUSD compra 1.07 1.08", 0)
    assert "strumento" in leggi_comando("/romeo compra 1.07", 0)


def _seguita(chiave, quando, ingresso, verso="long", entrata=False):
    return Seguita(chiave, "EURUSD", "H4", "M15", verso, quando, ingresso, ingresso - 0.0006, ingresso + 0.001,
                   ingresso + 0.002, 10**9, entrata, [0.0] * len(COLONNE), 1.0, 2.0, 0.05, 0.4, 0.3, -0.1)


def test_romeo_si_confronta_con_la_decisione_piu_vicina_delle_ultime_24_ore():
    adesso = utc(2026, 9, 25, 12)
    seguite = [_seguita("vicina", adesso - 3 * ORA, 1.0767), _seguita("lontana", adesso - 2 * ORA, 1.0790),
               _seguita("opposta", adesso - ORA, 1.0765, verso="short"), _seguita("vecchia", adesso - 30 * ORA, 1.0765)]
    e = leggi_comando("/romeo EURUSD compra 1.0765 stop 1.0760", adesso)
    assert confronta_romeo(e, seguite).chiave == "vicina"
    assert abs(e.distanza - 0.4) < 1e-9 and e.ritrovata and not e.presa
    casi, y = etichette([e], seguite)
    assert [s.chiave for s, v in zip(casi, y) if v] == ["vicina"]
    nessuna = leggi_comando("/romeo EURUSD vendo 1.0900 stop 1.0905", adesso)
    assert confronta_romeo(nessuna, seguite[:2]) is None and nessuna.vista is None


def test_telegram_legge_solo_dai_canali_del_bot():
    arrivi = [
        {"update_id": 5, "message": {"chat": {"id": -100}, "text": "/romeo EURUSD compra 1.07", "date": 1000}},
        {"update_id": 6, "message": {"chat": {"id": 999}, "text": "/romeo EURUSD compra 1.07", "date": 1001}},
        {"update_id": 7, "channel_post": {"chat": {"id": -200}, "text": "ciao", "date": 1002}},
    ]
    chiesti = []
    imp = Impostazioni(token="x", chat_operativo=("-100",), chat_equipe=("-200",))
    tg = Telegram(imp, invia=lambda c, t: None, stampa=lambda _: None, prendi=lambda dal: chiesti.append(dal) or arrivi)
    ricevuti, prossimo = tg.ricevi(5)
    assert [(r.chat, r.testo) for r in ricevuti] == [("-100", "/romeo EURUSD compra 1.07"), ("-200", "ciao")]
    assert prossimo == 8 and chiesti == [5]
    # Senza token non si chiede niente.
    assert Telegram(Impostazioni(), prendi=lambda dal: 1 / 0).ricevi(3) == ([], 3)


def test_il_bot_risponde_a_romeo_in_equipe_e_non_apre_niente(tmp_path, monkeypatch):
    import vivo
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    adesso = utc(2026, 9, 25, 12)
    arrivi = [{"update_id": 1, "message": {"chat": {"id": -1}, "text": "/romeo EURUSD compra 1.0765 stop 1.0760", "date": adesso}},
              {"update_id": 2, "message": {"chat": {"id": -1}, "text": "/romeo EURUSD 1.0765", "date": adesso}},
              {"update_id": 3, "message": {"chat": {"id": -1}, "text": "buongiorno", "date": adesso}}]
    mandati = []
    bot = object.__new__(vivo.Bot)
    bot._allarmi = {}
    bot.tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",), chat_equipe=("-2",)),
                      invia=lambda c, t: mandati.append((c, t)), stampa=lambda _: None, prendi=lambda dal: arrivi[dal - 1:] if dal else arrivi)
    bot.stato = Stato(seguite=[_seguita("vicina", adesso - 3 * ORA, 1.0767)])
    bot.ascolta()
    assert bot.stato.telegram_dal == 4 and len(bot.stato.romeo) == 1
    assert [c for c, _ in mandati] == ["-2", "-2"]
    assert "ritrovata" in mandati[0][1] and "Non la copio" in mandati[0][1]
    assert "non ho capito" in mandati[1][1]
    assert not bot.stato.vive
    bot.ascolta()                                # i messaggi gia' letti non tornano
    assert len(bot.stato.romeo) == 1
    # Se Telegram non risponde il bot va avanti, con un allarme.
    bot.tg = Telegram(Impostazioni(token="x", chat_operativo=("-1",)), invia=lambda c, t: mandati.append((c, t)),
                      stampa=lambda _: None, prendi=lambda dal: (_ for _ in ()).throw(RuntimeError("Telegram ha risposto 409")))
    bot.ascolta()
    assert "409" in mandati[-1][1]


def test_la_riunione_impara_romeo_anche_dal_vivo_e_da_il_metro():
    rng = np.random.default_rng(4)
    n = 600
    x = rng.integers(0, 2, size=(n, len(COLONNE))).astype(float)
    storico = Storico(x, rng.random(n) < 0.4, rng.random(n) < 0.15)
    storico.romeo_x, storico.romeo_y = x, (x[:, COLONNE.index("ora di Romeo: Londra")] == 1) & (rng.random(n) < 0.1)
    capo = Capo.allena(storico.x, storico.tp1, storico.tp2)
    adesso = utc(2026, 9, 26, 8)
    seguite = []
    for i in range(40):
        s = _seguita(f"k{i}", adesso - (i + 1) * 3 * ORA, 1.07 + 0.001 * i, entrata=i % 4 == 0)
        s.x = [0.0] * len(COLONNE)
        s.x[COLONNE.index("ora di Romeo: New York")] = float(i % 2 == 0)
        seguite.append(s)
    # Romeo sceglie le decisioni nell'ora di New York.
    romeo_vivo = [leggi_comando(f"/romeo EURUSD compra {s.ingresso:.4f} stop {s.ingresso - 0.0010:.4f}", s.quando + ORA)
                  for s in seguite if s.x[COLONNE.index("ora di Romeo: New York")] == 1][:10]
    testo, nuovo, _ = riunione(seguite, capo, storico, adesso - 7 * 86400, "2026-S39", romeo_vivo=romeo_vivo)
    _, solo_2023, _ = riunione(seguite, capo, storico, adesso - 7 * 86400, "2026-S39")
    assert "Romeo dal vivo" in testo and "ritrovate 10" in testo and "prese. Io ho aperto" in testo
    ny_ = np.zeros((1, len(COLONNE)))
    ny_[0, COLONNE.index("ora di Romeo: New York")] = 1
    assert nuovo.somiglianza(ny_)[0] > solo_2023.somiglianza(ny_)[0]


def test_il_bot_racconta_l_allenamento_una_volta_sola(tmp_path, monkeypatch):
    import vivo
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    monkeypatch.setattr(vivo, "leggi_memoria", lambda: {"ultimo": {"settimana": "2026-S40", "rapporto": "🏋️ Allenamento"}})
    mandati = []
    bot = object.__new__(vivo.Bot)
    bot.tg = Telegram(Impostazioni(token="x", chat_equipe=("-2",)), invia=lambda c, t: mandati.append(t), stampa=lambda _: None)
    bot.stato = Stato()
    bot.racconta_allenamento()
    bot.racconta_allenamento()
    assert mandati == ["🏋️ Allenamento"] and Stato.carica(tmp_path).ultimo_allenamento == "2026-S40"
    # Un secondo allenamento nella stessa settimana si racconta anche lui.
    monkeypatch.setattr(vivo, "leggi_memoria", lambda: {"ultimo": {"settimana": "2026-S40", "id": 99, "rapporto": "🏋️ Di nuovo"}})
    bot.racconta_allenamento()
    assert mandati[-1] == "🏋️ Di nuovo"


def test_il_pareggio_prima_del_primo_obiettivo_tiene_i_due_target():
    from nvm.vivo.esecutore import Viva
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    viva.pareggio_a = 0.5                         # i Livelli hanno imparato: pareggio a meta' strada
    a, b = viva.tickets
    meta = viva.ingresso + 0.6 * (viva.tp1 - viva.ingresso)
    m.tick["EURUSD"] = NS(time=0, bid=meta, ask=meta + 0.00001) if not viva.short else NS(time=0, bid=meta - 0.00001, ask=meta)
    vive, fatti = e.sorveglia([viva])
    assert vive[0].pareggio_fatto and "pareggio" in fatti[0].testo
    assert m.posizioni[a].sl == m.posizioni[b].sl == round(viva.ingresso, 5)
    assert m.posizioni[a].tp == round(d.op.tp1, 5) and m.posizioni[b].tp == round(d.op.tp2, 5)
