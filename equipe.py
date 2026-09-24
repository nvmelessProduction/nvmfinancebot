"""Guarda l'equipe al lavoro: le ultime decisioni, agente per agente.

## A che serve

A vedere. Per venti giorni la domanda e' stata *"perche' il bot ha aperto
quella?"*, e la risposta stava in un archivio che leggeva una persona sola.

Legge le decisioni gia' in archivio e le riscrive come verbale dell'equipe.
Non serve riavviare niente: i dati ci sono gia', mancava solo chi li
raccontasse.

## Uso

    python equipe.py                      # le ultime cinque, a schermo
    python equipe.py --quante 20
    python equipe.py --telegram           # e le manda sul telefono
    python equipe.py --solo-aperte        # solo quelle diventate ordini
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import equipe as eq
from core.apprendimento import carica as carica_appresi
from core.config import impostazioni

# Dove gli agenti tengono cio' che hanno imparato. Assente = tutti al manuale.
APPRESI = Path("dati/appresi.json")


def leggi(db: str, quante: int, solo_aperte: bool) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        dove = "WHERE d.azione IN ('BUY','SELL')" if solo_aperte else ""
        righe = conn.execute(
            f"""SELECT d.id, d.creata_utc, d.azione, d.motivo, d.esito,
                       d.dettaglio, d.volume, d.sl, d.tp, d.tf_crt,
                       d.responso_romeo, d.rapporto_giud01,
                       a.simbolo, a.tf, a.chiusura
                FROM decisione d LEFT JOIN alert a ON a.id = d.alert_id
                {dove}
                ORDER BY d.id DESC LIMIT ?""", (quante,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in righe]


def _responso(grezzo: Optional[str]) -> dict:
    if not grezzo:
        return {}
    try:
        letto = json.loads(grezzo)
    except (json.JSONDecodeError, TypeError):
        return {}
    return letto if isinstance(letto, dict) else {}


def verbale_di(riga: dict, appresi: dict) -> str:
    simbolo = riga.get("simbolo") or "?"
    azione = riga.get("azione") or "NONE"
    if azione == "BUY":
        titolo = f"🟢 <b>{simbolo} LONG</b>"
    elif azione == "SELL":
        titolo = f"🔴 <b>{simbolo} SHORT</b>"
    else:
        titolo = f"⬜ <b>{simbolo}</b> — nessuna operazione"
    quando = (riga.get("creata_utc") or "")[:19].replace("T", " ")
    titolo += f"  ·  {quando} UTC  ·  #{riga['id']}"

    ingresso = riga.get("chiusura")
    conclusione = riga.get("motivo") or ""
    if riga.get("esito"):
        conclusione = f"{riga['esito']} — {conclusione}"

    return eq.verbale(
        titolo=titolo,
        lettura={"coppia": riga.get("tf_crt") or riga.get("tf")},
        responso=_responso(riga.get("responso_romeo")),
        ingresso=ingresso,
        stop=riga.get("sl"),
        target=riga.get("tp"),
        volume=riga.get("volume"),
        appresi=appresi,
        conclusione=conclusione,
    )


def _a_schermo(testo: str) -> str:
    """Via i tag HTML, e via le emoji che la console di Windows non sa scrivere.

    Il terminale qui e' `cp1252`: un'emoji lo fa cadere con `UnicodeEncodeError`
    a meta' stampa. Su Telegram le emoji sono il modo piu' rapido di vedere a
    colpo d'occhio chi ha detto cosa, quindi restano li' e spariscono solo
    qui.
    """
    for tag in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
        testo = testo.replace(tag, "")
    sostituzioni = {"✅": "[si]", "❌": "[no]", "⬜": "[  ]",
                    "🟢": "LONG ", "🔴": "SHORT", "🔍": "*", "🗣": "*",
                    "📐": "*", "🧠": "*", "⚖️": "*", "🎓": "*", "·": "-",
                    "—": "-", "’": "'", "×": "x", "−": "-", "±": "+/-",
                    # Gli accenti si traslitterano invece di diventare "?":
                    # "il prezzo non ? stato respinto" e' illeggibile, e la
                    # riga esiste per essere letta.
                    "à": "a'", "è": "e'", "é": "e'", "ì": "i'", "ò": "o'",
                    "ù": "u'", "À": "A'", "È": "E'", "É": "E'"}
    for speciale, piatto in sostituzioni.items():
        testo = testo.replace(speciale, piatto)
    return testo.encode("ascii", "replace").decode("ascii")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--quante", type=int, default=5)
    p.add_argument("--solo-aperte", action="store_true")
    p.add_argument("--telegram", action="store_true",
                   help="manda i verbali sul canale dell'equipe "
                        "(TELEGRAM_CHAT_EQUIPE, separato da quello operativo)")
    p.add_argument("--db", default=None)
    a = p.parse_args()

    db = a.db or impostazioni().DB_PATH
    if not Path(db).exists():
        print(f"manca l'archivio: {db}")
        return 2

    appresi = carica_appresi(APPRESI)
    righe = leggi(db, a.quante, a.solo_aperte)
    if not righe:
        print("nessuna decisione in archivio")
        return 1

    for riga in reversed(righe):
        testo = verbale_di(riga, appresi)
        print(_a_schermo(testo))
        print("-" * 60)
        if a.telegram:
            from core.notifier import invia_all_equipe
            ok, detto = invia_all_equipe(testo)
            if not ok:
                print(f"   (canale equipe: {detto})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
