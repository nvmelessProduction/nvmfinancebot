"""Stiamo girando dentro una suite di prove?

Domanda banale, risposta importante: questo impianto ha due porte che danno
sul mondo e costano davvero.

Telegram: `ingresso_ltf.arma()` notifica, e la suite lo chiama una dozzina di
volte coi valori inventati del suo fixture. Per mesi ogni `pytest tests/` ha
spedito sul telefono dell'utente una fila di "EURUSD: setup ribassista armato,
spazzato 110,000" -- numeri che non somigliano a un cambio, perche' non lo
sono. Hanno sepolto i messaggi veri.

L'API di Claude: da quando il giudizio viene interpellato anche sui CRT
rifiutati, una valutazione dentro una prova diventa una chiamata a pagamento.
Misurato il 2026-09-21: acceso il giudizio, la suite e' passata da 5 secondi a
135 e ha bruciato credito vero -- e il tetto di spesa non se ne e' accorto,
perche' le prove scrivono il loro conto in un archivio temporaneo.

Il rimedio non puo' essere "ricordarsi di simulare la cosa giusta in ogni
prova che tocca quel percorso": e' il promemoria che salta alla prossima prova
scritta di fretta. Le porte si chiudono qui, una volta, e restano chiuse.

`PYTEST_CURRENT_TEST` lo valorizza pytest da solo ad ogni prova, quindi copre
anche un file nuovo che si dimenticasse del conftest.
"""

from __future__ import annotations

import os

VARIABILE_SILENZIO: str = "NVMBOT_NIENTE_TELEGRAM"
VARIABILE_PROVE: str = "NVMBOT_IN_PROVA"
VARIABILE_BROKER_FINTO: str = "NVMBOT_BROKER_FINTO"


def in_prova() -> bool:
    """True se questo processo sta girando dentro una suite di prove."""
    return bool(os.environ.get(VARIABILE_PROVE)
                or os.environ.get(VARIABILE_SILENZIO)
                or os.environ.get("PYTEST_CURRENT_TEST"))


def broker_finto() -> bool:
    """Chi gira questa prova ha gia' sostituito MT5 con un doppione?

    Il freno sugli ordini non puo' dedurlo: `test_impianto.py` mette il suo
    `FintoMT5` in `sys.modules` prima di importare `core.broker`, quindi da
    dentro `broker` il modulo finto e' indistinguibile da quello vero senza
    ricorrere a trucchi fragili. Lo dichiara chi lo sostituisce, dove lo
    sostituisce: e' una riga sola e si legge accanto al doppione.

    Vale solo dentro una prova. Fuori, `in_prova()` e' falsa e gli ordini
    partono comunque -- questa variabile non puo' aprire nulla in produzione.
    """
    return bool(os.environ.get(VARIABILE_BROKER_FINTO))
