"""I cervelli nel mondo reale.

Il bot carica la squadra uscita da scuola (`nvm/vivo/cervelli.json`) coi suoi ricordi di scuola
(`ricordi.npz`). A ogni occasione giudicano e si confrontano; a ogni occasione finita imparano
subito dall'esperienza (`esperienza.py`) e la squadra cosi' com'e' diventata si salva
(`dati/vivo/cervelli_vivi.json`): quando il bot riparte riprende da li'. Se la scuola cambia (un
nuovo `cervelli.json`), la squadra nuova rivive una per una tutte le esperienze vere di prima
(`cervelli_esempi.jsonl`): quello che hanno imparato dal vivo non si perde mai.

Accanto alla squadra vivono le sfidanti: per ogni agente una versione diversa di se' (preparata
in palestra, `scuola.scegli_sfidanti`). Giudicano ogni occasione e imparano come la squadra; a
ogni esperienza si segna chi ha sbagliato meno. Appena una sfidante sbaglia chiaramente meno di
quella di adesso (almeno `SFIDA_MINIMO` esperienze, differenza oltre `SFIDA_Z` errori standard),
prende il suo posto subito: l'agente ha cambiato se stesso perche' l'esperienza gli ha dato ragione.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.cervello import esperienza
from nvm.cervello.piani import PIANI, nome
from nvm.cervello.rete import ReteValori
from nvm.cervello.scuola import vista_dei_piani
from nvm.cervello.squadra import Squadra
from nvm.cervello.viste import AGENTI

ESEMPI = "cervelli_esempi.jsonl"
VIVI = "cervelli_vivi.json"
RICORDI = "ricordi.npz"
# I risultati si imparano dentro questa misura, in R.
TETTO = (-3.0, 5.0)
# Quante esperienze vere servono, e quanto chiara deve essere la differenza (in errori standard,
# severa perche' si guarda dopo ogni esperienza), perche' una sfidante prenda il posto.
SFIDA_MINIMO = 100
SFIDA_Z = 3.0
# Con una scuola nuova le sfidanti rivivono solo le ultime esperienze (il bot riparte prima).
SFIDANTI_RIVISSUTE = 300
# Chi decide e chi impara. Decide la squadra in comando (all'inizio quella uscita da scuola);
# accanto una copia impara da ogni esperienza. Sulle ultime PRUDENZA esperienze (giudicate prima di
# impararle): se quella che impara sbaglia chiaramente meno (oltre PRUDENZA_Z errori standard),
# prende il comando; se sbaglia chiaramente di piu', torna come quella in comando e impara piu'
# piano. Sui vent'anni imparare di continuo e usarlo subito faceva sbagliare di piu' (2018-2023).
PRUDENZA = 150
PRUDENZA_Z = 2.0
# Le regole con cui si impara dal vivo: se cambiano, la squadra salvata con le regole vecchie non si
# riprende, e le esperienze si rivivono con quelle nuove.
REGOLE = "3: chi impara prende il comando solo coi fatti"


def carica(file: Path, cartella: Path) -> tuple[Optional[Squadra], dict]:
    """La squadra con tutte le esperienze vere gia' imparate. Senza file: nessuna. Nelle
    informazioni: sotto "piani" il cervello dei Livelli che sceglie stop e obiettivi, sotto
    "memoria" i ricordi di scuola e le esperienze vissute, sotto "sfidanti" le versioni diverse
    degli agenti che si mettono alla prova, sotto "cambi" quelle che hanno preso il posto."""
    if not file.exists():
        return None, {}
    testo = file.read_text(encoding="utf-8")
    dati = json.loads(testo)
    squadra = Squadra.da_dati(dati["squadra"])
    info = {k: v for k, v in dati.items() if k not in ("squadra", "piani", "sfidanti")}
    info["piani"] = ReteValori.da_dati(dati["piani"]) if dati.get("piani") else None
    info["sfidanti"] = [{"agente": s["agente"], "modifica": s["modifica"], "genomi": s.get("genomi"),
                         "squadra": Squadra.da_dati(s["squadra"]), "confronto": []} for s in dati.get("sfidanti", [])]
    info["cambi"] = []
    scuola = hashlib.sha256((testo + REGOLE).encode("utf-8")).hexdigest()[:16]
    memoria = {"ricordi": esperienza.Memoria.carica(file.parent / RICORDI), "vissute": esperienza.Memoria.vuota(),
               "scuola": scuola, "impara": Squadra.da_dati(dati["squadra"]), "ritmo": 1.0, "contro_scuola": []}
    memoria["base"] = _base(squadra, memoria["ricordi"])
    for s in info["sfidanti"]:
        s["base"] = _base(s["squadra"], memoria["ricordi"])
    info["memoria"] = memoria
    esempi = [json.loads(r) for r in (cartella / ESEMPI).read_text(encoding="utf-8").splitlines() if r.strip()] \
        if (cartella / ESEMPI).exists() else []
    salvata = _salvata(cartella / VIVI, scuola, len(esempi))
    for k, e in enumerate(esempi):
        v = squadra.adatta({a: np.array([x]) for a, x in e["viste"].items()})
        if salvata is None and np.isfinite(e["w"]):
            _esperienza(squadra, info, v, e["y"], e["w"], seme=k, sfide=k >= len(esempi) - SFIDANTI_RIVISSUTE)
            _impara_piano(info["piani"], v, e.get("piano"), e.get("erre"))
        else:
            memoria["vissute"].aggiungi(v, e["y"], e["w"] if np.isfinite(e["w"]) else 0.0)
    if salvata is not None:
        squadra = Squadra.da_dati(salvata["squadra"])
        if salvata.get("piani") and info["piani"] is not None:
            info["piani"] = ReteValori.da_dati(salvata["piani"])
        info["sfidanti"] = [{**s, "squadra": Squadra.da_dati(s["squadra"])} for s in salvata.get("sfidanti", [])]
        info["cambi"] = salvata.get("cambi", [])
        memoria["impara"] = Squadra.da_dati(salvata["impara"]) if salvata.get("impara") else Squadra.da_dati(salvata["squadra"])
        memoria["ritmo"] = float(salvata.get("ritmo", 1.0))
        memoria["contro_scuola"] = list(salvata.get("contro_scuola", []))
        if salvata.get("base") is not None:
            memoria["base"] = float(salvata["base"])
    elif esempi:
        _salva(cartella, squadra, info)
    return squadra, info


def _perdita_una(squadra: Squadra, v: dict, y: float) -> float:
    p = float(np.clip(squadra.giudica(v)[2][0], 1e-6, 1 - 1e-6))
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _base(squadra: Squadra, ricordi) -> Optional[float]:
    """Quanto sbaglia la squadra sui ricordi di controllo: il metro fisso delle lezioni."""
    return esperienza.perdita(squadra, esperienza.controllo_di_scuola(squadra, ricordi)) if len(ricordi) else None


def _esperienza(squadra: Squadra, info: dict, v: dict, y: float, w: float, seme: int, sfide: bool = True) -> dict:
    """Un'esperienza finita. `squadra` e' quella in comando (decide); accanto la squadra che impara
    e le sfidanti. Prima si segna chi aveva giudicato meglio, poi imparano; se una sfidante o la
    squadra che impara ha dimostrato di sbagliare meno, prende il comando; se quella che impara e'
    peggiorata, torna come quella in comando e impara piu' piano."""
    m = info["memoria"]
    sfidanti = info.get("sfidanti", []) if sfide else []
    for s in sfidanti:
        s["confronto"].append(float(w * (_perdita_una(squadra, v, y) - _perdita_una(s["squadra"], v, y))))
    allieva = m.get("impara") or squadra
    if allieva is not squadra:
        m.setdefault("contro_scuola", []).append(float(w * (_perdita_una(squadra, v, y) - _perdita_una(allieva, v, y))))
    ritmo = float(m.get("ritmo", 1.0))
    lezione = esperienza.impara(allieva, v, y, w, m["ricordi"], m["vissute"], seme, base=m.get("base"), ritmo=ritmo)
    for s in sfidanti:
        esperienza.impara(s["squadra"], v, y, w, m["ricordi"], m["vissute"], seme, base=s.get("base"), ritmo=ritmo)
    m["vissute"].aggiungi(v, y, w)
    cambio = _chi_vince(squadra, info) if sfidanti else None
    if cambio:
        lezione["cambio"] = cambio
        m["impara"] = Squadra.da_dati(squadra.come_dati())      # si riparte a imparare dalla squadra nuova
        m["base"], m["contro_scuola"] = _base(squadra, m["ricordi"]), []
    elif allieva is not squadra:
        esito = _chi_comanda(squadra, m)
        if esito:
            lezione[esito] = {"ritmo": m["ritmo"], "esperienze": PRUDENZA}
    return lezione


