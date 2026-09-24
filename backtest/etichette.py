"""Com'e' finito un CRT: target, stop, o scaduto. Con i costi dentro.

## Perche' sta in un file suo

L'etichetta e' la meta' del dataset che conta. Le caratteristiche dicono cosa
si vedeva; l'etichetta dice cosa e' successo, ed e' il numero che il modello
della Fase 2 imparera' a predire. Sbagliarla non produce un errore: produce un
modello che impara benissimo la cosa sbagliata.

## Le tre regole che la definiscono

**Tre esiti, non due.** Target, stop, oppure **scaduto** dopo `T` barre. Senza
il terzo, le operazioni che non si risolvono verrebbero scartate -- e scartare
chi non decide e' gia' una scelta: tiene solo i casi netti e fa sembrare la
strategia piu' decisa di quanto sia. Uno scaduto vale l'R realizzato alla
chiusura della barra `T`.

**Stessa barra: vince lo stop.** Se una barra tocca sia lo stop sia il target
non si sa in che ordine il prezzo ci sia passato, e fra due letture possibili
si sceglie la peggiore. E' la stessa prudenza che la sentinella applica dal
vivo in `livello_toccato`.

**I costi entrano nell'R, non accanto.** Un R lordo non e' confrontabile con
niente: lo spread e lo slippage si pagano due volte, all'entrata e all'uscita,
e su stop stretti sono la differenza fra un vantaggio e una perdita. Il
progetto ha gia' misurato che lo spread da solo costa fra 0,15 e 0,35 R.

## Cosa NON fa

Non guarda le caratteristiche e non sa cosa il bot avrebbe deciso. Prende tre
livelli e una serie di barre successive, e dice come sarebbe finita. La
separazione e' voluta: l'etichetta puo' guardare il futuro -- e' il suo
mestiere -- mentre le caratteristiche non possono mai.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from core.definizioni import Bias, Candela


@dataclass(frozen=True)
class Esito:
    """Come e' finito un CRT, in multipli del rischio iniziale."""

    # "target", "stop", "scaduto"
    come: str
    # R al netto dei costi: il numero che il modello imparera'.
    erre: float
    # Quante barre sono servite. Serve al campione efficace: due CRT che si
    # risolvono nella stessa finestra non sono due casi indipendenti.
    barre: int


def _oltre(prezzo: float, livello: float, verso: Bias) -> bool:
    """Il prezzo ha raggiunto il livello, nel verso dell'operazione?"""
    return prezzo <= livello if verso is Bias.SHORT else prezzo >= livello


def esito_del_crt(
    ingresso: float,
    stop: float,
    target: float,
    verso: Bias,
    successive: Sequence[Candela],
    barre_massime: int,
    costo_per_lato: float = 0.0,
) -> Optional[Esito]:
    """Come sarebbe finita questa operazione, vista dopo.

    `successive` sono le barre DOPO quella in cui il CRT si e' formato, in
    ordine. `costo_per_lato` e' spread piu' slippage in prezzo, pagato due
    volte: all'entrata e all'uscita.

    `None` quando il rischio e' nullo o i livelli sono incoerenti: senza un
    rischio non esiste un R, e un'etichetta inventata e' peggio di
    un'etichetta assente.
    """
    rischio = abs(ingresso - stop)
    if rischio <= 0 or not successive:
        return None
    # Il target deve stare dalla parte del guadagno e lo stop dall'altra, o i
    # livelli non descrivono l'operazione che si dice di misurare.
    if not _oltre(target, ingresso, verso) or _oltre(stop, ingresso, verso):
        return None

    costo_totale = 2.0 * costo_per_lato

    for numero, barra in enumerate(successive[:barre_massime], start=1):
        preso_stop = (barra.massimo >= stop if verso is Bias.SHORT
                      else barra.minimo <= stop)
        preso_target = (barra.minimo <= target if verso is Bias.SHORT
                        else barra.massimo >= target)

        # Fra due letture possibili si sceglie la peggiore: non si sa in che
        # ordine il prezzo abbia toccato i due livelli dentro la stessa barra.
        if preso_stop:
            return Esito("stop", -(rischio + costo_totale) / rischio, numero)
        if preso_target:
            guadagno = abs(target - ingresso) - costo_totale
            return Esito("target", guadagno / rischio, numero)

    # Scaduto: vale quello che valeva alla chiusura dell'ultima barra guardata.
    viste = successive[:barre_massime]
    ultima = viste[-1].chiusura
    grezzo = (ingresso - ultima) if verso is Bias.SHORT else (ultima - ingresso)
    return Esito("scaduto", (grezzo - costo_totale) / rischio, len(viste))
