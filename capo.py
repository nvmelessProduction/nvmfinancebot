"""Il Capo alla prova (Fase F): le quattro configurazioni di `spec/capo.md`.

    python capo.py                      # tutte e quattro, poi il giudizio
    python capo.py --spread 1.5         # la prova di robustezza, stesso giudizio
    python capo.py --configurazioni 1
    python capo.py --configurazioni 5,6,7,8   # la variante "un gradino sotto"

La prima volta costruisce le tabelle delle operazioni (qualche minuto per
configurazione) e le lascia in dati/tabelle; le volte dopo le riprende.
Ogni giudizio va scritto in `registro/tentativi.md`, anche quando va male.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nvm.agenti.cacciatore import Variante
from nvm.agenti.capo import COLONNE
from nvm.agenti.conferme import SOPRA, contesto, key_level, orario
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO
from nvm.dati.ore import carica as carica_ore
from nvm.dati.spread import allarga
from nvm.prova.base import opera
from nvm.prova.cammino import Tabella, cammino, giudica
from nvm.tempo import TF

RADICE = Path(__file__).resolve().parent
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
# La variante "un gradino sotto" (spec/grilletto.md). Il giornaliero -> 15
# minuti aspetta i minuti di vent'anni: finche' mancano, queste
# configurazioni si misurano su mensile e settimanale, contro la base delle
# stesse coppie.
GRADINO = ((TF.MN, TF.H4), (TF.W1, TF.H1))
CONFIGURAZIONI = {
    1: (Variante.MANUALE, False),
    2: (Variante.MANUALE, True),
    3: (Variante.CHIUSURA_DENTRO, False),
    4: (Variante.CHIUSURA_DENTRO, True),
}
CONFIGURAZIONI |= {n + 4: v for n, v in CONFIGURAZIONI.items()}
K = len(CONFIGURAZIONI)
MINIMO_SCELTE = 300
SOGLIA = 0.10
DAL, AL = 2006, 2023
PRIMO_GIUDICATO = 2008


def _istante(anno: int) -> int:
    return int(datetime(anno, 1, 1, tzinfo=timezone.utc).timestamp())


def tabella(numero: int, spread: float, radice: Path) -> Tabella:
    nome = f"conf{numero}" + (f"-spread{spread:g}" if spread != 1 else "") + ".npz"
    percorso = RADICE / "dati" / "tabelle" / nome
    if percorso.exists():
        return Tabella.carica(percorso)
    variante, stretto = CONFIGURAZIONI[numero]
    dal, al = _istante(DAL), _istante(AL + 1)
    risultati, pareri = [], []
    for strumento in PUNTO:
        base, _ = carica_ore(radice, strumento, dal - 70 * 86400, al + 70 * 86400)
        fine = int(base.t[-1]) + base.passo
        for alto, basso in (GRADINO if numero > 4 else COPPIE):
            alte = costruisci(base, alto).chiuse_entro(fine)
            basse = costruisci(base, basso).chiuse_entro(fine)
            sopra = costruisci(base, SOPRA[alto]).chiuse_entro(fine)
            if spread != 1:
                basse = allarga(basse, spread)
            r = opera(alte, basse, dal, al, variante, stretto)
            risultati += r
            pareri += [(key_level(x.scatto, sopra, basse), orario(x.scatto, basse), contesto(x.scatto, alte, sopra)) for x in r]
            print(f"  conf {numero} {strumento} {alto.value}-{basso.value}: {len(r)} operazioni", flush=True)
    t = Tabella.da(risultati, pareri)
    t.salva(percorso)
    return t


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--configurazioni", default="1,2,3,4")
    parser.add_argument("--spread", type=float, default=1.0)
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    a = parser.parse_args()
    radice = Path(a.cartella)

    base = tabella(1, a.spread, radice)
    giudicati = _giudicati(base)
    # Le operazioni della base con il range giornaliero (colonna "coppia D1-H1").
    giornaliero = base.x[:, COLONNE.index("coppia D1-H1")] == 1
    for numero in map(int, a.configurazioni.split(",")):
        t = base if numero == 1 else tabella(numero, a.spread, radice)
        c = cammino(t, PRIMO_GIUDICATO, AL)
        # Il metro e' sempre la base vera (configurazione 1, senza Capo), negli
        # stessi anni e, per il gradino sotto, sulle stesse coppie.
        metro = giudicati & ~giornaliero if numero > 4 else giudicati
        g = giudica(t.quando[c.scelte], t.erre[c.scelte], base.quando[metro], base.erre[metro], k=K)
        variante, stretto = CONFIGURAZIONI[numero]
        passa = (g.n_scelte >= MINIMO_SCELTE and g.differenza >= SOGLIA and g.basso > 0 and g.anni_concordi >= 0.8)
        print(f"\n== configurazione {numero}: {variante.value}, {'stop stretto' if stretto else 'stop all estremo'}"
              + (", un gradino sotto (solo mensile e settimanale)" if numero > 4 else "")
              + (f", spread x{a.spread:g}" if a.spread != 1 else ""))
        print(f"  tutte le operazioni della configurazione negli anni giudicati: {int(c.giudicati.sum())}, "
              f"R medio {t.erre[c.giudicati].mean():+.3f}")
        print("  " + g.testo())
        print(f"  cancello: {'PASSA' if passa else 'non passa'}")
        ultimo = max(c.fiducia)
        print(f"  fiducia del Capo nel {ultimo} (peso su p1 / su q, colonne standardizzate):")
        for nome, w1, w2 in c.fiducia[ultimo]:
            print(f"    {nome:28} {w1:+.3f} / {w2:+.3f}")


def _giudicati(t: Tabella) -> np.ndarray:
    anni = t.anno
    return (anni >= PRIMO_GIUDICATO) & (anni <= AL)


if __name__ == "__main__":
    main()
