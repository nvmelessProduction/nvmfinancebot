# 07_casi.md

Versione: 0.1 — struttura e istruzioni di compilazione
Data: 2026-08-12
Stato: DA POPOLARE

---

## 1. Come si compila

**L'etichetta è di conformità, non di esito.** Ogni caso si etichetta
`CONFORME` o `NON CONFORME` alla strategia, mai `vinto` o `perso`. Una
decisione corretta può perdere e una pessima può vincere. Se si etichettasse
sull'esito, dopo qualche centinaio di casi il sistema avrebbe imparato il
rumore degli ultimi mesi di mercato invece della strategia.

L'esito si annota comunque, ma in un campo separato e marcato come
informativo.

**I casi di non ingresso vanno inclusi.** Sono i più informativi e sono quelli
che quasi nessuno annota. Un caso in cui il pattern sembrava valido ma un
filtro lo ha escluso vale quanto un ingresso riuscito.

**Un caso per blocco, formato fisso.** Nessun campo può essere omesso. Se un
dato non è disponibile, si scrive `n/d`.

---

## 2. Formato del blocco

```
CASO nn
Data/ora:        AAAA-MM-GG HH:MM UTC
Strumento:       simbolo future analizzato
TF del CRT:      timeframe su cui si è formato il pattern
TF del key level: timeframe del key level preso

DATI
  bias_comando:      LONG / SHORT / NESSUNA
  tf_comando:        timeframe
  key_level_preso:   valore e tipo (KL_max / KL_min) e TF
  gap_attivo_tf:     timeframe del gap attivo, o NESSUNO
  gap_zona:          [inferiore, superiore]
  gap_fase:          1 / 2 / 3 / 4 / n.a.
  N1 high/low:       valori
  N2 high/low/close: valori
  N3 open:           valore
  tf_allineati:      elenco dei timeframe allineati
  divergenza_rsi:    RIBASSISTA / RIALZISTA / NESSUNA
  rr_su_tp1:         valore calcolato

REGOLE APPLICABILI
  elenco degli ID coinvolti, es. SETUP-02A, SETUP-05, GEST-01

TUA DECISIONE
  LONG / SHORT / NESSUN INGRESSO

MOTIVO
  una o due righe, in linguaggio naturale

ETICHETTA
  CONFORME / NON CONFORME alla strategia

ESITO TRADE
  +1.8R  oppure  -1R  oppure  n.a.
  [informativo, NON è l'etichetta]
```

---

## 3. Categorie richieste

### 3.1 Per GIUD-01 — minimo 10 casi per categoria

GIUD-01 chiede: sul timeframe di riferimento esistono sia un key level sia un
gap nella direzione dell'operazione. Quale è il target?

| Categoria | Significato | Casi richiesti |
|---|---|---|
| A | il target è il gap | 10 |
| B | il target è il key level | 10 |
| C | ambiguo → il target resta al key level | 10 |

In ciascuno di questi casi il campo `DATI` deve contenere anche:

```
  distanza_kl_gap:   distanza in punti tra key level e bordo del gap
  atr_tf:            ATR(14) del timeframe di riferimento
  rapporto:          distanza_kl_gap / atr_tf
```

Il campo `rapporto` è ciò che permetterà di ricavare la soglia numerica di
"vicini" e "distanti" e di chiudere PA-44.

### 3.2 Casi di non ingresso — minimo 15

Situazioni in cui il pattern era presente ma non si è operato. Almeno due casi
per ciascun motivo:

```
- nessun key level preso (SETUP-00)
- direzione opposta a bias_comando (SETUP-07)
- meno di 2 timeframe superiori allineati (SETUP-05)
- rapporto rischio/rendimento sotto 1,5 (GEST-01)
- gap_fase diversa da 3 su ingresso da gap (SETUP-09)
- mitigazione_attesa NON_DETERMINATA (DEF-42)
- finestra di blocco news (RISK-13)
```

### 3.3 Casi di ingresso regolare — minimo 20

Distribuiti tra:

```
- CRT senza gap, stop aggressivo
- CRT a supporto di gap, doppio ingresso
- ingresso su TF basso che anticipa la N2 del TF superiore
- ingresso su TF di riferimento
- almeno 5 casi su XAUUSD e 5 sulle coppie forex
```

