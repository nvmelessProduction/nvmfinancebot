"""Il bot dal vivo, con un MT5 finto e Telegram muto."""

from dataclasses import replace
from types import SimpleNamespace as NS

import time

import numpy as np
import pytest

from nvm.agenti.cacciatore import Verso
from nvm.agenti.capo import COLONNE, Capo
from nvm.agenti.rischio import esiti, kelly
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import opera, opera_candela_3
from nvm.tempo import utc
from nvm.vivo.ambiente import Impostazioni, impostazioni
from nvm.vivo.esecutore import MAGIC, Esecutore
from nvm.vivo.giro import COPPIE, giro
from nvm.vivo.messaggi import pareri
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.stato import Seguita
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import Esito, Terminale
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


def test_i_messaggi_partono_da_una_coda_al_ritmo_di_telegram():
    import time
    from nvm.vivo.telegram import TroppiMessaggi
    mandati, rifiuti = [], [1]

    def invia(c, t):
        if t == "b" and rifiuti:
            rifiuti.pop()
            raise TroppiMessaggi(0.05)          # Telegram: aspetta un attimo
        mandati.append((c, t, time.monotonic()))

    imp = Impostazioni(token="x", chat_equipe=("eq",))
    tg = Telegram(imp, invia=invia, stampa=lambda _: None, intervallo=0.1, in_coda=True)
    prima = time.monotonic()
    for t in "abc":
        tg.equipe(t)
    assert time.monotonic() - prima < 0.05       # il bot non aspetta
    assert tg.svuota(5)
    assert [t for _, t, _ in mandati] == ["a", "b", "c"]
    distanze = [y[2] - x[2] for x, y in zip(mandati, mandati[1:])]
    assert all(d >= 0.09 for d in distanze)      # mai piu' veloce del ritmo


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


def test_il_grafico_del_dollaro_si_trova_col_nome_del_broker():
    """Su FP Markets il DXY si chiama USDX: il bot lo trova da solo e ne legge le orarie."""
    adesso = utc(2026, 10, 8, 10, 30)
    m, orologio = _terminale_con_barre(adesso)
    m.barre["USDX"] = m.barre["EURUSD"].copy()
    m.tick["USDX"] = NS(time=adesso + 3 * ORA - 5, bid=99.1, ask=99.11)
    t = Terminale(mt5=m, orologio=lambda: orologio[0])
    t.scarto = 3
    assert t.esiste("DXY") and t.simbolo("DXY") == "USDX"
    assert t.orarie("DXY", 100).strumento == "DXY"
    del m.tick["USDX"]
    t2 = Terminale(mt5=m, orologio=lambda: orologio[0])
    assert not t2.esiste("DXY")


def test_il_bot_usa_il_dxy_del_broker_quando_tradingview_non_e_attivo():
    """Il DXY deve arrivare da MT5 (USDX) anche senza grafici TradingView."""
    import vivo

    dati = ore_finte("DXY", giorni=2)
    chiamate, allarmi = [], []
    fonte = NS(esiste=lambda nome: chiamate.append(("esiste", nome)) or True,
               orarie=lambda nome, quante: (chiamate.append(("orarie", nome, quante)), dati)[1],
               simbolo=lambda nome: "USDX")
    bot = object.__new__(vivo.Bot)
    bot.fonte, bot.terminale, bot.dxy = None, fonte, None
    bot.allarme = allarmi.append

    bot.aggiorna_dxy()

    assert bot.dxy is dati
    assert chiamate == [("esiste", "DXY"), ("orarie", "DXY", vivo.ORARIE)]
    assert allarmi == []


# --- il giro fa quello che fa lo storico ---

def test_il_giro_decide_come_lo_storico():
    base = ore_finte()
    capo = CapoFinto()
    inizio, fine = int(base.t[0]) + 150 * 86400, int(base.t[-1])
    attese = set()
    for alto, basso in COPPIE:
        alte, basse = costruisci(base, alto).chiuse_entro(fine + ORA), costruisci(base, basso).chiuse_entro(fine + ORA)
        # Il metodo dei video: solo la candela 3 (`documenti/spec/metodo_romeo.md`).
        attese |= {(r.alto_tf, r.verso, r.quando, r.colpo) for r in opera_candela_3(alte, basse, inizio + 1, fine + 1)}
    viste, dal = set(), inizio + 1
    for adesso in range(inizio + 12 * ORA, fine + 1, 12 * ORA):
        viste |= {(d.r.alto_tf, d.r.verso, d.r.quando, d.r.colpo)
                  for d in giro({"EURUSD": base}, dal, adesso, capo, metodo="candela 3")}
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
    # Il metodo dei video: l'Esecutore e i messaggi non cambiano col metodo.
    d = giro({"EURUSD": base}, int(base.t[0]) + 100 * 86400, int(base.t[-1]), CapoFinto(), metodo="candela 3")
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
    assert "tutti i 2 mercati" in tutto_bene


def _pari(v, costo=None):
    """Lo stop a pareggio: oltre l'ingresso di quanto costano le commissioni (sul conto finto, quelle della tabella)."""
    from nvm.prova.campo import COMMISSIONE
    costo = COMMISSIONE[v.strumento] if costo is None else costo
    return round(v.ingresso + (-1 if v.short else 1) * costo, 5)


