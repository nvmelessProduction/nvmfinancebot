"""Una cella di Kaggle che porta con se' il codice nuovo: niente pacchetti da scaricare e ricaricare.

    python -m kaggle_rete.cella_unica occhi > cella.txt

Il proprietario scarica male i file grandi (13/10/2026: *"non riesco a scaricare lo zip, la connessione muore"*). La
cella prende il codice che e' gia' su Kaggle (il dataset `nvm-codice`, zip o cartella), ci aggiunge i file nuovi
scritti dentro la cella (compressi, con un'impronta: se la cella e' copiata a meta' lo dice), controlla la scheda
grafica e i dati, e lancia la scuola. I file nuovi si prendono dall'ultimo commit (`git show HEAD:...`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import lzma
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent

# Per ogni fase: i file nuovi rispetto al codice gia' su Kaggle (quello della fase 0) e cosa lanciare.
FASI = {
    "occhi": {"titolo": "NAMELESS FASE 1: GLI OCCHI",
              "file": ["nvm/nameless/__init__.py", "nvm/nameless/sensi.py", "nvm/nameless/occhi.py",
                       "kaggle_rete/occhi.py"],
              "lancia": "from kaggle_rete.occhi import scuola\nscuola(ore=3)"},
}


def cella(fase: str) -> str:
    f = FASI[fase]
    dentro = {p: subprocess.run(["git", "-C", str(RADICE), "show", f"HEAD:{p}"], capture_output=True, text=True,
                                check=True).stdout for p in f["file"]}
    grezzo = lzma.compress(json.dumps(dentro).encode(), preset=9)
    b = base64.b64encode(grezzo).decode()
    righe = "\n".join(b[i:i + 100] for i in range(0, len(b), 100))
    impronta = hashlib.sha256(grezzo).hexdigest()[:16]
    return f'''# {f["titolo"]}. Serve la GPU e due input: nvm-codice e il notebook dei dati.
import base64, glob, hashlib, json, lzma, os, shutil, sys
CODICE = '/tmp/codice'
shutil.rmtree(CODICE, ignore_errors=True)
z = glob.glob('/kaggle/input/**/nvm-codice*.zip', recursive=True)
if z:
    shutil.unpack_archive(z[0], CODICE)
else:
    d = [os.path.dirname(os.path.dirname(p)) for p in glob.glob('/kaggle/input/**/kaggle_rete/dati.py', recursive=True)]
    assert d, "MANCA IL CODICE: a destra Add Input, aggiungi il dataset nvm-codice"
    shutil.copytree(d[0], CODICE)
NUOVI = """
{righe}
"""
try:
    grezzo = base64.b64decode("".join(NUOVI.split()))
except Exception:
    grezzo = b""
assert hashlib.sha256(grezzo).hexdigest()[:16] == "{impronta}", "CELLA INCOMPLETA: ricopiala tutta"
for nome, testo in json.loads(lzma.decompress(grezzo)).items():
    os.makedirs(os.path.dirname(os.path.join(CODICE, nome)), exist_ok=True)
    open(os.path.join(CODICE, nome), "w", encoding="utf-8").write(testo)
sys.path.insert(0, CODICE)
import torch
assert torch.cuda.is_available(), "MANCA LA GPU: a destra Settings, Accelerator, GPU; poi rilancia"
assert glob.glob('/kaggle/input/**/ore_bid', recursive=True), \\
    "MANCANO I DATI: a destra Add Input, aggiungi il notebook dei dati"
{f["lancia"]}
'''


if __name__ == "__main__":
    sys.stdout.write(cella(sys.argv[1] if len(sys.argv) > 1 else "occhi"))
