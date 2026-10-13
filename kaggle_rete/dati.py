"""I dati di Nameless, scaricati dentro Kaggle (il proprietario, 13/10/2026: *"io non scarico dati. li scarichiamo su
kaggle"*; `documenti/PROGETTO-NAMELESS.md`, fase 0).

Tutti i mercati che si trovano gratis, a 1 ora:

- **HistData**: tutto il suo elenco, 66 mercati (forex con le esotiche, oro e argento anche contro euro, sterlina,
  franco e dollaro australiano, indici, petrolio, DXY). Solo il bid; l'orario e' gia' convertito in UTC
  (`histdata.ore_da_zip`).
- **Binance**: le crypto principali contro USDT, dal 2017 (`CRYPTO`), dai file mensili pubblici.

Gli orari sono quelli dei grafici di TradingView del proprietario (*"i grafici che noi abbiamo collegato già vanno 0, 4,
8, 12, 16, 20"*): le 18 di New York per tutto, il calendario UTC per le crypto (`ORARI`, `imposta_orari`). Le candele
grandi le fanno le scuole con questi orari; qui si salvano le ore come arrivano.

Nella cella di Kaggle (Internet acceso; basta il processore, la scheda grafica non serve):

    from kaggle_rete.dati import tutto
    tutto()

Alla fine, nell'output: `ore_bid/` (le ore, mese per mese, come le legge `nvm.dati.ore.carica`) e `mercati.json` (cosa
c'e', da quando, il calendario, e i pezzi tagliati dal controllo di qualita' `histdata.pezzi_buoni`). Poi "Save
Version": l'output diventa un dataset che le scuole di Nameless usano senza riscaricare niente.
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np

from kaggle_rete.histdata import NOMI, _leggi, pezzi_buoni, salva_mesi, scarica_tutto
from nvm.dati.minuti import PUNTO, Minuti

# I mercati di HistData che il bot non conosceva: nome -> (nome su HistData, punto). I nomi degli indici sono quelli
# dei broker.
NUOVI_HISTDATA = {
    **{c: (c, 1e-5) for c in ("USDMXN", "USDHKD", "USDNOK", "USDTRY", "USDZAR", "USDPLN", "USDCZK", "USDSEK",
                             "USDDKK", "USDSGD", "EURPLN", "EURCZK", "EURSEK", "EURDKK", "EURNOK", "EURTRY")},
    **{c: (c, 1e-3) for c in ("USDHUF", "EURHUF", "SGDJPY", "ZARJPY", "XAUAUD", "XAUCHF", "XAUEUR", "XAUGBP")},
    "AUS200": ("AUXAUD", 1e-3), "FRA40": ("FRXEUR", 1e-3), "HK50": ("HKXHKD", 1e-3), "EU50": ("ETXEUR", 1e-3),
}
for _nome, (_codice, _punto) in NUOVI_HISTDATA.items():
    NOMI.setdefault(_nome, _codice)
    PUNTO.setdefault(_nome, _punto)

# Le crypto da Binance (contro USDT): nome -> simbolo. Prezzi con al massimo 8 decimali: il punto e' 1e-8, tranne
# BTC ed ETH che il bot conosce gia' (`nvm/dati/strumenti.py`).
CRYPTO = {f"{c}USD": f"{c}USDT" for c in ("BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "LTC", "LINK", "DOT",
                                           "AVAX", "TRX", "XLM", "BCH", "ETC", "ATOM", "UNI", "NEAR", "FIL", "AAVE")}
for _nome in CRYPTO:
    PUNTO.setdefault(_nome, 1e-8)
BINANCE = "https://data.binance.vision/data/spot/monthly/klines/{simbolo}/1h/{simbolo}-1h-{anno:04d}-{mese:02d}.zip"
INIZIO_BINANCE = (2017, 8)

# Il calendario di ogni mercato, come i grafici di TradingView del proprietario: l'ora di New York in cui apre la
# sessione ("18": 0, 4, 8, 12, 16, 20 italiane) o "utc" per le crypto.
SESSIONE = "18"


def orari(nome: str) -> str:
    return "utc" if nome in CRYPTO else SESSIONE


def imposta_orari(nomi) -> None:
    """Le candele grandi con gli orari di TradingView: da chiamare prima di costruire i quadri (`candele.SESSIONI`)."""
    from nvm.dati import candele
    for n in nomi:
        o = orari(n)
        candele.SESSIONI[n] = True if o == "utc" else o


def mesi_fino_a(fino: date, dal: tuple[int, int] = INIZIO_BINANCE) -> list[tuple[int, int]]:
    """I mesi chiusi da `dal` fino al mese prima di `fino`."""
    a, m = dal
    fuori = []
    while (a, m) < (fino.year, fino.month):
        fuori.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return fuori


def ore_binance(grezzo: bytes, nome: str) -> Minuti:
    """Le ore di un file mensile di Binance: apertura in millisecondi (dal 2025 in microsecondi), o, h, l, c, volume."""
    z = zipfile.ZipFile(io.BytesIO(grezzo))
    testo = z.read(z.namelist()[0]).decode("ascii", "replace")
    righe = [r for r in testo.splitlines() if r and r[0].isdigit()]          # senza l'intestazione, se c'e'
    if not righe:
        return Minuti.vuoti(nome, 3600)
    a = np.loadtxt(io.StringIO("\n".join(righe)), delimiter=",", ndmin=2, usecols=range(6))
    t = a[:, 0].astype(np.int64)
    t = np.where(t > 10**14, t // 1_000_000, t // 1000)
    t = t - t % 3600
    punti = np.rint(a[:, 1:5] / PUNTO[nome]).astype(np.int64)
    v = a[:, 5].astype(np.float32)
    ordine = np.argsort(t, kind="stable")
    return Minuti(nome, t[ordine], punti[ordine], punti[ordine].copy(), v[ordine], v[ordine].copy(), 3600)


def scarica_crypto(radice: Path, fino: date | None = None, scrivi=print, pausa: float = 0.2) -> dict:
    """Tutti i mesi chiusi di ogni crypto. Riprende da dove era rimasto; un mese che Binance non ha (la moneta non
    c'era ancora) si salta."""
    fino = fino or date.today()
    fatti = radice / "binance_fatti"
    fatti.mkdir(parents=True, exist_ok=True)
    conti = {}
    for nome, simbolo in CRYPTO.items():
        conti[nome] = 0
        for anno, mese in mesi_fino_a(fino):
            segno = fatti / f"{nome}-{anno}-{mese:02d}"
            if segno.exists():
                conti[nome] += 1
                continue
            try:
                grezzo = _leggi(BINANCE.format(simbolo=simbolo, anno=anno, mese=mese), tentativi=2)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                scrivi(f"  {nome} {anno}-{mese:02d}: errore {e}")
                continue
            except Exception as e:
                scrivi(f"  {nome} {anno}-{mese:02d}: errore {e}")
                continue
            salva_mesi(ore_binance(grezzo, nome), radice)
            segno.touch()
            conti[nome] += 1
            time.sleep(pausa)
        scrivi(f"{nome}: {conti[nome]} mesi")
    return conti


def resoconto(radice: Path, nomi, fonte: dict) -> dict:
    """Cosa c'e' di ogni mercato, da quando a quando, con quale calendario, e cosa ha tagliato il controllo."""
    from nvm.dati.ore import carica
    fuori = {}
    for n in nomi:
        try:
            m, _ = carica(radice, n, 0, 2**40, solo_bid=True)
        except Exception as e:
            fuori[n] = {"errore": str(e)}
            continue
        if not len(m):
            fuori[n] = {"ore": 0}
            continue
        pezzi, nota = pezzi_buoni(m)
        giorno = lambda t: str(np.datetime64(int(t), "s"))[:10]
        fuori[n] = {"fonte": fonte[n], "orari": orari(n), "ore": int(len(m)), "dal": giorno(m.t[0]),
                    "al": giorno(m.t[-1]), "pezzi buoni": len(pezzi),
                    "ore buone": int(sum(len(p) for p in pezzi)), "tagli": nota}
    return fuori


def tutto(uscita: Path = Path("/kaggle/working"), solo: list[str] | None = None, scrivi=None) -> dict:
    """Scarica tutto (HistData, poi Binance), controlla e scrive `mercati.json`. `solo`: alcuni mercati, per prova."""
    scrivi = scrivi or (lambda t: print(t, flush=True))
    inizio = time.time()
    storici = [n for n in NOMI if solo is None or n in solo]
    crypto = [n for n in CRYPTO if solo is None or n in solo]
    scrivi(f"HistData: {len(storici)} mercati; Binance: {len(crypto)} crypto")
    scarica_tutto(storici, uscita, scrivi=scrivi)
    if crypto:
        tenute = dict(CRYPTO)
        CRYPTO.clear()
        CRYPTO.update({n: tenute[n] for n in crypto})
        try:
            scarica_crypto(uscita, scrivi=scrivi)
        finally:
            CRYPTO.clear()
            CRYPTO.update(tenute)
    fonte = {**{n: "HistData" for n in storici}, **{n: "Binance" for n in crypto}}
    mercati = resoconto(uscita, storici + crypto, fonte)
    (uscita / "mercati.json").write_text(json.dumps(mercati, indent=1, ensure_ascii=False), encoding="utf-8")
    pronti = [n for n, x in mercati.items() if x.get("ore buone", 0)]
    scrivi(f"Fatto in {(time.time() - inizio) / 60:.0f} minuti: {len(pronti)} mercati pronti su {len(mercati)}. "
           "Adesso 'Save Version': l'output diventa il dataset di Nameless.")
    return mercati
