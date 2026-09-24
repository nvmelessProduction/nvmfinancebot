"""L'Esecutore: porta sul conto demo le decisioni del Capo, con la puntata del Rischio.

Ogni operazione e' fatta di due meta': una esce al primo target, l'altra al
secondo, e quando la prima incassa lo stop della seconda va a pareggio. E'
la stessa regola delle prove sullo storico (`nvm/prova/campo.py`). Lo stop e
i target stanno sul broker: se il bot si spegne, le posizioni restano
protette.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti.rischio import USCITE, crescita, esiti, kelly
from nvm.vivo import messaggi
from nvm.vivo.giro import Decisione
from nvm.vivo.terminale import Conto, Terminale

# Il numero che MT5 attacca alle posizioni del bot, per riconoscerle.
MAGIC = 24092026


@dataclass
class Viva:
    """Un'operazione aperta sul conto."""

    chiave: str
    strumento: str
    verso: str
    quando: int
    ingresso: float
    stop: float
    tp1: float
    tp2: float
    uscita: str
    tickets: list[int]
    volume: float
    rischio: float
    valuta: str
    pareggio_fatto: bool = False
    incassato: float = 0.0
    chiusi: list[int] = field(default_factory=list)

    @property
    def short(self) -> bool:
        return self.verso == Verso.SHORT.value


@dataclass
class Fatto:
    """Cosa e' successo, da scrivere sul canale operativo (o sull'equipe se `equipe`)."""

    testo: str
    equipe: bool = False


def _giu(x: float, passo: float) -> float:
    return round(math.floor(x / passo + 1e-9) * passo, 8)


