"""L'allenamento degli agenti (`spec/allenamento.md`): ognuno impara dai suoi errori.

Ogni settimana, per ogni specialista:

1. **esperienza**: rilegge le sue operazioni dei vent'anni e dice dove va
   meglio e dove peggio (`diagnosi`);
2. **ipotesi**: prova da solo a spostare di un passo ognuna delle sue
   manopole, in su o in giu', senza recinti (`nvm/agenti/manopole.py`);
3. **prova**: il Capo si riallena anno per anno con la modifica;
4. **esame**: la modifica resta se migliora le **prestazioni**, non il
   guadagno (l'utente, 25/09/2026): la qualita' di ogni operazione scelta
   dal Capo, cioe' il rendimento medio diviso per quanto oscilla. Non cambia
   con quanto si punta ne' con quante operazioni si aprono; uno stop enorme
   la porta verso zero. Deve migliorare con certezza (un margine che cresce
   col numero di prove della settimana) e nella maggior parte degli anni.
   Nessun divieto: scadute, durata, drawdown, operazioni, entrate di Romeo
   ritrovate e guadagno si scrivono nel rapporto, ma non decidono;
5. **i colleghi**: se piu' agenti migliorano, si riprova la squadra insieme;
   di ogni modifica si vede chi ci guadagna e chi ci perde fra i colleghi;
6. **memoria**: ogni prova resta in `nvm/vivo/allenamento.json`; una prova
   scartata non si ripete per `RIPOSO` settimane.
"""

from __future__ import annotations

import json
import multiprocessing
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from nvm.agenti import capo as il_capo, inventate, manopole
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
# Quante domande nuove inventa ogni agente ogni settimana.
IDEE_PER_AGENTE = 2
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
    quadrati: np.ndarray            # somma dei quadrati degli R, per settimana
    conteggi: np.ndarray            # operazioni scelte, per settimana
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

    @property
    def qualita(self) -> float:
        return _qualita(self.serie.sum(), self.quadrati.sum(), self.conteggi.sum())


def _qualita(somma, quadrati, n):
    """Il rendimento medio di un'operazione diviso per quanto oscilla (in R)."""
    n = np.maximum(n, 1)
    media = somma / n
    varianza = np.maximum(quadrati / n - media ** 2, 1e-12)
    return media / np.sqrt(varianza)


@dataclass
class Esame:
    media: float                    # qualita' in piu'
    basso: float
    alto: float
    anni: float                     # quota di anni in cui fa meglio
    # Quello che cambia, scritto nel rapporto ma non decide.
    note: list[str] = field(default_factory=list)

    @property
    def passa(self) -> bool:
        return self.basso > 0 and self.anni >= ANNI


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
    quadrati = np.bincount(settimane, weights=t.erre[s] ** 2, minlength=w1 - w0)[: w1 - w0]
    conteggi = np.bincount(settimane, minlength=w1 - w0)[: w1 - w0].astype(float)
    cumulata = np.cumsum(serie)
    drawdown = float((np.maximum.accumulate(cumulata) - cumulata).max()) if len(cumulata) else 0.0
    x = t.x[s]
    segnali = {agente: {nome: [int(m.sum()), float(t.erre[s][m].sum())] for nome, f in g.items() for m in [f(x)]}
               for agente, g in GRUPPI.items()}
    scadute = float(t.scaduta[s].mean()) if t.scaduta is not None and s.any() else 0.0
    return Prova(valori, serie, w0, quadrati, conteggi, int(s.sum()), float(t.erre[s].mean()) if s.any() else 0.0, scadute,
                 float(np.median(t.chiusa[s] - t.quando[s]) / 86400) if s.any() else 0.0, drawdown, segnali)


