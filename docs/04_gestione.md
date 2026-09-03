# 04_gestione.md

Versione: 0.2 — bozza in revisione
Data: 2026-08-12
Stato: INCOMPLETO. Vedi sezione 6 (Punti aperti).

Prerequisito: `01_definizioni.md` e `03_setup.md`.

---

## 1. Filtro di ammissibilità

### GEST-01 — Rapporto rischio/rendimento minimo

```
rr = |target_iniziale - prezzo_ingresso| / |prezzo_ingresso - livello_stop|

SE rr < 1.5
ALLORA l'ordine NON viene inviato
ALTRIMENTI l'ordine è ammesso
```

Il controllo si esegue prima dell'invio, sui prezzi effettivi al momento
dell'ordine, non su quelli teorici alla chiusura di `N2`.

```
target_iniziale = target_finale alla data dell'ingresso (SETUP-14),
                  NON TP1
```

Il rapporto si calcola sul target finale, non sul parziale. Il filtro esclude
quindi i soli setup in cui lo stop è ampio rispetto alla distanza dal target
finale, e lascia passare la maggior parte dei setup conformi.

---

## 2. Stop loss

### GEST-02 — Stop iniziale

```
CRT senza gap        → stop_aggressivo   = estremo di N2
CRT a supporto di gap → due ingressi:
                        ingresso CRT → stop_aggressivo
                        ingresso gap → stop_conservativo = estremo della zona_gap
```

### GEST-03 — Immobilità dello stop fino a TP1

```
Lo stop iniziale non viene mai spostato prima del raggiungimento di TP1,
in nessuna circostanza e per nessun motivo.
```

Non esistono stop parziali, stop temporali, né riduzioni della distanza di stop
in caso di movimento contrario.

### GEST-04 — Break even

```
SE il prezzo scambiato del future raggiunge TP1
ALLORA chiudi il 25% della posizione
       sposta lo stop del restante 75% a livello_break_even
ALTRIMENTI nessuna azione
```

```
livello_break_even  long:  prezzo_ingresso + buffer_be
                    short: prezzo_ingresso - buffer_be
```

Il `buffer_be` copre spread e commissioni: lo stop a pareggio deve chiudere in
pareggio reale, non in perdita per i costi.

> **APERTO — vedi PA-46.** `buffer_be` non è quantificato. Va espresso in punti
> per ciascuno strumento, oppure come multiplo dello spread medio.

### GEST-05 — Immobilità dopo il break even

```
Dopo il passaggio a break even lo stop non si sposta più.
Nessun trailing stop è previsto in alcuna forma.
```

### GEST-06 — Invalidazione del gap con posizione aperta

```
SE la posizione usa stop_conservativo
AND il gap viene INVALIDATO (DEF-14)
ALLORA lo stop è già stato colpito: la posizione è chiusa in perdita
       Il livello di invalidazione del gap e lo stop conservativo coincidono.

SE la posizione usa stop_aggressivo
AND il gap viene INVALIDATO mentre lo stop non è stato colpito
ALLORA nessuna azione automatica
```

> **APERTO — vedi PA-47.** Il secondo caso non ha una regola. Una posizione con
> stop aggressivo può sopravvivere all'invalidazione del gap che l'aveva
> motivata: va deciso se chiuderla, portarla a break even o lasciarla correre.

---

## 3. Take profit

### GEST-07 — TP1 e parziale

```
TP1 = KL_50 della candela N1 del timeframe su cui è nato il CRT (DEF-36)
```

```
SE il prezzo raggiunge TP1
ALLORA chiudi il 25% della posizione, applica GEST-04
ALTRIMENTI la posizione resta invariata
```

Il restante 75% non ha ulteriori parziali.

### GEST-08 — Target finale ed estensione

```
Alla chiusura di ogni candela di un timeframe superiore a quello del CRT:
SE  quel timeframe conferma il pattern nella stessa direzione
ALLORA target_finale = key level di quel timeframe nella direzione
       dell'operazione
ALTRIMENTI target_finale resta invariato
```

L'estensione è a senso unico: il target si sposta solo verso timeframe
superiori, mai indietro.

### GEST-09 — Target consumato prima del raggiungimento

```
SE il key level scelto come target_finale viene CONSUMATO (DEF-27) da un
   movimento che non appartiene alla posizione
ALLORA la posizione è già protetta a break even e vi resta
ALTRIMENTI nessun effetto
```

> **APERTO — vedi PA-48.** La regola presuppone che `TP1` sia già stato
> raggiunto. Se il target viene consumato prima di `TP1`, la posizione è ancora
> allo stop iniziale e non esiste una regola.

### GEST-10 — Chiusura al target di tf_comando

```
SE il target di tf_comando è RAGGIUNTO
ALLORA chiudi a mercato tutte le posizioni aperte nella direzione della
       vecchia bias_comando
ALTRIMENTI nessuna azione
```

---

## 4. Esecuzione

### GEST-11 — Chiusura sempre eseguita

```
SE il prezzo del future raggiunge stop o target
ALLORA chiudi a mercato sul CFD, senza soglia di tolleranza sul prezzo
       ottenuto
```

Non esiste una deviazione massima oltre la quale rinunciare alla chiusura. Il
future è l'unico riferimento (RISK-12).

### GEST-12 — Riavvio del sistema

```
SE il sistema si riavvia con posizioni aperte
ALLORA ricostruisce lo stato di ciascuna posizione e continua a gestirla
ALTRIMENTI nessun effetto
```

Lo stato da ricostruire per ogni posizione comprende: strumento, direzione,
prezzo di ingresso, timeframe del CRT di origine, livello di stop corrente,
`TP1`, `target_finale`, e se `TP1` sia già stato raggiunto.

> **APERTO — vedi PA-49.** Va definito dove questo stato viene salvato e con
> quale frequenza, perché è ciò che rende possibile il recupero.

---

## 5. Posizioni multiple

### GEST-13 — Indipendenza delle posizioni

```
Ogni posizione ha il proprio TP1, il proprio break even e il proprio
target_finale, calcolati sul timeframe del CRT che l'ha generata.
```

Le posizioni sullo stesso strumento non si gestiscono come blocco unico. Lo
stop di una non influenza le altre.

### GEST-14 — Divieto di mediazione

```
Nessuna posizione in perdita viene mai incrementata.
Nessuno stop viene mai allargato.
```

---

## 6. Punti aperti

| ID | Punto aperto | Priorità |
|---|---|---|
| PA-45 | Target del rapporto R/R | CHIUSO in v0.2 (GEST-01): il target finale |
| PA-46 | Valore di `buffer_be` per ciascuno strumento | MEDIA |
| PA-47 | Comportamento con stop aggressivo quando il gap viene invalidato | ALTA |
| PA-48 | Target consumato prima del raggiungimento di TP1 | MEDIA |
| PA-49 | Dove e con quale frequenza si salva lo stato delle posizioni | ALTA |
