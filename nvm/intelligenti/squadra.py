"""La squadra di agenti intelligenti: dieci menti che ragionano, discutono, decidono e imparano.

Come una squadra vera (e come i sistemi multi-agente per il trading, per esempio TradingAgents):

1. **Ognuno guarda col suo mestiere.** Otto specialisti (Cacciatore, Grilletto, Livelli, Key level,
   Orario, Bias, Allineamento, Gap) leggono lo stesso dossier (`dossier.py`) con la bibbia di Romeo
   (`bibbia.md`) e il proprio manuale, e votano: entra, non entrare, neutro, con il perché e le regole
   di Romeo che hanno usato.
2. **Si confrontano.** Se non sono d'accordo, ognuno legge i pareri degli altri e risponde: puo'
   cambiare idea o tenere la sua, dicendo perché.
3. **Il Capo decide** con la lista di controllo di Romeo ("Enter a trade?": cinque domande, un solo
   no e non si entra) e sceglie il piano. **Il Rischio** dice quanto puntare, dentro tetti fissi che
   nessuna mente può superare (conto demo, parte massima del conto).
4. **Imparano da ogni operazione.** Quando un'occasione finisce (presa o solo sulla carta), la squadra
   rilegge cosa aveva detto e com'è andata e scrive una lezione per chi aveva sbagliato: *"win, journal,
   repeat; lose, journal, avoid; miss, journal, catch next time."* Le lezioni entrano nei pensieri dopo.
5. **Si modificano da sole.** Ogni settimana ogni agente riscrive il suo manuale personale (le sue
   istruzioni) con quello che ha imparato, e puo' proporre cambi al sistema. La bibbia di Romeo e i
   tetti di rischio non li puo' cambiare nessuno.

Tutto il ragionamento resta scritto (`dati/vivo/intelligenti/`): chi ha detto cosa, e perché.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nvm.intelligenti.mente import testo

SPECIALISTI = ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Allineamento", "Gap")

MESTIERI = {
    "Cacciatore": "Tu giudichi il CRT stesso: è un range pulito del timeframe giusto? Quale candela stiamo "
                  "operando (1, 2, 3)? La candela 2 ha chiuso dentro? Ci sono candele interne? La candela 1 è "
                  "spessa e arriva a un key level? È un micro CRT dentro un macro CRT? (bibbia 1, 3)",
    "Grilletto": "Tu giudichi l'entrata sulle candele piccole: c'è un vero turtle soup del lato del range? La "
                 "candela del turtle soup è spessa? La chiusura oltre il suo corpo (Model#1) è netta? C'è un FVG? "
                 "C'è la vera rottura di struttura? Siamo sotto/sopra l'apertura della candela 3 come vuole Romeo? "
                 "C'è SMT col gemello e con quali conferme? (bibbia 2, 3, 9, 11)",
    "Livelli": "Tu giudichi stop e obiettivi: lo stop è oltre l'estremo del turtle soup e non dentro la zona del "
               "tentativo fallito? Il 50% e il lato opposto sono raggiungibili prima di un livello che li blocca? "
               "Il rapporto rischio/rendimento e i costi valgono? Quale dei piani possibili sceglieresti e perché "
               "(indica il numero)? (bibbia 4, 5)",
    "Key level": "Tu giudichi il key level del grafico sopra: la manipolazione è arrivata a un key level vero "
                 "(vecchio massimo/minimo, rejection block, order block, FVG, apertura dell'ultima candela "
                 "contraria)? C'è ancora un livello non toccato oltre l'estremo, dove il prezzo andrà prima di "
                 "girare (il fondo finto)? Senza key level non si opera. (bibbia 7)",
    "Orario": "Tu giudichi il tempo: l'ora di New York della manipolazione e dell'entrata (Londra, New York, "
              "golden candle time), il giorno della settimana e dove sta il prezzo nella settimana (massimo e "
              "minimo della settimana hanno i loro giorni), se la manipolazione è alla fine della candela "
              "precedente. (bibbia 8)",
    "Bias": "Tu giudichi il bias: dove sta andando il prezzo (draw on liquidity)? Il bias di Romeo dalla "
            "chiusura/ombra delle candele prima, sul grafico del range e su quello sopra. L'operazione va nel "
            "verso dell'obiettivo del grafico grande o contro? (bibbia 6, 12)",
    "Allineamento": "Tu giudichi se i timeframe grandi (4 ore, giorno, settimana, mese) sono d'accordo con "
                    "l'operazione, e se ci sono CRT grandi armati nello stesso verso o contro. (bibbia 6, 13)",
    "Gap": "Tu giudichi i vuoti: FVG ancora aperti davanti (obiettivi che attirano il prezzo) e alle spalle "
           "(dove il prezzo può tornare contro di noi), e il gap del weekend. Un FVG sopra un vecchio massimo o "
           "sotto un vecchio minimo è un buon posto per il kiss of death. (bibbia 7, 10)",
}

VOTO = {
    "type": "object",
    "properties": {
        "voto": {"type": "string", "enum": ["entra", "non entrare", "neutro"]},
        "fiducia": {"type": "integer", "description": "0-100: quanto sei sicuro del tuo voto"},
        "regole": {"type": "array", "items": {"type": "string"},
                   "description": "le regole della bibbia di Romeo che hai usato, in poche parole"},
        "ragionamento": {"type": "string",
                         "description": "il perché, in italiano semplice, al massimo tre frasi, come in una chat fra colleghi"},
        "piano": {"type": "integer", "description": "solo per Livelli: il numero del piano che sceglieresti, -1 altrimenti"},
    },
    "required": ["voto", "fiducia", "regole", "ragionamento", "piano"],
    "additionalProperties": False,
}

CONFRONTO = {
    "type": "object",
    "properties": {
        "voto": {"type": "string", "enum": ["entra", "non entrare", "neutro"]},
        "fiducia": {"type": "integer"},
        "cambio": {"type": "boolean", "description": "hai cambiato idea rispetto al primo giro?"},
        "risposta": {"type": "string",
                     "description": "cosa rispondi ai colleghi che la pensano diversamente, al massimo due frasi"},
    },
    "required": ["voto", "fiducia", "cambio", "risposta"],
    "additionalProperties": False,
}

DOMANDE = ("key_level", "orderflow_alto", "draw_on_liquidity", "conferma_basso", "ore_giuste")
CAPO = {
    "type": "object",
    "properties": {
        "entra": {"type": "boolean"},
        "lista_di_romeo": {
            "type": "object",
            "description": "Enter a trade? Le cinque domande di Romeo: true = sì",
            "properties": {d: {"type": "boolean"} for d in DOMANDE},
            "required": list(DOMANDE),
            "additionalProperties": False,
        },
        "piano": {"type": "integer", "description": "il numero del piano scelto fra i piani possibili, -1 per quello proposto"},
        "fiducia": {"type": "integer", "description": "0-100"},
        "discorso": {"type": "string",
                     "description": "cosa dici alla squadra: la decisione e il perché, citando chi aveva ragione, al massimo quattro frasi"},
    },
    "required": ["entra", "lista_di_romeo", "piano", "fiducia", "discorso"],
    "additionalProperties": False,
}

RISCHIO = {
    "type": "object",
    "properties": {
        "puntata": {"type": "number", "description": "da 0 a 1: quanta parte della puntata massima usare"},
        "motivo": {"type": "string", "description": "il perché, al massimo due frasi"},
    },
    "required": ["puntata", "motivo"],
    "additionalProperties": False,
}

LEZIONI = {
    "type": "object",
    "properties": {
        "lezioni": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agente": {"type": "string"},
                    "lezione": {"type": "string", "description": "cosa ha capito, in una o due frasi, concreta"},
                    "regola_di_romeo": {"type": "string", "description": "la regola della bibbia che c'entra"},
                },
                "required": ["agente", "lezione", "regola_di_romeo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lezioni"],
    "additionalProperties": False,
}

MANUALE = {
    "type": "object",
    "properties": {
        "manuale": {"type": "string",
                    "description": "il tuo manuale personale riscritto: le tue regole di lavoro, al massimo 1500 caratteri"},
        "cosa_ho_cambiato": {"type": "string", "description": "in una o due frasi"},
        "proposta_al_sistema": {"type": "string",
                                "description": "un cambio al codice o alle regole del sistema che proponi, o stringa vuota"},
    },
    "required": ["manuale", "cosa_ho_cambiato", "proposta_al_sistema"],
    "additionalProperties": False,
}

# Quante lezioni recenti ogni agente rilegge prima di pensare.
LEZIONI_IN_MENTE = 12
LEZIONI_TENUTE = 300
MANUALE_MASSIMO = 1500


@dataclass
class Memoria:
    """La memoria della squadra, su disco: manuali personali, lezioni, decisioni discusse, proposte."""

    cartella: Path
    manuali: dict = field(default_factory=dict)
    lezioni: dict = field(default_factory=dict)
    discusse: dict = field(default_factory=dict)
    storia_manuali: list = field(default_factory=list)
    proposte: list = field(default_factory=list)

    @classmethod
    def carica(cls, cartella: Path) -> "Memoria":
        f = cartella / "memoria.json"
        if not f.exists():
            return cls(cartella)
        d = json.loads(f.read_text(encoding="utf-8"))
        return cls(cartella, d.get("manuali", {}), d.get("lezioni", {}), d.get("discusse", {}),
                   d.get("storia_manuali", []), d.get("proposte", []))

    def salva(self) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        # Le decisioni discusse si tengono finche' non finiscono (poi diventano lezioni), al massimo 500.
        if len(self.discusse) > 500:
            for k in sorted(self.discusse, key=lambda k: self.discusse[k].get("quando", 0))[:-500]:
                del self.discusse[k]
        f = self.cartella / "memoria.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"manuali": self.manuali, "lezioni": self.lezioni, "discusse": self.discusse,
                                   "storia_manuali": self.storia_manuali[-200:], "proposte": self.proposte[-200:]},
                                  ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)

    def ricordi(self, agente: str, strumento: str = "") -> str:
        """Il manuale personale e le lezioni recenti dell'agente (prima quelle sullo stesso strumento)."""
        tutte = self.lezioni.get(agente, [])
        stesse = [l for l in tutte if l.get("strumento") == strumento][-4:]
        altre = [l for l in tutte if l not in stesse][-(LEZIONI_IN_MENTE - len(stesse)):]
        righe = []
        if self.manuali.get(agente):
            righe.append(f"Il tuo manuale personale (scritto da te):\n{self.manuali[agente]}")
        if stesse or altre:
            righe.append("Le tue lezioni recenti (dalle operazioni vere o sulla carta):")
            for l in altre + stesse:
                righe.append(f"- [{l.get('strumento', '')} {l.get('esito', '')}] {l['lezione']} (regola: {l.get('regola', '')})")
        return "\n".join(righe) if righe else "Non hai ancora lezioni: è una delle prime operazioni."

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
    chiamate: int

    def come_dati(self) -> dict:
        return {"entra": self.entra, "piano": self.piano, "puntata": self.puntata, "fiducia": self.fiducia,
                "pareri": self.pareri, "lista": self.lista, "secondi": round(self.secondi, 1)}