def _chi_comanda(squadra: Squadra, m: dict) -> Optional[str]:
    """Sulle ultime esperienze (giudicate prima di impararle): la squadra che impara sbaglia
    chiaramente meno di quella in comando? Prende il comando ("promozione"). Chiaramente di piu'?
    Torna come quella in comando e impara piu' piano ("prudenza")."""
    d = np.asarray(m.get("contro_scuola", [])[-PRUDENZA:], float)
    if len(d) < PRUDENZA:
        return None
    errore = d.std(ddof=1) / np.sqrt(len(d))
    if not errore > 0 or abs(d.mean()) / errore <= PRUDENZA_Z:
        return None
    if d.mean() > 0:
        nuova = Squadra.da_dati(m["impara"].come_dati())
        squadra.primi, squadra.secondi, squadra.capo, squadra.confronto = nuova.primi, nuova.secondi, nuova.capo, nuova.confronto
        esito = "promozione"
    else:
        m["impara"] = Squadra.da_dati(squadra.come_dati())
        m["ritmo"] = float(m.get("ritmo", 1.0)) / 2
        esito = "prudenza"
    m["contro_scuola"] = []
    return esito


def _chi_vince(squadra: Squadra, info: dict) -> Optional[dict]:
    """Se una sfidante sbaglia chiaramente meno di quella di adesso sulle esperienze vere, prende
    il suo posto (la squadra resta lo stesso oggetto: il bot non se ne accorge, se non dai giudizi)."""
    for s in list(info.get("sfidanti", [])):
        d = np.asarray(s["confronto"], float)
        if len(d) < SFIDA_MINIMO:
            continue
        errore = d.std(ddof=1) / np.sqrt(len(d))
        if errore > 0 and d.mean() / errore > SFIDA_Z:
            nuova = s["squadra"]
            squadra.primi, squadra.secondi, squadra.capo, squadra.confronto = (nuova.primi, nuova.secondi, nuova.capo,
                                                                               nuova.confronto)
            info["sfidanti"].remove(s)
            for altra in info["sfidanti"]:
                altra["confronto"] = []      # si riparte alla pari contro la squadra nuova
            cambio = {"agente": s["agente"], "modifica": s["modifica"], "esperienze": len(d), "meglio": float(d.mean()),
                      "genoma": (s.get("genomi") or {}).get(s["agente"])}
            info.setdefault("cambi", []).append(cambio)
            return cambio
    return None


