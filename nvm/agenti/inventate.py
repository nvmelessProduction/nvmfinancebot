"""Le domande che gli agenti inventano da soli (`spec/allenamento.md`, "Le invenzioni").

Ogni specialista ha dei mattoni del suo mestiere: il Key level i massimi e i
minimi di qualunque candela o sessione, il Bias la posizione e la direzione
su qualunque timeframe, l'Orario le ore e i giorni, il Cacciatore l'ampiezza
dei range, i Livelli lo stop rispetto alla volatilita', il Grilletto la
velocita' dell'ingresso. Combinandoli inventa domande nuove, a caso, fra
quelle che non ha ancora provato. La palestra le prova: se migliorano le
prestazioni del Capo su anni mai visti diventano colonne nuove del Capo, e il
bot dal vivo le fa a ogni decisione.

Tutte le risposte sono si' (1) o no (0) e guardano solo candele gia' chiuse
prima dello scatto: niente futuro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import NEW_YORK, PASSO, TF

FILE = Path(__file__).resolve().parent.parent / "vivo" / "domande.json"
GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
NOMI_TF = {TF.H1: "l'ora", TF.H4: "le 4 ore", TF.D1: "il giorno", TF.W1: "la settimana", TF.MN: "il mese"}
ARTICOLATO = {TF.H4: "delle 4 ore", TF.D1: "del giorno", TF.W1: "della settimana", TF.MN: "del mese"}

# I mattoni di ogni agente: famiglia -> i valori possibili di ogni parametro.
MATTONI: dict[str, dict[str, dict[str, tuple]]] = {
    "Key level": {
        "livello": {"tf": ("H4", "D1", "W1", "MN"), "indietro": (1, 2, 3)},
        "sessione": {"inizio": tuple(range(0, 24)), "durata": (2, 3, 4, 6, 8)},
    },
    "Bias": {
        "posizione": {"tf": ("D1", "W1", "MN"), "frazione": (0.25, 0.5, 0.75)},
        "direzione": {"tf": ("H4", "D1", "W1", "MN"), "verso": ("a favore", "contro")},
    },
    "Orario": {
        "ora": {"inizio": tuple(range(0, 24)), "durata": (1, 2, 3, 4)},
        "giorno": {"giorno": (0, 1, 2, 3, 4)},
    },
    "Cacciatore": {
        "ampiezza": {"candele": (10, 20, 50), "volte": (0.5, 1.0, 1.5, 2.0), "verso": ("più", "meno")},
    },
    "Livelli": {
        "volatilità": {"candele": (14, 50), "volte": (0.5, 1.0, 2.0, 4.0), "verso": ("più", "meno")},
    },
    "Grilletto": {
        "velocità": {"candele": (1, 2, 3, 5, 8)},
    },
}


@dataclass(frozen=True)
class Domanda:
    agente: str
    famiglia: str
    parametri: tuple        # coppie (nome, valore), in ordine

    @property
    def p(self) -> dict:
        return dict(self.parametri)

    @property
    def chiave(self) -> str:
        return json.dumps([self.agente, self.famiglia, list(map(list, self.parametri))], ensure_ascii=False)

    @property
    def nome(self) -> str:
        p = self.p
        f = self.famiglia
        if f == "livello":
            dove = ARTICOLATO[TF(p["tf"])]
            return (f"presa l'estremo {dove} prima" if p["indietro"] == 1
                    else f"presa l'estremo {dove}, {p['indietro']} candele fa")
        if f == "sessione":
            return f"presa la sessione {p['inizio']:02d}-{(p['inizio'] + p['durata']) % 24:02d} NY"
        if f == "posizione":
            return f"entra nel {int(p['frazione'] * 100)}% buono {ARTICOLATO[TF(p['tf'])]} prima"
        if f == "direzione":
            return f"{NOMI_TF[TF(p['tf'])]} prima è {p['verso']}"
        if f == "ora":
            return f"scatta fra le {p['inizio']:02d} e le {(p['inizio'] + p['durata']) % 24:02d} NY"
        if f == "giorno":
            return f"scatta di {GIORNI[p['giorno']]}"
        if f == "ampiezza":
            return f"range {p['verso']} di {p['volte']:g} {_volte(p['volte'])} la media di {p['candele']} candele".replace(".", ",")
        if f == "volatilità":
            return f"stop {p['verso']} di {p['volte']:g} {_volte(p['volte'])} la volatilità di {p['candele']} ore".replace(".", ",")
        if f == "velocità":
            return f"Model#1 entro {p['candele']} candel{'a' if p['candele'] == 1 else 'e'} dal turtle soup"
        return f

    def come_dati(self) -> dict:
        return {"agente": self.agente, "famiglia": self.famiglia, "parametri": [list(x) for x in self.parametri]}

    @classmethod
    def da_dati(cls, d: dict) -> "Domanda":
        return cls(d["agente"], d["famiglia"], tuple(tuple(x) for x in d["parametri"]))


def _volte(x: float) -> str:
    return "volta" if x == 1 else "volte"


def inventa(agente: str, rng: np.random.Generator, gia: set[str], quante: int = 2, tentativi: int = 200) -> list[Domanda]:
    """Nuove domande dell'agente, mai provate prima."""
    famiglie = MATTONI.get(agente, {})
    nuove: list[Domanda] = []
    for _ in range(tentativi):
        if len(nuove) >= quante or not famiglie:
            break
        famiglia = list(famiglie)[int(rng.integers(len(famiglie)))]
        parametri = tuple((k, v[int(rng.integers(len(v)))]) for k, v in famiglie[famiglia].items())
        parametri = tuple((k, v.item() if hasattr(v, "item") else v) for k, v in parametri)
        d = Domanda(agente, famiglia, parametri)
        if d.chiave not in gia and all(d.chiave != x.chiave for x in nuove):
            nuove.append(d)
    return nuove


