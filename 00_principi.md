# 00_principi.md

Versione: 0.1 — bozza in revisione
Data: 2026-08-12
Stato: INCOMPLETO. Vedi sezione 8 (Punti aperti).

---

## 1. Il principio operativo

La strategia si fonda sulla **CRT — Candle Range Theory**: una sequenza di tre
candele in cui la prima costruisce un range di accumulazione, la seconda
manipola prendendo liquidità oltre un estremo, e la terza distribuisce nella
direzione opposta alla manipolazione.

Lo stesso schema si applica identico su ogni timeframe. Ciò che cambia da un
timeframe all'altro non è il pattern, ma il contesto che stabilisce dove
cercarlo e in quale direzione.

Il contesto è dato da tre elementi, in quest'ordine:

```
1. la bias di comando, determinata dal timeframe più alto con un target
   non ancora raggiunto
2. il key level preso, che indica dove la liquidità è stata prelevata
3. il gap, che indica dove il prezzo è diretto
```

Il CRT è lo strumento di ingresso. Non è mai il motivo dell'ingresso.

---

## 2. Cosa la strategia NON fa

```
PRIN-01  Non opera mai contro bias_comando, in nessuna circostanza,
         nemmeno con un CRT formato correttamente.

PRIN-02  Non entra mai senza la presa di un key level. Nessuna forma di
         candela, per quanto conforme, produce un ingresso in assenza di un
         key level sbilanciato.

PRIN-03  Non usa indicatori, con l'unica eccezione dell'RSI applicato ai gap,
         e limitatamente alla registrazione della divergenza (DEF-44).

PRIN-04  Non fa scalping. Nessun timeframe inferiore a TF_H1 viene mai
         analizzato o operato.

PRIN-05  Non media mai le posizioni in perdita e non allarga mai uno stop.

PRIN-06  Non prende reversal finché il target di tf_comando non è stato
         raggiunto.

PRIN-07  Non converte mai prezzi tra future e CFD, e non confronta mai i due.
```

---

## 3. Strumenti

### PRIN-08 — Universo operativo

| Esecuzione (CFD, FP Markets) | Analisi (future) | Segno |
|---|---|---|
| `XAUUSD` | `GC` (COMEX) | diretto |
| `EURUSD` | `6E` (CME) | diretto |
| `GBPUSD` | `6B` (CME) | diretto |
| `AUDUSD` | `6A` (CME) | diretto |
| `USDCHF` | `6S` (CME) | invertito |
| `USDJPY` | `6J` (CME) | invertito |

Strumento di sola analisi, mai operato:

| Simbolo | Uso |
|---|---|
| `ICEUS` | DXY future, per `TF_1D` e superiori |
| `CAPITALCOM:DXY` | DXY CFD, per `TF_H12` e inferiori |

Nessuno strumento al di fuori di questo elenco può essere analizzato o operato.

### PRIN-09 — Derivazione direzionale

`XAUUSD` ha bias propria e non deriva la direzione dal DXY.

Le cinque coppie forex derivano la direzione dal DXY secondo SETUP-08, ma si
opera esclusivamente sulle coppie che presentano un **setup proprio** nella
direzione inversa (RISK-05). La bias del DXY abilita, non obbliga.

---

## 4. Timeframe

### PRIN-10 — Timeframe ammessi

```
Bias ed esecuzione: TF_12M, TF_6M, TF_3M, TF_1M, TF_1W, TF_1D
Solo gap:           TF_H12, TF_H6
Solo esecuzione:    TF_H4, TF_H1
```

Nessun altro timeframe esiste per la strategia.

### PRIN-11 — Solo candele chiuse

Ogni regola usa esclusivamente candele chiuse. La candela in formazione non
viene mai valutata.

---

## 5. Sessioni operative

### PRIN-12 — Orario di attività

```
Il sistema è attivo 24 ore su 24 nei giorni di mercato aperto.
```

Non esistono fasce orarie escluse, né periodi dell'anno di sospensione.

### PRIN-13 — Apertura domenicale

```
SE all'apertura domenicale esiste un setup valido su TF_1W o superiore
ALLORA l'ingresso sulla candela N3 è ammesso
ALTRIMENTI nessuna operatività domenicale
```

### PRIN-14 — Unica sospensione: news ad alto impatto

L'unica interruzione prevista è la finestra di blocco per news a impatto
3 stelle (RISK-13).