### 3.4 Casi limite — minimo 10

Le situazioni che rompono i sistemi. Almeno uno per ciascuna:

```
- candela che rompe entrambi gli estremi e chiude in mezzo (DEF-16 passo 1)
- inside bar che forma un gap (DEF-23)
- serie di inside bar consecutive con bias ereditata (DEF-24)
- gap invalidato mentre la posizione è aperta (GEST-06)
- target consumato prima del raggiungimento di TP1 (GEST-09)
- key level di TF diversi che coincidono (DEF-37)
- gap formato in corrispondenza di un rollover (DEF-35)
- cambio di bias_comando con posizione aperta (SETUP-17)
```

**Totale minimo: 75 casi.**

---

## 4. Procedura pratica

```
Passo 1  Apri il grafico future su TradingView e usa la funzione Replay.
         Posizionati a una data passata e avanza candela per candela.

Passo 2  Quando il prezzo prende un key level, fermati e compila un blocco,
         anche se decidi di non entrare.

Passo 3  Annota i valori esatti di OHLC leggendoli dalla barra dati in alto,
         non a occhio dal grafico.

Passo 4  Scrivi la decisione PRIMA di far avanzare il replay.
         Questo è il punto critico: se avanzi e poi decidi, stai etichettando
         sull'esito e i casi diventano inutili.

Passo 5  Fai avanzare il replay e annota l'esito nel campo informativo.

Passo 6  Numerazione progressiva, senza buchi e senza riutilizzo.
```

**Ordine consigliato.** Comincia da XAUUSD, che ha già un percorso documentato
e ti è più familiare. Venti casi su un solo strumento valgono più di venti casi
sparsi su sei strumenti diversi.

**Ritmo realistico.** Un caso ben compilato richiede diversi minuti. Non
provare a farne settantacinque in una sessione: la qualità crolla e con essa
l'utilità dell'intero file.

---

## 5. Caso di esempio

Il caso che segue è un modello di compilazione, ricostruito dal percorso XAU
già documentato. I valori sono quelli letti dai grafici; va verificato e
sostituito con casi reali annotati in tempo reale.

```
CASO 01
Data/ora:         2026-05-12 04:00 UTC
Strumento:        GC (COMEX)
TF del CRT:       TF_H4
TF del key level: TF_1W

DATI
  bias_comando:      SHORT
  tf_comando:        TF_3M
  key_level_preso:   KL_max TF_1W = 4.775,4
  gap_attivo_tf:     TF_1W
  gap_zona:          [4.737,0 , 4.783,0]
  gap_fase:          3
  N1 high/low:       n/d — da rilevare
  N2 high/low/close: n/d — da rilevare
  N3 open:           n/d — da rilevare
  tf_allineati:      TF_1D, TF_1W
  divergenza_rsi:    n/d — da rilevare
  rr_su_tp1:         n/d — da calcolare

REGOLE APPLICABILI
  SETUP-00, SETUP-02A, SETUP-03, SETUP-05, SETUP-09, GEST-01, GEST-02

TUA DECISIONE
  SHORT

MOTIVO
  Presa del massimo settimanale come key level, prezzo in fase 3 dentro il
  gap weekly, CRT formato su H4 con TF_1D e TF_1W allineati in direzione
  short. Bias di comando trimestrale non ancora al target.

ETICHETTA
  CONFORME alla strategia

ESITO TRADE
  n/d [informativo, NON è l'etichetta]
```

---

## 6. Errori da non commettere

```
1. Etichettare sull'esito invece che sulla conformità.
   È l'errore più facile e il più costoso: rende inutile tutto il file.

2. Annotare solo gli ingressi.
   Senza i casi di non ingresso il sistema non impara quando astenersi.

3. Compilare dopo aver visto come è andata.
   La decisione va scritta prima di far avanzare il replay.

4. Leggere i prezzi a occhio dal grafico.
   I valori vanno letti dalla barra dati, con tutti i decimali.

5. Selezionare solo i casi belli.
   I casi ambigui e quelli in cui hai sbagliato sono i più utili.

6. Saltare i campi.
   Un campo mancante rende il caso inutilizzabile come test di verifica.
```

---

## 7. Casi annotati

Da qui in avanti, un blocco per caso, numerazione progressiva a partire da
CASO 02.