class Esecutore:
    def __init__(self, terminale: Terminale, parte: float = 1.0):
        self.t = terminale
        # Quanta parte del Kelly usa il Rischio: la impara, sullo storico e dal vivo.
        self.parte = parte

    def apri(self, d: Decisione, conto: Conto) -> tuple[Optional[Viva], Fatto]:
        k, op, verso = d.r.strumento, d.op, d.r.verso
        if not conto.demo:
            return None, Fatto(messaggi.allarme(f"il conto {conto.login} non è un demo: non apro {k}."))
        if not conto.trading_permesso:
            return None, Fatto(messaggi.allarme(
                "MT5 non permette al bot di operare: accendi il pulsante \"Algo Trading\" in alto nel terminale."))
        bid, ask = self.t.prezzo(k)
        prezzo = bid if verso is Verso.SHORT else ask
        segno = -1 if verso is Verso.SHORT else 1
        if segno * (prezzo - op.stop) <= 0:
            return None, Fatto(messaggi.saltata(d, "il prezzo è già oltre lo stop"), equipe=True)
        if segno * (op.tp1 - prezzo) <= 0:
            return None, Fatto(messaggi.saltata(d, "il prezzo è già oltre il primo target"), equipe=True)
        distanza = abs(prezzo - op.stop)
        minima = self.t.distanza_minima(k)
        if distanza <= minima or abs(op.tp1 - prezzo) <= minima:
            return None, Fatto(messaggi.saltata(d, "stop o target troppo vicini: il broker non li accetta"), equipe=True)

        # Il Rischio: la puntata di Kelly con le stime del Capo, al prezzo vero.
        rr1, rr2 = abs(op.tp1 - prezzo) / distanza, abs(op.tp2 - prezzo) / distanza
        costi = d.r.costo_erre
        per_lotto = self.t.perdita_per_lotto(k, verso, prezzo, op.stop)
        minimo, passo, massimo = self.t.lotti(k)
        pieno = kelly(esiti(d.p1, d.q, rr1, rr2, costi))
        f = pieno * self.parte
        volume = min(_giu(conto.saldo * f / per_lotto, passo), massimo)
        if volume >= 2 * minimo:
            meta = _giu(volume / 2, passo)
            parti = [(meta, op.tp1), (meta, op.tp2)]
            uscita = USCITE[0]
        else:
            # Una posizione sola: l'uscita che fa crescere di piu' il conto.
            v = max(volume, minimo)
            quota = v * per_lotto / conto.saldo
            scelte = [(crescita(esiti(d.p1, d.q, rr1, rr2, costi, u), quota), u) for u in USCITE[1:]]
            migliore, uscita = max(scelte)
            if migliore <= 0:
                return None, Fatto(messaggi.saltata(
                    d, f"anche il lotto minimo ({minimo:g}) rischierebbe {v * per_lotto:.2f} {conto.valuta}: "
                       "con queste stime il conto crescerebbe meno che non entrando"), equipe=True)
            parti = [(v, op.tp1 if uscita == USCITE[1] else op.tp2)]
        commento = f"nvm {k} {d.r.alto_tf.value}{d.r.basso_tf.value} {d.r.colpo}"
        tickets, prezzi, messi = [], [], 0.0
        for v, target in parti:
            e = self.t.apri(k, verso, v, op.stop, target, MAGIC, commento)
            if not e.ok:
                if not tickets:
                    return None, Fatto(messaggi.allarme(f"{k}: {e.messaggio}"))
                uscita = USCITE[1]  # la seconda meta' non e' partita: resta la prima, al primo target
                break
            tickets.append(e.ticket)
            prezzi.append(e.prezzo)
            messi += e.volume
        ingresso = sum(prezzi) / len(prezzi)
        rischio = messi * per_lotto
        viva = Viva(d.chiave, k, verso.value, d.r.quando, ingresso, op.stop, op.tp1, op.tp2, uscita,
                    tickets, messi, rischio, conto.valuta)
        testo = messaggi.apertura(d, messi, ingresso, rischio, conto.valuta, uscita != USCITE[0])
        testo += (f"\nIl Rischio: Kelly {pieno:.1%} del conto; ne uso la parte che ho imparato ({self.parte:.2f}), "
                  f"cioè {f:.2%}" + (" (sotto il lotto minimo: apro il minimo)." if volume < minimo else "."))
        return viva, Fatto(testo)

    def sorveglia(self, vive: list[Viva]) -> tuple[list[Viva], list[Fatto]]:
        """Pareggio dopo il primo target, e chiusure. Restituisce le operazioni ancora aperte."""
        aperte = self.t.aperte(MAGIC)
        restano, fatti = [], []
        for v in vive:
            for ticket in v.tickets:
                if ticket not in aperte and ticket not in v.chiusi:
                    netto, _ = self.t.chiusura(ticket)
                    v.chiusi.append(ticket)
                    v.incassato += netto
            ancora = [x for x in v.tickets if x not in v.chiusi]
            if not ancora:
                r = v.incassato / v.rischio if v.rischio else 0.0
                motivo = "stop" if r <= -0.8 else ("pareggio" if abs(r) < 0.1 else "target")
                if v.pareggio_fatto and r > 0.1:
                    motivo = "primo target e poi " + ("secondo target" if r > 0.5 * abs(v.tp1 - v.ingresso) / abs(v.ingresso - v.stop) + 0.1 else "pareggio")
                fatti.append(Fatto(messaggi.chiusa(v.strumento, Verso(v.verso), v.incassato, r, v.valuta, motivo)))
                continue
            if not v.pareggio_fatto:
                primo_preso = False
                if v.uscita == USCITE[0] and v.tickets[0] in v.chiusi and v.incassato > 0:
                    primo_preso = True
                elif v.uscita == USCITE[2]:
                    bid, ask = self.t.prezzo(v.strumento)
                    primo_preso = (ask <= v.tp1) if v.short else (bid >= v.tp1)
                if primo_preso:
                    for ticket in ancora:
                        e = self.t.sposta_stop(v.strumento, ticket, v.ingresso, v.tp2)
                        if not e.ok:
                            fatti.append(Fatto(messaggi.allarme(f"{v.strumento}: {e.messaggio}")))
                    v.pareggio_fatto = True
                    fatti.append(Fatto(messaggi.primo_target(v.strumento, Verso(v.verso), v.ingresso)))
            restano.append(v)
        return restano, fatti


def come_dati(v: Viva) -> dict:
    return asdict(v)
