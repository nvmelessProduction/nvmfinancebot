"""Il ponte verso Cowork: Claude come trader discrezionale sul bot vivo.

## Due modi di essere il trader discrezionale, e quando serve quale

`core/giudizio_claude.py` chiama l'API e ottiene un verdetto in un secondo.
E' automatico e non richiede che nessuno sia sveglio. Va bene quando il
giudizio puo' essere preso sui soli numeri del dossier.

Questo modulo serve all'altro caso: una sessione Cowork — cioe' Claude con
accesso al repository, ai documenti della strategia e allo storico delle
operazioni — che guarda il setup **in pausa** e decide. E' piu' lento e piu'
informato: puo' rileggere `docs/BIBBIA-CRT.md`, confrontare col grafico,
guardare come sono andate le ultime venti operazioni simili.

Il bot mette in attesa, Cowork risponde, il bot esegue o lascia perdere.

## Perche' il bot non aspetta per sempre

Un setup ha una scadenza: il prezzo si muove e l'ingresso che era buono alla
chiusura della candela non lo e' piu' dieci minuti dopo. `SCADENZA_MINUTI`
la fissa, e allo scadere **il setup decade** — non si esegue.

Decadere e' l'esito giusto, non un ripiego. `SETUP-04` fa gia' decadere un
CRT non eseguito all'apertura di `N3`, e `SETUP-16` vieta di recuperare un
setup saltato. Un'attesa senza scadenza trasformerebbe il trader
discrezionale in un generatore di ordini in ritardo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core import storage
from core.log import diario

log = diario("cowork")

# Quanto vive un setto in attesa. Dieci minuti sono generosi su candele orarie
# e superiori — le uniche su cui questo modo ha senso. Sulle coppie intraday
# il giudizio automatico e' l'unico praticabile.
SCADENZA_MINUTI = 10


@dataclass(frozen=True)
class SetupInAttesa:
    """Un setup approvato dalle regole, in attesa del giudizio di Cowork."""

    id_decisione: int
    strumento: str
    azione: str
    dossier: dict[str, Any]
    creato_utc: str

    @property
    def scaduto(self) -> bool:
        try:
            creato = datetime.fromisoformat(self.creato_utc.replace("Z", "+00:00"))
        except ValueError:
            return True
        return datetime.now(timezone.utc) - creato > timedelta(minutes=SCADENZA_MINUTI)

    def come_json(self) -> dict[str, Any]:
        return {
            "id": self.id_decisione,
            "strumento": self.strumento,
            "azione": self.azione,
            "creato_utc": self.creato_utc,
            "scade_fra_sec": max(0, int(
                (timedelta(minutes=SCADENZA_MINUTI) - (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(self.creato_utc.replace("Z", "+00:00"))
                )).total_seconds()
            )) if not self.scaduto else 0,
            "scaduto": self.scaduto,
            "dossier": self.dossier,
        }


def prepara_tabella() -> None:
    """La coda dei setup in attesa. Una riga per setup, cancellata all'esito."""
    with storage.connessione(scrittura=True) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS giudizio_in_attesa (
                id_decisione  INTEGER PRIMARY KEY,
                strumento     TEXT    NOT NULL,
                azione        TEXT    NOT NULL,
                dossier       TEXT    NOT NULL,
                creato_utc    TEXT    NOT NULL,
                verdetto      TEXT,
                motivo        TEXT,
                deciso_utc    TEXT
            )
        """)


def metti_in_attesa(
    id_decisione: int, strumento: str, azione: str, dossier: dict[str, Any]
) -> None:
    """Il bot parcheggia un setup e va avanti. Non blocca il thread."""
    prepara_tabella()
    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO giudizio_in_attesa "
            "(id_decisione, strumento, azione, dossier, creato_utc) "
            "VALUES (?, ?, ?, ?, ?)",
            (id_decisione, strumento, azione,
             json.dumps(dossier, ensure_ascii=False, sort_keys=True),
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
    log.info("setup %s su %s in attesa del giudizio di Cowork", id_decisione, strumento)


def in_attesa() -> list[SetupInAttesa]:
    """I setup che aspettano un verdetto, i piu' recenti per primi."""
    prepara_tabella()
    with storage.connessione() as conn:
        righe = conn.execute(
            "SELECT * FROM giudizio_in_attesa WHERE verdetto IS NULL "
            "ORDER BY id_decisione DESC"
        ).fetchall()
    fuori = []
    for r in righe:
        try:
            dossier = json.loads(r["dossier"])
        except json.JSONDecodeError:
            dossier = {}
        fuori.append(SetupInAttesa(
            int(r["id_decisione"]), str(r["strumento"]), str(r["azione"]),
            dossier, str(r["creato_utc"]),
        ))
    return fuori


def registra_verdetto(
    id_decisione: int, accetta: bool, motivo: str
) -> tuple[bool, str]:
    """Cowork risponde. Restituisce (eseguibile, spiegazione).

    `eseguibile` e' False anche quando il verdetto e' ACCETTA ma il setup e'
    gia' scaduto: il verdetto si registra lo stesso — serve a misurare se il
    giudizio aggiunga valore — ma l'ordine non parte.
    """
    prepara_tabella()
    setup = next((s for s in in_attesa() if s.id_decisione == id_decisione), None)
    if setup is None:
        return False, f"setup {id_decisione} non e' in attesa (gia' deciso o inesistente)"

    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "UPDATE giudizio_in_attesa SET verdetto = ?, motivo = ?, deciso_utc = ? "
            "WHERE id_decisione = ?",
            ("ACCETTA" if accetta else "RIFIUTA", motivo[:500],
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), id_decisione),
        )

    if setup.scaduto:
        return False, (
            f"verdetto registrato, ma il setup e' scaduto "
            f"(oltre {SCADENZA_MINUTI} minuti): SETUP-16, non si recupera"
        )
    if not accetta:
        return False, "RIFIUTATO da Cowork: nessun ordine"
    return True, "ACCETTATO da Cowork: l'ordine puo' partire"


def scadi_i_vecchi() -> int:
    """Chiude i setup rimasti senza risposta. Quanti ne ha chiusi.

    Va chiamata periodicamente: un setup che nessuno giudica non deve restare
    in coda a sembrare in attesa quando il momento e' passato da un pezzo.
    """
    prepara_tabella()
    scaduti = [s for s in in_attesa() if s.scaduto]
    if not scaduti:
        return 0
    with storage.connessione(scrittura=True) as conn:
        for s in scaduti:
            conn.execute(
                "UPDATE giudizio_in_attesa SET verdetto = 'SCADUTO', "
                "motivo = ?, deciso_utc = ? WHERE id_decisione = ?",
                (f"nessun giudizio entro {SCADENZA_MINUTI} minuti: SETUP-04, il "
                 "setup decade", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 s.id_decisione),
            )
    log.info("%d setup scaduti senza giudizio", len(scaduti))
    return len(scaduti)
