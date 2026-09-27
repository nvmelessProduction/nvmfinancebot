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
from nvm.agenti import portafoglio
from nvm.agenti.rischio import USCITE, crescita_creduta, esiti, kelly
from nvm.dati.minuti import CHIUSURA
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
    # Dove lo stop va a pareggio, in frazione del cammino fra ingresso e primo
    # target, com'era la manopola dei Livelli all'apertura (1 = al primo target).
    pareggio_a: float = 1.0
    primo_detto: bool = False
    # Per le uscite prima dello stop: il timeframe delle candele basse, il livello
    # del Model#1, e le manopole all'apertura (0 = spente).
    basso: str = ""
    livello: float = 0.0
    invalida_candele: int = 0
    tempo_candele: int = 0
    uscita_anticipata: str = ""
    # Il Rischio sul conto intero: quanto avrebbe rischiato da sola (in frazione del conto) e gli
    # strumenti aperti che vanno insieme a lei, per cui ha rischiato meno.
    da_sola: float = 0.0
    legate: list[str] = field(default_factory=list)

    @property
    def gambe(self) -> dict[str, float]:
        return portafoglio.gambe(self.strumento, -1 if self.short else 1)

    @property
    def short(self) -> bool:
        return self.verso == Verso.SHORT.value


@dataclass
class Fatto:
    """Cosa e' successo, da scrivere sul canale operativo (o sull'equipe se `equipe`)."""

    testo: str
    equipe: bool = False
    # Il Capo voleva entrare ma non si e' aperto: il perche' in breve. Non fa messaggi, si conta la sera.
    saltata: str = ""
    # Un'operazione chiusa sul conto: il risultato vero, in R (per il riepilogo della sera).
    erre: Optional[float] = None


def _giu(x: float, passo: float) -> float:
    return round(math.floor(x / passo + 1e-9) * passo, 8)


