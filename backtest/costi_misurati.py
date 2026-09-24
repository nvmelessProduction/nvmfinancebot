"""Lo spread come si e' visto davvero, per strumento e per ora del giorno.

## Perche' misurato e non stimato

La Fase 1 misura tutti gli R **al netto dei costi**, e senza un costo
credibile un backtest dice quello che si vuole. Su questa strategia pesa piu'
che altrove: gli stop sono stretti -- l'estremo di `N2` dista in media un
decimo di punto percentuale dall'ingresso -- e su uno stop stretto il costo di
un giro vale una frazione grande del rischio.

## Perche' il 90esimo percentile, e per ORA

Non la media. L'oro si allarga al rollover e sulle news, e una media nasconde
proprio i momenti in cui si perde: il 90esimo descrive il costo che si paga
quando le cose vanno come vanno spesso, non come vanno nel caso migliore.

E per **ora del giorno**, perche' lo spread non e' una costante dello
strumento: e' una funzione dell'orario. Un unico numero per `XAUUSD`
mescolerebbe le 10 del mattino con le 23.

## La distorsione che questo modulo esiste per evitare

Finche' l'unico spread registrato era `posizione.spread_ingresso`, il campione
era **distorto**: lo spread veniva letto solo negli istanti in cui il bot
aveva deciso di operare, cioe' plausibilmente i piu' stretti. Un percentile
calcolato li' descrive il momento dell'apertura, non l'ora del giorno -- e
moltiplicarlo per un fattore di sicurezza non raddrizza una distorsione, la
scala soltanto. Da qui il campionamento a ritmo regolare della Fase 0.

## Il ripiego, e perche' e' verso l'alto

Un'ora con pochi campioni non ha un percentile affidabile. In quel caso si
ripiega sul percentile di TUTTO lo strumento, e se manca anche quello si
prende il piu' largo fra gli strumenti noti. Il ripiego va sempre verso il
costo PIU' ALTO: sbagliare per eccesso scarta un setup buono, sbagliare per
difetto valida una strategia che dal vivo non regge.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import impostazioni                          # noqa: E402

# Sotto questo numero di misure l'ora non ha un percentile suo.
CAMPIONI_MINIMI_PER_ORA: int = 20

# Il percentile: vedi il docstring.
PERCENTILE: float = 0.90


def _percentile(valori: list[float], frazione: float) -> float:
    """Il percentile per interpolazione, senza dipendenze esterne."""
    if not valori:
        raise ValueError("percentile di un insieme vuoto")
    ordinati = sorted(valori)
    if len(ordinati) == 1:
        return ordinati[0]
    posto = frazione * (len(ordinati) - 1)
    sotto = int(posto)
    sopra = min(sotto + 1, len(ordinati) - 1)
    peso = posto - sotto
    return ordinati[sotto] * (1 - peso) + ordinati[sopra] * peso


@dataclass
class TabellaSpread:
    """Lo spread al 90esimo percentile, per strumento e ora."""

    per_ora: dict[tuple[str, int], float] = field(default_factory=dict)
    per_strumento: dict[str, float] = field(default_factory=dict)
    campioni: int = 0
    il_piu_largo: float = 0.0

    def spread(self, simbolo: str, ora: int) -> float:
        """Il costo di spread da usare per questo strumento a quest'ora.

        Il ripiego va sempre verso il costo piu' alto: sbagliare per eccesso
        scarta un setup buono, sbagliare per difetto valida una strategia che
        dal vivo non regge.
        """
        preciso = self.per_ora.get((simbolo, ora))
        if preciso is not None:
            return preciso
        di_strumento = self.per_strumento.get(simbolo)
        if di_strumento is not None:
            return di_strumento
        return self.il_piu_largo

    def copertura(self) -> str:
        """Quanto della tabella e' misurato e quanto e' ripiego."""
        ore_viste = len({ora for _, ora in self.per_ora})
        return (f"{self.campioni:,} misure, {len(self.per_strumento)} strumenti, "
                f"{len(self.per_ora)} caselle strumento-ora su "
                f"{len(self.per_strumento) * 24} possibili ({ore_viste} ore viste)")


def costruisci(db: Optional[str] = None,
               minimi: int = CAMPIONI_MINIMI_PER_ORA) -> TabellaSpread:
    """Legge le misure campionate e costruisce la tabella."""
    percorso = db or impostazioni().DB_PATH
    conn = sqlite3.connect(f"file:{percorso}?mode=ro", uri=True)
    try:
        righe = conn.execute(
            "SELECT simbolo, CAST(substr(misurato_utc, 12, 2) AS INTEGER), spread "
            "FROM spread WHERE spread >= 0").fetchall()
    finally:
        conn.close()

    per_ora: dict[tuple[str, int], list[float]] = {}
    per_strumento: dict[str, list[float]] = {}
    for simbolo, ora, valore in righe:
        per_ora.setdefault((str(simbolo), int(ora)), []).append(float(valore))
        per_strumento.setdefault(str(simbolo), []).append(float(valore))

    tabella = TabellaSpread(campioni=len(righe))
    for chiave, valori in per_ora.items():
        if len(valori) >= minimi:
            tabella.per_ora[chiave] = _percentile(valori, PERCENTILE)
    for simbolo, valori in per_strumento.items():
        tabella.per_strumento[simbolo] = _percentile(valori, PERCENTILE)
    if tabella.per_strumento:
        tabella.il_piu_largo = max(tabella.per_strumento.values())
    return tabella


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fattore", type=float, default=1.0,
                   help="moltiplicatore per la prova di robustezza (1.5)")
    a = p.parse_args()

    t = costruisci()
    print(t.copertura())
    print()
    if not t.per_strumento:
        print("nessuna misura: il campionamento non ha ancora raccolto nulla")
        return 1

    print(f"spread al {PERCENTILE * 100:.0f}esimo percentile"
          + (f", moltiplicato per {a.fattore}" if a.fattore != 1.0 else ""))
    print(f"  {'strumento':10} {'tutto il giorno':>16}   {'per ora (min - max)':>22}")
    for simbolo in sorted(t.per_strumento):
        tutto = t.per_strumento[simbolo] * a.fattore
        ore = [v * a.fattore for (s, _), v in t.per_ora.items() if s == simbolo]
        se_ore = (f"{min(ore):.5f} - {max(ore):.5f}  ({len(ore)} ore)"
                  if ore else "nessuna ora con abbastanza misure")
        print(f"  {simbolo:10} {tutto:>16.5f}   {se_ore:>22}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


# ===========================================================================
# Il costo completo di un lato, in unita' di prezzo
# ===========================================================================
#
# Lo spread da solo non basta, e su questo conto e' il pezzo piccolo: e' un
# conto RAW, dove `bid == ask` e' normale e il 90esimo percentile di EURUSD
# vale ZERO. Fermarsi li' direbbe che operare su EURUSD e' gratis.
#
# Il costo vero e' spread + commissione + slippage. La commissione e' quella
# MISURATA sul conto -- 4,06 EUR per lotto andata e ritorno, contro i 6 $ che
# la tabella teorica di `costi.py` assume -- e va espressa in frazione di
# prezzo per essere sommata allo spread.

# Quante unita' di prezzo si perdono in esecuzione, oltre allo spread. Zero e'
# una scelta di chi chiama: qui non si inventa un numero che nessuno ha
# misurato. Chi vuole la prova di robustezza moltiplica tutto per 1,5.
SLIPPAGE_PREDEFINITO: float = 0.0

# Unita' per lotto standard, e se il contratto e' gia' in dollari. Stessa
# tabella di `costi.py`, che e' dove il ragionamento vive.
CONTRATTI: dict[str, tuple[float, bool]] = {
    "XAUUSD": (100.0, True),
    "EURUSD": (100_000.0, True),
    "GBPUSD": (100_000.0, True),
    "AUDUSD": (100_000.0, True),
    "USDCHF": (100_000.0, False),
    "USDJPY": (100_000.0, False),
}


def costo_per_lato(
    tabella: TabellaSpread,
    strumento: str,
    simbolo_broker: str,
    prezzo: float,
    ora: int,
    slippage: float = SLIPPAGE_PREDEFINITO,
    fattore: float = 1.0,
) -> float:
    """Quanto costa UN lato, in unita' di prezzo.

    Le etichette lo pagano due volte -- all'entrata e all'uscita -- quindi qui
    si restituisce la meta' del giro completo.

    `fattore` e' la prova di robustezza: il risultato della Fase 2 deve
    reggere anche a 1,5. Se regge solo col costo nominale, non e' un si'.
    """
    from core.parametri import COMMISSIONE_PER_LOTTO

    spread = tabella.spread(simbolo_broker, ora)

    contratto, base_e_dollaro = CONTRATTI.get(strumento, (100_000.0, True))
    nozionale = contratto * prezzo if base_e_dollaro else contratto
    # La commissione e' per LOTTO e per giro completo: in frazione di prezzo
    # diventa commissione / nozionale, e moltiplicata per il prezzo torna in
    # unita' di prezzo.
    commissione_in_prezzo = (COMMISSIONE_PER_LOTTO / nozionale) * prezzo

    giro = spread + commissione_in_prezzo + slippage
    return (giro / 2.0) * fattore
