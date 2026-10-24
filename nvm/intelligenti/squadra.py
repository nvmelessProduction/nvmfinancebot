"""La squadra: i nostri agenti, col metodo delle foto del proprietario, che imparano dal vivo.

Il proprietario: *"come nelle foto"* (06/10/2026, `documenti/spec/metodo_foto.md`), *"bot intelligente e strategia di
Romeo"*, *"non voglio essere preso in giro"*. Nessuna AI esterna. Qui c'e' scritto esattamente cosa fa ogni
agente, e i messaggi su Telegram dicono solo questo.

1. **Le domande del metodo** (`metodo.valuta_foto`): il CRT, il key level, la direzione. Ogni agente
   risponde alla sua. Sono il metodo: **se anche una sola dice no, non si entra**, e non si disimparano.
2. **Il giudizio di ogni agente si impara.** Ognuno guarda i numeri del suo mestiere (`Metodo.numeri`:
   il Cacciatore il timeframe e gli allineati, il Gap la fase e l'RSI, il DXY il dollaro, l'Orario l'ora e
   il giorno, Livelli quanto si guadagna...)
   e ha un suo piccolo modello (regressione logistica) che stima quanto spesso un'occasione cosi' va
   bene. All'inizio non sa niente (50%, *"nessuna esperienza"*); impara da **ogni** occasione finita,
   presa o lasciata, e da quelle vere prima che da quelle sulla carta.
3. **Si confrontano davvero.** Dopo il primo giudizio c'e' un secondo giro: ogni agente sente quello
   che hanno visto i colleghi e cambia il suo giudizio con le regole di Romeo che legano i mestieri (per
   esempio il Bias sente l'SMT confermato dal Grilletto: *"SMT equals expansion"*, V11 13:01). Quanto
   pesa ogni collega lo impara dai risultati: se sentirlo non aiuta, conta sempre meno. Su Telegram si
   dice chi ha cambiato idea, da quanto a quanto, e perche'.
4. **Il Capo** mette insieme i giudizi (quanto fidarsi di ciascuno lo impara) e guarda la **memoria dei
   casi simili** gia' finiti dal vivo. Entra in ogni A+ con lo stop (il proprietario: *"Se c'e' setup bene
   altrimenti sti cavoli"*); ne lascia una solo quando i fatti dicono chiaro che occasioni cosi' perdono
   (*"lose, journal, avoid"*, V9 23:30): almeno `MINIMO_SIMILI` casi simili, in perdita con certezza.
5. **Livelli** sceglie fra tre piani (`foto.PIANI`, sempre il TP1 all'altro lato del range): parte da
   quello delle foto e cambia solo se un altro rende di piu' dal vivo.
6. **Il Rischio** parte dall'1% del conto, punta di piu' quando il Capo e' piu' convinto del solito e
   meno con altre operazioni aperte, e corregge la puntata coi risultati veri.
7. **Inventano**: un errore del Capo che si ripete sempre nello stesso verso in una situazione precisa
   diventa un'idea nuova; se poi non cambia niente, si lascia.

Tutto resta scritto in `dati/vivo/intelligenti/memoria.json`.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nvm.intelligenti.metodo import Metodo
from nvm.intelligenti.pareri import VOTANO, Parere, confronto

VERSIONE = "foto-1"
AGENTI = ("Cacciatore", "Grilletto", "Key level", "Bias", "Gap", "DXY", "Orario", "Livelli")
# Le domande obbligatorie, in parole semplici: quello che manca quando dicono no.
MANCA_IN_PAROLE = {
    "CRT": "il CRT (la candela 2 che prende un lato e rientra)",
    "candela 3": "aspettare la candela 3",
    "oltre l'apertura": "la finta oltre l'apertura della candela 3",
    "modello d'entrata": "la conferma (Model#1 con la candela spessa, o la vera rottura di struttura)",
    "key level": "un key level del grafico grande",
    "direzione": "il grafico grande dalla nostra parte",
    "ora giusta": "l'ora giusta",
    "obiettivo da prendere": "l'obiettivo ancora da prendere",
}

# Il secondo giro: le regole di Romeo che legano i mestieri. (chi ascolta, chi parla, cosa ha visto, peso
# di partenza in logit, la regola). Il peso poi lo impara: e' una colonna in piu' nel suo modello.
ASCOLTI = (
    ("Bias", "Gap", "dentro un gap a favore", 0.3,
     "dentro un gap che spinge dalla nostra parte la direzione è più forte (il CRT a supporto di gap, cartella 5)"),
    ("Bias", "DXY", "DXY a favore", 0.3, "il DXY è un grafico fondamentale: se fa il setup, le coppie col dollaro seguono"),
    ("Livelli", "Gap", "RSI", 0.3, "con la continuazione confermata dall'RSI il prezzo esce dal gap e va al target"),
    ("Livelli", "Cacciatore", "allineati", 0.2, "con più timeframe allineati il target arriva più spesso"),
    ("Key level", "Cacciatore", "inside bar", 0.2, "dopo le inside bar la finta prende più liquidità"),
)

# Come impara ogni modello.
PASSO_GIUDIZIO = 0.08
FRENO = 0.002                  # quanto i pesi tornano verso zero (verso quelli di Romeo per gli ascolti)
ESPERIENZA_MINIMA = 10         # sotto, l'agente dice che non ha ancora esperienza
# Il Capo: quanto si fida di ogni agente all'inizio (in logit), e quanto impara.
FIDUCIA_INIZIALE = 0.5
PASSO_CAPO = 0.05
# La memoria dei casi simili.
CASI_TENUTI = 4000
SIMILI = 20
MINIMO_SIMILI = 15
CERTEZZA_EVITA = 2.0
# Il Rischio nasce puntando l'1% del conto: Romeo non dice un numero, dice di non esagerare.
PUNTATA_INIZIALE = 0.01
# Il Rischio riparte da zero una volta (il proprietario, 23/10/2026: *"resetta tutto quanto ciò che riguarda il rischio e
# deve decidere lui quanto puntare"*): aveva imparato anche dalle operazioni aperte su CRT del DXY che non c'erano. Se
# un giorno serve ripartire ancora, si cambia questa data.
RIPARTENZA_RISCHIO = "2026-10-23"
PASSO_RISCHIO = 0.01
# Livelli nasce col piano delle foto (`foto.PIANI`).
PIANO_ROMEO = 1
# Il peso dei risultati veri rispetto a quelli sulla carta.
PESO_VERO, PESO_CARTA = 1.0, 0.5
# Il Capo pesa i voti di tutti (`pareri.py`): quanto si fida di ognuno, in logit per punto di voto. Parte uguale per
# tutti e lo impara dal vivo: chi ci prende pesa di piu', chi sbaglia di meno (mai sotto zero: nessuno si ascolta
# al contrario).
FIDUCIA_VOTO = 0.25
FIDUCIA_MASSIMA = 1.0
# Da dove parte la stima del Capo prima di sentire i voti: il 40% (le A+ finite dal vivo fino al 07/10/2026).
BASE_VOTI = math.log(0.4 / 0.6)
# Il Capo entra con almeno questi punti pesati a favore (un punto = un voto +1 di chi ha la fiducia di partenza).
SOGLIA_PUNTI = 3.0
# Un ascolto del secondo giro si spegne se dal vivo, dopo almeno tante volte, ha cambiato il voto nel verso giusto
# meno di questa parte delle volte (sentire quel collega non aiuta).
ASCOLTO_MINIMO = 20
ASCOLTO_UTILE = 0.45
# Le idee.
VOLTE_IDEA = 20
CERTEZZA_IDEA = 3.0
LEZIONI_TENUTE = 300
OMBRA_MASSIMA = 20000


def _stretto(x: float, basso: float, alto: float) -> float:
    return min(max(x, basso), alto)


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-_stretto(x, -30.0, 30.0)))


def _logit(p: float) -> float:
    p = _stretto(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


def _pct(x: float) -> str:
    return f"{x:.2%}".replace(".", ",")


def _p(x: float) -> str:
    return f"{x:.0%}"


def _erre(x: float) -> str:
    return f"{x:+.1f}".replace(".", ",")


def _virgola(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _cap(testo: str) -> str:
    return testo[:1].upper() + testo[1:] if testo else testo


def con_stop(op) -> bool:
    """L'unica regola fissa di sempre: un'operazione ha lo stop, dalla parte giusta."""
    try:
        stop, ingresso, tp1 = float(op.stop), float(op.ingresso), float(op.tp1)
    except (TypeError, ValueError, AttributeError):
        return False
    if not all(math.isfinite(x) for x in (stop, ingresso, tp1)):
        return False
    segno = 1 if tp1 > ingresso else -1
    return segno * (ingresso - stop) > 0


def _colonne(agente: str, m: Metodo) -> tuple[dict, dict]:
    """Le colonne del modello di un agente: i numeri del suo mestiere, e quello che sente dai colleghi."""
    proprie = dict(m.numeri.get(agente, {}))
    sentite = {}
    for chi, da, cosa, _, _ in ASCOLTI:
        if chi == agente:
            sentite[f"{da}: {cosa}"] = float(m.numeri.get(da, {}).get(cosa, 0.0))
    return proprie, sentite


@dataclass
class Memoria:
    """Tutto quello che la squadra ha imparato dal vivo."""

    cartella: Path
    versione: str = VERSIONE
    # Il modello di ogni agente: {"base": b, "pesi": {colonna: w}, "n": casi visti, "giuste": quante}.
    agenti: dict = field(default_factory=dict)
    capo: dict = field(default_factory=dict)
    rischio: dict = field(default_factory=dict)
    piani: dict = field(default_factory=dict)
    idee: dict = field(default_factory=dict)
    pesi_idee: dict = field(default_factory=dict)
    ombra: dict = field(default_factory=dict)
    lezioni: dict = field(default_factory=dict)
    discusse: dict = field(default_factory=dict)
    da_vedere: dict = field(default_factory=dict)
    # I casi finiti, per la memoria dei casi simili.
    casi: list = field(default_factory=list)
    # Come sarebbero andate le occasioni lasciate perche' una regola di Romeo diceva no: [volte, somma R].
    controprova: dict = field(default_factory=dict)
    # Come vanno le A+: [volte, somma R, vinte].
    a_piu: list = field(default_factory=lambda: [0, 0.0, 0])
    # I risultati veri arrivati dal broker prima che l'occasione finisse sulla carta: chiave -> R.
    veri: dict = field(default_factory=dict)
    sabato: dict = field(default_factory=dict)
    storia: list = field(default_factory=list)
    # Le previsioni del Bias, per strumento: quella del giorno (`pareri.Previsione`), tenuta fino a sera.
    previsioni: dict = field(default_factory=dict)
    # Il giorno (apertura, UTC) delle previsioni gia' dette in equipe.
    previsioni_dette: int = 0
    # Come vanno i voti di ognuno dal vivo: {"si": [volte, andate bene], "no": [volte, andate male]}.
    pagella: dict = field(default_factory=dict)
    # Il secondo giro: per ogni ascolto ("Bias sente Gap"), [volte usato, volte che ha cambiato nel verso giusto].
    ascolti: dict = field(default_factory=dict)

    CAMPI = ("versione", "agenti", "capo", "rischio", "piani", "idee", "pesi_idee", "ombra", "lezioni", "discusse",
             "da_vedere", "casi", "controprova", "a_piu", "veri", "sabato", "storia", "previsioni", "previsioni_dette",
             "pagella", "ascolti")

    def ascolti_spenti(self) -> set:
        """Gli ascolti che dal vivo non aiutano: nel secondo giro non si usano piu'."""
        return {k for k, (n, giuste) in self.ascolti.items() if n >= ASCOLTO_MINIMO and giuste / n < ASCOLTO_UTILE}

    def __post_init__(self):
        for a in AGENTI:
            g = self.agenti.setdefault(a, {})
            g.setdefault("base", 0.0)
            g.setdefault("pesi", {})
            g.setdefault("n", 0)
            g.setdefault("giuste", 0)
        self.capo.setdefault("base", 0.0)
        self.capo.setdefault("fiducia", {a: FIDUCIA_INIZIALE for a in AGENTI})
        self.capo.setdefault("errori", [0, 0.0, 0.0])
        self.capo.setdefault("voti", {})
        for a in VOTANO:
            self.capo["voti"].setdefault(a, FIDUCIA_VOTO)
        self.capo.setdefault("base_voti", BASE_VOTI)
        if self.rischio.get("ripartito") != RIPARTENZA_RISCHIO:
            self.rischio.clear()
            self.rischio["ripartito"] = RIPARTENZA_RISCHIO
        for k, v in (("base", PUNTATA_INIZIALE), ("convinzione", 0.2), ("aperte", 0.2), ("stesso", 0.2), ("media", 0.0),
                     ("scarto", 0.1), ("volte", 0)):
            self.rischio.setdefault(k, v)
        for a in VOTANO:
            self.pagella.setdefault(a, {"si": [0, 0], "no": [0, 0]})

    @classmethod
    def carica(cls, cartella: Path) -> "Memoria":
        f = cartella / "memoria.json"
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
            if d.get("versione") == VERSIONE:
                return cls(cartella, **{k: d[k] for k in cls.CAMPI if k in d})
            # La memoria di una squadra di prima: si riparte da zero.
        return cls(cartella)

    def salva(self) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        for nome, massimo in (("discusse", 4000), ("da_vedere", 4000)):
            d = getattr(self, nome)
            if len(d) > massimo:
                for k in sorted(d, key=lambda k: d[k].get("quando", 0))[:-massimo]:
                    del d[k]
        if len(self.ombra) > OMBRA_MASSIMA:
            tenute = sorted(self.ombra, key=lambda k: -self.ombra[k][0])[:OMBRA_MASSIMA * 2 // 3]
            self.ombra = {k: self.ombra[k] for k in tenute}
        self.casi = self.casi[-CASI_TENUTI:]
        self.storia = self.storia[-300:]
        if len(self.veri) > 2000:
            self.veri = dict(list(self.veri.items())[-2000:])
        f = self.cartella / "memoria.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: getattr(self, k) for k in self.CAMPI}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)

    def impara(self, agente: str, lezione: dict) -> None:
        self.lezioni.setdefault(agente, []).append(lezione)
        self.lezioni[agente] = self.lezioni[agente][-LEZIONI_TENUTE:]

    def ci_prende(self, agente: str) -> tuple[int, int]:
        g = self.agenti.get(agente, {})
        return int(g.get("giuste", 0)), int(g.get("n", 0))

    @property
    def voti(self) -> dict:
        return {a: {"n": g["n"], "giuste": g["giuste"]} for a, g in self.agenti.items()}


@dataclass
class Verdetto:
    entra: bool
    piano: int
    puntata: float
    fiducia: float
    voci: list
    pareri: dict
    lista: dict
    secondi: float
    a_piu: bool = False
    chiamate: int = 0
    # Le domande di Romeo su cui si e' deciso (per i disegni e la revisione).
    metodo: Optional[Metodo] = None
    # I pareri di tutti (`pareri.py`) e quanti punti pesati fanno per il Capo.
    pareri_squadra: list = field(default_factory=list)
    punti: float = 0.0
    # Perche' il Capo l'ha lasciata quando ha scelto le migliori del giro ("" se non l'ha lasciata per questo).
    lasciata: str = ""

    def come_dati(self) -> dict:
        return {"entra": self.entra, "piano": self.piano, "puntata": self.puntata, "fiducia": self.fiducia,
                "pareri": self.pareri, "lista": self.lista, "a_piu": self.a_piu, "secondi": round(self.secondi, 3)}


def _idea_vera(chiave: str, visti: set) -> bool:
    return all(a in visti for a in chiave.split("&"))


def nome_idea(chiave: str) -> str:
    return " e ".join(f"«{_in_parole(a)}»" for a in chiave.split("&"))


def _in_parole(atomo: str) -> str:
    chi, _, valore = atomo.partition("=")
    if chi == "strumento":
        return f"su {valore}"
    if chi == "coppia":
        return {"MN-D1": "sul mensile", "W1-H4": "sul settimanale", "D1-H1": "sul giornaliero",
                "H4-M15": "sulle 4 ore"}.get(valore, valore)
    if chi == "giorno":
        return f"di {valore}"
    if chi == "ora":
        return f"verso le {int(valore)} di New York" if valore.isdigit() else valore
    if chi == "verso":
        return "quando compriamo" if valore == "acquisto" else "quando vendiamo"
    if chi == "modello":
        return f"con l'entrata «{valore}»"
    return chi


class Squadra:
    """Si riunisce su ogni occasione della candela 3, decide, impara."""

    def __init__(self, cartella: Path):
        self.memoria = Memoria.carica(cartella)
        self.ultimo_errore = ""
        # Il riassunto dell'ultima scelta del Capo fra le occasioni del giro (`al_lavoro.scegli`).
        self.ultima_scelta = ""
        self._lucchetto = threading.RLock()

    def salva(self) -> None:
        with self._lucchetto:
            self.memoria.salva()

    # --- il giudizio di ogni agente ---

    def _logit_agente(self, agente: str, proprie: dict, sentite: dict) -> tuple[float, float]:
        """(logit col solo suo mestiere, logit dopo aver sentito i colleghi)."""
        g = self.memoria.agenti[agente]
        w = g["pesi"]
        primo = g["base"] + sum(w.get(k, 0.0) * x for k, x in proprie.items())
        secondo = primo + sum(w.get(k, self._prior(agente, k)) * x for k, x in sentite.items())
        return primo, secondo

    @staticmethod
    def _prior(agente: str, colonna: str) -> float:
        for chi, da, cosa, peso, _ in ASCOLTI:
            if chi == agente and colonna == f"{da}: {cosa}":
                return peso
        return 0.0

    def giudizi(self, m: Metodo) -> dict:
        """Il giudizio di ogni agente: probabilita' che vada bene prima e dopo il confronto, e chi ha sentito."""
        fuori = {}
        for a in AGENTI:
            proprie, sentite = _colonne(a, m)
            l1, l2 = self._logit_agente(a, proprie, sentite)
            regole = [(da, cosa, regola) for chi, da, cosa, _, regola in ASCOLTI
                      if chi == a and sentite.get(f"{da}: {cosa}", 0.0) > 0]
            fuori[a] = {"prima": _sig(l1), "dopo": _sig(l2), "logit": l2, "sentiti": regole,
                        "n": self.memoria.agenti[a]["n"]}
        return fuori

    def _capo(self, giudizi: dict) -> float:
        c = self.memoria.capo
        return _sig(c["base"] + sum(c["fiducia"].get(a, FIDUCIA_INIZIALE) * g["logit"] for a, g in giudizi.items()))

    def simili(self, m: Metodo, a_piu: Optional[bool] = None) -> tuple[int, int, float, float]:
        """I casi finiti piu' simili: quanti, quanti andati bene, R medio, e quanto e' sicuro il segno (t)."""
        atomi = set(m.atomi())
        modello = m.fatti.get("modello", "")
        coppia = m.fatti.get("coppia", "")
        a_piu = m.a_piu if a_piu is None else a_piu
        candidati = [c for c in self.memoria.casi if c.get("modello") == modello and c.get("coppia") == coppia
                     and bool(c.get("a_piu")) == a_piu]
        candidati.sort(key=lambda c: -len(atomi & set(c.get("atomi", []))) / max(len(atomi | set(c.get("atomi", []))), 1))
        scelti = candidati[:SIMILI]
        if not scelti:
            return 0, 0, 0.0, 0.0
        r = [float(c["erre"]) for c in scelti]
        n = len(r)
        media = sum(r) / n
        scarto = math.sqrt(sum((x - media) ** 2 for x in r) / max(n - 1, 1)) if n > 1 else 0.0
        t = media / (scarto / math.sqrt(n)) if scarto > 0 else 0.0
        return n, sum(1 for x in r if x > 0), media, t

    def stima(self, m: Metodo) -> float:
        """Quanto la squadra si aspetta dall'occasione, in volte il rischio: la probabilita' del Capo per
        quanto si guadagna, meno quello che si perde, piu' le idee inventate che valgono."""
        p = self._capo(self.giudizi(m))
        vinto = float(m.fatti.get("rr", 1.0))
        visti = set(m.atomi())
        idee = sum(self.memoria.pesi_idee.get(k, 0.0) for k in self.memoria.idee if _idea_vera(k, visti))
        return p * vinto - (1 - p) + idee

    # --- il Capo ascolta tutti ---

    def voti(self, pareri: list[Parere]) -> tuple[float, float]:
        """Il Capo mette insieme i voti di tutti, ognuno pesato da quanto se ne fida: (quanto spesso stima che vada
        bene, punti pesati). Un punto e' un voto +1 di chi ha la fiducia di partenza."""
        c = self.memoria.capo
        w = c["voti"]
        logit = c["base_voti"] + sum(w.get(x.agente, FIDUCIA_VOTO) * x.voto for x in pareri)
        punti = sum(w.get(x.agente, FIDUCIA_VOTO) / FIDUCIA_VOTO * x.voto for x in pareri)
        return _sig(logit), punti

    # --- la riunione ---

    def _piano(self, coppia: str, modello: str, piani: Optional[list]) -> int:
        """Livelli: il piano che dal vivo ha reso di piu' su questo grafico e con questa entrata."""
        if not piani:
            return -1
        conti = self.memoria.piani.get(f"{coppia} {modello}", {})

        def valore(j):
            n, somma = conti.get(str(j), [0, 0.0])
            prima = 0.05 if j == PIANO_ROMEO else 0.0
            return (somma + 10 * prima) / (n + 10)
        buoni = [j for j, op in enumerate(piani) if op is not None and con_stop(op)]
        return max(buoni, key=valore) if buoni else -1

    def _rischio(self, p: float, esposizione: float, stesso: float = 0.0) -> tuple[float, float]:
        """La puntata: la base, piu' quando il Capo e' piu' convinto del solito, meno con altre operazioni aperte e
        meno ancora se sono sullo stesso strumento. Quanto pesa ognuna lo impara dai risultati (il proprietario,
        07/10/2026: un'operazione alla volta per strumento? *"lo gestisce l'agente rischio. decisione sua"*)."""
        ri = self.memoria.rischio
        # Quanto e' convinto il Capo rispetto al solito. Finche' il solito non lo sa (meno di 10 occasioni prese),
        # rispetto a una su due: punta di piu' sulle occasioni migliori fin dalla prima.
        if ri.get("volte", 0) >= 10:
            z = _stretto((p - ri["media"]) / max(ri["scarto"], 1e-6), -3.0, 3.0)
        else:
            z = _stretto((p - 0.5) / 0.1, -3.0, 3.0)
        esponente = ri["convinzione"] * z - ri["aperte"] * 100 * esposizione - ri.get("stesso", 0.2) * 100 * stesso
        return ri["base"] * math.exp(_stretto(esponente, -5.0, 3.0)), z

    def ripunta(self, chiave: str, esposizione: float) -> float:
        """La puntata di un'occasione gia' discussa, rifatta con quanto e' a rischio adesso, subito prima dell'ordine:
        quando il DXY fa il CRT si aprono piu' coppie nello stesso giro, e ognuna vede quelle appena aperte (che con
        lei vanno insieme, perche' le muove lo stesso dollaro). Quanto pesano lo impara il Rischio dai risultati.
        0 se l'occasione non si conosce."""
        with self._lucchetto:
            d = self.memoria.discusse.get(chiave)
            if not d:
                return 0.0
            g = d.setdefault("pareri", {}).setdefault("Rischio", {})
            parte, z = self._rischio(float(d.get("fiducia", 0.5)), esposizione, float(g.get("stesso", 0.0)))
            g.update({"parte": round(parte, 6), "z": round(z, 4), "esposizione": round(esposizione, 6)})
            d["puntata"] = round(parte, 6)
            return parte

    def riunione(self, chiave: str, strumento: str, m: Metodo, quando: int, piani: Optional[list] = None,
                 esposizione: float = 0.0, da_seguire: Optional[dict] = None, op=None, stesso: float = 0.0,
                 pareri: Optional[list] = None) -> Verdetto:
        """La riunione su un'occasione: le domande di Romeo gia' risposte (`metodo.valuta`).

        Con i `pareri` di tutti (`pareri.py`, il metodo delle foto) decide il Capo: le regole del metodo devono esserci
        tutte, poi pesa i voti di ognuno (quanto si fida di chi lo impara dal vivo) ed entra solo con abbastanza punti a
        favore. Il Rischio decide quanto, come sempre."""
        t0 = time.time()
        with self._lucchetto:
            mem = self.memoria
            coppia = m.fatti.get("coppia", "")
            modello = m.fatti.get("modello", "")
            piano = self._piano(coppia, modello, piani)
            scelta = piani[piano] if piano >= 0 else op
            stop_ok = scelta is not None and con_stop(scelta)
            if scelta is not None and stop_ok:
                rischio = abs(float(scelta.ingresso) - float(scelta.stop))
                parz = float(getattr(scelta, "parziale", 0.5))
                rr1 = abs(float(scelta.tp1) - float(scelta.ingresso)) / rischio
                rr2 = abs(float(getattr(scelta, "tp2", scelta.tp1)) - float(scelta.ingresso)) / rischio
                m.fatti["rr"] = round(parz * rr1 + (1 - parz) * rr2, 4)
            giudizi = self.giudizi(m)
            n_s, vinte_s, media_s, t_s = self.simili(m)
            punti = 0.0
            usati = []
            if pareri is not None:
                # Il secondo giro: si sentono fra colleghi e chi ha un motivo cambia idea, dicendolo.
                usati = confronto(pareri, self.memoria.ascolti_spenti())
                # Decide il Capo, dopo aver sentito tutti.
                p, punti = self.voti(pareri)
                visti = set(m.atomi())
                idee = sum(self.memoria.pesi_idee.get(k, 0.0) for k in self.memoria.idee if _idea_vera(k, visti))
                stima = p * float(m.fatti.get("rr", 1.0)) - (1 - p) + idee
                evita = False
                # Con tutte le regole del metodo si entra: la squadra da' il suo parere ma non blocca piu' (il
                # proprietario, 12/10/2026, dopo un AUDUSD perfetto lasciato per un voto contro: *"tu devi seguire
                # quello che c'è scritto nelle foto e tutte le varie cose che io ti ho detto"*). Restano i no
                # delle regole e il Rischio decide quanto. Dal 22/10/2026 non c'e' piu' un veto: la previsione della
                # domenica e' solo un parere (*"Leva il veto ovunque"*).
                capo_entra = m.a_piu and stop_ok
                parte, z = self._rischio(p, esposizione, stesso)
            else:
                p = self._capo(giudizi)
                stima = self.stima(m)
                evita = m.a_piu and n_s >= MINIMO_SIMILI and media_s < 0 and t_s <= -CERTEZZA_EVITA
                capo_entra = m.a_piu and stop_ok and not evita
                parte, z = self._rischio(p, esposizione, stesso)
            puntata = max(parte, 0.0) if capo_entra else 0.0
            entra = capo_entra and puntata > 0
            if entra:
                ri = mem.rischio
                ri["volte"] = ri.get("volte", 0) + 1
                ri["media"] = round(p if ri["volte"] == 1 else 0.95 * ri["media"] + 0.05 * p, 6)
                ri["scarto"] = round(max(math.sqrt(0.95 * ri["scarto"] ** 2 + 0.05 * (p - ri["media"]) ** 2), 0.02), 6)
            if pareri is not None:
                voci = self._voci_della_squadra(m, pareri, entra, stop_ok, p, punti, puntata, z, esposizione, stesso)
            else:
                voci = self._voci(m, giudizi, entra, stop_ok, evita, p, puntata, z, esposizione, piano,
                                  (n_s, vinte_s, media_s), stesso)
            lista = {d.nome: bool(d.si) for d in m.obbligatorie}
            dati = {"Capo": {"entra": capo_entra, "p": round(p, 4), "stima": round(stima, 4), "a_piu": m.a_piu,
                             "evita": evita, "mancano": [d.nome for d in m.mancano],
                             "simili": [n_s, vinte_s, round(media_s, 4)], "punti": round(punti, 3)},
                    "Rischio": {"parte": round(parte, 6), "z": round(z, 4), "esposizione": round(esposizione, 6),
                                "stesso": round(stesso, 6)},
                    "agenti": {a: {"prima": round(g["prima"], 4), "dopo": round(g["dopo"], 4)}
                               for a, g in giudizi.items()}}
            if pareri is not None:
                dati["voti"] = {x.agente: x.voto for x in pareri}
                dati["ragioni"] = {x.agente: x.ragioni[:1] for x in pareri}
                dati["ascolti"] = [[k, q] for k, q in usati]
            v = Verdetto(entra, piano, round(puntata, 6), round(p, 3), voci, dati, lista, time.time() - t0,
                         a_piu=m.a_piu, pareri_squadra=list(pareri or []), punti=round(punti, 3))
            colonne = {a: dict(zip(("proprie", "sentite"), _colonne(a, m))) for a in AGENTI}
            mem.discusse[chiave] = {"quando": int(time.time()), "momento": int(quando), "strumento": strumento,
                                    "coppia": coppia, "modello": modello, "verso": m.fatti.get("verso", ""),
                                    "atomi": sorted(set(m.atomi())), "confluenze": m.presenti,
                                    "colonne": colonne, "logit": {a: g["logit"] for a, g in giudizi.items()},
                                    "agenti": {d.nome: d.agente for d in m.obbligatorie + m.confluenze},
                                    **v.come_dati()}
            if da_seguire and piani:
                mem.da_vedere[chiave] = {"quando": int(time.time()), "coppia": f"{coppia} {modello}", **da_seguire}
        return v

    def _voci_della_squadra(self, m: Metodo, pareri: list[Parere], entra: bool, stop_ok: bool, p: float, punti: float,
                            puntata: float, z: float, esposizione: float, stesso: float) -> list:
        """La riunione in equipe col metodo delle foto: ogni agente dice il suo voto e perche' (e, quando ha
        abbastanza casi dal vivo, quante volte ci prende); il Capo dice chi ha sentito, decide e se ne prende la
        responsabilita'; il Rischio dice quanto."""
        voci = []
        for x in pareri:
            voci.append((x.agente, x.frase() + self._come_ci_prende(x.agente)))
        if not stop_ok:
            voci.append(("Capo", "Non entriamo: senza uno stop giusto non si entra, mai."))
            return voci
        if not m.a_piu:
            voci.append(("Capo", "Non entriamo. Il metodo vuole " + ", ".join(MANCA_IN_PAROLE.get(d.nome, d.nome)
                                                                            for d in m.mancano) + "."))
            return voci
        voci.append(("Capo", self.decisione_in_parole(m, pareri, entra, p, punti, puntata)))
        if entra:
            if z > 0.5:
                testo = "il Capo è più convinto del solito, punto un po' di più"
            elif z < -0.5:
                testo = "il Capo è meno convinto del solito, punto un po' di meno"
            else:
                testo = "convinzione nella media, puntata normale"
            if stesso > 0:
                testo += f"; su {m.fatti.get('strumento')} c'è già un'operazione aperta: ne tengo conto e punto meno"
            elif esposizione > 0:
                testo += "; ci sono già altre operazioni aperte e ne tengo conto"
            voci.append(("Rischio", _cap(testo) + "."))
        return voci

    def _come_ci_prende(self, agente: str) -> str:
        pag = self.memoria.pagella.get(agente, {})
        si, no = pag.get("si", [0, 0]), pag.get("no", [0, 0])
        parti = []
        if si[0] >= ESPERIENZA_MINIMA:
            parti.append(f"quando dico sì va bene {si[1]} volte su {si[0]}")
        if no[0] >= ESPERIENZA_MINIMA:
            parti.append(f"quando dico no va male {no[1]} volte su {no[0]}")
        return (" Dal vivo: " + "; ".join(parti) + ".") if parti else ""

    def decisione_in_parole(self, m: Metodo, pareri: list[Parere], entra: bool, p: float, punti: float,
                            puntata: float) -> str:
        """Il Capo: chi era a favore e chi contro, quanti punti fanno pesati, cosa decide e perche'."""
        compra = m.fatti.get("verso") == "acquisto"
        favore = [f"{x.agente} ({x.voto:+d})" for x in pareri if x.voto > 0]
        contro = [f"{x.agente} ({x.voto:+d})" for x in pareri if x.voto < 0]
        sentiti = (f"A favore: {', '.join(favore) if favore else 'nessuno'}. Contro: {', '.join(contro) if contro else 'nessuno'}. "
                   f"Pesando quanto ognuno ci ha preso finora fanno {_erre(punti)} punti (entro da "
                   f"{_erre(SOGLIA_PUNTI)}): stimo che vada bene il {_p(p)} delle volte.")
        if entra:
            fine = (f" {'Compriamo' if compra else 'Vendiamo'} {m.fatti.get('strumento')}: decido io e la responsabilità è mia.")
            if punti < SOGLIA_PUNTI:
                fine = (" Le regole del metodo ci sono tutte, quindi si entra: la squadra dà il suo parere, ma non "
                        f"blocca. {'Compriamo' if compra else 'Vendiamo'} {m.fatti.get('strumento')}.")
            if contro:
                fine += f" Se va male, chi era contro peserà di più."
            return "Ho sentito tutti. " + sentiti + fine
        if punti < SOGLIA_PUNTI:
            return ("Ho sentito tutti. " + sentiti + " Le regole del metodo ci sono, ma la squadra non è convinta "
                    "abbastanza: la lascio.")
        return "Ho sentito tutti. " + sentiti + " Il Rischio non trova una puntata possibile: la lascio."

    def annulla(self, chiave: str) -> None:
        """L'ordine non e' partito (mercato chiuso, margine...): per imparare conta come non presa."""
        with self._lucchetto:
            d = self.memoria.discusse.get(chiave)
            if d is not None:
                d["entra"] = False
                d.setdefault("pareri", {}).setdefault("Capo", {})["entra"] = False

    def _voci(self, m: Metodo, giudizi, entra, stop_ok, evita, p, puntata, z, esposizione, piano, simili,
              stesso: float = 0.0) -> list:
        """La riunione in equipe: ogni agente dice la sua domanda di Romeo e il suo giudizio, chi ha
        cambiato idea dopo aver sentito i colleghi, il Capo decide, il Rischio dice quanto."""
        compra = m.fatti.get("verso") == "acquisto"
        verbo = "Compriamo" if compra else "Vendiamo"
        voci = []
        for d in m.obbligatorie:
            testo = d.riga()
            extra = [c.perche for c in m.confluenze if c.si and c.agente == d.agente]
            if extra:
                testo += ". In più: " + "; ".join(extra[:2])
            g = giudizi.get(d.agente)
            if g is not None and d.si:
                if g["n"] < ESPERIENZA_MINIMA:
                    testo += f". Dal vivo ho visto solo {g['n']} casi: non ho ancora un giudizio mio"
                else:
                    testo += f". Dai {g['n']} casi che ho visto dal vivo, occasioni così vanno bene il {_p(g['prima'])} delle volte"
                if abs(g["dopo"] - g["prima"]) >= 0.03 and g["sentiti"]:
                    da, cosa, regola = g["sentiti"][0]
                    testo += (f"; sentito {'me stesso' if da == d.agente else da} («{cosa}») passo al {_p(g['dopo'])}: "
                              f"{regola}")
            voci.append((d.agente, testo + "."))
        if piano >= 0 and piano != PIANO_ROMEO:
            from nvm.agenti.foto import PIANI
            voci.append(("Livelli", f"Stavolta {PIANI[piano][1]}: dal vivo, finora, su questo grafico così "
                                    "ha reso di più."))
        if not stop_ok:
            voci.append(("Capo", "Non entriamo: senza uno stop giusto non si entra, mai."))
            return voci
        if not m.a_piu:
            voci.append(("Capo", "Non entriamo. Il metodo vuole " + ", ".join(MANCA_IN_PAROLE.get(d.nome, d.nome)
                                                                            for d in m.mancano) + "."))
            return voci
        n_s, vinte_s, media_s = simili
        if evita:
            voci.append(("Capo", f"Tutte le regole del metodo dicono sì, ma dal vivo occasioni così finora sono andate "
                                 f"male: su {n_s} casi simili ne sono andati bene {vinte_s}, in media {_erre(media_s)} "
                                 "volte il rischio. Romeo: «lose, journal, avoid». Stavolta la lasciamo."))
            return voci
        if not entra:
            voci.append(("Capo", "Tutte le regole del metodo dicono sì, ma il Rischio non trova una puntata possibile."))
            return voci
        n = len(m.obbligatorie)
        punti = [d.nome for d in m.confluenze if d.si]
        entrata = {"vera rottura": " (entrata: vera rottura di struttura)",
                   "kiss of death": " (entrata: kiss of death)",
                   "dal DXY": " (il setup l'ha fatto il DXY)"}.get(m.fatti.get("modello", ""), "")
        testo = f"Tutte e {n} le regole del metodo dicono sì. {verbo} {m.fatti.get('strumento')}{entrata}."
        if punti:
            testo += f" Punti in più: {len(punti)}."
        testo += f" Mettendo insieme i giudizi della squadra stimo che vada bene il {_p(p)} delle volte"
        testo += (f"; nei {n_s} casi più simili già finiti dal vivo ne sono andati bene {vinte_s}." if n_s else
                  "; casi simili dal vivo non ne abbiamo ancora.")
        voci.append(("Capo", testo))
        if z > 0.5:
            perche_r = "il Capo è più convinto del solito, punto un po' di più"
        elif z < -0.5:
            perche_r = "il Capo è meno convinto del solito, punto un po' di meno"
        else:
            perche_r = "convinzione nella media, puntata normale"
        if stesso > 0:
            perche_r += f"; su {m.fatti.get('strumento')} c'è già un'operazione aperta: ne tengo conto e punto meno"
        elif esposizione > 0:
            perche_r += "; ci sono già altre operazioni aperte e ne tengo conto"
        voci.append(("Rischio", _cap(perche_r) + "."))
        return voci

    # --- ogni errore diventa una miglioria ---

    def vero(self, chiave: str, erre: float) -> None:
        """Il risultato vero dal broker di un'operazione presa: vale piu' di quello sulla carta."""
        with self._lucchetto:
            self.memoria.veri[chiave] = round(float(erre), 4)

    def _impara_agenti(self, d: dict, bene: bool, peso: float) -> list[dict]:
        """Ogni agente corregge il suo modello (discesa del gradiente della regressione logistica)."""
        mem = self.memoria
        y = 1.0 if bene else 0.0
        cambiati = []
        for a in AGENTI:
            col = d.get("colonne", {}).get(a)
            if col is None:
                continue
            g = mem.agenti[a]
            proprie, sentite = col.get("proprie", {}), col.get("sentite", {})
            l1, l2 = self._logit_agente(a, proprie, sentite)
            prima = _sig(l2)
            errore = (y - prima) * peso
            g["base"] = round(g["base"] + PASSO_GIUDIZIO * errore, 6)
            for k, x in list(proprie.items()) + list(sentite.items()):
                w = g["pesi"].get(k, self._prior(a, k))
                verso_dove = self._prior(a, k)
                g["pesi"][k] = round(w + PASSO_GIUDIZIO * (errore * x - FRENO * (w - verso_dove)), 6)
            g["n"] += 1
            g["giuste"] += int((prima >= 0.5) == bene)
            cambiati.append({"agente": a, "prima": prima, "dopo": _sig(self._logit_agente(a, proprie, sentite)[1])})
        # Il Capo impara quanto fidarsi di ognuno.
        c = mem.capo
        logit = d.get("logit", {})
        if logit:
            p = _sig(c["base"] + sum(c["fiducia"].get(a, FIDUCIA_INIZIALE) * logit.get(a, 0.0) for a in AGENTI))
            errore = (y - p) * peso
            c["base"] = round(c["base"] + PASSO_CAPO * errore, 6)
            for a in AGENTI:
                f = c["fiducia"].get(a, FIDUCIA_INIZIALE)
                c["fiducia"][a] = round(f + PASSO_CAPO * (errore * logit.get(a, 0.0) - FRENO * (f - FIDUCIA_INIZIALE)), 6)
        return cambiati

    def rifletti(self, chiave: str, esito_erre: float, preso: bool, racconto: str = "") -> list[dict]:
        """L'occasione e' finita (presa o solo sulla carta): si impara. Se dal broker e' arrivato il
        risultato vero, conta quello. Restituisce le lezioni, in parole semplici."""
        with self._lucchetto:
            mem = self.memoria
            d = mem.discusse.pop(chiave, None)
            if d is None:
                return []
            reale = chiave in mem.veri
            erre = float(mem.veri.pop(chiave)) if reale else float(esito_erre)
            r = _stretto(erre, -2.0, 3.0)
            bene = r > 0
            peso = PESO_VERO if reale else PESO_CARTA
            capo = d.get("pareri", {}).get("Capo", {})
            agenti = d.get("agenti", {})
            fatte = []
            cambiati = self._impara_agenti(d, bene, peso)
            mem.casi.append({"quando": int(time.time()), "modello": d.get("modello", ""), "coppia": d.get("coppia", ""),
                             "strumento": d.get("strumento", ""), "a_piu": bool(d.get("a_piu")),
                             "atomi": d.get("atomi", []), "erre": round(erre, 4), "reale": reale})
            if not d.get("a_piu"):
                # La controprova: la regola di Romeo che ha detto no aveva ragione?
                for nome in capo.get("mancano", []):
                    c = mem.controprova.setdefault(nome, [0, 0.0])
                    c[0] += 1
                    c[1] = round(c[1] + r, 4)
                for nome in capo.get("mancano", [])[:1]:
                    a = agenti.get(nome, "Capo")
                    lezione = (f"Avevo detto di no ({MANCA_IN_PAROLE.get(nome, nome)} mancava) e sarebbe andata "
                               + ("male: la regola aveva ragione." if not bene else "bene lo stesso: lo segno, ma la regola resta."))
                    fatte.append({"agente": a, "lezione": lezione, "giusto": not bene})
            else:
                ap = mem.a_piu
                ap[0] += 1
                ap[1] = round(ap[1] + r, 4)
                ap[2] += int(bene)
                entrato = bool(capo.get("entra")) and bool(d.get("entra"))
                voti = d.get("pareri", {}).get("voti")
                if voti:
                    # La squadra coi pareri: il Capo impara di chi fidarsi, ognuno dice se aveva ragione.
                    fatte += self._impara_dai_voti(d, voti, bene, peso, entrato, reale)
                else:
                    # Chi ha imparato qualcosa: chi si era sbagliato di piu' dice di quanto cambia idea.
                    for c in sorted(cambiati, key=lambda c: -abs(c["dopo"] - c["prima"]))[:3]:
                        sbagliato = (c["prima"] >= 0.5) != bene
                        fatte.append({"agente": c["agente"], "giusto": not sbagliato, "lezione":
                                      f"pensavo che andasse bene il {_p(c['prima'])} delle volte ed è andata "
                                      f"{'bene' if bene else 'male'}: per occasioni così ora dico {_p(c['dopo'])}."})
                    if entrato:
                        lezione = ("Siamo entrati con tutte le regole del metodo ed è andata bene." if bene else
                                   "Siamo entrati con tutte le regole del metodo ed è andata male: capita, lo stop ci ha "
                                   "protetti. Lo segno nel diario.")
                    else:
                        lezione = ("L'avevamo lasciata e sarebbe andata bene: lo segno, la prossima volta pesa di meno."
                                   if bene else "L'avevamo lasciata e abbiamo fatto bene.")
                    fatte.append({"agente": "Capo", "lezione": lezione + (" (risultato vero dal broker)" if reale else ""),
                                  "giusto": entrato == bene})
                if entrato and preso:
                    ri, g = mem.rischio, d.get("pareri", {}).get("Rischio", {})
                    prima = ri["base"]
                    parte = max(float(g.get("parte", prima)), 0.0)
                    rr = _stretto(erre, -1.2, 3.0)
                    spinta = PASSO_RISCHIO * rr / max(1.0 + 2 * parte * rr, 0.05)
                    ri["base"] = round(ri["base"] * math.exp(_stretto(spinta, -0.5, 0.5)), 8)
                    ri["convinzione"] = round(ri["convinzione"] + spinta * float(g.get("z", 0.0)), 6)
                    ri["aperte"] = round(ri["aperte"] - spinta * 100 * float(g.get("esposizione", 0.0)), 6)
                    ri["stesso"] = round(ri.get("stesso", 0.2) - spinta * 100 * float(g.get("stesso", 0.0)), 6)
                    fatte.append({"agente": "Rischio", "giusto": bene, "lezione":
                                  f"Dopo questa {'vincita' if bene else 'perdita'} la mia puntata base passa da "
                                  f"{_pct(prima)} a {_pct(ri['base'])} del conto."})
                # Le idee: l'errore del Capo si segna in ogni situazione in cui e' successo.
                errore = r - float(capo.get("stima", 0.0))
                visti = d.get("atomi", [])
                chiavi = list(visti) + [f"{x}&{y}" for i, x in enumerate(visti) for y in visti[i + 1:]]
                for o in [mem.capo["errori"]] + [mem.ombra.setdefault(k, [0, 0.0, 0.0]) for k in chiavi]:
                    o[0] += 1
                    o[1] = round(o[1] + errore, 5)
                    o[2] = round(o[2] + errore * errore, 5)
                for k, idea in mem.idee.items():
                    if _idea_vera(k, set(visti)):
                        idea["dopo"] = idea.get("dopo", 0) + 1
                        # L'idea si corregge anche lei, come gli altri pesi.
                        mem.pesi_idee[k] = round(mem.pesi_idee.get(k, 0.0) + 0.03 * _stretto(errore, -4, 4), 6)
            for l in fatte:
                mem.impara(l["agente"], {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                         "esito": round(erre, 3), "preso": preso, "reale": reale, "lezione": l["lezione"]})
            mem.salva()
        return fatte

    def _impara_dai_voti(self, d: dict, voti: dict, bene: bool, peso: float, entrato: bool, reale: bool) -> list[dict]:
        """Il Capo corregge quanto si fida di ognuno (regressione logistica sui voti: chi aveva ragione pesa di piu'),
        la pagella di ogni agente si aggiorna, e le lezioni dicono le cose come stanno: chi era contro e aveva
        ragione, chi era a favore e ha sbagliato, e il Capo che se ne prende la responsabilita'."""
        mem = self.memoria
        c = mem.capo
        w = c["voti"]
        y = 1.0 if bene else 0.0
        prima = dict(w)
        p = _sig(c["base_voti"] + sum(w.get(a, FIDUCIA_VOTO) * v for a, v in voti.items()))
        errore = (y - p) * peso
        c["base_voti"] = round(c["base_voti"] + PASSO_CAPO * errore, 6)
        for a, v in voti.items():
            f = w.get(a, FIDUCIA_VOTO)
            w[a] = round(_stretto(f + PASSO_CAPO * (errore * v - FRENO * (f - FIDUCIA_VOTO)), 0.0, FIDUCIA_MASSIMA), 6)
            pag = mem.pagella.setdefault(a, {"si": [0, 0], "no": [0, 0]})
            if v > 0:
                pag["si"][0] += 1
                pag["si"][1] += int(bene)
            elif v < 0:
                pag["no"][0] += 1
                pag["no"][1] += int(not bene)
        for k, q in d.get("pareri", {}).get("ascolti", []):
            a = mem.ascolti.setdefault(k, [0, 0])
            a[0] += 1
            a[1] += int((q > 0) == bene)
        ragioni = d.get("pareri", {}).get("ragioni", {})

        def perche(a: str) -> str:
            r = ragioni.get(a) or []
            return f" ({r[0]})" if r else ""
        favore = [a for a, v in voti.items() if v > 0]
        contro = [a for a, v in voti.items() if v < 0]
        punti = float(d.get("pareri", {}).get("Capo", {}).get("punti", 0.0))
        fatte = []
        vero = " (risultato vero dal broker)" if reale else ""
        if entrato and not bene:
            for a in contro[:3]:
                fatte.append({"agente": a, "giusto": True, "lezione": f"Avevo detto di no{perche(a)}: avevo ragione."})
            for a in [a for a in favore if voti[a] >= 2][:2]:
                fatte.append({"agente": a, "giusto": False,
                              "lezione": f"Avevo detto sì con forza{perche(a)} ed è andata male: il Capo mi peserà un po' meno."})
            piu = [a for a in contro if w[a] > prima.get(a, FIDUCIA_VOTO) + 1e-9]
            testo = "Sono entrato io ed è andata male: la responsabilità è mia."
            if piu:
                testo += " Da ora peso di più " + ", ".join(f"{a} ({_virgola(prima[a])} → {_virgola(w[a])})" for a in piu[:3]) + "."
            fatte.append({"agente": "Capo", "giusto": False, "lezione": testo + vero})
        elif entrato:
            testo = "Sono entrato ed è andata bene." + (f" Avevano visto giusto: {', '.join(favore[:4])}." if favore else "")
            for a in contro[:2]:
                fatte.append({"agente": a, "giusto": False,
                              "lezione": f"Avevo detto di no{perche(a)} ed è andata bene lo stesso: lo segno."})
            fatte.append({"agente": "Capo", "giusto": True, "lezione": testo + vero})
        elif d.get("pareri", {}).get("Capo", {}).get("veto"):
            # Solo le occasioni discusse prima del 22/10/2026, quando la previsione della domenica era un no.
            fatte.append({"agente": "Capo", "giusto": not bene, "lezione":
                          f"L'ho lasciata perché andava contro la nostra previsione della domenica: sarebbe andata "
                          f"{'bene' if bene else 'male'}. La previsione la seguiamo sempre." + vero})
        elif bene:
            fatte.append({"agente": "Capo", "giusto": False, "lezione":
                          f"L'avevo lasciata ({_erre(punti)} punti) e sarebbe andata bene: da ora peso un po' di più chi "
                          f"era a favore ({', '.join(favore[:4]) or 'nessuno'})." + vero})
        else:
            fatte.append({"agente": "Capo", "giusto": True, "lezione": "L'avevo lasciata e ho fatto bene." + vero})
        return fatte

    def impara_piani(self, chiave: str, risultati: list) -> None:
        """Livelli: come sarebbe andato ogni piano su un'occasione finita (None se non si poteva fare)."""
        with self._lucchetto:
            d = self.memoria.da_vedere.pop(chiave, None)
            if d is None:
                return
            conti = self.memoria.piani.setdefault(d.get("coppia", ""), {})
            for j, r in enumerate(risultati):
                if r is None or not math.isfinite(r):
                    continue
                n, somma = conti.get(str(j), [0, 0.0])
                conti[str(j)] = [n + 1, round(somma + _stretto(float(r), -2.0, 3.0), 5)]

    # --- il sabato ---

    def _inventa(self) -> list[tuple[str, str, str]]:
        mem = self.memoria
        n_tutti, somma_tutti, quadrati_tutti = mem.capo["errori"]
        if n_tutti < 2 * VOLTE_IDEA:
            return []
        media_tutti = somma_tutti / n_tutti
        scarto = math.sqrt(max(quadrati_tutti / n_tutti - media_tutti ** 2, 1e-9))
        nuove, usati, candidate = [], set(), []
        for k, (n, somma, _) in mem.ombra.items():
            if n < VOLTE_IDEA or k in mem.idee or "&" not in k and not k.startswith(("strumento=", "coppia=", "modello=")):
                continue
            media = somma / n - media_tutti
            certezza = abs(media) / (scarto / math.sqrt(n))
            if certezza >= CERTEZZA_IDEA:
                candidate.append((certezza, k, n, media))
        for certezza, k, n, media in sorted(candidate, reverse=True):
            parti = k.split("&")
            if usati.intersection(parti):
                continue
            usati.update(parti)
            mem.pesi_idee[k] = round(media, 6)
            mem.idee[k] = {"agente": "Capo", "quando": int(time.time()), "volte": round(n), "media": round(media, 4), "dopo": 0}
            nuove.append(("Capo", f"💡 idea nuova: quando c'è {nome_idea(k)} va {'meglio' if media > 0 else 'peggio'} "
                                  f"di come pensavamo (visto circa {round(n)} volte). Da ora ne tengo conto.", ""))
        return nuove

    def _dimentica(self) -> list[tuple[str, str, str]]:
        mem = self.memoria
        via = []
        for k, idea in list(mem.idee.items()):
            if idea.get("dopo", 0) >= VOLTE_IDEA and abs(mem.pesi_idee.get(k, 0.0)) < 0.01:
                del mem.idee[k]
                mem.pesi_idee.pop(k, None)
                via.append(("Capo", f"lascio perdere l'idea {nome_idea(k)}: alla prova dei fatti non cambiava niente.", ""))
        return via

    def riscrivi_manuali(self, pagelle: str = "") -> list[tuple[str, str, str]]:
        """La revisione del sabato: chi ha cambiato giudizio in settimana, se Romeo aveva ragione, le idee."""
        with self._lucchetto:
            mem = self.memoria
            prima = mem.sabato or {"agenti": {}, "fiducia": {}, "base": PUNTATA_INIZIALE, "controprova": {},
                                   "a_piu": [0, 0.0, 0]}
            cambi = []
            for a in AGENTI:
                g = mem.agenti[a]
                n_prima = prima.get("agenti", {}).get(a, {}).get("n", 0)
                if g["n"] - n_prima <= 0:
                    continue
                pesi_prima = prima.get("agenti", {}).get(a, {}).get("pesi", {})
                mosse = sorted(((k, w - pesi_prima.get(k, self._prior(a, k))) for k, w in g["pesi"].items()),
                               key=lambda x: -abs(x[1]))
                if mosse and abs(mosse[0][1]) >= 0.05:
                    k, delta = mosse[0]
                    cambi.append((a, f"in settimana ho visto {g['n'] - n_prima} casi; ora do "
                                     f"{'più' if delta > 0 else 'meno'} peso a «{k}».", ""))
            for a in AGENTI:
                f, f0 = mem.capo["fiducia"].get(a, FIDUCIA_INIZIALE), prima.get("fiducia", {}).get(a, FIDUCIA_INIZIALE)
                if abs(f - f0) >= 0.05:
                    cambi.append(("Capo", f"mi fido {'di più' if f > f0 else 'di meno'} del giudizio di {a}.", ""))
            n0, s0, v0 = prima.get("a_piu", [0, 0.0, 0])
            n1, s1, v1 = mem.a_piu
            if n1 > n0:
                k = n1 - n0
                cambi.append(("Capo", f"questa settimana {k} occasion{'e' if k == 1 else 'i'} con tutte le regole del "
                                      f"metodo: {v1 - v0} andat{'a' if v1 - v0 == 1 else 'e'} bene, in media "
                                      f"{_erre((s1 - s0) / k)} volte il rischio.", ""))
            for nome, (n, somma) in sorted(mem.controprova.items()):
                n_p, s_p = prima.get("controprova", {}).get(nome, [0, 0.0])
                if n - n_p >= 3:
                    media = (somma - s_p) / (n - n_p)
                    cambi.append(("Capo", f"senza «{MANCA_IN_PAROLE.get(nome, nome)}» abbiamo lasciato {n - n_p} "
                                          f"occasioni: sarebbero andate in media {_erre(media)} volte il rischio. "
                                          + ("La regola aveva ragione." if media <= 0 else "Stavolta sarebbero andate bene, "
                                             "ma la regola resta: la seguiamo sempre."), ""))
            if abs(mem.rischio["base"] - prima.get("base", PUNTATA_INIZIALE)) >= 0.0005:
                cambi.append(("Rischio", f"la mia puntata base passa da {_pct(prima.get('base', PUNTATA_INIZIALE))} a "
                                         f"{_pct(mem.rischio['base'])} del conto.", ""))
            cambi += self._inventa() + self._dimentica()
            mem.ombra = {k: [o[0] * 0.7, o[1] * 0.7, o[2] * 0.7] for k, o in mem.ombra.items() if o[0] * 0.7 >= 1}
            mem.capo["errori"] = [x * 0.7 for x in mem.capo["errori"]]
            mem.sabato = {"agenti": {a: {"n": g["n"], "pesi": dict(g["pesi"])} for a, g in mem.agenti.items()},
                          "fiducia": dict(mem.capo["fiducia"]), "base": mem.rischio["base"],
                          "controprova": {k: list(v) for k, v in mem.controprova.items()}, "a_piu": list(mem.a_piu)}
            mem.storia.append({"quando": int(time.time()), "cambi": cambi})
            mem.salva()
        return cambi
