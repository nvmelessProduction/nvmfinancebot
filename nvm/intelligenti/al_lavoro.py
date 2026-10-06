"""La squadra intelligente al lavoro nel bot dal vivo (`vivo.py`): chi la accende, le riunioni sulle
occasioni del giro, i piani da rivedere, i messaggi in equipe in parole semplici.

La squadra e' nostra (nessuna AI esterna) e decide da sola: si spegne solo da
`nvm/vivo/scelte.json` con `"squadra_intelligente": false`.
"""

from __future__ import annotations

import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import costruisci
from nvm.intelligenti import metodo
from nvm.intelligenti.squadra import Squadra, Verdetto
from nvm.prova.campo import Operazione, Uscita, simula
from nvm.tempo import TF


def crea(cartella: Path, scelte: dict) -> Optional[Squadra]:
    if scelte.get("squadra_intelligente") is False:
        return None
    return Squadra(cartella / "intelligenti")


def _dati(op) -> Optional[dict]:
    if op is None:
        return None
    d = asdict(op)
    d["verso"] = op.verso.value
    return d


def _gemello(strumento: str, basi: dict):
    """Le ore del mercato gemello per l'SMT (V8 22:00), se il bot le ha: solo le coppie di Romeo."""
    g = metodo.GEMELLI.get(strumento)
    if not g or g[0] not in basi:
        return None
    return basi[g[0]], g[1]


def riunioni(squadra: Squadra, decisioni, basi: dict, fini: dict, esposizione: float = 0.0) -> dict[str, Verdetto]:
    """La squadra si riunisce su ogni occasione del giro: le domande di Romeo dai video (`metodo.py`),
    poi decide. Restituisce i verdetti per chiave; manca solo l'occasione su cui qualcosa si e' rotto
    (l'errore resta in `squadra.ultimo_errore`)."""
    fatte = {}
    for d in decisioni:
        s = d.r.strumento
        try:
            if getattr(d, "foto", None):
                m = metodo.valuta_foto(d)
            else:
                m = metodo.valuta(d, basi[s], fini.get(s), _gemello(s, basi))
            piani = getattr(d, "piani_romeo", None) or None
            seguire = {"strumento": s, "basso": d.r.basso_tf.value, "scadenza": int(d.scadenza),
                       "piani": [_dati(op) for op in piani]} if piani else None
            v = squadra.riunione(d.chiave, s, m, int(d.r.quando), piani, esposizione, seguire, d.op)
            v.metodo = m
            fatte[d.chiave] = v
        except Exception:
            squadra.ultimo_errore = traceback.format_exc()[-1500:]
    squadra.salva()
    return fatte


def valuta_piani(squadra: Squadra, basi: dict, fini: dict, adesso: int) -> int:
    """Livelli rivede i piani delle occasioni passate: come sarebbe andato ogni stop e ogni uscita.
    Quando sono finiti tutti (o e' scaduta l'occasione) li impara. Restituisce quante ne ha imparate."""
    with squadra._lucchetto:
        return _valuta_piani(squadra, basi, fini, adesso)


def _valuta_piani(squadra: Squadra, basi: dict, fini: dict, adesso: int) -> int:
    candele: dict = {}
    imparate = 0
    for chiave, d in list(squadra.memoria.da_vedere.items()):
        try:
            sorgente = fini if TF(d["basso"]) is TF.M15 else basi
            if d["strumento"] not in sorgente:
                continue
            k = (d["strumento"], d["basso"])
            if k not in candele:
                candele[k] = costruisci(sorgente[d["strumento"]], TF(d["basso"])).chiuse_entro(adesso)
            finiti = d.setdefault("finiti", {})
            for j, p in enumerate(d["piani"]):
                if p is None or str(j) in finiti:
                    continue
                op = Operazione(**{**p, "verso": Verso(p["verso"])})
                e = simula(op, candele[k], d["scadenza"])
                if e.uscita is not Uscita.SCADUTA or adesso >= d["scadenza"]:
                    finiti[str(j)] = float(e.erre)
            if all(p is None or str(j) in finiti for j, p in enumerate(d["piani"])):
                squadra.impara_piani(chiave, [finiti.get(str(j)) for j in range(len(d["piani"]))])
                imparate += 1
        except Exception:
            squadra.ultimo_errore = traceback.format_exc()[-1500:]
            squadra.memoria.da_vedere.pop(chiave, None)
    return imparate


# --- I messaggi in equipe, in parole semplici ---------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:.2%}".replace(".", ",")


def _euro(x: float, valuta: str) -> str:
    testo = f"{abs(x):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return ("−" if x < 0 else "") + testo + f" {valuta}"


