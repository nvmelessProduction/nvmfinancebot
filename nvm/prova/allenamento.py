"""L'allenamento degli agenti (`spec/allenamento.md`): ognuno impara dai suoi errori.

Ogni settimana, per ogni specialista:

1. **esperienza**: rilegge le sue operazioni dei vent'anni e dice dove va
   meglio e dove peggio (`diagnosi`);
2. **ipotesi**: prova da solo a girare di un passo ognuna delle sue manopole,
   dentro il mansionario (`nvm/agenti/manopole.py`);
3. **prova**: il Capo si riallena anno per anno con la modifica, e si guarda
   il guadagno settimana per settimana contro quello di oggi (`esame`);
4. **paletti**: la modifica non vale se fa scadere piu' operazioni, se le
   allunga troppo, se allarga il drawdown o se ci allontana da Romeo;
5. **decisione**: la tiene solo se vince con un margine che cresce col numero
   di prove fatte quella settimana. Se piu' agenti vincono, si riprova la
   squadra insieme: le modifiche devono andare d'accordo;
6. **memoria**: ogni prova resta in `nvm/vivo/allenamento.json`; una prova
   scartata non si ripete per `RIPOSO` settimane.

I colleghi si parlano: di ogni prova si vede anche chi ci guadagna e chi ci
perde fra gli altri agenti (`effetti`), e lo dice il rapporto.
"""

from __future__ import annotations

import json
import multiprocessing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from nvm.agenti import manopole
from nvm.agenti.capo import COLONNE, Capo, pesi_per_eta
from nvm.prova.base import SETTIMANA
from nvm.prova.cammino import Tabella, _anno, cammino, costruisci_tabella

MEMORIA = manopole.FILE.parent / "allenamento.json"
# Il confronto: il guadagno delle scelte del Capo settimana per settimana, con
# e senza la modifica, ricampionato a blocchi di un trimestre.
BLOCCO = 13
RICAMPIONI = 2000
# L'errore ammesso prima della correzione per le prove fatte: con k prove si divide per k.
ALFA = 0.10
# In quale parte degli anni la modifica deve fare meglio.
ANNI = 0.7
# I paletti.
PIU_SCADUTE = 0.01          # operazioni chiuse dal tetto di sicurezza: al massimo un punto in piu'
PIU_LUNGHE = 1.5            # durata mediana: al massimo una volta e mezza
PIU_DRAWDOWN = 1.1          # drawdown: al massimo il 10% in piu'
MENO_ROMEO = 1              # entrate di Romeo ritrovate dal Capo nel 2023: al massimo una in meno
# Settimane prima di riprovare una modifica scartata.
RIPOSO = 8

# I segnali di ogni agente, dalle colonne del Capo: per la diagnosi e per gli effetti sui colleghi.
_C = COLONNE.index


def _gruppi() -> dict[str, dict[str, Callable[[np.ndarray], np.ndarray]]]:
    coppia_mensile = lambda x: (x[:, _C("coppia W1-H4")] == 0) & (x[:, _C("coppia D1-H1")] == 0) & (x[:, _C("coppia H4-M15")] == 0)
    return {
        "Cacciatore": {
            "mensile → giornaliero": coppia_mensile,
            "settimanale → 4 ore": lambda x: x[:, _C("coppia W1-H4")] == 1,
            "giornaliero → 1 ora": lambda x: x[:, _C("coppia D1-H1")] == 1,
            "dentro un CRT più grande": lambda x: x[:, _C("dentro un CRT più grande")] == 1,
        },
        "Grilletto": {
            "primo colpo": lambda x: (x[:, _C("secondo colpo")] == 0) & (x[:, _C("terzo colpo")] == 0),
            "secondo colpo": lambda x: x[:, _C("secondo colpo")] == 1,
            "terzo colpo": lambda x: x[:, _C("terzo colpo")] == 1,
            "liquidità presa prima": lambda x: x[:, _C("liquidità presa prima")] == 1,
        },
        "Livelli": {
            "stop stretto (meno di metà range)": lambda x: x[:, _C("stop su ampiezza")] < 0.5,
            "stop largo (oltre metà range)": lambda x: x[:, _C("stop su ampiezza")] >= 0.5,
            "primo obiettivo sotto 1 R": lambda x: x[:, _C("RR1")] < 1,
            "primo obiettivo oltre 2 R": lambda x: x[:, _C("RR1")] >= 2,
        },
        "Key level": {
            "massimo preso": lambda x: x[:, _C("key level: massimo preso")] == 1,
            "arriva al massimo": lambda x: x[:, _C("key level: arriva al massimo")] == 1,
            "rejection block": lambda x: x[:, _C("key level: rejection block")] == 1,
            "FVG": lambda x: x[:, _C("key level: fvg")] == 1,
            "nessuna zona": lambda x: x[:, :4].sum(1) == 0,
        },
        "Orario": {
            "ora di Londra di Romeo": lambda x: x[:, _C("ora di Romeo: Londra")] == 1,
            "ora di New York di Romeo": lambda x: x[:, _C("ora di Romeo: New York")] == 1,
            "fuori dalle ore di Romeo": lambda x: (x[:, _C("ora di Romeo: Londra")] == 0) & (x[:, _C("ora di Romeo: New York")] == 0),
        },
        "Bias": {
            "range a favore": lambda x: x[:, _C("bias range a favore")] == 1,
            "range contro": lambda x: x[:, _C("bias range contro")] == 1,
            "sopra a favore": lambda x: x[:, _C("bias sopra a favore")] == 1,
            "sopra contro": lambda x: x[:, _C("bias sopra contro")] == 1,
            "a sconto": lambda x: x[:, _C("a sconto sulla settimana")] == 1,
        },
    }