# --- Le risposte ------------------------------------------------------------------------

@dataclass
class Contesto:
    """Le candele di uno strumento che servono alle domande, dalle ore: chiuse entro `fine`."""

    ore: Candele
    candele: dict

    @classmethod
    def da(cls, ore: Minuti, fine: int) -> "Contesto":
        tutte = {tf: costruisci(ore, tf).chiuse_entro(fine) for tf in (TF.H4, TF.D1, TF.W1, TF.MN)}
        return cls(costruisci(ore, TF.H1).chiuse_entro(fine), tutte)


def _prima(c: Candele, t: int, indietro: int = 1) -> int:
    """L'indice della candela chiusa `indietro` volte prima di t (-1 se non c'e')."""
    k = int(np.searchsorted(c.fine, t, side="right")) - indietro
    return k if k >= 0 else -1


def _ora_ny(t: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(t, tz=NEW_YORK)
    return d.hour, d.weekday()


def rispondi(domanda: Domanda, r, ctx: Contesto) -> float:
    """La risposta a una domanda per un'operazione (un `Risultato` con il suo scatto)."""
    s = r.scatto
    crt = s.crt
    short = crt.verso is Verso.SHORT
    p = domanda.p
    f = domanda.famiglia
    t = s.quando
    if f in ("livello", "sessione"):
        estremo = crt.estremo_a(t)
        if estremo is None:
            return 0.0
        if f == "livello":
            c = ctx.candele[TF(p["tf"])]
            k = _prima(c, s.turtle_soup_inizio, p["indietro"])
            if k < 0:
                return 0.0
            livello = c.bid[k, MASSIMO] if short else c.bid[k, MINIMO]
        else:
            # L'ultima sessione [inizio, inizio + durata) di New York finita prima del turtle soup.
            d = datetime.fromtimestamp(s.turtle_soup_inizio, tz=NEW_YORK)
            fine = d.replace(hour=(p["inizio"] + p["durata"]) % 24, minute=0, second=0, microsecond=0)
            if fine > d:
                fine -= timedelta(days=1)
            i0, i1 = np.searchsorted(ctx.ore.inizio, [int((fine - timedelta(hours=p["durata"])).timestamp()),
                                                      int(fine.timestamp())])
            if i1 <= i0:
                return 0.0
            livello = ctx.ore.bid[i0:i1, MASSIMO].max() if short else ctx.ore.bid[i0:i1, MINIMO].min()
        return float(estremo > livello if short else estremo < livello)
    if f == "posizione":
        c = ctx.candele[TF(p["tf"])]
        k = _prima(c, t)
        if k < 0:
            return 0.0
        alto, basso = c.bid[k, MASSIMO], c.bid[k, MINIMO]
        if alto <= basso:
            return 0.0
        dove = (r.ingresso - basso) / (alto - basso)
        return float(dove < p["frazione"] if not short else dove > 1 - p["frazione"])
    if f == "direzione":
        c = ctx.candele[TF(p["tf"])]
        k = _prima(c, t)
        if k < 0:
            return 0.0
        su = c.bid[k, CHIUSURA] > c.bid[k, APERTURA]
        a_favore = su != short
        return float(a_favore if p["verso"] == "a favore" else not a_favore)
    if f == "ora":
        h, _ = _ora_ny(t)
        return float((h - p["inizio"]) % 24 < p["durata"])
    if f == "giorno":
        return float(_ora_ny(t)[1] == p["giorno"])
    if f == "ampiezza":
        c = ctx.candele.get(crt.alto_tf) if crt.alto_tf is not TF.H1 else ctx.ore
        if c is None:
            return 0.0
        k = int(np.searchsorted(c.inizio, crt.range_inizio))
        if k < p["candele"]:
            return 0.0
        media = float(np.mean(c.bid[k - p["candele"]:k, MASSIMO] - c.bid[k - p["candele"]:k, MINIMO]))
        rapporto = (crt.crt_high - crt.crt_low) / media if media > 0 else 0.0
        return float(rapporto > p["volte"] if p["verso"] == "più" else rapporto < p["volte"])
    if f == "volatilità":
        k = _prima(ctx.ore, t)
        if k < p["candele"]:
            return 0.0
        media = float(np.mean(ctx.ore.bid[k - p["candele"] + 1:k + 1, MASSIMO] - ctx.ore.bid[k - p["candele"] + 1:k + 1, MINIMO]))
        rapporto = r.rischio / media if media > 0 else 0.0
        return float(rapporto > p["volte"] if p["verso"] == "più" else rapporto < p["volte"])
    if f == "velocità":
        return float((t - s.turtle_soup_inizio) / PASSO[r.basso_tf] <= p["candele"] + 1)
    return 0.0


def rispondi_tutte(domande: list[Domanda], r, ctx: Optional[Contesto]) -> list[float]:
    if ctx is None:
        return [0.0] * len(domande)
    return [rispondi(d, r, ctx) for d in domande]


# --- Quelle tenute ----------------------------------------------------------------------

def tenute(percorso: Path = FILE) -> list[Domanda]:
    """Le invenzioni entrate nel Capo, nell'ordine in cui sono entrate."""
    if not percorso.exists():
        return []
    return [Domanda.da_dati(d) for d in json.loads(percorso.read_text(encoding="utf-8")).get("domande", [])]


def salva(domande: list[Domanda], percorso: Path = FILE) -> None:
    percorso.write_text(json.dumps({"domande": [d.come_dati() for d in domande]}, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")


def impronta(domande: list[Domanda]) -> str:
    """Un nome corto per un elenco di domande: le tabelle salvate lo portano nel nome."""
    if not domande:
        return ""
    import hashlib
    return "-i" + hashlib.sha1("|".join(d.chiave for d in domande).encode("utf-8")).hexdigest()[:6]
