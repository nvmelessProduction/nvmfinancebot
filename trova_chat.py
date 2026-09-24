"""Trova il chat id dei canali e gruppi dove il bot e' stato messo.

## Come si usa, in tre passi

1. Crea il canale (o il gruppo) su Telegram.
2. Aggiungici il bot **come amministratore**. Per un canale serve che sia
   amministratore, altrimenti non puo' scrivere.
3. Scrivi un messaggio qualsiasi nel canale -- anche solo "ciao" -- e poi
   lancia questo script.

Il messaggio serve: Telegram non da' l'elenco dei canali di un bot. Si puo'
solo guardare cosa gli e' arrivato, e finche' nessuno scrive li' dentro non
gli e' arrivato niente.

## Se non trova niente

Due cause, in ordine di frequenza:

- **il bot non e' amministratore del canale.** Aggiungerlo come membro non
  basta: senza i permessi di amministratore Telegram non gli inoltra niente;
- **il messaggio e' stato scritto prima di aggiungere il bot.** Telegram
  consegna solo cio' che arriva dopo. Scrivine un altro adesso.

C'e' anche un terzo caso piu' insidioso: se il bot ha un **webhook** attivo,
`getUpdates` non restituisce nulla per progetto -- i due modi si escludono a
vicenda. Lo script se ne accorge e lo dice.

Non stampa mai il token, e non scrive niente nel `.env`: il valore te lo
mostra e lo copi tu.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from core.config import impostazioni


def main() -> int:
    cfg = impostazioni()
    token = cfg.TELEGRAM_TOKEN.strip()
    if not token:
        print("manca TELEGRAM_TOKEN nel .env: senza non si puo' chiedere niente")
        return 2

    base = f"https://api.telegram.org/bot{token}"
    try:
        chi = httpx.get(f"{base}/getMe", timeout=cfg.TIMEOUT_HTTP).json()
    except httpx.HTTPError as errore:
        print(f"Telegram non risponde: {errore}")
        return 1
    if not chi.get("ok"):
        print(f"il token non va bene: {chi.get('description', chi)}")
        return 1
    print(f"bot: @{chi['result'].get('username')} ({chi['result'].get('first_name')})")

    # Il webhook esclude getUpdates: se c'e', qui non arriverebbe mai niente e
    # si cercherebbe a lungo una causa che non c'e'.
    try:
        gancio = httpx.get(f"{base}/getWebhookInfo",
                           timeout=cfg.TIMEOUT_HTTP).json()
        indirizzo = (gancio.get("result") or {}).get("url") or ""
        if indirizzo:
            print()
            print(f"ATTENZIONE: questo bot ha un webhook attivo ({indirizzo}).")
            print("Finche' c'e', Telegram manda li' gli aggiornamenti e questo")
            print("elenco resta vuoto. I due modi si escludono a vicenda.")
    except httpx.HTTPError:
        pass

    try:
        risposta = httpx.get(f"{base}/getUpdates",
                             params={"limit": 100, "timeout": 0},
                             timeout=cfg.TIMEOUT_HTTP).json()
    except httpx.HTTPError as errore:
        print(f"Telegram non risponde: {errore}")
        return 1
    if not risposta.get("ok"):
        print(f"Telegram ha rifiutato: {risposta.get('description', risposta)}")
        return 1

    viste: dict[str, tuple[str, str]] = {}
    for aggiornamento in risposta.get("result", []):
        for chiave in ("message", "channel_post", "edited_message",
                       "edited_channel_post", "my_chat_member"):
            pezzo = aggiornamento.get(chiave)
            if not pezzo:
                continue
            chat = pezzo.get("chat") or {}
            ident = chat.get("id")
            if ident is None:
                continue
            nome = chat.get("title") or chat.get("username") or chat.get(
                "first_name") or "(senza nome)"
            viste[str(ident)] = (str(nome), str(chat.get("type", "?")))

    print()
    if not viste:
        print("nessuna chat trovata. Le due cause piu' frequenti:")
        print("  1. il bot non e' AMMINISTRATORE del canale (membro non basta)")
        print("  2. il messaggio e' stato scritto prima di aggiungere il bot:")
        print("     scrivine un altro adesso e rilancia")
        return 1

    print("chat in cui il bot vede qualcosa:")
    for ident, (nome, tipo) in sorted(viste.items()):
        print(f"  {ident:>16}   {tipo:<10} {nome}")
    print()
    print("Metti quello del canale dell'equipe nel .env, su una riga sua:")
    print()
    print("    TELEGRAM_CHAT_EQUIPE=<il numero qui sopra>")
    print()
    print("Un canale ha l'id NEGATIVO e comincia per -100. Poi:")
    print("    python equipe.py --quante 10 --telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
