"""Prende i dati spediti dalla VPS (`consegna.py`, ramo `dati-vps`). Gira da Claude, prima della palestra.

    python importa_vps.py

I quarti d'ora dei vent'anni vanno in `dati/grezzi/quarti/`, un file per
strumento e anno; le ore delle coppie nuove in `dati/grezzi/ore/`, un file
per mese come le altre; lo stato del bot dal vivo in `dati/vps/vivo/`. Se il
ramo non c'e' ancora, lo dice e non fa niente.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from nvm.dati.minuti import Minuti, file_del_mese

RADICE = Path(__file__).resolve().parent
RAMO = "dati-vps"


def apri_pacco(dati: bytes, dove: Path) -> int:
    """Un pacco dei video di Romeo (`video.py`): i file nuovi sotto `video/`."""
    import io
    import zipfile
    fatti = 0
    with zipfile.ZipFile(io.BytesIO(dati)) as z:
        for nome in z.namelist():
            if not nome.startswith("video/") or nome.endswith("/") or ".." in nome.split("/"):
                continue
            destinazione = dove / nome
            if not destinazione.exists():
                destinazione.parent.mkdir(parents=True, exist_ok=True)
                destinazione.write_bytes(z.read(nome))
                fatti += 1
    return fatti


def main() -> None:
    r = subprocess.run(["git", "fetch", "-q", "origin", f"{RAMO}:refs/remotes/origin/{RAMO}"], cwd=RADICE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Il ramo {RAMO} non c'e' ancora: la VPS non ha spedito niente (VPS.md).")
    elenco = subprocess.run(["git", "ls-tree", "-r", "--name-only", f"origin/{RAMO}"], cwd=RADICE,
                            capture_output=True, text=True, check=True).stdout.split()
    quarti = vivi = mesi = video = 0
    for nome in elenco:
        contenuto = lambda: subprocess.run(["git", "show", f"origin/{RAMO}:{nome}"], cwd=RADICE, capture_output=True,
                                           check=True).stdout
        if nome.startswith("ore/"):
            # Le ore delle coppie nuove, un file per anno: si rimettono un file per mese, come le altre.
            # I mesi che ci sono gia' (l'archivio dei sei di partenza) non si toccano.
            with tempfile.TemporaryDirectory() as cartella:
                f = Path(cartella) / "anno.npz"
                f.write_bytes(contenuto())
                mesi += salva_mesi_nuovi(Minuti.carica(f), RADICE / "dati" / "grezzi" / "ore")
            continue
        if nome.startswith("quarti/"):
            destinazione = RADICE / "dati" / "grezzi" / nome
            quarti += 1
        elif nome.startswith("vivo/"):
            destinazione = RADICE / "dati" / "vps" / nome
            vivi += 1
        elif nome.startswith("video/"):
            # I fotogrammi e le parole dei video di Romeo (`video.py`): solo quelli nuovi.
            destinazione = RADICE / "dati" / "vps" / nome
            if destinazione.exists():
                continue
            video += 1
        elif nome.startswith("video_romeo") and nome.endswith(".zip"):
            # I pacchi fatti sul computer di casa e caricati dal sito di GitHub: si aprono in dati/vps/video.
            video += apri_pacco(contenuto(), RADICE / "dati" / "vps")
            continue
        else:
            continue
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        destinazione.write_bytes(contenuto())
    print(f"Dalla VPS: {quarti} file di quarti d'ora, {mesi} mesi di ore nuovi, {vivi} file del bot dal vivo, "
          f"{video} file dei video di Romeo.")


def salva_mesi_nuovi(ore: Minuti, cartella: Path) -> int:
    """Un file per mese UTC, solo per i mesi che mancano. Restituisce quanti file nuovi."""
    mesi = ore.t.astype("datetime64[s]").astype("datetime64[M]")
    n = 0
    for mese in np.unique(mesi):
        anno, m = int(str(mese)[:4]), int(str(mese)[5:7])
        percorso = file_del_mese(cartella, ore.strumento, anno, m)
        if percorso.exists():
            continue
        dentro = mesi == mese
        Minuti(ore.strumento, ore.t[dentro], ore.bid[dentro], ore.ask[dentro],
               ore.volume_bid[dentro], ore.volume_ask[dentro], ore.passo).salva(percorso)
        n += 1
    return n


if __name__ == "__main__":
    main()
