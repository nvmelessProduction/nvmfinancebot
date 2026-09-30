"""La squadra di agenti intelligenti: nostri, nessuna AI esterna, nessun test sui vent'anni.

Ogni agente e' un programma che percepisce, ragiona, decide e impara (l'agente intelligente dei
libri: percezione -> conoscenza -> decisione -> esperienza):

1. **Percepisce.** Legge i fatti dell'occasione dal mercato (`fatti.py`): in che candela siamo, il
   key level, l'ora, il bias, i grafici grandi, i vuoti.
2. **Sa quello che sa Romeo.** Ognuno ha le regole di Romeo del suo mestiere (`regole.py`, dalla
   `bibbia.md`), ognuna col suo peso: all'inizio quanto conta per Romeo.
3. **Vota e discute.** Ognuno vota (entra, non entrare, neutro) col suo perche'. Se non sono
   d'accordo si confrontano: chi e' incerto ascolta i colleghi che ultimamente ci hanno preso di piu',
   chi e' sicuro risponde a chi la pensa al contrario.
4. **Il Capo decide** con la lista di Romeo ("Enter a trade?": cinque domande, un solo no e non si
   entra) e poi col voto della squadra, pesato da quanto ognuno ci ha preso dal vivo. **Il Rischio**
   dice quanto puntare, dentro un tetto fisso che nessuno puo' superare (`PARTE_MASSIMA`).
5. **Imparano solo dal vivo.** Quando un'occasione finisce (presa o solo sulla carta) ogni regola
   che aveva parlato guadagna o perde fiducia, e ogni agente guadagna o perde credito presso i
   colleghi. Scrivono la lezione (*"win, journal, repeat; lose, journal, avoid; miss, journal, catch
   next time"*).
6. **Si modificano da soli.** Ogni sabato ognuno riscrive il suo manuale: spegne le regole che dal
   vivo sbagliano sempre, riaccende quelle che tornano a funzionare; il Capo cambia quanto e'
   esigente per tenere il ritmo di Romeo. La lista di Romeo e il tetto di rischio non li cambia nessuno.

Tutto resta scritto (`dati/vivo/intelligenti/memoria.json`): chi ha detto cosa, perche', e cosa ha imparato.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nvm.intelligenti.regole import AGENTI, LISTA, REGOLE

SPECIALISTI = AGENTI
DOMANDE = LISTA
PER_AGENTE = {a: [r for r in REGOLE if r.agente == a] for a in AGENTI}
PER_NOME = {r.nome: r for r in REGOLE}
DOMANDE_IN_PAROLE = {
    "key_level": "il prezzo è a un key level del grafico sopra",
    "orderflow_alto": "è allineato all'orderflow del grafico grande",
    "draw_on_liquidity": "c'è una strada libera verso l'obiettivo",
    "conferma_basso": "c'è la conferma del Model#1 sul grafico piccolo",
    "ore_giuste": "siamo nelle ore di Romeo",
}

# Il tetto del rischio: la parte del conto che un'operazione rischia al massimo. Fisso, per tutti.
PARTE_MASSIMA = 0.01
# Quante esperienze "a zero" pesano nel giudizio di una regola o di un agente: con poche esperienze
# vere la fiducia resta quella di partenza (quella di Romeo), e cambia man mano che il vivo parla.
PRUDENZA = 20
# Una regola che dal vivo sbaglia piu' di quanto indovina si spegne dopo almeno tante esperienze.
PER_SPEGNERE = 20
# Quanto deve essere d'accordo la squadra perche' il Capo entri, all'inizio (da -1 a 1). Sulle occasioni
# vere del 2023 (solo per contarle, non per giudicarle) la lista di Romeo passa circa mezza volta a
# settimana per strumento, e con 0,6 ne resta una su cinque: qualche operazione a settimana su 40
# strumenti. Poi il Capo la regola da solo, sul ritmo di Romeo.
SOGLIA_INIZIALE = 0.6
# Il ritmo di Romeo: *"You only need 1-2 of these a week"*; su tanti strumenti qualcuna in piu'.
RITMO = (1, 5)
LEZIONI_TENUTE = 300


def _stretto(x: float, basso: float, alto: float) -> float:
    return min(max(x, basso), alto)


def _erre(x: float) -> float:
    """Un risultato in R, senza che un colpo eccezionale da solo cambi tutto."""
    return _stretto(float(x), -2.0, 3.0)


@dataclass
class Memoria:
    """La memoria della squadra, su disco: esperienze, fiducia, lezioni, manuali, decisioni aperte."""

    cartella: Path
    # Per ogni regola: quante volte ha parlato dal vivo e quanto ci ha preso (somma di esito x R).
    regole: dict = field(default_factory=dict)
    # Per ogni agente: quante volte ha votato e quanto ci ha preso.
    agenti: dict = field(default_factory=dict)
    spente: list = field(default_factory=list)
    soglia: float = SOGLIA_INIZIALE
    lezioni: dict = field(default_factory=dict)
    manuali: dict = field(default_factory=dict)
    storia_manuali: list = field(default_factory=list)
    proposte: list = field(default_factory=list)
    discusse: dict = field(default_factory=dict)
    # I pesi alla revisione scorsa: per dire cosa e' cambiato in settimana.
    pesi_sabato: dict = field(default_factory=dict)
    # Le operazioni prese dalla revisione scorsa, e quanto era d'accordo la squadra sulle occasioni
    # che passavano la lista di Romeo.
    prese: int = 0
    forze: list = field(default_factory=list)

    CAMPI = ("regole", "agenti", "spente", "soglia", "lezioni", "manuali", "storia_manuali", "proposte",
             "discusse", "pesi_sabato", "prese", "forze")

    @classmethod
    def carica(cls, cartella: Path) -> "Memoria":
        f = cartella / "memoria.json"
        m = cls(cartella)
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            if "regole" not in d:
                # La memoria della squadra di prima (quella che pensava con Claude): si riparte da Romeo.
                return m
            for k in cls.CAMPI:
                if k in d:
                    setattr(m, k, d[k])
        return m

    def salva(self) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        if len(self.discusse) > 2000:
            for k in sorted(self.discusse, key=lambda k: self.discusse[k].get("quando", 0))[:-2000]:
                del self.discusse[k]
        self.storia_manuali = self.storia_manuali[-300:]
        self.proposte = self.proposte[-200:]
        f = self.cartella / "memoria.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: getattr(self, k) for k in self.CAMPI}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)

    # --- quanto credono a una regola, e ai colleghi ---

    def fiducia_regola(self, nome: str) -> float:
        """1 = quanto dice Romeo; sopra, il vivo gli ha dato ragione; sotto, torto (da 0,2 a 2)."""
        e = self.regole.get(nome, {})
        return _stretto(1.0 + 2.0 * e.get("somma", 0.0) / (e.get("n", 0) + PRUDENZA), 0.2, 2.0)

    def peso(self, nome: str) -> float:
        return PER_NOME[nome].peso * self.fiducia_regola(nome)

    def credito(self, agente: str) -> float:
        """Quanto i colleghi ascoltano un agente: da quanto ci ha preso dal vivo (da 0,3 a 2)."""
        e = self.agenti.get(agente, {})
        return _stretto(1.0 + 2.0 * e.get("somma", 0.0) / (e.get("n", 0) + PRUDENZA), 0.3, 2.0)

    def ricordi(self, agente: str, strumento: str = "") -> str:
        """Il manuale dell'agente e le sue ultime lezioni, in parole."""
        tutte = self.lezioni.get(agente, [])
        stesse = [l for l in tutte if l.get("strumento") == strumento][-3:]
        altre = [l for l in tutte if l not in stesse][-(8 - len(stesse)):]
        righe = [self.manuali[agente]] if self.manuali.get(agente) else []
        righe += [f"- [{l.get('strumento', '')} {l.get('esito', '')}] {l['lezione']}" for l in altre + stesse]
        return "\n".join(righe)

    def impara(self, agente: str, lezione: dict) -> None:
        self.lezioni.setdefault(agente, []).append(lezione)
        self.lezioni[agente] = self.lezioni[agente][-LEZIONI_TENUTE:]


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
    chiamate: int = 0

    def come_dati(self) -> dict:
        return {"entra": self.entra, "piano": self.piano, "puntata": self.puntata, "fiducia": self.fiducia,
                "pareri": self.pareri, "lista": self.lista, "secondi": round(self.secondi, 3)}


