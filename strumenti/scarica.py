"""Scarica lo storico al minuto da Dukascopy, con bid e ask. Gira sulla VPS.

    python -m strumenti.scarica                          # minuti, i sei strumenti di partenza, dal 2006 a oggi
    python -m strumenti.scarica --strumenti nuovi --ore  # le ore degli strumenti nuovi (nvm/dati/strumenti.py)
    python -m strumenti.scarica --ore                    # solo le ore: 50 volte meno richieste
    python -m strumenti.scarica --strumenti EURUSD --dal 2024-01 --al 2024-03

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
from nvm.dati.dukascopy import Scaricatore, completa_con_ask, mesi, mesi_a_campione, scarica
from nvm.dati.minuti import PUNTO, Minuti, file_del_mese
from nvm.dati.strumenti import ALTRI_NUOVI, BASE, COPPIE_NUOVE, NUOVI

RADICE = Path(__file__).resolve().parent.parent


def main() -> None:
    oggi = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strumenti", default="base",
                        help="separati da virgola, oppure: base (i sei di partenza), nuovi (tutti gli altri), "
                             "coppie (le altre coppie forex), altri (argento, petrolio, indici, crypto), tutti")
    parser.add_argument("--dal", default="2006-01", help="primo mese, AAAA-MM")
    parser.add_argument("--al", default=f"{oggi:%Y-%m}", help="ultimo mese, AAAA-MM")
    parser.add_argument("--ore", action="store_true", help="scarica le ore invece dei minuti")
    parser.add_argument("--pausa", type=float, default=0.5, help="secondi fra una richiesta e l'altra")
    parser.add_argument("--solo-ask", action="store_true",
                        help="completa con l'ask i mesi che hanno gia' il bid in ore_bid (meta' delle richieste)")
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--rapporto", default=str(RADICE / "dati" / "rapporto-dati.txt"))
    argomenti = parser.parse_args()

    gruppi = {"BASE": list(BASE), "NUOVI": list(NUOVI), "COPPIE": list(COPPIE_NUOVE), "ALTRI": list(ALTRI_NUOVI),
              "TUTTI": list(PUNTO)}
    strumenti = [x for s in argomenti.strumenti.split(",") if s.strip() for x in gruppi.get(s.strip().upper(), [s.strip().upper()])]
    sconosciuti = [s for s in strumenti if s not in PUNTO]
    if sconosciuti:
        parser.error(f"strumenti sconosciuti: {', '.join(sconosciuti)}")

    radice = Path(argomenti.cartella)
    if argomenti.solo_ask:
        scaricatore = Scaricatore(radice / "cache", pausa=argomenti.pausa)
        for anno, mese in mesi_a_campione(argomenti.dal, argomenti.al):
            for strumento in strumenti:
                fatto = completa_con_ask(scaricatore, radice, strumento, anno, mese)
                print(f"{strumento} {anno}-{mese:02d}: {'esatto' if fatto else 'resta stimato'}", flush=True)
        print(f"fatto: {scaricatore.richieste} richieste a Dukascopy")
        return
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
