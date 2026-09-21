"""Quanto puo' spendere il giudizio discrezionale, e su cosa.

## Perche' esiste

`core/giudizio_claude.py` chiama un modello a pagamento dentro il percorso
della decisione. Finche' girava solo su ordini gia' approvati dalle regole non
e' mai partita una chiamata in tutta la vita del progetto: zero setup erano
arrivati fin li'. Aprendolo ai CRT **rifiutati** da una regola sola, le
chiamate diventano decine al giorno, e il conto e' vero.

Due freni, e servono tutti e due.

## Il primo: non giudicare due volte lo stesso CRT

Un CRT vive finche' vive la sua candela di range, e il motore lo ritrova
identico ad ogni chiusura di candela del timeframe di ingresso. Misurato il
2026-09-21 su sei ore: 46 rifiuti da una regola sola erano **14 CRT
distinti**, e due di essi comparivano undici volte ciascuno. Senza questo
freno si paga tre volte lo stesso identico giudizio, con lo stesso identico
dossier, per ottenere lo stesso identico verdetto.

L'impronta e' il CRT, non la valutazione: strumento, direzione, timeframe del
range e l'estremo spazzato da `N2`. Quando `N2` cambia, cambia il CRT, e
quello e' un caso nuovo che merita un giudizio nuovo.

## Il secondo: un tetto di spesa vero

Il tetto e' in euro al giorno e si misura sul consumo **dichiarato dall'API**,
non su una stima. La stima sarebbe sbagliata: `giudica` usa `thinking`
adattivo con effort alto, quindi i token di ragionamento -- fatturati come
uscita -- dipendono da quanto il modello decide di pensarci, e non si sanno
prima. Un tetto costruito su un numero inventato e' un tetto che non tiene.

Esaurito il tetto il giudizio non viene interpellato e il motore resta con la
sua decisione meccanica, cioe' si astiene. E' l'esito prudente: senza
giudizio non si apre niente che le regole non avessero gia' approvato.

I prezzi stanno nella configurazione e non qui: cambiano, e un numero
sbagliato scritto nel codice produce un tetto che sembra rispettato e non lo
e'. Se non sono configurati il tetto lavora sui soli token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from core import storage
from core.log import diario

log = diario("budget")


def _oggi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def prepara_tabelle() -> None:
    with storage.connessione(scrittura=True) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS giudizio_speso (
                giorno          TEXT PRIMARY KEY,
                chiamate        INTEGER NOT NULL DEFAULT 0,
                token_ingresso  INTEGER NOT NULL DEFAULT 0,
                token_uscita    INTEGER NOT NULL DEFAULT 0,
                euro            REAL    NOT NULL DEFAULT 0.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS giudizio_visto (
                impronta    TEXT PRIMARY KEY,
                strumento   TEXT NOT NULL,
                obiezione   TEXT NOT NULL,
                verdetto    TEXT NOT NULL,
                motivo      TEXT,
                deciso_utc  TEXT NOT NULL
            )
        """)


def impronta_crt(strumento: str, direzione: str, tf_crt: str,
                 estremo_n2: float, obiezione: str) -> str:
    """Cosa rende due giudizi "lo stesso giudizio".

    L'obiezione fa parte dell'impronta: lo stesso CRT fermato da `RISK-05` e
    lo stesso CRT fermato da `CRT-20` sono due domande diverse, e meritano due
    risposte. L'estremo di `N2` distingue un CRT dal successivo meglio di un
    orario: e' il livello spazzato, cioe' l'identita' del pattern.
    """
    return f"{strumento}|{direzione}|{tf_crt}|{estremo_n2:.6f}|{obiezione}"


@dataclass(frozen=True)
class Speso:
    chiamate: int
    token_ingresso: int
    token_uscita: int
    euro: float


def speso_oggi() -> Speso:
    prepara_tabelle()
    with storage.connessione() as conn:
        r = conn.execute(
            "SELECT chiamate, token_ingresso, token_uscita, euro "
            "FROM giudizio_speso WHERE giorno = ?", (_oggi(),)).fetchone()
    if r is None:
        return Speso(0, 0, 0, 0.0)
    return Speso(int(r["chiamate"]), int(r["token_ingresso"]),
                 int(r["token_uscita"]), float(r["euro"]))


