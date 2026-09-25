"""Il giro di ogni ora: con le orarie chiuse fino ad adesso, cosa dice l'equipe.

E' la stessa catena delle prove sullo storico (`nvm/prova/base.opera`, con la
configurazione 1: manuale, stop all'estremo), chiamata sui soli dati gia'
chiusi. Per questo il bot dal vivo decide come avrebbe deciso sullo storico:
`tests/test_vivo.py` lo controlla ora per ora.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import CRT, caccia
from nvm.agenti.capo import Capo, riga
from nvm.agenti.conferme import SOPRA, AllaRomeo, Contesto, KeyLevel, Liquidita, Orario, tutti_i_pareri
from nvm.agenti.livelli import piano, scadenza
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import Risultato, opera
from nvm.prova.campo import Operazione
from nvm.agenti import capo as capo_mod, inventate, manopole, panorama
from nvm.agenti.conferme import Grandi
from nvm.tempo import TF

# Le coppie che si guardano con le orarie, ogni ora.
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
# La quarta coppia di Romeo si guarda con i quarti d'ora di MT5, ogni quarto d'ora.
COPPIA_VELOCE = (TF.H4, TF.M15)


@dataclass
class Decisione:
    r: Risultato
    op: Operazione
    scadenza: int
    key_level: Optional[KeyLevel]
    orario: Orario
    contesto: Optional[Contesto]
    p1: float
    q: float
    atteso: float
    # Le colonne del Capo per questa decisione: servono al riaddestramento.
    x: np.ndarray
    # Le risposte alla Romeo, e quanto il Capo pensa che somigli a una sua
    # entrata: un parere per l'equipe, non un obbligo.
    alla_romeo: Optional[AllaRomeo] = None
    romeo: Optional[float] = None
    # La somiglianza di un candidato medio, per dire se questa e' sopra o sotto.
    romeo_medio: Optional[float] = None
    # La risposta del Grilletto sulla liquidita' presa dalla manipolazione.
    liquidita: Optional[Liquidita] = None
    # Cosa vedono Allineamento e Gap dai timeframe grandi.
    sguardo: Optional[panorama.Sguardo] = None

    @property
    def entra(self) -> bool:
        return self.atteso > 0

    @property
    def chiave(self) -> str:
        # Due CRT uno dentro l'altro possono scattare sullo stesso turtle soup: sono due decisioni,
        # e le distingue l'inizio del range.
        r = self.r
        crt = f" crt {r.scatto.crt.range_inizio}" if r.scatto is not None else ""
        return f"{r.strumento} {r.alto_tf.value}-{r.basso_tf.value} {r.verso.value} {r.quando} colpo {r.colpo}{crt}"


# Le candele e i CRT gia' costruiti: il bot li rifarebbe uguali a ogni giro e a
# ogni quarto d'ora. Si riusano finche' le candele di base sono le stesse.
_MEMORIA: dict = {}
_MEMORIA_MASSIMA = 256


def _ricorda(chiave, fai):
    if chiave not in _MEMORIA:
        if len(_MEMORIA) >= _MEMORIA_MASSIMA:
            _MEMORIA.pop(next(iter(_MEMORIA)))
        _MEMORIA[chiave] = fai()
    return _MEMORIA[chiave]


def _impronta(base: Minuti) -> tuple:
    """Le candele di base sono le stesse se hanno lo stesso strumento, passo, numero, inizio, fine e ultima chiusura."""
    return (base.strumento, base.passo, len(base), int(base.t[0]), int(base.t[-1]), int(base.bid[-1, 3]))


def _candele(base: Minuti, tf: TF, adesso: int):
    return _ricorda(("candele", _impronta(base), tf, adesso), lambda: costruisci(base, tf).chiuse_entro(adesso))


def _crt(base: Minuti, alto: TF, basso: TF, adesso: int):
    return _ricorda(("crt", _impronta(base), alto, basso, adesso, manopole.impronta()),
                    lambda: caccia(_candele(base, alto, adesso), _candele(base, basso, adesso)))


def _grandi(ore: Minuti, adesso: int):
    """I CRT delle coppie sulle ore, per "dentro un CRT piu' grande?": gli stessi del giro orario."""
    return _ricorda(("grandi", _impronta(ore), adesso, manopole.impronta()),
                    lambda: Grandi.da([c for alto, basso in COPPIE for c in _crt(ore, alto, basso, adesso)]))


def giro(basi: dict[str, Minuti], dal: int, adesso: int, capo: Capo, coppie=COPPIE,
         orarie: Optional[dict[str, Minuti]] = None) -> list[Decisione]:
    """Le decisioni con lo scatto in [dal, adesso], su candele chiuse entro `adesso`.

    `orarie` sono le ore di ogni strumento, se `basi` sono i quarti d'ora: da
    li' vengono il timeframe sopra, la settimana e i CRT piu' grandi.
    """
    orarie = basi if orarie is None else orarie
    decisioni = []
    for strumento, base in basi.items():
        ore = orarie.get(strumento, base)
        if not len(base) or not len(ore):
            continue
        # Le ore cambiano una volta l'ora: fino ad allora i CRT grandi e la settimana sono gli stessi.
        fine_ore = min(adesso, int(ore.t[-1]) + ore.passo)
        g = _grandi(ore, fine_ore)
        settimane = _candele(ore, TF.W1, fine_ore)
        idee = capo_mod.INVENTATE
        # Le candele grandi: per Allineamento e Gap, e per le domande inventate.
        ctx_idee = _ricorda(("idee", _impronta(ore), fine_ore, manopole.impronta()),
                            lambda: inventate.Contesto.da(ore, fine_ore, g))
        for alto, basso in coppie:
            alte = _candele(base, alto, adesso)
            basse = _candele(base, basso, adesso)
            sopra = _candele(ore, SOPRA[alto], fine_ore)
            for r in opera(alte, basse, dal, adesso + 1, trovati=_crt(base, alto, basso, adesso)):
                op = piano(r.scatto, basse)
                kl, ora, ctx, ar, liq = tutti_i_pareri(r.scatto, alte, basse, sopra, settimane, g)
                x = riga(r, kl, ora, ctx, ar, liq, inventate.rispondi_tutte(idee, r, ctx_idee))[None]
                p1, q = capo.probabilita(x)
                atteso = capo.valore_atteso(x, np.array([r.rr1]), np.array([r.rr2]), np.array([r.costo_erre]))
                decisioni.append(Decisione(
                    r, op, scadenza(r.scatto), kl, ora, ctx, float(p1[0]), float(q[0]), float(atteso[0]), x[0],
                    ar, float(capo.somiglianza(x)[0]) if capo.romeo is not None else None,
                    float(1 / (1 + np.exp(-capo.romeo_logit_media))) if capo.romeo is not None else None, liq,
                    panorama.sguardo(r, ctx_idee)))
    decisioni.sort(key=lambda d: (d.r.quando, d.r.strumento))
    return decisioni


def armati(basi: dict[str, Minuti], dal: int, adesso: int, coppie=COPPIE) -> list[CRT]:
    """I CRT che il Cacciatore ha visto armarsi in [dal, adesso]."""
    trovati = []
    for base in basi.values():
        if not len(base):
            continue
        for alto, basso in coppie:
            trovati += [c for c in _crt(base, alto, basso, adesso) if dal <= c.armato_quando <= adesso]
    trovati.sort(key=lambda c: (c.armato_quando, c.strumento))
    return trovati
