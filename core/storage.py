"""Archivio su SQLite: alert ricevuti, decisioni prese, posizioni sorvegliate.

Regola dell'impianto: l'alert va scritto qui *prima* di qualunque altra cosa,
cosi' se il resto della catena esplode il dato resta comunque.

Due proprieta' su cui si regge il resto:
  - la parola segreta del webhook non viene mai scritta in archivio;
  - ogni alert ha un'impronta unica, quindi una consegna doppia non puo'
    diventare un ordine doppio.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from core.config import impostazioni
from core.log import diario
from core.models import AlertIn, Decision, Esito

log = diario("archivio")

# Serializza le scritture: SQLite regge piu' lettori ma un solo scrittore, e
# webhook e sentinella scrivono da thread diversi.
_lucchetto_scrittura = threading.Lock()

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS alert (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    impronta                TEXT    NOT NULL,
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
    ritardo_sec             REAL,
    payload_json            TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS candela (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    strumento               TEXT    NOT NULL,
    tf                      TEXT    NOT NULL,
    chiusura_utc            TEXT    NOT NULL,
    apertura                REAL    NOT NULL,
    massimo                 REAL    NOT NULL,
    minimo                  REAL    NOT NULL,
    chiusura                REAL    NOT NULL,
    origine                 TEXT    NOT NULL DEFAULT 'tradingview',
    ricevuta_utc            TEXT    NOT NULL
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

"""

# Gli indici stanno a parte perche' vanno creati DOPO la migrazione: su un
# archivio vecchio la colonna `impronta` non esiste ancora.
INDICI: str = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_impronta ON alert(impronta);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candela_unica
    ON candela(strumento, tf, chiusura_utc);
