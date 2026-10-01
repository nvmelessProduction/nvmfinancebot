"""La squadra: i nostri agenti, col metodo dei 17 video di Romeo, che imparano dal vivo.

Il proprietario: *"Voglio che li riaddestri da zero seguendo i 17 video in maniera corretta e completa"*,
*"bot intelligente e strategia di Romeo"*, *"non voglio essere preso in giro"*. Nessuna AI esterna. Qui
c'e' scritto esattamente cosa fa ogni agente, e i messaggi su Telegram dicono solo questo.

1. **Le domande di Romeo** (`metodo.py`, `spec/metodo_romeo.md`). Ogni agente risponde alla sua. Sono
   il metodo: **se anche una sola dice no, non si entra**, e non si disimparano.
2. **Il giudizio di ogni agente si impara.** Ognuno guarda i numeri del suo mestiere (`Metodo.numeri`:
   il Grilletto lo spessore, l'FVG, l'SMT...; l'Orario l'ora e il giorno; Livelli quanto si guadagna...)
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
5. **Livelli** sceglie fra tre piani, tutti di Romeo (al 50% si prende sempre qualcosa): parte da quello
   dei video e cambia solo se un altro rende di piu' dal vivo.
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

VERSIONE = "video-2"
AGENTI = ("Cacciatore", "Grilletto", "Key level", "Bias", "Orario", "Livelli")
# Le domande obbligatorie, in parole semplici: quello che manca quando dicono no.
MANCA_IN_PAROLE = {
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
    ("Bias", "Grilletto", "SMT", 0.4, "l'SMT confermato vuol dire espansione (V11 13:01)"),
    ("Orario", "Grilletto", "finta a fine candela", 0.3,
     "se la finta è arrivata a fine candela, la distribuzione parte subito (V8 07:31)"),
    ("Key level", "Cacciatore", "candela 1 spessa", 0.3,
     "una candela 1 spessa appena prima del livello è il CRT ideale (V9 02:43)"),
    ("Grilletto", "Grilletto", "FVG", 0.3, "il Model#1 con l'FVG è più probabile (V3 16:01)"),
    ("Livelli", "Cacciatore", "dentro un CRT più grande", 0.3,
     "dentro un movimento più grande nello stesso verso l'obiettivo arriva più spesso (V5 13:00)"),
    ("Livelli", "Grilletto", "kiss of death", 0.3, "dopo il kiss of death si va dritti all'obiettivo (V4 07:32)"),
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
PASSO_RISCHIO = 0.01
# Livelli nasce col piano di Romeo (`livelli.PIANI_ROMEO`).
PIANO_ROMEO = 1
# Il peso dei risultati veri rispetto a quelli sulla carta.
PESO_VERO, PESO_CARTA = 1.0, 0.5
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

    CAMPI = ("versione", "agenti", "capo", "rischio", "piani", "idee", "pesi_idee", "ombra", "lezioni", "discusse",
             "da_vedere", "casi", "controprova", "a_piu", "veri", "sabato", "storia")

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
        for k, v in (("base", PUNTATA_INIZIALE), ("convinzione", 0.2), ("aperte", 0.2), ("media", 0.0),
                     ("scarto", 0.1), ("volte", 0)):
            self.rischio.setdefault(k, v)

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

    def _rischio(self, p: float, esposizione: float) -> tuple[float, float]:
        ri = self.memoria.rischio
        # Quanto e' convinto il Capo rispetto al solito: si sa solo dopo un po' di occasioni.
        z = _stretto((p - ri["media"]) / max(ri["scarto"], 1e-6), -3.0, 3.0) if ri.get("volte", 0) >= 10 else 0.0
        return ri["base"] * math.exp(_stretto(ri["convinzione"] * z - ri["aperte"] * 100 * esposizione, -5.0, 3.0)), z

    def riunione(self, chiave: str, strumento: str, m: Metodo, quando: int, piani: Optional[list] = None,
                 esposizione: float = 0.0, da_seguire: Optional[dict] = None, op=None) -> Verdetto:
        """La riunione su un'occasione: le domande di Romeo gia' risposte (`metodo.valuta`)."""
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
            p = self._capo(giudizi)
            stima = self.stima(m)
            n_s, vinte_s, media_s, t_s = self.simili(m)
            evita = m.a_piu and n_s >= MINIMO_SIMILI and media_s < 0 and t_s <= -CERTEZZA_EVITA
            capo_entra = m.a_piu and stop_ok and not evita
            parte, z = self._rischio(p, esposizione)
            puntata = max(parte, 0.0) if capo_entra else 0.0
            entra = capo_entra and puntata > 0
            if entra:
                ri = mem.rischio
                ri["volte"] = ri.get("volte", 0) + 1
                ri["media"] = round(p if ri["volte"] == 1 else 0.95 * ri["media"] + 0.05 * p, 6)
                ri["scarto"] = round(max(math.sqrt(0.95 * ri["scarto"] ** 2 + 0.05 * (p - ri["media"]) ** 2), 0.02), 6)
            voci = self._voci(m, giudizi, entra, stop_ok, evita, p, puntata, z, esposizione, piano,
                              (n_s, vinte_s, media_s))
            lista = {d.nome: bool(d.si) for d in m.obbligatorie}
            pareri = {"Capo": {"entra": capo_entra, "p": round(p, 4), "stima": round(stima, 4), "a_piu": m.a_piu,
                               "evita": evita, "mancano": [d.nome for d in m.mancano],
                               "simili": [n_s, vinte_s, round(media_s, 4)]},
                      "Rischio": {"parte": round(parte, 6), "z": round(z, 4), "esposizione": round(esposizione, 6)},
                      "agenti": {a: {"prima": round(g["prima"], 4), "dopo": round(g["dopo"], 4)}
                                 for a, g in giudizi.items()}}
            v = Verdetto(entra, piano, round(puntata, 6), round(p, 3), voci, pareri, lista, time.time() - t0,
                         a_piu=m.a_piu)
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

    def annulla(self, chiave: str) -> None:
        """L'ordine non e' partito (mercato chiuso, margine...): per imparare conta come non presa."""
        with self._lucchetto:
            d = self.memoria.discusse.get(chiave)
            if d is not None:
                d["entra"] = False
                d.setdefault("pareri", {}).setdefault("Capo", {})["entra"] = False

    def _voci(self, m: Metodo, giudizi, entra, stop_ok, evita, p, puntata, z, esposizione, piano, simili) -> list:
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
            from nvm.agenti.livelli import PIANI_ROMEO
            voci.append(("Livelli", f"Stavolta {PIANI_ROMEO[piano][1]}: dal vivo, finora, su questo grafico così "
                                    "ha reso di più."))
        if not stop_ok:
            voci.append(("Capo", "Non entriamo: senza uno stop giusto non si entra, mai."))
            return voci
        if not m.a_piu:
            voci.append(("Capo", "Non entriamo. Romeo vuole " + ", ".join(MANCA_IN_PAROLE.get(d.nome, d.nome)
                                                                        for d in m.mancano) + "."))
            return voci
        n_s, vinte_s, media_s = simili
        if evita:
            voci.append(("Capo", f"Tutte le regole di Romeo dicono sì, ma dal vivo occasioni così finora sono andate "
                                 f"male: su {n_s} casi simili ne sono andati bene {vinte_s}, in media {_erre(media_s)} "
                                 "volte il rischio. Romeo: «lose, journal, avoid». Stavolta la lasciamo."))
            return voci
        if not entra:
            voci.append(("Capo", "Tutte le regole di Romeo dicono sì, ma il Rischio non trova una puntata possibile."))
            return voci
        n = len(m.obbligatorie)
        punti = [d.nome for d in m.confluenze if d.si]
        entrata = {"vera rottura": " (entrata: vera rottura di struttura)",
                   "kiss of death": " (entrata: kiss of death)"}.get(m.fatti.get("modello", ""), "")
        testo = f"Tutte e {n} le regole di Romeo dicono sì. {verbo} {m.fatti.get('strumento')}{entrata}."
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
        if esposizione > 0:
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
                               + ("male: Romeo aveva ragione." if not bene else "bene lo stesso: lo segno, ma la regola resta."))
                    fatte.append({"agente": a, "lezione": lezione, "giusto": not bene})
            else:
                ap = mem.a_piu
                ap[0] += 1
                ap[1] = round(ap[1] + r, 4)
                ap[2] += int(bene)
                # Chi ha imparato qualcosa: chi si era sbagliato di piu' dice di quanto cambia idea.
                for c in sorted(cambiati, key=lambda c: -abs(c["dopo"] - c["prima"]))[:3]:
                    sbagliato = (c["prima"] >= 0.5) != bene
                    fatte.append({"agente": c["agente"], "giusto": not sbagliato, "lezione":
                                  f"pensavo che andasse bene il {_p(c['prima'])} delle volte ed è andata "
                                  f"{'bene' if bene else 'male'}: per occasioni così ora dico {_p(c['dopo'])}."})
                entrato = bool(capo.get("entra")) and bool(d.get("entra"))
                if entrato:
                    lezione = ("Siamo entrati con tutte le regole di Romeo ed è andata bene." if bene else
                               "Siamo entrati con tutte le regole di Romeo ed è andata male: capita, lo stop ci ha "
                               "protetti. Lo segno nel diario.")
                else:
                    lezione = ("L'avevamo lasciata e sarebbe andata bene: lo segno, la prossima volta pesa di meno." if bene
                               else "L'avevamo lasciata e abbiamo fatto bene.")
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
                cambi.append(("Capo", f"questa settimana {k} occasion{'e' if k == 1 else 'i'} con tutte le regole di "
                                      f"Romeo: {v1 - v0} andat{'a' if v1 - v0 == 1 else 'e'} bene, in media "
                                      f"{_erre((s1 - s0) / k)} volte il rischio.", ""))
            for nome, (n, somma) in sorted(mem.controprova.items()):
                n_p, s_p = prima.get("controprova", {}).get(nome, [0, 0.0])
                if n - n_p >= 3:
                    media = (somma - s_p) / (n - n_p)
                    cambi.append(("Capo", f"senza «{MANCA_IN_PAROLE.get(nome, nome)}» abbiamo lasciato {n - n_p} "
                                          f"occasioni: sarebbero andate in media {_erre(media)} volte il rischio. "
                                          + ("Romeo aveva ragione." if media <= 0 else "Stavolta sarebbero andate bene, "
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