def test_il_pareggio_copre_le_commissioni():
    """Il proprietario, 20/10/2026: *"il be non va messo preciso al prezzo di entrata ... ma leggermente in guadagno
    per coprire i costi di commissione"*. Con la commissione vera dell'apertura su MT5, apertura e chiusura."""
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    (a,) = viva.tickets
    # 3 euro a lotto all'apertura: con la chiusura 6 a lotto, cioe' 0,6 pip su EURUSD (100.000 euro a lotto per unita').
    m._affari(a, viva.ingresso)[0].commission = -3.0 * viva.volume
    m.tick["EURUSD"] = NS(time=0, bid=d.op.tp1, ask=d.op.tp1 + 0.0001)
    vive, fatti = e.sorveglia([viva])
    assert vive[0].pareggio_fatto and m.posizioni[a].sl == _pari(viva, 0.00006)
    assert (m.posizioni[a].sl > viva.ingresso) == (not viva.short) and "commissioni coperte" in fatti[0].testo
    # Senza la commissione di MT5, quella della tabella (0,7 pip su EURUSD).
    assert e.pareggio(replace(viva, tickets=[999]), [999]) == pytest.approx(_pari(viva), abs=1e-9)


def test_una_posizione_sola_meta_al_tp1_dal_bot_pareggio_e_chiude():
    # Il proprietario, 07/10/2026: *"vorrei che apri una sola operazione. Quando arriva [al TP1], parzializza.
    # Se si può parzializzare, altrimenti no. E continua fino al TP"*.
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, fatto = e.apri(d, t.conto())
    assert viva is not None and len(viva.tickets) == 1 and len(m.posizioni) == 1, fatto.testo
    (a,) = viva.tickets
    # Sul broker: lo stop e il target finale; il TP1 lo fa il bot.
    assert m.posizioni[a].tp == round(d.op.tp2, 5) and m.posizioni[a].sl == round(d.op.stop, 5)
    assert 0 < viva.meta <= m.posizioni[a].volume / 2 + 1e-9
    # In parole semplici: cosa ho fatto, quanto posso perdere, quanto posso guadagnare, in euro.
    assert ("HO COMPRATO" in fatto.testo or "HO VENDUTO" in fatto.testo) and "se va male perdo" in fatto.testo
    assert "Obiettivo 1" in fatto.testo and "Obiettivo 2" in fatto.testo and "EUR" in fatto.testo
    assert "in una posizione sola" in fatto.testo
    assert "del conto" in fatto.testo and "Model#1" not in fatto.testo and "Kelly" not in fatto.testo
    assert " R" not in fatto.testo and "Probabilità" not in fatto.testo

    vive, fatti = e.sorveglia([viva])          # niente ancora
    assert vive and not vive[0].meta_fatta and not fatti
    volume = m.posizioni[a].volume
    m.tick["EURUSD"] = NS(time=0, bid=d.op.tp1, ask=d.op.tp1 + 0.0001)   # il TP1
    vive, fatti = e.sorveglia(vive)
    v = vive[0]
    assert v.meta_fatta and v.pareggio_fatto
    assert abs(m.posizioni[a].volume - (volume - v.meta)) < 1e-9          # chiusa meta', il resto resta
    assert m.posizioni[a].sl == _pari(v) and m.posizioni[a].tp == round(d.op.tp2, 5)
    assert "primo obiettivo" in fatti[0].testo
    vive, fatti = e.sorveglia(vive)            # una volta sola
    assert not fatti and abs(m.posizioni[a].volume - (volume - v.meta)) < 1e-9

    m.chiudi(a, v.ingresso)                    # il resto torna a pareggio
    vive, fatti = e.sorveglia(vive)
    assert vive == [] and "chiusa in guadagno" in fatti[0].testo
    assert fatti[0].libro["netto"] > 0         # il parziale e' nel risultato


def test_il_pareggio_solo_al_tp1_mai_alla_chiusura_della_candela_d_ingresso():
    """Il proprietario, 20/10/2026: *"levi assolutamente la funzione che alla chiusura della candela d'entrata il bot
    mette be. lo deve mettere solo al tp1"*. Anche una posizione aperta quando c'era quella regola (`tp1_entro`)."""
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    assert viva.tp1_entro == 0
    (a,) = viva.tickets
    volume = m.posizioni[a].volume
    viva.tp1_entro = int(time.time()) - 60          # la candela d'ingresso e' chiusa da un minuto
    vive, fatti = e.sorveglia([viva])
    v = vive[0]
    assert not v.pareggio_fatto and not v.meta_fatta and not fatti
    assert m.posizioni[a].sl == round(d.op.stop, 5) and m.posizioni[a].volume == volume
    m.tick["EURUSD"] = NS(time=0, bid=d.op.tp1, ask=d.op.tp1 + 0.0001)   # il TP1
    vive, fatti = e.sorveglia(vive)
    assert vive[0].pareggio_fatto and vive[0].meta_fatta and m.posizioni[a].sl == _pari(v)
    assert "primo obiettivo" in fatti[0].testo


def test_se_mt5_rifiuta_il_pareggio_riprova_ma_l_allarme_arriva_una_volta():
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    vero = t.sposta_stop
    t.sposta_stop = lambda *a: Esito(False, "stop non spostato: mercato chiuso")
    m.tick["EURUSD"] = NS(time=0, bid=d.op.tp1, ask=d.op.tp1 + 0.0001)
    vive, fatti = e.sorveglia([viva])
    assert not vive[0].pareggio_fatto and sum("mercato chiuso" in f.testo for f in fatti) == 1
    for _ in range(3):
        vive, fatti = e.sorveglia(vive)
        assert not any("mercato chiuso" in f.testo for f in fatti)
    t.sposta_stop = vero
    vive, fatti = e.sorveglia(vive)
    assert vive[0].pareggio_fatto and not vive[0].pareggio_rifiutato