def _segno(voto: str) -> int:
    return 1 if voto == "entra" else -1 if voto == "non entrare" else 0


def _frase(motivi: list) -> str:
    return "; ".join(m[3] for m in motivi)


class Squadra:
    """La squadra: si riunisce su ogni occasione trovata dal sistema e decide da sola."""

    def __init__(self, cartella: Path):
        self.memoria = Memoria.carica(cartella)
        self.ultimo_errore = ""
        # Il giro e le lezioni (in disparte) toccano la memoria: una cosa alla volta.
        self._lucchetto = threading.Lock()

    # --- 1-3. ognuno guarda, vota, si confronta ---

    def _guarda(self, agente: str, f: dict) -> dict:
        """Il parere di un agente: le sue regole sui fatti, pesate da quanto ci crede."""
        motivi, punti, uditi = [], 0.0, []
        for r in PER_AGENTE[agente]:
            if r.nome in self.memoria.spente and not r.lista:
                continue
            try:
                esito, perche = r.guarda(f)
            except Exception:
                continue
            if esito:
                w = self.memoria.peso(r.nome)
                punti += esito * w
                motivi.append((esito * w, r.nome, int(esito), perche))
                uditi.append([r.nome, int(esito)])
        motivi.sort(key=lambda m: -abs(m[0]))
        voto = "entra" if punti >= 0.5 else "non entrare" if punti <= -0.5 else "neutro"
        fiducia = 1.0 - math.exp(-abs(punti))
        if voto == "neutro":
            testo = ("Dal mio mestiere niente di deciso" + (f": {_frase(motivi[:2])}." if motivi else ": non vedo niente che conti."))
        else:
            giusti = [m for m in motivi if (m[2] > 0) == (voto == "entra")][:2]
            contro = [m for m in motivi if (m[2] > 0) != (voto == "entra")][:1]
            testo = ("Entrerei" if voto == "entra" else "Io non entrerei") + f": {_frase(giusti)}."
            if contro:
                testo += f" Unico dubbio: {contro[0][3]}."
        return {"voto": voto, "fiducia": round(fiducia, 3), "punti": round(punti, 3), "regole": uditi,
                "ragionamento": testo}

    def _confronto(self, pareri: dict) -> list:
        """Se non sono d'accordo: chi e' incerto ascolta i colleghi con piu' credito, chi e' sicuro risponde."""
        voti = {p["voto"] for p in pareri.values() if p["voto"] != "neutro"}
        if len(voti) < 2:
            return []
        voci = []
        credito = {a: self.memoria.credito(a) for a in pareri}
        for a, p in pareri.items():
            altri = sum(credito[b] * _segno(q["voto"]) * q["fiducia"] for b, q in pareri.items() if b != a)
            mio = _segno(p["voto"]) * p["fiducia"] * credito[a]
            verso = "entra" if altri > 0 else "non entrare"
            if p["fiducia"] < 0.5 and abs(altri) > 2 * abs(mio) and p["voto"] != verso:
                chi = sorted((b for b, q in pareri.items() if b != a and q["voto"] == verso),
                             key=lambda b: -credito[b] * pareri[b]["fiducia"])[:2]
                p["secondo"] = {"voto": verso, "fiducia": round(min(abs(altri) / len(pareri), 1.0), 3), "cambio": True}
                voci.append((a, f"Cambio idea: {' e '.join(chi)} hanno visto cose che dal mio mestiere non vedo. Voto "
                                f"{'entra' if verso == 'entra' else 'non entrare'}."))
        # Chi e' piu' sicuro da una parte risponde al piu' sicuro dell'altra.
        finale = {a: p.get("secondo", p) for a, p in pareri.items()}
        per = {s: sorted((a for a in finale if _segno(finale[a]["voto"]) == s), key=lambda a: -pareri[a]["fiducia"])
               for s in (1, -1)}
        if per[1] and per[-1]:
            a, b = per[-1][0], per[1][0]
            if pareri[a]["fiducia"] >= 0.5 and "secondo" not in pareri[a]:
                voci.append((a, f"Rispondo a {b}: capisco, ma per Romeo pesa di più questo: "
                                f"{pareri[a]['ragionamento'].split(': ', 1)[-1]}"))
        return voci

    # --- 4. il Capo e il Rischio ---

    def _lista(self, f: dict) -> tuple[dict, dict]:
        """Le cinque domande di Romeo sui fatti: si' o no, e perche'."""
        risposte, perche = {}, {}
        for d in DOMANDE:
            if d == "conferma_basso":
                # Ogni occasione nasce da un Model#1 confermato sul grafico piccolo (il Grilletto).
                risposte[d], perche[d] = True, "Model#1 confermato"
                continue
            r = next(r for r in REGOLE if r.lista == d)
            try:
                esito, testo = r.guarda(f)
            except Exception:
                esito, testo = -1, "non riesco a leggerlo"
            risposte[d], perche[d] = esito > 0, testo
        return risposte, perche

    def _capo(self, f: dict, finale: dict, lista: dict, perche: dict) -> tuple[bool, float, str]:
        credito = {a: self.memoria.credito(a) for a in finale}
        totale = sum(credito[a] * _segno(p["voto"]) * p["fiducia"] for a, p in finale.items())
        forza = totale / (sum(credito.values()) or 1.0)
        a_favore = [a for a, p in finale.items() if p["voto"] == "entra"]
        contro = [a for a, p in finale.items() if p["voto"] == "non entrare"]
        no = [d for d in DOMANDE if not lista[d]]
        if no:
            discorso = ("Non entriamo. La lista di Romeo dice no: " +
                        "; ".join(f"{DOMANDE_IN_PAROLE[d]}? No, {perche[d]}" for d in no) + ".")
            return False, forza, discorso
        if forza <= self.memoria.soglia:
            discorso = (f"Non entriamo. La lista di Romeo è tutta sì, ma la squadra non è abbastanza convinta "
                        f"({len(a_favore)} a favore, {len(contro)} contro). Romeo aspetta le A+.")
            return False, forza, discorso
        principale = max(a_favore, key=lambda a: credito[a] * finale[a]["fiducia"]) if a_favore else ""
        discorso = (f"Entriamo. Le cinque domande di Romeo sono tutte sì: key level ({f.get('tipo di key level')}), "
                    f"orderflow, strada libera, Model#1, ore giuste ({f.get('ora di New York')} a New York). "
                    f"La squadra è con me: {len(a_favore)} a favore, {len(contro)} contro"
                    + (f"; seguo soprattutto {principale}" if principale else "") + ".")
        if contro:
            discorso += f" Ho sentito {' e '.join(contro)}: il resto della squadra pesa di più."
        return True, forza, discorso

    def _rischio(self, forza: float, finale: dict) -> tuple[float, str]:
        contro = sum(1 for p in finale.values() if p["voto"] == "non entrare")
        su = (forza - self.memoria.soglia) / max(1.0 - self.memoria.soglia, 1e-6)
        puntata = _stretto(0.5 + 0.5 * su, 0.5, 1.0)
        if contro:
            puntata = min(puntata, 0.75)
        tipo = "un'operazione A+" if puntata >= 0.9 else "buona, ma non perfetta" if puntata >= 0.7 else "valida, con qualche dubbio"
        return round(puntata, 2), (f"È {tipo}: metto il {puntata:.0%} della puntata massima (che è "
                                   f"l'{PARTE_MASSIMA:.0%} del conto). Romeo: mai troppa leva.")

    def riunione(self, chiave: str, strumento: str, f: dict, conto: str = "") -> Verdetto:
        """La riunione su un'occasione, coi fatti gia' letti (`fatti.py`)."""
        t0 = time.time()
        with self._lucchetto:
            pareri = {a: self._guarda(a, f) for a in SPECIALISTI}
            voci = [(a, p["ragionamento"]) for a, p in pareri.items()]
            voci += self._confronto(pareri)
            finale = {a: p.get("secondo", p) for a, p in pareri.items()}
            lista, perche = self._lista(f)
            entra, forza, discorso = self._capo(f, finale, lista, perche)
            voci.append(("Capo", discorso))
            puntata = 0.0
            if entra:
                puntata, motivo = self._rischio(forza, finale)
                voci.append(("Rischio", motivo))
            capo = {"entra": entra, "forza": round(forza, 3), "discorso": discorso, "soglia": self.memoria.soglia}
            v = Verdetto(entra, -1, puntata, round(_stretto(0.5 + forza / 2, 0.0, 1.0), 3), voci,
                         {**pareri, "Capo": capo}, lista, time.time() - t0)
            if all(lista.values()):
                self.memoria.forze = (self.memoria.forze + [round(forza, 3)])[-500:]
            if entra:
                self.memoria.prese += 1
            self.memoria.discusse[chiave] = {"quando": int(time.time()), "strumento": strumento,
                                             "fatti": {k: x for k, x in f.items() if isinstance(x, (bool, int, float, str)) or x is None},
                                             **v.come_dati()}
            self.memoria.salva()
        return v

    # --- 5. imparano dal vivo ---

    def rifletti(self, chiave: str, esito_erre: float, preso: bool, racconto: str = "") -> list[dict]:
        """L'occasione e' finita (presa o solo sulla carta): ogni regola che aveva parlato e ogni agente
        che aveva votato imparano dal risultato vero. Restituisce le lezioni (agente, lezione, regola)."""
        with self._lucchetto:
            d = self.memoria.discusse.pop(chiave, None)
            if d is None:
                return []
            r = _erre(esito_erre)
            com_e = f"{esito_erre:+.2f} R" + ("" if preso else " sulla carta")
            fatte = []
            for a, p in d.get("pareri", {}).items():
                if a == "Capo":
                    continue
                prima = {n: self.memoria.fiducia_regola(n) for n, _ in p.get("regole", [])}
                for nome, esito in p.get("regole", []):
                    if nome not in PER_NOME:
                        continue
                    e = self.memoria.regole.setdefault(nome, {"n": 0, "somma": 0.0, "giuste": 0})
                    e["n"] += 1
                    e["somma"] = round(e["somma"] + esito * r, 4)
                    e["giuste"] += int(esito * r > 0)
                voto = p.get("secondo", p).get("voto", "neutro")
                s = _segno(voto)
                if not s:
                    continue
                e = self.memoria.agenti.setdefault(a, {"n": 0, "somma": 0.0, "giuste": 0})
                e["n"] += 1
                e["somma"] = round(e["somma"] + s * r, 4)
                e["giuste"] += int(s * r > 0)
                # La regola che l'aveva convinto di piu', e cosa ne pensa adesso.
                sue = [(nome, es) for nome, es in p.get("regole", []) if nome in PER_NOME and (es > 0) == (s > 0)]
                if not sue:
                    continue
                nome = max(sue, key=lambda x: PER_NOME[x[0]].peso * prima.get(x[0], 1.0))[0]
                dopo = self.memoria.fiducia_regola(nome)
                giusto = s * r > 0
                lezione = (f"Avevo detto {voto} per «{nome}» ed è finita {com_e}: "
                           + ("avevo ragione, ci credo di più" if giusto else "avevo torto, ci credo di meno")
                           + f" (fiducia da {prima.get(nome, 1.0):.2f} a {dopo:.2f}).")
                l = {"agente": a, "lezione": lezione, "regola_di_romeo": PER_NOME[nome].romeo, "giusto": giusto}
                self.memoria.impara(a, {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                        "esito": com_e, "lezione": lezione, "regola": nome})
                fatte.append(l)
            capo = d.get("pareri", {}).get("Capo", {})
            if capo:
                entrato = bool(capo.get("entra"))
                if entrato:
                    lezione = (f"Siamo entrati ed è finita {com_e}: " +
                               ("win, journal, repeat." if r > 0 else "lose, journal, avoid."))
                else:
                    lezione = (f"Non siamo entrati; sulla carta è finita {com_e}: " +
                               ("miss, journal, catch next time." if r > 0 else "abbiamo fatto bene ad aspettare."))
                self.memoria.impara("Capo", {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                             "esito": com_e, "lezione": lezione, "regola": "lista di Romeo"})
                fatte.append({"agente": "Capo", "lezione": lezione, "regola_di_romeo": "Enter a trade?",
                              "giusto": (r > 0) == entrato})
            self.memoria.salva()
        return fatte

    # --- 6. si modificano da soli ---

    def riscrivi_manuali(self, pagelle: str = "") -> list[tuple[str, str, str]]:
        """La revisione del sabato: ognuno guarda le sue regole alla luce del vivo, spegne quelle che
        sbagliano sempre, riaccende quelle tornate buone, riscrive il manuale. Il Capo regola quanto
        e' esigente sul ritmo di Romeo. Restituisce (agente, cosa ha cambiato, proposta)."""
        cambi = []
        with self._lucchetto:
            m = self.memoria
            for a in SPECIALISTI:
                cosa = []
                for r in PER_AGENTE[a]:
                    e = m.regole.get(r.nome, {})
                    fid = m.fiducia_regola(r.nome)
                    if not r.lista and r.nome not in m.spente and e.get("n", 0) >= PER_SPEGNERE and fid <= 0.5:
                        m.spente.append(r.nome)
                        cosa.append(f"smetto di usare «{r.nome}»: dal vivo in {e['n']} occasioni ha indovinato "
                                    f"solo {e.get('giuste', 0)} volte")
                    elif r.nome in m.spente and fid >= 1.0:
                        m.spente.remove(r.nome)
                        cosa.append(f"torno a usare «{r.nome}»: dal vivo ha ripreso a funzionare")
                    else:
                        prima = m.pesi_sabato.get(r.nome, 1.0)
                        if abs(fid - prima) >= 0.1:
                            cosa.append(f"«{r.nome}» {'conta di più' if fid > prima else 'conta di meno'} "
                                        f"(da {prima:.2f} a {fid:.2f})")
                    m.pesi_sabato[r.nome] = round(fid, 4)
                manuale = self._manuale(a)
                if cosa:
                    proposta = ""
                    cr = m.credito(a)
                    if cr < 0.6:
                        proposta = f"ascoltatemi meno: dal vivo ci ho preso poco (credito {cr:.2f})"
                    self._nuovo_manuale(a, manuale, "; ".join(cosa), proposta)
                    cambi.append((a, "; ".join(cosa) + ".", proposta))
                else:
                    m.manuali[a] = manuale
            # Il Capo: Romeo prende 1-2 operazioni a settimana e aspetta le A+.
            prima = m.soglia
            forze = sorted(m.forze, reverse=True)
            if m.prese > RITMO[1] and len(forze) > RITMO[1]:
                # Troppe: a meta' strada verso l'accordo che ne avrebbe lasciate passare solo RITMO[1].
                m.soglia = round(_stretto((m.soglia + forze[RITMO[1]]) / 2, 0.0, 0.95), 3)
            elif m.prese < RITMO[0] and forze:
                # Nessuna: a meta' strada verso l'accordo della migliore della settimana.
                m.soglia = round(_stretto((m.soglia + forze[0] - 0.01) / 2, 0.0, 0.95), 3)
            if m.soglia != prima:
                cosa = (f"questa settimana siamo entrati {m.prese} volte: "
                        + ("sono più esigente" if m.soglia > prima else "sono meno esigente")
                        + f" (accordo della squadra richiesto da {prima:.2f} a {m.soglia:.2f})")
                self._nuovo_manuale("Capo", f"Entro solo con la lista di Romeo tutta sì e la squadra d'accordo oltre {m.soglia:.2f}.",
                                    cosa, "")
                cambi.append(("Capo", cosa + ".", ""))
            m.prese, m.forze = 0, []
            m.salva()
        return cambi

    def _manuale(self, a: str) -> str:
        m = self.memoria
        righe = [f"Le regole di {a}, dalla più forte:"]
        for r in sorted(PER_AGENTE[a], key=lambda r: -m.peso(r.nome)):
            e = m.regole.get(r.nome, {})
            stato = " (spenta)" if r.nome in m.spente and not r.lista else (" (lista di Romeo)" if r.lista else "")
            righe.append(f"- {r.nome}: peso {m.peso(r.nome):.2f}{stato}, dal vivo {e.get('giuste', 0)}/{e.get('n', 0)}")
        return "\n".join(righe)

    def _nuovo_manuale(self, a: str, nuovo: str, perche: str, proposta: str) -> None:
        m = self.memoria
        m.storia_manuali.append({"quando": int(time.time()), "agente": a, "prima": m.manuali.get(a, ""),
                                 "dopo": nuovo, "perche": perche})
        m.manuali[a] = nuovo
        if proposta:
            m.proposte.append({"quando": int(time.time()), "agente": a, "proposta": proposta})
