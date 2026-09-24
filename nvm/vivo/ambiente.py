"""Le impostazioni del bot dal vivo, dal file `.env` nella cartella del progetto.

Il `.env` non entra mai nel repository (`.gitignore`). Si usano gli stessi
nomi del vecchio bot, cosi' il suo `.env` si copia com'e': cambia solo il
token di Telegram, che va rigenerato. Il token non si stampa mai.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Impostazioni:
    token: str = field(default="", repr=False)
    chat_operativo: tuple[str, ...] = ()
    chat_equipe: tuple[str, ...] = ()
    # Alcuni broker chiamano i simboli con un suffisso ("EURUSD.a", "EURUSD+").
    suffisso: str = ""

    @property
    def telegram(self) -> bool:
        return bool(self.token and (self.chat_operativo or self.chat_equipe))


def leggi_env(percorso: Path) -> dict[str, str]:
    """Le righe NOME=valore di un file .env; commenti e righe vuote si saltano."""
    valori: dict[str, str] = {}
    if not percorso.exists():
        return valori
    for riga in percorso.read_text(encoding="utf-8-sig").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        nome, valore = riga.split("=", 1)
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "\"'":
            valore = valore[1:-1]
        valori[nome.strip()] = valore
    return valori


def _chat(testo: str) -> tuple[str, ...]:
    return tuple(x for x in testo.replace(";", ",").replace(" ", ",").split(",") if x)


def impostazioni(radice: Path, ambiente: Mapping[str, str] = os.environ) -> Impostazioni:
    """Dal `.env` di `radice`; le variabili d'ambiente, se ci sono, vincono."""
    v = {**leggi_env(radice / ".env"), **{k: x for k, x in ambiente.items() if k.startswith(("TELEGRAM_", "MT5_"))}}
    return Impostazioni(
        token=v.get("TELEGRAM_TOKEN", ""),
        chat_operativo=_chat(v.get("TELEGRAM_CHAT_ID", "")),
        chat_equipe=_chat(v.get("TELEGRAM_CHAT_EQUIPE", "")),
        suffisso=v.get("MT5_SUFFISSO_SIMBOLI", ""),
    )