def test_il_tp1_toccato_fra_due_controlli_si_vede_dalle_barre_da_un_minuto():
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    long = d.r.verso is Verso.LONG
    # Fra un minuto e l'altro il prezzo ha toccato il TP1 ed e' tornato indietro.
    barra = np.zeros(1, BARRA)
    barra["time"] = viva.quando + 60 + m.scarto * 3600
    barra["high"] = d.op.tp1 + 0.0001 if long else d.op.ingresso
    barra["low"] = d.op.ingresso if long else d.op.tp1 - 0.0002
    m.barre[("EURUSD", m.TIMEFRAME_M1)] = barra
    vive, fatti = e.sorveglia([viva])
    assert vive[0].meta_fatta and vive[0].pareggio_fatto and "primo obiettivo" in fatti[0].testo
    # Le barre di prima dell'apertura non contano.
    viva2, _ = e.apri(replace(d, r=replace(d.r, quando=d.r.quando + 86400)), t.conto())
    barra["time"] = viva2.quando - 120 + m.scarto * 3600
    vive, fatti = e.sorveglia([viva2])
    assert not vive[0].meta_fatta


def test_se_il_lotto_non_si_divide_niente_parziale_e_tutto_al_target_finale():
    d = _una_decisione()
    m = MT5Finto(saldo=2.0)                    # la puntata e' il lotto minimo: non si divide
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, fatto = e.apri(d, t.conto(), pieno=1.0, parte=1.0, fiducia_minima=0.0, riduci=False)
    assert viva is not None and len(viva.tickets) == 1 and viva.meta == 0.0, fatto.testo
    (a,) = viva.tickets
    assert m.posizioni[a].tp == round(d.op.tp2, 5)
    m.tick["EURUSD"] = NS(time=0, bid=d.op.tp1, ask=d.op.tp1 + 0.0001)
    vive, fatti = e.sorveglia([viva])
    assert m.posizioni[a].volume == viva.volume and m.posizioni[a].sl == _pari(viva)
    assert "non si poteva dividere" in fatti[0].testo


def test_lo_stesso_crt_non_si_apre_due_volte():
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    assert viva is not None
    # Anche se il bot se l'e' dimenticato (ripartito senza stato): il commento sul broker dice quale CRT e'.
    di_nuovo, fatto = e.apri(d, t.conto())
    assert di_nuovo is None and len(m.posizioni) == 1 and "già" in fatto.testo
    assert all(len(p.comment) <= 31 for p in m.posizioni.values())


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


def test_il_lotto_minimo_si_apre_solo_se_il_conto_lo_regge():
    """Sotto il lotto minimo si apre il minimo solo se, con la fiducia nelle stime imparata dal
    Rischio, fa ancora crescere il conto: su un conto minuscolo il minimo sarebbe un azzardo."""
    from nvm.agenti.rischio import crescita_creduta, esiti, kelly
    e = esiti(0.5, 0.3, 1.5, 3.0, 0.0)
    k = kelly(e)
    assert crescita_creduta(e, 0.2 * k, 0.2) > 0 and crescita_creduta(e, 0.39 * k, 0.2) > 0
    assert crescita_creduta(e, 0.41 * k, 0.2) < 0 and crescita_creduta(e, 0.0, 0.2) == 0
    d = _una_decisione()
    for saldo, apre in ((1000.0, True), (5.0, False)):
        m = MT5Finto(saldo=saldo)
        m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
        t = Terminale(mt5=m)
        viva, fatto = Esecutore(t, parte=0.2).apri(d, t.conto())
        assert (viva is not None) == apre, fatto.testo
        if not apre:
            assert fatto.saltata == "conto troppo piccolo per il lotto minimo" and m.richieste == []


# --- l'equipe e la riunione ---

