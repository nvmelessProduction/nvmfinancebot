"""Lo storico al minuto di HistData.com (gratis), trasformato nelle ore del bot.

- Un file zip per anno (per l'anno in corso, uno per mese): poche richieste, nessun limite stretto come Dukascopy.
- Solo il bid. Il DXY c'e' (UDXUSD).
- L'ora di HistData NON e' New York fisso: segue l'ora legale europea (verificato contro Dukascopy su EURUSD
  2007, 2013, 2019, 2024, XAUUSD 2015, USDJPY 2010). UTC = ora HistData + 5 ore d'inverno, + 4 ore quando in
  Europa c'e' l'ora legale (dall'ultima domenica di marzo all'ultima di ottobre).
"""

from __future__ import annotations

import io
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from nvm.dati.minuti import Minuti, PUNTO, file_del_mese

SITO = "https://www.histdata.com"
PAGINA = SITO + "/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{coppia}"
# Il nome di HistData per ogni strumento del bot (US30 su HistData non c'e').
NOMI = {n: n for n in (
    "EURUSD GBPUSD AUDUSD NZDUSD USDCAD USDCHF USDJPY EURGBP EURAUD EURNZD EURCAD EURCHF EURJPY GBPAUD GBPNZD "
    "GBPCAD GBPCHF GBPJPY AUDNZD AUDCAD AUDCHF AUDJPY NZDCAD NZDCHF NZDJPY CADCHF CADJPY CHFJPY XAUUSD XAGUSD").split()}
NOMI |= {"USOIL": "WTIUSD", "UKOIL": "BCOUSD", "SPX500": "SPXUSD", "NAS100": "NSXUSD", "GER40": "GRXEUR",
         "UK100": "UKXGBP", "JPN225": "JPXJPY", "DXY": "UDXUSD"}
PUNTO.setdefault("DXY", 1e-3)


def _leggi(url: str, dati: bytes | None = None, referer: str | None = None, tentativi: int = 5) -> bytes:
    for k in range(tentativi):
        try:
            r = urllib.request.Request(url, data=dati, headers={"User-Agent": "Mozilla/5.0", **(
                {"Referer": referer} if referer else {})})
            with urllib.request.urlopen(r, timeout=120) as risposta:
                return risposta.read()
        except Exception:
            if k == tentativi - 1:
                raise
            time.sleep(5 * (k + 1))


def periodi(coppia: str) -> list[str]:
    """I file che HistData ha per una coppia: 'AAAA' per gli anni chiusi, 'AAAA/M' per i mesi dell'anno in corso."""
    html = _leggi(PAGINA.format(coppia=coppia.lower())).decode("utf-8", "replace")
    trovati = set(re.findall(rf"1-minute-bar-quotes/{coppia.lower()}/(\d{{4}}(?:/\d{{1,2}})?)\"", html))
    return sorted(trovati, key=lambda p: tuple(int(x) for x in p.split("/")))


def scarica_zip(coppia: str, periodo: str) -> bytes:
    pagina = PAGINA.format(coppia=coppia.lower()) + "/" + periodo
    html = _leggi(pagina).decode("utf-8", "replace")
    modulo = html[html.index('id="file_down"'):]
    modulo = modulo[:modulo.index("</form>")]
    campi = dict(re.findall(r'name="(\w+)" id="\w+" value="([^"]*)"', modulo))
    grezzo = _leggi(SITO + "/get.php", urllib.parse.urlencode(campi).encode(), referer=pagina)
    if not grezzo.startswith(b"PK"):
        raise ValueError(f"HistData non ha dato uno zip per {coppia} {periodo}")
    return grezzo


