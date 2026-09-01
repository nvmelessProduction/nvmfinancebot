# nvmfinancebot — impianto

Infrastruttura di un bot di trading: riceve gli alert di TradingView, li
archivia, li passa a una funzione di strategia, sa eseguire ordini su
MetaTrader 5, sorveglia stop e target, e notifica su Telegram.

> **La strategia non c'è ancora, ed è voluto.**
> `core/strategy.py` contiene una funzione `valuta(alert) -> Decision` che
> restituisce sempre `action="NONE"`. Finché resta così, l'impianto gira a
> vuoto: registra tutto e non apre niente. È esattamente il comportamento
> atteso in questa fase.
>
> Tutto il resto — sicurezza, archivio, esecuzione, sorveglianza, salvaguardie
> — è vero e collaudato. Quando la strategia arriverà, non ci sarà altro da
> costruire attorno.

---

## I file

| File | Ruolo |
|---|---|
| `main.py` | Server FastAPI: `POST /webhook`, `GET /salute` |
| `prova_impianto.py` | Collaudo manuale dei tre collegamenti (MT5, Telegram, webhook) |
| `test_impianto.py` | Collaudo automatico: 40 prove, gira anche senza MT5 |
| `core/config.py` | Configurazione dal `.env` |
| `core/models.py` | `AlertIn`, `Decision`, `OrderResult` |
| `core/storage.py` | Archivio SQLite: `alert`, `decisione`, `posizione` |
| `core/notifier.py` | Messaggi Telegram via HTTP |
| `core/broker.py` | Adattatore MetaTrader 5: tutto ciò che tocca il broker sta qui |
| `core/sentinella.py` | Sorveglia stop e target delle posizioni aperte |
| `core/log.py` | Diario di bordo su console e file, con rotazione |
| `core/strategy.py` | **Stub.** Restituisce sempre `NONE` |

Il percorso di un alert:

```
TradingView
    │
    ▼
POST /webhook ──► segreto sbagliato? ──► 401, nessuna traccia
    │
    ▼
archivio SQLite  (prima di tutto il resto: se il resto esplode, il dato resta)
    │
    ├──► già visto? ──► "duplicato", non si rivaluta
    ▼
strategy.valuta()  ──► oggi sempre NONE
    │
    ▼
salvaguardie  ──► una dice di no? ──► "bloccato"
    │
    ▼
modalità: dry_run / semi / auto
    │
    ▼
archivio della decisione  +  Telegram
```

E, in parallelo, sempre:

```
sentinella (ogni 5s) ──► prezzo vs stop/target in archivio ──► chiude a mercato
                    └──► riconcilia archivio e broker
```

---

## Quanto costa

| Voce | Costo | Note |
|---|---|---|
| TradingView — piano a pagamento | **a pagamento** | **I webhook non sono inclusi nel piano gratuito.** Servono almeno i piani a pagamento (Essential o superiore). È l'unica spesa dell'impianto, e ce l'hai già |
| MetaTrader 5 | gratuito | Il terminale è gratis |
| Conto FP Markets | gratuito da aprire | Si paga solo lo spread/commissione sulle operazioni |
| Python + librerie | gratuito | Tutte open source |
| SQLite | gratuito | È un file sul disco, nessun server da installare |
| Telegram Bot API | gratuito | Nessun limite rilevante per questo volume |
| Cloudflare Tunnel | gratuito | Il tunnel "quick" non richiede nemmeno un account |
| Hosting | **zero** | Il bot gira sul tuo PC. Vedi qui sotto |

### Il PC deve restare acceso. Sul serio.

Per scelta di impianto **non ci sono ordini pendenti sul broker**: stop loss e
take profit non vengono inviati a MT5, ma restano in archivio e li sorveglia
`core/sentinella.py`, che gira solo finché il server è acceso.

Conseguenza: se il PC si spegne, va in sospensione o perde la rete mentre una
posizione è aperta, **nessuno sta guardando quello stop**. La posizione resta
aperta sul broker, senza protezione, fino a quando non riaccendi.

Prima di passare in modalità `auto`:

- disattiva sospensione e ibernazione (Impostazioni → Sistema → Alimentazione)
- disattiva il riavvio automatico per gli aggiornamenti di Windows
- valuta un gruppo di continuità
- valuta comunque uno stop di emergenza largo messo a mano su MT5, come rete
  di sicurezza indipendente dal bot