def esame(oggi: Prova, nuova: Prova, prove: int, seme: int = 0) -> Esame:
    """La modifica migliora la qualita' delle operazioni, con abbastanza certezza?

    Si ricampionano le stesse settimane per tutte e due (a blocchi di un
    trimestre): la differenza di qualita' e' appaiata, stesso mercato."""
    n = len(oggi.serie)
    rng = np.random.default_rng(seme)
    blocchi = int(np.ceil(n / BLOCCO))
    inizi = rng.integers(0, n, size=(RICAMPIONI, blocchi))
    indici = (inizi[:, :, None] + np.arange(BLOCCO)[None, None, :]).reshape(RICAMPIONI, -1)[:, :n] % n
    q = lambda p: _qualita(p.serie[indici].sum(1), p.quadrati[indici].sum(1), p.conteggi[indici].sum(1))
    differenze = q(nuova) - q(oggi)
    livello = ALFA / max(prove, 1)
    basso, alto = np.quantile(differenze, [livello / 2, 1 - livello / 2])
    anni = _anno(np.arange(n) * SETTIMANA + oggi.prima_settimana * SETTIMANA)
    meglio = []
    for a in np.unique(anni):
        m = anni == a
        # Un anno senza operazioni vale zero: operare bene dove prima non si operava e' meglio.
        if oggi.conteggi[m].sum() or nuova.conteggi[m].sum():
            meglio.append(_qualita(nuova.serie[m].sum(), nuova.quadrati[m].sum(), nuova.conteggi[m].sum())
                          > _qualita(oggi.serie[m].sum(), oggi.quadrati[m].sum(), oggi.conteggi[m].sum()))
    note = []
    if abs(nuova.scadute - oggi.scadute) >= 0.005:
        note.append(f"scadute {oggi.scadute:.1%} → {nuova.scadute:.1%}")
    if abs(nuova.durata - oggi.durata) >= 0.2 * max(oggi.durata, 0.1):
        note.append(f"durata {oggi.durata:.1f} → {nuova.durata:.1f} giorni")
    if abs(nuova.drawdown - oggi.drawdown) >= 0.1 * max(oggi.drawdown, 1):
        note.append(f"drawdown {oggi.drawdown:.0f} → {nuova.drawdown:.0f} R")
    if abs(nuova.n - oggi.n) >= 0.1 * max(oggi.n, 1):
        note.append(f"operazioni {oggi.n} → {nuova.n}")
    if oggi.romeo is not None and nuova.romeo is not None and nuova.romeo != oggi.romeo:
        note.append(f"entrate di Romeo ritrovate {oggi.romeo} → {nuova.romeo}")
    return Esame(float(nuova.qualita - oggi.qualita), float(basso), float(alto),
                 float(np.mean(meglio)) if meglio else 0.0, [x.replace(".", ",") for x in note])


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
# L'ultima tabella fatta in questo processo (la squadra di oggi), e quella su cui provare le idee.
_ULTIMA: Optional[Tabella] = None
_IDEE: tuple = ()


def _valuta(valori: dict) -> Prova:
    """In un processo a parte: mette i valori, rifa' la tabella, misura. Se chiesto, conta Romeo."""
    manopole.applica(valori)
    imp = _IMPOSTAZIONI
    t = costruisci_tabella(_BASI, imp["coppie"], imp["dal"], imp["al"])
    global _ULTIMA
    _ULTIMA = t
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


def risposte(domande: list, basi: dict, coppie, dal: int, al: int) -> np.ndarray:
    """Le risposte alle domande inventate, per le operazioni della tabella, nello stesso ordine
    di `costruisci_tabella` (con le manopole in uso)."""
    from nvm.dati.candele import costruisci
    from nvm.prova.base import opera
    from nvm.prova.romeo import grandi
    righe = []
    if not domande:
        return np.zeros((0, 0))
    for base in basi.values():
        fine = int(base.t[-1]) + base.passo
        ctx = inventate.Contesto.da(base, fine, grandi(base, fine))
        for alto, basso in coppie:
            alte, basse = costruisci(base, alto).chiuse_entro(fine), costruisci(base, basso).chiuse_entro(fine)
            righe += [inventate.rispondi_tutte(domande, r, ctx) for r in opera(alte, basse, dal, al)]
    return np.array(righe, float).reshape(len(righe), len(domande))


def _con_colonne(t: Tabella, colonne: np.ndarray) -> Tabella:
    return replace(t, x=np.c_[t.x, colonne])


def _valuta_idea(j: int) -> Prova:
    t, r, primo, ultimo = _IDEE
    return misura(_con_colonne(t, r[:, [j]]), {}, primo, ultimo)


def prova_idee(t: Tabella, r: np.ndarray, primo: int, ultimo: int, processi: int = 4) -> list[Prova]:
    """Il Capo anno per anno con ogni domanda nuova come colonna in piu'."""
    global _IDEE
    _IDEE = (t, r, primo, ultimo)
    if not r.shape[1]:
        return []
    if processi <= 1:
        return [_valuta_idea(j) for j in range(r.shape[1])]
    with multiprocessing.get_context("fork").Pool(processi) as pool:
        return pool.map(_valuta_idea, range(r.shape[1]))


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
    # Le domande inventate che entrano nel Capo, e tutte quelle provate (per la memoria).
    idee: list = field(default_factory=list)
    prove_idee: list = field(default_factory=list)


def _r(x: float) -> str:
    return f"{x:+.3f}".replace(".", ",").replace("-", "−")


def _v(x: Any) -> str:
    if isinstance(x, list):
        return "–".join(map(str, x))
    return str(x).replace(".", ",")


def idee_della_settimana(agenti, gia: set[str], rng: np.random.Generator) -> list:
    """Un agente nuovo prova prima le domande del suo mestiere (`inventate.PRIME`); poi inventa
    ogni settimana IDEE_PER_AGENTE domande a caso fra quelle mai provate."""
    idee = []
    for agente in agenti:
        prime = [d for d in inventate.PRIME.get(agente, []) if d.chiave not in gia]
        idee += prime or inventate.inventa(agente, rng, gia, IDEE_PER_AGENTE)
    return idee


