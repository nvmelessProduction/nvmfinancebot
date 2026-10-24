"""La misura delle regole di oggi sullo storico, con la stessa catena del bot dal vivo (24/10/2026).

La richiesta (Venice, accettata dal proprietario): *"Misura le regole di oggi sui vent'anni, coi costi e fuori
campione, usando la stessa catena del bot dal vivo. Nello stesso run confronta target vicino vs lontano, RR 1.0 vs 1.5,
e con/senza correlazioni ... Dichiara cosa non è misurabile ... Dammi i numeri: baseline, R per mercato e timeframe,
intervalli, occasioni"*.

Come:

1. mese per mese, per ogni mercato, `giro.occasioni_foto` (la catena del bot dal vivo: le coppie col dollaro solo col
   CRT del DXY, oro e argento coi loro CRT) col quadro tagliato a ogni candela 3 (niente futuro);
2. le regole della squadra: si entra con `metodo.valuta_foto(d).a_piu` (CRT, key level, direzione), una operazione
   aperta per strumento;
3. l'esito con `prova.campo.simula`: il 25% al TP1 col pareggio e il resto al target, o tutto al TP1; stop e target
   nella stessa ora conta lo stop; scadenza di `giro.TETTO_FOTO`; commissione tolta in R.

I dati:
- `--duka` (`dati/grezzi`): le ore di Dukascopy con bid e ask veri;
- `--storico`: le ore di HistData (`kaggle_rete.histdata.scarica_tutto`), solo bid, con lo spread stimato
  (`kaggle_rete.esperienza.SPREAD`);
- il DXY e' quello vero di HistData (UDXUSD), dal novembre 2010.

Non si misurano BTC ed ETH: la TOTAL storica non c'e'.

    python -m strumenti.misura_vivo raccogli --storico dati/storico --uscita dati/misura_vivo
    python -m strumenti.misura_vivo analizza --uscita dati/misura_vivo
"""

from __future__ import annotations

import argparse
import json
import math
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

RADICE = Path(__file__).resolve().parent.parent
FOREX = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD")
METALLI = ("XAUUSD", "XAGUSD")
# Da quando si misura: il DXY vero comincia il 01/11/2010, e servono alcuni mesi per i suoi key level.
INIZIO = {**{s: (2011, 1) for s in FOREX}, "XAUUSD": (2007, 1), "XAGUSD": (2010, 1)}
FINE = (2026, 9)            # le ore di Dukascopy arrivano a fine agosto 2026
ESAME = 2023                # dal 2023 l'esame, guardato una volta; prima la scelta delle varianti


def _t(anno: int, mese: int) -> int:
    return int(datetime(anno, mese, 1, tzinfo=timezone.utc).timestamp())


def _mesi(inizio: tuple, fine: tuple) -> list[tuple[int, int]]:
    fuori, (a, m) = [], inizio
    while (a, m) < fine:
        n = (a + (m == 12), m % 12 + 1)
        fuori.append((_t(a, m), _t(*n)))
        a, m = n
    return fuori


def _ore(strumento: str, duka: Path, storico: Path, al: int):
    from kaggle_rete.esperienza import con_spread
    from nvm.dati.ore import carica
    if (duka / "ore" / strumento).exists():
        m, _ = carica(duka, strumento, _t(2006, 1), al)
        return m, "Dukascopy (bid e ask veri)"
    m, _ = carica(storico, strumento, _t(2000, 1), al, solo_bid=True)
    if strumento == "DXY":
        return m, "HistData (solo bid)"
    return con_spread(m), "HistData (bid, spread stimato)"


