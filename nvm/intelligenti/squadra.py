"""La squadra di agenti intelligenti: nostri, nessuna AI esterna, nessun test sui vent'anni.

Nessun limite e nessun obbligo (il proprietario, 30/09/2026: *"non dobbiamo dargli ne' limiti ne'
obblighi. Solo una regola: senza stop non si entra"*). Nessuno nasce imparato: nascono con la
strategia di Romeo e imparano a usarla dal vivo, un errore alla volta.

1. **Percepiscono.** I fatti dell'occasione dal mercato (`fatti.py`).
2. **Sanno quello che sa Romeo.** Ogni agente ha le regole di Romeo del suo mestiere (`regole.py`),
   ognuna con quanto ci crede. Da li' si fa un'idea di quanto rendera' l'operazione.
3. **Il Capo** mette insieme gli agenti, piu' o meno ascoltati, e le domande di Romeo prima di entrare
   ("Enter a trade?"): nasce credendo che un solo no basti a lasciar perdere. Entra se si aspetta di
   guadagnare. **Livelli** sceglie dove mettere lo stop e come prendere il profitto. **Il Rischio**
   sceglie quanto puntare, da solo.
4. **Ogni errore diventa una miglioria.** Quando un'occasione finisce (presa o solo sulla carta) la
   squadra confronta quello che si aspettava con quello che e' successo: ognuno corregge quanto crede
   alle sue regole, il Capo quanto ascolta ognuno e quanto crede alla lista di Romeo, il Rischio
   quanto puntare (piu' se il conto cresce, meno se cala), Livelli quali stop e uscite funzionano.
5. **Inventano.** Tengono d'occhio gli errori che si ripetono sempre nello stesso verso in una
   situazione precisa (due cose di Romeo insieme, o una cosa di Romeo e un giorno, un'ora, uno
   strumento...). Quando e' chiaro, ne fanno un'idea nuova, sua, e la usano.
6. **Il sabato** ognuno rivede quello che ha imparato in settimana e lo racconta.

L'unica regola fissa: senza stop non si entra. Tutto resta scritto in `dati/vivo/intelligenti/memoria.json`.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nvm.intelligenti.regole import AGENTI, LISTA, PER_NOME, REGOLE, atomi, di_chi, in_parole

SPECIALISTI = AGENTI
DOMANDE = LISTA
PER_AGENTE = {a: [r for r in REGOLE if r.agente == a] for a in AGENTI}
DOMANDA_DI = {r.lista: r for r in REGOLE if r.lista}
# Quello che manca, quando una domanda di Romeo ha risposta no.
DOMANDE_IN_PAROLE = {
    "key_level": "una zona importante del grafico grande",
    "orderflow_alto": "il grafico grande dalla nostra parte",
    "draw_on_liquidity": "una strada libera verso l'obiettivo",
    "ore_giuste": "l'ora giusta",
}

# --- Da dove partono il primo giorno: da Romeo. Da li' in poi decide il vivo. -------------------------

# Quanto vale, in volte il rischio, un'unita' di peso di Romeo.
SCALA = 0.05
# Il Capo nasce credendo alla lista di Romeo: ogni no pesa come una perdita piena...
NO_ROMEO = -1.0
# ...e con la prudenza di Romeo: *"At the beginning of each trading week, I genuinely intend on placing
# ZERO trades… I wait and pick the best one."*
PRUDENZA_ROMEO = -0.3
# Il Rischio nasce puntando l'1% del conto a operazione: Romeo non dice un numero, e' il nostro punto
# di partenza. Poi lo cambia lui, senza tetti.
PUNTATA_INIZIALE = 0.01
# Livelli nasce col piano di Romeo: stop oltre l'estremo della finta, meta' al 50% e il resto al lato opposto.
PIANO_ROMEO = 4

# Quanto dell'errore si corregge ogni volta (diviso fra tutto quello che aveva contato, perche' nessuna
# correzione sia troppo grande).
PASSO = 0.03
# Il Rischio: quanto cambia la puntata a ogni operazione finita (in proporzione), per far crescere il
# conto il piu' possibile senza troppa leva (Romeo: *"If you blow your account because of one bad setup,
# you suck at risk management"*): punta la meta' di quello che farebbe crescere il conto piu' in fretta.
PASSO_RISCHIO = 0.01
# Un'idea nuova: un errore che si ripete almeno tante volte, e cosi' netto da non essere un caso.
VOLTE_IDEA = 30
CERTEZZA_IDEA = 4.0
LEZIONI_TENUTE = 300
OMBRA_MASSIMA = 60000


def _stretto(x: float, basso: float, alto: float) -> float:
    return min(max(x, basso), alto)


def _pct(x: float) -> str:
    return f"{x:.2%}".replace(".", ",")


def _cap(testo: str) -> str:
    return testo[:1].upper() + testo[1:] if testo else testo


def con_stop(op) -> bool:
    """L'unica regola: un'operazione ha sempre lo stop, dalla parte giusta."""
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
    """La memoria della squadra, su disco: tutto quello che hanno imparato."""

    cartella: Path
    # Quanto ogni agente crede a ogni sua regola (e alle sue idee), in volte il rischio.
    pesi: dict = field(default_factory=dict)
    # Il Capo: la sua prudenza, quanto ascolta ogni agente, quanto crede a ogni domanda di Romeo.
    capo: dict = field(default_factory=dict)
    # Il Rischio: la puntata base, quanto la cambia con la convinzione e con le altre aperte.
    rischio: dict = field(default_factory=dict)
    # Livelli: com'e' andato ogni piano, per grafico.
    piani: dict = field(default_factory=dict)
    # Le idee inventate, e gli errori che si tengono d'occhio per inventarne di nuove.
    idee: dict = field(default_factory=dict)
    ombra: dict = field(default_factory=dict)
    # Come ci prende ogni agente dal vivo.
    voti: dict = field(default_factory=dict)
    lezioni: dict = field(default_factory=dict)
    discusse: dict = field(default_factory=dict)
    da_vedere: dict = field(default_factory=dict)
    # Com'erano le cose alla revisione di sabato scorso: per dire cosa e' cambiato.
    sabato: dict = field(default_factory=dict)
    storia: list = field(default_factory=list)

    CAMPI = ("pesi", "capo", "rischio", "piani", "idee", "ombra", "voti", "lezioni", "discusse", "da_vedere",
             "sabato", "storia")

    def __post_init__(self):
        for a in AGENTI:
            p = self.pesi.setdefault(a, {})
            for r in PER_AGENTE[a]:
                p.setdefault(r.nome, round(SCALA * r.peso, 6))
        self.capo.setdefault("prudenza", PRUDENZA_ROMEO)
        ascolto = self.capo.setdefault("ascolto", {})
        for a in AGENTI:
            ascolto.setdefault(a, 1.0)
        no = self.capo.setdefault("no", {})
        for q in DOMANDA_DI:
            no.setdefault(q, NO_ROMEO)
        for k, v in (("base", PUNTATA_INIZIALE), ("convinzione", 0.2), ("aperte", 0.2), ("media", 0.3),
                     ("scarto", 0.3)):
            self.rischio.setdefault(k, v)
        # Gli errori della settimana, per le idee nuove: tutti insieme e situazione per situazione (`ombra`).
        self.capo.setdefault("errori", [0, 0.0, 0.0])

    @classmethod
    def carica(cls, cartella: Path) -> "Memoria":
        f = cartella / "memoria.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            if "pesi" in d:
                return cls(cartella, **{k: d[k] for k in cls.CAMPI if k in d})
            # La memoria di una squadra di prima (con altre regole): si riparte da Romeo.
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


@dataclass
class Verdetto:
    entra: bool
    piano: int
    # La parte del conto da rischiare (0 = non si punta).
    puntata: float
    fiducia: float
    voci: list
    pareri: dict
    lista: dict
    secondi: float
    chiamate: int = 0

    def come_dati(self) -> dict:
        return {"entra": self.entra, "piano": self.piano, "puntata": self.puntata, "fiducia": self.fiducia,
                "pareri": self.pareri, "lista": self.lista, "secondi": round(self.secondi, 3)}


def _idea_vera(chiave: str, visti: set) -> bool:
    return all(a in visti for a in chiave.split("&"))


def nome_idea(chiave: str) -> str:
    return " e ".join(f"«{in_parole(a)}»" for a in chiave.split("&"))


class Squadra:
    """La squadra: si riunisce su ogni occasione trovata dal sistema, decide da sola, impara."""

    def __init__(self, cartella: Path):
        self.memoria = Memoria.carica(cartella)
        self.ultimo_errore = ""
        # Il giro e le lezioni (in disparte) toccano la memoria: una cosa alla volta.
        self._lucchetto = threading.RLock()

    def salva(self) -> None:
        with self._lucchetto:
            self.memoria.salva()

    # --- 1-3. guardano, si fanno un'idea, decidono ---

    def _guarda(self, agente: str, f: dict, visti: set) -> dict:
        """Il parere di un agente: le sue regole e le sue idee sui fatti, pesate da quanto ci crede."""
        pesi = self.memoria.pesi[agente]
        x, motivi = {}, []
        for r in PER_AGENTE[agente]:
            try:
                esito, perche = r.guarda(f)
            except Exception:
                continue
            if esito:
                x[r.nome] = int(esito)
                motivi.append((esito * pesi[r.nome], perche))
        for chiave, idea in self.memoria.idee.items():
            if idea["agente"] == agente and _idea_vera(chiave, visti):
                x[chiave] = 1
                w = pesi.get(chiave, 0.0)
                motivi.append((w, ("secondo una mia idea nuova, " if w > 0 else "attenzione, una mia idea nuova: ")
                               + f"{nome_idea(chiave)} di solito va {'meglio' if w > 0 else 'peggio'} di come sembra"))
        stima = sum(pesi.get(k, 0.0) * v for k, v in x.items())
        motivi.sort(key=lambda m: -abs(m[0]))
        voto = "entra" if stima > 0.02 else "non entrare" if stima < -0.02 else "neutro"
        a_favore = [m[1] for m in motivi if m[0] > 0]
        contro = [m[1] for m in motivi if m[0] < 0]
        principale = (a_favore if voto == "entra" else contro if voto == "non entrare" else [m[1] for m in motivi])
        return {"voto": voto, "stima": round(stima, 4), "x": x,
                "ragionamento": _cap(principale[0]) + "." if principale else "",
                "a_favore": a_favore[:2], "contro": contro[:2]}

    def _lista(self, f: dict) -> tuple[dict, dict]:
        """Le domande di Romeo sui fatti: si' o no, e perche'."""
        risposte, perche = {}, {}
        for d in DOMANDE:
            if d not in DOMANDA_DI:
                # La conferma sul grafico piccolo c'e' sempre: ogni occasione nasce da un Model#1.
                risposte[d], perche[d] = True, "conferma dell'inversione"
                continue
            try:
                esito, testo = DOMANDA_DI[d].guarda(f)
            except Exception:
                esito, testo = -1, "non riesco a leggerlo"
            risposte[d], perche[d] = esito > 0, testo
        return risposte, perche

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
        """Il Rischio: quanto del conto, dalla sua puntata base, da quanto e' convinta la squadra rispetto
        al solito e da quanto e' gia' in gioco (in punti percentuali del conto). Restituisce (parte del
        conto, convinzione)."""
        ri = self.memoria.rischio
        z = _stretto((stima - ri["media"]) / max(ri["scarto"], 1e-6), -3.0, 3.0)
        return ri["base"] * math.exp(_stretto(ri["convinzione"] * z - ri["aperte"] * 100 * esposizione, -5.0, 3.0)), z

    def riunione(self, chiave: str, strumento: str, f: dict, piani: Optional[list] = None,
                 esposizione: float = 0.0, da_seguire: Optional[dict] = None, op=None) -> Verdetto:
        """La riunione su un'occasione, coi fatti gia' letti (`fatti.py`). `piani`: le operazioni possibili
        (stop e uscite diversi); `op`: quella proposta; `da_seguire`: cosa serve per rivedere i piani dopo."""
        t0 = time.time()
        with self._lucchetto:
            m = self.memoria
            visti = set(atomi(f))
            pareri = {a: self._guarda(a, f, visti) for a in SPECIALISTI}
            lista, perche = self._lista(f)
            ascolto = m.capo["ascolto"]
            no = [q for q in DOMANDA_DI if not lista[q]]
            stima = (m.capo["prudenza"] + sum(ascolto[a] * p["stima"] for a, p in pareri.items())
                     + sum(m.capo["no"][q] for q in no))
            piano = self._piano(f.get("coppia", ""), piani)
            scelta = piani[piano] if piano >= 0 else op
            stop_ok = scelta is None or con_stop(scelta)
            capo_entra = stima > 0 and stop_ok
            puntata, z = 0.0, 0.0
            parte, z = self._rischio(stima, esposizione)
            if capo_entra:
                ri = m.rischio
                ri["media"] = round(0.98 * ri["media"] + 0.02 * stima, 6)
                ri["scarto"] = round(math.sqrt(0.98 * ri["scarto"] ** 2 + 0.02 * (stima - ri["media"]) ** 2), 6)
                puntata = max(parte, 0.0)
            entra = capo_entra and puntata > 0
            voci = self._voci(f, pareri, capo_entra, entra, stop_ok, stima, no, perche, puntata, z, esposizione, piano)
            capo = {"entra": capo_entra, "stima": round(stima, 4), "no": no, "ascolto": dict(ascolto)}
            rischio = {"parte": round(parte, 6), "z": round(z, 4), "esposizione": round(esposizione, 6)}
            v = Verdetto(entra, piano, round(puntata, 6), round(_stretto(0.5 + stima / 2, 0.0, 1.0), 3), voci,
                         {**pareri, "Capo": capo, "Rischio": rischio}, lista, time.time() - t0)
            m.discusse[chiave] = {"quando": int(time.time()), "strumento": strumento, "coppia": f.get("coppia", ""),
                                  "verso": f.get("verso", ""), "atomi": sorted(visti), **v.come_dati()}
            if da_seguire and piani:
                m.da_vedere[chiave] = {"quando": int(time.time()), "coppia": f.get("coppia", ""), **da_seguire}
        return v

    def _voci(self, f, pareri, capo_entra, entra, stop_ok, stima, no, perche, puntata, z, esposizione, piano) -> list:
        """Quello che la squadra dice in equipe, in parole semplici: chi ha pesato di piu' a favore, chi
        era contro, il Capo, il Rischio."""
        compra = f.get("verso") == "acquisto"
        verbo = "Compriamo" if compra else "Vendiamo"
        ascolto = self.memoria.capo["ascolto"]
        pesati = sorted(pareri, key=lambda a: -abs(ascolto[a] * pareri[a]["stima"]))
        favore = [a for a in pesati if pareri[a]["voto"] == "entra"]
        contro = [a for a in pesati if pareri[a]["voto"] == "non entrare"]
        voci = [(a, pareri[a]["ragionamento"]) for a in favore[:2]]
        if contro:
            voci.append((contro[0], "Però: " + pareri[contro[0]]["ragionamento"][:1].lower() + pareri[contro[0]]["ragionamento"][1:]))
        if piano >= 0 and piano != PIANO_ROMEO:
            from nvm.cervello.piani import PIANI
            st, us = PIANI[piano]
            piano_detto = ("Stavolta " + {"stretto": "metto lo stop stretto, appena oltre la conferma",
                                                   "estremo": "metto lo stop oltre la finta",
                                                   "largo": "metto lo stop più largo del solito"}[st]
                         + " e " + {"primo": "prendo tutto al primo obiettivo", "meta": "chiudo metà al primo obiettivo",
                                    "secondo": "punto tutto al secondo obiettivo"}[us]
                           + ": dal vivo, finora, così ha reso di più.")
            k = next((i for i, (chi, _) in enumerate(voci) if chi == "Livelli"), None)
            if k is None:
                voci.append(("Livelli", piano_detto))
            else:
                voci[k] = ("Livelli", voci[k][1] + " " + piano_detto)
        if not stop_ok:
            voci.append(("Capo", "Non entriamo: senza uno stop giusto non si entra, mai."))
            return voci
        if not capo_entra:
            if no:
                testo = "Non entriamo. Mancano cose che Romeo vuole: " + ", ".join(DOMANDE_IN_PAROLE[q] for q in no) + "."
            else:
                testo = "Non entriamo: la squadra non è abbastanza convinta."
            voci.append(("Capo", testo))
            return voci
        conta = f"{len(favore)} a favore, {len(contro)} contro"
        testo = f"{verbo} {f.get('strumento')}. La squadra: {conta}."
        if contro:
            testo += f" Ho sentito {contro[0]}, ma il resto pesa di più."
        if no:
            testo += (" Romeo qui non entrerebbe (manca " + ", ".join(DOMANDE_IN_PAROLE[q] for q in no)
                      + "), ma dal vivo ho imparato che in casi così conviene.")
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

    # --- 4-5. ogni errore diventa una miglioria ---

    def rifletti(self, chiave: str, esito_erre: float, preso: bool, racconto: str = "") -> list[dict]:
        """L'occasione e' finita (presa o solo sulla carta): tutti imparano dall'errore fra quello che
        si aspettavano e quello che e' successo. Restituisce le lezioni (agente, lezione, giusto)."""
        with self._lucchetto:
            m = self.memoria
            d = m.discusse.pop(chiave, None)
            if d is None:
                return []
            r = _stretto(float(esito_erre), -2.0, 3.0)
            pareri = d.get("pareri", {})
            capo = pareri.get("Capo", {})
            stima = float(capo.get("stima", 0.0))
            errore = r - stima
            bene = r > 0
            fatte = []
            # Ognuno corregge un pezzetto dell'errore, in proporzione a quanto aveva contato: gli agenti
            # quanto credono alle cose che avevano visto, il Capo la sua prudenza, quanto ascolta ognuno e
            # quanto crede alle domande di Romeo.
            ascolti = capo.get("ascolto", {})
            no = capo.get("no", [])
            quanto = 1.0 + len(no) + sum(float(pareri[a].get("stima", 0.0)) ** 2 for a in SPECIALISTI if a in pareri)
            quanto += sum(ascolti.get(a, 1.0) ** 2 * sum(v * v for v in pareri[a].get("x", {}).values())
                          for a in SPECIALISTI if a in pareri)
            passo = PASSO * _stretto(errore, -4.0, 4.0) / quanto
            c = m.capo
            c["prudenza"] = round(c["prudenza"] + passo, 6)
            for q in no:
                c["no"][q] = round(c["no"][q] + passo, 6)
            for a in SPECIALISTI:
                p = pareri.get(a)
                if not p:
                    continue
                ascolto = ascolti.get(a, 1.0)
                c["ascolto"][a] = round(c["ascolto"][a] + passo * float(p.get("stima", 0.0)), 6)
                pesi = m.pesi[a]
                for k, v in p.get("x", {}).items():
                    pesi[k] = round(pesi.get(k, 0.0) + passo * ascolto * v, 6)
            for a in SPECIALISTI:
                p = pareri.get(a)
                if not p or p["voto"] == "neutro":
                    continue
                giusto = (p["voto"] == "entra") == bene
                v = m.voti.setdefault(a, {"n": 0, "giuste": 0})
                v["n"] += 1
                v["giuste"] += int(giusto)
                perche = (p.get("a_favore") if p["voto"] == "entra" else p.get("contro")) or [""]
                detto = "di entrare" if p["voto"] == "entra" else "di non entrare"
                if giusto:
                    lezione = f"Avevo detto {detto} e avevo ragione ({perche[0]}): ci crederò un po' di più."
                else:
                    lezione = f"Avevo detto {detto} ({perche[0]}), ma è andata al contrario: ci crederò un po' di meno."
                fatte.append({"agente": a, "lezione": lezione, "giusto": giusto})
            entrato = bool(capo.get("entra"))
            if entrato:
                lezione = ("Siamo entrati ed è andata bene." if bene else
                           "Siamo entrati ed è andata male: in casi così sarò più prudente.")
            else:
                lezione = ("Non siamo entrati e sarebbe andata bene: in casi così sarò meno severo." if bene else
                           "Non siamo entrati e abbiamo fatto bene.")
            fatte.append({"agente": "Capo", "lezione": lezione, "giusto": entrato == bene})
            # Il Rischio: quanto puntare, da come sarebbe cresciuto il conto puntando un po' di piu' o di meno.
            if entrato:
                ri, g = m.rischio, pareri.get("Rischio", {})
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
            # Le idee: ogni errore si segna nelle situazioni in cui e' successo.
            visti = d.get("atomi", [])
            chiavi = list(visti) + [f"{x}&{y}" for i, x in enumerate(visti) for y in visti[i + 1:]]
            for o in [m.capo["errori"]] + [m.ombra.setdefault(k, [0, 0.0, 0.0]) for k in chiavi]:
                o[0] += 1
                o[1] = round(o[1] + errore, 5)
                o[2] = round(o[2] + errore * errore, 5)
            for k, idea in m.idee.items():
                if _idea_vera(k, set(visti)):
                    idea["dopo"] = idea.get("dopo", 0) + 1
            for l in fatte:
                m.impara(l["agente"], {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                       "esito": round(float(esito_erre), 3), "preso": preso, "lezione": l["lezione"]})
            m.salva()
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

    # --- 6. il sabato: rivedono tutto, inventano, raccontano ---

    def _inventa(self) -> list[tuple[str, str, str]]:
        """Gli errori della settimana che in una situazione precisa vanno sempre nello stesso verso (piu'
        di quanto sbagliamo in generale) diventano idee nuove. Poi si ricomincia a guardare."""
        m = self.memoria
        n_tutti, somma_tutti, quadrati_tutti = m.capo["errori"]
        if n_tutti < 2 * VOLTE_IDEA:
            return []
        media_tutti = somma_tutti / n_tutti
        scarto = math.sqrt(max(quadrati_tutti / n_tutti - media_tutti ** 2, 1e-9))
        nuove, usati = [], set()
        candidate = []
        for k, (n, somma, _) in m.ombra.items():
            if n < VOLTE_IDEA or k in m.idee or ("&" not in k and k.partition("=")[0] in PER_NOME):
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
            agente = next((di_chi(p) for p in parti if p.partition("=")[0] in PER_NOME), di_chi(parti[0]))
            m.pesi[agente][k] = round(media, 6)
            m.idee[k] = {"agente": agente, "quando": int(time.time()), "volte": round(n), "media": round(media, 4), "dopo": 0}
            verso = "meglio" if media > 0 else "peggio"
            nuove.append((agente, f"💡 idea nuova: quando c'è {nome_idea(k)} va {verso} di come pensavamo "
                                  f"(visto circa {round(n)} volte). Da ora ne tengo conto.", ""))
        return nuove

    def _dimentica(self) -> list[tuple[str, str, str]]:
        m = self.memoria
        via = []
        for k, idea in list(m.idee.items()):
            a = idea["agente"]
            if idea.get("dopo", 0) >= VOLTE_IDEA and abs(m.pesi[a].get(k, 0.0)) < 0.01:
                del m.idee[k]
                m.pesi[a].pop(k, None)
                via.append((a, f"lascio perdere l'idea {nome_idea(k)}: alla prova dei fatti non cambiava niente.", ""))
        return via

    def riscrivi_manuali(self, pagelle: str = "") -> list[tuple[str, str, str]]:
        """La revisione del sabato: ognuno racconta cosa ha cambiato in settimana e le idee nuove.
        Restituisce (agente, cosa, proposta)."""
        with self._lucchetto:
            m = self.memoria
            prima = m.sabato or {"pesi": {a: {r.nome: round(SCALA * r.peso, 6) for r in PER_AGENTE[a]} for a in AGENTI},
                                 "capo": {"prudenza": PRUDENZA_ROMEO, "no": {q: NO_ROMEO for q in DOMANDA_DI},
                                          "ascolto": {a: 1.0 for a in AGENTI}},
                                 "rischio": {"base": PUNTATA_INIZIALE}}
            cambi = []
            for a in SPECIALISTI:
                vecchi = prima["pesi"].get(a, {})
                mosse = sorted(((k, m.pesi[a].get(k, 0.0) - vecchi.get(k, 0.0)) for k in m.pesi[a] if k in PER_NOME),
                               key=lambda x: -abs(x[1]))
                cosa = []
                for k, delta in mosse[:2]:
                    if abs(delta) < 0.005:
                        continue
                    r = PER_NOME[k]
                    etichetta = r.si or r.no or k
                    ora = m.pesi[a][k]
                    if ora <= 0 < vecchi.get(k, 0.0):
                        cosa.append(f"non credo più che «{etichetta}» aiuti")
                    else:
                        cosa.append(f"credo {'di più' if delta > 0 else 'di meno'} a «{etichetta}»")
                if cosa:
                    giuste, n = m.ci_prende(a)
                    cambi.append((a, "; ".join(cosa) + (f" (dal vivo ci ho preso {giuste} volte su {n})" if n else "") + ".", ""))
            c, pc = m.capo, prima["capo"]
            cosa = []
            dno = sum(c["no"].values()) - sum(pc["no"].values())
            if abs(dno) >= 0.05:
                cosa.append("credo " + ("di più" if dno < 0 else "di meno") + " che un solo no di Romeo basti a non entrare")
            dp = c["prudenza"] - pc["prudenza"]
            if abs(dp) >= 0.02:
                cosa.append("sono " + ("più prudente" if dp < 0 else "meno prudente"))
            asc = sorted(((a, c["ascolto"][a] - pc["ascolto"].get(a, 1.0)) for a in AGENTI), key=lambda x: -abs(x[1]))
            if asc and abs(asc[0][1]) >= 0.02:
                cosa.append(f"ascolto {'di più' if asc[0][1] > 0 else 'di meno'} {asc[0][0]}")
            if cosa:
                cambi.append(("Capo", "; ".join(cosa) + ".", ""))
            base_prima = prima["rischio"]["base"]
            if abs(m.rischio["base"] - base_prima) >= 0.0005:
                cambi.append(("Rischio", f"la mia puntata base passa da {_pct(base_prima)} a {_pct(m.rischio['base'])} del conto.", ""))
            cambi += self._inventa() + self._dimentica()
            # Gli errori vecchi contano sempre meno: le idee nascono da quello che succede adesso.
            m.ombra = {k: [o[0] * 0.7, o[1] * 0.7, o[2] * 0.7] for k, o in m.ombra.items() if o[0] * 0.7 >= 1}
            m.capo["errori"] = [x * 0.7 for x in m.capo["errori"]]
            m.sabato = {"pesi": {a: dict(m.pesi[a]) for a in AGENTI},
                        "capo": {"prudenza": c["prudenza"], "no": dict(c["no"]), "ascolto": dict(c["ascolto"])},
                        "rischio": {"base": m.rischio["base"]}}
            m.storia.append({"quando": int(time.time()), "cambi": cambi})
            m.salva()
        return cambi
