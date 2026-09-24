"""Scarica lo storico al minuto da Dukascopy, con bid e ask. Gira sulla VPS.

    python scarica.py                          # minuti, sei strumenti, dal 2006 a oggi
    python scarica.py --ore                    # solo le ore: 50 volte meno richieste
    python scarica.py --strumenti EURUSD --dal 2024-01 --al 2024-03

Le ore bastano per le coppie mensile -> giornaliero, settimanale -> 4 ore e
giornaliero -> 1 ora. La coppia 4 ore -> 15 minuti ha bisogno dei minuti.

Riprende da dove si era fermato: si puo' interrompere e rilanciare quando si
vuole. Alla fine controlla i dati e scrive il rapporto.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from nvm.dati.controlli import controlla
from nvm.dati.dukascopy import mesi, scarica
from nvm.dati.minuti import PUNTO, Minuti, file_del_mese

RADICE = Path(__file__).resolve().parent


def main() -> None:
    oggi = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strumenti", default=",".join(PUNTO), help="separati da virgola")
    parser.add_argument("--dal", default="2006-01", help="primo mese, AAAA-MM")
    parser.add_argument("--al", default=f"{oggi:%Y-%m}", help="ultimo mese, AAAA-MM")
    parser.add_argument("--ore", action="store_true", help="scarica le ore invece dei minuti")
    parser.add_argument("--pausa", type=float, default=0.5, help="secondi fra una richiesta e l'altra")
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--rapporto", default=str(RADICE / "dati" / "rapporto-dati.txt"))
    argomenti = parser.parse_args()

    strumenti = [s.strip().upper() for s in argomenti.strumenti.split(",") if s.strip()]
    sconosciuti = [s for s in strumenti if s not in PUNTO]
    if sconosciuti:
        parser.error(f"strumenti sconosciuti: {', '.join(sconosciuti)}")

    radice = Path(argomenti.cartella)
    unita = "ore" if argomenti.ore else "minuti"
    scarica(strumenti, argomenti.dal, argomenti.al, radice / unita, radice / "cache", ore=argomenti.ore, pausa=argomenti.pausa)

    righe = []
    for strumento in strumenti:
        pezzi = []
        for anno, mese in mesi(argomenti.dal, argomenti.al):
            percorso = file_del_mese(radice / unita, strumento, anno, mese)
            if percorso.exists():
                pezzi.append(Minuti.carica(percorso))
        pezzi = [p for p in pezzi if len(p)]
        if pezzi:
            righe.append(controlla(Minuti.unisci(pezzi)).testo())
    Path(argomenti.rapporto).write_text("\n\n".join(righe) + "\n", encoding="utf-8")
    print(f"rapporto dei controlli: {argomenti.rapporto}")


if __name__ == "__main__":
    main()