def allena(basi: dict, impostazioni: dict, memoria: list[dict], adesso: int,
           dire: Callable[[str], None] = print, processi: int = 4, memoria_idee: list[dict] = (),
           solo: Optional[set[str]] = None) -> Esito:
    """Una settimana di palestra: prove, invenzioni, esami, decisioni e rapporto.
    `solo`: si allenano solo questi agenti (per esempio i nuovi, appena arrivati)."""
    settimana = adesso // SETTIMANA
    etichetta = datetime.fromtimestamp(adesso, tz=timezone.utc).strftime("%G-S%V")
    valori = manopole.attuali()
    elenco = [x for x in proposte(valori, memoria, settimana) if solo is None or x[0] in solo]
    # Le invenzioni: ogni agente combina i suoi mattoni in domande mai provate.
    gia = {x["chiave"] for x in memoria_idee} | {d.chiave for d in il_capo.INVENTATE}
    rng = np.random.default_rng(settimana)
    agenti = [a for a in dict.fromkeys(list(manopole.AGENTI) + list(inventate.MATTONI)) if solo is None or a in solo]
    idee = idee_della_settimana(agenti, gia, rng)
    dire(f"{len(elenco)} prove sulle manopole e {len(idee)} idee nuove, più la squadra di oggi")
    senza_romeo = {k: v for k, v in impostazioni.items() if k != "romeo"}
    oggi = prova_tutti([valori], basi, impostazioni, 1)[0]
    tabella_oggi = _ULTIMA
    risposte_idee = risposte(idee, basi, impostazioni["coppie"], impostazioni["dal"], impostazioni["al"])
    prove_idee = prova_idee(tabella_oggi, risposte_idee, impostazioni["primo"], impostazioni["ultimo"], processi)
    candidate = prova_tutti([_con(valori, a, n, v) for a, n, _, v in elenco], basi, senza_romeo, processi)
    # L'asticella conta tutte le prove fatte da sempre, non solo quelle di questa settimana: la
    # storia e' la stessa, e chi prova tante volte prima o poi trova qualcosa per caso.
    k = max(len(memoria) + len(memoria_idee) + len(elenco) + len(idee), 1)
    esami = [esame(oggi, c, k) for c in candidate]
    esami_idee = [esame(oggi, p, k) for p in prove_idee]

    # Il migliore di ogni agente fra quelli che passano; poi la squadra insieme.
    vincitori: dict[str, int] = {}
    for i, ((agente, *_), e) in enumerate(zip(elenco, esami)):
        if e.passa and (agente not in vincitori or e.media > esami[vincitori[agente]].media):
            vincitori[agente] = i
    scelti = list(vincitori.values())
    finali = valori
    squadra = None
    finale: Optional[Prova] = None
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
            finale = risultati[0]
        else:
            # Insieme non vanno d'accordo: resta la sola modifica migliore, se passa ancora.
            singoli = risultati[1:] if len(scelti) > 1 else risultati
            migliore = max(range(len(singoli)), key=lambda j: esame(oggi, singoli[j], k).media)
            if esame(oggi, singoli[migliore], k).passa:
                finale = singoli[migliore]
                i = scelti[migliore]
                finali = _con(valori, elenco[i][0], elenco[i][1], elenco[i][3])
                scelti = [i]
            else:
                scelti = []

    # Le idee: la migliore di ogni agente fra quelle che passano, provate insieme sulla squadra finale.
    migliori_idee: dict[str, int] = {}
    for j, (d, e) in enumerate(zip(idee, esami_idee)):
        if e.passa and (d.agente not in migliori_idee or e.media > esami_idee[migliori_idee[d.agente]].media):
            migliori_idee[d.agente] = j
    nuove_idee: list = []
    if migliori_idee:
        scelte = sorted(migliori_idee.values(), key=lambda j: -esami_idee[j].media)
        if finali is valori:
            base_tab, r_base = tabella_oggi, risposte_idee[:, scelte]
        else:
            manopole.applica(finali)
            base_tab = costruisci_tabella(basi, impostazioni["coppie"], impostazioni["dal"], impostazioni["al"])
            r_base = risposte([idee[j] for j in scelte], basi, impostazioni["coppie"], impostazioni["dal"], impostazioni["al"])
            manopole.applica(valori)
        for quante in ([len(scelte), 1] if len(scelte) > 1 else [1]):
            p = misura(_con_colonne(base_tab, r_base[:, :quante]), finali, impostazioni["primo"], impostazioni["ultimo"])
            if esame(oggi, p, k + len(scelte)).passa:
                nuove_idee = [idee[j] for j in scelte[:quante]]
                finale = p
                break

    tenute = set(scelti) if finali is not valori else set()
    idee_tenute = {d.chiave for d in nuove_idee}
    registro = []
    righe = [f"🏋️ Allenamento della settimana {etichetta}",
             "Ognuno ha riletto i suoi vent'anni e ha provato da solo a migliorarsi. Una modifica resta se migliora "
             "le prestazioni, non il guadagno: la qualità di ogni operazione (quanto rende per quanto oscilla), "
             f"con una certezza che cresce con le prove fatte da sempre ({k}) e nella maggior parte degli anni.", ""]
    registro_idee = []
    for agente in agenti:
        if agente in GRUPPI:
            righe.append(f"• {agente}: {diagnosi(agente, oggi)}.")
        else:
            righe.append(f"• {agente}: sono nuovo, provo le domande del mio mestiere.")
        for j, d in enumerate(idee):
            if d.agente != agente:
                continue
            e = esami_idee[j]
            entra = d.chiave in idee_tenute
            giudizio = "✅ entra nel Capo" if entra else ("❌ non basta" if not e.passa
                                                        else "❌ da sola sì, ma non con la squadra di oggi")
            righe.append(f"  💡 ho inventato «{d.nome}»: qualità {_r(e.media)} (fra {_r(e.basso)} e {_r(e.alto)}), "
                         f"meglio in {e.anni:.0%} degli anni. {giudizio}.")
            registro_idee.append({"settimana": etichetta, "numero": settimana, "agente": d.agente, "chiave": d.chiave,
                                  "nome": d.nome, "esito": "tenuta" if entra else "scartata", "qualita": e.media,
                                  "basso": e.basso, "alto": e.alto, "anni": e.anni})
        for i, (a, nome, da, v) in enumerate(elenco):
            if a != agente:
                continue
            e = esami[i]
            tenuta = i in tenute
            if tenuta:
                giudizio = "✅ la tengo"
            elif not e.passa:
                giudizio = "❌ non basta"
            else:
                giudizio = "❌ da sola sì, ma non va d'accordo con le modifiche dei colleghi"
            su, giu = effetti(oggi, candidate[i], agente)
            dopo = "".join([f" Ci guadagna {su}." if su and tenuta else "", f" Ci perde {giu}." if giu and tenuta else ""])
            cambia = f" Cambia anche: {'; '.join(e.note)}." if e.note and (tenuta or e.passa) else ""
            righe.append(f"  ↳ {nome} {_v(da)} → {_v(v)}: qualità {_r(e.media)} "
                         f"(fra {_r(e.basso)} e {_r(e.alto)}), meglio in {e.anni:.0%} degli anni. {giudizio}.{cambia}{dopo}")
            registro.append({"settimana": etichetta, "numero": settimana, "agente": a, "manopola": nome, "da": da, "a": v,
                             "chiave": _chiave(a, nome, da, v), "esito": "tenuta" if tenuta else "scartata",
                             "qualita": e.media, "basso": e.basso, "alto": e.alto, "anni": e.anni, "note": e.note})
    righe.append("")
    if tenute or nuove_idee:
        cambi = ", ".join([f"{elenco[i][0]} ({elenco[i][1]} {_v(elenco[i][2])} → {_v(elenco[i][3])})" for i in sorted(tenute)]
                          + [f"{d.agente} (l'idea «{d.nome}»)" for d in nuove_idee])
        righe.append(f"Capo: da oggi cambiano {cambi}. Mi riaddestro sulle operazioni nuove. Sui vent'anni: "
                     f"qualità {_r(oggi.qualita)} → {_r(finale.qualita)}, R a operazione {_r(oggi.r_medio)} → "
                     f"{_r(finale.r_medio)}, operazioni {oggi.n} → {finale.n}, drawdown {oggi.drawdown:.0f} → "
                     f"{finale.drawdown:.0f} R"
                     + (f", entrate di Romeo del 2023 ritrovate {oggi.romeo} → {finale.romeo}" if finale.romeo is not None else "")
                     + ".")
    else:
        righe.append(f"Capo: questa settimana nessuna modifica ha migliorato la squadra di oggi (qualità {_r(oggi.qualita)}, "
                     f"{_r(oggi.r_medio)} R a operazione sui vent'anni). Si resta così, e si riprova con altro.")
    return Esito("\n".join(righe), finali, bool(tenute) or bool(nuove_idee), registro, nuove_idee, registro_idee)


# --- Le entrate di Romeo ritrovate (nel rapporto) ----------------------------------------------------------------

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
        return {"prove": [], "idee": [], "ultimo": {}}
    return json.loads(percorso.read_text(encoding="utf-8"))


def salva_memoria(memoria: dict, percorso: Path = MEMORIA) -> None:
    percorso.write_text(json.dumps(memoria, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
