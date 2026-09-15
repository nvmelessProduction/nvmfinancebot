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

from datetime import timedelta
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
        # L'orario di una candela e' la sua chiusura, e la chiusura appartiene
        # al mese che sta finendo, non a quello che comincia. Si guarda percio'
        # l'ultimo istante *prima* della chiusura.
        #
        # Non e' un dettaglio: chi costruisce le candele dagli orari di
        # apertura (importa_storico, scarica_storico, il fornitore) marca la
        # mensile di gennaio con la chiusura "1 febbraio 00:00". Leggendo
        # `.month` direttamente si otterrebbe febbraio, i gruppi
        # risulterebbero sfasati di un mese e quasi ogni trimestre finirebbe
        # con due mesi o con quattro: scartato come incompleto. Il risultato
        # non e' un errore visibile, e' un TF_12M sempre vuoto.
        appartenenza = candela.orario - timedelta(microseconds=1)
        chiave = (appartenenza.year, _indice_gruppo(appartenenza.month, quanti))
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


def aggrega_per_mese(giornaliere: Sequence[Candela]) -> tuple[Candela, ...]:
    """Costruisce le mensili dalle giornaliere.

    Serve quando la fonte dei dati ha le giornaliere complete ma le mensili
    bucate — che e' esattamente il caso delle fonti gratuite sui future: sul
    contratto dell'oro mancano una quarantina di mesi su trecento, sempre
    diversi da strumento a strumento. Un mese mancante non e' un fastidio
    estetico: `aggrega` rifiuta giustamente i periodi incompleti, quindi ogni
    trimestre che contiene quel buco sparisce, e con esso l'anno intero. Il
    sintomo e' un `TF_12M` sempre vuoto.

    Un mese e' la somma delle sue sessioni, quindi costruirlo dalle giornaliere
    non inventa niente: apertura della prima sessione, chiusura dell'ultima,
    estremi di tutte. E' la stessa operazione che `aggrega` fa dai mesi ai
    trimestri, un piano piu' in basso.

    **L'ultimo mese si scarta.** Un mese e' finito quando esiste una sessione
    che gli e' successiva: senza quella prova il mese e' in corso, ed e' una
    candela in formazione (`ESCL-13`). E' la stessa regola con cui
    l'importatore scarta l'ultima barra.
    """
    ordinate = sorted(giornaliere, key=lambda c: c.orario)
    gruppi: dict[tuple[int, int], list[Candela]] = {}
    for candela in ordinate:
        # Stessa convenzione di `aggrega`: la chiusura appartiene al periodo
        # che sta finendo, quindi si guarda l'istante prima.
        appartenenza = candela.orario - timedelta(microseconds=1)
        gruppi.setdefault((appartenenza.year, appartenenza.month), []).append(candela)

    chiavi = sorted(gruppi)
    mensili: list[Candela] = []
    for chiave in chiavi[:-1]:           # l'ultimo mese e' in formazione
        gruppo = gruppi[chiave]
        mensili.append(
            Candela(
                orario=gruppo[-1].orario,
                apertura=gruppo[0].apertura,
                massimo=max(c.massimo for c in gruppo),
                minimo=min(c.minimo for c in gruppo),
                chiusura=gruppo[-1].chiusura,
            )
        )
    return tuple(mensili)


def aggrega_orarie(orarie: Sequence[Candela], quante: int = 4) -> tuple[Candela, ...]:
    """Costruisce `TF_H4` dalle orarie, in blocchi allineati alla giornata.

    Serve perche' SETUP-05 non puo' autorizzare un ingresso su `TF_H1` senza
    sapere cosa ha fatto `TF_H4` (REV-48), e la fonte gratuita dello storico
    non serve barre a quattro ore.

    **Il confine, e il suo limite.** `DEF-03` vuole i confini della sessione
    dell'exchange, non quelli dell'orologio. Questi blocchi sono ancorati
    all'orologio UTC, e vanno dichiarati per quello che sono: sulla fonte
    gratuita la giornaliera dei future di `PRIN-08` chiude alle 04:00 UTC in
    inverno — multiplo di quattro, e allora i blocchi coincidono con la
    sessione — ma alle 05:00 UTC durante l'ora legale americana, e li' il
    taglio cade un'ora dopo l'apertura della sessione.

    Non e' una `TF_H4` di TradingView e non va spacciata per tale. Serve a
    dare a SETUP-05 uno storico su cui misurarsi quando il bot parte da zero;
    dal vivo le `TF_H4` vere arrivano dagli alert e prendono il posto di
    queste. Chi volesse l'ancoraggio esatto deve importare lo storico dal CSV
    di TradingView (`importa_storico.py`), che porta i confini giusti.

    **Il blocco incompleto si scarta**: senza tutte e `quante` le orarie e' o
    una candela in formazione o un buco nei dati, e in nessuno dei due casi e'
    una candela (`ESCL-13`).
    """
    ordinate = sorted(orarie, key=lambda c: c.orario)
    gruppi: dict[tuple, list[Candela]] = {}
    for candela in ordinate:
        # `orario` e' la CHIUSURA (DEF-02): l'ora di appartenenza e' quella che
        # precede, altrimenti la barra che chiude alle 04:00 finirebbe nel
        # blocco successivo invece che in quello che l'ha vista formarsi.
        appartenenza = candela.orario - timedelta(microseconds=1)
        gruppi.setdefault(
            (appartenenza.date(), appartenenza.hour // quante), []
        ).append(candela)

    aggregate: list[Candela] = []
    for chiave in sorted(gruppi):
        gruppo = gruppi[chiave]
        if len(gruppo) < quante:
            continue                     # blocco incompleto: non e' una candela
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
