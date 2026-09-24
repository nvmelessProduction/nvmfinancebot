"""La carriera degli agenti: che si scelga sul passato e si misuri sul futuro.

Il modo piu' facile di fabbricare un agente bravissimo e' scegliere il suo
numero guardando gli stessi dati su cui poi lo si misura. Non sbaglia:
indovina. Questi test recintano il punto in cui succederebbe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))

import griglie                                                  # noqa: E402
from impara_agenti import (                                     # noqa: E402
    _confronto_appaiato, _valori, cammina, carriera,
    scegli_sul_passato, sorvegliati_speciali, stabilita_della_scelta,
)


PAREGGIO = griglie.GRIGLIE[0]


def riga(anno, strumento="EURUSD", coppia="TF_1D->TF_H1", **cammini) -> dict:
    d = {"strumento": strumento, "coppia": coppia,
         "quando": f"{anno}-06-01T00:00:00+00:00", "barre": "3"}
    for colonna in griglie.colonne_delle_griglie():
        d[colonna] = ""
    for nome, valore in cammini.items():
        d[nome.replace("_", ".", 1).replace("k0.", "k0.")] = valore
    return d


def riga_pareggio(anno, valori: dict, strumento="EURUSD") -> dict:
    """Una riga con solo le colonne della griglia del pareggio riempite."""
    d = {"strumento": strumento, "coppia": "TF_1D->TF_H1",
         "quando": f"{anno}-06-01T00:00:00+00:00", "barre": "3"}
    for colonna in griglie.colonne_delle_griglie():
        d[colonna] = ""
    for k, erre in valori.items():
        d[PAREGGIO.nome_colonna(k)] = f"{erre:.4f}"
    return d


class TestLeCelleVuote:

    def test_una_cella_vuota_non_e_un_pareggio(self):
        """"Non misurabile" non e' zero. Trattarlo come zero gonfierebbe di
        pareggi finti proprio le griglie con piu' casi incoerenti."""
        righe = [riga_pareggio(2010, {0.0: 1.0}),
                 riga_pareggio(2010, {})]
        valori, indici = _valori(righe, PAREGGIO.nome_colonna(0.0))
        assert valori == [1.0]
        assert indici == [0]

    def test_il_confronto_e_appaiato(self):
        """Confrontare due medie su insiemi diversi direbbe soprattutto quali
        CRT sono capitati a chi. Su differenze da centesimi di R, basta a
        inventare un vincitore."""
        righe = [riga_pareggio(2010, {0.0: 1.0, 0.5: 2.0}),
                 riga_pareggio(2010, {0.0: 5.0})]           # 0.5 non misurato
        d, gruppi = _confronto_appaiato(
            righe, ["a", "b"], PAREGGIO.nome_colonna(0.5),
            PAREGGIO.nome_colonna(0.0))
        assert d == [1.0], "solo la riga dove entrambi esistono"
        assert gruppi == ["a"]


class TestLaScelta:

    def test_prende_il_candidato_migliore(self):
        righe = [riga_pareggio(2010, {0.0: 0.0, 0.75: 1.0})
                 for _ in range(100)]
        scelto = scegli_sul_passato(righe, PAREGGIO, range(100))
        assert scelto == pytest.approx(0.75)

    def test_senza_abbastanza_casi_resta_il_manuale(self):
        """Un candidato con pochi casi non si sceglie: e' il modo piu' rapido
        di farsi convincere da tre operazioni fortunate."""
        righe = [riga_pareggio(2010, {0.0: 0.0}) for _ in range(100)]
        righe[0][PAREGGIO.nome_colonna(0.75)] = "99.0"
        assert scegli_sul_passato(righe, PAREGGIO, range(100)) == pytest.approx(
            PAREGGIO.competenza.predefinito)


class TestIlWalkForward:

    def test_si_sceglie_sul_passato_e_si_misura_sul_futuro(self):
        """Il candidato dell'anno N e' scelto sugli anni < N, e la differenza
        e' misurata su N."""
        righe = []
        for anno in range(2006, 2016):
            for _ in range(100):
                righe.append(riga_pareggio(anno, {0.0: 0.0, 0.75: 0.5}))
        blocchi = [f"b{i}" for i in range(len(righe))]
        differenze, gruppi, scelte = cammina(righe, blocchi, PAREGGIO,
                                             2010, 2015)
        assert scelte and all(s == pytest.approx(0.75) for s in scelte)
        assert differenze and all(d == pytest.approx(0.5) for d in differenze)
        # 2010 si salta: davanti ha solo 400 righe (2006-2009) e ne servono
        # 500. Restano 2011-2015, cioe' cinque anni da cento.
        assert len(scelte) == 5
        assert len(differenze) == 100 * 5

    def test_un_anno_senza_abbastanza_casi_si_salta(self):
        righe = [riga_pareggio(2006, {0.0: 0.0}) for _ in range(600)]
        righe += [riga_pareggio(2011, {0.0: 0.0}) for _ in range(3)]
        blocchi = [f"b{i}" for i in range(len(righe))]
        _, _, scelte = cammina(righe, blocchi, PAREGGIO, 2010, 2015)
        assert scelte == []


