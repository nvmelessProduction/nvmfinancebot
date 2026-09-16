"""Inserisce la chiave API nel `.env` senza che compaia da nessuna parte.

## Perche' non basta aprire il blocco note

Aprire il file va benissimo. Questo script serve a chi la chiave la deve
incollare da un telefono o da un altro computer, e vuole essere sicuro che
non finisca in posti dove resta:

- **non si vede a schermo** mentre la digiti (`getpass`);
- **non entra nella cronologia dei comandi**, come farebbe un `echo CHIAVE > file`;
- **non passa da una chat**, che e' il modo in cui il token Telegram di questo
  stesso progetto e' finito pubblico su GitHub.

Lo script non stampa mai la chiave. Dice solo se e' stata scritta, e le prime
cinque lettere per farti riconoscere che sia quella giusta.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

PERCORSO = Path(".env")
CHIAVE = "ANTHROPIC_API_KEY"


def main() -> int:
    if not PERCORSO.exists():
        print("Manca il file .env. Crealo prima con:  python crea_env.py")
        return 1

    print("Incolla la chiave API e premi Invio.")
    print("Non la vedrai comparire: e' voluto.\n")
    try:
        valore = getpass.getpass("chiave: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nannullato, niente e' stato scritto")
        return 1

    if not valore:
        print("niente incollato, il file non e' stato toccato")
        return 1
    if not valore.startswith("sk-ant-"):
        # Non e' un controllo di validita': e' per accorgersi subito di aver
        # incollato un'altra cosa — succede, copiando da un telefono.
        print(f"Questa non sembra una chiave Anthropic (inizia con "
              f"'{valore[:7]}...', dovrebbe iniziare con 'sk-ant-').")
        print("Il file non e' stato toccato.")
        return 1

    righe = PERCORSO.read_text(encoding="utf-8").splitlines()
    trovata = False
    for i, riga in enumerate(righe):
        if riga.strip().startswith(f"{CHIAVE}="):
            righe[i] = f"{CHIAVE}={valore}"
            trovata = True
            break
    if not trovata:
        righe.append(f"{CHIAVE}={valore}")

    PERCORSO.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"\nscritta in {PERCORSO} (inizia con {valore[:9]}...)")

    # Conferma leggendola come la leggera' il bot, non come l'abbiamo scritta.
    try:
        from core.config import impostazioni

        impostazioni.cache_clear()
        letta = impostazioni().ANTHROPIC_API_KEY
    except Exception as errore:
        print(f"scritta, ma non ho potuto rileggerla: {errore!r}")
        return 0

    if letta == valore:
        print("il bot la legge correttamente.")
        print("\nProssimo passo:  python importa_dukascopy.py")
        return 0
    print("ATTENZIONE: scritta nel file ma il bot ne legge un'altra.")
    print("Controlla che non ci sia una seconda riga ANTHROPIC_API_KEY.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