def _ultima_domenica(anno: int, mese: int) -> date:
    d = date(anno + (mese == 12), mese % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def ore_da_zip(grezzo: bytes, strumento: str) -> Minuti:
    """Le ore UTC (bid; ask uguale al bid) dai minuti di un file di HistData."""
    z = zipfile.ZipFile(io.BytesIO(grezzo))
    nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    testo = z.read(nome).decode("ascii", "replace")
    # "AAAAMMGG HHMMSS;apertura;massimo;minimo;chiusura;volume". Negli anni vecchi i prezzi hanno spazi dopo
    # ("1.2397    "): lo spazio fra giorno e ora diventa un separatore, gli altri spariscono.
    testo = re.sub(r"(\d{8}) (\d{6})", r"\1;\2", testo).replace(" ", "")
    a = np.loadtxt(io.StringIO(testo), delimiter=";", ndmin=2, usecols=range(6))
    if a.size == 0:
        return Minuti.vuoti(strumento, 3600)
    d, hhmmss = a[:, 0].astype(np.int64), a[:, 1].astype(np.int64)
    mesi = (d // 10000 - 1970) * 12 + (d // 100) % 100 - 1
    giorno = mesi.astype("datetime64[M]").astype("datetime64[D]") + (d % 100 - 1)
    secondi = giorno.astype("datetime64[s]").astype(np.int64) + hhmmss // 10000 * 3600 + (hhmmss // 100) % 100 * 60
    # Ora legale europea, decisa dal giorno di HistData (i cambi cadono a mercato chiuso).
    anni = giorno.astype("datetime64[Y]").astype(int) + 1970
    estate = np.zeros(len(d), bool)
    for y in np.unique(anni):
        da = np.datetime64(_ultima_domenica(int(y), 3))
        a_ = np.datetime64(_ultima_domenica(int(y), 10))
        sel = anni == y
        estate[sel] = (giorno[sel] >= da) & (giorno[sel] < a_)
    t = secondi + np.where(estate, 4, 5) * 3600
    ordine = np.argsort(t, kind="stable")
    t = t[ordine]
    prezzi = a[ordine, 2:6]
    ora = t // 3600 * 3600
    u, inizio = np.unique(ora, return_index=True)
    fine = np.r_[inizio[1:], len(ora)]
    bid = np.c_[prezzi[inizio, 0], np.maximum.reduceat(prezzi[:, 1], inizio),
                np.minimum.reduceat(prezzi[:, 2], inizio), prezzi[fine - 1, 3]]
    punti = np.rint(bid / PUNTO[strumento]).astype(np.int64)
    zero = np.zeros(len(u), np.float32)
    return Minuti(strumento, u.astype(np.int64), punti, punti.copy(), zero, zero.copy(), 3600)


def salva_mesi(ore: Minuti, radice: Path) -> int:
    """Salva le ore mese per mese in `radice/ore_bid` (dove `nvm.dati.ore.carica` le cerca). Quanti mesi."""
    if not len(ore):
        return 0
    mesi = ore.t.astype("datetime64[s]").astype("datetime64[M]")
    n = 0
    for m in np.unique(mesi):
        sel = np.flatnonzero(mesi == m)
        pezzo = ore.fra(int(ore.t[sel[0]]), int(ore.t[sel[-1]]) + 1)
        anno, mese = int(str(m)[:4]), int(str(m)[5:7])
        percorso = file_del_mese(radice / "ore_bid", ore.strumento, anno, mese)
        if percorso.exists():   # un mese a cavallo di due file: si uniscono, in ordine e senza doppioni
            vecchio = Minuti.carica(percorso)
            t = np.r_[vecchio.t, pezzo.t]
            _, unici = np.unique(t, return_index=True)       # gia' in ordine di tempo
            pezzo = Minuti(ore.strumento, t[unici], *(np.r_[getattr(vecchio, k), getattr(pezzo, k)][unici] for k in
                                                       ("bid", "ask", "volume_bid", "volume_ask")), 3600)
        pezzo.salva(percorso)
        n += 1
    return n


def scarica_tutto(strumenti: list[str], radice: Path, scrivi=print, pausa: float = 1.0) -> dict:
    """Scarica e converte tutti gli anni di ogni strumento. Riprende da dove era rimasto (un segno per file)."""
    fatti = radice / "histdata_fatti"
    fatti.mkdir(parents=True, exist_ok=True)
    conti = {}
    for s in strumenti:
        coppia = NOMI.get(s)
        if coppia is None:
            scrivi(f"{s}: HistData non ce l'ha, salto")
            continue
        try:
            lista = periodi(coppia)
        except Exception as e:
            scrivi(f"{s}: elenco non letto ({e}), salto")
            continue
        conti[s] = 0
        for p in lista:
            segno = fatti / f"{s}-{p.replace('/', '-')}"
            if segno.exists():
                conti[s] += 1
                continue
            try:
                ore = ore_da_zip(scarica_zip(coppia, p), s)
                salva_mesi(ore, radice)
                segno.touch()
                conti[s] += 1
            except Exception as e:
                scrivi(f"  {s} {p}: errore {e}")
            time.sleep(pausa)
        scrivi(f"{s}: {conti[s]} file su {len(lista)} ({lista[0] if lista else '-'} -> {lista[-1] if lista else '-'})")
    return conti


def pezzi_buoni(m, minimo_anni: float = 4.0) -> tuple[list, str]:
    """Divide lo storico in pezzi di cui ci si puo' fidare. Si taglia:
    - a ogni salto impossibile (la chiusura cambia di oltre il 40% da un'ora all'altra, o un prezzo non positivo): li'
      HistData passa a un'altra serie (il suo "DXY" prima di dicembre 2018 ha i valori del Dow Jones, il suo "DAX"
      2021-2023 quelli dell'Euro Stoxx). Il franco svizzero del 15/01/2015 (circa -15% fra due chiusure) non e' un
      taglio;
    - a ogni buco di oltre 10 giorni (HistData non ha il WTI dal 2024 a maggio 2026).
    Ogni pezzo e' una serie vera e coerente: la rete non sa come si chiama lo strumento (vede prezzi in scala), quindi
    tutti i pezzi di almeno `minimo_anni` servono. Restituisce i pezzi e cosa e' stato tagliato (vuoto se niente)."""
    if len(m) < 2:
        return ([m] if len(m) else []), ""
    c = m.bid[:, 3].astype(np.float64)
    salti = np.flatnonzero((c[1:] <= 0) | (c[:-1] <= 0) | (np.abs(c[1:] / np.where(c[:-1] > 0, c[:-1], 1) - 1) > 0.4))
    buchi = np.flatnonzero(np.diff(m.t) > 10 * 86400)
    tagli = np.unique(np.r_[0, salti + 1, buchi + 1, len(m.t)])
    giorno = lambda i: str(np.datetime64(int(m.t[i]), "s"))[:10]
    pezzi, note = [], []
    for a, b in zip(tagli[:-1], tagli[1:]):
        a, b = int(a), int(b)
        if b - a < 2:
            continue
        anni = (m.t[b - 1] - m.t[a]) / (365.25 * 86400)
        if anni >= minimo_anni:
            pezzi.append(m.fra(int(m.t[a]), int(m.t[b - 1]) + 1))
        if len(tagli) > 2:
            note.append(f"{giorno(a)} -> {giorno(b - 1)} {'tenuto' if anni >= minimo_anni else 'troppo corto'}")
    nota = ""
    if len(tagli) > 2:
        nota = f"{len(salti)} salti impossibili e {len(buchi)} buchi: pezzi " + ", ".join(note)
    return pezzi, nota