---

## 6. Modalità di esercizio

### PRIN-15 — Percorso di attivazione

```
Fase 1  Conto demo
Fase 2  Conto reale       ← le regole di questi documenti sono scritte per qui
Fase 3  Conto prop
```

Il passaggio da una fase alla successiva non è automatico.

**Ambito attuale dei documenti.** Tutte le soglie di `05_rischio.md` sono
dimensionate per un conto reale personale, con capitale iniziale minimo
indicativo di 1.000 EUR.

**Il conto prop richiederà una revisione separata.** I fornitori prop impongono
limiti propri che non sono negoziabili e che non coincidono con quelli scelti
qui. Con i valori indicati a titolo di riferimento — conto da 50.000 e limite
di perdita di 500 EUR — una singola operazione al rischio dell'1% (500 EUR)
esaurirebbe l'intero limite del fornitore, e il limite giornaliero interno del
3% (1.500 EUR) ne consentirebbe il triplo. Nel caso di massima esposizione
(quattro posizioni su ciascuno dei cinque strumenti forex) si arriverebbe al
9%, cioè 4.500 EUR: nove volte il limite.

Prima della fase 3 va prodotta una versione di `05_rischio.md` con soglie
ricalcolate sui vincoli effettivi del fornitore.

> **APERTO — vedi PA-50.** Non sono definiti i criteri di passaggio tra le
> fasi: quante operazioni, per quanto tempo, con quali risultati.

### PRIN-16 — Supervisione

```
Modalità iniziale: SEMI-AUTOMATICA
Il sistema calcola il setup, la size e i livelli, e propone l'ordine.
L'esecuzione richiede conferma manuale.
```

Il passaggio alla modalità completamente automatica avviene solo dopo una fase
di funzionamento verificato in semi-automatico.

> **APERTO — vedi PA-51.** Non è definito cosa accade a un setup proposto che
> non riceve conferma entro il tempo utile. Per SETUP-04 l'ingresso decade se
> non eseguito all'apertura di `N3`: la conferma manuale deve arrivare entro
> quel momento, altrimenti il setup è perso.

---

## 7. Default di sicurezza

### PRIN-99 — Astensione

```
In assenza di una regola applicabile, o in presenza di dati mancanti o
incoerenti: NON OPERARE.

L'astensione non richiede giustificazione.
```

Un trade saltato costa zero. Un trade sbagliato costa.

### PREC-01 — Precedenza in caso di conflitto

```
In conflitto: RISK batte SETUP.
Se un limite di 05_rischio.md è raggiunto, nessun setup valido viene eseguito.
```

### PREC-02 — Precedenza tra timeframe

```
In conflitto tra timeframe: il timeframe più alto comanda sempre.
```

### PREC-03 — Precedenza della fonte dati

```
In conflitto tra future e CFD: il future comanda sempre.
```

---

## 8. Punti aperti

| ID | Punto aperto | Priorità |
|---|---|---|
| PA-50 | Criteri di passaggio tra demo, reale e prop (PRIN-15) | MEDIA |
| PA-51 | Comportamento di un setup proposto e non confermato in tempo (PRIN-16) | ALTA |
| PA-52 | Vincoli del fornitore prop | RINVIATO alla Fase 3. Vedi nota sotto |

### Nota su PA-52 — da riprendere prima della Fase 3

I limiti di `05_rischio.md` sono tarati su un conto personale. Su un conto prop
i limiti sono imposti dal fornitore e non sono negoziabili.

Con i valori indicati a titolo orientativo — conto da 50.000 e limite di perdita
di 500 — i numeri attuali risultano incompatibili:

| Regola | Valore | Su 50.000 |
|---|---|---|
| RISK-01, rischio per operazione | 1,00% | 500 |
| RISK-07, limite giornaliero | 3,00% | 1.500 |
| RISK-06, quattro posizioni su uno strumento | 1,80% | 900 |
| Esposizione teorica massima, cinque strumenti | 9,00% | 4.500 |

Una sola operazione in stop consumerebbe l'intero limite giornaliero del
fornitore. Prima di passare alla Fase 3 vanno raccolti i limiti esatti
(perdita giornaliera, perdita totale, base di calcolo su saldo o equity,
eventuale target) e va prodotta una taratura dedicata di `05_rischio.md`.