def _salvata(file: Path, scuola: str, esperienze: int) -> Optional[dict]:
    """La squadra salvata dopo l'ultima esperienza, se viene dalla stessa scuola e le ha tutte."""
    if not file.exists():
        return None
    try:
        d = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("scuola") == scuola and d.get("esperienze") == esperienze else None


def _salva(cartella: Path, squadra: Squadra, info: dict) -> None:
    m = info.get("memoria") or {}
    cartella.mkdir(parents=True, exist_ok=True)
    provvisorio = cartella / (VIVI + ".nuovo")
    provvisorio.write_text(json.dumps({
        "scuola": m.get("scuola"), "esperienze": len(m.get("vissute") or []), "squadra": squadra.come_dati(),
        "piani": info["piani"].come_dati() if info.get("piani") is not None else None,
        "sfidanti": [{**s, "squadra": s["squadra"].come_dati()} for s in info.get("sfidanti", [])],
        "cambi": info.get("cambi", []), "ritmo": m.get("ritmo", 1.0), "contro_scuola": m.get("contro_scuola", []),
        "base": m.get("base"), "impara": m["impara"].come_dati() if m.get("impara") is not None else None}),
        encoding="utf-8")
    provvisorio.replace(cartella / VIVI)


def _per_i_piani(rete: ReteValori, v: dict) -> Optional[np.ndarray]:
    """Quello che vede il cervello dei piani; None se e' nato con viste di un'altra misura (per
    esempio prima degli occhi nuovi): allora si segue il piano di sempre finche' non si riallena."""
    if any(a not in v for a in AGENTI):
        return None
    x = vista_dei_piani({a: np.atleast_2d(v[a]) for a in AGENTI})
    return x if x.shape[1] == len(rete.media) else None