GRUPPI = _gruppi()


@dataclass
class Prova:
    """Come va la squadra con certi valori delle manopole: le scelte del Capo, anno per anno."""

    valori: dict
    serie: np.ndarray               # R delle scelte del Capo per settimana, dalla prima giudicata all'ultima
    prima_settimana: int
    n: int
    r_medio: float
    scadute: float
    durata: float                   # giorni, mediana
    drawdown: float                 # R
    # Per agente e segnale: [operazioni, R totale] delle scelte del Capo.
    segnali: dict = field(default_factory=dict)
    romeo: Optional[int] = None

    @property
    def per_settimana(self) -> float:
        return float(self.serie.mean())


@dataclass
class Esame:
    media: float                    # R in piu' a settimana
    basso: float
    alto: float
    anni: float                     # quota di anni in cui fa meglio
    paletti: list[str]

    @property
    def passa(self) -> bool:
        return self.basso > 0 and self.anni >= ANNI and not self.paletti


# --- La prova di un insieme di valori -------------------------------------------------

def _settimane(primo: int, ultimo: int) -> tuple[int, int]:
    dal = int(datetime(primo, 1, 1, tzinfo=timezone.utc).timestamp()) // SETTIMANA
    al = int(datetime(ultimo + 1, 1, 1, tzinfo=timezone.utc).timestamp()) // SETTIMANA
    return dal, al


def misura(t: Tabella, valori: dict, primo: int, ultimo: int) -> Prova:
    """Il Capo anno per anno sulla tabella, e le sue scelte settimana per settimana."""
    c = cammino(t, primo, ultimo)
    s = c.scelte
    w0, w1 = _settimane(primo, ultimo)
    settimane = t.quando[s] // SETTIMANA - w0
    serie = np.bincount(settimane, weights=t.erre[s], minlength=w1 - w0)[: w1 - w0]
    cumulata = np.cumsum(serie)
    drawdown = float((np.maximum.accumulate(cumulata) - cumulata).max()) if len(cumulata) else 0.0
    x = t.x[s]
    segnali = {agente: {nome: [int(m.sum()), float(t.erre[s][m].sum())] for nome, f in g.items() for m in [f(x)]}
               for agente, g in GRUPPI.items()}
    scadute = float(t.scaduta[s].mean()) if t.scaduta is not None and s.any() else 0.0
    return Prova(valori, serie, w0, int(s.sum()), float(t.erre[s].mean()) if s.any() else 0.0, scadute,
                 float(np.median(t.chiusa[s] - t.quando[s]) / 86400) if s.any() else 0.0, drawdown, segnali)


