"""Prende i dati spediti dalla VPS (`consegna.py`, ramo `dati-vps`). Gira da Claude, prima della palestra.

    python importa_vps.py

I quarti d'ora dei vent'anni vanno in `dati/grezzi/quarti/`, un file per
strumento e anno; lo stato del bot dal vivo in `dati/vps/vivo/`. Se il ramo
non c'e' ancora, lo dice e non fa niente.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
RAMO = "dati-vps"


def main() -> None:
    r = subprocess.run(["git", "fetch", "-q", "origin", f"{RAMO}:refs/remotes/origin/{RAMO}"], cwd=RADICE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Il ramo {RAMO} non c'e' ancora: la VPS non ha spedito niente (VPS.md).")
    elenco = subprocess.run(["git", "ls-tree", "-r", "--name-only", f"origin/{RAMO}"], cwd=RADICE,
                            capture_output=True, text=True, check=True).stdout.split()
    quarti = vivi = 0
    for nome in elenco:
        if nome.startswith("quarti/"):
            destinazione = RADICE / "dati" / "grezzi" / nome
            quarti += 1
        elif nome.startswith("vivo/"):
            destinazione = RADICE / "dati" / "vps" / nome
            vivi += 1
        else:
            continue
        contenuto = subprocess.run(["git", "show", f"origin/{RAMO}:{nome}"], cwd=RADICE, capture_output=True,
                                   check=True).stdout
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        destinazione.write_bytes(contenuto)
    print(f"Dalla VPS: {quarti} file di quarti d'ora, {vivi} file del bot dal vivo.")


if __name__ == "__main__":
    main()
