"""La codifica e' una sola, e `None` non diventa mai `False`.

Se chi addestra codificasse "non lo so" come zero e chi decide lo codificasse
come "no", i pesi sarebbero giusti per un mondo e applicati a un altro -- e il
bot opererebbe con numeri che sembrano sensati. E' la famiglia di difetti che
questo progetto ha gia' trovato cinque volte, e qui c'e' la rete.
"""

from __future__ import annotations

import json
import math

import pytest

from core.pesi import (
    LE_OTTO, Pesi, caratteristiche_numeriche, carica, conviene,
    nomi_delle_colonne, probabilita, salva, valore_atteso,
)

TUTTE_NULLE = {r: None for r in LE_OTTO}


class TestLaCodifica:

    def test_ogni_conferma_ha_due_colonne(self):
        nomi = nomi_delle_colonne()
        for regola in LE_OTTO:
            assert f"{regola}=si" in nomi
            assert f"{regola}=no" in nomi

    def test_non_lo_so_e_il_caso_di_riferimento(self):
        """`None` mette a zero ENTRAMBE le colonne. Con una colonna sola
        finirebbe schiacciato su un lato, e nel campo di prova `CRT-10`
        risponde `None` sul 98% dei CRT."""
        vettore = caratteristiche_numeriche(TUTTE_NULLE, None, 2.0)
        for nome, valore in zip(nomi_delle_colonne(), vettore):
            if nome.endswith("=si") or nome.endswith("=no"):
                assert valore == 0.0, nome

    def test_si_e_no_sono_distinguibili(self):
        si = caratteristiche_numeriche({**TUTTE_NULLE, "CRT-11": True}, None, 2.0)
        no = caratteristiche_numeriche({**TUTTE_NULLE, "CRT-11": False}, None, 2.0)
        assert si != no
        nulla = caratteristiche_numeriche(TUTTE_NULLE, None, 2.0)
        assert si != nulla and no != nulla

    def test_il_vettore_ha_la_lunghezza_dei_nomi(self):
        vettore = caratteristiche_numeriche(TUTTE_NULLE, 2, 3.0)
        assert len(vettore) == len(nomi_delle_colonne())

    def test_allineati_none_non_e_zero_allineati(self):
        """`CRT-06` a `None` significa "non c'e' nessun altro CRT", non
        "nessuno e' d'accordo". Sono due cose diverse e restano diverse."""
        indice_si = nomi_delle_colonne().index("CRT-06=si")
        ignoto = caratteristiche_numeriche(TUTTE_NULLE, None, 2.0)
        zero = caratteristiche_numeriche({**TUTTE_NULLE, "CRT-06": False}, 0, 2.0)
        assert ignoto[indice_si] == 0.0
        assert ignoto != zero

    def test_il_conteggio_e_a_soglie(self):
        uno = caratteristiche_numeriche(TUTTE_NULLE, 1, 2.0)
        due = caratteristiche_numeriche(TUTTE_NULLE, 2, 2.0)
        nomi = nomi_delle_colonne()
        assert uno[nomi.index("allineati>=1")] == 1.0
        assert uno[nomi.index("allineati>=2")] == 0.0
        assert due[nomi.index("allineati>=2")] == 1.0

    def test_il_rapporto_entra_in_logaritmo(self):
        """Mediana 2,21 e novantesimo percentile 8,58: in scala lineare le
        poche code deciderebbero da sole tutti i pesi."""
        nomi = nomi_delle_colonne()
        v = caratteristiche_numeriche(TUTTE_NULLE, None, math.e)
        assert v[nomi.index("log(RR)")] == pytest.approx(1.0)

    def test_un_rapporto_nullo_non_fa_esplodere_niente(self):
        v = caratteristiche_numeriche(TUTTE_NULLE, None, 0.0)
        assert math.isfinite(v[-1])