class Esecutore:
    def __init__(self, terminale: Terminale, parte: float = 1.0, correlazioni: Optional[dict] = None,
                 minimo: float = 0.0):
        self.t = terminale
        # Il Kelly pieno sotto cui un'operazione non prende soldi: il Rischio l'ha imparato sul conto
        # intero (le operazioni di poca fiducia, nei vent'anni, hanno perso).
        self.minimo = minimo
        # Quanta parte del Kelly usa il Rischio: la impara, sullo storico e dal vivo.
        self.parte = parte
        # Quanto vanno insieme le operazioni aperte nello stesso momento, per quello che hanno in
        # comune (`nvm/agenti/portafoglio.py`): senza, ogni operazione si punta come se fosse sola.
        self.correlazioni = {float(c): float(r) for c, r in correlazioni.items()} if correlazioni else None

    def apri(self, d: Decisione, conto: Conto, aperte: list = (), pieno: Optional[float] = None,
             parte: Optional[float] = None, fiducia_minima: Optional[float] = None) -> tuple[Optional[Viva], Fatto]:
        """Apre la decisione sul conto. `aperte`: le operazioni gia' aperte (`Viva`), perche' il
        Rischio punti sul conto intero e non su un'operazione alla volta."""
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
            return None, Fatto(messaggi.saltata(d, "il prezzo è già oltre lo stop"), equipe=True, saltata="il prezzo era già oltre lo stop")
        if segno * (op.tp1 - prezzo) <= 0:
            return None, Fatto(messaggi.saltata(d, "il prezzo è già oltre il primo target"), equipe=True, saltata="il prezzo era già oltre il primo obiettivo")
        distanza = abs(prezzo - op.stop)
        minima = self.t.distanza_minima(k)
        if distanza <= minima or abs(op.tp1 - prezzo) <= minima:
            return None, Fatto(messaggi.saltata(d, "stop o target troppo vicini: il broker non li accetta"), equipe=True, saltata="stop troppo vicino per il broker")

        # Il Rischio: la puntata di Kelly con le stime del Capo, al prezzo vero.
        rr1, rr2 = abs(op.tp1 - prezzo) / distanza, abs(op.tp2 - prezzo) / distanza
        costi = d.r.costo_erre
        per_lotto = self.t.perdita_per_lotto(k, verso, prezzo, op.stop)
        minimo, passo, massimo = self.t.lotti(k)
        # Il Kelly pieno del Capo; se decidono i cervelli, la loro fiducia (con parte e minimo loro).
        dei_cervelli = pieno is not None
        pieno = kelly(esiti(d.p1, d.q, rr1, rr2, costi)) if pieno is None else pieno
        parte = self.parte if parte is None else parte
        fiducia_minima = self.minimo if fiducia_minima is None else fiducia_minima
        gamba = portafoglio.gambe(k, segno)
        # Quelle a pareggio non rischiano piu' niente.
        in_corso = [(v.gambe, v.rischio / conto.saldo) for v in aperte if not v.pareggio_fatto and conto.saldo > 0]
        togli = portafoglio.riduzione(gamba, in_corso, self.correlazioni)
        da_sola = pieno * parte
        f = max(da_sola - togli, 0.0)
        legate = portafoglio.legate(gamba, [(v.strumento, v.gambe) for v in aperte if not v.pareggio_fatto],
                                    self.correlazioni)
        if pieno < fiducia_minima:
            return None, Fatto(messaggi.saltata(d, "le stime sono troppo deboli per metterci soldi"), equipe=True,
                               saltata="fiducia troppo bassa per metterci soldi")
        if pieno > 0 and f <= 0:
            return None, Fatto(messaggi.saltata(d, "siamo già troppo esposti con " + ", ".join(legate or ["le altre aperte"])),
                               equipe=True, saltata="già troppo esposti su operazioni legate")
        volume = min(_giu(conto.saldo * f / per_lotto, passo), massimo)
        if op.parziale in (0.0, 1.0) and volume >= minimo:
            # Il piano scelto dai cervelli: tutto al primo obiettivo, o tutto al secondo col pareggio.
            uscita = USCITE[1] if op.parziale == 1.0 else USCITE[2]
            parti = [(volume, op.tp1 if op.parziale == 1.0 else op.tp2)]
        elif volume >= 2 * minimo:
            meta = _giu(volume / 2, passo)
            parti = [(meta, op.tp1), (meta, op.tp2)]
            uscita = USCITE[0]
        else:
            # Una posizione sola: l'uscita che fa crescere di piu' il conto, con la fiducia nelle stime
            # che il Rischio ha imparato (non con le stime prese per buone: il lotto minimo puo' essere
            # molte volte la puntata giusta, e un conto piccolo si brucerebbe).
            v = max(volume, minimo)
            quota = v * per_lotto / conto.saldo
            if dei_cervelli:
                # La crescita torna a zero al doppio della puntata giusta (`crescita_creduta`).
                migliore = 1.0 if quota < 2 * (da_sola - togli) else -1.0
                uscita = USCITE[2] if op.parziale == 0.0 else USCITE[1]
            else:
                scelte = [(crescita_creduta(esiti(d.p1, d.q, rr1, rr2, costi, u), quota, parte, togli), u)
                          for u in USCITE[1:]]
                migliore, uscita = max(scelte)
            if migliore <= 0:
                return None, Fatto(messaggi.saltata(
                    d, f"anche il lotto minimo ({minimo:g}) rischierebbe {v * per_lotto:.2f} {conto.valuta} "
                       f"({quota:.1%} del conto): troppo per quanto valgono le stime"), equipe=True,
                    saltata="conto troppo piccolo per il lotto minimo")
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
                    tickets, messi, rischio, conto.valuta, pareggio_a=op.pareggio_a, basso=d.r.basso_tf.value,
                    livello=float(op.livello_model1 or 0.0), invalida_candele=op.invalida_candele,
                    tempo_candele=op.tempo_candele, da_sola=da_sola, legate=legate if togli > 0 else [])
        testo = messaggi.apertura(d, messi, ingresso, rischio, conto.valuta, uscita != USCITE[0],
                                  rischio / conto.saldo if conto.saldo else None)
        if volume < minimo:
            testo += f"\nLa dimensione giusta era sotto il lotto minimo: apro il minimo ({minimo:g})."
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
                if v.uscita_anticipata:
                    motivo = v.uscita_anticipata
                elif v.pareggio_fatto and r > 0.1:
                    motivo = "primo target e poi " + ("secondo target" if r > 0.5 * abs(v.tp1 - v.ingresso) / abs(v.ingresso - v.stop) + 0.1 else "pareggio")
                fatti.append(Fatto(messaggi.chiusa(v.strumento, Verso(v.verso), v.incassato, r, v.valuta, motivo), erre=r))
                continue
            bid, ask = self.t.prezzo(v.strumento)
            # Il primo target: la meta' al primo target e' stata incassata, o il prezzo ci e' arrivato.
            primo_preso = (v.uscita == USCITE[0] and v.tickets[0] in v.chiusi and v.incassato > 0) or (
                (ask <= v.tp1) if v.short else (bid >= v.tp1))
            # Il pareggio: al livello che i Livelli avevano scelto all'apertura.
            livello = v.ingresso + v.pareggio_a * (v.tp1 - v.ingresso)
            oltre = (ask <= livello) if v.short else (bid >= livello)
            sposta = not v.pareggio_fatto and (oltre or (primo_preso and v.pareggio_a <= 1))
            if sposta:
                for ticket in ancora:
                    # Ogni posizione tiene il suo target: la prima meta' il primo, la seconda il secondo.
                    primo = v.uscita == USCITE[1] or (v.uscita == USCITE[0] and ticket == v.tickets[0])
                    e = self.t.sposta_stop(v.strumento, ticket, v.ingresso, v.tp1 if primo else v.tp2)
                    if not e.ok:
                        fatti.append(Fatto(messaggi.allarme(f"{v.strumento}: {e.messaggio}")))
                v.pareggio_fatto = True
            if primo_preso and not v.primo_detto and v.uscita != USCITE[1]:
                v.primo_detto = True
                fatti.append(Fatto(messaggi.primo_target(v.strumento, Verso(v.verso), v.ingresso, v.pareggio_fatto,
                                                         None if v.pareggio_fatto else livello)))
            elif sposta:
                fatti.append(Fatto(messaggi.pareggio(v.strumento, Verso(v.verso), v.ingresso)))
            restano.append(v)
        return restano, fatti


    def uscita_anticipata(self, v: Viva, basse) -> Optional[Fatto]:
        """Chiude prima dello stop se l'idea non vale piu' o e' troppo lenta, come nelle prove
        (`nvm/prova/campo.simula`): solo prima del primo target e del pareggio."""
        if v.pareggio_fatto or v.primo_detto or v.uscita_anticipata:
            return None
        dopo = basse.inizio >= v.quando
        chiusure = basse.bid[dopo, CHIUSURA] if not v.short else basse.ask[dopo, CHIUSURA]
        motivo = ""
        if v.invalida_candele and len(chiusure) >= v.invalida_candele:
            segno = -1 if v.short else 1
            ultime = chiusure[-v.invalida_candele:]
            if all(segno * (c - v.livello) < 0 for c in ultime):
                motivo = f"l'idea non vale più: {v.invalida_candele} candele chiuse oltre il livello del Model#1"
        if not motivo and v.tempo_candele and len(chiusure) >= v.tempo_candele:
            motivo = f"troppo lenta: il primo obiettivo non è arrivato in {v.tempo_candele} candele"
        if not motivo:
            return None
        for ticket in v.tickets:
            if ticket not in v.chiusi:
                e = self.t.chiudi_posizione(v.strumento, ticket)
                if not e.ok:
                    return Fatto(messaggi.allarme(f"{v.strumento}: non riesco a chiudere ({e.messaggio})"))
        v.uscita_anticipata = motivo
        return Fatto(messaggi.uscita_anticipata(v.strumento, Verso(v.verso), motivo))


def come_dati(v: Viva) -> dict:
    return asdict(v)
