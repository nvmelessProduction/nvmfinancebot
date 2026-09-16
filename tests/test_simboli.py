"""Collaudo di core/simboli.py — la traduzione fra i tre nomi di uno strumento.

Uno strumento ha tre nomi e vanno tenuti distinti, perche' confonderli e' gia'
costato due difetti gravi:

- il **future** (`6E`), su cui si analizza (DEF-32);
- il **CFD** (`EURUSD`), con cui parlano le regole (PRIN-08);
- il **simbolo del broker** (`EURUSD.a`), con cui si eseguono gli ordini.
"""

from __future__ import annotations

from core.parametri import UNIVERSO
from core.simboli import cfd_da_simbolo_esecuzione, simbolo_esecuzione


class TestAndataERitorno:
    def test_senza_suffisso_il_nome_non_cambia(self) -> None:
        assert simbolo_esecuzione("EURUSD") == "EURUSD"
        assert cfd_da_simbolo_esecuzione("EURUSD") == "EURUSD"

    def test_con_suffisso(self) -> None:
        assert simbolo_esecuzione("EURUSD", ".a") == "EURUSD.a"
        assert cfd_da_simbolo_esecuzione("EURUSD.a", ".a") == "EURUSD"

    def test_il_giro_completo_torna_al_punto_di_partenza(self) -> None:
        """Per ogni strumento e per ogni suffisso plausibile."""
        for suffisso in ("", ".a", ".pro", "m", "-ECN", ".raw"):
            for strumento in UNIVERSO:
                broker = simbolo_esecuzione(strumento, suffisso)
                assert cfd_da_simbolo_esecuzione(broker, suffisso) == strumento


class TestQuandoNonSiRiconosce:
    def test_strumento_fuori_universo(self) -> None:
        """Una posizione aperta a mano su un simbolo che il bot non tratta.

        Non e' un errore: va solo tenuta fuori dai conteggi di RISK-02 e
        RISK-06, che parlano dell'UNIVERSO di PRIN-08.
        """
        assert cfd_da_simbolo_esecuzione("BTCUSD.a", ".a") is None
        assert cfd_da_simbolo_esecuzione("US500") is None

    def test_suffisso_atteso_ma_assente(self) -> None:
        """Il broker restituisce un nome nudo benche' il suffisso sia configurato.

        Succede sui conti che suffissano solo alcune categorie. Il nome nudo e'
        gia' quello dell'UNIVERSO, e va riconosciuto lo stesso.
        """
        assert cfd_da_simbolo_esecuzione("EURUSD", ".a") == "EURUSD"

    def test_non_si_tronca_a_caso(self) -> None:
        """Il suffisso si toglie solo se e' davvero in fondo."""
        assert cfd_da_simbolo_esecuzione("EURUSD.b", ".a") is None