def esame(oggi: Prova, nuova: Prova, prove: int, seme: int = 0) -> Esame:
    """La modifica fa guadagnare di piu', con abbastanza certezza, senza passare i paletti?"""
    d = nuova.serie - oggi.serie
    n = len(d)
    rng = np.random.default_rng(seme)
    blocchi = int(np.ceil(n / BLOCCO))
    inizi = rng.integers(0, n, size=(RICAMPIONI, blocchi))
    indici = (inizi[:, :, None] + np.arange(BLOCCO)[None, None, :]).reshape(RICAMPIONI, -1)[:, :n] % n
    medie = d[indici].mean(1)
    livello = ALFA / max(prove, 1)
    basso, alto = np.quantile(medie, [livello / 2, 1 - livello / 2])
    anni = _anno(np.arange(n) * SETTIMANA + oggi.prima_settimana * SETTIMANA)
    per_anno = {a: d[anni == a].sum() for a in np.unique(anni)}
    quota = float(np.mean([v > 0 for v in per_anno.values()]))
    paletti = []
    if nuova.scadute > oggi.scadute + PIU_SCADUTE:
        paletti.append(f"più operazioni scadute ({oggi.scadute:.1%} → {nuova.scadute:.1%})")
    if nuova.durata > oggi.durata * PIU_LUNGHE:
        paletti.append(f"operazioni troppo lunghe ({oggi.durata:.1f} → {nuova.durata:.1f} giorni)")
    if nuova.drawdown > oggi.drawdown * PIU_DRAWDOWN:
        paletti.append(f"drawdown più profondo ({oggi.drawdown:.0f} → {nuova.drawdown:.0f} R)")
    if oggi.romeo is not None and nuova.romeo is not None and nuova.romeo < oggi.romeo - MENO_ROMEO:
        paletti.append(f"ci allontana da Romeo ({oggi.romeo} → {nuova.romeo} sue entrate ritrovate)")
    return Esame(float(d.mean()), float(basso), float(alto), quota, paletti)


def effetti(oggi: Prova, nuova: Prova, escluso: str) -> tuple[Optional[str], Optional[str]]:
    """Fra i colleghi, il segnale che ci guadagna di piu' e quello che ci perde di piu' (in R totali)."""
    variazioni = []
    for agente, g in nuova.segnali.items():
        if agente == escluso:
            continue
        for nome, (n, r) in g.items():
            n0, r0 = oggi.segnali.get(agente, {}).get(nome, [0, 0.0])
            if max(n, n0) >= 200:
                variazioni.append((r - r0, agente, nome))
    if not variazioni:
        return None, None
    su, giu = max(variazioni), min(variazioni)
    testo = lambda v: f"{v[1]} con «{v[2]}» ({v[0]:+.0f} R)".replace("-", "−")
    return (testo(su) if su[0] > 0 else None), (testo(giu) if giu[0] < 0 else None)


def diagnosi(agente: str, oggi: Prova) -> str:
    """Dove l'agente va meglio e peggio, fra le scelte del Capo dei vent'anni."""
    voci = [(r / n, nome, n) for nome, (n, r) in oggi.segnali.get(agente, {}).items() if n >= 200]
    if len(voci) < 2:
        return "pochi casi per dire dove sbaglio"
    meglio, peggio = max(voci), min(voci)
    v = _r
    return f"vado meglio con «{meglio[1]}» ({v(meglio[0])} R a operazione) e peggio con «{peggio[1]}» ({v(peggio[0])} R)"


# --- La squadra in palestra -----------------------------------------------------------

_BASI: dict = {}
_IMPOSTAZIONI: dict = {}


def _valuta(valori: dict) -> Prova:
    """In un processo a parte: mette i valori, rifa' la tabella, misura. Se chiesto, conta Romeo."""
    manopole.applica(valori)
    imp = _IMPOSTAZIONI
    t = costruisci_tabella(_BASI, imp["coppie"], imp["dal"], imp["al"])
    p = misura(t, valori, imp["primo"], imp["ultimo"])
    if imp.get("romeo"):
        p.romeo = imp["romeo"](t)
    return p


def prova_tutti(valori: list[dict], basi: dict, impostazioni: dict, processi: int = 4) -> list[Prova]:
    global _BASI, _IMPOSTAZIONI
    _BASI, _IMPOSTAZIONI = basi, impostazioni
    if processi <= 1 or len(valori) == 1:
        return [_valuta(v) for v in valori]
    with multiprocessing.get_context("fork").Pool(processi) as pool:
        return pool.map(_valuta, valori)


