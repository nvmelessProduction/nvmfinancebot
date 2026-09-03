# 05_rischio.md

Versione: 0.5 — ridimensionamento e size sul future
Data: 2026-08-12
Stato: INCOMPLETO. Vedi sezione 7 (Punti aperti).

Fuso orario: ogni orario di questo file è espresso nel fuso del server
FP Markets (`fuso_esecuzione`, DEF-03).

---

## 1. Rischio per operazione

### RISK-01 — Rischio base

```
rischio_base = 1.00% dell'equity per singola operazione
```

L'equity di riferimento è `equity` (MT5) al momento del calcolo della size, non
il saldo iniziale né il picco storico.

### RISK-02 — Rischio ridotto in caso di correlazione piena

Si applica esclusivamente agli strumenti forex derivati dal DXY: `EURUSD`,
`GBPUSD`, `AUDUSD`, `USDCHF`, `USDJPY`.

Sia `n` il numero di posizioni che verrebbero aperte simultaneamente.

```
SE n == 1  ALLORA rischio_operazione = 1.00%
SE n == 2  ALLORA rischio_operazione = 0.75%
SE n >= 3  ALLORA rischio_operazione = 0.45%
```

**Ridimensionamento.** A ogni nuova apertura tutte le posizioni già aperte
vengono ridimensionate al nuovo `rischio_operazione`, così che ciascuna rischi
sempre la stessa percentuale.

```
SE viene aperta una nuova posizione e n cambia
ALLORA ricalcola rischio_operazione
       adegua il volume di TUTTE le posizioni aperte al nuovo valore
ALTRIMENTI nessun effetto
```

| `n` | Rischio per posizione | Rischio totale |
|---|---|---|
| 1 | 1,00% | 1,00% |
| 2 | 0,75% | 1,50% |
| 3 | 0,45% | 1,35% |
| 4 | 0,45% | 1,80% |
| 5 | 0,45% | 2,25% |

**Due conseguenze da conoscere.**

La tabella non è monotona: passando da 2 a 3 posizioni il rischio totale scende
da 1,50% a 1,35%. Aprire una terza posizione **riduce** l'esposizione
complessiva. È una conseguenza voluta del ridimensionamento, ma va tenuta
presente: non è il comportamento che ci si aspetta intuitivamente.

Il ridimensionamento richiede di modificare il volume di posizioni già aperte.
Su MT5 questo significa chiudere parzialmente una posizione in essere, con i
costi di transazione relativi e senza garanzia di ottenere un volume esatto se
il passo minimo del broker non lo consente.

> **APERTO — vedi PA-63.** Va deciso cosa fare quando il ridimensionamento
> produrrebbe un volume inferiore al passo minimo del broker, o quando la
> chiusura parziale non è eseguibile.

```
SE n == 1  ALLORA rischio_operazione = 1.00%
SE n == 2  ALLORA rischio_operazione = 0.75%
SE n >= 3  ALLORA rischio_operazione = 0.45%
```

La stessa scala si applica sia alle posizioni su strumenti forex diversi
(RISK-05) sia alle posizioni multiple sullo stesso strumento (RISK-06).

`n` si calcola al momento dell'invio dell'ordine, contando le posizioni già
aperte più quella in valutazione. Le posizioni già aperte non vengono
ridimensionate quando `n` cresce.

### RISK-03 — Calcolo della size

Si applica DEF-47: la distanza di stop si misura **interamente sul future**.

```
distanza_stop_future = |chiusura_N2_future - livello_stop_future|
valore_punto         = valore monetario di 1 punto per 1 lotto sul CFD
size_lotti = (equity × rischio_operazione) / (distanza_stop_future × valore_punto × k)
```

dove `k` è il fattore di conversione tra punto future e punto CFD dello
strumento (PA-62).

Nessun prezzo CFD entra nel calcolo della distanza.

SE `distanza_stop == 0`
ALLORA il dato è incoerente: nessun ordine, si applica PRIN-99
ALTRIMENTI la size è calcolabile

La size viene arrotondata per **difetto** al passo minimo consentito dal
broker. Se l'arrotondamento per difetto produce zero, l'operazione non viene
eseguita.

### RISK-04 — Divisione del rischio su doppio ingresso

```
SE il CRT è a supporto di un gap (SETUP-04) e sono previsti due ingressi
ALLORA rischio_operazione viene diviso tra i due ingressi, metà ciascuno
ALTRIMENTI l'intero rischio_operazione è allocato all'unico ingresso
```

Il rischio complessivo dell'operazione resta invariato: due ingressi da metà
rischio, non due ingressi da rischio pieno.