def _impara_piano(rete: Optional[ReteValori], v: dict, piano: Optional[int], erre: Optional[float]) -> None:
    """Il cervello dei piani impara il valore vero del piano seguito (gli altri non si sanno)."""
    if rete is None or piano is None or erre is None:
        return
    if not np.isfinite(erre):
        return
    valori = np.full((1, len(PIANI)), np.nan)
    valori[0, piano] = float(np.clip(erre, *TETTO))
    x = _per_i_piani(rete, v)
    if x is None:
        return
    prima = rete.come_dati()
    rete.aggiorna(x, valori)
    if not np.all(np.isfinite(rete.valori(x))):
        tornata = ReteValori.da_dati(prima)
        rete.w1, rete.b1, rete.w2, rete.b2 = tornata.w1, tornata.b1, tornata.w2, tornata.b2


def scegli_piano(rete: Optional[ReteValori], viste: dict, fattibili: Optional[list]) -> Optional[tuple[int, list]]:
    """Il piano che il cervello dei Livelli stima migliore, fra quelli che si possono fare."""
    if rete is None or not fattibili:
        return None
    x = _per_i_piani(rete, viste)
    if x is None:
        return None
    valori = rete.valori(x)[0]
    possibili = [j for j, op in enumerate(fattibili) if op is not None]
    if not possibili:
        return None
    j = max(possibili, key=lambda k: valori[k])
    return j, [float(x) for x in valori]


def _cento(logit: float) -> int:
    return int(round(100 / (1 + np.exp(-logit))))


def giudica(squadra: Squadra, viste: dict) -> dict:
    """Il primo giudizio di ognuno, quello dopo il confronto, chi ha convinto chi, e la fiducia
    della squadra (su 100: quanto credono che l'operazione guadagni)."""
    v = {a: np.atleast_2d(viste[a]) for a in AGENTI if a in viste}
    primo, dopo, p = squadra.giudica(v)
    convinti = squadra.chi_ha_convinto(v)
    return {"primo": {a: _cento(float(primo[a][0])) for a in squadra.agenti},
            "dopo": {a: _cento(float(dopo[a][0])) for a in squadra.agenti},
            "convinti": {a: [b, float(e)] for a, (b, e) in convinti.items()},
            "fiducia": float(p[0]), "viste": {a: [round(float(x), 5) for x in viste[a]] for a in AGENTI if a in viste}}


def impara(squadra: Squadra, cartella: Path, giudizio: dict, erre: float, info: Optional[dict] = None) -> Optional[dict]:
    """Un'occasione finita: la squadra impara subito dall'esperienza, la ricorda, e si salva.
    Restituisce com'e' andata la lezione (`esperienza.impara`)."""
    if not np.isfinite(erre):
        return None
    info = info if info is not None else {}
    m = info.setdefault("memoria", {"ricordi": esperienza.Memoria.vuota(), "vissute": esperienza.Memoria.vuota(),
                                    "scuola": None})
    # Un risultato fuori misura (uno stop quasi nullo fa R enormi) non deve travolgere quello che sanno.
    erre = float(np.clip(erre, *TETTO))
    y, w = float(erre > 0), abs(erre)
    v = squadra.adatta({a: np.array([x]) for a, x in giudizio["viste"].items()})
    lezione = _esperienza(squadra, info, v, y, w, seme=len(m["vissute"]))
    piano = giudizio.get("piano")
    _impara_piano(info.get("piani"), v, piano, erre)
    cartella.mkdir(parents=True, exist_ok=True)
    with (cartella / ESEMPI).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"viste": giudizio["viste"], "y": y, "w": w, "piano": piano, "erre": float(erre)}) + "\n")
    _salva(cartella, squadra, info)
    return lezione


