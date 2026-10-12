"""La consegna dei dati dalla VPS alla palestra (`strumenti/consegna.py`)."""

import subprocess

import numpy as np

from strumenti import consegna
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti, file_del_mese
from nvm.tempo import TF, utc
from tests.aiuti import passeggiata


def test_i_quarti_d_ora_sono_quelli_dei_minuti():
    m = passeggiata("EURUSD", utc(2023, 3, 1), utc(2023, 3, 3), seme=3)
    q = consegna.a_quarti(m)
    assert q.passo == 900 and np.all(q.t % 900 == 0)
    dai_minuti = costruisci(m, TF.M15)
    dai_quarti = costruisci(q, TF.M15)
    assert np.array_equal(dai_minuti.inizio, dai_quarti.inizio)
    assert np.allclose(dai_minuti.bid, dai_quarti.bid) and np.allclose(dai_minuti.ask, dai_quarti.ask)
    # E le 4 ore fatte dai quarti sono le stesse fatte dai minuti.
    assert np.allclose(costruisci(m, TF.H4).bid, costruisci(q, TF.H4).bid)


def test_con_i_quarti_la_tabella_ha_anche_la_coppia_4_ore_15_minuti():
    from nvm.agenti import inventate
    from nvm.agenti.capo import COLONNE
    from nvm.prova.allenamento import risposte
    from nvm.prova.cammino import costruisci_tabella
    coppie = ((TF.W1, TF.H4), (TF.D1, TF.H1))
    m = passeggiata("EURUSD", utc(2023, 1, 2), utc(2023, 4, 1), seme=7)
    basi = {"EURUSD": consegna.a_quarti(m, 3600)}
    quarti = {"EURUSD": consegna.a_quarti(m)}
    dal, al = utc(2023, 2, 1), utc(2023, 4, 1)
    senza = costruisci_tabella(basi, coppie, dal, al)
    con = costruisci_tabella(basi, coppie, dal, al, quarti=quarti)
    veloce = con.x[:, COLONNE.index("coppia H4-M15")] == 1
    assert veloce.sum() > 0 and len(con) == len(senza) + veloce.sum()
    # Le risposte delle domande inventate restano allineate con le righe della tabella.
    assert risposte(inventate.PRIME["Gap"][:1], basi, coppie, dal, al, quarti).shape == (len(con), 1)


def test_un_file_per_anno_rifatto_solo_se_arrivano_minuti_nuovi(tmp_path):
    grezzi = tmp_path / "grezzi"
    for mese in (1, 2):
        passeggiata("EURUSD", utc(2023, mese, 1), utc(2023, mese, 2), seme=mese).salva(
            file_del_mese(grezzi / "minuti", "EURUSD", 2023, mese))
    uscita = tmp_path / "uscita"
    assert consegna.quarti(grezzi, uscita) == 1
    anno = Minuti.carica(uscita / "quarti" / "EURUSD" / "EURUSD-2023.npz")
    assert anno.passo == 900 and len(anno) == 2 * 96
    assert consegna.quarti(grezzi, uscita) == 0


def test_spedisce_sul_ramo_dei_dati_senza_toccare_il_resto(tmp_path):
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remoto)], check=True)
    uscita = tmp_path / "uscita"
    (uscita / "vivo").mkdir(parents=True)
    (uscita / "vivo" / "stato.json").write_text("{}")
    assert consegna.spedisci(uscita, str(remoto), "") == "spedito"
    assert consegna.spedisci(uscita, str(remoto), "") == "niente di nuovo"
    elenco = subprocess.run(["git", "--git-dir", str(remoto), "ls-tree", "-r", "--name-only", consegna.RAMO],
                            capture_output=True, text=True, check=True).stdout.split()
    assert elenco == ["vivo/stato.json"]
    # Una cartella rifatta da capo (per esempio su un'altra VPS) riparte dal ramo che c'e' gia'.
    altra = tmp_path / "altra"
    (altra / "vivo").mkdir(parents=True)
    (altra / "vivo" / "stato.json").write_text('{"nuovo": 1}')
    assert consegna.spedisci(altra, str(remoto), "") == "spedito"
    ultimo = subprocess.run(["git", "--git-dir", str(remoto), "show", f"{consegna.RAMO}:vivo/stato.json"],
                            capture_output=True, text=True, check=True).stdout
    assert ultimo == '{"nuovo": 1}'