def voci(v: Verdetto, rischio: Optional[float] = None, valuta: str = "EUR", quota: Optional[float] = None,
         aperte: int = 0, quota_totale: float = 0.0) -> list:
    """La discussione della squadra su un'operazione aperta, come chat fra colleghi. Il Rischio dice
    quanto ha messo in gioco davvero (in soldi e in parte del conto)."""
    from nvm.vivo.conversazione import Voce
    fuori = []
    for chi, testo in v.voci:
        if not testo:
            continue
        if chi == "Rischio" and rischio is not None:
            testo = f"Metto in gioco {_euro(rischio, valuta)}" + (f" ({_pct(quota)} del conto)" if quota else "") + ". " + testo
            if aperte > 1:
                testo += f" Con le altre aperte, in tutto è in gioco {_pct(quota_totale)} del conto."
        fuori.append(Voce(chi, testo))
    return fuori


def benvenuto(strumenti: int) -> str:
    return (f"Guardiamo {strumenti} mercati col metodo delle foto del proprietario (la strategia CRT di Romeo come la "
            "fa lui). Entriamo all'apertura della candela 3, a qualunque ora, quando: la candela 2 ha preso un lato del "
            "range (la candela 1, o la madre se ci sono inside bar) ed è rientrata; la finta ha preso un key level "
            "(massimo o minimo del giorno, della settimana, del mese, dei 3 mesi, dell'anno prima); il timeframe di "
            "comando è dalla nostra parte. Stop oltre la candela 2. TP1 all'altro lato del range, con metà chiusa e "
            "il pareggio; il resto al gap del timeframe grande, o al key level se il gap non c'è. Lavoriamo su 1 ora "
            "(solo quando prende il key level del giorno e il massimo o minimo delle 4 ore), 4 ore, 6 ore, giorno, "
            "settimana e mese; il DXY vale per tutte le coppie col dollaro. Se manca una regola, aspettiamo. Mai "
            "senza stop.\n"
            "Come lavoriamo davvero: ognuno di noi stima quanto spesso un'occasione così va bene e lo impara dai "
            "risultati dal vivo (all'inizio non sappiamo niente e lo diciamo): il Gap guarda le fasi del gap e "
            "l'RSI, il DXY il dollaro, l'Orario l'ora, Livelli dove chiudere. Poi ci ascoltiamo, e se uno cambia "
            "idea lo dice. Il Capo mette insieme i giudizi e lascia un'occasione con tutte le regole solo se i fatti "
            "dicono chiaro che occasioni così perdono. Il Rischio parte dall'1% del conto. Impariamo prima dai "
            "risultati veri del broker, poi da quelli sulla carta. Non siamo un'intelligenza artificiale che parla: "
            "siamo le regole del metodo e numeri che si correggono coi fatti.")


def lezioni_in_breve(lezioni: list[dict], nome: str, erre: float) -> str:
    """Quello che la squadra impara da un'operazione chiusa: chi si era sbagliato, il Capo, il Rischio."""
    come = "è andata bene" if erre > 0.05 else "è finita in pari" if erre > -0.05 else "è andata male"
    righe = [f"📓 {nome}: {come}. Cosa impariamo:"]
    sbagliati = [l for l in lezioni if l["agente"] not in ("Capo", "Rischio") and not l.get("giusto")][:3]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in sbagliati]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in lezioni if l["agente"] in ("Capo", "Rischio")]
    giusti = [l["agente"] for l in lezioni if l["agente"] not in ("Capo", "Rischio") and l.get("giusto")]
    if giusti:
        righe.append(f"• Avevano visto giusto: {', '.join(giusti)}.")
    return "\n".join(righe)


def manuali_in_breve(cambi: list[tuple[str, str, str]]) -> str:
    if not cambi:
        return ("🧠 Revisione della settimana: nessuno ha cambiato idea. Non abbiamo ancora visto abbastanza "
                "per cambiare quello che dice Romeo.")
    righe = ["🧠 Revisione della settimana: cosa abbiamo imparato dal vivo."]
    righe += [f"• {a}: {cosa}" for a, cosa, _ in cambi]
    return "\n".join(righe)


def come_va(squadra: Squadra) -> list[str]:
    """Righe per il riepilogo della sera: la puntata del Rischio e chi ci prende di piu'."""
    m = squadra.memoria
    righe = [f"• Il Rischio adesso punta in media {_pct(m.rischio['base'])} del conto a operazione"]
    n, somma, vinte = m.a_piu
    if n:
        righe.append(f"• Occasioni con tutte le regole del metodo finite finora: {n}, andate bene {vinte}")
    voti = [(a, *m.ci_prende(a)) for a in m.voti]
    voti = [(a, g, n) for a, g, n in voti if n >= 5]
    if voti:
        a, g, n = max(voti, key=lambda x: x[1] / x[2])
        righe.append(f"• Chi ci prende di più: {a} ({g} volte su {n})")
    if m.idee:
        righe.append(f"• Idee inventate dalla squadra finora: {len(m.idee)}")
    return righe
