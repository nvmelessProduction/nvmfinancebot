"""La scuola degli occhi di Nameless (fase 1), su Kaggle con la scheda grafica e i dati della fase 0.

    from kaggle_rete.occhi import scuola
    scuola(ore=3)

- I dati sono l'output del notebook dei dati (`kaggle_rete/dati.py`: `ore_bid/` e `mercati.json`), aggiunto come
  input: si trovano da soli sotto `/kaggle/input`. Tutti i mercati, con gli orari di TradingView (`dati.imposta_orari`)
  e i pezzi che passano il controllo di qualita' (`histdata.pezzi_buoni`).
- **Impara** sugli anni fino al 2019, **si controlla** sul 2020-2022, l'**esame** e' dal 2023: quegli anni la rete non
  li vede mai mentre impara (una finestra a un'ora del 2019 ha solo candele chiuse prima).
- Meta' degli esempi nasconde candele a caso, meta' nasconde il futuro (`nvm/nameless/occhi.py`).
- **Esame**: per ogni timeframe e ogni modo, l'errore della rete contro quello di chi copia l'ultima candela vista.
  Passa se la rete e' meglio dappertutto (dove ci sono almeno `MINIMO_ESAME` candele da confrontare).
- Nell'output: `occhi_nameless.pt` (i pesi, da cui parte la fase 2) ed `esame_occhi.json`. La rete migliore si salva
  anche durante la scuola, cosi' se Kaggle si ferma il lavoro non si perde.
"""

from __future__ import annotations

import glob
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from kaggle_rete.dati import CRYPTO, imposta_orari
from kaggle_rete.histdata import NOMI, pezzi_buoni
from nvm.dati.ore import carica
from nvm.dati.strumenti import STRUMENTI
from nvm.nameless.occhi import LUNGHEZZA, ORE_FUTURO, Lettore, Occhi, copia, nascondi
from nvm.nameless.sensi import TF_NAMELESS, Sensi
from nvm.tempo import utc

CONTROLLO = utc(2020, 1, 1)
ESAME = utc(2023, 1, 1)
MINIMO_ESAME = 200
NOMI_TF = {"H1": "1h", "H4": "4h", "H6": "6h", "H12": "12h", "D1": "1d", "W1": "1w", "MN": "1m", "3M": "3m",
           "12M": "12m"}
MODI = {"caso": "candele nascoste a caso", "futuro": "il futuro dopo il taglio"}


def trova_dati() -> Path:
    """La cartella con `ore_bid/` fra gli input del notebook."""
    trovate = sorted(glob.glob("/kaggle/input/**/ore_bid", recursive=True))
    if not trovate:
        raise FileNotFoundError("non trovo i dati: aggiungi come input l'output del notebook dei dati (fase 0)")
    return Path(trovate[0]).parent


def famiglia(nome: str) -> str:
    base = nome.split(" ")[0]
    if base in CRYPTO:
        return "crypto"
    if base.startswith(("XAU", "XAG")):
        return "metalli"
    s = STRUMENTI.get(base)
    if s is not None:
        return s.famiglia
    return "forex" if len(base) == 6 and base.isalpha() and base not in ("AUS200", "UKOIL", "USOIL") else "indici"


def carica_sensi(radice: Path, nomi: list[str], scrivi=print) -> tuple[Sensi, dict]:
    """Tutti i mercati, un pezzo buono alla volta, con gli orari di TradingView."""
    imposta_orari(nomi)
    pezzi, conti = [], {}
    for n in nomi:
        try:
            m, _ = carica(radice, n, 0, 2 ** 40, solo_bid=True)
        except Exception as e:
            scrivi(f"{n}: non si legge ({e})")
            continue
        buoni, nota = pezzi_buoni(m)
        if nota:
            scrivi(f"{n}: {nota}")
        for p in buoni:
            nome = n if len(buoni) == 1 else f"{n} dal {str(np.datetime64(int(p.t[0]), 's'))[:10]}"
            pezzi.append((nome, p))
            conti[nome] = {"ore": int(len(p)), "dal": str(np.datetime64(int(p.t[0]), "s"))[:10],
                           "al": str(np.datetime64(int(p.t[-1]), "s"))[:10], "famiglia": famiglia(nome)}
    inizio = time.time()
    sensi = Sensi.da(pezzi)
    scrivi(f"{len(pezzi)} pezzi di mercato, {sensi.ore()} ore, candele pronte in {time.time() - inizio:.0f} s")
    return sensi, conti