class TestLaStabilita:

    def test_scegliere_sempre_lo_stesso_vale_uno(self):
        assert stabilita_della_scelta([0.75] * 5, 0.0) == pytest.approx(1.0)

    def test_cambiare_ogni_anno_scende(self):
        """Un agente che ogni anno sceglie un numero diverso non ha trovato
        una proprieta' del mercato: ha trovato il rumore di quell'anno."""
        assert stabilita_della_scelta([0.0, 0.25, 0.5, 0.75], 0.0) < 0.5

    def test_se_vince_il_manuale_non_c_e_carriera(self):
        """Nessuna promozione da dare: la stabilita' e' zero per
        costruzione, e il cancello si chiude da solo."""
        assert stabilita_della_scelta([0.0] * 5, 0.0) == 0.0

    def test_senza_scelte_e_zero(self):
        assert stabilita_della_scelta([], 0.0) == 0.0


class TestLaCarriera:

    def _righe(self, vantaggio: float, anni=range(2006, 2020), quante=100):
        caso = np.random.default_rng(7)
        righe = []
        for anno in anni:
            for _ in range(quante):
                base = float(caso.normal(0, 0.5))
                righe.append(riga_pareggio(
                    anno, {0.0: base, 0.75: base + vantaggio}))
        return righe

    def test_un_vantaggio_vero_porta_alla_promozione(self):
        righe = self._righe(vantaggio=0.30)
        blocchi = [f"b{i}" for i in range(len(righe))]
        appreso = carriera(righe, blocchi, PAREGGIO, 300, 2010, 2019)
        assert appreso.promosso(PAREGGIO.competenza), appreso.perche_no(
            PAREGGIO.competenza)
        assert appreso.valore == pytest.approx(0.75)

    def test_nessun_vantaggio_non_promuove(self):
        righe = self._righe(vantaggio=0.0)
        blocchi = [f"b{i}" for i in range(len(righe))]
        appreso = carriera(righe, blocchi, PAREGGIO, 300, 2010, 2019)
        assert not appreso.promosso(PAREGGIO.competenza)

    def test_senza_finestre_resta_neolaureato(self):
        appreso = carriera([], [], PAREGGIO, 100, 2010, 2019)
        assert appreso.campioni == 0
        assert appreso.valore == pytest.approx(PAREGGIO.competenza.predefinito)
        assert not appreso.promosso(PAREGGIO.competenza)


class TestISorvegliatiSpeciali:
    """Un agente nullo in media puo' aver ragione dentro una fetta, e una
    misura globale lo seppellisce."""

    def test_trova_l_effetto_che_vive_in_una_fetta_sola(self):
        righe = ([riga_pareggio(2010, {0.0: 0.0, 0.75: 0.5}, "XAUUSD")
                  for _ in range(300)]
                 + [riga_pareggio(2010, {0.0: 0.0, 0.75: 0.0}, "EURUSD")
                    for _ in range(300)])
        blocchi = [f"b{i}" for i in range(len(righe))]
        trovati = sorvegliati_speciali(righe, blocchi, PAREGGIO)
        assert any("XAUUSD" in t for t in trovati)
        assert not any("EURUSD" in t for t in trovati)

    def test_una_fetta_troppo_piccola_non_conta(self):
        """Tre operazioni fortunate su uno strumento non sono un effetto."""
        righe = [riga_pareggio(2010, {0.0: 0.0, 0.75: 5.0}, "XAUUSD")
                 for _ in range(10)]
        blocchi = [f"b{i}" for i in range(len(righe))]
        assert sorvegliati_speciali(righe, blocchi, PAREGGIO) == []

    def test_non_promuove_nessuno(self):
        """Segnala e basta: un effetto trovato guardando venti fette e
        tenendo la migliore e' il modo classico di trovare qualcosa che non
        c'e'."""
        import inspect
        import impara_agenti
        corpo = inspect.getsource(impara_agenti.sorvegliati_speciali)
        assert "Appreso" not in corpo
        assert "-> list[str]" in corpo