def test_ogni_agente_dice_la_sua():
    d = _una_decisione()
    testo = pareri(d)
    for agente in ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Allineamento", "Gap", "Capo"):
        assert agente in testo
    # Allineamento e Gap guardano i quattro timeframe grandi e dicono cosa vedono.
    assert d.sguardo is not None and len(d.sguardo.lati) == 4
    riga = next(r for r in testo.splitlines() if r.startswith("Allineamento — "))
    assert sum(n in riga for n in ("4 ore", "giorno", "settimana", "mese")) == 4
    assert "FVG" in next(r for r in testo.splitlines() if r.startswith("Gap — "))


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
    testo, nuovo, rischio, verbale = riunione(seguite, capo, storico, 0, "2026-S39", rischio={"parte": 0.2, "quando": 1})
    assert "Riunione" in testo and "30 dal vivo" in testo
    assert not np.allclose(nuovo.primo.pesi, capo.primo.pesi)
    # Senza lo storico completo il Rischio resta com'era: non torna al modo che brucia il conto.
    assert rischio == {"parte": 0.2, "quando": 1} and "resto com'ero" in verbale
    # Con lo storico completo rigioca il conto intero, con le operazioni dal vivo.
    n = 400
    storico.kelly_f, storico.kelly_r = np.full(n, 0.1), np.where(rng.random(n) < 0.45, 2.0, -1.0)
    storico.k_entrata = np.arange(n) * 86400
    storico.k_chiusa = storico.k_entrata + 3600
    storico.k_strumento, storico.k_verso = np.full(n, "EURUSD"), np.ones(n, np.int8)
    _, _, rischio, verbale = riunione(seguite, capo, storico, 0, "2026-S39", rischio={"parte": 0.2, "quando": 1})
    assert {"parte", "minimo", "calo_sfortunato", "quando"} <= set(rischio) and "rigiocato il conto intero su 430" in verbale


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
    testo, nuovo, _, _ = riunione([vecchia], capo, storico, 0, "2026-S39")
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
    testo, nuovo, _, _ = riunione(seguite, capo, storico, adesso - 7 * 86400, "2026-S39", romeo_vivo=romeo_vivo)
    _, solo_2023, _, _ = riunione(seguite, capo, storico, adesso - 7 * 86400, "2026-S39")
    assert "Romeo dal vivo" in testo and "ritrovate 10" in testo and "prese. Io ho aperto" in testo
    ny_ = np.zeros((1, len(COLONNE)))
    ny_[0, COLONNE.index("ora di Romeo: New York")] = 1
    assert nuovo.somiglianza(ny_)[0] > solo_2023.somiglianza(ny_)[0]


def test_il_bot_racconta_l_allenamento_una_volta_sola(tmp_path, monkeypatch):
    import vivo
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    monkeypatch.setattr(vivo, "leggi_memoria", lambda: {"ultimo": {"settimana": "2026-S40", "rapporto": "lungo", "breve": "🏋️ Allenamento"}})
    mandati = []
    bot = object.__new__(vivo.Bot)
    bot.tg = Telegram(Impostazioni(token="x", chat_equipe=("-2",)), invia=lambda c, t: mandati.append(t), stampa=lambda _: None)
    bot.stato = Stato()
    bot.racconta_allenamento()
    bot.racconta_allenamento()
    assert mandati == ["🏋️ Allenamento"] and Stato.carica(tmp_path).ultimo_allenamento == "2026-S40"
    # Un secondo allenamento nella stessa settimana si racconta anche lui.
    monkeypatch.setattr(vivo, "leggi_memoria", lambda: {"ultimo": {"settimana": "2026-S40", "id": 99, "breve": "🏋️ Di nuovo"}})
    bot.racconta_allenamento()
    assert mandati[-1] == "🏋️ Di nuovo"
    # I rapporti di prima, solo lunghi, non si mandano.
    monkeypatch.setattr(vivo, "leggi_memoria", lambda: {"ultimo": {"settimana": "2026-S41", "id": 100, "rapporto": "lungo"}})
    bot.racconta_allenamento()
    assert mandati[-1] == "🏋️ Di nuovo"


def test_il_pareggio_prima_del_primo_obiettivo_tiene_il_target_finale():
    from nvm.vivo.esecutore import Viva
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    viva.pareggio_a = 0.5                         # i Livelli hanno imparato: pareggio a meta' strada
    (a,) = viva.tickets
    meta = viva.ingresso + 0.6 * (viva.tp1 - viva.ingresso)
    m.tick["EURUSD"] = NS(time=0, bid=meta, ask=meta + 0.00001) if not viva.short else NS(time=0, bid=meta - 0.00001, ask=meta)
    volume = m.posizioni[a].volume
    vive, fatti = e.sorveglia([viva])
    assert vive[0].pareggio_fatto and "pareggio" in fatti[0].testo
    assert m.posizioni[a].sl == _pari(viva) and m.posizioni[a].tp == round(d.op.tp2, 5)
    assert m.posizioni[a].volume == volume and not vive[0].meta_fatta     # il TP1 non e' ancora arrivato


def test_l_uscita_anticipata_chiude_a_mercato_e_lo_dice():
    from tests.aiuti import candele
    from nvm.tempo import TF
    d = _una_decisione()
    m = MT5Finto()
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    viva.invalida_candele, viva.livello = 2, viva.ingresso      # l'allenamento l'ha accesa
    segno = -1 if viva.short else 1
    oltre = viva.livello - segno * 0.0003                       # dalla parte sbagliata del livello
    passo = 3600 if viva.basso == "H1" else 900
    righe = [(viva.quando + k * passo, oltre, oltre + 0.0001, oltre - 0.0001, oltre) for k in range(2)]
    basse = candele("EURUSD", TF(viva.basso or "H1"), righe)
    assert e.uscita_anticipata(viva, candele("EURUSD", TF(viva.basso or "H1"), righe[:1])) is None
    fatto = e.uscita_anticipata(viva, basse)
    assert fatto is not None and "prima dello stop" in fatto.testo and not m.posizioni
    vive, fatti = e.sorveglia([viva])
    assert vive == [] and "l'idea non vale più" in fatti[0].testo.lower()


def test_il_bot_si_sveglia_pochi_secondi_dopo_la_chiusura():
    import vivo
    base = utc(2026, 9, 25, 10)                       # una chiusura di quarto d'ora
    assert vivo.attesa(base + 1) == vivo.RITARDO_GIRO - 1      # appena dopo: aspetta solo il ritardo
    assert vivo.attesa(base + vivo.RITARDO_GIRO) == 60 - vivo.RITARDO_GIRO + 1   # giro fatto: al prossimo minuto
    assert vivo.attesa(base + 14 * 60 + 58) == 3      # prima il minuto, poi la chiusura
    assert vivo.RITARDO_GIRO <= 5


