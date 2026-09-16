"""Ricostruisce il file `.env` senza che nessun segreto passi da una chat.

## Perche' esiste

Il `.env` tiene token e credenziali. Dettarli a voce, incollarli in una
conversazione o passarli fra macchine e' il modo in cui sono finiti pubblici
la prima volta. Questo script li prende da dove sono gia' — la storia di git
e il file attuale — e li riscrive, senza mai stamparli.

Cosa NON fa, di proposito: non mostra un solo valore. Dice se una chiave c'e'
o manca, e basta. Un elenco di chiavi si puo' incollare ovunque; un elenco di
valori no.

## Da dove prende i valori, in ordine di precedenza

    1. il `.env` ATTUALE           quello che hai gia' messo vince su tutto
    2. la storia di git            i valori del vecchio `.env`, prima che
                                   venisse tolto dal versionamento
    3. i valori predefiniti        quelli scritti qui sotto

Cosi' rilanciarlo e' sempre sicuro: non sovrascrive mai quello che hai
scritto a mano.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Il commit in cui il `.env` fu caricato, prima di essere tolto dal
# versionamento in `d9384e7`. E' li' che stanno i valori vecchi.
COMMIT_STORICO = "6740333"

PERCORSO = Path(".env")

# Cio' che il bot vuole adesso. I valori qui sono quelli giusti per partire:
# vengono usati solo se la chiave non esiste gia' da nessuna parte.
NUOVI: dict[str, str] = {
    "MODE": "dry_run",
    "FORNITORE_DATI": "dukascopy",
    "MERCATO_INTERVALLO_SEC": "120",
    "GIUDIZIO_ATTIVO": "true",
    "ANTHROPIC_API_KEY": "",
    "MT5_LOGIN": "0",
    "MT5_PASSWORD": "",
    "MT5_SERVER": "",
    "MT5_SUFFISSO_SIMBOLI": "",
    "SENTINELLA_ATTIVA": "true",
    "SENTINELLA_INTERVALLO_SEC": "5",
    "CONSENTI_CONTO_REALE": "false",
    "VOLUME_MASSIMO": "1.0",
    "MAX_POSIZIONI_APERTE": "5",
    "TELEGRAM_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "WEBHOOK_SECRET": "",
}

# Le chiavi senza le quali il bot non fa il suo lavoro. Se mancano lo dice.
INDISPENSABILI = ("ANTHROPIC_API_KEY",)

SEZIONI: list[tuple[str, tuple[str, ...]]] = [
    ("Modalita' operativa — dry_run valuta e registra, NON manda ordini",
     ("MODE",)),
    ("Dati di analisi — Dukascopy: prezzi scambiati, spread misurato",
     ("FORNITORE_DATI", "MERCATO_INTERVALLO_SEC")),
    ("Il trader discrezionale — senza la chiave si astiene, e l'astensione\n"
     "# ferma l'ordine (PRIN-99: se non si sa, non si opera)",
     ("GIUDIZIO_ATTIVO", "ANTHROPIC_API_KEY")),
    ("MetaTrader 5 — con MT5_LOGIN=0 il bot usa il terminale gia' collegato\n"
     "# a mano. MT5_SUFFISSO_SIMBOLI lo trova `python prova_esecuzione.py`:\n"
     "# sbagliarlo rende muti i conteggi di RISK-02 e RISK-06 SENZA errori",
     ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_SUFFISSO_SIMBOLI")),
    ("Sorveglianza di stop e target",
     ("SENTINELLA_ATTIVA", "SENTINELLA_INTERVALLO_SEC")),
    ("Salvaguardie — non toccarle finche' non hai dati tuoi",
     ("CONSENTI_CONTO_REALE", "VOLUME_MASSIMO", "MAX_POSIZIONI_APERTE")),
    ("Telegram — facoltativo, solo notifiche",
     ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")),
    ("Webhook — serve solo con gli alert TradingView",
     ("WEBHOOK_SECRET",)),
]


def leggi(testo: str) -> dict[str, str]:
    """Le coppie chiave=valore di un file .env. Commenti e vuote si saltano."""
    fuori: dict[str, str] = {}
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, _, valore = riga.partition("=")
        chiave = chiave.strip()
        if chiave:
            fuori[chiave] = valore.strip()
    return fuori


def dalla_storia() -> dict[str, str]:
    """Il vecchio `.env`, dal commit in cui era ancora versionato."""
    try:
        esito = subprocess.run(
            ["git", "show", f"{COMMIT_STORICO}:.env"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if esito.returncode != 0:
        return {}
    return leggi(esito.stdout)


def main() -> int:
    attuale = leggi(PERCORSO.read_text(encoding="utf-8")) if PERCORSO.exists() else {}
    storico = dalla_storia()

    print(f"chiavi nel .env attuale:      {len(attuale)}")
    print(f"chiavi recuperate da git:     {len(storico)}")

    # Precedenza: quello che hai gia' scritto vince sempre.
    valori = {**NUOVI, **storico, **attuale}

    # Ma le impostazioni che il bot richiede ADESSO vanno aggiornate, perche'
    # il vecchio .env puntava a una fonte dati che non si usa piu'.
    for chiave in ("FORNITORE_DATI", "GIUDIZIO_ATTIVO"):
        if not attuale.get(chiave):
            valori[chiave] = NUOVI[chiave]

    if PERCORSO.exists():
        salvataggio = PERCORSO.with_suffix(".env.precedente")
        salvataggio.write_text(PERCORSO.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"copia del precedente in:      {salvataggio.name}")

    righe: list[str] = [
        "# File generato da crea_env.py.",
        "# NON va mai su GitHub: e' gia' in .gitignore, e deve restarci.",
        "",
    ]
    scritte: set[str] = set()
    for titolo, chiavi in SEZIONI:
        righe.append(f"# ===== {titolo} =====")
        for chiave in chiavi:
            righe.append(f"{chiave}={valori.get(chiave, '')}")
            scritte.add(chiave)
        righe.append("")

    # Tutto ciò che c'era e non rientra nelle sezioni: non si perde.
    residue = sorted(set(valori) - scritte)
    if residue:
        righe.append("# ===== Altre impostazioni gia' presenti =====")
        for chiave in residue:
            righe.append(f"{chiave}={valori[chiave]}")
        righe.append("")

    PERCORSO.write_text("\n".join(righe), encoding="utf-8")
    print(f"\nscritto {PERCORSO} con {len(valori)} chiavi\n")

    # Il rendiconto: CHE COSA c'e', mai QUANTO vale.
    print("stato delle chiavi (nessun valore viene mostrato):")
    mancano: list[str] = []
    for chiave in sorted(valori):
        pieno = bool(valori[chiave])
        segno = "ok " if pieno else "   "
        nota = ""
        if not pieno and chiave in INDISPENSABILI:
            nota = "  <-- SERVE, vai a metterla"
            mancano.append(chiave)
        elif not pieno:
            nota = "  (vuota: va bene cosi')"
        print(f"  {segno} {chiave}{nota}")

    if mancano:
        print(f"\nDa compilare a mano: {', '.join(mancano)}")
        print("Aprilo con:  notepad .env")
        return 1

    print("\nTutto a posto. Prossimo passo:  python importa_dukascopy.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