def _esempi(j: np.ndarray, futuro: bool, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r = rng.integers(1, ORE_FUTURO + 1, size=len(j)) if futuro else np.zeros(len(j), np.int64)
    return j, j - r, np.full(len(j), futuro)


@torch.no_grad()
def misura(rete: Occhi, lettore: Lettore, j: np.ndarray, futuro: bool, seme: int = 7, lotto: int = 512) -> dict:
    """Per ogni timeframe: l'errore medio (quadrato, in scala) della rete e di chi copia l'ultima candela vista, sulle
    stesse candele nascoste. In piu', sulla sola chiusura, la rete contro chi dice "il prezzo resta dov'e'" (zero: la
    chiusura dell'ora del taglio): per il futuro e' la direzione, la cosa piu' difficile."""
    rete.eval()
    rng = np.random.default_rng(seme)
    g = torch.Generator(device=lettore.dove).manual_seed(seme)
    k = len(TF_NAMELESS)
    somma_rete, somma_copia, quante = torch.zeros(k), torch.zeros(k), torch.zeros(k)
    chiusura_rete, chiusura_ferma = torch.zeros(k), torch.zeros(k)
    jj, tt, ff = _esempi(j, futuro, rng)
    for a in range(0, len(jj), lotto):
        dj, dt, df = (torch.as_tensor(x[a:a + lotto], device=lettore.dove) for x in (jj, tt, ff))
        contenuto, tempo, vuote, dopo = lettore.guarda(dj, dt)
        nascoste = nascondi(vuote, dopo, df, g)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=lettore.dove == "cuda"):
            previsione = rete.indovina(contenuto, tempo, vuote, nascoste).float()
        base, ok = copia(contenuto, vuote, nascoste)
        vero = contenuto[..., :4]
        e_rete = ((previsione - vero) ** 2).mean(-1)
        e_copia = ((base - vero) ** 2).mean(-1)
        somma_rete += (e_rete * ok).sum((0, 2)).cpu()
        somma_copia += (e_copia * ok).sum((0, 2)).cpu()
        quante += ok.sum((0, 2)).cpu()
        chiusura_rete += (((previsione[..., 3] - vero[..., 3]) ** 2) * ok).sum((0, 2)).cpu()
        chiusura_ferma += ((vero[..., 3] ** 2) * ok).sum((0, 2)).cpu()
    rete.train()
    fuori = {}
    for i, tf in enumerate(TF_NAMELESS):
        n = int(quante[i])
        fuori[NOMI_TF[tf.value]] = {"rete": float(somma_rete[i] / max(n, 1)),
                                    "copia": float(somma_copia[i] / max(n, 1)), "candele": n,
                                    "chiusura rete": float(chiusura_rete[i] / max(n, 1)),
                                    "chiusura ferma": float(chiusura_ferma[i] / max(n, 1))}
    return fuori


def voto(m: dict) -> float:
    """Quanto l'errore della rete e' di quello di chi copia, in media sui timeframe (meno e' meglio)."""
    r = [x["rete"] / x["copia"] for x in m.values() if x["candele"] >= MINIMO_ESAME and x["copia"] > 0]
    return float(np.mean(r)) if r else float("inf")


def passa(esame: dict) -> bool:
    return all(x["rete"] < x["copia"] for modo in esame.values() for x in modo.values() if x["candele"] >= MINIMO_ESAME)


def _salva(uscita: Path, rete: Occhi, extra: dict) -> None:
    uscita.mkdir(parents=True, exist_ok=True)
    torch.save({"pesi": rete.state_dict(), "misura": rete.misura, "timeframe": [tf.value for tf in TF_NAMELESS],
                "lunghezza": LUNGHEZZA, **extra}, uscita / "occhi_nameless.pt")