def test_le_decisioni_vecchie_vanno_nell_archivio_e_la_riunione_le_rilegge(tmp_path):
    from nvm.vivo.stato import archivia, archiviate
    vecchia = Seguita("k1", "EURUSD", "D1", "H1", "short", 100, 1.1, 1.101, 1.099, 1.098, 10**9, False,
                      [0.0] * len(COLONNE), 1.0, 2.0, 0.0, 0.5, 0.3, 0.1)
    vecchia.esito = {"uscita": "stop", "erre": -1.0, "quando": 1000, "tp1": False, "tp2": False}
    recente = Seguita(**{**vecchia.__dict__, "chiave": "k2"})
    recente.esito = {**vecchia.esito, "quando": 5000}
    archivia(tmp_path, [vecchia, recente])
    assert [s.chiave for s in archiviate(tmp_path)] == ["k1", "k2"]
    assert [s.chiave for s in archiviate(tmp_path, dal=2000)] == ["k2"]
    assert archiviate(tmp_path / "vuota") == []


def test_il_rischio_non_mette_soldi_sulle_stime_deboli():
    d = _una_decisione()
    m = MT5Finto(saldo=100000.0)
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    viva, fatto = Esecutore(t, parte=0.2, minimo=10.0).apri(d, t.conto())
    assert viva is None and fatto.saltata == "fiducia troppo bassa per metterci soldi" and m.richieste == []


def test_del_rischio_vale_il_piu_recente(tmp_path, monkeypatch):
    import json
    import vivo
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path / "vivo")
    monkeypatch.setattr(vivo, "RADICE", tmp_path)
    (tmp_path / "vivo").mkdir()
    (tmp_path / "nvm" / "vivo").mkdir(parents=True)
    (tmp_path / "vivo" / "rischio.json").write_text(json.dumps({"parte": 0.2}))
    (tmp_path / "nvm" / "vivo" / "rischio.json").write_text(json.dumps({"parte": 0.01, "minimo": 0.06, "quando": 5}))
    assert vivo._leggi("rischio.json")["parte"] == 0.01      # quello vecchio del sabato non vince piu'
    (tmp_path / "vivo" / "rischio.json").write_text(json.dumps({"parte": 0.02, "minimo": 0.06, "quando": 9}))
    assert vivo._leggi("rischio.json")["parte"] == 0.02


def test_il_piano_scelto_dai_cervelli_si_apre_com_e():
    from dataclasses import replace
    d = _una_decisione()
    for parziale, target in ((1.0, "tp1"), (0.0, "tp2")):
        m = MT5Finto(saldo=100000.0)
        m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
        t = Terminale(mt5=m)
        dd = replace(d, op=replace(d.op, parziale=parziale))
        viva, fatto = Esecutore(t, parte=0.2).apri(dd, t.conto(), pieno=0.3, parte=0.2, fiducia_minima=0.0)
        assert viva is not None and len(viva.tickets) == 1, fatto.testo
        assert m.posizioni[viva.tickets[0]].tp == round(getattr(d.op, target), 5)


def test_una_chiusura_che_mt5_non_trova_non_ferma_il_bot():
    from nvm.vivo.esecutore import ATTESA_CHIUSURA
    d = _una_decisione()
    m = MT5Finto(saldo=100000.0)
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    for ticket in viva.tickets:          # sparite dal conto, senza storico della chiusura
        del m.posizioni[ticket]
    m.history_deals_get = lambda **k: None
    vive = [viva]
    for _ in range(ATTESA_CHIUSURA - 1):
        vive, fatti = e.sorveglia(vive)
        assert vive == [viva] and fatti == []           # aspetta, senza errori e senza rumore
    vive, fatti = e.sorveglia(vive)
    assert vive == [] and any("non ne dà il risultato" in f.testo for f in fatti)


def test_il_riepilogo_della_sera_arriva_anche_se_non_e_successo_niente():
    from nvm.vivo.conversazione import riepilogo
    assert riepilogo([], 0, 86400, 0, 0.0, []) == ""
    testo = riepilogo([], 0, 86400, 0, 0.0, [], sempre=True, saldo=1000.0,
                      mancanze={"tutte le regole": 1, "l'ora giusta": 5, "un key level del grafico grande": 3})
    assert "Com'è andata oggi" in testo and "Il conto" in testo
    assert "Con tutte le regole di Romeo: 1" in testo
    assert "Alle altre mancava soprattutto: l'ora giusta (5), un key level del grafico grande (3)" in testo
    assert "Giornata tranquilla" in testo and "acceso" in testo


def test_se_il_bot_si_inchioda_il_cane_da_guardia_lo_chiude_e_lo_dice(tmp_path, monkeypatch):
    import vivo
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    detti, uscite = [], []
    bot = NS(battito=time.time() - vivo.INCHIODATO - 5, tg=NS(operativo=detti.append, svuota=lambda _: True))
    filo = vivo.cane_da_guardia(bot, controlla_ogni=0.01, uscita=uscite.append)
    filo.join(2)
    assert uscite == [vivo.BLOCCATO] and "bloccato" in detti[0]
    # Finche' il giro finisce, non fa niente.
    uscite.clear()
    vivo_bot = NS(battito=time.time(), tg=NS(operativo=detti.append, svuota=lambda _: True))
    vivo.cane_da_guardia(vivo_bot, controlla_ogni=0.01, uscita=uscite.append)
    time.sleep(0.1)
    assert not uscite


