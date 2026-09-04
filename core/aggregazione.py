"""Costruzione dei timeframe che MT5 non ha: `TF_3M`, `TF_6M`, `TF_12M`.

MT5 si ferma a `MN1`. I tre timeframe superiori di `DEF-01` vanno aggregati dai
mensili, e questo file lo fa.

**Solo periodi completi.** Un trimestre in corso non e' una candela: e' una
candela in formazione, e `DEF-02` con `ESCL-13` dicono che non va mai valutata.
Un aggregatore che emettesse il trimestre parziale creerebbe un lookahead di
mesi, non di minuti — e sarebbe invisibile, perche' i numeri sembrerebbero
giusti.

**I confini li eredita dalla fonte.** `DEF-03` vuole le candele costruite sulla
sessione dell'exchange. Le mensili di MT5 portano gia' i confini del server da
cui vengono: aggregandole si conservano, senza reinventarli.
"""

from __future__ import annotations

from typing import Sequence

from core.definizioni import Candela
from core.parametri import TF

# Quanti mensili servono per ciascun timeframe aggregato.
MENSILI_PER_TIMEFRAME: dict[TF, int] = {
    TF.M3: 3,
    TF.M6: 6,
    TF.M12: 12,
}

# Mese in cui comincia ciascun gruppo, contando da gennaio.
# Un trimestre parte a gennaio, aprile, luglio o ottobre; un semestre a
# gennaio o luglio; l'anno a gennaio.
def _indice_gruppo(mese: int, quanti: int) -> int:
    """Il gruppo di calendario a cui appartiene un mese (1-12)."""
    return (mese - 1) // quanti


def aggrega(mensili: Sequence[Candela], quanti: int) -> tuple[Candela, ...]:
    """Unisce le mensili in gruppi di `quanti`, allineati al calendario.

    Un gruppo diventa candela solo se contiene **tutti** i mesi che gli
    spettano: un trimestre con due mensili su tre e' in formazione, e non
    esiste.

    `orario` della candela aggregata e' quello dell'ultima mensile del gruppo,
    cioe' il momento in cui il gruppo si e' chiuso.
    """
    if quanti < 1:
        raise ValueError(f"gruppo non valido: {quanti}")

    ordinate = sorted(mensili, key=lambda c: c.orario)
    gruppi: dict[tuple[int, int], list[Candela]] = {}
    for candela in ordinate:
        # L'orario di una candela e' la sua chiusura: il mese di appartenenza
        # e' quello che sta finendo, quindi si guarda l'ultimo istante utile.
        chiave = (candela.orario.year, _indice_gruppo(candela.orario.month, quanti))
        gruppi.setdefault(chiave, []).append(candela)

    aggregate: list[Candela] = []
    for chiave in sorted(gruppi):
        gruppo = gruppi[chiave]
        if len(gruppo) < quanti:
            continue                    # periodo incompleto: non esiste ancora
        aggregate.append(
            Candela(
                orario=gruppo[-1].orario,
                apertura=gruppo[0].apertura,
                massimo=max(c.massimo for c in gruppo),
                minimo=min(c.minimo for c in gruppo),
                chiusura=gruppo[-1].chiusura,
            )
        )
    return tuple(aggregate)


def costruisci_superiori(mensili: Sequence[Candela]) -> dict[TF, tuple[Candela, ...]]:
    """I tre timeframe che MT5 non fornisce, dalle sue mensili."""
    return {tf: aggrega(mensili, quanti) for tf, quanti in MENSILI_PER_TIMEFRAME.items()}


def orari_di_chiusura(orari_di_apertura: Sequence, durata_finale=None) -> tuple:
    """Converte gli orari di **apertura** di MT5 in orari di **chiusura**.

    E' il punto in cui si perde un backtest senza accorgersene. MT5 marca ogni
    barra con l'istante in cui si e' **aperta**; `Candela.orario` e' l'istante
    in cui si e' **chiusa** (DEF-02). Usare l'apertura come chiusura renderebbe
    ogni candela visibile un intero periodo prima del dovuto: su `TF_1W`
    significherebbe leggere la settimana con sette giorni di anticipo.

    La chiusura della barra `i` e' l'apertura della barra `i+1`. E' esatto
    anche sui periodi irregolari — mesi di lunghezza diversa, fine settimana,
    festivita' — e non richiede di sapere quanto dura un periodo.

    L'ultima barra non ha un successore, quindi non ha una chiusura nota: e'
    quella in formazione, e va scartata. La funzione restituisce un elemento in
    meno di quanti ne riceve, ed e' voluto.

    Quando c'e' un buco nei dati — mercato chiuso una settimana intera — la
    chiusura risulta piu' tarda di quella vera. E' l'errore dal lato sicuro:
    la candela diventa disponibile piu' tardi, mai prima.
    """
    del durata_finale                   # l'ultima barra si scarta, non si stima
    return tuple(orari_di_apertura[1:])
