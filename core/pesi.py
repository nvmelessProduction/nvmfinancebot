"""Dagli otto responsi a una probabilita', e da li' a un si' o un no.

## Cos'e' questo file, e cosa NON e'

E' il lato **di produzione** dell'apprendimento: prende il responso che
`conferme_di_romeo` gia' produce, lo trasforma in numeri, applica dei pesi e
restituisce una probabilita' di arrivare al bersaglio. I pesi li stima
`backtest/addestra.py`, offline, e arrivano qui dentro un file.

Qui **non si impara**. Imparare mentre si opera vorrebbe dire cambiare le
regole con cui si giudica un'operazione mentre quell'operazione e' aperta, e
nessuno saprebbe piu' dire cosa ha deciso cosa.

## Perche' la codifica sta QUI e non nell'addestratore

La codifica -- come `True`, `False` e `None` diventano numeri -- e' il punto
esatto in cui due copie della stessa regola divergono senza che nessuno se ne
accorga. Se chi addestra codificasse `None` come zero e chi decide lo
codificasse come `-1`, i pesi sarebbero giusti per un mondo e applicati a un
altro, e il bot opererebbe con numeri che sembrano sensati.

Quindi c'e' **una** funzione, `caratteristiche_numeriche`, e l'addestratore la
importa da qui. Non e' una scelta estetica: e' la famiglia di difetti che
questo progetto ha gia' trovato cinque volte.

## `None` non e' `False`

Ogni conferma diventa **due** colonne, `si` e `no`. `None` le mette entrambe a
zero, cioe' e' il caso di riferimento. Con una colonna sola "non lo so"
finirebbe schiacciato su uno dei due, e nel campo di prova "non lo so" e'
frequente: `CRT-10` risponde `None` sul 98% dei CRT, `CRT-11` sul 34%.

## La regola d'ingresso

    p x RR - (1 - p) - costi > 0

Non "p > qualcosa". Una probabilita' bassa su un rapporto alto puo' convenire,
e una probabilita' alta su un rapporto misero puo' non convenire: e' il
rapporto che decide quanto vale avere ragione. Per questo `RR` e' anche una
**caratteristica**: senza, `p` sarebbe una media su tutti i rapporti e la
moltiplicazione non avrebbe senso.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

# Le otto conferme, nell'ordine in cui entrano nel vettore. L'ordine conta:
# i pesi sono salvati per nome, ma un vettore costruito in ordine diverso
# darebbe un altro modello con gli stessi numeri.
LE_OTTO: tuple[str, ...] = ("CRT-06", "CRT-10", "CRT-11", "CRT-12",
                            "CRT-15", "CRT-17", "CRT-18", "CRT-20")


def nomi_delle_colonne() -> tuple[str, ...]:
    """Come si chiama ogni posizione del vettore.

    Serve a leggere i pesi come testo: un vettore di numeri senza nomi non e'
    controllabile da nessuno, e un modello che nessuno puo' controllare non
    puo' essere messo a operare.
    """
    nomi: list[str] = []
    for regola in LE_OTTO:
        nomi.append(f"{regola}=si")
        nomi.append(f"{regola}=no")
    nomi.append("allineati>=1")
    nomi.append("allineati>=2")
    nomi.append("log(RR)")
    return tuple(nomi)


def caratteristiche_numeriche(
    responso: Mapping[str, Optional[bool]],
    allineati: Optional[int],
    rapporto: float,
) -> list[float]:
    """Il vettore, da qui in poi uguale per chi impara e per chi decide.

    `responso` e' esattamente cio' che `conferme_di_romeo` restituisce.
    `allineati` e' il conteggio di `CRT-06` (`None` = non lo so, non zero).
    `rapporto` e' `|target - ingresso| / |ingresso - stop|`.
    """
    vettore: list[float] = []
    for regola in LE_OTTO:
        valore = responso.get(regola)
        vettore.append(1.0 if valore is True else 0.0)
        vettore.append(1.0 if valore is False else 0.0)
    # Il conteggio di CRT-06 e' informazione in piu' rispetto al si'/no: le
    # fonti dicono "TRE modelli allineati", non "almeno uno".
    vettore.append(1.0 if (allineati or 0) >= 1 else 0.0)
    vettore.append(1.0 if (allineati or 0) >= 2 else 0.0)
    # Il logaritmo perche' il rapporto e' molto asimmetrico: mediana 2,21 e
    # novantesimo percentile 8,58. In scala lineare le poche code
    # deciderebbero da sole tutti i pesi.
    vettore.append(math.log(max(rapporto, 1e-6)))
    return vettore


@dataclass(frozen=True)
class Pesi:
    """Un modello stimato: un peso per colonna, piu' l'intercetta."""

    intercetta: float
    per_colonna: dict[str, float] = field(default_factory=dict)
    # Da dove viene, per poterlo rifiutare quando non si sa.
    addestrato_su: str = ""
    righe: int = 0
    brier: float = 0.0

    def vettore(self) -> list[float]:
        return [self.per_colonna.get(n, 0.0) for n in nomi_delle_colonne()]

    def leggibile(self) -> str:
        """I pesi in chiaro, dal piu' forte al piu' debole."""
        righe = [f"intercetta {self.intercetta:+.4f}"]
        for nome, peso in sorted(self.per_colonna.items(),
                                 key=lambda kv: -abs(kv[1])):
            righe.append(f"  {nome:18} {peso:+.4f}")
        return "\n".join(righe)


def probabilita(pesi: Pesi, caratteristiche: Sequence[float]) -> float:
    """La probabilita' di arrivare al bersaglio, fra 0 e 1."""
    z = pesi.intercetta + sum(
        p * x for p, x in zip(pesi.vettore(), caratteristiche))
    # La forma stabile della logistica: l'esponenziale di un numero grande
    # trabocca, e un modello che solleva un'eccezione in produzione e' un
    # modello che ferma il bot.
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def valore_atteso(p: float, rapporto: float, costo_in_erre: float) -> float:
    """`p x RR - (1 - p) - costi`, in multipli del rischio.

    E' il numero che decide, e si restituisce invece di un si'/no perche'
    quanto conviene e' informazione che serve a chi legge il diario. Chi vuole
    il si'/no chiama `conviene`.
    """
    return p * rapporto - (1.0 - p) - costo_in_erre