def raccogli_uno(strumento: str, duka: str, storico: str, uscita: str) -> str:
    """Tutte le occasioni di `strumento` con la catena del bot, e l'esito di ogni piano. Una riga JSON per occasione."""
    from nvm.agenti import foto
    from nvm.dati import candele as C
    from nvm.intelligenti import metodo
    from nvm.prova.campo import simula
    from nvm.tempo import TF
    from nvm.vivo import giro

    for s in FOREX + METALLI:
        C.SESSIONI[s] = "18"            # come i grafici di TradingView del proprietario (0-4-8 italiane)
    C.SESSIONI["DXY"] = "20"            # come il DXY di Capital.com letto dal bot (2-6-10 italiane)
    duka, storico, uscita = Path(duka), Path(storico), Path(uscita)
    fine_t = _t(*FINE)
    ore, fonte = _ore(strumento, duka, storico, fine_t)
    dxy, _ = _ore("DXY", duka, storico, fine_t)
    basse = foto.Quadro.da(ore, int(ore.t[-1]) + 3600).candele[TF.H1]
    capo = type("Capo", (), {"media": None})()
    righe, errori, inizio = [], 0, time.time()
    for dal, al in _mesi(INIZIO[strumento], FINE):
        try:
            gemelli = {"DXY": dxy.fra(int(dxy.t[0]), al)} if len(dxy) and dxy.t[0] < dal else None
            decisioni = giro.occasioni_foto(strumento, ore.fra(int(ore.t[0]), al), dal, al, capo, gemelli=gemelli)
        except Exception:
            errori += 1
            (uscita / f"errori-{strumento}.txt").open("a").write(f"{dal}: {traceback.format_exc()}\n")
            continue
        for d in decisioni:
            s = d.foto["setup"]
            if not dal <= s.n3_inizio < al:
                continue
            try:
                righe.append(_riga(d, s, metodo.valuta_foto(d), basse, simula))
            except Exception:
                errori += 1
                (uscita / f"errori-{strumento}.txt").open("a").write(f"{s.n3_inizio}: {traceback.format_exc()}\n")
    with open(uscita / f"{strumento}.jsonl", "w") as f:
        for r in righe:
            f.write(json.dumps(r) + "\n")
    return f"{strumento}: {len(righe)} occasioni, {errori} errori, {time.time() - inizio:.0f} s, dati {fonte}"


def _riga(d, s, m, basse, simula) -> dict:
    op = d.op
    segno = -1 if s.short else 1
    rischio = abs(op.ingresso - op.stop)
    ob, altro = d.foto["obiettivo"], d.foto.get("dopo")
    sg = d.foto.get("dxy") if s.dal_dxy else None
    piani = {"tp1": replace(op, tp2=op.tp1, parziale=1.0, pareggio=False)}
    if segno * (ob.prezzo - op.tp1) > 0:
        piani["vicino"] = replace(op, tp2=ob.prezzo, parziale=0.25, pareggio=True)
    if altro is not None and segno * (altro.prezzo - max(ob.prezzo, op.tp1, key=lambda x: segno * x)) > 0:
        piani["lontano"] = replace(op, tp2=altro.prezzo, parziale=0.25, pareggio=True)
    esiti = {}
    for nome, p in piani.items():
        e = simula(p, basse, int(d.scadenza))
        esiti[nome] = [round(float(e.erre), 4), e.uscita.value, int(e.quando)]
    return {
        "strumento": s.strumento, "tf": s.tf.value, "verso": s.verso.value, "n3": int(s.n3_inizio),
        "dal_dxy": bool(s.dal_dxy), "guida": [sg.tf.value, int(sg.n3_inizio)] if sg is not None else None,
        "a_piu": bool(m.a_piu), "manca": [x.nome for x in m.mancano][:1],
        "piano_vivo": "tp1" if op.parziale == 1.0 else "vicino",
        "rr_tp1": round(abs(op.tp1 - op.ingresso) / rischio, 3),
        "rr_vicino": round(abs(ob.prezzo - op.ingresso) / rischio, 3),
        "rr_lontano": round(abs(altro.prezzo - op.ingresso) / rischio, 3) if "lontano" in piani else None,
        "target": ob.tipo, "esiti": esiti,
    }


def raccogli(duka: Path, storico: Path, uscita: Path, processi: int, strumenti) -> None:
    uscita.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(processi) as ex:
        futuri = [ex.submit(raccogli_uno, s, str(duka), str(storico), str(uscita)) for s in strumenti]
        for f in futuri:
            print(f.result(), flush=True)