def _con(valori: dict, agente: str, nome: str, v: Any) -> dict:
    nuovi = {a: dict(p) for a, p in valori.items()}
    nuovi.setdefault(agente, {})[nome] = v
    return nuovi


def _chiave(agente: str, nome: str, da: Any, a: Any) -> str:
    return json.dumps([agente, nome, da, a], ensure_ascii=False)


def proposte(valori: dict, memoria: list[dict], settimana: int) -> list[tuple[str, str, Any, Any]]:
    """Ogni agente prova un passo su ogni sua manopola, tranne le prove scartate da poco."""
    scartate = {p["chiave"] for p in memoria if p["esito"] == "scartata" and settimana - p["numero"] < RIPOSO}
    fuori = []
    for m in manopole.MANOPOLE:
        da = valori[m.agente][m.nome]
        for a in m.vicini(da):
            if _chiave(m.agente, m.nome, da, a) not in scartate:
                fuori.append((m.agente, m.nome, da, a))
    return fuori


@dataclass
class Esito:
    rapporto: str
    valori: dict
    cambiato: bool
    prove: list[dict]


def _r(x: float) -> str:
    return f"{x:+.3f}".replace(".", ",").replace("-", "−")


def _v(x: Any) -> str:
    if isinstance(x, list):
        return "–".join(map(str, x))
    return str(x).replace(".", ",")


def allena(basi: dict, impostazioni: dict, memoria: list[dict], adesso: int,
           dire: Callable[[str], None] = print, processi: int = 4) -> Esito:
    """Una settimana di palestra: prove, esami, decisioni e rapporto."""
    settimana = adesso // SETTIMANA
    etichetta = datetime.fromtimestamp(adesso, tz=timezone.utc).strftime("%G-S%V")
    valori = manopole.attuali()
    elenco = proposte(valori, memoria, settimana)
    dire(f"{len(elenco)} prove, più la squadra di oggi")
    senza_romeo = {k: v for k, v in impostazioni.items() if k != "romeo"}
    oggi = prova_tutti([valori], basi, impostazioni, 1)[0]
    candidate = prova_tutti([_con(valori, a, n, v) for a, n, _, v in elenco], basi, senza_romeo, processi)
    k = max(len(elenco), 1)
    esami = [esame(oggi, c, k) for c in candidate]

    # Il migliore di ogni agente fra quelli che passano, poi il controllo su Romeo.
    vincitori: dict[str, int] = {}
    for i, ((agente, *_), e) in enumerate(zip(elenco, esami)):
        if e.passa and (agente not in vincitori or e.media > esami[vincitori[agente]].media):
            vincitori[agente] = i
    scelti = list(vincitori.values())
    finali = valori
    squadra = None
    finale_romeo = None
    if scelti:
        insieme = valori
        for i in scelti:
            agente, nome, _, v = elenco[i]
            insieme = _con(insieme, agente, nome, v)
        prove_finali = [insieme] + ([_con(valori, *elenco[i][:2], elenco[i][3]) for i in scelti] if len(scelti) > 1 else [])
        risultati = prova_tutti(prove_finali, basi, impostazioni, processi)
        squadra = esame(oggi, risultati[0], k + len(scelti))
        if squadra.passa:
            finali = insieme
            finale_romeo = risultati[0].romeo
        else:
            # Insieme non vanno d'accordo: resta la sola modifica migliore, se passa ancora con Romeo.
            singoli = risultati[1:] if len(scelti) > 1 else risultati
            migliore = max(range(len(singoli)), key=lambda j: esame(oggi, singoli[j], k).media)
            if esame(oggi, singoli[migliore], k).passa:
                finale_romeo = singoli[migliore].romeo
                i = scelti[migliore]
                finali = _con(valori, elenco[i][0], elenco[i][1], elenco[i][3])
                scelti = [i]
            else:
                scelti = []

    tenute = set(scelti) if finali is not valori else set()
    registro = []
    righe = [f"🏋️ Allenamento della settimana {etichetta}",
             "Ognuno ha riletto i suoi vent'anni e ha provato da solo a migliorarsi. Una modifica resta "
             f"solo se fa guadagnare di più con certezza, contro {k} prove fatte insieme.", ""]
    for agente in manopole.AGENTI:
        righe.append(f"• {agente}: {diagnosi(agente, oggi)}.")
        for i, (a, nome, da, v) in enumerate(elenco):
            if a != agente:
                continue
            e = esami[i]
            tenuta = i in tenute
            if tenuta:
                giudizio = "✅ la tengo"
            elif e.basso <= 0 or e.anni < ANNI:
                giudizio = "❌ non basta"
            elif e.paletti:
                giudizio = "❌ no: " + "; ".join(e.paletti)
            else:
                giudizio = "❌ da sola sì, ma non va d'accordo con le modifiche dei colleghi"
            su, giu = effetti(oggi, candidate[i], agente)
            dopo = "".join([f" Ci guadagna {su}." if su and tenuta else "", f" Ci perde {giu}." if giu and tenuta else ""])
            righe.append(f"  ↳ {nome} {_v(da)} → {_v(v)}: {_r(e.media)} R a settimana "
                         f"(fra {_r(e.basso)} e {_r(e.alto)}), meglio in {e.anni:.0%} degli anni. {giudizio}.{dopo}")
            registro.append({"settimana": etichetta, "numero": settimana, "agente": a, "manopola": nome, "da": da, "a": v,
                             "chiave": _chiave(a, nome, da, v), "esito": "tenuta" if tenuta else "scartata",
                             "media": e.media, "basso": e.basso, "alto": e.alto, "anni": e.anni, "paletti": e.paletti})
    righe.append("")
    if tenute:
        cambi = ", ".join(f"{elenco[i][0]} ({elenco[i][1]} {_v(elenco[i][2])} → {_v(elenco[i][3])})" for i in sorted(tenute))
        guadagno = squadra.media if squadra is not None and squadra.passa else esami[scelti[0]].media
        righe.append(f"Capo: da oggi cambiano {cambi}. Mi riaddestro sulle operazioni nuove. "
                     f"Sui vent'anni la squadra faceva {_r(oggi.per_settimana)} R a settimana; "
                     f"con le novità {_r(oggi.per_settimana + guadagno)}."
                     + (f" Le entrate di Romeo del 2023 che ritrovo: {oggi.romeo} → {finale_romeo}." if finale_romeo is not None else ""))
    else:
        righe.append(f"Capo: questa settimana nessuna modifica ha battuto la squadra di oggi "
                     f"({_r(oggi.per_settimana)} R a settimana sui vent'anni). Si resta così, e si riprova con altro.")
    return Esito("\n".join(righe), finali, bool(tenute), registro)