def voce_della_lezione(lezione: dict, erre: float) -> str:
    """Cosa hanno imparato i cervelli da un'operazione vera appena chiusa."""
    prima, dopo = round(100 * lezione["prima"]), round(100 * lezione["dopo"])
    com_e_andata = "è andata bene" if erre > 0 else "è andata male"
    if not lezione["tenuta"]:
        return (f"🧠 Eravamo al {prima}% e {com_e_andata}. Abbiamo provato a impararlo, ma ci faceva sbagliare "
                f"di più su quello che sapevamo già: per ora lo teniamo solo come esperienza.")
    if abs(dopo - prima) < 1:
        return f"🧠 Eravamo al {prima}% e {com_e_andata}: ce lo aspettavamo, lo ricordiamo e non cambia quasi niente."
    return (f"🧠 Eravamo al {prima}% e {com_e_andata}. Lezione imparata: su casi così adesso siamo al {dopo}%. "
            f"Decideremo così quando i fatti ci daranno ragione.")


def puntata(info: dict, giudizio: dict, viste: Optional[dict]) -> float:
    """Quanto puntare su un'operazione quando decidono i cervelli, da 0 a 1: lo dice il cervello
    del Rischio (se all'esame ha battuto la formula), se no la formula di prima (2 x fiducia - 1)."""
    formula = max(2 * giudizio["fiducia"] - 1, 0.0)
    dati = (info.get("rischio") or {}).get("cervello")
    if not dati or not viste or "Livelli" not in viste:
        return formula
    if "_cervello_rischio" not in info:
        from nvm.cervello.rischio_cervello import CervelloRischio
        info["_cervello_rischio"] = CervelloRischio.da_dati(dati)
    from nvm.cervello.rischio_cervello import vista_del_rischio
    x = vista_del_rischio(giudizio["fiducia"], np.atleast_2d(viste["Livelli"]))
    if x.shape[1] != len(info["_cervello_rischio"].media):
        return formula
    return float(info["_cervello_rischio"].quanto(x)[0])


def voce_della_prudenza(prudenza: dict) -> str:
    """I cervelli si sono accorti che imparare cosi' in fretta li faceva sbagliare di piu'."""
    return (f"🧠 Ci siamo accorti che quello che avevamo imparato nelle ultime {PRUDENZA} occasioni ci faceva sbagliare "
            f"di più. Ripartiamo da come decidiamo adesso e impariamo più piano (ritmo {round(100 * prudenza['ritmo'])}%).")


def voce_della_promozione(promozione: dict) -> str:
    """Quello che hanno imparato dal vivo ha dimostrato di funzionare: adesso decide cosi'."""
    return (f"🧠 Da {promozione['esperienze']} occasioni vere quello che abbiamo imparato dal vivo sbaglia chiaramente "
            f"meno di come decidevamo. Da adesso decidiamo così.")


def voce_del_cambio(cambio: dict) -> str:
    """L'agente racconta in equipe come ha cambiato se stesso dal vivo."""
    return (f"🧬 {cambio['agente']} ha cambiato se stesso: {cambio['modifica']}. Per {cambio['esperienze']} "
            f"occasioni vere la versione nuova ha giudicato insieme alla vecchia, e ha sbagliato chiaramente meno. "
            f"Da adesso ragiono così.")


def voce_livelli(piano: int, valori: list) -> str:
    """Livelli dice quale piano sceglie e perche': quanto vale, contro il piano di sempre."""
    solito = PIANI.index(("estremo", "meta"))

    def r(x):
        return f"{x:+.2f}".replace(".", ",").replace("-", "−")
    testo = f"Scelgo {nome(PIANI[piano])}: in casi così vale {r(valori[piano])} volte il rischio"
    if piano != solito:
        testo += f", il piano di sempre {r(valori[solito])}"
    return testo + "."


