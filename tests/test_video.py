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
    bot = tmp_path / "bot"
    bot.mkdir()
    video.impacchetta(casa, bot / "video_romeo.zip")
    uscita = tmp_path / "consegna"
    (uscita / "video" / "abc").mkdir(parents=True)
    (uscita / "video" / "abc" / "parole.vtt").write_text("gia' qui\n")
    assert consegna.video_da_casa([bot, tmp_path / "Desktop"], uscita) == 2
    assert (uscita / "video" / "abc" / "s00000.jpg").read_bytes() == b"foto"
    assert (uscita / "video" / "abc" / "parole.vtt").read_text() == "gia' qui\n"   # non si sovrascrive
    assert not (bot / "video_romeo.zip").exists() and (bot / "video_romeo.importato.zip").exists()
    assert consegna.video_da_casa([bot], uscita) == 0
