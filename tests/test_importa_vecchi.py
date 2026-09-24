"""L'importazione dei file di Dukascopy del vecchio bot."""

import zipfile

from importa_vecchi import destinazione, importa


def test_i_nomi_vecchi_diventano_quelli_nuovi(tmp_path):
    assert destinazione("dukascopy/EURUSD_2024_00_BID_candles_hour_1.bi5", tmp_path) == tmp_path / "EURUSD/ore/2024-01_BID.bi5"
    assert destinazione("EURUSD_2026_07_15_ASK_candles_min_1.bi5", tmp_path) == tmp_path / "EURUSD/2026/08/15_ASK.bi5"
    assert destinazione("bot.db", tmp_path) is None


def test_da_uno_zip_senza_sovrascrivere(tmp_path):
    archivio = tmp_path / "vecchi.zip"
    with zipfile.ZipFile(archivio, "w") as z:
        z.writestr("dukascopy/EURUSD_2024_00_BID_candles_hour_1.bi5", b"dati")
        z.writestr("dukascopy/EURUSD_2024_01_BID_candles_hour_1.bi5", b"")
        z.writestr("dukascopy/leggimi.txt", b"x")
    cache = tmp_path / "cache"
    (cache / "EURUSD/ore").mkdir(parents=True)
    (cache / "EURUSD/ore/2024-02_BID.bi5").write_bytes(b"gia' qui")
    conti = importa([archivio], cache)
    assert conti == {"copiati": 1, "gia_presenti": 1, "vuoti": 0, "ignorati": 0}
    assert (cache / "EURUSD/ore/2024-01_BID.bi5").read_bytes() == b"dati"
    assert (cache / "EURUSD/ore/2024-02_BID.bi5").read_bytes() == b"gia' qui"
