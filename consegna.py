"""Manda alla palestra i dati che nascono sulla VPS. Gira sulla VPS.

    python consegna.py              # quarti d'ora, ore delle coppie nuove e settimane dal vivo
    python consegna.py --solo-vivo  # solo le settimane dal vivo (lo fa il bot ogni sabato)

La palestra (`allena.py`) gira da Claude, e da li' Dukascopy blocca i download:
i minuti si scaricano sulla VPS (`scarica.bat`, `VPS.md`). Questo script ne fa
candele da 15 minuti, un file per strumento e anno (quindici volte piu'
leggere), ci aggiunge le ore scaricate (le coppie nuove), lo stato del bot dal vivo (decisioni, risultati,
diario degli agenti) e spedisce tutto su GitHub, nel ramo `dati-vps`: un ramo
a parte, che il bot non legge e che non tocca il codice.

Per spedire serve `GITHUB_TOKEN` nel file `.env` (un token di GitHub che puo'
scrivere solo in questo repository, `VPS.md`). Il token non si stampa mai e
non entra mai nel repository.
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, PUNTO, Minuti, cartella_strumento
from nvm.vivo.ambiente import leggi_env

RADICE = Path(__file__).resolve().parent
USCITA = RADICE / "dati" / "consegna"
RAMO = "dati-vps"
QUARTO = 900


def a_quarti(m: Minuti, passo: int = QUARTO) -> Minuti:
    """Candele da 15 minuti (o da `passo` secondi) dai minuti: apertura la prima, massimo e
    minimo, chiusura l'ultima."""
    if not len(m):
        return Minuti.vuoti(m.strumento, passo)
    blocco = m.t // passo * passo
    inizi = np.flatnonzero(np.r_[True, blocco[1:] != blocco[:-1]])
    fini = np.r_[inizi[1:], len(m.t)] - 1

    def ohlc(p: np.ndarray) -> np.ndarray:
        return np.column_stack([p[inizi, APERTURA], np.maximum.reduceat(p[:, MASSIMO], inizi),
                                np.minimum.reduceat(p[:, MINIMO], inizi), p[fini, CHIUSURA]]).astype(p.dtype)

    return Minuti(m.strumento, blocco[inizi].astype(np.int64), ohlc(m.bid), ohlc(m.ask),
                  np.add.reduceat(m.volume_bid, inizi), np.add.reduceat(m.volume_ask, inizi), passo)


def _per_anno(sorgente: Path, destinazione: Path, trasforma) -> int:
    """Un file per strumento e anno dai file mensili; si rifanno solo gli anni con mesi nuovi."""
    fatti = 0
    for strumento in PUNTO:
        per_anno: dict[int, list[Path]] = defaultdict(list)
        for f in sorted(cartella_strumento(sorgente, strumento).glob(f"{strumento}-*.npz")):
            per_anno[int(f.stem.split("-")[1])].append(f)
        for anno, mesi in per_anno.items():
            finale = destinazione / strumento / f"{strumento}-{anno}.npz"
            if finale.exists() and finale.stat().st_mtime >= max(f.stat().st_mtime for f in mesi):
                continue
            pezzi = [p for p in (trasforma(Minuti.carica(f)) for f in mesi) if len(p)]
            if not pezzi:
                continue
            Minuti.unisci(pezzi).salva(finale)
            fatti += 1
    return fatti


def quarti(grezzi: Path, uscita: Path) -> int:
    """I quarti d'ora dai minuti scaricati: un file per strumento e anno."""
    return _per_anno(grezzi / "minuti", uscita / "quarti", a_quarti)


def ore(grezzi: Path, uscita: Path) -> int:
    """Le ore scaricate (`scarica.py --ore`, per le coppie nuove): un file per strumento e anno."""
    return _per_anno(grezzi / "ore", uscita / "ore", lambda m: m)


def segreti(env: dict[str, str]) -> list[str]:
    """I valori del .env che non devono mai uscire dalla VPS: token, password, chiavi, login."""
    parole = ("TOKEN", "PASS", "SECRET", "KEY", "LOGIN")
    return [v for k, v in env.items() if any(p in k.upper() for p in parole) and len(v) >= 4]


