"""Configurazione dell'impianto, letta da variabili d'ambiente e dal file .env.

Qui non c'e' nessuna logica di trading: solo i parametri di collegamento
(broker, Telegram, webhook), la modalita' operativa e le salvaguardie.

Le salvaguardie NON decidono mai di operare: possono solo rifiutare. E'
la differenza fra un interruttore di sicurezza e una strategia.
"""

import os
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
    # Quante volte ritentare un messaggio prima di rinunciare. Telegram cade
    # di rado ma cade, e una notifica persa in modalita' semi e' un'occasione persa.
    TELEGRAM_TENTATIVI: int = 3

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
    # Scarto massimo di prezzo tollerato sull'esecuzione, in punti.
    MT5_DEVIAZIONE: int = 20

    # =======================================================================
    # SALVAGUARDIE
    # Nessuna di queste apre posizioni: possono solo impedirne l'apertura.
    # Mettere 0 disattiva il controllo.
    # =======================================================================

    # Interruttore di emergenza: se esiste un file con questo nome nella
    # cartella del progetto, il bot non invia piu' ordini. Funziona anche a
    # server avviato, basta creare il file. E' il freno a mano.
    FILE_BLOCCO: str = "STOP"

    # Un alert consegnato in ritardo (tunnel caduto, rete lenta, PC in affanno)
    # descrive un prezzo che non esiste piu'. Oltre questo ritardo l'alert
    # viene archiviato ma NON eseguito. 0 disattiva il controllo.
    MAX_RITARDO_ALERT_SEC: int = 180

    # Tetto anti-errore sul volume del singolo ordine. Non calcola la size:
    # rifiuta e basta, se qualcuno chiede un volume fuori scala. 0 disattiva.
    VOLUME_MASSIMO: float = 1.0

    # Quante posizioni il bot puo' tenere aperte contemporaneamente.
    # E' un limite di capienza dell'impianto, non una regola di portafoglio.
    # 0 disattiva.
    MAX_POSIZIONI_APERTE: int = 5

    # --- Sorvegliante di stop e target --------------------------------------
    # Sul broker non ci sono ordini pendenti: i livelli stanno in archivio e
    # li sorveglia questo ciclo. Se lo spegni, stop e target non esistono.
    SENTINELLA_ATTIVA: bool = True
    SENTINELLA_INTERVALLO_SEC: float = 5.0

    # --- Fornitore dei dati di analisi ---------------------------------------
    # "mercato":     il bot va a prendersi da solo le candele dei future
    #                (DEFAULT). Niente alert da creare, niente tunnel, niente
    #                segreto: si preme avvia e basta.
    # "nessuno":     il motore non riceve dati e si astiene dichiarandolo.
    # "tradingview": i prezzi arrivano dagli alert sul grafico FUTURE e si
    #                accumulano in archivio; MT5 serve solo al conto e
    #                all'esecuzione sul CFD. E' l'architettura di DEF-32,
    #                DEF-33 e DEF-34.
    FORNITORE_DATI: Literal["nessuno", "tradingview", "mercato"] = "mercato"
    # Ogni quanto il bot va a cercare candele nuove, in secondi. Non serve
    # scendere: una serie viene chiesta solo quando puo' essersi chiusa
    # qualcosa, quindi girare spesso non moltiplica le richieste.
    MERCATO_INTERVALLO_SEC: float = 60.0
    # Suffisso che il broker aggiunge ai simboli (es. ".a", ".pro").
    # Si scopre con: python prova_esecuzione.py
    MT5_SUFFISSO_SIMBOLI: str = ""

    # --- Archivio ------------------------------------------------------------
    DB_PATH: str = "bot.db"

    # --- Diario di bordo -----------------------------------------------------
    LOG_FILE: str = "bot.log"
    LOG_LIVELLO: str = "INFO"
    # Dimensione massima del file di log prima della rotazione, e quante
    # copie storiche tenere.
    LOG_MAX_BYTE: int = 5_000_000
    LOG_COPIE: int = 5

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

    @property
    def bloccato(self) -> bool:
        """True se il freno a mano e' tirato (esiste il file di blocco).

        Viene riletto a ogni chiamata di proposito: deve poter cambiare
        mentre il server e' in funzione, senza riavviarlo.
        """
        nome = self.FILE_BLOCCO.strip()
        return bool(nome) and os.path.exists(nome)


@lru_cache(maxsize=1)
def impostazioni() -> Impostazioni:
    """Restituisce l'istanza unica delle impostazioni (letta una sola volta)."""
    return Impostazioni()