def scuola(ore: float = 3.0, radice: Path | None = None, uscita: Path = Path("/kaggle/working"),
           solo: list[str] | None = None, lotto: int = 256, d: int = 128, strati: int = 4, seme: int = 1,
           campione: int = 30000, ogni_minuti: float = 10, ritmo: float = 3e-4, riscaldamento: int = 500,
           scrivi=None) -> dict:
    scrivi = scrivi or (lambda t: print(t, flush=True))
    inizio = time.time()
    torch.manual_seed(seme)
    rng = np.random.default_rng(seme)
    dove = "cuda" if torch.cuda.is_available() else "cpu"
    radice = radice or trova_dati()
    nomi = [n for n in list(NOMI) + list(CRYPTO) if solo is None or n in solo]
    sensi, conti = carica_sensi(radice, nomi, scrivi)
    lettore = Lettore(sensi, dove)
    impara = sensi.istanti(0, CONTROLLO)
    controlla = sensi.istanti(CONTROLLO, ESAME)
    esame = sensi.istanti(ESAME, 2 ** 62)
    scrivi(f"ore per imparare {len(impara)}, per controllare {len(controlla)}, per l'esame {len(esame)} ({dove})")
    rete = Occhi(d, strati).to(dove)
    scrivi(f"pesi della rete: {sum(p.numel() for p in rete.parameters())}")
    ottimo = torch.optim.AdamW(rete.parameters(), lr=ritmo, weight_decay=0.01)
    scala = torch.amp.GradScaler("cuda", enabled=dove == "cuda")
    g = torch.Generator(device=dove).manual_seed(seme)
    prova = rng.choice(controlla, size=min(3000, len(controlla)), replace=False)
    # Ogni timeframe pesa uguale: l'errore di ogni candela si divide per quello tipico di chi copia sul suo timeframe
    # (una candela annuale sbaglia di piu' di una oraria anche quando e' letta bene), come nell'esame.
    tipico = [misura(rete, lettore, impara[rng.integers(len(impara), size=3000)], m == "futuro") for m in MODI]
    pesi = torch.tensor([1.0 / max(np.mean([t[NOMI_TF[tf.value]]["copia"] for t in tipico
                                            if t[NOMI_TF[tf.value]]["candele"]] or [1.0]), 1e-6)
                         for tf in TF_NAMELESS], device=dove)
    scrivi("errore tipico di chi copia: " + ", ".join(f"{NOMI_TF[tf.value]} {1 / float(w):.4f}"
                                                      for tf, w in zip(TF_NAMELESS, pesi)))
    fine = time.time() + 3600 * ore
    partenza, passi, migliore, storia, ultimo = time.time(), 0, None, [], time.time()
    while time.time() < fine:
        quota = (time.time() - partenza) / (fine - partenza)
        for gruppo in ottimo.param_groups:
            discesa = 0.05 + 0.475 * (1 + math.cos(math.pi * quota))
            gruppo["lr"] = ritmo * min(1.0, (passi + 1) / riscaldamento) * discesa
        futuro = rng.random(lotto) < 0.5
        j = impara[rng.integers(len(impara), size=lotto)]
        r = np.where(futuro, rng.integers(1, ORE_FUTURO + 1, size=lotto), 0)
        dj, dt, df = (torch.as_tensor(x, device=dove) for x in (j, j - r, futuro))
        contenuto, tempo, vuote, dopo = lettore.guarda(dj, dt)
        nascoste = nascondi(vuote, dopo, df, g)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dove == "cuda"):
            previsione = rete.indovina(contenuto, tempo, vuote, nascoste)
        errore = ((previsione.float() - contenuto[..., :4]) ** 2).mean(-1) * pesi[None, :, None]
        perdita = errore[nascoste].mean()
        ottimo.zero_grad(set_to_none=True)
        scala.scale(perdita).backward()
        scala.unscale_(ottimo)
        nn.utils.clip_grad_norm_(rete.parameters(), 1.0)
        scala.step(ottimo)
        scala.update()
        passi += 1
        if time.time() - ultimo > 60 * ogni_minuti or time.time() >= fine:
            ultimo = time.time()
            c = {m: misura(rete, lettore, prova, m == "futuro") for m in MODI}
            v = float(np.mean([voto(x) for x in c.values()]))
            storia.append({"passo": passi, "minuti": round((time.time() - inizio) / 60),
                           "perdita": float(perdita.detach()), "controllo": v})
            scrivi(f"passo {passi}: errore {float(perdita.detach()):.3f}; al controllo la rete sbaglia il {v:.0%} "
                   "di chi copia")
            if migliore is None or v < migliore[0]:
                migliore = (v, {k: t.detach().clone() for k, t in rete.state_dict().items()})
                _salva(uscita, rete, {"passi": passi, "controllo": v})
    if migliore is not None:
        rete.load_state_dict(migliore[1])
    per_esame = rng.choice(esame, size=min(campione, len(esame)), replace=False)
    risultato = {m: misura(rete, lettore, per_esame, m == "futuro") for m in MODI}
    famiglie = np.array([conti[sensi.nomi[p]]["famiglia"] for p in sensi.chi[per_esame]])
    per_famiglia = {f: {m: voto(misura(rete, lettore, per_esame[famiglie == f], m == "futuro")) for m in MODI}
                    for f in sorted(set(famiglie))}
    resoconto = {"passa": passa(risultato), "esame": risultato, "per famiglia (rete / copia)": per_famiglia,
                 "controllo": {m: misura(rete, lettore, rng.choice(controlla, size=min(campione, len(controlla)),
                                                                    replace=False), m == "futuro") for m in MODI},
                 "passi": passi, "ore": ore, "minuti": round((time.time() - inizio) / 60), "storia": storia,
                 "mercati": conti, "rete": rete.misura}
    _salva(uscita, rete, {"passi": passi, "esame": risultato, "passa": resoconto["passa"]})
    (uscita / "esame_occhi.json").write_text(json.dumps(resoconto, indent=1, ensure_ascii=False), encoding="utf-8")
    stampa(resoconto, scrivi)
    return resoconto


