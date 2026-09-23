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
    ticket          INTEGER,
    -- 07_casi.md §3.1: distanza key level/gap normalizzata sull'ATR. Si
    -- registra per ogni decisione e non entra in nessun calcolo: e' il dato
    -- che deve chiudere PA-44 coi numeri invece che a occhio.
    rapporto_giud01 REAL
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
    -- Stato di GEST-12: quanto serve a ricostruire una `gestione.Posizione`
    -- dopo un riavvio, senza chiedere nulla al broker.
    tp1                 REAL,
    tf_crt              TEXT,
    volume_iniziale     REAL,
    tp1_raggiunto       INTEGER NOT NULL DEFAULT 0,
    spread_ingresso     REAL,
    -- RISK-02: la frazione di equity che questa posizione rischia ORA.
    -- Cambia a ogni nuova apertura nel gruppo di correlazione, perche'
    -- il ridimensionamento porta tutte allo stesso rischio.
    rischio_corrente    REAL,
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

    # Lo stato che GEST-12 vuole ricostruibile dopo un riavvio. Finche' queste
    # colonne non c'erano, TP1 veniva calcolato dal motore e buttato via un
    # passaggio dopo: nessun parziale, nessun break even, e nessun modo di
    # farli. Vanno tutte con un default, perche' le posizioni gia' aperte
    # quando l'archivio si aggiorna non hanno questo stato e non devono
    # sparire: `sentinella` le riconosce e le lascia alla vecchia gestione
    # (stop e target soli), che e' esattamente cio' che erano.
    posizione = {riga["name"] for riga in conn.execute("PRAGMA table_info(posizione)")}
    if posizione:
        for nome, tipo in (
            ("tp1", "REAL"),
            ("tf_crt", "TEXT"),
            ("volume_iniziale", "REAL"),
            ("tp1_raggiunto", "INTEGER NOT NULL DEFAULT 0"),
            ("spread_ingresso", "REAL"),
            ("rischio_corrente", "REAL"),
        ):
            if nome not in posizione:
                log.warning("archivio da aggiornare: aggiungo posizione.%s", nome)
                conn.execute(f"ALTER TABLE posizione ADD COLUMN {nome} {tipo}")

    decisione = {riga["name"] for riga in conn.execute("PRAGMA table_info(decisione)")}
    if decisione and "rapporto_giud01" not in decisione:
        log.warning("archivio da aggiornare: aggiungo decisione.rapporto_giud01")
        conn.execute("ALTER TABLE decisione ADD COLUMN rapporto_giud01 REAL")
        if "volume_iniziale" not in posizione:
            # Le righe vecchie non hanno mai avuto parziali: il volume attuale
            # e' anche quello di partenza.
            conn.execute(
                "UPDATE posizione SET volume_iniziale = volume "
                "WHERE volume_iniziale IS NULL"
            )


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
                volume, sl, tp, esito, dettaglio, ticket, rapporto_giud01
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                decisione.rapporto_giud01,
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
    tp1: Optional[float] = None,
    tf_crt: Optional[str] = None,
    spread_ingresso: Optional[float] = None,
    rischio_corrente: Optional[float] = None,
) -> int:
    """Annota una posizione aperta dal bot.

    Serve alla sentinella: sul broker non ci sono ordini pendenti, quindi la
    memoria dei livelli di stop e target vive solo qui. Da REV-54 ci vive
    anche lo stato che GEST-12 vuole ricostruibile dopo un riavvio: `tp1`,
    il timeframe del CRT di origine, il volume iniziale e lo spread al
    momento dell'ingresso, che serve al buffer di break even di PA-46.
    """
    with connessione(scrittura=True) as conn:
        cur = conn.execute(
            """
            INSERT INTO posizione (
                ticket, decisione_id, simbolo, direzione, volume,
                prezzo_ingresso, sl, tp, tp1, tf_crt, volume_iniziale,
                tp1_raggiunto, spread_ingresso, rischio_corrente, aperta_utc, stato
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'aperta')
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
                tp1,
                tf_crt,
                volume,
                spread_ingresso,
                rischio_corrente,
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


def applica_parziale_tp1(
    id_posizione: int,
    volume_residuo: float,
    nuovo_stop: float,
) -> None:
    """GEST-04 — Registra il parziale del 25% e lo stop portato a break even.

    Le due scritture stanno in una transazione sola perche' sono un fatto
    solo: una posizione col volume ridotto e lo stop ancora all'estremo di N2
    rischierebbe la distanza piena su un quarto di size, e una posizione a
    break even col volume intero direbbe che il parziale e' avvenuto quando
    non e' avvenuto.

    `tp1_raggiunto` a 1 e' cio' che rende l'operazione irripetibile: GEST-05
    vieta di muovere ancora lo stop, e questo flag e' il solo modo che la
    sentinella ha di saperlo dopo un riavvio (GEST-12).

    La clausola `tp1_raggiunto = 0` rende la scrittura idempotente: se il giro
    successivo della sentinella rileggesse la stessa posizione prima che la
    memoria si aggiorni, non chiuderebbe un secondo quarto.
    """
    with connessione(scrittura=True) as conn:
        conn.execute(
            """
            UPDATE posizione
               SET volume = ?,
                   sl = ?,
                   tp1_raggiunto = 1
             WHERE id = ? AND stato = 'aperta' AND tp1_raggiunto = 0
            """,
            (volume_residuo, nuovo_stop, id_posizione),
        )


def aggiorna_target(id_posizione: int, nuovo_target: float) -> None:
    """GEST-08 — Estende il target finale del 75% residuo.

    L'estensione e' a senso unico (GEST-08): chi chiama ha gia' verificato che
    il nuovo target sia piu' lontano del precedente. Qui si scrive e basta.
    """
    with connessione(scrittura=True) as conn:
        conn.execute(
            "UPDATE posizione SET tp = ? WHERE id = ? AND stato = 'aperta'",
            (nuovo_target, id_posizione),
        )


def ridimensiona_posizione(
    id_posizione: int, volume: float, rischio_corrente: float
) -> None:
    """RISK-02 — Adegua volume e rischio di una posizione gia' aperta.

    Il ridimensionamento non tocca stop, TP1 ne' target: cambia quanto si
    rischia, non dove si esce. E non tocca `volume_iniziale`, perche' quello
    e' la base su cui GEST-04 calcola il 25%.
    """
    with connessione(scrittura=True) as conn:
        conn.execute(
            "UPDATE posizione SET volume = ?, rischio_corrente = ? "
            "WHERE id = ? AND stato = 'aperta'",
            (volume, rischio_corrente, id_posizione),
        )


def posizioni_aperte() -> list[dict[str, Any]]:
    """Elenca le posizioni che l'archivio considera ancora aperte."""
    with connessione() as conn:
        righe = conn.execute(
            "SELECT * FROM posizione WHERE stato = 'aperta' ORDER BY id"
        ).fetchall()
    return [dict(riga) for riga in righe]


def crt_gia_stoppati(simbolo: str, direzione: str) -> list[dict[str, Any]]:
    """Le posizioni di questo simbolo e verso finite allo STOP.

    Serve a non rientrare su un CRT che il mercato ha gia' smentito. Un CRT
    stoppato non e' un CRT sfortunato: lo stop sta all'estremo dello sweep, e
    toccarlo significa che il prezzo e' andato OLTRE quell'estremo, cioe' che
    la lettura del range su cui il setup si reggeva non vale piu' (SETUP-02).

    Il 2026-09-23 il bot rientrava sullo stesso identico setup pochi minuti
    dopo esserci stato stoppato -- XAUUSD SELL con stop 4289,74 e target
    4276,71 inviato alle 19:47, 19:50 e 19:54 -- perche' il controllo sui
    doppioni guardava solo le posizioni ANCORA aperte, e una posizione
    stoppata in pochi secondi non lo e' piu'.
    """
    with connessione() as conn:
        righe = conn.execute(
            "SELECT tp, ticket, chiusa_utc FROM posizione "
            "WHERE simbolo = ? AND direzione = ? AND stato != 'aperta' "
            "AND motivo_chiusura LIKE 'sl%' AND tp IS NOT NULL "
            "ORDER BY id DESC LIMIT 200",
            (simbolo, direzione),
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
        nuova = cur.rowcount > 0
    if nuova:
        _archivio_cambiato()
    return nuova


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
    if nuove:
        _archivio_cambiato()
    return nuove, len(righe) - nuove


def dimentica_candele(strumento: str, tranne_origine: str) -> int:
    """Cancella le candele di uno strumento che vengono da un'altra fonte.

    Serve a una cosa sola e va usata solo per quella: rendere **omogenea**
    una serie che si e' riempita da due fonti diverse.

    Il caso vero e' il DXY. Una macchina puo' avere un `ICEUS` arrivato dalla
    fonte gratuita -- estremi attenuati, cioe' massimi e minimi campionati
    invece che toccati -- e poi ricevere quello calcolato dai costituenti
    Dukascopy. `salva_candele` fa `INSERT OR IGNORE`, quindi le nuove
    riempirebbero solo i buchi e la serie diventerebbe un mosaico: DEF-16
    confronta ogni candela con la precedente, e sui punti di giunzione
    confronterebbe due oggetti costruiti in modi diversi.

    Un mosaico e' peggio di entrambe le fonti prese da sole, e non lascia
    alcun segno: le candele ci sono tutte e sembrano giuste.

    Restituisce quante ne ha cancellate, perche' chi chiama lo deve dire.
    """
    with connessione(scrittura=True) as conn:
        cur = conn.execute(
            "DELETE FROM candela WHERE strumento = ? AND origine != ?",
            (strumento, tranne_origine),
        )
        cancellate = cur.rowcount
    if cancellate:
        _archivio_cambiato()
    return cancellate


def candele_archiviate(
    strumento: str,
    tf: str,
    limite: Optional[int] = None,
    dopo: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Le candele di uno strumento su un timeframe, dalla piu' vecchia.

    Con `limite` restituisce le piu' recenti, comunque in ordine cronologico:
    e' quello che serve al motore, che guarda sempre la coda della serie.

    Con `dopo` restituisce solo quelle chiuse DOPO quell'istante. Serve a chi
    tiene gia' in memoria la serie e vuole solo la coda nuova: l'archivio
    cresce in fondo e le candele non si modificano mai sul posto, quindi
    rileggerle tutte per aggiungerne una era il grosso del ritardo.
    """
    if dopo is not None:
        with connessione() as conn:
            righe = conn.execute(
                "SELECT * FROM candela WHERE strumento = ? AND tf = ? "
                "AND chiusura_utc > ? ORDER BY chiusura_utc",
                (strumento, tf, dopo),
            ).fetchall()
        return [dict(riga) for riga in righe]

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


# Quante volte sono state scritte candele da quando il processo e' partito.
# Serve a `impronta_candele` per sapere se puo' fidarsi di cio' che ricorda.
_VERSIONE_ARCHIVIO: int = 0
_IMPRONTE: dict[tuple[str, str], tuple[tuple, tuple]] = {}


def _archivio_cambiato() -> None:
    """Una scrittura di candele: le impronte ricordate non valgono piu'."""
    global _VERSIONE_ARCHIVIO
    _VERSIONE_ARCHIVIO += 1


def impronta_candele(strumento: str) -> tuple:
    """Come sono messe adesso le candele di uno strumento, in poche decine di ms.

    Serve a rispondere a "e' cambiato qualcosa da quando ho letto?" senza
    rileggere. Per EURUSD l'archivio e' di 285.000 candele: leggerlo costa due
    secondi e mezzo, questa impronta cinquantacinque millesimi.

    `(timeframe, quante, ultima)` per ogni timeframe e' un'impronta fedele
    perche' le candele si inseriscono e basta: `salva_candele` usa
    `INSERT OR IGNORE` e nessuno le aggiorna mai sul posto. Una candela nuova
    in coda cambia `ultima`, una che tappa un buco a meta' serie cambia
    `quante`, una cancellata pure. Se non cambia nulla di tutto questo, le
    candele sono le stesse di prima -- non "probabilmente", proprio le stesse.
    """
    # L'impronta si ricalcola solo quando qualcuno ha scritto.
    #
    # La query e' gia' su indice coprente, ma deve comunque contare tutte le
    # righe dello strumento: 47 ms su 285.000 candele. Chiamata quindici
    # volte per valutazione faceva 700 ms -- il costo piu' grosso rimasto
    # dopo aver sistemato `candele_visibili` (misurato il 2026-09-23).
    #
    # `_VERSIONE_ARCHIVIO` cambia ad ogni scrittura di candele, quindi la
    # memoria e' ESATTA e non a scadenza: una candela appena archiviata
    # invalida l'impronta nello stesso istante in cui entra. Una cache a
    # tempo invece avrebbe potuto servire un'impronta vecchia proprio
    # nell'alert che porta la candela nuova.
    # La chiave comprende il FILE dell'archivio: le prove ne aprono uno
    # temporaneo per ciascuna, e una memoria legata al solo nome dello
    # strumento servirebbe l'impronta di un database a un altro.
    chiave = (impostazioni().DB_PATH, strumento)
    with connessione() as conn:
        # Il testimone: `MAX(rowid)` sull'intera tabella costa O(1) in SQLite
        # e cambia ad OGNI inserimento, da qualunque parte arrivi. Il
        # contatore in memoria da solo non bastava -- basta un percorso di
        # scrittura non intercettato e la memoria serve dati vecchi, che e'
        # esattamente il guasto che si sta cercando di evitare.
        testimone = conn.execute("SELECT MAX(rowid) FROM candela").fetchone()[0]
        valido = (testimone, _VERSIONE_ARCHIVIO)

        memoria = _IMPRONTE.get(chiave)
        if memoria is not None and memoria[0] == valido:
            return memoria[1]

        righe = conn.execute(
            "SELECT tf, COUNT(*), MAX(chiusura_utc) FROM candela "
            "WHERE strumento = ? GROUP BY tf ORDER BY tf",
            (strumento,),
        ).fetchall()
    fuori = tuple(tuple(r) for r in righe)
    _IMPRONTE[chiave] = (valido, fuori)
    return fuori


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