# --- Il paletto di Romeo ----------------------------------------------------------------

def ritrovate_da_romeo(t: Tabella, radice: Path, catalogo: Path) -> int:
    """Quante entrate di Romeo del 2023 il Capo ritrova (entro meta' del suo rischio), allenato
    fino al 2022 su questa tabella: lo stesso conto di `romeo.py` ("il Capo senza la voce di Romeo")."""
    from nvm.dati.minuti import carica_periodo
    from nvm.prova.romeo import candidati, confronta, leggi

    inizio, fine = (int(datetime(a, 1, 1, tzinfo=timezone.utc).timestamp()) for a in (2023, 2024))
    prima = t.chiusa < inizio
    capo = Capo.allena(t.x[prima], t.tp1[prima], t.tp2[prima], pesi=pesi_per_eta(t.chiusa[prima], inizio))
    entrate = [e for e in leggi(catalogo) if e.periodo == "studio" and e.strumento in _BASI]
    trovate = 0
    for strumento in sorted({e.strumento for e in entrate}):
        minuti = carica_periodo(radice / "minuti", strumento, inizio, fine)
        ops, x = candidati(_BASI[strumento], minuti, inizio, fine)
        if not ops:
            continue
        atteso = capo.valore_atteso(x, np.array([o.rr1 for o in ops]), np.array([o.rr2 for o in ops]),
                                    np.array([o.costo_erre for o in ops]))
        prese = [o for o, a in zip(ops, atteso) if a > 0]
        trovate += sum(1 for e in entrate if e.strumento == strumento and (c := confronta(e, prese)) and c[0].ritrovata)
    return trovate


# --- Memoria --------------------------------------------------------------------------

def leggi_memoria(percorso: Path = MEMORIA) -> dict:
    if not percorso.exists():
        return {"prove": [], "ultimo": {}}
    return json.loads(percorso.read_text(encoding="utf-8"))


def salva_memoria(memoria: dict, percorso: Path = MEMORIA) -> None:
    percorso.write_text(json.dumps(memoria, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