def gia_giudicato(impronta: str) -> Optional[tuple[str, str]]:
    """Il verdetto gia' dato su questo CRT, se c'e'. (verdetto, motivo)."""
    prepara_tabelle()
    with storage.connessione() as conn:
        r = conn.execute(
            "SELECT verdetto, motivo FROM giudizio_visto WHERE impronta = ?",
            (impronta,)).fetchone()
    return (str(r["verdetto"]), str(r["motivo"] or "")) if r else None


def ricorda(impronta: str, strumento: str, obiezione: str,
            verdetto: str, motivo: str) -> None:
    prepara_tabelle()
    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO giudizio_visto "
            "(impronta, strumento, obiezione, verdetto, motivo, deciso_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (impronta, strumento, obiezione, verdetto, motivo[:500],
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))


def tetto_giornaliero() -> float:
    from core.config import impostazioni
    return float(getattr(impostazioni(), "GIUDIZIO_EURO_AL_GIORNO", 0.0) or 0.0)


def c_e_budget() -> tuple[bool, str]:
    """Si puo' ancora interpellare il giudizio oggi?

    Con tetto a zero il freno e' spento e si spende senza limite: e' una
    scelta esplicita di chi configura, non il valore di partenza.
    """
    tetto = tetto_giornaliero()
    if tetto <= 0:
        return True, "nessun tetto configurato"
    s = speso_oggi()
    if s.euro >= tetto:
        return False, (f"tetto giornaliero raggiunto: {s.euro:.3f} di "
                       f"{tetto:.2f} EUR in {s.chiamate} giudizi")
    return True, f"speso {s.euro:.3f} di {tetto:.2f} EUR in {s.chiamate} giudizi"


def costo(token_ingresso: int, token_cache_scritta: int,
          token_cache_letta: int, token_uscita: int) -> float:
    """Il costo in euro di una chiamata, dai prezzi in configurazione.

    Scrittura e lettura della cache sono due prezzi diversi e vanno tenuti
    separati: su Opus 5 la scrittura costa 6,25 al milione e la lettura 0,50,
    cioe' dodici volte meno. Le istruzioni del giudizio vengono messe in cache
    apposta, quindi la prima chiamata paga la scrittura e tutte le altre la
    lettura -- accorparle sotto un prezzo solo sovrastima o sottostima tutto
    il conto a seconda di quale dei due si sceglie.
    """
    from core.config import impostazioni
    cfg = impostazioni()
    p_in = float(getattr(cfg, "PREZZO_INGRESSO_PER_MILIONE", 0.0) or 0.0)
    p_scrittura = float(getattr(cfg, "PREZZO_CACHE_SCRITTA_PER_MILIONE", 0.0) or 0.0)
    p_lettura = float(getattr(cfg, "PREZZO_CACHE_LETTA_PER_MILIONE", 0.0) or 0.0)
    p_out = float(getattr(cfg, "PREZZO_USCITA_PER_MILIONE", 0.0) or 0.0)
    return (token_ingresso * p_in
            + token_cache_scritta * p_scrittura
            + token_cache_letta * p_lettura
            + token_uscita * p_out) / 1_000_000.0


def registra(token_ingresso: int, token_cache_scritta: int,
             token_cache_letta: int, token_uscita: int) -> float:
    """Somma una chiamata al conto di oggi. Restituisce l'euro speso adesso."""
    prepara_tabelle()
    euro = costo(token_ingresso, token_cache_scritta, token_cache_letta, token_uscita)
    token_ingresso_cache = token_cache_scritta + token_cache_letta
    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "INSERT INTO giudizio_speso (giorno, chiamate, token_ingresso,"
            " token_uscita, euro) VALUES (?, 1, ?, ?, ?)"
            " ON CONFLICT(giorno) DO UPDATE SET"
            "   chiamate = chiamate + 1,"
            "   token_ingresso = token_ingresso + excluded.token_ingresso,"
            "   token_uscita = token_uscita + excluded.token_uscita,"
            "   euro = euro + excluded.euro",
            (_oggi(), token_ingresso + token_ingresso_cache, token_uscita, euro))
    return euro
