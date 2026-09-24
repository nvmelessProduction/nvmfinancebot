"""Le decisioni seguite sulla carta: come sarebbe finita ognuna, presa o no.

Serve all'equipe per imparare anche dalle operazioni non aperte, e al Capo
per riaddestrarsi il fine settimana. Si simula con lo stesso campo di prova
dello storico, sulle candele del broker.
"""

from __future__ import annotations

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.campo import Operazione, Uscita, simula
from nvm.tempo import TF
from nvm.vivo.stato import Seguita


def segui(seguite: list[Seguita], basi: dict[str, Minuti], adesso: int) -> list[Seguita]:
    """Aggiorna le seguite ancora aperte; restituisce quelle appena finite."""
    candele: dict[tuple[str, str], object] = {}
    finite = []
    for s in seguite:
        if s.esito is not None or s.strumento not in basi:
            continue
        chiave = (s.strumento, s.basso)
        if chiave not in candele:
            candele[chiave] = costruisci(basi[s.strumento], TF(s.basso)).chiuse_entro(adesso)
        op = Operazione(s.strumento, Verso(s.verso), s.quando, s.ingresso, s.stop, s.tp1, s.tp2)
        e = simula(op, candele[chiave], s.scadenza)
        if e.uscita is Uscita.SCADUTA and adesso < s.scadenza:
            continue
        s.esito = {
            "uscita": e.uscita.value, "erre": e.erre, "quando": e.quando,
            "tp1": bool(e.tp1_preso or e.uscita is Uscita.TARGET), "tp2": e.uscita is Uscita.TARGET,
        }
        finite.append(s)
    return finite