# --- l'analisi ------------------------------------------------------------------------------------------------------

def _piano(r: dict, variante: str):
    """L'esito (R, uscita, chiusa) del piano che la variante sceglie, o None se la variante non entra."""
    e = r["esiti"]
    rr_min = 1.5 if "1,5" in variante else 1.0
    lontano = "lontano" in variante
    if lontano and r["rr_vicino"] < 1.5 and "lontano" in e and r["rr_lontano"] >= rr_min:
        return e["lontano"]
    if "vicino" in e and r["rr_vicino"] >= rr_min:
        return e["vicino"]
    if lontano and "lontano" in e and r["rr_lontano"] >= rr_min:
        return e["lontano"]
    if r["rr_tp1"] >= rr_min:
        return e["tp1"]
    return None


VARIANTI = ("oggi", "lontano", "RR 1,5", "lontano + RR 1,5")


def _presi(righe: list, variante: str, una_per_strumento: bool = True) -> list:
    """Le operazioni che il bot avrebbe aperto: con tutte le regole, una alla volta per strumento."""
    fuori, libero = [], {}
    for r in sorted(righe, key=lambda r: (r["n3"], r["strumento"])):
        if not r["a_piu"]:
            continue
        e = _piano(r, variante)
        if e is None:
            continue
        if una_per_strumento and r["n3"] < libero.get(r["strumento"], 0):
            continue
        libero[r["strumento"]] = e[2]
        fuori.append({**r, "erre": e[0], "uscita": e[1], "chiusa": e[2]})
    return fuori


