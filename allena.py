"""L'allenamento settimanale degli agenti (`spec/allenamento.md`).

    python allena.py                 # una settimana di palestra: prove, esami, rapporto
    python allena.py --processi 2    # con meno processori

Ogni specialista prova da solo a girare di un passo le sue manopole; resta
solo quello che fa guadagnare di piu' con certezza, dentro i paletti. Se
qualcosa cambia: `nvm/vivo/agenti.json` si riscrive, la tabella dei vent'anni
si rifa' e il Capo del bot si riaddestra (come `capo.py --vivo`). Ogni prova
resta in `nvm/vivo/allenamento.json`, e il bot dal vivo manda il rapporto sul
canale equipe al primo avvio dopo l'aggiornamento.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import capo
from nvm.agenti import manopole
from nvm.prova import allenamento

RADICE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--processi", type=int, default=4)
    a = parser.parse_args()
    radice = Path(a.cartella)
    manopole.carica_e_applica()
    adesso = int(time.time())
    basi = capo.ore_storiche(radice)
    impostazioni = {
        "coppie": capo.COPPIE, "dal": capo._istante(capo.DAL), "al": capo._istante(capo.AL + 1),
        "primo": capo.PRIMO_GIUDICATO, "ultimo": capo.AL,
        "romeo": partial(allenamento.ritrovate_da_romeo, radice=radice, catalogo=RADICE / "casi" / "entrate-romeo.csv"),
    }
    memoria = allenamento.leggi_memoria()
    esito = allenamento.allena(basi, impostazioni, memoria["prove"], adesso, processi=a.processi,
                               dire=lambda testo: print(testo, flush=True))
    print(esito.rapporto, flush=True)
    settimana = datetime.fromtimestamp(adesso, tz=timezone.utc).strftime("%G-S%V")
    memoria["prove"] += esito.prove
    memoria["ultimo"] = {"settimana": settimana, "id": adesso, "rapporto": esito.rapporto, "cambiato": esito.cambiato}
    allenamento.salva_memoria(memoria)
    manopole.applica(esito.valori)
    manopole.salva(manopole.attuali())
    # Il Capo del bot si riallena sempre sulla tabella delle manopole in uso: se nessuno e' cambiato,
    # la tabella c'e' gia' e ci vuole poco.
    print("Riaddestro il Capo del bot sulle manopole in uso.", flush=True)
    capo.salva_per_il_vivo(capo.tabella(1, 1.0, radice))


if __name__ == "__main__":
    main()