CREATE INDEX IF NOT EXISTS idx_candela_serie ON candela(strumento, tf, chiusura_utc);
CREATE INDEX IF NOT EXISTS idx_alert_simbolo ON alert(simbolo);
CREATE INDEX IF NOT EXISTS idx_decisione_alert ON decisione(alert_id);
CREATE INDEX IF NOT EXISTS idx_posizione_stato ON posizione(stato);
"""


def adesso_utc() -> str:
    """Timestamp UTC in formato ISO, usato per tutte le colonne temporali."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connessione(scrittura: bool = False) -> Iterator[sqlite3.Connection]:
    """Apre una connessione per singola operazione e la chiude sempre.

    Una connessione per operazione evita i problemi di SQLite fra thread
    diversi (FastAPI esegue gli endpoint sincroni in un threadpool, e la
    sentinella gira in un thread suo).
    """
    if scrittura:
        _lucchetto_scrittura.acquire()
    conn = sqlite3.connect(impostazioni().DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        # WAL: lettori e scrittore non si bloccano a vicenda.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()
        if scrittura:
            _lucchetto_scrittura.release()


def _migra(conn: sqlite3.Connection) -> None:
    """Aggiunge le colonne nuove a un archivio creato da una versione precedente.

    Nessuno strumento di migrazione: sono due colonne, si fa a mano e si
    controlla prima se ci sono gia'.
    """
    colonne = {riga["name"] for riga in conn.execute("PRAGMA table_info(alert)")}
    if not colonne:
        return  # tabella non ancora creata: ci pensa lo SCHEMA
    if "impronta" not in colonne:
        log.warning("archivio da aggiornare: aggiungo alert.impronta")
        conn.execute("ALTER TABLE alert ADD COLUMN impronta TEXT NOT NULL DEFAULT ''")
        # Le righe vecchie non hanno impronta: gli diamo la loro chiave naturale
        # cosi' l'indice unico non le rifiuta.
        conn.execute(
            "UPDATE alert SET impronta = 'vecchio-' || id WHERE impronta = ''"
        )
    if "ritardo_sec" not in colonne:
        log.warning("archivio da aggiornare: aggiungo alert.ritardo_sec")
        conn.execute("ALTER TABLE alert ADD COLUMN ritardo_sec REAL")


def inizializza() -> None:
    """Crea o aggiorna le tabelle. Va chiamata all'avvio del server.

    L'ordine conta: prima le tabelle, poi le colonne mancanti, poi gli indici.
    Un indice su una colonna non ancora aggiunta fallirebbe.
    """
    with connessione(scrittura=True) as conn:
        conn.executescript(SCHEMA)
        _migra(conn)
        conn.executescript(INDICI)


def salva_alert(alert: AlertIn) -> tuple[int, bool]:
    """Scrive l'alert in archivio.

    Restituisce (id, gia_visto). `gia_visto` e' True se lo stesso alert era
    gia' arrivato: succede quando TradingView o il tunnel ritentano la
    consegna, ed e' il motivo per cui esiste l'impronta. In quel caso non si
    inserisce niente e si restituisce l'id della riga originale.

    Il payload completo viene conservato in JSON, ma senza il campo `secret`.
    """
    payload: dict[str, Any] = alert.model_dump(by_alias=True)
    payload.pop("secret", None)
    impronta = alert.impronta()

    with connessione(scrittura=True) as conn:
        esistente = conn.execute(
            "SELECT id FROM alert WHERE impronta = ?", (impronta,)
        ).fetchone()
        if esistente is not None:
            return int(esistente["id"]), True

        cur = conn.execute(
            """
            INSERT INTO alert (
                impronta, ricevuto_utc, simbolo, tf, chiusura_candela_utc,
                apertura, massimo, minimo, chiusura, rsi, nota,
                ritardo_sec, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                impronta,
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
                alert.ritardo_secondi(),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        id_alert = cur.lastrowid

    if id_alert is None:
        raise sqlite3.Error("inserimento alert non ha restituito un id")
    return id_alert, False


def salva_decisione(
    alert_id: int,
    decisione: Decision,
    esito: Esito,
    dettaglio: Optional[str] = None,
    ticket: Optional[int] = None,
) -> int:
    """Scrive la decisione presa per un alert, con il suo esito."""
    with connessione(scrittura=True) as conn:
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

    Serve alla sentinella: sul broker non ci sono ordini pendenti, quindi la
    memoria dei livelli di stop e target vive solo qui.
    """
    with connessione(scrittura=True) as conn:
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
    with connessione(scrittura=True) as conn:
        conn.execute(
            """
            UPDATE posizione
               SET stato = 'chiusa',
                   chiusa_utc = ?,
                   prezzo_uscita = ?,
                   motivo_chiusura = ?
             WHERE id = ? AND stato = 'aperta'
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
            "candela": conn.execute("SELECT COUNT(*) FROM candela").fetchone()[0],
        }


def salva_candela(
    strumento: str,
    tf: str,
    chiusura_utc: str,
    apertura: float,
    massimo: float,
    minimo: float,
    chiusura: float,
    origine: str = "tradingview",
) -> bool:
    """Archivia una candela chiusa. True se e' nuova, False se gia' c'era.

    E' l'archivio dei prezzi su cui il motore ragiona: le candele arrivano da
    TradingView, una per alert, e restano. La chiave e' (strumento, tf,
    chiusura), quindi lo stesso alert riconsegnato non duplica nulla.

    `origine` distingue le candele arrivate dal vivo da quelle importate: una
    riga importata da un CSV vale come una ricevuta dal webhook, ma sapere
    quale e' quale serve quando qualcosa non torna.
    """
    with connessione(scrittura=True) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO candela (
                strumento, tf, chiusura_utc, apertura, massimo, minimo,
                chiusura, origine, ricevuta_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (strumento, tf, chiusura_utc, apertura, massimo, minimo,
             chiusura, origine, adesso_utc()),
        )
        return cur.rowcount > 0


def salva_candele(righe: list[dict[str, Any]], origine: str = "importazione") -> tuple[int, int]:
    """Archivia molte candele in un colpo solo. Restituisce (nuove, gia' viste)."""
    if not righe:
        return 0, 0
    with connessione(scrittura=True) as conn:
        prima = conn.execute("SELECT COUNT(*) FROM candela").fetchone()[0]
        conn.executemany(
            """
            INSERT OR IGNORE INTO candela (
                strumento, tf, chiusura_utc, apertura, massimo, minimo,
                chiusura, origine, ricevuta_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r["strumento"], r["tf"], r["chiusura_utc"], r["apertura"],
                 r["massimo"], r["minimo"], r["chiusura"], origine, adesso_utc())
                for r in righe
            ],
        )
        dopo = conn.execute("SELECT COUNT(*) FROM candela").fetchone()[0]
    nuove = dopo - prima
    return nuove, len(righe) - nuove


def candele_archiviate(
    strumento: str,
    tf: str,
    limite: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Le candele di uno strumento su un timeframe, dalla piu' vecchia.

    Con `limite` restituisce le piu' recenti, comunque in ordine cronologico:
    e' quello che serve al motore, che guarda sempre la coda della serie.
    """
    with connessione() as conn:
        if limite is None:
            righe = conn.execute(
                "SELECT * FROM candela WHERE strumento = ? AND tf = ? "
                "ORDER BY chiusura_utc",
                (strumento, tf),
            ).fetchall()
        else:
            righe = conn.execute(
                "SELECT * FROM candela WHERE strumento = ? AND tf = ? "
                "ORDER BY chiusura_utc DESC LIMIT ?",
                (strumento, tf, limite),
            ).fetchall()
            righe = list(reversed(righe))
    return [dict(riga) for riga in righe]


def copertura_candele() -> list[dict[str, Any]]:
    """Quante candele ci sono per strumento e timeframe, e da quando.

    Serve a sapere se l'archivio basta prima di accendere il motore: senza
    storia sufficiente DEF-26 fa tacere i timeframe, e il bot non opera senza
    che sia evidente il perche'.
    """
    with connessione() as conn:
        righe = conn.execute(
            """
            SELECT strumento, tf, COUNT(*) AS quante,
                   MIN(chiusura_utc) AS dalla, MAX(chiusura_utc) AS alla
              FROM candela
             GROUP BY strumento, tf
             ORDER BY strumento, tf
            """
        ).fetchall()
    return [dict(riga) for riga in righe]


def decisione_completa(id_decisione: int) -> Optional[dict[str, Any]]:
    """Una decisione con l'alert che l'ha innescata, per poterla ridisegnare."""
    with connessione() as conn:
        riga = conn.execute(
            """
            SELECT d.*, a.simbolo AS alert_simbolo, a.tf AS alert_tf,
                   a.chiusura_candela_utc, a.chiusura AS alert_chiusura
              FROM decisione d
              JOIN alert a ON a.id = d.alert_id
             WHERE d.id = ?
            """,
            (id_decisione,),
        ).fetchone()
    return dict(riga) if riga else None


def ultime_decisioni(quante: int = 5) -> list[dict[str, Any]]:
    """Le ultime decisioni prese, per capire al volo cosa sta succedendo."""
    with connessione() as conn:
        righe = conn.execute(
            """
            SELECT d.id, d.creata_utc, a.simbolo, a.tf, d.azione, d.esito,
                   d.motivo, d.dettaglio
              FROM decisione d
              JOIN alert a ON a.id = d.alert_id
             ORDER BY d.id DESC
             LIMIT ?
            """,
            (quante,),
        ).fetchall()
    return [dict(riga) for riga in righe]
