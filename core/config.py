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

    # --- Il trader discrezionale (Claude) ------------------------------------
    # Con GIUDIZIO_ATTIVO=true ogni setup gia' approvato dalle regole passa da
    # Claude, che puo' solo RIFIUTARLO. Non puo' autorizzare cio' che le regole
    # vietano: quello sarebbe un bug con una buona spiegazione.
    #
    # Serve ANTHROPIC_API_KEY nell'ambiente. Senza chiave il giudizio si
    # astiene e non parte nulla: fallisce chiuso, come PRIN-99 impone.
    GIUDIZIO_ATTIVO: bool = False

    # Con GIUDIZIO_SULLE_OBIEZIONI=true il giudizio viene interpellato anche
    # su un CRT che le regole hanno RIFIUTATO -- ma solo quando l'obiezione e'
    # UNA SOLA e non e' uno dei muri (limiti di perdita, esclusioni, dati
    # incoerenti, tetto posizioni, freno a mano, PRIN-13).
    #
    # E' la differenza fra un veto e un trader: un CRT fermato da tre regole
    # insieme non e' un caso limite, e' un setup che nessuno guarderebbe.
    # Misurato il 2026-09-21: su 1.250 valutazioni in sei ore, 1.071 non
    # avevano alcun CRT, 104 erano bocciature triple, e i casi da trader erano
    # 46 -- che deduplicati sul CRT diventano 14.
    GIUDIZIO_SULLE_OBIEZIONI: bool = False

    # Tetto di spesa al giorno per i giudizi, in euro. A zero il freno e'
    # spento. Si misura sul consumo dichiarato dall'API, non su una stima:
    # `giudica` usa thinking adattivo con effort alto, e i token di
    # ragionamento non si sanno prima.
    GIUDIZIO_EURO_AL_GIORNO: float = 0.0

    # Prezzi del modello, per milione di token. Stanno in configurazione e non
    # nel codice perche' cambiano, e un prezzo sbagliato scritto nel codice
    # produce un tetto che sembra rispettato e non lo e'. A zero il tetto
    # lavora sui soli conteggi e non puo' fermare nulla: vanno compilati.
    # Scrittura e lettura della cache sono due prezzi diversi -- su Opus 5,
    # 6,25 contro 0,50 al milione -- e vanno separati: la prima chiamata
    # scrive le istruzioni in cache, tutte le altre le rileggono.
    PREZZO_INGRESSO_PER_MILIONE: float = 0.0
    PREZZO_CACHE_SCRITTA_PER_MILIONE: float = 0.0
    PREZZO_CACHE_LETTA_PER_MILIONE: float = 0.0
    PREZZO_USCITA_PER_MILIONE: float = 0.0

    # La chiave per il giudizio. Deve stare QUI e non solo nell'ambiente:
    # pydantic-settings legge il `.env` dentro questo oggetto, ma NON lo
    # esporta in `os.environ`. La libreria `anthropic` guarda l'ambiente,
    # quindi una chiave messa solo nel `.env` non la vedrebbe mai — e il
    # giudizio fallirebbe in silenzio, astenendosi a ogni setup senza che
    # nulla nei log spieghi il perche'.
    ANTHROPIC_API_KEY: str = ""

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

    # Consenso esplicito a operare su un conto REALE. Finche' resta False, in
    # modalita' auto il bot rifiuta di inviare ordini se il conto collegato
    # non e' un demo. Non e' burocrazia: passare al reale e' una riga nel
    # .env, e la differenza fra demo e reale non si vede dal log degli ordini.
    CONSENTI_CONTO_REALE: bool = False

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
    FORNITORE_DATI: Literal["nessuno", "tradingview", "mercato", "dukascopy", "mt5"] = "dukascopy"
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
    def destinatari_telegram(self) -> tuple[str, ...]:
        """Le chat a cui mandare le notifiche.

        Piu' di una si separa con la virgola. Passare l'intera stringa a
        Telegram come se fosse un numero solo significa non ricevere niente,
        e accorgersene il giorno in cui la notifica serviva.
        """
        grezzo = self.TELEGRAM_CHAT_ID.replace(";", ",").replace(" ", ",")
        return tuple(pezzo for pezzo in (p.strip() for p in grezzo.split(",")) if pezzo)

    @property
    def telegram_configurato(self) -> bool:
        """True solo se abbiamo sia il token sia la chat di destinazione."""
        return bool(self.TELEGRAM_TOKEN.strip() and self.destinatari_telegram)

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