---

## 2. Esposizione

### RISK-05 — Selezione degli strumenti forex

Non si apre una posizione su uno strumento solo perché il DXY ha dato una bias.
Si apre esclusivamente sugli strumenti che presentano un **setup proprio** nella
direzione inversa al DXY.

```
Per ciascuno strumento forex, indipendentemente dagli altri:
SE  bias_comando su DXY è definita
AND lo strumento presenta un setup valido (03_setup.md)
AND la direzione del setup è inversa a quella del DXY secondo SETUP-08
ALLORA lo strumento è eleggibile
ALTRIMENTI nessuna posizione su quello strumento
```

Esempio: DXY con setup LONG, `EURUSD` con setup SHORT valido, `GBPUSD` senza
setup. Si apre esclusivamente `EURUSD`.

### RISK-06 — Posizioni multiple sullo stesso strumento

Sono ammesse più posizioni sullo stesso strumento, una per ciascun timeframe che
conferma il pattern, secondo questa progressione:

```
Un trigger su TF_H1 abilita un ingresso sulla candela N2 di TF_H4
Se poi TF_H4 conferma, abilita un ingresso sulla candela N3 di TF_H4
Se poi TF_1D conferma, abilita un ingresso sulla candela di TF_1D
e così via verso i timeframe superiori
```

```
Massimo 4 posizioni contemporanee per singolo strumento.
```

SE sono già aperte 4 posizioni su uno strumento
ALLORA nessun ulteriore ingresso su quello strumento, anche in presenza di
       setup valido su timeframe superiori
ALTRIMENTI l'ingresso è ammesso

Il rischio di ciascuna posizione segue la scala di RISK-02.

**Conseguenza aritmetica da conoscere.** Quattro posizioni su uno strumento
valgono 1,80% di rischio. Cinque strumenti forex con quattro posizioni ciascuno
valgono 9,00% di rischio aggregato, che eccede sia il limite giornaliero di
RISK-07 (3%) sia quello settimanale di RISK-08 (6%). Il limite giornaliero
blocca le nuove aperture solo dopo che la perdita è stata realizzata: non
impedisce di costruire in anticipo un'esposizione superiore al limite.

> **APERTO — vedi PA-33.** Va deciso se introdurre un tetto di rischio
> aggregato di portafoglio, calcolato prima dell'apertura, che impedisca di
> superare una soglia complessiva a prescindere dal numero di strumenti.

---

## 3. Limiti di perdita

### RISK-07 — Limite giornaliero

```
SE pnl_giornaliero <= -3.00% dell'equity di inizio giornata
ALLORA nessun nuovo ordine fino alla successiva apertura giornaliera
ALTRIMENTI l'operatività è consentita
```

### RISK-08 — Limite settimanale

```
SE pnl_settimanale <= -6.00% dell'equity di inizio settimana
ALLORA nessun nuovo ordine fino alla successiva apertura settimanale
ALTRIMENTI l'operatività è consentita
```

### RISK-09 — Limite mensile

```
SE pnl_mensile <= -10.00% dell'equity di inizio mese
ALLORA nessun nuovo ordine fino alla successiva apertura mensile
ALTRIMENTI l'operatività è consentita
```

### RISK-10 — Comportamento dei limiti

I tre limiti si calcolano sul **P&L chiuso**. Le posizioni aperte non vengono
chiuse dal raggiungimento di un limite: il limite blocca l'apertura di nuove
posizioni, non la gestione di quelle esistenti.

> **APERTO — vedi PA-34.** Va deciso se un limite raggiunto debba anche
> chiudere le posizioni in essere. Con la regola attuale, il limite giornaliero
> del 3% può essere superato dalle posizioni già aperte senza che il sistema
> intervenga.

### PREC-01 — Precedenza del rischio sui setup

```
In conflitto: RISK batte SETUP.
SE un limite di RISK-07, RISK-08 o RISK-09 è raggiunto
ALLORA nessun setup valido viene eseguito, su nessuno strumento
```

---

## 4. Stop loss

### RISK-11 — Obbligatorietà dello stop

Nessuna posizione può esistere senza uno stop loss. Il livello è quello
definito da SETUP-10.

```
SE lo stop non è calcolabile
ALLORA l'ordine non viene inviato
ALTRIMENTI l'ordine è ammesso
```

### RISK-12 — Stop e target sorvegliati sul future

Stop loss e take profit **non** sono ordini pendenti presso il broker. Sono
livelli definiti sul prezzo del future e sorvegliati dal server.

