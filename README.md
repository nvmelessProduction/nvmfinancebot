# nvmfinancebot — impianto

Infrastruttura di un bot di trading: riceve gli alert di TradingView, li
archivia, li passa a una funzione di strategia, e sa eseguire ordini su
MetaTrader 5 e notificare su Telegram.

> **La strategia non c'e' ancora, ed e' voluto.**
> `core/strategy.py` contiene una funzione `valuta(alert) -> Decision` che
> restituisce sempre `action="NONE"`. Finche' resta cosi', l'impianto gira a
> vuoto: registra tutto e non apre niente. E' esattamente il comportamento
> atteso in questa fase.

---

## Cosa fa, in una riga per pezzo

| File | Ruolo |
|---|---|
| `main.py` | Server FastAPI: `POST /webhook`, `GET /salute` |
| `prova_impianto.py` | Collauda i tre collegamenti (MT5, Telegram, webhook) uno per uno |
| `core/config.py` | Configurazione letta dal `.env` |
| `core/models.py` | Modelli dei dati: `AlertIn`, `Decision`, `OrderResult` |
| `core/storage.py` | Archivio SQLite: tabelle `alert`, `decisione`, `posizione` |
| `core/notifier.py` | Messaggi Telegram via HTTP |
| `core/broker.py` | Adattatore MetaTrader 5: tutto cio' che tocca il broker sta qui |
| `core/strategy.py` | **Stub.** Restituisce sempre `NONE` |

Il percorso di un alert e' sempre lo stesso:

```
TradingView -> POST /webhook -> controllo del segreto -> salvataggio su SQLite
            -> strategy.valuta() -> azione secondo la modalita' -> archivio + Telegram
```

---

## Quanto costa

| Voce | Costo | Note |
|---|---|---|
| TradingView — piano a pagamento | **a pagamento** | **I webhook non sono inclusi nel piano gratuito.** Servono almeno i piani a pagamento (Essential o superiore). E' l'unica spesa dell'impianto, e ce l'hai gia' |
| MetaTrader 5 | gratuito | Il terminale e' gratis |
| Conto FP Markets | gratuito da aprire | Si paga solo lo spread/commissione sulle operazioni |
| Python + librerie | gratuito | Tutte open source |
| SQLite | gratuito | E' un file sul disco, nessun server da installare |
| Telegram Bot API | gratuito | Nessun limite rilevante per questo volume |
| Cloudflare Tunnel | gratuito | Il tunnel "quick" non richiede nemmeno un account |
| Hosting | **zero** | Il bot gira sul tuo PC. Vedi l'avvertenza qui sotto |

### Avvertenza: il PC deve restare acceso

Non ci sono server esterni e, per scelta di impianto, **non ci sono ordini
pendenti sul broker**: stop loss e take profit non vengono inviati a MT5, ma
restano in archivio (tabella `posizione`) perche' saranno sorvegliati dal
server.

Conseguenza pratica: se il PC si spegne, va in sospensione o perde la rete
mentre una posizione e' aperta, **nessuno sta guardando quello stop**. La
posizione resta aperta sul broker senza protezione.

Prima di passare in modalita' `auto`, quindi:

- disattiva sospensione e ibernazione (Impostazioni → Alimentazione)
- disattiva il riavvio automatico per gli aggiornamenti di Windows
- considera un gruppo di continuita', o l'idea di mettere comunque uno stop
  di emergenza largo direttamente su MT5

---

## Installazione su Windows

1. **Python 3.11 o superiore** da [python.org](https://www.python.org/downloads/windows/).
   In fase di installazione spunta **"Add python.exe to PATH"**.

2. **MetaTrader 5 di FP Markets**: installalo, accedi al conto e lascia il
   terminale aperto. Nella barra in alto attiva il pulsante **"Algo Trading"**:
   senza quello MT5 rifiuta gli ordini inviati da programma.

3. **Prepara il progetto** (Prompt dei comandi, dentro la cartella del progetto):

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Configura**:

   ```bat
   copy .env.example .env
   notepad .env
   ```

   Il minimo indispensabile e' `WEBHOOK_SECRET` (inventane uno lungo e
   casuale). Telegram e MT5 puoi aggiungerli dopo.

