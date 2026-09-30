"""La squadra: i nostri agenti, riaddestrati da zero sul metodo dei 17 video di Romeo.

Il proprietario, 30/09/2026: *"Voglio che li riaddestri da zero seguendo i 17 video in maniera
corretta e completa"*. Nessuna AI esterna, niente test sui vent'anni: imparano solo dal vivo.

1. **Le domande di Romeo** (`metodo.py`, `spec/metodo_romeo.md`). Ogni agente risponde alla sua:
   il Cacciatore (candela 3), il Grilletto (la finta oltre l'apertura, il Model#1 con la candela
   spessa), il Key level, il Bias (la direzione del grafico grande), l'Orario, Livelli (la strada fino
   al 50%). Sono il metodo: **se anche una sola dice no, non si entra**, e non si disimparano.
2. **Si entra quando c'e' il setup di Romeo**, tutte le volte che c'e'; altrimenti niente. Nessun
   limite inventato da noi (il proprietario, 30/09/2026: *"Se c'e' setup bene altrimenti sti cavoli.
   Non inventiamo cose"*).
3. **Le confluenze** (SMT, FVG, vera rottura di struttura, ...): punti in piu'. Ognuna nasce con lo
   stesso piccolo peso; dal vivo la squadra impara quanto conta davvero. Se un'occasione A+ con certe
   confluenze va sempre male, il Capo impara a lasciarla (*"lose, journal, avoid"*, V9 22:45).
4. **Senza stop non si entra**, mai. **Livelli** sceglie fra gli stop e le uscite quello che rende
   (all'inizio quello di Romeo: stop alla punta della finta, meta' al 50% e il resto al lato opposto).
   **Il Rischio** sceglie quanto puntare, e impara dal conto (*"always manage risk"*).
5. **Ogni errore diventa una miglioria**, anche le occasioni lasciate: se una regola di Romeo ha detto
   no, si guarda come sarebbe andata (la controprova), e il sabato si dice se Romeo aveva ragione.
6. **Inventano**: un errore che si ripete sempre nello stesso verso in una situazione precisa diventa
   un'idea nuova, loro.

Tutto resta scritto in `dati/vivo/intelligenti/memoria.json`. La memoria di prima si butta: si
riparte da zero, dai video.
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

VERSIONE = "video-1"
AGENTI = ("Cacciatore", "Grilletto", "Key level", "Bias", "Orario", "Livelli")
# Le domande obbligatorie, in parole semplici: quello che manca quando dicono no.
MANCA_IN_PAROLE = {
    "candela 3": "aspettare la candela 3",
    "oltre l'apertura": "la finta oltre l'apertura della candela 3",
    "Model#1 spesso": "la conferma con una candela spessa",
    "key level": "un key level del grafico grande",
    "direzione": "il grafico grande dalla nostra parte",
    "ora giusta": "l'ora giusta",
    "50% da prendere": "il 50% ancora da prendere",
}

# Ogni confluenza nasce con questo peso (in volte il rischio); il Capo nasce senza prudenza: ogni A+
# si prende, finche' il vivo non insegna altro.
PESO_INIZIALE = 0.05
PRUDENZA_INIZIALE = 0.0
# Il Rischio nasce puntando l'1% del conto: Romeo non dice un numero, dice di non esagerare.
PUNTATA_INIZIALE = 0.01
# Livelli nasce col piano di Romeo: stop alla punta della finta, meta' al 50% e il resto al lato opposto.
PIANO_ROMEO = 4

PASSO = 0.03
PASSO_RISCHIO = 0.01
VOLTE_IDEA = 20
CERTEZZA_IDEA = 3.0
LEZIONI_TENUTE = 300
OMBRA_MASSIMA = 20000


def _stretto(x: float, basso: float, alto: float) -> float:
    return min(max(x, basso), alto)


def _pct(x: float) -> str:
    return f"{x:.2%}".replace(".", ",")


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


@dataclass
class Memoria:
    """Tutto quello che la squadra ha imparato dal vivo."""

    cartella: Path
    versione: str = VERSIONE
    # Quanto vale ogni confluenza (e ogni idea inventata), in volte il rischio.
    pesi: dict = field(default_factory=dict)
    capo: dict = field(default_factory=dict)
    rischio: dict = field(default_factory=dict)
    piani: dict = field(default_factory=dict)
    idee: dict = field(default_factory=dict)
    ombra: dict = field(default_factory=dict)
    voti: dict = field(default_factory=dict)
    lezioni: dict = field(default_factory=dict)
    discusse: dict = field(default_factory=dict)
    da_vedere: dict = field(default_factory=dict)
    # Come sarebbero andate le occasioni lasciate perche' una regola di Romeo diceva no: [volte, somma R].
    controprova: dict = field(default_factory=dict)
    # Come vanno le A+: [volte, somma R, vinte].
    a_piu: list = field(default_factory=lambda: [0, 0.0, 0])
    sabato: dict = field(default_factory=dict)
    storia: list = field(default_factory=list)

    CAMPI = ("versione", "pesi", "capo", "rischio", "piani", "idee", "ombra", "voti", "lezioni", "discusse",
             "da_vedere", "controprova", "a_piu", "sabato", "storia")

    def __post_init__(self):
        self.capo.setdefault("prudenza", PRUDENZA_INIZIALE)
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
            # La memoria di una squadra di prima: si riparte da zero, dai video.
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
        self.storia = self.storia[-300:]
        f = self.cartella / "memoria.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: getattr(self, k) for k in self.CAMPI}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)

    def impara(self, agente: str, lezione: dict) -> None:
        self.lezioni.setdefault(agente, []).append(lezione)
        self.lezioni[agente] = self.lezioni[agente][-LEZIONI_TENUTE:]

    def ci_prende(self, agente: str) -> tuple[int, int]:
        v = self.voti.get(agente, {})
        return v.get("giuste", 0), v.get("n", 0)

    def peso(self, nome: str) -> float:
        return float(self.pesi.get(nome, PESO_INIZIALE))


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

    # --- la riunione ---

    def stima(self, m: Metodo) -> float:
        """Quanto la squadra si aspetta da un'occasione A+, in volte il rischio: la prudenza del Capo
        piu' il peso di ogni confluenza presente e di ogni idea inventata che vale."""
        mem = self.memoria
        visti = set(m.atomi())
        s = mem.capo["prudenza"] + sum(mem.peso(n) for n in m.presenti)
        s += sum(mem.pesi.get(k, 0.0) for k in mem.idee if _idea_vera(k, visti))
        return s

    def _piano(self, coppia: str, piani: Optional[list]) -> int:
        """Livelli: il piano che dal vivo ha reso di piu' su questo grafico (all'inizio quello di Romeo)."""
        if not piani:
            return -1
        conti = self.memoria.piani.get(coppia, {})

        def valore(j):
            n, somma = conti.get(str(j), [0, 0.0])
            prima = 0.05 if j == PIANO_ROMEO else 0.0
            return (somma + 10 * prima) / (n + 10)
        buoni = [j for j, op in enumerate(piani) if op is not None and con_stop(op)]
        return max(buoni, key=valore) if buoni else -1

    def _rischio(self, stima: float, esposizione: float) -> tuple[float, float]:
        ri = self.memoria.rischio
        # Quanto e' convinta la squadra rispetto al solito: si sa solo dopo un po' di occasioni.
        z = _stretto((stima - ri["media"]) / max(ri["scarto"], 1e-6), -3.0, 3.0) if ri.get("volte", 0) >= 10 else 0.0
        return ri["base"] * math.exp(_stretto(ri["convinzione"] * z - ri["aperte"] * 100 * esposizione, -5.0, 3.0)), z

    def riunione(self, chiave: str, strumento: str, m: Metodo, quando: int, piani: Optional[list] = None,
                 esposizione: float = 0.0, da_seguire: Optional[dict] = None, op=None) -> Verdetto:
        """La riunione su un'occasione: le domande di Romeo gia' risposte (`metodo.valuta`)."""
        t0 = time.time()
        with self._lucchetto:
            mem = self.memoria
            coppia = m.fatti.get("coppia", "")
            piano = self._piano(coppia, piani)
            scelta = piani[piano] if piano >= 0 else op
            stop_ok = scelta is not None and con_stop(scelta)
            stima = self.stima(m)
            capo_entra = m.a_piu and stop_ok and stima >= 0
            parte, z = self._rischio(stima, esposizione)
            puntata = max(parte, 0.0) if capo_entra else 0.0
            entra = capo_entra and puntata > 0
            if entra:
                ri = mem.rischio
                ri["volte"] = ri.get("volte", 0) + 1
                ri["media"] = round(stima if ri["volte"] == 1 else 0.95 * ri["media"] + 0.05 * stima, 6)
                ri["scarto"] = round(max(math.sqrt(0.95 * ri["scarto"] ** 2 + 0.05 * (stima - ri["media"]) ** 2), 0.02), 6)
            voci = self._voci(m, entra, stop_ok, stima, puntata, z, esposizione, piano)
            lista = {d.nome: bool(d.si) for d in m.obbligatorie}
            pareri = {"Capo": {"entra": capo_entra, "stima": round(stima, 4), "a_piu": m.a_piu,
                               "mancano": [d.nome for d in m.mancano]},
                      "Rischio": {"parte": round(parte, 6), "z": round(z, 4), "esposizione": round(esposizione, 6)}}
            v = Verdetto(entra, piano, round(puntata, 6), round(_stretto(0.5 + stima, 0.0, 1.0), 3), voci, pareri,
                         lista, time.time() - t0, a_piu=m.a_piu)
            mem.discusse[chiave] = {"quando": int(time.time()), "momento": int(quando), "strumento": strumento, "coppia": coppia,
                                    "verso": m.fatti.get("verso", ""), "atomi": sorted(set(m.atomi())),
                                    "confluenze": m.presenti,
                                    "agenti": {d.nome: d.agente for d in m.obbligatorie + m.confluenze},
                                    **v.come_dati()}
            if da_seguire and piani:
                mem.da_vedere[chiave] = {"quando": int(time.time()), "coppia": coppia, **da_seguire}
        return v

    def annulla(self, chiave: str) -> None:
        """L'ordine non e' partito (mercato chiuso, margine...): per imparare conta come non presa."""
        with self._lucchetto:
            d = self.memoria.discusse.get(chiave)
            if d is not None:
                d["entra"] = False
                d.setdefault("pareri", {}).setdefault("Capo", {})["entra"] = False

    def _voci(self, m: Metodo, entra, stop_ok, stima, puntata, z, esposizione, piano) -> list:
        """La riunione in equipe, in parole semplici: ogni agente dice la sua domanda di Romeo, il Capo
        decide, il Rischio dice quanto."""
        compra = m.fatti.get("verso") == "acquisto"
        verbo = "Compriamo" if compra else "Vendiamo"
        voci = []
        for d in m.obbligatorie:
            testo = d.riga()
            extra = [c.perche for c in m.confluenze if c.si and c.agente == d.agente]
            if extra:
                testo += ". In più: " + "; ".join(extra[:2])
            voci.append((d.agente, testo + "."))
        if piano >= 0 and piano != PIANO_ROMEO:
            from nvm.cervello.piani import PIANI
            st, us = PIANI[piano]
            voci.append(("Livelli", "Stavolta " + {"stretto": "metto lo stop stretto, appena oltre la conferma",
                                                   "estremo": "metto lo stop alla punta della finta",
                                                   "largo": "metto lo stop più largo"}[st]
                         + " e " + {"primo": "prendo tutto al primo obiettivo", "meta": "chiudo metà al primo obiettivo",
                                    "secondo": "punto tutto al secondo obiettivo"}[us]
                         + ": dal vivo, finora, così ha reso di più."))
        if not stop_ok:
            voci.append(("Capo", "Non entriamo: senza uno stop giusto non si entra, mai."))
            return voci
        if not m.a_piu:
            voci.append(("Capo", "Non entriamo. Romeo vuole " + ", ".join(MANCA_IN_PAROLE.get(d.nome, d.nome)
                                                                        for d in m.mancano) + "."))
            return voci
        if not entra:
            voci.append(("Capo", "Tutte le regole di Romeo dicono sì, ma dal vivo abbiamo visto che occasioni "
                                 "così finora sono andate male: stavolta la lasciamo."))
            return voci
        n = len(m.obbligatorie)
        punti = [d.nome for d in m.confluenze if d.si]
        testo = f"Tutte e {n} le regole di Romeo dicono sì. {verbo} {m.fatti.get('strumento')}."
        if punti:
            testo += f" Punti in più: {len(punti)}."
        voci.append(("Capo", testo))
        if z > 0.5:
            perche_r = "la squadra è più convinta del solito, punto un po' di più"
        elif z < -0.5:
            perche_r = "la squadra è meno convinta del solito, punto un po' di meno"
        else:
            perche_r = "convinzione nella media, puntata normale"
        if esposizione > 0:
            perche_r += "; ci sono già altre operazioni aperte e ne tengo conto"
        voci.append(("Rischio", _cap(perche_r) + "."))
        return voci

    # --- ogni errore diventa una miglioria ---

    def rifletti(self, chiave: str, esito_erre: float, preso: bool, racconto: str = "") -> list[dict]:
        """L'occasione e' finita (presa o solo sulla carta): si impara. Restituisce le lezioni."""
        with self._lucchetto:
            mem = self.memoria
            d = mem.discusse.pop(chiave, None)
            if d is None:
                return []
            r = _stretto(float(esito_erre), -2.0, 3.0)
            bene = r > 0
            capo = d.get("pareri", {}).get("Capo", {})
            fatte = []
            if not d.get("a_piu"):
                # La controprova: la regola di Romeo che ha detto no aveva ragione?
                for nome in capo.get("mancano", []):
                    c = mem.controprova.setdefault(nome, [0, 0.0])
                    c[0] += 1
                    c[1] = round(c[1] + r, 4)
                agenti = d.get("agenti", {})
                for nome in capo.get("mancano", [])[:1]:
                    a = agenti.get(nome, "Capo")
                    lezione = (f"Avevo detto di no ({MANCA_IN_PAROLE.get(nome, nome)} mancava) e sarebbe andata "
                               + ("male: Romeo aveva ragione." if not bene else "bene lo stesso: lo segno, ma la regola resta."))
                    fatte.append({"agente": a, "lezione": lezione, "giusto": not bene})
                    v = mem.voti.setdefault(a, {"n": 0, "giuste": 0})
                    v["n"] += 1
                    v["giuste"] += int(not bene)
                for l in fatte:
                    mem.impara(l["agente"], {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                             "esito": round(float(esito_erre), 3), "preso": preso, "lezione": l["lezione"]})
                mem.salva()
                return fatte
            # Un'occasione A+: si corregge quanto contano le confluenze e la prudenza del Capo.
            ap = mem.a_piu
            ap[0] += 1
            ap[1] = round(ap[1] + r, 4)
            ap[2] += int(bene)
            stima = float(capo.get("stima", 0.0))
            errore = r - stima
            confluenze = d.get("confluenze", [])
            idee = [k for k in mem.idee if _idea_vera(k, set(d.get("atomi", [])))]
            passo = PASSO * _stretto(errore, -4.0, 4.0) / (1.0 + len(confluenze) + len(idee))
            mem.capo["prudenza"] = round(mem.capo["prudenza"] + passo, 6)
            for n in confluenze:
                mem.pesi[n] = round(mem.peso(n) + passo, 6)
            for k in idee:
                mem.pesi[k] = round(mem.pesi.get(k, 0.0) + passo, 6)
            agenti = d.get("agenti", {})
            for n in confluenze[:3]:
                a = agenti.get(n, "Grilletto")
                v = mem.voti.setdefault(a, {"n": 0, "giuste": 0})
                v["n"] += 1
                v["giuste"] += int(bene)
                fatte.append({"agente": a, "giusto": bene, "lezione":
                              f"C'era «{n}» ed è andata {'bene' if bene else 'male'}: "
                              f"ci crederò un po' {'di più' if bene else 'di meno'}."})
            entrato = bool(capo.get("entra")) and bool(d.get("entra"))
            if entrato:
                lezione = ("Siamo entrati con tutte le regole di Romeo ed è andata bene." if bene else
                           "Siamo entrati con tutte le regole di Romeo ed è andata male: capita, lo stop ci ha protetti. "
                           "Lo segno nel diario.")
            else:
                lezione = ("L'avevamo lasciata e sarebbe andata bene: sarò meno severo." if bene else
                           "L'avevamo lasciata e abbiamo fatto bene.")
            fatte.append({"agente": "Capo", "lezione": lezione, "giusto": entrato == bene})
            if entrato:
                ri, g = mem.rischio, d.get("pareri", {}).get("Rischio", {})
                prima = ri["base"]
                parte = max(float(g.get("parte", prima)), 0.0)
                rr = _stretto(float(esito_erre), -1.2, 3.0)
                spinta = PASSO_RISCHIO * rr / max(1.0 + 2 * parte * rr, 0.05)
                ri["base"] = round(ri["base"] * math.exp(_stretto(spinta, -0.5, 0.5)), 8)
                ri["convinzione"] = round(ri["convinzione"] + spinta * float(g.get("z", 0.0)), 6)
                ri["aperte"] = round(ri["aperte"] - spinta * 100 * float(g.get("esposizione", 0.0)), 6)
                if preso:
                    fatte.append({"agente": "Rischio", "giusto": bene, "lezione":
                                  f"Dopo questa {'vincita' if bene else 'perdita'} la mia puntata base passa da "
                                  f"{_pct(prima)} a {_pct(ri['base'])} del conto."})
            # Le idee: l'errore si segna in ogni situazione in cui e' successo.
            visti = d.get("atomi", [])
            chiavi = list(visti) + [f"{x}&{y}" for i, x in enumerate(visti) for y in visti[i + 1:]]
            for o in [mem.capo["errori"]] + [mem.ombra.setdefault(k, [0, 0.0, 0.0]) for k in chiavi]:
                o[0] += 1
                o[1] = round(o[1] + errore, 5)
                o[2] = round(o[2] + errore * errore, 5)
            for k, idea in mem.idee.items():
                if _idea_vera(k, set(visti)):
                    idea["dopo"] = idea.get("dopo", 0) + 1
            for l in fatte:
                mem.impara(l["agente"], {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                         "esito": round(float(esito_erre), 3), "preso": preso, "lezione": l["lezione"]})
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
            if n < VOLTE_IDEA or k in mem.idee or "&" not in k and not k.startswith(("strumento=", "coppia=")):
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
            mem.pesi[k] = round(media, 6)
            mem.idee[k] = {"agente": "Capo", "quando": int(time.time()), "volte": round(n), "media": round(media, 4), "dopo": 0}
            nuove.append(("Capo", f"💡 idea nuova: quando c'è {nome_idea(k)} va {'meglio' if media > 0 else 'peggio'} "
                                  f"di come pensavamo (visto circa {round(n)} volte). Da ora ne tengo conto.", ""))
        return nuove

    def _dimentica(self) -> list[tuple[str, str, str]]:
        mem = self.memoria
        via = []
        for k, idea in list(mem.idee.items()):
            if idea.get("dopo", 0) >= VOLTE_IDEA and abs(mem.pesi.get(k, 0.0)) < 0.01:
                del mem.idee[k]
                mem.pesi.pop(k, None)
                via.append(("Capo", f"lascio perdere l'idea {nome_idea(k)}: alla prova dei fatti non cambiava niente.", ""))
        return via

    def riscrivi_manuali(self, pagelle: str = "") -> list[tuple[str, str, str]]:
        """La revisione del sabato: cosa e' cambiato in settimana, se Romeo aveva ragione, le idee nuove."""
        with self._lucchetto:
            mem = self.memoria
            prima = mem.sabato or {"pesi": {}, "prudenza": PRUDENZA_INIZIALE, "base": PUNTATA_INIZIALE,
                                   "controprova": {}, "a_piu": [0, 0.0, 0]}
            cambi = []
            mosse = sorted(((n, mem.peso(n) - prima["pesi"].get(n, PESO_INIZIALE)) for n in mem.pesi if n not in mem.idee),
                           key=lambda x: -abs(x[1]))
            for n, delta in mosse[:3]:
                if abs(delta) >= 0.005:
                    cambi.append(("Capo", f"credo {'di più' if delta > 0 else 'di meno'} a «{n}».", ""))
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
            dp = mem.capo["prudenza"] - prima.get("prudenza", PRUDENZA_INIZIALE)
            if abs(dp) >= 0.02:
                cambi.append(("Capo", "sono " + ("più prudente" if dp < 0 else "meno prudente") + " con le A+.", ""))
            if abs(mem.rischio["base"] - prima.get("base", PUNTATA_INIZIALE)) >= 0.0005:
                cambi.append(("Rischio", f"la mia puntata base passa da {_pct(prima.get('base', PUNTATA_INIZIALE))} a "
                                         f"{_pct(mem.rischio['base'])} del conto.", ""))
            cambi += self._inventa() + self._dimentica()
            mem.ombra = {k: [o[0] * 0.7, o[1] * 0.7, o[2] * 0.7] for k, o in mem.ombra.items() if o[0] * 0.7 >= 1}
            mem.capo["errori"] = [x * 0.7 for x in mem.capo["errori"]]
            mem.sabato = {"pesi": dict(mem.pesi), "prudenza": mem.capo["prudenza"], "base": mem.rischio["base"],
                          "controprova": {k: list(v) for k, v in mem.controprova.items()}, "a_piu": list(mem.a_piu)}
            mem.storia.append({"quando": int(time.time()), "cambi": cambi})
            mem.salva()
        return cambi