# Da quanti punti su 100 un cambio d'idea si racconta.
CAMBIO = 3


def voce(g: dict, soglia: float, decidono: bool) -> str:
    """Il ragionamento dei cervelli su un'operazione, in un messaggio."""
    primi = ", ".join(f"{a} {x}" for a, x in g["primo"].items())
    cambi = []
    for a in g["primo"]:
        prima, dopo = g["primo"][a], g["dopo"][a]
        if abs(dopo - prima) >= CAMBIO:
            chi = g["convinti"].get(a, [None])[0]
            cambi.append(f"{a} da {prima} a {dopo}" + (f" (l'ha convinto {chi})" if chi else ""))
    fiducia = round(100 * g["fiducia"])
    entra = g["fiducia"] > soglia
    righe = [f"Quanto ci crediamo, su 100: {primi}."]
    righe.append("Dopo il confronto: " + ("; ".join(cambi) + "." if cambi else "nessuno ha cambiato idea."))
    if decidono:
        righe.append(f"Pesando i nostri giudizi (quanto ognuno ha avuto ragione a scuola): {fiducia} su 100: "
                     + ("entriamo." if entra else "non entriamo."))
    else:
        righe.append(f"Pesando i nostri giudizi (quanto ognuno ha avuto ragione a scuola): {fiducia} su 100, "
                     + ("entreremmo." if entra else "non entreremmo.")
                     + " Siamo in prova: decidiamo solo quando all'esame battiamo il Capo.")
    return "\n".join(righe)


def capo_quando_decidono(p1: float, capo_entrava: bool) -> str:
    """Il Capo quando decidono i cervelli: lo dice, e dice cosa avrebbe fatto lui."""
    return (f"Decidono i cervelli, scelta del proprietario. Io, col mio vecchio calcolo, "
            f"{'sarei entrato anch' + chr(39) + 'io' if capo_entrava else 'non sarei entrato'} "
            f"({round(100 * p1)} possibilità su 100 di arrivare al primo obiettivo).")


def gara(seguite: list, dal: int, al: int, soglia: float) -> Optional[str]:
    """La giornata, sulle occasioni finite: cosa avrebbero fatto i cervelli e cosa il Capo."""
    finite = [s for s in seguite if s.esito is not None and s.cervelli and dal <= s.esito["quando"] < al]
    if not finite:
        return None
    loro = [float(s.esito["erre"]) for s in finite if s.cervelli["fiducia"] > soglia]
    capo = [float(s.esito["erre"]) for s in finite if s.cervelli.get("capo", s.presa_dal_capo)]

    def v(x):
        return f"{sum(x):+.2f}".replace(".", ",").replace("-", "−") + " volte il rischio"
    return (f"• Cervelli contro Capo, sulle {len(finite)} occasioni finite oggi: i cervelli ne avrebbero prese "
            f"{len(loro)} ({v(loro)}), il Capo {len(capo)} ({v(capo)})")


def la_migliore(seguite: list, dal: int, al: int, fiducia_minima: float) -> Optional[str]:
    """L'occasione di oggi in cui i cervelli hanno creduto di piu', e quanto serviva per metterci
    soldi: cosi' si vede perche' sono stati fermi (o perche' sono entrati)."""
    oggi = [s for s in seguite if s.cervelli and dal <= s.quando < al]
    if not oggi:
        return None
    s = max(oggi, key=lambda x: x.cervelli["fiducia"])
    ci_credono = round(100 * s.cervelli["fiducia"])
    serve = round(100 * (1 + fiducia_minima) / 2)
    verso = "acquisto" if s.verso == "long" else "vendita"
    esito = "abbastanza per metterci soldi" if ci_credono >= serve else "non abbastanza per metterci soldi"
    return (f"• L'occasione più convincente per i cervelli: {s.strumento} in {verso}, ci credevano {ci_credono} su "
            f"100; per rischiare ne serve almeno {serve}: {esito}")
