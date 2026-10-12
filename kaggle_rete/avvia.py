"""Tutta la scuola in un comando, per la cella del notebook di Kaggle:

    from kaggle_rete.avvia import tutto
    tutto(ore=6)

Scarica lo storico da HistData (circa un'ora e un quarto), allena la rete sulla scheda grafica per `ore` ore e fa
l'esame dal 2023. Nella scheda Output di Kaggle restano `occhi.pt` (la rete) e `resoconto.json` (l'esame).
"""

from __future__ import annotations

import time
from pathlib import Path

from kaggle_rete.allena import allena, stampa
from kaggle_rete.histdata import NOMI, scarica_tutto


def tutto(ore: float = 6.0, strumenti: list[str] | None = None, dati: Path = Path("/tmp/dati"),
          uscita: Path = Path("/kaggle/working"), serve_scheda: bool = True) -> dict:
    import torch
    if serve_scheda and not torch.cuda.is_available():
        raise SystemExit("Manca la scheda grafica: menu Settings -> Accelerator -> GPU, poi rilancia")
    strumenti = strumenti or list(NOMI)
    print(f"{len(strumenti)} strumenti: {' '.join(strumenti)}", flush=True)
    inizio = time.time()
    scarica_tutto(strumenti, dati, scrivi=lambda t: print(t, flush=True))
    print(f"storico scaricato in {(time.time() - inizio) / 60:.0f} minuti", flush=True)
    resoconto = allena(dati, strumenti, uscita, ore=ore, scrivi=lambda t: print(t, flush=True))
    stampa(resoconto)
    return resoconto


def passo2(minuti: float = 60, minuti_senza_occhi: float = 20, dati: Path = Path("/tmp/dati"),
           uscita: Path = Path("/kaggle/working")) -> dict:
    """Il passo 2 (la scuola dell'esperienza): riscarica lo storico, prende i casi gia' preparati (`casi.npz`) e gli
    occhi della prima notte (`occhi.pt`) che stanno nel pacchetto, allena e fa l'esame contro il bot."""
    import torch
    from kaggle_rete import trader
    if not torch.cuda.is_available():
        raise SystemExit("Manca la scheda grafica: menu Settings -> Accelerator -> GPU, poi rilancia")
    qui = Path(__file__).resolve().parent
    inizio = time.time()
    scarica_tutto(list(NOMI), dati, scrivi=lambda t: print(t, flush=True))
    print(f"storico scaricato in {(time.time() - inizio) / 60:.0f} minuti", flush=True)
    return trader.tutto(dati, qui / "casi.npz", qui / "occhi.pt", uscita, minuti, minuti_senza_occhi,
                        scrivi=lambda t: print(t, flush=True))