def vivo(cartella_vivo: Path, uscita: Path, nascosti: list[str] = ()) -> list[str]:
    """Lo stato e il registro del bot dal vivo: decisioni, risultati, diario. Se per caso un
    valore segreto del .env ci fosse finito dentro (in un messaggio d'errore, per esempio),
    al suo posto si scrive ***: i segreti non escono mai dalla VPS."""
    copiati = []
    for nome in ("stato.json", "registro.jsonl", "seguite_finite.jsonl", "libro.jsonl"):
        sorgente = cartella_vivo / nome
        if sorgente.exists():
            testo = sorgente.read_text(encoding="utf-8", errors="replace")
            for s in sorted(nascosti, key=len, reverse=True):
                testo = testo.replace(s, "***")
            (uscita / "vivo").mkdir(parents=True, exist_ok=True)
            (uscita / "vivo" / nome).write_text(testo, encoding="utf-8")
            copiati.append(nome)
    return copiati


def _git(cartella: Path, *argomenti: str, ambiente: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *argomenti], cwd=cartella, capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(ambiente or {})})


def _con_token(token: str, indirizzo: str) -> dict:
    """Il token passa a git in un'intestazione, dalle variabili d'ambiente: non compare mai
    nei comandi, nei messaggi o nella configurazione salvata."""
    if not token or not indirizzo.startswith("https://"):
        return {}
    base = "/".join(indirizzo.split("/")[:3]) + "/"
    chiave = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"http.{base}.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {chiave}"}


def spedisci(uscita: Path, indirizzo: str, token: str) -> str:
    """Un commit con tutto e una spinta sul ramo `dati-vps`. Solo questo script scrive su quel ramo:
    se GitHub ha qualcosa di diverso, vince la VPS."""
    auth = _con_token(token, indirizzo)
    if not (uscita / ".git").exists():
        _git(uscita, "init", "-q")
        _git(uscita, "checkout", "-q", "-b", RAMO)
    _git(uscita, "config", "user.name", "bot della VPS")
    _git(uscita, "config", "user.email", "bot@vps.invalid")
    _git(uscita, "add", "-A")
    if _git(uscita, "diff", "--cached", "--quiet").returncode == 0 and _git(uscita, "rev-parse", "HEAD").returncode == 0:
        fatto = "niente di nuovo"
    else:
        _git(uscita, "commit", "-q", "-m", "Dati dalla VPS")
        fatto = "spedito"
    r = _git(uscita, "push", "-q", indirizzo, f"HEAD:refs/heads/{RAMO}", ambiente=auth)
    if r.returncode != 0:
        # Il ramo su GitHub e' andato avanti per conto suo: si riparte da li' con i dati di adesso.
        _git(uscita, "fetch", "-q", indirizzo, RAMO, ambiente=auth)
        _git(uscita, "reset", "-q", "--soft", "FETCH_HEAD")
        _git(uscita, "commit", "-q", "-m", "Dati dalla VPS")
        r = _git(uscita, "push", "-q", indirizzo, f"HEAD:refs/heads/{RAMO}", ambiente=auth)
    if r.returncode != 0:
        errore = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError("GitHub non accetta i dati: " + (errore[-1] if errore else "motivo sconosciuto")
                           + ". Controlla il GITHUB_TOKEN nel .env (VPS.md).")
    return fatto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo-vivo", action="store_true", help="solo lo stato del bot dal vivo")
    parser.add_argument("--grezzi", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--vivo", default=str(RADICE / "dati" / "vivo"))
    parser.add_argument("--uscita", default=str(USCITA))
    parser.add_argument("--indirizzo", default="", help="dove spedire (di solito si ricava da solo)")
    a = parser.parse_args()
    uscita = Path(a.uscita)
    uscita.mkdir(parents=True, exist_ok=True)
    if not a.solo_vivo:
        print("Preparo i quarti d'ora dai minuti scaricati...", flush=True)
        print(f"  {quarti(Path(a.grezzi), uscita)} anni nuovi o aggiornati", flush=True)
        print("Preparo le ore scaricate...", flush=True)
        print(f"  {ore(Path(a.grezzi), uscita)} anni nuovi o aggiornati", flush=True)
    env = leggi_env(RADICE / ".env")
    copiati = vivo(Path(a.vivo), uscita, segreti(env))
    print(f"Stato del bot dal vivo: {', '.join(copiati) or 'niente (il bot non ha ancora girato qui)'}", flush=True)
    token = env.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    indirizzo = a.indirizzo or _git(RADICE, "remote", "get-url", "origin").stdout.strip()
    if not token and indirizzo.startswith("https://"):
        sys.exit("Manca GITHUB_TOKEN nel file .env: i dati sono pronti in dati\\consegna ma non spediti (VPS.md).")
    print(f"GitHub: {spedisci(uscita, indirizzo, token)}.", flush=True)


if __name__ == "__main__":
    main()
