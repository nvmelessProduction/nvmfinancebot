"""Statistiche sul forward test: cosa ha fatto il motore, e cosa l'ha fermato.

Le metriche sono quelle richieste. Una in particolare merita la posizione che
ha nell'elenco originale:

> quante volte ciascun filtro di `CTX-01` ha impedito un'operazione: e' la
> statistica piu' utile, perche' mi dice se un filtro sta bloccando tutto o
> non scatta mai.

E' vera, ed e' il motivo per cui `motore.valuta()` raccoglie **tutti** i
blocchi valutabili e non si ferma al primo: uscendo subito, questo conteggio
avrebbe visto sempre e solo `SETUP-00`.

L'altra che serve a chiudere un punto aperto e' la distribuzione del campo
`rapporto` di `GIUD-01`: e' cio' che permettera' di dare una soglia numerica a
"vicini" e "distanti" (`PA-44`) invece di sceglierla a occhio.

Nessuna dipendenza: solo la libreria standard. `pandas` servira' quando i
numeri saranno tanti, non prima.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Iterable, Mapping, Optional, Sequence

from core.motore import Decisione
from core.parametri import TF


@dataclass(frozen=True)
class Operazione:
    """Un'operazione chiusa, ridotta a cio' che serve alle statistiche.

    `risultato_r` e' il risultato in multipli del rischio iniziale. E' l'unita'
    giusta per confrontare operazioni di size diversa: due euro persi su un
    rischio di due euro sono -1R come duecento persi su duecento.
    """

    strumento: str
    tf_ingresso: TF
    con_gap: bool
    risultato_r: float
    rapporto_giud01: Optional[float] = None


@dataclass
class Riepilogo:
    """Il risultato di un periodo di forward test."""

    operazioni: int = 0
    vincenti: int = 0
    percentuale_vincenti: float = 0.0
    r_medio: float = 0.0
    r_totale: float = 0.0
    drawdown_massimo_r: float = 0.0
    drawdown_massimo_percentuale: float = 0.0
    per_strumento: Mapping[str, "Riepilogo"] = field(default_factory=dict)
    per_timeframe: Mapping[str, "Riepilogo"] = field(default_factory=dict)
    per_tipo_setup: Mapping[str, "Riepilogo"] = field(default_factory=dict)


def _riepiloga(operazioni: Sequence[Operazione], equity_iniziale: float) -> Riepilogo:
    """Le metriche di base su un insieme di operazioni."""
    if not operazioni:
        return Riepilogo()

    risultati = [o.risultato_r for o in operazioni]
    vincenti = sum(1 for r in risultati if r > 0)
    massimo, minimo = drawdown(risultati)

    return Riepilogo(
        operazioni=len(operazioni),
        vincenti=vincenti,
        percentuale_vincenti=100.0 * vincenti / len(operazioni),
        r_medio=mean(risultati),
        r_totale=sum(risultati),
        drawdown_massimo_r=massimo,
        drawdown_massimo_percentuale=minimo,
    )


def drawdown(risultati_r: Sequence[float], rischio_per_operazione: float = 0.01) -> tuple[float, float]:
    """Drawdown massimo, in R e in percentuale di equity.

    Si misura sulla curva cumulata dei risultati: la distanza piu' grande fra
    un picco e il minimo che lo segue. La percentuale si ottiene moltiplicando
    per il rischio per operazione, che di norma e' l'1% (RISK-01).

    Restituisce (drawdown in R, drawdown in percentuale), entrambi positivi.
    """
    if not risultati_r:
        return 0.0, 0.0

    cumulata = 0.0
    picco = 0.0
    peggiore = 0.0
    for risultato in risultati_r:
        cumulata += risultato
        picco = max(picco, cumulata)
        peggiore = max(peggiore, picco - cumulata)

    return peggiore, peggiore * rischio_per_operazione * 100.0


def riepilogo(
    operazioni: Sequence[Operazione],
    equity_iniziale: float = 0.0,
) -> Riepilogo:
    """Il quadro completo, con le tre scomposizioni richieste.

    Per strumento, per timeframe di ingresso, e per tipo di setup — con gap o
    senza. Quest'ultima e' la piu' interessante delle tre: `SETUP-10` prevede
    per i gap un doppio ingresso con rischio dimezzato, quindi le due famiglie
    non sono confrontabili a occhio.
    """
    complessivo = _riepiloga(operazioni, equity_iniziale)

    def raggruppa(chiave) -> dict[str, Riepilogo]:
        gruppi: dict[str, list[Operazione]] = {}
        for operazione in operazioni:
            gruppi.setdefault(str(chiave(operazione)), []).append(operazione)
        return {nome: _riepiloga(gruppo, equity_iniziale) for nome, gruppo in sorted(gruppi.items())}

    complessivo.per_strumento = raggruppa(lambda o: o.strumento)
    complessivo.per_timeframe = raggruppa(lambda o: o.tf_ingresso.value)
    complessivo.per_tipo_setup = raggruppa(lambda o: "con gap" if o.con_gap else "senza gap")
    return complessivo


# ===========================================================================
# La statistica piu' utile: cosa ha impedito di operare
# ===========================================================================


def conteggio_filtri(decisioni: Iterable[Decisione]) -> dict[str, int]:
    """Quante volte ciascuna regola ha impedito un'operazione.

    Conta **tutte** le regole che hanno bloccato ciascuna decisione, non solo
    la prima: un filtro che scatta sempre insieme a un altro non si vedrebbe
    mai, e non si saprebbe se sta lavorando o se e' inerte.

    Un filtro con conteggio zero non e' necessariamente inutile — puo' non
    essersi presentata l'occasione — ma dopo qualche mese di forward test uno
    zero e' un'informazione: o non serve, o e' scritto male e non scatta mai.
    """
    conteggi: Counter[str] = Counter()
    for decisione in decisioni:
        conteggi.update(decisione.regole_che_bloccano)
    return dict(conteggi.most_common())


def filtri_mai_scattati(decisioni: Iterable[Decisione], attesi: Iterable[str]) -> list[str]:
    """Le regole che, nel periodo osservato, non hanno mai fermato nulla.

    `attesi` e' l'elenco dei filtri che ci si aspetta di vedere all'opera —
    tipicamente le undici condizioni di `CTX-01`. Uno che non compare mai va
    guardato: nella migliore delle ipotesi il mercato non ne ha dato occasione,
    nella peggiore la sua condizione non e' raggiungibile.
    """
    visti = set(conteggio_filtri(decisioni))
    return sorted(set(attesi) - visti)


# ===========================================================================
# Distribuzione del rapporto di GIUD-01, per chiudere PA-44
# ===========================================================================


@dataclass(frozen=True)
class DistribuzioneRapporto:
    """La distribuzione di `distanza_kl_gap / atr` (07_casi.md §3.1)."""

    campioni: int
    minimo: Optional[float]
    primo_quartile: Optional[float]
    mediana: Optional[float]
    terzo_quartile: Optional[float]
    massimo: Optional[float]

    def sufficiente_per_pa44(self) -> bool:
        """`07_casi.md` §3.1 chiede minimo 10 casi per categoria, tre categorie."""
        return self.campioni >= 30


def _quantile(ordinati: Sequence[float], frazione: float) -> float:
    """Quantile per interpolazione lineare. Con un solo campione, quello."""
    if len(ordinati) == 1:
        return ordinati[0]
    posizione = frazione * (len(ordinati) - 1)
    basso = int(posizione)
    alto = min(basso + 1, len(ordinati) - 1)
    peso = posizione - basso
    return ordinati[basso] * (1 - peso) + ordinati[alto] * peso


def distribuzione_rapporto(operazioni: Iterable[Operazione]) -> DistribuzioneRapporto:
    """Il dato che serve a dare un numero a "vicini" e "distanti".

    Finche' `PA-44` resta aperta ogni caso e' categoria C e il target resta al
    key level (`GIUD-01`, regola di uscita). Questa distribuzione e' cio' che
    permettera' di chiuderla guardando dove si separano davvero i casi in cui
    il prezzo e' andato al gap da quelli in cui ha invertito sul key level.
    """
    valori = sorted(
        o.rapporto_giud01 for o in operazioni if o.rapporto_giud01 is not None
    )
    if not valori:
        return DistribuzioneRapporto(0, None, None, None, None, None)
    return DistribuzioneRapporto(
        campioni=len(valori),
        minimo=valori[0],
        primo_quartile=_quantile(valori, 0.25),
        mediana=median(valori),
        terzo_quartile=_quantile(valori, 0.75),
        massimo=valori[-1],
    )


# ===========================================================================
# Resoconto leggibile
# ===========================================================================


def resoconto(
    operazioni: Sequence[Operazione],
    decisioni: Sequence[Decisione],
    filtri_attesi: Sequence[str] = (),
) -> str:
    """Il quadro in testo, per il log e per guardarlo una volta a settimana."""
    quadro = riepilogo(operazioni)
    righe: list[str] = []

    righe.append("=" * 66)
    righe.append("FORWARD TEST — RIEPILOGO")
    righe.append("=" * 66)
    righe.append(f"  operazioni:        {quadro.operazioni}")
    if quadro.operazioni:
        righe.append(f"  vincenti:          {quadro.vincenti} ({quadro.percentuale_vincenti:.1f}%)")
        righe.append(f"  R medio:           {quadro.r_medio:+.2f}")
        righe.append(f"  R totale:          {quadro.r_totale:+.2f}")
        righe.append(f"  drawdown massimo:  {quadro.drawdown_massimo_r:.2f}R "
                     f"({quadro.drawdown_massimo_percentuale:.2f}% di equity)")

    for titolo, gruppi in (
        ("PER STRUMENTO", quadro.per_strumento),
        ("PER TIMEFRAME DI INGRESSO", quadro.per_timeframe),
        ("PER TIPO DI SETUP", quadro.per_tipo_setup),
    ):
        if gruppi:
            righe.append("")
            righe.append(titolo)
            for nome, gruppo in gruppi.items():
                righe.append(
                    f"  {nome:<14} {gruppo.operazioni:3} operazioni, "
                    f"{gruppo.percentuale_vincenti:5.1f}% vincenti, R medio {gruppo.r_medio:+.2f}"
                )

    righe.append("")
    righe.append("COSA HA IMPEDITO DI OPERARE")
    conteggi = conteggio_filtri(decisioni)
    if not conteggi:
        righe.append("  nessun blocco registrato")
    for regola, quante in conteggi.items():
        righe.append(f"  {regola:<12} {quante:4} volte")

    mai = filtri_mai_scattati(decisioni, filtri_attesi)
    if mai:
        righe.append("")
        righe.append("  Filtri mai scattati nel periodo — o non servono, o non scattano mai:")
        for regola in mai:
            righe.append(f"    {regola}")

    distribuzione = distribuzione_rapporto(operazioni)
    righe.append("")
    righe.append("RAPPORTO DI GIUD-01 (per chiudere PA-44)")
    if distribuzione.campioni == 0:
        righe.append("  nessun campione")
    else:
        righe.append(f"  campioni:   {distribuzione.campioni}")
        righe.append(f"  min / max:  {distribuzione.minimo:.2f} / {distribuzione.massimo:.2f}")
        righe.append(
            f"  quartili:   {distribuzione.primo_quartile:.2f} | "
            f"{distribuzione.mediana:.2f} | {distribuzione.terzo_quartile:.2f}"
        )
        stato = "sufficienti" if distribuzione.sufficiente_per_pa44() else "ancora pochi"
        righe.append(f"  {stato} per chiudere PA-44 (ne servono 30)")

    righe.append("=" * 66)
    return "\n".join(righe)
