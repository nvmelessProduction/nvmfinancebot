"""Configurazione dell'impianto, letta da variabili d'ambiente e dal file .env.

Qui non c'e' nessuna logica di trading: solo i parametri di collegamento
(broker, Telegram, webhook) e la modalita' operativa.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Le tre modalita' operative previste dall'impianto.
Modalita = Literal["dry_run", "semi", "auto"]


class Impostazioni(BaseSettings):
    """Tutti i parametri configurabili. Nomi delle variabili = nomi nel .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Modalita' operativa -------------------------------------------------
    # dry_run: non tocca MT5, registra e stampa soltanto (DEFAULT, il piu' sicuro)
    # semi:    notifica su Telegram e si ferma, in attesa di conferma manuale
    # auto:    esegue davvero sul broker
    MODE: Modalita = "dry_run"

    # --- Webhook TradingView -------------------------------------------------
    # Parola segreta condivisa con l'alert di TradingView. Se resta vuota
    # l'endpoint rifiuta tutto: meglio non ricevere nulla che accettare chiunque.
    WEBHOOK_SECRET: str = ""
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # --- Telegram ------------------------------------------------------------
    # Se uno dei due manca, il notificatore stampa a console invece di fallire.
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # --- MetaTrader 5 (FP Markets) ------------------------------------------
    # Se MT5_LOGIN e' 0 si assume che il terminale sia gia' loggato a mano.
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""
    # Percorso del terminale, utile su Windows se ne hai piu' di uno installato.
    # Esempio: C:\\Program Files\\MetaTrader 5\\terminal64.exe
    MT5_PATH: str = ""
    # Identificativo numerico che il bot mette sugli ordini che apre lui,
    # per distinguerli da quelli aperti a mano nello stesso conto.
    MT5_MAGIC: int = 20260901

    # --- Archivio ------------------------------------------------------------
    DB_PATH: str = "bot.db"

    # --- Rete ----------------------------------------------------------------
    TIMEOUT_HTTP: float = 10.0

    @property
    def telegram_configurato(self) -> bool:
        """True solo se abbiamo sia il token sia la chat di destinazione."""
        return bool(self.TELEGRAM_TOKEN.strip() and self.TELEGRAM_CHAT_ID.strip())

    @property
    def webhook_configurato(self) -> bool:
        """True se la parola segreta del webhook e' stata impostata."""
        return bool(self.WEBHOOK_SECRET.strip())


@lru_cache(maxsize=1)
def impostazioni() -> Impostazioni:
    """Restituisce l'istanza unica delle impostazioni (letta una sola volta)."""
    return Impostazioni()
