# Mettere in funzione il bot

## 1. La configurazione operativa

Questa è la configurazione che ha dato il miglior risultato **al netto dello
spread reale**, cercata su 36 combinazioni di coppia di timeframe, bersaglio e
filtri (`backtest/` — la ricerca, non un test):

```
coppia          M1 → D1        (candela mensile come range, giornaliera per l'ingresso)
bersaglio       3R             (invece del 50% fisso del range)
filtro          CISD presente sul timeframe basso
filtro          peso delle ombre di N2 ≥ 0,6
```

| | |
|---|---:|
| operazioni in 20 anni | 136 |
| costo medio dello spread | 0,071 R |
| **R netto per operazione** | **+0,1008** |
| σ | +0,9 |

**Cosa significa σ = 0,9.** È il migliore che esiste nei dati, non è
statisticamente stabilito. Con 136 operazioni in vent'anni — circa 7 all'anno —
servono anni per distinguerlo dal caso. Va operato su demo abbastanza a lungo
da raccogliere operazioni vere, e la configurazione va rivista con quelle.

Le tre cose che l'hanno resa positiva, in ordine di peso:

1. **Il CISD.** Senza, il CRT rende negativo. È l'unica conferma di Romeo che
   regge alla misura (`docs/MISURA-REGOLE-MANCANTI-2026-09-16.md`).
2. **Il bersaglio a 3R invece del 50%.** Il 50% del range è vicino, e su un
   bersaglio vicino il costo pesa. A 3R le vittorie pagano il costo.
3. **`M1 → D1`.** Stop larghi: lo spread è 0,071 R invece dei 0,15–0,35 R che
   avevo riportato per le coppie orarie. Il costo non è una costante della
   strategia, dipende dalla coppia — ed è l'errore che mi aveva fatto
   dichiarare la strategia impraticabile.

## 2. Configurazione del file `.env`

```ini
MODE=dry_run                 # dry_run -> semi -> auto, in quest'ordine
FORNITORE_DATI=dukascopy     # candele vere: estremi toccati, spread misurato
SENTINELLA_ATTIVA=true       # sorveglia stop e target: non spegnerla mai

GIUDIZIO_ATTIVO=true         # Claude giudica ogni setup
ANTHROPIC_API_KEY=...        # da console.anthropic.com

MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...
MT5_SUFFISSO_SIMBOLI=        # scoprilo con: python prova_esecuzione.py

CONSENTI_CONTO_REALE=false   # lasciala false finché non hai dati tuoi
```

`.env` non va mai committato. È già in `.gitignore`.

## 3. Avviare

```bash
pip install -r requirements.txt

# 1. Semina l'archivio con vent'anni di candele vere (una volta sola,
#    riprende da dove era se lo rilanci).
python importa_dukascopy.py

# 2. Verifica broker, simboli e suffisso.
python prova_esecuzione.py

# 3. Accendi.
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Da dove vengono le candele

**Dukascopy**, il book della banca svizzera. File `.bi5`, uno per mese,
compressi LZMA. Due cose che nessun'altra fonte gratuita dà:

- **gli estremi sono quelli davvero toccati**, non campionati. Su una fonte
  aggregata il **37,7% degli esiti cambiava** e un vantaggio inesistente
  sembrava reale (`docs/SPOT-CONTRO-FUTURE-2026-09-16.md`);
- **BID e ASK separati**, quindi lo spread si *misura* invece di assumerlo.

Verificato: EURUSD 1,00 pip nel 2006 → 1,50 nel 2008 (crisi finanziaria) →
0,20–0,30 oggi. È la storia reale dello spread.

Sono gli **stessi dati su cui ogni misura di questo progetto è stata fatta**.
Far girare il bot su dati diversi da quelli su cui è stato misurato è il modo
più silenzioso di invalidare la misura: nessun test fallisce, nessun log
protesta, e i numeri promessi non arrivano.

**Uno scostamento dichiarato.** Dukascopy serve il book di un broker, non il
future CME. È della stessa famiglia del CFD su cui `DEF-34` fa eseguire, e per
questo le candele si archiviano sotto il nome del CFD (`EURUSD`) e non del
future (`6E`). È uno scostamento da `DEF-32`, che vuole l'analisi sul future:
si rinuncia al future e si guadagnano estremi veri e spread misurato.
Misurando, la seconda cosa pesa di più — ma resta una scelta, non un fatto.

### Come si aggiornano

Due meccanismi distinti:

| | |
|---|---|
| **Storico** | `python importa_dukascopy.py`, a mano, quando vuoi. Non riscrive ciò che c'è già. |
| **Tempo reale** | `core/mercato_duka.py`, un ciclo che gira da solo ogni 15 minuti, scarica gli ultimi due mesi di orarie, costruisce i cinque timeframe e fa scattare una valutazione a ogni candela chiusa. |

L'ultima candela oraria si scarta sempre: Dukascopy pubblica il mese corrente
man mano e l'ultima riga può essere incompleta. `ESCL-13` vieta di valutare
una candela in formazione.

Il bot scarica le candele da solo, valuta a ogni chiusura, sorveglia le
posizioni aperte ogni 5 secondi.

## 4. Il trader discrezionale

Con `GIUDIZIO_ATTIVO=true`, ogni setup che **tutte** le regole hanno approvato
passa da Claude, che riceve un dossier numerico e risponde `ACCETTA` o
`RIFIUTA` con un motivo.

**Può solo rifiutare.** Non può autorizzare ciò che le regole vietano, né
cambiare direzione, size, stop o bersaglio. Un trader discrezionale che possa
scavalcare `RISK-07` — il limite di perdita giornaliero — non è un trader
discrezionale: è un bug con una buona spiegazione.

**Fallisce chiuso.** Chiave assente, rete giù, timeout, risposta malformata:
ogni esito diverso da un `ACCETTA` esplicito ferma l'ordine. Se non si sa, non
si opera.

Ogni verdetto finisce in archivio col suo motivo. Fra sei mesi si potrà
confrontare l'esito degli accettati con quello dei rifiutati: se i rifiutati
fossero andati meglio, il giudizio toglie valore e va spento. È l'unico modo
di saperlo.

## 5. Le tre modalità, in ordine

| `MODE` | Cosa fa |
|---|---|
| `dry_run` | Valuta e registra, non manda nulla. Parti da qui. |
| `semi` | Ti avvisa su Telegram e aspetta la tua conferma a mano. |
| `auto` | Manda gli ordini da solo. Su conto non demo serve `CONSENTI_CONTO_REALE=true`. |

Resta in `dry_run` finché non vedi che le decisioni che registra sono quelle
che ti aspetti. Poi `semi` per un po'. Poi `auto` su demo.

## 6. Cosa guardare

```
GET /salute      stato di broker, sentinella, mercato, ultimo errore
GET /decisioni   le ultime decisioni con motivo e regole applicate
GET /posizioni   cosa è aperto e con quali livelli
```

Su Telegram arrivano ordini, TP1, break even e chiusure.
