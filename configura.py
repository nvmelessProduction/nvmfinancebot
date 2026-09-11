"""Configurazione guidata, una volta sola: scrive il file .env.

Si lancia da solo al primo `avvia.bat`. Fa tre domande — Telegram, MT5,
modalita' — e scrive `.env`. Chi ha gia' un `.env` non lo vede mai piu'.

Non chiede il segreto del webhook: con il bot che si prende i dati da solo
non serve piu' nessun webhook. Viene generato lo stesso, cosi' chi un giorno
volesse riaccendere gli alert non deve tornare qui.
"""

from __future__ import annotations

import secrets
import shutil
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
ENV = RADICE / ".env"
MODELLO = RADICE / ".env.example"


def chiedi(domanda: str, default: str = "") -> str:
    suggerimento = f" [{default}]" if default else " (invio per saltare)"
    risposta = input(f"{domanda}{suggerimento}: ").strip()
    return risposta or default


def si_o_no(domanda: str, default: bool = True) -> bool:
    predefinito = "S/n" if default else "s/N"
    while True:
        risposta = input(f"{domanda} [{predefinito}]: ").strip().lower()
        if not risposta:
            return default
        if risposta in ("s", "si", "sì", "y", "yes"):
            return True
        if risposta in ("n", "no"):
            return False
        print("  Rispondi s oppure n.")


def scrivi(valori: dict[str, str]) -> None:
    """Riscrive .env dal modello, sostituendo solo le chiavi indicate."""
    if not MODELLO.exists():
        raise SystemExit(f"manca {MODELLO.name}: il progetto non e' completo")

    righe = MODELLO.read_text(encoding="utf-8").splitlines()
    scritte: set[str] = set()
    risultato: list[str] = []
    for riga in righe:
        nudo = riga.strip()
        if nudo and not nudo.startswith("#") and "=" in nudo:
            chiave = nudo.split("=", 1)[0].strip()
            if chiave in valori:
                risultato.append(f"{chiave}={valori[chiave]}")
                scritte.add(chiave)
                continue
        risultato.append(riga)

    for chiave, valore in valori.items():
        if chiave not in scritte:
            risultato.append(f"{chiave}={valore}")

    if ENV.exists():
        shutil.copy2(ENV, ENV.with_suffix(".env.precedente"))
    ENV.write_text("\n".join(risultato) + "\n", encoding="utf-8")


def main() -> int:
    print()
    print("=" * 70)
    print("  CONFIGURAZIONE — si fa una volta sola")
    print("=" * 70)

    if ENV.exists():
        print(f"\n{ENV.name} esiste gia'.")
        if not si_o_no("Vuoi rifarlo da capo?", default=False):
            print("Lascio tutto com'e'.")
            return 0
        print("Il file attuale viene salvato come .env.precedente.\n")

    valori: dict[str, str] = {
        "FORNITORE_DATI": "mercato",
        "WEBHOOK_SECRET": secrets.token_urlsafe(32),
    }

    # --- Telegram ---------------------------------------------------------
    print("\n--- TELEGRAM -------------------------------------------------")
    print("Serve a farti sapere cosa sta facendo il bot. Puoi saltarlo:")
    print("senza, scrive solo nel file bot.log.")
    print()
    print("Per averlo: su Telegram cerca @BotFather, scrivi /newbot, segui le")
    print("istruzioni. Ti da' un codice lungo: e' il token.")
    print()
    token = chiedi("Token del bot Telegram")
    chat = ""
    if token:
        print()
        print("Adesso scrivi un messaggio qualsiasi al bot che hai creato, poi")
        print("apri nel browser questo indirizzo e cerca  \"chat\":{\"id\":NUMERO")
        print(f"   https://api.telegram.org/bot{token}/getUpdates")
        print()
        chat = chiedi("Numero della chat")
    valori["TELEGRAM_TOKEN"] = token
    valori["TELEGRAM_CHAT_ID"] = chat

    # --- MetaTrader 5 -----------------------------------------------------
    print("\n--- METATRADER 5 ---------------------------------------------")
    print("Il bot si aggancia al terminale MT5 che tieni aperto: non fa il")
    print("login da solo, quindi qui non serve la password.")
    print()
    print("Alcuni broker aggiungono un suffisso ai simboli: XAUUSD.a, XAUUSD_ecn.")
    print("Se non sai quale sia, lascia vuoto: lo scopri dopo con")
    print("   python prova_esecuzione.py")
    print()
    valori["MT5_SUFFISSO_SIMBOLI"] = chiedi("Suffisso dei simboli del tuo broker")

    # --- Modalita' --------------------------------------------------------
    print("\n--- MODALITA' -------------------------------------------------")
    print("  dry_run   guarda e scrive cosa avrebbe fatto. Non tocca il conto.")
    print("  semi      ti avvisa su Telegram e aspetta che decida tu.")
    print("  auto      opera da solo.")
    print()
    print("Si parte sempre da dry_run. Cambierai riga MODE nel file .env")
    print("quando ti fiderai.")
    valori["MODE"] = "dry_run"

    scrivi(valori)

    print("\n" + "=" * 70)
    print(f"  Fatto. Ho scritto {ENV.name}")
    print("=" * 70)
    print("\nDa adesso in poi ti basta lanciare avvia.bat: questa schermata")
    print("non la rivedrai piu'.\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrotto: non ho scritto niente.")
        sys.exit(1)