def _intervallo(presi: list, volte: int = 2000, seme: int = 7) -> tuple[float, float, float]:
    """R medio e intervallo al 95% col bootstrap a blocchi di settimane (le operazioni della stessa settimana insieme)."""
    if not presi:
        return math.nan, math.nan, math.nan
    sett = {}
    for p in presi:
        sett.setdefault(p["n3"] // (7 * 86400), []).append(p["erre"])
    blocchi = [np.array(v) for v in sett.values()]
    somme = np.array([b.sum() for b in blocchi])
    conti = np.array([len(b) for b in blocchi])
    g = np.random.default_rng(seme)
    k = g.integers(0, len(blocchi), (volte, len(blocchi)))
    medie = somme[k].sum(1) / conti[k].sum(1)
    return float(somme.sum() / conti.sum()), float(np.percentile(medie, 2.5)), float(np.percentile(medie, 97.5))


def _riga_tab(nome: str, presi: list) -> str:
    if not presi:
        return f"| {nome} | 0 | | | |"
    m, a, b = _intervallo(presi)
    vinte = sum(p["erre"] > 0 for p in presi) / len(presi)
    return f"| {nome} | {len(presi)} | {m:+.3f} | [{a:+.3f}; {b:+.3f}] | {vinte:.0%} |"


def _conto(presi: list, regola: str) -> tuple[float, float]:
    """Il conto in % del capitale iniziale (senza interesse composto): il rendimento finale e il drawdown massimo.
    `regola`: "1%" fisso; "Rischio" come la squadra di oggi coi pesi di partenza (1% x e^(-20 x esposizione aperta));
    "Rischio + idea" come prima, ma le operazioni nate dallo stesso CRT del DXY si dividono una puntata."""
    eventi = sorted(presi, key=lambda p: p["n3"])
    aperte, curva, conto = [], [0.0], 0.0
    gruppi = {}
    for p in eventi:
        if p["guida"]:
            gruppi.setdefault((tuple(p["guida"]), p["n3"]), []).append(p)
    for p in eventi:
        for c in sorted([c for c in aperte if c[0] <= p["n3"]]):
            conto += c[1]
            curva.append(conto)
        aperte = [c for c in aperte if c[0] > p["n3"]]
        esposizione = sum(c[2] for c in aperte)
        puntata = 1.0 if regola == "1%" else 1.0 * math.exp(-0.2 * 100 * esposizione / 100)
        if regola == "Rischio + idea" and p["guida"]:
            puntata /= len(gruppi[(tuple(p["guida"]), p["n3"])])
        aperte.append((p["chiusa"], puntata * p["erre"], puntata))
    for c in sorted(aperte):
        conto += c[1]
        curva.append(conto)
    curva = np.array(curva)
    dd = float((np.maximum.accumulate(curva) - curva).max())
    return float(curva[-1]), dd


def analizza(uscita: Path) -> str:
    righe = []
    for f in sorted(uscita.glob("*.jsonl")):
        righe += [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    anno = lambda r: datetime.fromtimestamp(r["n3"], timezone.utc).year
    out = [f"# Le regole di oggi sullo storico ({datetime.now(timezone.utc):%d/%m/%Y})", "",
           f"Occasioni trovate dalla catena del bot: {len(righe)}; con tutte le regole: "
           f"{sum(r['a_piu'] for r in righe)}.", ""]
    intestazione = ["| Gruppo | Operazioni | R medio | Intervallo 95% | Vinte |", "|---|---|---|---|---|"]
    for variante in VARIANTI:
        presi = _presi(righe, variante)
        out += [f"## Variante: {variante}", ""] + intestazione
        out.append(_riga_tab("tutte", presi))
        out.append(_riga_tab(f"scelta (fino al {ESAME - 1})", [p for p in presi if anno(p) < ESAME]))
        out.append(_riga_tab(f"esame (dal {ESAME})", [p for p in presi if anno(p) >= ESAME]))
        if variante == "oggi":
            out.append(_riga_tab("prendili tutti (senza una per strumento)", _presi(righe, variante, False)))
            out.append(_riga_tab("coppie dal DXY", [p for p in presi if p["dal_dxy"]]))
            out.append(_riga_tab("oro e argento", [p for p in presi if not p["dal_dxy"]]))
            for s in FOREX + METALLI:
                out.append(_riga_tab(s, [p for p in presi if p["strumento"] == s]))
            for tf in ("H1", "H4", "H6", "D1", "W1", "MN"):
                out.append(_riga_tab(f"CRT {tf}", [p for p in presi if p["tf"] == tf]))
            scartate = [{**r, "erre": r["esiti"][r["piano_vivo"]][0]} for r in righe if not r["a_piu"]]
            out.append(_riga_tab("scartate dalle regole (non A+), col piano del vivo", scartate))
        out.append("")
        out.append("Il conto (somma delle puntate x R, in % del capitale iniziale; drawdown massimo):")
        for regola in ("1%", "Rischio", "Rischio + idea"):
            fine, dd = _conto(presi, regola)
            out.append(f"- {regola}: {fine:+.1f}% in tutto, drawdown massimo {dd:.1f}%")
        out.append("")
    out += ["Non misurati: BTC ed ETH (la TOTAL storica non c'e'). DXY vero di HistData dal 11/2010.",
            "Il pareggio nella simulazione e' all'ingresso preciso (dal vivo copre le commissioni): un filo prudente."]
    testo = "\n".join(out) + "\n"
    (uscita / "risultato.md").write_text(testo, encoding="utf-8")
    return testo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fase", choices=("raccogli", "analizza"))
    p.add_argument("--duka", default=str(RADICE / "dati" / "grezzi"))
    p.add_argument("--storico", default=str(RADICE / "dati" / "storico"))
    p.add_argument("--uscita", default=str(RADICE / "dati" / "misura_vivo"))
    p.add_argument("--processi", type=int, default=4)
    p.add_argument("--strumenti", default=",".join(FOREX + METALLI))
    a = p.parse_args()
    if a.fase == "raccogli":
        raccogli(Path(a.duka), Path(a.storico), Path(a.uscita), a.processi, a.strumenti.split(","))
    else:
        print(analizza(Path(a.uscita)))


if __name__ == "__main__":
    main()