5. **Avvia il server**:

   ```bat
   python main.py
   ```

   Resta in ascolto su `http://127.0.0.1:8000`.

6. **Collauda**, in una *seconda* finestra del prompt:

   ```bat
   .venv\Scripts\activate
   python prova_impianto.py
   ```

   Stampa OK o ERRORE per ciascuno dei tre collegamenti, con il dettaglio.
   Esce con codice 0 solo se passano tutti e tre.

> Il file `.env` contiene la password del conto e il segreto del webhook:
> **non va mai messo su git.** Nel progetto non c'e' un `.gitignore` (per
> scelta, l'elenco dei file e' chiuso): se metti la cartella sotto controllo
> di versione, creane uno con dentro almeno `.env`, `bot.db` e `__pycache__/`.

---

## Esporre il server con Cloudflare Tunnel (gratuito)

TradingView deve poter raggiungere il tuo PC da internet. Cloudflare Tunnel lo
fa gratis senza aprire porte sul router.

1. Scarica `cloudflared` per Windows dalla
   [pagina dei rilasci](https://github.com/cloudflare/cloudflared/releases)
   (file `cloudflared-windows-amd64.exe`, rinominalo `cloudflared.exe`).

2. Con il server gia' avviato, in una terza finestra:

   ```bat
   cloudflared.exe tunnel --url http://localhost:8000
   ```

3. Cloudflared stampa un indirizzo del tipo:

   ```
   https://qualcosa-di-casuale.trycloudflare.com
   ```

   L'URL da mettere in TradingView e' quello **con `/webhook` in fondo**:

   ```
   https://qualcosa-di-casuale.trycloudflare.com/webhook
   ```

**Attenzione:** il tunnel "quick" e' gratuito e non richiede account, ma
l'indirizzo **cambia a ogni riavvio** di cloudflared, e ogni volta va
aggiornato dentro l'alert di TradingView. Se hai gia' un dominio, con un
account Cloudflare gratuito puoi creare un *named tunnel* e ottenere un
indirizzo stabile.

Verifica che il tunnel funzioni aprendo nel browser
`https://tuo-indirizzo.trycloudflare.com/salute`.

---

## L'alert su TradingView

Crea l'alert, apri la scheda **Notifiche**, spunta **Webhook URL** e incolla
l'indirizzo del tunnel (`.../webhook`).

Nella scheda **Impostazioni**, nel campo **Messaggio**, incolla esattamente
questo JSON:

```json
{
  "secret": "IL_TUO_WEBHOOK_SECRET",
  "symbol": "{{ticker}}",
  "tf": "{{interval}}",
  "candle_close_time_utc": "{{timenow}}",
  "open": {{open}},
  "high": {{high}},
  "low": {{low}},
  "close": {{close}},
  "note": "{{exchange}}"
}
```

Note importanti:

- `"secret"` va sostituito con lo stesso identico valore che hai messo in
  `WEBHOOK_SECRET` nel `.env`. E' l'unica cosa che separa il tuo conto da
  chiunque conosca l'URL: se non coincide, il server risponde **401** e non
  scrive niente in archivio.
- I prezzi (`open`, `high`, `low`, `close`) **non vanno tra virgolette**: sono
  numeri. Gli altri campi si'.
- Il simbolo che arriva da `{{ticker}}` (es. `EURUSD`) puo' non coincidere con
  il nome del simbolo su FP Markets (es. `EURUSD.a` o simili). Quando la
  strategia esistera' potrebbe servire una tabella di conversione.
- Il campo `rsi` e' facoltativo e non e' nel modello sopra: si aggiunge solo se
  l'alert nasce da un indicatore che espone quel valore, con
  `"rsi": {{plot("RSI")}}` (il nome tra virgolette deve essere quello del plot
  nel Pine Script). Se non serve, lascialo fuori.
- `"note"` e' libero: mettici quello che ti aiuta a riconoscere l'alert.
- Imposta l'alert su **"Once Per Bar Close"**, altrimenti riceverai eventi a
  candela ancora aperta.

---

## Le tre modalita' (`MODE` nel `.env`)

| Modalita' | Cosa fa | Quando usarla |
|---|---|---|
| `dry_run` | Non tocca MT5. Salva l'alert e la decisione, stampa a console | **Default.** Per collaudare l'impianto e per tutta la fase in cui la strategia e' uno stub |
| `semi` | Notifica su Telegram e si ferma, in attesa di conferma manuale | Per i primi giorni con una strategia vera, quando vuoi vedere cosa *avrebbe* fatto |
| `auto` | Esegue davvero gli ordini sul broker | Solo quando ti fidi |

Il default e' `dry_run` di proposito: una configurazione dimenticata a meta'
non deve poter operare.

---

## Endpoint

**`POST /webhook`** — riceve l'alert. Risposte possibili:

| Codice | Significato |
|---|---|
| `200` | Alert accettato, archiviato e valutato (il corpo riporta azione ed esito) |
| `401` | Segreto sbagliato o mancante. **Nessuna traccia in archivio** |
| `422` | JSON malformato o campi mancanti |
| `500` | Archiviazione fallita |

**`GET /salute`** — stato dell'impianto: modalita' corrente, se MT5 e'
disponibile e connesso, equity del conto, posizioni aperte (sul broker e in
archivio), conteggi delle tabelle, se Telegram e il webhook sono configurati.

---

## Cosa c'e' in archivio

File SQLite (`bot.db` per default), tre tabelle:

- **`alert`** — ogni alert valido ricevuto, con il payload completo in JSON.
  Il campo `secret` non viene mai scritto.
- **`decisione`** — cosa e' stato deciso per ogni alert e com'e' andata
  (`ignorato`, `simulato`, `in_attesa_conferma`, `eseguito`, `errore`).
- **`posizione`** — le posizioni aperte dal bot, con i livelli di stop e
  target. E' qui che vivranno i livelli sorvegliati dal server, visto che sul
  broker non ci sono ordini pendenti.

Per guardarci dentro va bene qualunque browser SQLite, o da riga di comando:

```bat
python -c "import sqlite3; c=sqlite3.connect('bot.db'); c.row_factory=sqlite3.Row; [print(dict(r)) for r in c.execute('SELECT * FROM alert ORDER BY id DESC LIMIT 10')]"
```

---

## Cosa manca ancora

In ordine di importanza:

1. **La strategia.** `core/strategy.py` e' uno stub che restituisce sempre
   `NONE`. E' il punto in cui andra' scritta la logica, quando i documenti che
   la descrivono saranno pronti. Nessun'altra parte del progetto va toccata
   per aggiungerla.
2. **Il calcolo della size.** `Decision.volume` esiste ma nessuno lo riempie.
   Finche' resta `None`, in modalita' `auto` l'ordine non parte (ed e' giusto
   cosi').
3. **Il sorvegliante di stop e target.** Nessuno controlla ancora le posizioni
   aperte: la tabella `posizione` c'e', il ciclo che la legge e chiude quando
   il prezzo tocca i livelli no.
4. **La conferma manuale in modalita' `semi`.** Oggi la modalita' notifica e si
   ferma: manca il modo di dire "si, esegui" (per esempio un bottone nel
   messaggio Telegram, o un endpoint di conferma).
5. **La chiusura mirata (`CLOSE`).** L'adattatore sa chiudere per ticket, ma
   nessuno gli dice quale ticket: servira' quando la strategia esprimera'
   uscite.
6. **La conversione dei simboli** fra il nome TradingView e quello FP Markets.
7. **Riavvio automatico** del server e di cloudflared all'accensione del PC
   (Utilita' di pianificazione di Windows).
8. **Log su file.** Oggi si stampa a console e basta.
9. **Test automatici.** Il collaudo e' manuale, via `prova_impianto.py`.