def conviene(p: float, rapporto: float, costo_in_erre: float,
             margine: float = 0.0) -> bool:
    """Il valore atteso supera il margine richiesto?

    `margine` esiste perche' un vantaggio di un millesimo di R non e' un
    vantaggio: e' rumore di stima. Chi chiama dichiara quanto vuole.
    """
    return valore_atteso(p, rapporto, costo_in_erre) > margine


def salva(pesi: Pesi, percorso: Path) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps({
        "intercetta": pesi.intercetta,
        "per_colonna": pesi.per_colonna,
        "addestrato_su": pesi.addestrato_su,
        "righe": pesi.righe,
        "brier": pesi.brier,
        "colonne": list(nomi_delle_colonne()),
    }, indent=2), encoding="utf-8")


def carica(percorso: Path) -> Optional[Pesi]:
    """I pesi dal file, o `None` se non ci sono o non combaciano.

    Il controllo sulle colonne non e' formalita': se un giorno se ne
    aggiungesse una, un file vecchio verrebbe applicato con i pesi spostati
    di posto. Meglio nessun modello che un modello storto -- senza, il bot
    opererebbe con numeri che sembrano sensati.
    """
    if not percorso.exists():
        return None
    dato = json.loads(percorso.read_text(encoding="utf-8"))
    if tuple(dato.get("colonne", ())) != nomi_delle_colonne():
        return None
    return Pesi(
        intercetta=float(dato["intercetta"]),
        per_colonna={str(k): float(v)
                     for k, v in dato.get("per_colonna", {}).items()},
        addestrato_su=str(dato.get("addestrato_su", "")),
        righe=int(dato.get("righe", 0)),
        brier=float(dato.get("brier", 0.0)),
    )