def test_la_lista_degli_strumenti_del_broker(tmp_path, monkeypatch):
    """Il comando /strumenti: tutti gli strumenti del broker per cartella, con quelli del bot segnati."""
    import vivo
    from nvm.vivo import messaggi
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    m = MT5Finto()
    m.tick["EURUSD.x"] = NS(time=0, bid=1.1, ask=1.1001)
    m.tick["XAUUSD.x"] = NS(time=0, bid=2000.0, ask=2000.3)
    t = Terminale(mt5=m)
    simboli = t.tutti_i_simboli()
    assert [s[0] for s in simboli] == ["EURUSD.x", "DE40.x", "XAUUSD.x"]
    testi = messaggi.simboli_del_broker(simboli, {"EURUSD.x": "EURUSD"})
    testo = "\n".join(testi)
    assert "3 in tutto" in testo and "✅ EURUSD.x" in testo and "Forex (1)" in testo and "Metals (1)" in testo
    # Tanti strumenti: piu' messaggi, ognuno sotto il limite di Telegram.
    tanti = [(f"S{i:04d}", "Forex\\Exotics", "") for i in range(900)]
    assert len(messaggi.simboli_del_broker(tanti, {})) > 1
    assert all(len(x) < 4000 for x in messaggi.simboli_del_broker(tanti, {}))
    mandati = []
    bot = object.__new__(vivo.Bot)
    bot.terminale, bot.strumenti = t, ["EURUSD"]
    t._nomi["EURUSD"] = "EURUSD.x"
    bot.tg = NS(operativo=lambda x: mandati.append(("op", x)), equipe=lambda x: mandati.append(("eq", x)))
    bot.manda_simboli("equipe")
    assert mandati and mandati[0][0] == "eq" and "✅ EURUSD.x" in mandati[0][1]


def test_il_bot_guarda_solo_i_mercati_della_lista_del_20_10():
    """Il proprietario, 20/10/2026: *"lasciamo solo dxy, eurusd, gbpusd, nzdusd, audusd, xauusd, xagusd, aggiungiamo
    xptusd, usdchf usdcad poi total, btcusd, ethusd"*, e poco dopo *"togli xpt"*. Anche se il .env di TradingView ne ha
    altri."""
    import vivo
    from nvm.agenti import foto
    assert set(vivo.STRUMENTI_VIVO) == {"EURUSD", "GBPUSD", "NZDUSD", "AUDUSD", "XAUUSD", "XAGUSD",
                                        "USDCHF", "USDCAD", "BTCUSD", "ETHUSD"}
    assert all(n in vivo.STRUMENTI for n in vivo.STRUMENTI_VIVO)
    # Tutti guidati: dal DXY i dieci col dollaro, dalla TOTAL le crypto.
    assert {n for n in vivo.STRUMENTI_VIVO if n not in foto.CRYPTO_TOTALE} <= set(foto.GUIDATI_DAL_DXY)
    assert foto.verso_dal_dxy("XAGUSD", Verso.LONG) is Verso.SHORT and foto.verso_dal_dxy("USDCAD", Verso.LONG) is Verso.LONG
    dal_env = [("FX_IDC:EURUSD", "EURUSD"), ("FX_IDC:USDJPY", "USDJPY"), ("OANDA:US30USD", "US30"),
               ("FX_IDC:GBPUSD", "GBPUSD"), ("OANDA:XPTUSD", "XPTUSD")]
    assert vivo.grafici_da_guardare(dal_env) == [("FX_IDC:EURUSD", "EURUSD"), ("FX_IDC:GBPUSD", "GBPUSD")]


def test_un_errore_su_uno_strumento_non_rifa_il_giro_e_non_riapre(tmp_path, monkeypatch):
    # Prima un errore su uno strumento faceva ripartire tutto il giro dell'ora al minuto dopo, e gli
    # strumenti gia' guardati (euro-dollaro per primo) riaprivano la stessa operazione.
    import vivo
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    monkeypatch.setattr(vivo, "giro_orario", lambda basi, *a, **k: [NS(chiave=f"{next(iter(basi))} H4 1",
                                                                       r=NS(quando=0, strumento=next(iter(basi))))])
    bot = object.__new__(vivo.Bot)
    allarmi, decise = [], []

    def orarie(s, quante):
        if s == "GBPUSD":
            raise RuntimeError("niente barre")
        return ore_finte(s, giorni=1)
    bot.terminale = NS(orarie=orarie, scarto=3)
    bot.strumenti = ["EURUSD", "GBPUSD", "AUDUSD"]
    bot.basi = {s: ore_finte(s, giorni=1) for s in bot.strumenti}
    bot.fini, bot.lunghe, bot.squadra, bot.capo = {}, {}, None, None
    bot.stato = Stato()
    bot.stato.ultimo_giro = utc(2025, 1, 1)
    bot.allarme = allarmi.append
    finestre = []
    bot._decidi = lambda dd, adesso, finestra: (decise.extend(d.chiave for d in dd), finestre.append((adesso, finestra)))
    for nome in ("aggiorna_lunghe", "aggiorna_dxy", "aggiorna_totale", "uscite", "aggiorna_disegni",
                 "controlla_disegni", "parla"):
        setattr(bot, nome, lambda *a: None)
    ora = utc(2025, 1, 1, 5)
    bot.giro(ora)
    # Le occasioni di tutti gli strumenti si decidono insieme (il Capo sceglie le migliori del giro).
    assert sorted(decise) == ["AUDUSD H4 1", "EURUSD H4 1"] and len(finestre) == 1 and bot.stato.ultimo_giro == ora
    assert len(allarmi) == 1 and "GBPUSD" in allarmi[0]
    # Col metodo delle foto si entra solo vicino all'apertura della candela 3, contando l'ora vera.
    if vivo.il_metodo() == "foto":
        assert all(f == vivo.RITARDO_MASSIMO and abs(a - time.time()) < 60 for a, f in finestre)
    # Un errore dopo le decisioni (foto, disegni, carta) non fa ripetere il giro.
    bot.uscite = lambda *a: (_ for _ in ()).throw(RuntimeError("disegni rotti"))
    bot.giro(ora + 3600)
    assert bot.stato.ultimo_giro == ora + 3600
    # Se non va nessuno strumento (MT5 staccato) il giro si riprova al minuto dopo.
    bot.terminale = NS(orarie=lambda s, q: (_ for _ in ()).throw(RuntimeError("MT5 staccato")), scarto=3)
    with pytest.raises(RuntimeError):
        bot.giro(ora + 7200)
    assert bot.stato.ultimo_giro == ora + 3600