class TestLaProbabilita:

    def test_senza_pesi_vale_una_moneta(self):
        p = probabilita(Pesi(intercetta=0.0), [0.0] * len(nomi_delle_colonne()))
        assert p == pytest.approx(0.5)

    def test_resta_fra_zero_e_uno_anche_agli_estremi(self):
        """Un esponenziale che trabocca solleverebbe un'eccezione, e un
        modello che ferma il bot non e' un modello."""
        for z in (-10_000.0, -50.0, 50.0, 10_000.0):
            p = probabilita(Pesi(intercetta=z), [0.0] * len(nomi_delle_colonne()))
            assert 0.0 <= p <= 1.0

    def test_un_peso_positivo_alza_la_probabilita(self):
        colonne = {"CRT-11=si": 2.0}
        v = caratteristiche_numeriche({**TUTTE_NULLE, "CRT-11": True}, None, 1.0)
        senza = probabilita(Pesi(0.0, {}), v)
        con = probabilita(Pesi(0.0, colonne), v)
        assert con > senza


class TestLaRegolaDIngresso:
    """`p x RR - (1 - p) - costi > 0`, non `p > qualcosa`."""

    def test_una_probabilita_bassa_su_un_rapporto_alto_puo_convenire(self):
        assert conviene(0.30, rapporto=5.0, costo_in_erre=0.05)

    def test_una_probabilita_alta_su_un_rapporto_misero_puo_non_convenire(self):
        assert not conviene(0.55, rapporto=0.5, costo_in_erre=0.05)

    def test_i_costi_possono_ribaltare_il_verdetto(self):
        """Su stop stretti il costo e' una frazione grande del rischio: e'
        esattamente il caso in cui un backtest senza costi mente."""
        assert conviene(0.40, rapporto=1.60, costo_in_erre=0.0)
        assert not conviene(0.40, rapporto=1.60, costo_in_erre=0.30)

    def test_il_margine_tiene_fuori_il_rumore(self):
        """Un vantaggio di un millesimo di R non e' un vantaggio."""
        p, rr = 0.4, 1.68
        assert valore_atteso(p, rr, 0.0) > 0
        assert not conviene(p, rr, 0.0, margine=0.10)

    def test_il_valore_atteso_e_in_erre(self):
        # p=0,5 su RR=3: metà delle volte +3, metà -1 => +1 di media.
        assert valore_atteso(0.5, 3.0, 0.0) == pytest.approx(1.0)


class TestIlFileDeiPesi:

    def test_andata_e_ritorno(self, tmp_path):
        pesi = Pesi(intercetta=-0.3, per_colonna={"CRT-11=si": 0.42},
                    addestrato_su="2006-2023", righe=16463, brier=0.21)
        percorso = tmp_path / "pesi.json"
        salva(pesi, percorso)
        tornati = carica(percorso)
        assert tornati is not None
        assert tornati.intercetta == pytest.approx(-0.3)
        assert tornati.per_colonna["CRT-11=si"] == pytest.approx(0.42)
        assert tornati.righe == 16463

    def test_senza_file_non_si_inventa_un_modello(self, tmp_path):
        assert carica(tmp_path / "nessuno.json") is None

    def test_colonne_diverse_fanno_rifiutare_il_file(self, tmp_path):
        """Se un giorno si aggiungesse una colonna, un file vecchio verrebbe
        applicato con i pesi spostati di posto. Meglio nessun modello che un
        modello storto."""
        percorso = tmp_path / "pesi.json"
        percorso.write_text(json.dumps({
            "intercetta": 0.0, "per_colonna": {},
            "colonne": ["una", "colonna", "che", "non", "esiste"],
        }), encoding="utf-8")
        assert carica(percorso) is None

    def test_i_pesi_si_possono_leggere_in_chiaro(self):
        """Un vettore di numeri senza nomi non e' controllabile da nessuno,
        e un modello che nessuno puo' controllare non puo' operare."""
        testo = Pesi(-0.3, {"CRT-11=si": 0.42, "CRT-20=no": -0.01}).leggibile()
        assert "CRT-11=si" in testo
        # Il piu' forte per primo.
        assert testo.index("CRT-11=si") < testo.index("CRT-20=no")