def test_il_token_non_finisce_mai_nei_comandi():
    ambiente = consegna._con_token("segreto123", "https://github.com/a/b")
    assert "segreto123" not in " ".join(ambiente.values())
    assert ambiente["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert consegna._con_token("", "https://github.com/a/b") == {}


def test_nessun_segreto_del_env_esce_dalla_vps(tmp_path):
    env = {"TELEGRAM_TOKEN": "finto:TOKEN123", "MT5_PASSWORD": "finta-pw-99", "GITHUB_TOKEN": "finto_pat_xyz",
           "TELEGRAM_CHAT_ID": "-100", "MT5_SUFFISSO_SIMBOLI": ""}
    nascosti = consegna.segreti(env)
    assert set(nascosti) == {"finto:TOKEN123", "finta-pw-99", "finto_pat_xyz"}
    cartella = tmp_path / "vivo"
    cartella.mkdir()
    (cartella / "registro.jsonl").write_text('{"testo": "errore su https://esempio/botfinto:TOKEN123/x"}\n')
    (cartella / "stato.json").write_text('{"ultimo_giro": 1}')
    assert consegna.vivo(cartella, tmp_path / "uscita", nascosti) == ["stato.json", "registro.jsonl"]
    spedito = (tmp_path / "uscita" / "vivo" / "registro.jsonl").read_text()
    assert "TOKEN123" not in spedito and "***" in spedito
    assert (tmp_path / "uscita" / "vivo" / "stato.json").read_text() == '{"ultimo_giro": 1}'


def test_il_bot_spedisce_le_settimane_solo_se_c_e_il_token(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    import vivo
    partiti = []
    monkeypatch.setattr(vivo, "RADICE", tmp_path)
    monkeypatch.setattr(vivo.subprocess, "Popen", lambda comando, **k: partiti.append(comando))
    vivo.Bot.consegna(NS())
    assert partiti == []
    (tmp_path / ".env").write_text("TELEGRAM_TOKEN=x\nGITHUB_TOKEN=abc\n")
    vivo.Bot.consegna(NS())
    assert len(partiti) == 1 and partiti[0][-1] == "--solo-vivo" and "abc" not in " ".join(partiti[0])


def test_le_ore_delle_coppie_nuove_vanno_e_tornano_un_mese_per_file(tmp_path):
    from strumenti.importa_vps import salva_mesi_nuovi
    grezzi = tmp_path / "grezzi"
    for mese in (1, 2):
        ore = consegna.a_quarti(passeggiata("EURGBP", utc(2020, mese, 1), utc(2020, mese, 3), seme=mese), 3600)
        ore.salva(file_del_mese(grezzi / "ore", "EURGBP", 2020, mese))
    uscita = tmp_path / "uscita"
    assert consegna.ore(grezzi, uscita) == 1
    anno = Minuti.carica(uscita / "ore" / "EURGBP" / "EURGBP-2020.npz")
    assert anno.passo == 3600 and len(anno) == 2 * 48
    arrivo = tmp_path / "arrivo"
    file_del_mese(arrivo, "EURGBP", 2020, 1).parent.mkdir(parents=True)
    gia = Minuti.vuoti("EURGBP", 3600)
    gia.salva(file_del_mese(arrivo, "EURGBP", 2020, 1))
    # Il mese che c'era gia' non si tocca; quello che mancava arriva.
    assert salva_mesi_nuovi(anno, arrivo) == 1
    assert len(Minuti.carica(file_del_mese(arrivo, "EURGBP", 2020, 1))) == 0
    assert len(Minuti.carica(file_del_mese(arrivo, "EURGBP", 2020, 2))) == 48