def test_con_la_quota_di_tradingview_finita_un_messaggio_solo_e_nessuna_richiesta(tmp_path, monkeypatch):
    """20/10/2026: finita la quota giornaliera di TradingView, il bot mandava un allarme per grafico a ogni minuto (il
    testo cambiava col conto alla rovescia) e riprovava il giro, bruciando altre richieste. Ora: un messaggio, il giro
    dell'ora si chiude senza occasioni, e fino a mezzanotte UTC non si chiede piu' niente."""
    import vivo
    from nvm.vivo.stato import Stato
    from nvm.vivo.tradingview import QuotaFinita
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    monkeypatch.setattr(vivo, "giro_orario", lambda *a, **k: [])
    adesso = time.time()
    fine = adesso + 7 * 3600
    tv = NS(ferma=False, ferma_fino=0.0, chiamate_oggi=812)
    chieste = []

    def orarie(s, quante):
        chieste.append(s)
        if s == "GBPUSD" and not tv.ferma_fino:
            tv.ferma, tv.ferma_fino = True, fine
            raise QuotaFinita(f"get_ohlcv: TOOL_QUOTA_EXCEEDED ... in about {len(chieste)}h", fine)
        return ore_finte(s, giorni=1)
    bot = object.__new__(vivo.Bot)
    bot.fonte = NS(tv=tv, orarie=orarie, esiste=lambda s: True)
    bot.terminale = NS(scarto=3)
    bot.strumenti = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY"]
    bot.basi = {s: ore_finte(s, giorni=1) for s in bot.strumenti}
    bot.fini, bot.lunghe, bot.squadra, bot.capo = {}, {}, None, None
    bot.stato = Stato()
    bot.stato.ultimo_giro = utc(2025, 1, 1)
    detti = []
    bot.tg = NS(operativo=detti.append)
    bot.allarme = detti.append
    bot._decidi = lambda *a: None
    for nome in ("aggiorna_lunghe", "aggiorna_dxy", "aggiorna_totale", "uscite", "aggiorna_disegni",
                 "controlla_disegni", "parla"):
        setattr(bot, nome, lambda *a: None)
    ora = utc(2025, 1, 1, 5)
    bot.giro(ora)
    # Dopo la quota finita non si chiede piu' niente, e il giro non si ripete al minuto dopo.
    assert chieste == ["EURUSD", "GBPUSD"] and bot.stato.ultimo_giro == ora
    assert len(detti) == 1 and "finite le richieste di oggi" in detti[0] and "812" in detti[0]
    bot.giro(ora + 3600)
    bot.giro(ora + 7200)
    assert chieste == ["EURUSD", "GBPUSD"] and len(detti) == 1 and bot.stato.ultimo_giro == ora + 7200
    # A mezzanotte UTC la quota riparte: si torna a chiedere.
    tv.ferma = False
    bot.giro(ora + 10800)
    assert chieste[2:] == bot.strumenti


def test_col_metodo_delle_foto_i_quarti_d_ora_arrivano_da_mt5():
    """Su TradingView i quarti d'ora erano circa 900 richieste al giorno, e col metodo delle foto non servono a
    decidere: si prendono da MT5, tutti a ogni quarto d'ora, e a TradingView non si chiedono."""
    import vivo
    from nvm.vivo.stato import Stato
    if vivo.il_metodo() != "foto":
        pytest.skip("solo col metodo delle foto")
    da_tv, da_mt5 = [], []
    bot = object.__new__(vivo.Bot)
    bot.fonte = NS(barre=lambda s, quante, passo: da_tv.append(s) or vivo.Minuti.vuoti(s, 900))
    bot.terminale = NS(barre=lambda s, quante, passo: da_mt5.append((s, quante, passo)) or vivo.Minuti.vuoti(s, 900))
    bot.strumenti = [f"S{i}" for i in range(4)]
    bot.fini = {s: vivo.Minuti.vuoti(s, 900) for s in bot.strumenti}
    bot.stato = Stato()
    bot.stato.ultimo_quarto = 0
    for nome in ("uscite", "parla"):
        setattr(bot, nome, lambda *a: None)
    bot.giro_veloce(900 * 5)
    assert da_tv == [] and [x[0] for x in da_mt5] == bot.strumenti and all(x[2] == 900 for x in da_mt5)


