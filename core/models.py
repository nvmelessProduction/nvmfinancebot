"""Modelli dei dati che attraversano l'impianto.

I nomi dei campi sono in italiano, ma ognuno porta l'alias inglese usato sul
filo (TradingView manda `close`, non `chiusura`): grazie a `populate_by_name`
entrambe le forme sono accettate in ingresso.
"""

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Azioni che una decisione puo' esprimere. NONE = non fare nulla.
Azione = Literal["NONE", "BUY", "SELL", "CLOSE"]

# Esiti registrati in archivio per ogni decisione.
#   ignorato            la strategia non ha chiesto nulla (azione NONE)
#   simulato            dry_run: nessun ordine e' partito
#   in_attesa_conferma  semi: notificato, aspetta il via libera umano
#   eseguito            l'ordine e' andato a mercato
#   errore              si doveva operare e non si e' riusciti
#   bloccato            una salvaguardia ha impedito l'operazione
#   duplicato           alert gia' ricevuto, non rivalutato
Esito = Literal[
    "ignorato",
    "simulato",
    "in_attesa_conferma",
    "eseguito",
    "errore",
    "bloccato",
    "duplicato",
]


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

    def orario_candela(self) -> Optional[datetime]:
        """Interpreta `chiusura_candela_utc` in modo tollerante.

        TradingView puo' mandare ISO 8601 con la Z, con un fuso esplicito, o
        senza fuso. Se il formato e' irriconoscibile restituiamo None: chi
        chiama deve trattare "non lo so" come "non blocco nulla", perche' un
        formato inatteso non e' un buon motivo per perdere un segnale.
        """
        testo = self.chiusura_candela_utc.strip()
        if not testo:
            return None
        try:
            momento = datetime.fromisoformat(testo.replace("Z", "+00:00"))
        except ValueError:
            return None
        # Senza fuso esplicito assumiamo UTC: e' quello che chiede il campo.
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=timezone.utc)
        return momento.astimezone(timezone.utc)

    def ritardo_secondi(self, adesso: Optional[datetime] = None) -> Optional[float]:
        """Quanti secondi sono passati dalla chiusura candela dichiarata.

        None se l'orario non e' interpretabile. Puo' essere negativo se
        l'orologio del PC e' indietro rispetto a quello di TradingView.
        """
        momento = self.orario_candela()
        if momento is None:
            return None
        riferimento = adesso or datetime.now(timezone.utc)
        return (riferimento - momento).total_seconds()

    def impronta(self) -> str:
        """Identita' dell'alert, per riconoscere le consegne doppie.

        Stesso simbolo, stesso timeframe, stessa candela = stesso alert, anche
        se arriva tre volte perche' il tunnel ha ritentato.
        """
        semi = f"{self.simbolo}|{self.tf}|{self.chiusura_candela_utc}"
        return hashlib.sha256(semi.encode("utf-8")).hexdigest()[:32]


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
