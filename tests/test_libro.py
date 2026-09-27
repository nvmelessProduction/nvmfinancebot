"""Il libro delle operazioni vere (`nvm/vivo/libro.py`)."""

import json

from nvm.vivo import libro


def test_il_libro_si_accorge_se_qualcuno_lo_tocca(tmp_path):
    libro.scrivi(tmp_path, "apertura", quando=1_700_000_000, strumento="EURUSD", rischio=10.0)
    libro.scrivi(tmp_path, "chiusura", quando=1_700_086_400, strumento="EURUSD", erre=1.5, netto=15.0, saldo=1015.0,
                 valuta="EUR")
    libro.scrivi(tmp_path, "chiusura", quando=1_702_700_000, strumento="GBPUSD", erre=-1.0, netto=-10.0, saldo=1005.0,
                 valuta="EUR")
    assert libro.verifica(tmp_path) == (True, "il libro è integro")
    testo = libro.rendiconto(tmp_path)
    assert "Operazioni chiuse: 2 · in guadagno: 1 (50%)" in testo and "+0,50 volte il rischio" in testo
    assert "11/2023" in testo and "12/2023" in testo
    # Qualcuno trasforma la perdita in guadagno: la catena si rompe.
    p = tmp_path / libro.LIBRO
    righe = p.read_text(encoding="utf-8").splitlines()
    falsa = json.loads(righe[2])
    falsa["erre"] = 1.0
    righe[2] = json.dumps(falsa, ensure_ascii=False)
    p.write_text("\n".join(righe) + "\n", encoding="utf-8")
    assert libro.verifica(tmp_path) == (False, "il libro è stato toccato alla riga 3")
    # E anche se si toglie una riga.
    p.write_text("\n".join([righe[0], righe[2]]) + "\n", encoding="utf-8")
    assert not libro.verifica(tmp_path)[0]
