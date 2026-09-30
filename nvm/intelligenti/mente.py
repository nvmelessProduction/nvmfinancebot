"""La mente di un agente: un modello di linguaggio (Claude) che ragiona e risponde in forma fissa.

Ogni agente della squadra pensa con la stessa mente ma con il suo mestiere, i suoi occhi e la sua
memoria (`squadra.py`). La bibbia di Romeo (`bibbia.md`) sta davanti a tutto e si tiene in cache:
la pagano una volta, poi costa un decimo. La risposta e' sempre un JSON con la forma chiesta
(uscite strutturate), cosi' il bot non deve indovinare cosa ha detto.

La chiave sta solo nel `.env` della VPS (`ANTHROPIC_API_KEY=...`): mai nel codice, mai stampata.
Senza chiave o senza il pacchetto `anthropic`, `Mente.disponibile()` e' falso e il bot lavora come
prima, con i cervelli numerici.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BIBBIA = Path(__file__).with_name("bibbia.md")
# Il modello di ogni agente. Si cambia da `nvm/vivo/scelte.json` ("modello": ...).
MODELLO = "claude-opus-5-5"
# Se il modello rifiuta una richiesta per i suoi filtri di sicurezza, il server la rifa' con un altro.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class Consumo:
    """Quanto e' costata la squadra: token letti, scritti in cache, letti dalla cache, generati."""

    chiamate: int = 0
    ingresso: int = 0
    cache_scritta: int = 0
    cache_letta: int = 0
    uscita: int = 0
    errori: int = 0

    def aggiungi(self, u) -> None:
        self.chiamate += 1
        self.ingresso += getattr(u, "input_tokens", 0) or 0
        self.cache_scritta += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.cache_letta += getattr(u, "cache_read_input_tokens", 0) or 0
        self.uscita += getattr(u, "output_tokens", 0) or 0

    def dollari(self, ingresso: float = 4.0, uscita: float = 20.0) -> float:
        """Il costo in dollari ai prezzi di Claude Opus 5.5: $4 per milione di token letti, $20 generati;
        la cache di un'ora costa il doppio da scrivere e $0,20 per milione da rileggere."""
        m = 1e6
        return (self.ingresso * ingresso + self.cache_scritta * ingresso * 2 + self.cache_letta * 0.20
                + self.uscita * uscita) / m

    def come_dati(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Mente:
    """Il collegamento con Claude, condiviso da tutta la squadra."""

    chiave: str = field(default="", repr=False)
    modello: str = MODELLO
    consumo: Consumo = field(default_factory=Consumo)
    _client: object = field(default=None, repr=False)

    @classmethod
    def dal_env(cls, radice: Path, modello: Optional[str] = None) -> "Mente":
        from nvm.vivo.ambiente import leggi_env
        chiave = os.environ.get("ANTHROPIC_API_KEY") or leggi_env(radice / ".env").get("ANTHROPIC_API_KEY", "")
        return cls(chiave=chiave, modello=modello or MODELLO)

    def disponibile(self) -> bool:
        if not self.chiave:
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _cliente(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.chiave, max_retries=3, timeout=240.0)
        return self._client

    def pensa(self, blocchi: list[dict], schema: dict, sforzo: str = "low", massimo: int = 16000) -> Optional[dict]:
        """Un pensiero: `blocchi` sono i pezzi del messaggio (testo, alcuni in cache), `schema` la
        forma della risposta. Restituisce il JSON della risposta, o None se non e' andata."""
        import anthropic
        sistema = [{"type": "text", "text": BIBBIA.read_text(encoding="utf-8"),
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        try:
            risposta = self._cliente().beta.messages.create(
                model=self.modello,
                max_tokens=massimo,
                system=sistema,
                messages=[{"role": "user", "content": blocchi}],
                output_config={"effort": sforzo, "format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.BadRequestError, anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.NotFoundError):
            self.consumo.errori += 1
            raise
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError):
            self.consumo.errori += 1
            return None
        self.consumo.aggiungi(risposta.usage)
        if risposta.stop_reason in ("refusal", "max_tokens"):
            self.consumo.errori += 1
            return None
        testo = next((b.text for b in risposta.content if b.type == "text"), "")
        try:
            return json.loads(testo)
        except json.JSONDecodeError:
            self.consumo.errori += 1
            return None


def testo(t: str, cache: bool = False) -> dict:
    """Un pezzo di messaggio; con `cache` resta in memoria un'ora (il dossier, uguale per tutti)."""
    b = {"type": "text", "text": t}
    if cache:
        b["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    return b


@dataclass
class MenteFinta:
    """Una mente per le prove: risponde con quello che le si dice, senza rete."""

    risposte: dict = field(default_factory=dict)
    chiamate: list = field(default_factory=list)
    # Tutti i pezzi di ogni messaggio (il dossier compreso), per le prove.
    messaggi: list = field(default_factory=list)
    consumo: Consumo = field(default_factory=Consumo)
    modello: str = "finta"

    def disponibile(self) -> bool:
        return True

    def pensa(self, blocchi: list[dict], schema: dict, sforzo: str = "low", massimo: int = 16000) -> Optional[dict]:
        ultimo = blocchi[-1]["text"]
        self.chiamate.append(ultimo)
        self.messaggi.append([b["text"] for b in blocchi])
        self.consumo.chiamate += 1
        for chiave, risposta in self.risposte.items():
            if chiave in ultimo:
                return risposta(ultimo) if callable(risposta) else risposta
        return None


def adesso() -> int:
    return int(time.time())