def stampa(resoconto: dict, scrivi=print) -> None:
    scrivi(f"\nESAME DEGLI OCCHI (dal 2023, anni mai visti), {resoconto['passi']} passi in "
           f"{resoconto['minuti']} minuti")
    for modo, righe in resoconto["esame"].items():
        scrivi(f"  {MODI[modo]}:")
        for tf, x in righe.items():
            if not x["candele"]:
                continue
            meglio = 1 - x["rete"] / x["copia"] if x["copia"] > 0 else 0.0
            nota = "" if x["candele"] >= MINIMO_ESAME else " (poche candele, non conta)"
            segno = "ok" if x["rete"] < x["copia"] else "NO"
            scrivi(f"    {tf:>4}: {segno} errore {x['rete']:.4f} contro {x['copia']:.4f} di chi copia, "
                   f"{meglio:+.0%} ({x['candele']} candele){nota}")
    futuro = [x["chiusura rete"] / x["chiusura ferma"] for x in resoconto["esame"]["futuro"].values()
              if x["candele"] >= MINIMO_ESAME and x["chiusura ferma"] > 0]
    if futuro:
        scrivi(f"  la chiusura del futuro (la direzione): la rete sbaglia il {np.mean(futuro):.0%} di chi dice \"il "
               "prezzo resta dov'e'\" (sotto il 100% vede un po' dove va; non e' l'esame di questa fase)")
    for f, v in resoconto["per famiglia (rete / copia)"].items():
        scrivi(f"  {f}: " + ", ".join(f"{MODI[m]} {x:.0%} dell'errore di chi copia" for m, x in v.items()))
    scrivi("PASSATO: gli occhi leggono meglio di chi copia l'ultima candela." if resoconto["passa"] else
           "NON PASSATO: dove c'e' NO la rete non fa meglio di chi copia l'ultima candela.")
