"""Modelli dei dati che attraversano l'impianto.

I nomi dei campi sono in italiano, ma ognuno porta l'alias inglese usato sul
filo (TradingView manda `close`, non `chiusura`): grazie a `populate_by_name`
entrambe le forme sono accettate in ingresso.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Azioni che una decisione puo' esprimere. NONE = non fare nulla.
Azione = Literal["NONE", "BUY", "SELL", "CLOSE"]

# Esiti registrati in archivio per ogni decisione.
Esito = Literal["ignorato", "simulato", "in_attesa_conferma", "eseguito", "errore"]


class AlertIn(BaseModel):
    """Payload JSON inviato da TradingView all'endpoint /webhook."""

    model_config = ConfigDict(populate_by_name=True)

    # Parola segreta condivisa: e' l'unica cosa che separa il conto da
    # chiunque conosca l'URL del tunnel.
    segreto: str = Field(alias="secret")
    simbolo: str = Field(alias="symbol")
    # Timeframe cosi' come lo scrive TradingView: "5", "15", "60", "1D"...
    tf: str
    # Orario di chiusura candela in UTC. Tenuto come stringa grezza di
    # proposito: un formato inatteso non deve farci perdere l'alert.
    chiusura_candela_utc: str = Field(alias="candle_close_time_utc")
    apertura: float = Field(alias="open")
    massimo: float = Field(alias="high")
    minimo: float = Field(alias="low")
    chiusura: float = Field(alias="close")
    # Campi facoltativi.
    rsi: Optional[float] = None
    nota: Optional[str] = Field(default=None, alias="note")


class Decision(BaseModel):
    """Cosa l'impianto ha deciso di fare a fronte di un alert.

    In questa fase la strategia restituisce sempre azione "NONE": i campi
    volume/sl/tp esistono solo perche' l'esecutore sappia gia' leggerli.
    """

    model_config = ConfigDict(populate_by_name=True)

    azione: Azione = Field(default="NONE", alias="action")
    # Spiegazione leggibile del perche' di questa azione: finisce in archivio
    # e nel messaggio Telegram.
    motivo: str = ""
    volume: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None


class OrderResult(BaseModel):
    """Esito di un'operazione sul broker (invio o chiusura di un ordine)."""

    ok: bool
    messaggio: str
    ticket: Optional[int] = None
    prezzo: Optional[float] = None
    codice_errore: Optional[int] = None