def _ruolo(agente: str, compito: str, ricordi: str) -> str:
    return (f"Sei {agente}, uno specialista di una squadra di trading che segue la strategia di Romeo (la bibbia "
            f"sopra è la vostra legge). Il tuo mestiere: {MESTIERI.get(agente, '')}\n\n{ricordi}\n\n{compito}")


class Squadra:
    """La squadra: si riunisce su ogni occasione trovata dal sistema e decide."""

    def __init__(self, mente, cartella: Path):
        self.mente = mente
        self.memoria = Memoria.carica(cartella)
        # L'ultimo errore delle menti, per il registro (mai la chiave).
        self.ultimo_errore = ""
        # Piu' riunioni possono girare insieme: la memoria si scrive una alla volta.
        self._lucchetto = threading.Lock()

    def _pensa(self, blocchi, schema, sforzo="low") -> Optional[dict]:
        try:
            return self.mente.pensa(blocchi, schema, sforzo=sforzo)
        except Exception as e:
            self.ultimo_errore = f"{type(e).__name__}: {e}"[:300]
            return None

    def riunione(self, chiave: str, strumento: str, dossier: str, conto: str = "",
                 decide_da_solo: bool = False) -> Optional[Verdetto]:
        """La riunione su un'occasione: primo giro, confronto se serve, il Capo, il Rischio. None se le
        menti non rispondono (il bot allora decide come prima)."""
        t0 = time.time()
        chiamate0 = self.mente.consumo.chiamate
        base = testo(dossier, cache=True)
        compito = ("Leggi il dossier e dai il tuo voto dal tuo mestiere. Sii severo: Romeo prende 1-2 operazioni "
                   "a settimana; senza le condizioni della bibbia si vota 'non entrare'. Se il tuo mestiere non ha "
                   "abbastanza informazioni, vota 'neutro'.")
        with ThreadPoolExecutor(len(SPECIALISTI)) as pool:
            primi = dict(zip(SPECIALISTI, pool.map(
                lambda a: self._pensa([base, testo(_ruolo(a, compito, self.memoria.ricordi(a, strumento)))], VOTO),
                SPECIALISTI)))
        primi = {a: p for a, p in primi.items() if p}
        if len(primi) < len(SPECIALISTI) // 2:
            return None
        voci = [(a, p["ragionamento"]) for a, p in primi.items()]
        pareri = {a: {"primo": p} for a, p in primi.items()}
        voti = {p["voto"] for p in primi.values() if p["voto"] != "neutro"}
        if len(voti) > 1:
            # Non sono d'accordo: ognuno legge gli altri e risponde.
            riassunto = "\n".join(f"- {a}: {p['voto']} ({p['fiducia']}%): {p['ragionamento']}" for a, p in primi.items())
            def confronta(a):
                mio = primi[a]
                c = (f"Primo giro della squadra:\n{riassunto}\n\nTu avevi votato '{mio['voto']}'. Leggi i colleghi: "
                     "se hanno visto qualcosa che ti era sfuggito cambia idea, altrimenti tieni il tuo voto e spiega "
                     "perché. Rispondi a chi la pensa diversamente.")
                return self._pensa([base, testo(_ruolo(a, c, self.memoria.ricordi(a, strumento)))], CONFRONTO)
            with ThreadPoolExecutor(len(primi)) as pool:
                secondi = dict(zip(primi, pool.map(confronta, primi)))
            for a, s in secondi.items():
                if s:
                    pareri[a]["secondo"] = s
                    if s["cambio"] or s["risposta"]:
                        voci.append((a, s["risposta"]))
        finale = {a: p.get("secondo") or p["primo"] for a, p in pareri.items()}
        tavolo = "\n".join(f"- {a}: {f['voto']} ({f['fiducia']}%): "
                           f"{pareri[a]['primo']['ragionamento']}"
                           + (f" / nel confronto: {pareri[a]['secondo']['risposta']}" if "secondo" in pareri[a] else "")
                           + (f" [piano {pareri[a]['primo']['piano']}]" if a == "Livelli" else "")
                           for a, f in finale.items())
        compito_capo = (
            "Sei il Capo, il boss della squadra. Hai sentito tutti:\n" + tavolo + "\n\n"
            "Decidi tu. Prima rispondi alle cinque domande di Romeo (Enter a trade?): un solo no e non si entra. "
            "Poi scegli il piano (il numero fra i piani possibili, o -1 per quello proposto). Nel discorso spiega la "
            "decisione alla squadra in italiano semplice, dicendo di chi hai seguito il parere.\n\n"
            + self.memoria.ricordi("Capo", strumento))
        capo = self._pensa([base, testo(compito_capo)], CAPO, sforzo="medium")
        if capo is None:
            return None
        lista = capo["lista_di_romeo"]
        # La legge di Romeo, anche se il Capo si distrae: un solo no e non si entra.
        entra = bool(capo["entra"]) and all(lista.get(d, False) for d in DOMANDE)
        voci.append(("Capo", capo["discorso"]))
        puntata = 0.0
        if entra:
            compito_rischio = (
                "Sei il Rischio della squadra. Il Capo ha deciso di entrare:\n" + capo["discorso"] + "\n\n"
                f"Fiducia del Capo {capo['fiducia']}%. {conto}\n"
                "Di' quanta parte della puntata massima usare, da 0 a 1 (la puntata massima la fissa il sistema e "
                "non puoi superarla). Pensa a Romeo: niente leva eccessiva, le operazioni A+ meritano di più, "
                "quelle dubbie di meno; conta le operazioni già aperte e quanto sono legate a questa.\n\n"
                + self.memoria.ricordi("Rischio", strumento))
            r = self._pensa([base, testo(compito_rischio)], RISCHIO)
            puntata = min(max(float(r["puntata"]), 0.0), 1.0) if r else 0.5
            if r:
                voci.append(("Rischio", r["motivo"]))
        v = Verdetto(entra, int(capo["piano"]), puntata, capo["fiducia"] / 100, voci,
                     {**pareri, "Capo": capo}, lista, time.time() - t0, self.mente.consumo.chiamate - chiamate0)
        with self._lucchetto:
            self.memoria.discusse[chiave] = {"quando": int(time.time()), "strumento": strumento, **v.come_dati()}
            self.memoria.salva()
        return v

    def rifletti(self, chiave: str, esito_erre: float, preso: bool, racconto: str = "") -> list[dict]:
        """L'occasione e' finita: la squadra rilegge cosa aveva detto e scrive le lezioni per chi ha
        sbagliato (o per chi ha avuto ragione per il motivo giusto). Una chiamata sola."""
        with self._lucchetto:
            d = self.memoria.discusse.pop(chiave, None)
        if d is None:
            return []
        pareri = d.get("pareri", {})
        tavolo = []
        for a, p in pareri.items():
            if a == "Capo":
                tavolo.append(f"- Capo: {'entra' if p.get('entra') else 'non entrare'}: {p.get('discorso', '')}")
            else:
                f = p.get("secondo") or p.get("primo", {})
                tavolo.append(f"- {a}: {f.get('voto')} ({f.get('fiducia')}%): {p.get('primo', {}).get('ragionamento', '')}")
        com_e = ("guadagnato" if esito_erre > 0 else "perso") + f" {esito_erre:+.2f} R"
        compito = (
            f"Revisione dell'occasione {chiave} su {d.get('strumento')}: {'l’avete PRESA' if preso else 'NON l’avete presa (solo sulla carta)'}"
            f" ed è finita così: {com_e}. {racconto}\nCosa avevate detto:\n" + "\n".join(tavolo) + "\n\n"
            "Come Romeo col suo diario (win, journal, repeat; lose, journal, avoid; miss, journal, catch next time): "
            "scrivi una lezione concreta per ogni agente che ha sbagliato e per chi ha avuto ragione per il motivo "
            "giusto, legata a una regola della bibbia. Niente frasi generiche: cosa guarderà diversamente la "
            "prossima volta.")
        r = self._pensa([testo(compito)], LEZIONI)
        if not r:
            return []
        fatte = []
        with self._lucchetto:
            for l in r["lezioni"]:
                if l["agente"] in SPECIALISTI + ("Capo", "Rischio"):
                    self.memoria.impara(l["agente"], {"quando": int(time.time()), "strumento": d.get("strumento", ""),
                                                      "esito": com_e, "lezione": l["lezione"], "regola": l["regola_di_romeo"]})
                    fatte.append(l)
            self.memoria.salva()
        return fatte

    def riscrivi_manuali(self, pagelle: str = "") -> list[tuple[str, str, str]]:
        """Una volta a settimana: ogni agente riscrive il suo manuale personale con le sue lezioni, e
        puo' proporre un cambio al sistema. Restituisce (agente, cosa ha cambiato, proposta)."""
        cambi = []
        for a in SPECIALISTI + ("Capo", "Rischio"):
            lezioni = self.memoria.lezioni.get(a, [])[-40:]
            if not lezioni:
                continue
            compito = (
                f"Sei {a}. È la revisione del fine settimana (come il sabato di Romeo). Il tuo manuale attuale:\n"
                f"{self.memoria.manuali.get(a) or '(vuoto)'}\n\nLe tue lezioni recenti:\n"
                + "\n".join(f"- [{l.get('esito', '')}] {l['lezione']}" for l in lezioni)
                + f"\n\n{pagelle}\n\nRiscrivi il tuo manuale personale: le regole di lavoro che userai d'ora in poi, "
                "tenendo quelle che funzionano e correggendo gli errori che si ripetono. Non puoi contraddire la "
                "bibbia di Romeo né toccare i limiti di rischio. Se vedi un cambio che servirebbe al sistema "
                "(codice o regole), proponilo.")
            r = self._pensa([testo(compito)], MANUALE, sforzo="medium")
            if not r:
                continue
            nuovo = r["manuale"][:MANUALE_MASSIMO]
            with self._lucchetto:
                self._nuovo_manuale(a, nuovo, r)
            cambi.append((a, r["cosa_ho_cambiato"], r["proposta_al_sistema"]))
        with self._lucchetto:
            self.memoria.salva()
        return cambi

    def _nuovo_manuale(self, a: str, nuovo: str, r: dict) -> None:
        """Il manuale nuovo di un agente, con la storia (prima e dopo) e la sua proposta al sistema."""
        self.memoria.storia_manuali.append({"quando": int(time.time()), "agente": a,
                                            "prima": self.memoria.manuali.get(a, ""), "dopo": nuovo,
                                            "perche": r["cosa_ho_cambiato"]})
        self.memoria.manuali[a] = nuovo
        if r["proposta_al_sistema"].strip():
            self.memoria.proposte.append({"quando": int(time.time()), "agente": a, "proposta": r["proposta_al_sistema"]})