def test_il_bot_non_rimette_sul_tavolo_un_crt_gia_visto(tmp_path, monkeypatch):
    import vivo
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    bot = object.__new__(vivo.Bot)
    bot.stato = Stato()
    bot.stato.vive = [NS(chiave="EURUSD H4-H1 short 1 colpo 1 crt 0")]
    chiesto = []
    bot.terminale = NS(conto=lambda: chiesto.append(1))
    bot.squadra = None
    bot._decidi([NS(chiave="EURUSD H4-H1 short 1 colpo 1 crt 0")], 1, 3600)
    assert not chiesto                 # gia' aperto: non si riunisce nessuno e non si apre niente


def test_il_controllo_degli_aggiornamenti_non_dipende_dal_giro(monkeypatch):
    # Prima il controllo stava in fondo a `minuto`: se il giro si rompeva, il bot non si aggiornava piu'.
    import vivo
    chiamate = []
    bot = object.__new__(vivo.Bot)
    bot._ultimo_controllo = 0.0
    bot.aggiorna_se_serve = lambda: chiamate.append(1)
    bot.controlla_versione()
    bot.controlla_versione()                 # non prima di due minuti
    assert chiamate == [1]
    import inspect
    sorgente = inspect.getsource(vivo.main)
    assert sorgente.index("bot.controlla_versione()") > sorgente.index("bot.minuto()")
    assert "aggiorna_se_serve" not in inspect.getsource(vivo.Bot.minuto)


def test_una_posizione_chiusa_a_mano_si_riconosce():
    # Il proprietario ha chiuso tutto a mano: quei risultati non sono il metodo e la squadra non li conta.
    d = _una_decisione()
    m = MT5Finto()
    m.DEAL_REASON_CLIENT, m.DEAL_REASON_MOBILE, m.DEAL_REASON_WEB, m.DEAL_REASON_SL = 0, 1, 2, 4
    m.tick["EURUSD"] = NS(time=0, bid=d.op.ingresso, ask=d.op.ingresso + 0.0001)
    t = Terminale(mt5=m)
    t.scarto = m.scarto
    e = Esecutore(t)
    viva, _ = e.apri(d, t.conto())
    (a,) = viva.tickets
    m.chiudi(a, viva.ingresso + (0.0002 if viva.short else -0.0002))
    m.affari[a][-1].reason = m.DEAL_REASON_MOBILE          # dal telefono
    vive, fatti = e.sorveglia([viva])
    assert vive == [] and fatti[0].libro["a_mano"] and "a mano" in fatti[0].testo
    # Allo stop invece e' un risultato vero.
    viva2, _ = e.apri(replace(d, r=replace(d.r, quando=d.r.quando + 86400)), t.conto())
    (b,) = viva2.tickets
    m.chiudi(b, viva2.stop)
    m.affari[b][-1].reason = m.DEAL_REASON_SL
    vive, fatti = e.sorveglia([viva2])
    assert not fatti[0].libro["a_mano"] and "a mano" not in fatti[0].testo


def test_col_comando_piano_si_cambia_il_piano_di_un_operazione_aperta(tmp_path, monkeypatch):
    """Il proprietario, 08/10/2026, sull'SPX500 aperto con le candele di prima: *"prendere il TP1, mettere il TP finale
    e mettere a BE una volta preso il TP1 e preso il 25%"*."""
    import vivo
    from nvm.agenti.rischio import USCITE
    from nvm.vivo.esecutore import Viva
    from nvm.vivo.stato import Stato
    monkeypatch.setattr(vivo, "CARTELLA", tmp_path)
    bot = object.__new__(vivo.Bot)
    detti, spostati = [], []
    bot.tg = NS(operativo=detti.append, equipe=detti.append)
    bot.imp = NS(chat_operativo=("1",), chat_equipe=("2",))
    bot.terminale = NS(lotti=lambda s: (0.01, 0.01, 100.0),
                       sposta_stop=lambda s, t, stop, tp: (spostati.append((s, t, stop, tp)), NS(ok=True, messaggio=""))[1])
    bot.stato = Stato()
    v = Viva("k", "SPX500", "long", 0, 7778.29, 7749.44, 7791.89, 7791.89, USCITE[1], [55], 1.10, 28.48, "EUR")
    bot.stato.vive = [v]
    bot._piano(NS(chat="1", testo="/piano SPX500 7799 7832,5"))
    assert spostati == [("SPX500", 55, 7749.44, 7832.5)]
    assert (v.tp1, v.tp2, v.meta, v.uscita, v.meta_fatta) == (7799.0, 7832.5, 0.27, USCITE[0], False)
    assert "TP finale 7832.5" in detti[-1] and "0.27 lotti" in detti[-1]
    # Un TP1 sotto l'entrata di un acquisto non va: il piano resta.
    bot._piano(NS(chat="1", testo="/piano SPX500 7770 7832"))
    assert v.tp1 == 7799.0 and "sopra" in detti[-1]
    bot._piano(NS(chat="1", testo="/piano EURUSD 1.2 1.3"))
    assert "Non ho operazioni aperte su EURUSD" in detti[-1]
