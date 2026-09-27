"""L'equipe come una chat fra professionisti (`nvm/vivo/conversazione.py`)."""

import numpy as np

from nvm.agenti.capo import COLONNE
from nvm.vivo import conversazione
from nvm.vivo.ambiente import Impostazioni, impostazioni
from nvm.vivo.conversazione import Voce
from nvm.vivo.stato import Seguita
from nvm.vivo.telegram import Telegram
from tests.test_vivo import _una_decisione

GERGO = ("Model#1", " R ", "firma", "colonn", "spinta", "Kelly", "qualità attesa")


def test_su_un_operazione_aperta_parla_chi_ha_pesato_e_il_capo_chiude():
    d = _una_decisione()
    per = {"Orario": 0.08, "Bias": -0.05, "Key level": 0.01, "Livelli": 0.02}
    voci = conversazione.apertura(d, per, None, 0.008, 3, 0.021)
    chi = [v.chi for v in voci]
    assert chi[0] == "Grilletto" and chi[-1] == "Capo" and "Rischio" in chi
    assert "Orario" in chi and "Bias" in chi and "Key level" not in chi     # chi non ha pesato non parla
    testo = conversazione.insieme(voci)
    assert all(g not in testo for g in GERGO), testo
    assert "0,8% del conto" in testo and "2,1% del conto" in testo and "3 operazioni aperte" in testo
    assert next(v for v in voci if v.chi == "Bias").testo.startswith("Attenzione")
    # Il Rischio spiega perche' rischia meno: e' legata a operazioni gia' aperte.
    voci = conversazione.apertura(d, per, None, 0.004, 3, 0.021, da_sola=0.008, legate=("GBPUSD",))
    rischio = next(v for v in voci if v.chi == "Rischio").testo
    assert "Da sola sarebbe 0,8%, ma è legata a GBPUSD, già aperta" in rischio


def test_le_prove_dicono_quante_volte_su_cento():
    x = np.zeros((300, len(COLONNE)))
    x[:200, COLONNE.index("ora 09-13")] = 1
    tp1 = np.r_[np.ones(120), np.zeros(80), np.ones(30), np.zeros(70)].astype(bool)
    storia = conversazione.prove(x, tp1)
    assert storia["Orario"]["09–13 NY"] == (200, 0.6)
    frase = conversazione._prova("Orario", "09–13 NY", storia)
    assert "60 volte su 100" in frase and "di solito 50" in frase


def _seguita(chiave, quando, entrata, erre=None):
    s = Seguita(chiave, "EURUSD", "D1", "H1", "short", quando, 1.1, 1.101, 1.099, 1.098, 10**9, entrata,
                [0.0] * len(COLONNE), 1.0, 2.0, 0.0, 0.5, 0.3, 0.1)
    if erre is not None:
        s.esito = {"uscita": "stop", "erre": erre, "quando": quando + 3600, "tp1": erre > 0, "tp2": False}
    return s


def test_il_riepilogo_della_sera_e_un_messaggio_solo_e_chiaro():
    seguite = [_seguita("a", 1000, True, 1.5), _seguita("b", 2000, True, -1.0), _seguita("c", 3000, False, -1.0),
               _seguita("d", 4000, False, None)]
    testo = conversazione.riepilogo(seguite, 0, 86400, 2, 0.015, ["Livelli: «stop almeno a 0,3» avrebbe fatto meglio 3 volte"])
    assert "Occasioni guardate: 4 · prese: 2 · lasciate: 2" in testo
    assert "Operazioni chiuse: 2 (1 in guadagno)" in testo and "+0,50 volte il rischio" in testo
    assert "ha fatto bene a lasciarle" in testo and "1,5% del conto" in testo and "Da ricordare" in testo


def test_il_riepilogo_conta_le_saltate_e_tace_se_non_e_successo_niente():
    testo = conversazione.riepilogo([_seguita("a", 1000, False)], 0, 86400, 0, 0.0, [],
                                    {"conto troppo piccolo per il lotto minimo": 2, "il prezzo era già oltre lo stop": 1})
    assert "Il Capo ne voleva altre 3, non aperte: 2 conto troppo piccolo per il lotto minimo, 1 il prezzo" in testo
    # Il sabato non succede niente: niente messaggio.
    assert conversazione.riepilogo([], 0, 86400, 0, 0.0, []) == ""


def test_ogni_agente_puo_avere_il_suo_bot(tmp_path):
    (tmp_path / ".env").write_text("TELEGRAM_TOKEN=principale\nTELEGRAM_CHAT_EQUIPE=-2\n"
                                   "TELEGRAM_TOKEN_GRILLETTO=g\nTELEGRAM_TOKEN_KEY_LEVEL=k\n")
    imp = impostazioni(tmp_path, ambiente={})
    assert imp.voci == {"Grilletto": "g", "Key level": "k"} and "g" not in repr(imp)
    da_bot, principale = [], []
    tg = Telegram(imp, invia=lambda c, t: principale.append(t), invia_come=lambda tok, c, t: da_bot.append((tok, t)),
                  stampa=lambda _: None)
    tg.voci([Voce("Grilletto", "Entro."), Voce("Capo", "Confermo.")])
    assert da_bot == [("g", "Entro.")] and principale == ["👔 Capo: Confermo."]
    # Senza bot propri: un messaggio solo con tutte le voci.
    senza = Telegram(Impostazioni(token="x", chat_equipe=("-2",)), invia=lambda c, t: principale.append(t),
                     stampa=lambda _: None)
    principale.clear()
    senza.voci([Voce("Grilletto", "Entro."), Voce("Capo", "Confermo.")])
    assert principale == ["🎯 Grilletto: Entro.\n👔 Capo: Confermo."]


def test_una_prova_si_cita_solo_se_sostiene_quello_che_si_dice():
    x = np.zeros((300, len(COLONNE)))
    x[:200, COLONNE.index("ora 09-13")] = 1
    tp1 = np.r_[np.ones(120), np.zeros(80), np.ones(30), np.zeros(70)].astype(bool)
    storia = conversazione.prove(x, tp1)
    assert "60 volte su 100" in conversazione._prova("Orario", "09–13 NY", storia, True)
    assert conversazione._prova("Orario", "09–13 NY", storia, False) == ""


def test_il_grilletto_non_parla_due_volte():
    d = _una_decisione()
    voci = conversazione.apertura(d, {"Grilletto": -0.08, "Orario": 0.05}, None, 0.004, 1, 0.004)
    assert [v.chi for v in voci].count("Grilletto") == 1
    assert "Attenzione." in voci[0].testo and voci[-1].chi == "Capo"