L'endpoint `/salute` espone `posizioni_scoperte`: se è `true`, ci sono
posizioni aperte e nessuno le sta sorvegliando. È il campanello che va
guardato per primo.

---

## Installazione su Windows

1. **Python 3.11 o superiore** da [python.org](https://www.python.org/downloads/windows/).
   In fase di installazione spunta **"Add python.exe to PATH"**.

2. **MetaTrader 5 di FP Markets**: installalo, accedi al conto e lascia il
   terminale aperto. Nella barra in alto attiva il pulsante **"Algo Trading"**:
   senza quello MT5 rifiuta gli ordini inviati da programma. Il collaudo te lo
   dice esplicitamente se è spento.

3. **Prepara il progetto** (Prompt dei comandi, nella cartella del progetto):

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

   Il minimo indispensabile è `WEBHOOK_SECRET`. Per generarne uno serio:

   ```bat
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

5. **Prova che tutto si regga in piedi**, prima ancora di avviare il server:

   ```bat
   python -m unittest test_impianto
   ```

   Sono 40 prove e girano in mezzo secondo, senza MT5 e senza toccare il conto.
   Se qualcuna fallisce, non andare avanti.

6. **Avvia il server**:

   ```bat
   python main.py
   ```

7. **Collauda i collegamenti**, in una *seconda* finestra:

   ```bat
   .venv\Scripts\activate
   python prova_impianto.py
   ```

   Stampa il quadro operativo e poi OK o ERRORE per ciascuno dei tre
   collegamenti, con il dettaglio. Esce con codice 0 solo se passano tutti.

---

## Esporre il server con Cloudflare Tunnel (gratuito)

TradingView deve poter raggiungere il tuo PC da internet. Cloudflare Tunnel lo
fa gratis senza aprire porte sul router.

1. Scarica `cloudflared` per Windows dalla
   [pagina dei rilasci](https://github.com/cloudflare/cloudflared/releases)
   (file `cloudflared-windows-amd64.exe`, rinominalo `cloudflared.exe`).

2. Con il server già avviato, in una terza finestra:

   ```bat
   cloudflared.exe tunnel --url http://localhost:8000
   ```

3. Cloudflared stampa un indirizzo del tipo
   `https://qualcosa-di-casuale.trycloudflare.com`. L'URL da mettere in
   TradingView è quello **con `/webhook` in fondo**:

   ```
   https://qualcosa-di-casuale.trycloudflare.com/webhook
   ```

**Attenzione:** il tunnel "quick" è gratuito e non richiede account, ma
l'indirizzo **cambia a ogni riavvio** di cloudflared, e ogni volta va
aggiornato dentro l'alert di TradingView. Se hai un dominio, con un account
Cloudflare gratuito puoi creare un *named tunnel* e avere un indirizzo stabile.

Verifica aprendo nel browser `https://tuo-indirizzo.trycloudflare.com/salute`.

---

## L'alert su TradingView

Crea l'alert, apri la scheda **Notifiche**, spunta **Webhook URL** e incolla
l'indirizzo del tunnel (`.../webhook`).

Nella scheda **Impostazioni**, campo **Messaggio**, incolla esattamente questo:

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
  `WEBHOOK_SECRET` nel `.env`. È l'unica cosa che separa il tuo conto da
  chiunque conosca l'URL: se non coincide, il server risponde **401** e non
  scrive niente in archivio.
- I prezzi (`open`, `high`, `low`, `close`) **non vanno tra virgolette**: sono
  numeri. Gli altri campi sì.
- Imposta l'alert su **"Once Per Bar Close"**, altrimenti riceverai eventi a
  candela ancora aperta.
- `{{timenow}}` serve a due cose: capire se l'alert è arrivato in ritardo, e
  riconoscere le consegne doppie. **Non toglierlo.**
- Il campo `rsi` è facoltativo e non è nel modello sopra: si aggiunge solo se
  l'alert nasce da un indicatore che espone quel valore, con
  `"rsi": {{plot("RSI")}}` (il nome tra virgolette dev'essere quello del plot
  nel Pine Script).
- Il simbolo che arriva da `{{ticker}}` (es. `EURUSD`) può non coincidere con
  il nome su FP Markets (es. `EURUSD.a`). Quando la strategia esisterà potrebbe
  servire una tabella di conversione: vedi "cosa manca ancora".

### Consegne doppie

TradingView e il tunnel possono riconsegnare lo stesso alert più volte. Ogni
alert ha un'impronta calcolata su `simbolo + timeframe + orario candela`: la
seconda consegna viene riconosciuta, archiviata come `duplicato` e **non
rivalutata**. Senza questo, un ritentativo di rete diventerebbe un secondo
ordine sullo stesso segnale.

---

## Le tre modalità (`MODE` nel `.env`)

| Modalità | Cosa fa | Quando usarla |
|---|---|---|
| `dry_run` | Non tocca MT5. Salva alert e decisione, e dice anche *quale salvaguardia avrebbe bloccato l'ordine* | **Default.** Per collaudare e per tutta la fase in cui la strategia è uno stub |
| `semi` | Notifica su Telegram e si ferma, in attesa di conferma manuale | I primi giorni con una strategia vera, per vedere cosa *avrebbe* fatto |
| `auto` | Esegue davvero gli ordini | Solo quando ti fidi |

Il default è `dry_run` di proposito: una configurazione dimenticata a metà non
deve poter operare.

---

## Le salvaguardie

Sono controlli che possono solo **dire di no**. Nessuno di loro decide di
aprire qualcosa: quella è competenza della strategia, che ancora non esiste.
Si configurano nel `.env`, e `0` disattiva il controllo.

| Salvaguardia | Cosa impedisce | Default |
|---|---|---|
| **Freno a mano** (`FILE_BLOCCO`) | Se esiste un file con quel nome nella cartella, non parte nessun ordine | `STOP` |
| **Alert vecchio** (`MAX_RITARDO_ALERT_SEC`) | Un alert consegnato in ritardo descrive un prezzo che non c'è più | 180 s |
| **Tetto volume** (`VOLUME_MASSIMO`) | Un ordine di size fuori scala | 1.0 lotti |
| **Tetto posizioni** (`MAX_POSIZIONI_APERTE`) | Aprire più posizioni di quante se ne riescano a sorvegliare | 5 |
| **Sentinella viva** | Aprire una posizione con stop o target quando il sorvegliante non gira | sempre attiva |

### Il freno a mano

È volutamente un file, non un'impostazione: si tira e si molla a server acceso,
senza riavviare niente e senza aprire il `.env`.

```bat
type nul > STOP     :: tirato: da adesso non parte piu' nessun ordine
del STOP            :: mollato
```

Il freno blocca l'**apertura** di posizioni, **non** la sorveglianza di quelle
già aperte. Un interruttore d'emergenza che smettesse anche di proteggere il
già aperto sarebbe un interruttore pericoloso.

Un alert con formato di data irriconoscibile **non** viene bloccato dal
controllo sul ritardo: perdere un segnale buono per un formato inatteso sarebbe
il modo peggiore di fallire.

---

## La sentinella (stop e target)

Sul broker non ci sono ordini pendenti. I livelli stanno nella tabella
`posizione` e li guarda un ciclo in un thread suo, ogni `SENTINELLA_INTERVALLO_SEC`
secondi. Fa tre cose, e solo queste:

1. **Confronta** il prezzo corrente con i livelli già scritti in archivio, e
   chiude a mercato quando vengono toccati. Il confronto usa il prezzo a cui si
   **uscirebbe**: bid per le posizioni lunghe, ask per le corte. Se stop e
   target risultassero toccati nello stesso istante, vince lo stop — fra due
   letture possibili si sceglie la peggiore.
2. **Riconcilia** archivio e broker: se una posizione è stata chiusa a mano, per
   stop out o dal broker, l'archivio si allinea e arriva una notifica.
3. **Segnala le orfane**: se sul broker c'è una posizione aperta dal bot che
   l'archivio non conosce (successo se il bot è stato spento fra l'invio
   dell'ordine e la sua registrazione), lo scrive nel log come errore. Sono
   posizioni senza stop sorvegliato.

Non decide i livelli, non li sposta, non fa trailing, non apre niente. I livelli
glieli scriverà la strategia.

Se una chiusura fallisce, l'archivio **non** viene aggiornato: la posizione
resta "aperta" e al giro dopo si riprova. Un archivio che mente è peggio di un
archivio in ritardo.

---

## Endpoint

**`POST /webhook`**

| Codice | Significato |
|---|---|
| `200` | Alert accettato (il corpo riporta azione ed esito) |
| `401` | Segreto sbagliato o mancante. **Nessuna traccia in archivio** |
| `422` | JSON malformato o campi mancanti |
| `500` | Archiviazione fallita |

Esiti possibili nel corpo della risposta: `ignorato` (azione NONE),
`simulato` (dry_run), `in_attesa_conferma` (semi), `eseguito`, `errore`,
`bloccato` (salvaguardia), `duplicato`.

**`GET /salute`** — modalità corrente, MT5 disponibile/connesso/abilitato al
trading, equity e saldo, posizioni aperte (sul broker e in archivio), stato
della sentinella, stato delle salvaguardie, `posizioni_scoperte`, conteggi
delle tabelle e ultime cinque decisioni.

---

## Cosa c'è in archivio

File SQLite (`bot.db` per default), tre tabelle:

- **`alert`** — ogni alert valido ricevuto, con impronta, ritardo di consegna e
  payload completo in JSON. Il campo `secret` non viene mai scritto.
- **`decisione`** — cosa è stato deciso per ogni alert e com'è andata.
- **`posizione`** — le posizioni aperte dal bot con i loro livelli di stop e
  target. È la memoria su cui lavora la sentinella.

Per guardarci dentro:

```bat
python -c "import sqlite3; c=sqlite3.connect('bot.db'); c.row_factory=sqlite3.Row; [print(dict(r)) for r in c.execute('SELECT * FROM alert ORDER BY id DESC LIMIT 10')]"
```

C'è anche `bot.log`, che ruota a 5 MB e tiene le ultime 5 copie: quando un
ordine va storto alle 3 di notte, la console non c'è più ma il file sì.

---

## Il collaudo automatico

```bat
python -m unittest test_impianto -v
```

40 prove, mezzo secondo, nessun conto toccato. Coprono:

- la sicurezza del webhook (segreto sbagliato, vuoto, non configurato)
- che la strategia resti uno stub e che un alert valido non apra nulla
- le consegne doppie
- ogni salvaguardia, una per una
- il percorso completo degli ordini, **con un MetaTrader5 finto**: BUY in ask,
  SELL in bid, volume sotto il minimo del simbolo, Algo Trading spento, ordine
  rifiutato dal broker, riconnessione quando il terminale sparisce
- la sentinella: stop toccato, target toccato, prezzo in mezzo, short che si
  chiude sull'ask e non sul bid, riconciliazione, chiusura fallita che lascia
  la posizione aperta per riprovare
- la migrazione dell'archivio da uno schema precedente

Il MetaTrader5 finto è la parte che conta: permette di collaudare il codice che
un giorno muoverà soldi veri, su una macchina che non ha MT5 e senza rischiare
un centesimo.

---

## Quando la strategia sarà pronta

Si scrive **solo** in `core/strategy.py`. Il contratto è già fissato:

```python
def valuta(alert: AlertIn) -> Decision:
    ...
    return Decision(
        action="BUY",      # oppure SELL, CLOSE, NONE
        motivo="...",      # finisce in archivio e su Telegram
        volume=0.05,       # senza questo, in auto l'ordine non parte
        sl=1.0950,         # sorvegliati dalla sentinella,
        tp=1.1050,         # non mandati al broker
    )
```

Tutto il resto — archiviazione, salvaguardie, invio, sorveglianza, notifica,
riconciliazione — è già costruito e collaudato attorno a questa funzione.

---

## Cosa manca ancora

In ordine di importanza:

1. **La strategia.** `core/strategy.py` è uno stub. È il punto in cui andrà
   scritta la logica, quando i documenti che la descrivono saranno pronti.
2. **Il calcolo della size.** `Decision.volume` esiste ma nessuno lo riempie.
   Finché resta `None`, in `auto` l'ordine non parte — ed è giusto così.
3. **La conferma manuale in `semi`.** Oggi la modalità notifica e si ferma:
   manca il modo di dire "sì, esegui" (un bottone nel messaggio Telegram, o un
   endpoint di conferma).
4. **La chiusura mirata (`CLOSE`).** L'adattatore sa chiudere per ticket, ma
   nessuno gli dice quale: servirà quando la strategia esprimerà uscite.
5. **La conversione dei simboli** fra il nome TradingView e quello FP Markets.
6. **Riavvio automatico** di server e cloudflared all'accensione del PC
   (Utilità di pianificazione di Windows).
7. **Un secondo canale di allarme** indipendente dal PC: se il PC muore, muore
   anche Telegram, e non lo sai.
8. **Trailing stop e uscite parziali**, se la strategia le prevederà.