```
SE il prezzo scambiato del future raggiunge livello_stop
ALLORA chiudi a mercato la posizione corrispondente sul CFD

SE il prezzo scambiato del future raggiunge target_valore
ALLORA chiudi a mercato la posizione corrispondente sul CFD

ALTRIMENTI la posizione resta aperta
```

Il future è l'unico riferimento. Una posizione viene chiusa quando il livello è
raggiunto sul future, anche se sul CFD di FP Markets quel livello non è stato
toccato. Vale simmetricamente per stop e target. Nessuna conversione di prezzo
viene mai effettuata.

**Rischio residuo da conoscere.** Non esistendo ordini pendenti presso il
broker, la protezione della posizione dipende interamente dalla disponibilità
del server, della connessione e del flusso dati dal future. In caso di
interruzione, la posizione su FP Markets resta aperta senza alcuna protezione a
livello broker.

> **APERTO — vedi PA-38.** Va deciso il comportamento del sistema in caso di
> perdita del flusso dati o della connessione: chiusura di tutte le posizioni,
> mantenimento, o soglia di tempo oltre la quale intervenire.

---

## 5. Filtri temporali

### RISK-13 — Blocco per news ad alto impatto

```
fonte_calendario = investing.com, calendario economico
filtro           = eventi a impatto 3 stelle (alto)
finestra_blocco  = da 30 minuti prima a 30 minuti dopo l'orario della news
```

```
SE è prevista una news 3 stelle su una valuta coinvolta nello strumento
AND l'orario corrente è dentro finestra_blocco
ALLORA nessun nuovo ordine su quello strumento
ALTRIMENTI l'operatività è consentita
```

**Posizioni già aperte.** Una posizione aperta prima dell'inizio della finestra
di blocco resta aperta e attraversa la news senza modifiche. Il blocco riguarda
esclusivamente le nuove aperture.

Esempio: news alle 14:30. Un setup che si presenta alle 14:00 è eseguibile,
perché precede la finestra. Un setup alle 14:05 non lo è. Le nuove aperture
riprendono alle 15:00.

**XAUUSD.** Per l'oro il filtro non è ristretto a una valuta: ogni news a
impatto 3 stelle, di qualsiasi paese, blocca le nuove aperture su `XAUUSD`
secondo la stessa `finestra_blocco`.

---

## 6. Durata delle posizioni

### RISK-14 — Mantenimento oltre la chiusura settimanale

Le posizioni non vengono chiuse per motivi di calendario. Una posizione aperta
resta aperta fino al raggiungimento del target o dello stop, anche attraverso
la chiusura settimanale e il fine settimana.

```
SE la posizione è stata aperta su un timeframe di riferimento e quel timeframe
   ha confermato il pattern
ALLORA la posizione resta aperta fino a target o stop
ALTRIMENTI si applicano le regole di 04_gestione.md
```

Il target finale è quello del timeframe di riferimento: per un'operazione con
visione settimanale, l'estremo opposto della candela `N1` settimanale.

> **APERTO — vedi PA-37.** Il mantenimento nel fine settimana espone al rischio
> di apertura domenicale, che nessuno stop può coprire: il prezzo può aprire
> oltre il livello di stop. Va deciso se accettare questo rischio o ridurre la
> size delle posizioni mantenute attraverso il weekend.

---

## 7. Punti aperti

| ID | Punto aperto | Priorità |
|---|---|---|
| PA-32 | Scala del rischio | CHIUSO in v0.2 (RISK-02) |
| PA-33 | Tetto di rischio aggregato di portafoglio, calcolato prima dell'apertura | ALTA |
| PA-58 | Calcolo della size | CHIUSO in v0.5 (DEF-47) |
| PA-62 | Fattore di conversione `k` punto future / punto CFD per i sei strumenti | CRITICA |
| PA-61 | Ridimensionamento | CHIUSO in v0.5 (RISK-02): tutte le posizioni si adeguano |
| PA-63 | Ridimensionamento non eseguibile per passo minimo del broker | ALTA |
| PA-34 | Se il raggiungimento di un limite di perdita debba chiudere le posizioni aperte | MEDIA |
| PA-35 | Conflitto stop broker vs future | CHIUSO in v0.2 (RISK-12): il future è l'unico riferimento, chiusura a mercato sul CFD |
| PA-36 | Filtro news per `XAUUSD` | CHIUSO in v0.3 (RISK-13): tutte le news 3 stelle |
| PA-38 | Comportamento in caso di perdita del flusso dati o della connessione | ALTA |
| PA-37 | Rischio di apertura domenicale sulle posizioni mantenute nel fine settimana | MEDIA |
