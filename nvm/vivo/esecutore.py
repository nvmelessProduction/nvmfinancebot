"""L'Esecutore: porta sul conto demo le decisioni del Capo, con la puntata del Rischio.

Ogni operazione e' una posizione sola (il proprietario, 07/10/2026: *"vorrei che apri una sola operazione"*),
con lo stop e il target finale sul broker: se il bot si spegne, la posizione resta protetta. Quando il prezzo
arriva al TP1 il bot chiude meta' e mette lo stop al prezzo d'entrata; se il lotto non si puo' dividere, sposta
solo lo stop e tiene tutto fino al target finale. E' la stessa regola delle prove sullo storico
(`nvm/prova/campo.py`).
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti import portafoglio
from nvm.agenti.rischio import USCITE, crescita_creduta, esiti, kelly
from nvm.dati.minuti import CHIUSURA
from nvm.prova.campo import COMMISSIONE
from nvm.vivo import messaggi
from nvm.vivo.giro import Decisione
from nvm.vivo.terminale import Conto, ErroreMT5, Terminale

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
    # Le chiusure che MT5 non ha ancora dato: ticket -> minuti di attesa.
    attese_chiusura: dict = field(default_factory=dict)
    # Il Rischio sul conto intero: quanto avrebbe rischiato da sola (in frazione del conto) e gli
    # strumenti aperti che vanno insieme a lei, per cui ha rischiato meno.
    da_sola: float = 0.0
    legate: list[str] = field(default_factory=list)
    # Quando il prezzo ha toccato il primo obiettivo (per il kiss of death che non va superato).
    primo_quando: int = 0
    # La posizione sola: quanti lotti chiude il bot al TP1 (0 = nessun parziale: il lotto non si divide, o le
    # operazioni di prima con due posizioni) e se l'ha gia' fatto.
    meta: float = 0.0
    meta_fatta: bool = False
    # Non si usa piu': era la chiusura della candela d'ingresso, quando il pareggio scattava li' (dal 16 al
    # 20/10/2026). Resta perche' lo stato salvato sulla VPS lo contiene.
    tp1_entro: int = 0
    # MT5 ha rifiutato lo stop a pareggio: si riprova ogni minuto senza ripetere l'allarme.
    pareggio_rifiutato: bool = False
    # Chiusa da una persona (dal terminale o dal telefono): il risultato non insegna niente alla squadra.
    a_mano: bool = False

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
    # Per il libro delle operazioni vere (`libro.py`): i dati dell'evento.
    libro: Optional[dict] = None


# Quanti minuti si aspetta lo storico di una chiusura prima di darla per chiusa senza risultato.
ATTESA_CHIUSURA = 60


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
             parte: Optional[float] = None, fiducia_minima: Optional[float] = None,
             riduci: bool = True) -> tuple[Optional[Viva], Fatto]:
        """Apre la decisione sul conto. `aperte`: le operazioni gia' aperte (`Viva`), perche' il
        Rischio punti sul conto intero e non su un'operazione alla volta. `riduci=False`: la puntata
        l'ha gia' decisa il Rischio della squadra, tenendo conto delle aperte; nessuno la riduce."""
        k, op, verso = d.r.strumento, d.op, d.r.verso
        if not conto.demo:
            return None, Fatto(messaggi.allarme(f"il conto {conto.login} non è un demo: non apro {k}."))
        if not conto.trading_permesso:
            return None, Fatto(messaggi.allarme(
                "MT5 non permette al bot di operare: accendi il pulsante \"Algo Trading\" in alto nel terminale."))
        # L'unica regola che vale per tutti: senza stop non si apre, mai.
        if op.stop is None or not math.isfinite(float(op.stop)):
            return None, Fatto(messaggi.allarme(f"{k}: un'operazione senza stop non la apro, mai."))
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
        togli = portafoglio.riduzione(gamba, in_corso, self.correlazioni) if riduci else 0.0
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
        meta = 0.0
        if op.parziale in (0.0, 1.0) and volume >= minimo:
            # Il piano scelto: tutto al primo obiettivo, o tutto al secondo col pareggio.
            uscita = USCITE[1] if op.parziale == 1.0 else USCITE[2]
            parti = [(volume, op.tp1 if op.parziale == 1.0 else op.tp2)]
        elif volume >= minimo:
            # Una posizione sola fino al target finale; al TP1 il bot ne chiude meta', se il lotto si divide
            # (*"Se si può parzializzare, altrimenti no. E continua fino al TP"*).
            meta = _giu(volume * op.parziale, passo)
            if meta < minimo or volume - meta < minimo - 1e-9:
                meta = 0.0
            uscita = USCITE[0] if meta > 0 else USCITE[2]
            parti = [(volume, op.tp2)]
        else:
            # Una posizione sola: l'uscita che fa crescere di piu' il conto, con la fiducia nelle stime
            # che il Rischio ha imparato (non con le stime prese per buone: il lotto minimo puo' essere
            # molte volte la puntata giusta, e un conto piccolo si brucerebbe).
            v = max(volume, minimo)
            quota = v * per_lotto / conto.saldo
            if dei_cervelli:
                # La crescita torna a zero al doppio della puntata giusta (`crescita_creduta`).
                migliore = 1.0 if quota < 2 * (da_sola - togli) else -1.0
                # Col lotto minimo non si divide: tutto al target del piano (col pareggio al TP1).
                uscita = USCITE[1] if op.parziale == 1.0 else USCITE[2]
            elif getattr(d, "foto", None):
                # Senza lotto divisibile si tiene tutto fino al target finale, col pareggio al TP1.
                uscita = USCITE[2]
                migliore = crescita_creduta(esiti(d.p1, d.q, rr1, rr2, costi, uscita), quota, parte, togli)
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
        # Il commento dice di quale CRT e' la posizione: lo stesso CRT non si apre due volte, neanche se il bot
        # riparte senza ricordarselo.
        commento = commento_crt(d)
        try:
            gia = commento in self.t.commenti(MAGIC)
        except (ErroreMT5, AttributeError):
            gia = False
        if gia:
            return None, Fatto(messaggi.saltata(d, "questo CRT ha già la sua operazione aperta"), equipe=True,
                               saltata="CRT già aperto")
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
                    tempo_candele=op.tempo_candele, da_sola=da_sola, legate=legate if togli > 0 else [],
                    meta=meta if len(tickets) == 1 else 0.0)
        try:
            testo = messaggi.apertura(d, messi, ingresso, rischio, conto.valuta, uscita,
                                      rischio / conto.saldo if conto.saldo else None, meta=meta)
        except Exception:
            # L'ordine e' gia' sul conto: un messaggio sbagliato non deve farla perdere di vista al bot.
            testo = f"{'🔴 HO VENDUTO' if verso is Verso.SHORT else '🟢 HO COMPRATO'} {k}: {messi:g} lotti a {ingresso:g}"
        if volume < minimo:
            testo += f"\n(La puntata giusta era più piccola del minimo che il broker accetta: apro il minimo, {minimo:g} lotti.)"
        return viva, Fatto(testo)

    def sorveglia(self, vive: list[Viva]) -> tuple[list[Viva], list[Fatto]]:
        """Pareggio dopo il primo target, e chiusure. Restituisce le operazioni ancora aperte."""
        aperte = self.t.aperte(MAGIC)
        restano, fatti = [], []
        for v in vive:
            for ticket in v.tickets:
                if ticket not in aperte and ticket not in v.chiusi:
                    try:
                        netto, _ = self.t.chiusura(ticket)
                    except ErroreMT5:
                        # MT5 a volte non ha ancora lo storico della chiusura: si riprova al minuto dopo.
                        # Dopo un'ora si da' per chiusa senza il risultato, e lo si dice: un ticket
                        # perso non deve fermare il bot.
                        v.attese_chiusura[str(ticket)] = v.attese_chiusura.get(str(ticket), 0) + 1
                        if v.attese_chiusura[str(ticket)] < ATTESA_CHIUSURA:
                            continue
                        netto = 0.0
                        fatti.append(Fatto(messaggi.allarme(
                            f"{v.strumento}: la posizione {ticket} non è più aperta ma MT5 non ne dà il risultato. "
                            "La conto chiusa a zero: controlla nella cronologia di MT5.")))
                    v.chiusi.append(ticket)
                    v.incassato += netto
                    try:
                        if not v.uscita_anticipata and self.t.chiusa_a_mano(ticket):
                            v.a_mano = True
                    except Exception:
                        pass
            if any(x not in aperte and x not in v.chiusi for x in v.tickets):
                # Una parte e' chiusa ma MT5 non ne da' ancora il risultato: si aspetta, senza toccarla.
                restano.append(v)
                continue
            ancora = [x for x in v.tickets if x not in v.chiusi]
            if not ancora:
                r = v.incassato / v.rischio if v.rischio else 0.0
                motivo = "stop" if r <= -0.8 else ("pareggio" if abs(r) < 0.1 else "target")
                if v.a_mano:
                    motivo = "chiusa a mano"
                elif v.uscita_anticipata:
                    motivo = v.uscita_anticipata
                elif v.pareggio_fatto and r > 0.1:
                    finale = "secondo target" if r > 0.5 * abs(v.tp1 - v.ingresso) / abs(v.ingresso - v.stop) + 0.1 else "pareggio"
                    motivo = "primo target e poi " + finale
                fatti.append(Fatto(messaggi.chiusa(v.strumento, Verso(v.verso), v.incassato, r, v.valuta, motivo), erre=r,
                                   libro={"strumento": v.strumento, "verso": v.verso, "tickets": v.tickets,
                                          "volume": v.volume, "ingresso": v.ingresso, "rischio": v.rischio,
                                          "netto": v.incassato, "erre": r, "motivo": motivo, "valuta": v.valuta,
                                          "chiave": v.chiave, "a_mano": v.a_mano}))
                continue
            bid, ask = self.t.prezzo(v.strumento)
            sola = len(v.tickets) == 1
            # Il primo target: la parte al TP1 e' stata incassata, o il prezzo ci e' arrivato (anche fra un controllo
            # e l'altro: le barre da un minuto dopo l'apertura). Lo stop va a pareggio solo li', mai alla chiusura della
            # candela d'ingresso (il proprietario, 20/10/2026: *"lo deve mettere solo al tp1"*), anche sulle posizioni
            # aperte prima, quando c'era quella regola (`tp1_entro`).
            alto, basso = bid, bid
            if sola and (not v.pareggio_fatto or (v.meta > 0 and not v.meta_fatta)):
                try:
                    e = self.t.estremi(v.strumento, v.quando)
                except Exception:
                    e = None
                if e is not None:
                    alto, basso = max(bid, e[0]), min(bid, e[1])
            primo_preso = (v.uscita == USCITE[0] and not sola and v.tickets[0] in v.chiusi and v.incassato > 0) or (
                (min(ask, basso + (ask - bid)) <= v.tp1) if v.short else (alto >= v.tp1))
            if sola and v.meta > 0 and not v.meta_fatta and primo_preso:
                # Il TP1: il bot chiude la sua parte della posizione (*"Quando arriva ... parzializza"*).
                e = self.t.chiudi_posizione(v.strumento, ancora[0], v.meta)
                if e.ok:
                    v.meta_fatta = True
                else:
                    parte = 100 * v.meta / v.volume if v.volume else 25
                    fatti.append(Fatto(messaggi.allarme(f"{v.strumento}: TP1 preso ma non riesco a chiudere il "
                                                        f"{parte:.0f}% ({e.messaggio}): riprovo al minuto dopo.")))
                    primo_preso = False
            # Il pareggio: al livello che i Livelli avevano scelto all'apertura (nel metodo delle foto, il TP1). Se MT5
            # lo rifiuta (mercato chiuso) si riprova ogni minuto, ma l'allarme arriva una volta sola.
            livello = v.ingresso + v.pareggio_a * (v.tp1 - v.ingresso)
            oltre = (ask <= livello) if v.short else (bid >= livello)
            sposta = not v.pareggio_fatto and (oltre or (primo_preso and v.pareggio_a <= 1))
            pari = self.pareggio(v, ancora) if sposta or (primo_preso and not v.primo_detto) else v.ingresso
            if sposta:
                tutto_spostato = True
                for ticket in ancora:
                    # Ogni posizione tiene il suo target: la prima meta' il primo, la seconda il secondo.
                    primo = v.uscita == USCITE[1] or (v.uscita == USCITE[0] and not sola and ticket == v.tickets[0])
                    e = self.t.sposta_stop(v.strumento, ticket, pari, v.tp1 if primo else v.tp2)
                    if not e.ok:
                        tutto_spostato = False
                        if not v.pareggio_rifiutato:
                            fatti.append(Fatto(messaggi.allarme(f"{v.strumento}: {e.messaggio}. Riprovo ogni minuto.")))
                v.pareggio_rifiutato = not tutto_spostato
                if tutto_spostato:
                    v.pareggio_fatto = True
            if primo_preso and not v.primo_quando:
                v.primo_quando = int(time.time())
            if primo_preso and not v.primo_detto and v.uscita != USCITE[1]:
                v.primo_detto = True
                if sola and not v.meta_fatta:
                    # Il lotto non si divideva: niente parziale, solo lo stop a pareggio.
                    fatti.append(Fatto(messaggi.pareggio(v.strumento, Verso(v.verso), pari, tp1=True,
                                                         a_pareggio=v.pareggio_fatto)))
                else:
                    fatti.append(Fatto(messaggi.primo_target(v.strumento, Verso(v.verso), pari, v.pareggio_fatto,
                                                             None if v.pareggio_fatto else livello,
                                                             parte=(v.meta / v.volume) if sola and v.meta and v.volume else None)))
            elif sposta and v.pareggio_fatto:
                fatti.append(Fatto(messaggi.pareggio(v.strumento, Verso(v.verso), pari)))
            restano.append(v)
        return restano, fatti

    def pareggio(self, v: Viva, ancora: list[int]) -> float:
        """Dove va lo stop a pareggio: un poco oltre l'ingresso, quanto copre le commissioni d'apertura e di chiusura
        (il proprietario, 20/10/2026: *"il be non va messo preciso al prezzo di entrata ... ma leggermente in guadagno
        per coprire i costi di commissione"*). La commissione e' quella vera dell'apertura su MT5 (la chiusura costa
        uguale); se MT5 non la da', quella della tabella degli strumenti."""
        segno = -1 if v.short else 1
        costo = COMMISSIONE.get(v.strumento, 0.0)
        try:
            pagata = sum(self.t.commissione_aperta(t) or 0.0 for t in v.tickets)
            distanza = abs(v.ingresso - v.stop)
            per_lotto = self.t.perdita_per_lotto(v.strumento, Verso(v.verso), v.ingresso, v.stop) / distanza
            if pagata > 0 and v.volume > 0 and per_lotto > 0:
                # Per lotto e per unita' di prezzo: apertura e chiusura.
                costo = 2 * pagata / v.volume / per_lotto
        except Exception:
            pass
        return v.ingresso + segno * costo


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
        return self.chiudi(v, motivo)

    def chiudi(self, v: Viva, motivo: str) -> Fatto:
        """Chiude a mercato quello che resta dell'operazione, per il motivo detto."""
        for ticket in v.tickets:
            if ticket not in v.chiusi:
                e = self.t.chiudi_posizione(v.strumento, ticket)
                if not e.ok:
                    return Fatto(messaggi.allarme(f"{v.strumento}: non riesco a chiudere ({e.messaggio})"))
        v.uscita_anticipata = motivo
        return Fatto(messaggi.uscita_anticipata(v.strumento, Verso(v.verso), motivo))


def commento_crt(d: Decisione) -> str:
    """Il commento della posizione sul broker (al massimo 31 caratteri): strumento, timeframe, verso e
    l'apertura della candela 3, cioe' quale CRT e'."""
    quando = int(d.r.quando)
    cifre = "0123456789abcdefghijklmnopqrstuvwxyz"
    b36 = ""
    while quando:
        quando, resto = divmod(quando, 36)
        b36 = cifre[resto] + b36
    return f"nvm {d.r.strumento} {d.r.alto_tf.value}{'S' if d.r.verso is Verso.SHORT else 'L'} {b36 or '0'}"[:31]


def come_dati(v: Viva) -> dict:
    return asdict(v)
