"""Esportazione delle decisioni nel formato blocco di `docs/07_casi.md`.

I casi si generano dal motore invece che a mano. Restano da annotare a mano
solo quelli in cui serve il tuo giudizio — le categorie A, B e C di `GIUD-01`
— perche' quelli sono la materia prima di `PA-44`.

**L'etichetta e' di conformita', non di esito** (`ESCL-23`). Un caso prodotto
dal motore e' `CONFORME` per costruzione: il bot non ha un percorso che porti
a un ordine se non attraverso le regole. Diventa `NON CONFORME` solo quando c'e'
di mezzo una mano umana che ha fatto qualcosa che le regole non prevedevano
(`AMM-01`).

L'esito si annota, ma in un campo separato e marcato come informativo. E' il
punto su cui `07_casi.md` insiste di piu': etichettare sull'esito rende inutile
tutto il file, perche' dopo qualche centinaio di casi il sistema avrebbe
imparato il rumore degli ultimi mesi di mercato invece della strategia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from core.definizioni import Bias, Candela, Divergenza, Gap, KeyLevel
from core.motore import Decisione
from core.parametri import TF

NON_DISPONIBILE = "n/d"


@dataclass(frozen=True)
class Caso:
    """Un caso pronto da scrivere in `07_casi.md`.

    Nessun campo puo' essere omesso: se un dato non c'e' si scrive `n/d`, come
    prescrive la sezione 1 del documento. Un campo mancante rende il caso
    inutilizzabile come test di verifica, ed e' l'errore numero 6 dell'elenco
    finale di `07_casi.md`.
    """

    numero: int
    istante: datetime
    strumento_future: str
    decisione: Decisione
    tf_key_level: Optional[TF] = None
    tf_comando: Optional[TF] = None
    bias_comando: Bias = Bias.NESSUNA
    key_level_preso: Optional[KeyLevel] = None
    gap: Optional[Gap] = None
    gap_fase: Optional[int] = None
    n1: Optional[Candela] = None
    n2: Optional[Candela] = None
    n3_apertura: Optional[float] = None
    tf_allineati: Sequence[TF] = ()
    divergenza: Divergenza = Divergenza.NESSUNA
    # Solo per i casi di GIUD-01 (07_casi.md §3.1).
    distanza_kl_gap: Optional[float] = None
    atr_tf: Optional[float] = None
    # Informativo, mai l'etichetta (ESCL-23).
    esito_r: Optional[float] = None
    chiusura_manuale: bool = False


def _valore(x: object, cifre: int = 5) -> str:
    if x is None:
        return NON_DISPONIBILE
    if isinstance(x, float):
        return f"{x:.{cifre}f}".rstrip("0").rstrip(".")
    if isinstance(x, TF):
        return x.value
    return str(x)


def _etichetta(caso: Caso) -> str:
    """ESCL-23 e AMM-01 — Conformita', mai esito.

    Una chiusura manuale non prevista dalle regole e', per definizione, NON
    CONFORME: registrarla e' cio' che permette di capire se convenga cambiare
    una regola o correggere il comportamento.
    """
    if caso.chiusura_manuale:
        return "NON CONFORME alla strategia"
    return "CONFORME alla strategia"


def _rapporto_giud01(caso: Caso) -> Optional[float]:
    from core.setup import rapporto_giud01

    if caso.distanza_kl_gap is None or caso.atr_tf is None:
        return None
    return rapporto_giud01(caso.distanza_kl_gap, caso.atr_tf)


def formatta(caso: Caso) -> str:
    """Il blocco di testo, nel formato esatto della sezione 2 di `07_casi.md`."""
    d = caso.decisione
    righe: list[str] = []

    righe.append(f"CASO {caso.numero:02d}")
    righe.append(f"Data/ora:         {caso.istante:%Y-%m-%d %H:%M} UTC")
    righe.append(f"Strumento:        {caso.strumento_future}")
    righe.append(f"TF del CRT:       {_valore(d.tf_crt)}")
    righe.append(f"TF del key level: {_valore(caso.tf_key_level)}")
    righe.append("")

    righe.append("DATI")
    righe.append(f"  bias_comando:      {caso.bias_comando.value}")
    righe.append(f"  tf_comando:        {_valore(caso.tf_comando)}")
    if caso.key_level_preso is not None:
        kl = caso.key_level_preso
        righe.append(f"  key_level_preso:   {kl.tipo.value} {kl.tf.value} = {_valore(kl.valore)}")
    else:
        righe.append(f"  key_level_preso:   {NON_DISPONIBILE}")
    righe.append(f"  gap_attivo_tf:     {_valore(caso.gap.tf) if caso.gap else 'NESSUNO'}")
    righe.append(
        f"  gap_zona:          [{_valore(caso.gap.zona_inf)}, {_valore(caso.gap.zona_sup)}]"
        if caso.gap else f"  gap_zona:          {NON_DISPONIBILE}"
    )
    righe.append(f"  gap_fase:          {caso.gap_fase if caso.gap_fase else 'n.a.'}")
    righe.append(
        f"  N1 high/low:       {_valore(caso.n1.massimo)} / {_valore(caso.n1.minimo)}"
        if caso.n1 else f"  N1 high/low:       {NON_DISPONIBILE}"
    )
    righe.append(
        f"  N2 high/low/close: {_valore(caso.n2.massimo)} / {_valore(caso.n2.minimo)}"
        f" / {_valore(caso.n2.chiusura)}"
        if caso.n2 else f"  N2 high/low/close: {NON_DISPONIBILE}"
    )
    righe.append(f"  N3 open:           {_valore(caso.n3_apertura)}")
    allineati = ", ".join(tf.value for tf in caso.tf_allineati) or NON_DISPONIBILE
    righe.append(f"  tf_allineati:      {allineati}")
    righe.append(f"  divergenza_rsi:    {caso.divergenza.value}")
    righe.append(f"  rr_su_tp1:         {_valore(d.rapporto_su_tp1, 2)}")

    # Campi richiesti dai soli casi di GIUD-01 (07_casi.md §3.1).
    if caso.distanza_kl_gap is not None or caso.atr_tf is not None:
        righe.append(f"  distanza_kl_gap:   {_valore(caso.distanza_kl_gap)}")
        righe.append(f"  atr_tf:            {_valore(caso.atr_tf)}")
        righe.append(f"  rapporto:          {_valore(_rapporto_giud01(caso), 3)}")
    righe.append("")

    righe.append("REGOLE APPLICABILI")
    regole = list(d.regole_applicate) + list(d.regole_che_bloccano)
    righe.append(f"  {', '.join(dict.fromkeys(regole)) or NON_DISPONIBILE}")
    righe.append("")

    righe.append("TUA DECISIONE")
    if d.azione == "NONE":
        righe.append("  NESSUN INGRESSO")
    else:
        righe.append(f"  {'SHORT' if d.direzione is Bias.SHORT else 'LONG'}")
    righe.append("")

    righe.append("MOTIVO")
    righe.append(f"  {d.motivo or NON_DISPONIBILE}")
    righe.append("")

    righe.append("ETICHETTA")
    righe.append(f"  {_etichetta(caso)}")
    righe.append("")

    righe.append("ESITO TRADE")
    esito = f"{caso.esito_r:+.1f}R" if caso.esito_r is not None else "n.a."
    righe.append(f"  {esito} [informativo, NON e' l'etichetta]")

    return "\n".join(righe)


def formatta_molti(casi: Sequence[Caso]) -> str:
    """Piu' casi, separati come nel documento, in ordine di numerazione.

    La numerazione e' progressiva senza buchi e senza riutilizzo (passo 6 della
    procedura): questa funzione la verifica invece di fidarsi.
    """
    ordinati = sorted(casi, key=lambda c: c.numero)
    numeri = [c.numero for c in ordinati]
    if len(set(numeri)) != len(numeri):
        raise ValueError(f"numerazione con duplicati: {numeri}")
    return "\n\n```\n\n```\n".join(formatta(c) for c in ordinati)


def blocco_markdown(caso: Caso) -> str:
    """Il caso dentro il recinto di codice, pronto da incollare in `07_casi.md`."""
    return f"```\n{formatta(caso)}\n```"
