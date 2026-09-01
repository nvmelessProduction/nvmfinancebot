"""Archivio su SQLite: alert ricevuti, decisioni prese, posizioni sorvegliate.

Regola dell'impianto: l'alert va scritto qui *prima* di qualunque altra cosa,
cosi' se il resto della catena esplode il dato resta comunque.

La parola segreta del webhook non viene mai scritta in archivio.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from core.config import impostazioni
from core.models import AlertIn, Decision, Esito

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS alert (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ricevuto_utc            TEXT    NOT NULL,
    simbolo                 TEXT    NOT NULL,
    tf                      TEXT    NOT NULL,
    chiusura_candela_utc    TEXT    NOT NULL,
    apertura                REAL    NOT NULL,
    massimo                 REAL    NOT NULL,
    minimo                  REAL    NOT NULL,
    chiusura                REAL    NOT NULL,
    rsi                     REAL,
    nota                    TEXT,
    payload_json            TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS decisione (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id        INTEGER NOT NULL REFERENCES alert(id),
    creata_utc      TEXT    NOT NULL,
    azione          TEXT    NOT NULL,
    motivo          TEXT    NOT NULL,
    volume          REAL,
    sl              REAL,
    tp              REAL,
    esito           TEXT    NOT NULL,
    dettaglio       TEXT,
    ticket          INTEGER
);

CREATE TABLE IF NOT EXISTS posizione (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket              INTEGER UNIQUE,
    decisione_id        INTEGER REFERENCES decisione(id),
    simbolo             TEXT    NOT NULL,
    direzione           TEXT    NOT NULL,
    volume              REAL    NOT NULL,
    prezzo_ingresso     REAL,
    sl                  REAL,
    tp                  REAL,
    aperta_utc          TEXT    NOT NULL,
    chiusa_utc          TEXT,
    prezzo_uscita       REAL,
    stato               TEXT    NOT NULL DEFAULT 'aperta',
    motivo_chiusura     TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_simbolo ON alert(simbolo);
CREATE INDEX IF NOT EXISTS idx_decisione_alert ON decisione(alert_id);
CREATE INDEX IF NOT EXISTS idx_posizione_stato ON posizione(stato);
"""


def adesso_utc() -> str:
    """Timestamp UTC in formato ISO, usato per tutte le colonne temporali."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connessione() -> Iterator[sqlite3.Connection]:
    """Apre una connessione per singola operazione e la chiude sempre.

    Una connessione per operazione evita i problemi di SQLite fra thread
    diversi (FastAPI esegue gli endpoint sincroni in un threadpool).
    """
    conn = sqlite3.connect(impostazioni().DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def inizializza() -> None:
    """Crea le tabelle se non esistono. Va chiamata all'avvio del server."""
    with connessione() as conn:
        conn.executescript(SCHEMA)


def salva_alert(alert: AlertIn) -> int:
    """Scrive l'alert in archivio e restituisce il suo id.

    Il payload completo viene conservato in JSON, ma senza il campo `secret`.
    """
    payload: dict[str, Any] = alert.model_dump(by_alias=True)
    payload.pop("secret", None)
    with connessione() as conn:
        cur = conn.execute(
            """
            INSERT INTO alert (
                ricevuto_utc, simbolo, tf, chiusura_candela_utc,
                apertura, massimo, minimo, chiusura, rsi, nota, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                adesso_utc(),
                alert.simbolo,
                alert.tf,
                alert.chiusura_candela_utc,
                alert.apertura,
                alert.massimo,
                alert.minimo,
                alert.chiusura,
                alert.rsi,
                alert.nota,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        id_alert = cur.lastrowid
    if id_alert is None:
        raise sqlite3.Error("inserimento alert non ha restituito un id")
    return id_alert


def salva_decisione(
    alert_id: int,
    decisione: Decision,
    esito: Esito,
    dettaglio: Optional[str] = None,
    ticket: Optional[int] = None,
) -> int:
    """Scrive la decisione presa per un alert, con il suo esito."""
    with connessione() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisione (
                alert_id, creata_utc, azione, motivo,
                volume, sl, tp, esito, dettaglio, ticket
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                adesso_utc(),
                decisione.azione,
                decisione.motivo,
                decisione.volume,
                decisione.sl,
                decisione.tp,
                esito,
                dettaglio,
                ticket,
            ),
        )
        id_decisione = cur.lastrowid
    if id_decisione is None:
        raise sqlite3.Error("inserimento decisione non ha restituito un id")
    return id_decisione


def registra_posizione(
    simbolo: str,
    direzione: str,
    volume: float,
    ticket: Optional[int] = None,
    decisione_id: Optional[int] = None,
    prezzo_ingresso: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
) -> int:
    """Annota una posizione aperta dal bot.

    Serve al futuro sorvegliante di stop e target: sul broker non ci saranno
    ordini pendenti, quindi la memoria dei livelli sta qui.
    """
    with connessione() as conn:
        cur = conn.execute(
            """
            INSERT INTO posizione (
                ticket, decisione_id, simbolo, direzione, volume,
                prezzo_ingresso, sl, tp, aperta_utc, stato
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aperta')
            """,
            (
                ticket,
                decisione_id,
                simbolo,
                direzione,
                volume,
                prezzo_ingresso,
                sl,
                tp,
                adesso_utc(),
            ),
        )
        id_posizione = cur.lastrowid
    if id_posizione is None:
        raise sqlite3.Error("inserimento posizione non ha restituito un id")
    return id_posizione


def chiudi_posizione(
    id_posizione: int,
    prezzo_uscita: Optional[float] = None,
    motivo_chiusura: str = "",
) -> None:
    """Segna come chiusa una posizione gia' registrata."""
    with connessione() as conn:
        conn.execute(
            """
            UPDATE posizione
               SET stato = 'chiusa',
                   chiusa_utc = ?,
                   prezzo_uscita = ?,
                   motivo_chiusura = ?
             WHERE id = ?
            """,
            (adesso_utc(), prezzo_uscita, motivo_chiusura, id_posizione),
        )


def posizioni_aperte() -> list[dict[str, Any]]:
    """Elenca le posizioni che l'archivio considera ancora aperte."""
    with connessione() as conn:
        righe = conn.execute(
            "SELECT * FROM posizione WHERE stato = 'aperta' ORDER BY id"
        ).fetchall()
    return [dict(riga) for riga in righe]


def conteggi() -> dict[str, int]:
    """Numero di righe per tabella: comodo per il collaudo e per /salute."""
    with connessione() as conn:
        return {
            "alert": conn.execute("SELECT COUNT(*) FROM alert").fetchone()[0],
            "decisione": conn.execute("SELECT COUNT(*) FROM decisione").fetchone()[0],
            "posizione": conn.execute("SELECT COUNT(*) FROM posizione").fetchone()[0],
        }
