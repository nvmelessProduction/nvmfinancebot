"""I video di Romeo fatti sul computer di casa arrivano alla VPS in un pacco solo."""

import json

import consegna
import video


def test_il_pacco_di_casa_si_apre_sulla_vps(tmp_path):
    casa = tmp_path / "casa" / "video"
    (casa / "abc").mkdir(parents=True)
    (casa / "abc" / "s00000.jpg").write_bytes(b"foto")
    (casa / "abc" / "parole.vtt").write_text("WEBVTT\n")
    (casa / "abc" / "fatto.json").write_text(json.dumps({"id": "abc"}))
    (casa / "def").mkdir()
    (casa / "def" / "s00000.jpg").write_bytes(b"x" * 300_000)
    bot = tmp_path / "bot"
    bot.mkdir()
    pacchi = video.impacchetta(casa, bot, massimo_mb=0.2)       # un video per pacco, sotto la misura
    assert [p.name for p in pacchi] == ["video_romeo_1.zip", "video_romeo_2.zip"]
    uscita = tmp_path / "consegna"
    (uscita / "video" / "abc").mkdir(parents=True)
    (uscita / "video" / "abc" / "parole.vtt").write_text("gia' qui\n")
    assert consegna.video_da_casa([bot, tmp_path / "Desktop"], uscita) == 3
    assert (uscita / "video" / "abc" / "s00000.jpg").read_bytes() == b"foto"
    assert (uscita / "video" / "abc" / "parole.vtt").read_text() == "gia' qui\n"   # non si sovrascrive
    assert not (bot / "video_romeo_1.zip").exists() and (bot / "video_romeo_1.importato.zip").exists()
    assert consegna.video_da_casa([bot], uscita) == 0


def test_i_pacchi_caricati_su_github_si_aprono_in_palestra(tmp_path):
    import importa_vps
    casa = tmp_path / "casa" / "video"
    (casa / "abc").mkdir(parents=True)
    (casa / "abc" / "s00015.jpg").write_bytes(b"foto")
    (pacco,) = video.impacchetta(casa, tmp_path)
    dove = tmp_path / "vps"
    assert importa_vps.apri_pacco(pacco.read_bytes(), dove) == 1
    assert (dove / "video" / "abc" / "s00015.jpg").read_bytes() == b"foto"
    assert importa_vps.apri_pacco(pacco.read_bytes(), dove) == 0
