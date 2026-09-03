# 03_setup.md

Versione: 0.3 — bozza in revisione
Data: 2026-08-12
Stato: INCOMPLETO. Vedi sezione 9 (Punti aperti).

Prerequisito: ogni termine usato qui è definito in `01_definizioni.md`.
Nessuna regola di questo file introduce concetti nuovi.

---

## 1. Il vincolo fondamentale

### SETUP-00 — Nessun CRT senza key level

```
Il CRT esiste solo come reazione alla presa di un key level.
In assenza di un key level preso (DEF-38), nessun CRT è valido,
qualunque sia la forma delle candele.
```

Ogni massimo e minimo di candela chiusa su `TF_1D`, `TF_1W`, `TF_1M`, `TF_3M`,
`TF_6M`, `TF_12M` è un key level (DEF-36). L'insieme si aggiorna alla chiusura
di ogni candela del rispettivo timeframe.

Il CRT è lo strumento di ingresso. Il key level e il gap sono ciò che stabilisce
dove e in quale direzione cercarlo.

---

## 2. Struttura CRT

### SETUP-01 — Nomenclatura

Tre candele consecutive chiuse sullo stesso timeframe:

```
N1 = candela di range / accumulazione   (la più vecchia)
N2 = candela di manipolazione
N3 = candela di distribuzione           (la più recente)
```

### SETUP-02A — CRT short

```
SE  high[N2] > KL_max di un timeframe superiore a quello del CRT (DEF-38)
AND high[N2] > high[N1]
AND close[N2] <= high[N1]
AND close[N2] < close[N1]
ALLORA il CRT short è FORMATO alla chiusura di N2
ALTRIMENTI nessun CRT short
```

### SETUP-02B — CRT long

```
SE  low[N2] < KL_min di un timeframe superiore a quello del CRT (DEF-38)
AND low[N2] < low[N1]
AND close[N2] >= low[N1]
AND close[N2] > close[N1]
ALLORA il CRT long è FORMATO alla chiusura di N2
ALTRIMENTI nessun CRT long
```

Il key level preso deve appartenere a un timeframe **strettamente superiore** a
quello su cui si forma il CRT (DEF-30). Un key level mensile abilita trigger da
`TF_1W` in giù; un key level settimanale abilita trigger da `TF_1D` in giù.

---

## 3. L'ingresso

### SETUP-03 — L'ingresso è sempre sulla candela N3

```
SE  il CRT è FORMATO (SETUP-02A o SETUP-02B)
AND la direzione coincide con bias_comando (SETUP-06)
AND il timeframe del CRT è ammesso da DEF-30
AND nessun filtro di 02_contesto.md è attivo
AND nessun limite di 05_rischio.md è raggiunto
ALLORA invia ordine a mercato all'apertura di N3
ALTRIMENTI nessuna azione
```

**Non esistono due tipi di ingresso.** Esiste un solo ingresso, sulla candela
`N3`, applicato a timeframe diversi. Quella che gli appunti chiamano "entrata
sulla seconda candela" è l'ingresso su `N3` di un timeframe inferiore, che cade
temporalmente dentro la candela `N2` del timeframe superiore.

```
Entrare su N3 di TF_H1  anticipa  la candela N2 di TF_H4
Entrare su N3 di TF_H4  anticipa  la candela N2 di TF_1D
Entrare su N3 di TF_1D  anticipa  la candela N2 di TF_1W
```

L'ingresso su `N3` del timeframe più basso offre un rapporto rischio/rendimento
maggiore e meno conferme. L'ingresso su `N3` del timeframe più alto offre più
conferme e un rapporto minore.

### SETUP-04 — Immediatezza dell'ingresso

```
SE il CRT è FORMATO e tutte le condizioni di SETUP-03 sono soddisfatte
ALLORA l'ordine si invia all'apertura di N3, senza attese
ALTRIMENTI il setup decade
```

Un CRT non eseguito all'apertura di `N3` non è più eseguibile. Non esiste
validità residua su candele successive.

**Momento di esecuzione.** Per DEF-32 il dato di chiusura del future arriva
fino a 10 minuti dopo la chiusura del periodo. L'ordine parte all'arrivo del
dato confermato, non al timestamp teorico.

---

## 4. Allineamento dei timeframe

### SETUP-05 — Condizione di allineamento

Due timeframe sono allineati quando entrambe le condizioni sono vere:

```
SE  bias del TF_A == bias del TF_B                    (DEF-16)
AND entrambi presentano un CRT nella stessa direzione (SETUP-02)
ALLORA TF_A e TF_B sono ALLINEATI
ALTRIMENTI non sono allineati
```

**Numero minimo.**

**Regola dei due timeframe superiori.** Per operare su un timeframe, i **due
timeframe immediatamente superiori** devono aver prodotto lo sbilanciamento di
un key level nella stessa direzione.

```
SE  TF_trigger è il timeframe su cui si cerca il CRT
AND i due timeframe immediatamente superiori nella gerarchia di DEF-01 hanno
    entrambi sbilanciato un key level nella direzione dell'operazione
ALLORA la condizione di allineamento è soddisfatta
ALTRIMENTI nessun ingresso su TF_trigger
```

| TF del trigger | Devono aver sbilanciato |
|---|---|
| `TF_H1` | `TF_H4` e `TF_1D` |
| `TF_H4` | `TF_1D` e `TF_1W` |
| `TF_1D` | `TF_1W` e `TF_1M` |
| `TF_1W` | `TF_1M` e `TF_3M` |
| `TF_1M` | `TF_3M` e `TF_6M` |

`TF_H12` e `TF_H6` non compaiono: servono solo ai gap (DEF-31) e non sono
timeframe di allineamento.

**La catena non si spezza.**

```
SE un timeframe intermedio non è allineato
ALLORA il CRT già formato su un timeframe inferiore NON viene invalidato
ALTRIMENTI nessun effetto
```

Esempio conforme: key level `TF_1W` preso, CRT formato su `TF_H4`, `TF_1D` non
conferma. Il CRT `TF_H4` resta valido. Se successivamente `TF_1W` conferma, la
sequenza è regolare.

---

## 5. Bias di comando

### SETUP-06 — Determinazione di bias_comando

```
Passo 1 — Scorri i timeframe in questo ordine esatto:
          TF_12M, TF_6M, TF_3M, TF_1M, TF_1W, TF_1D
Passo 2 — Fermati al PRIMO timeframe che soddisfa entrambe:
          a) bias_TF diversa da NESSUNA
          b) il target associato non è RAGGIUNTO (DEF-29)
Passo 3 — bias_comando = bias di quel timeframe
          tf_comando    = quel timeframe
Passo 4 — SE nessun timeframe soddisfa le condizioni
          ALLORA bias_comando = NESSUNA, si applica PRIN-99
```

### SETUP-07 — Divieto di reversal

```
SE  bias_comando è definita
AND il target di tf_comando non è RAGGIUNTO
ALLORA sono ammessi esclusivamente ingressi in direzione bias_comando
ALTRIMENTI si riesegue SETUP-06
```

Un segnale contrario a `bias_comando` non viene mai eseguito, su nessun
timeframe, nemmeno se il CRT è formato correttamente e nemmeno se timeframe
intermedi indicano la direzione opposta.

### SETUP-08 — Reversal dopo il target

```
SE  il target di tf_comando è RAGGIUNTO
ALLORA si riesegue SETUP-06 e si ricalcola bias_comando
       nella nuova direzione sono ammessi gli ingressi ordinari (SETUP-03)
```

Il reversal richiede le stesse condizioni di qualsiasi altro ingresso: un key
level preso nella nuova direzione e un CRT formato (SETUP-00). Il timeframe su
cui si cerca il setup è inferiore a quello del key level o del gap che ha
generato il contesto (DEF-30).

**Chiusura delle posizioni.**

```
SE il target di tf_comando è RAGGIUNTO
ALLORA chiudi a mercato tutte le posizioni aperte nella direzione della
       vecchia bias_comando
ALTRIMENTI le posizioni restano aperte
```

Il target di `tf_comando` era il bersaglio dichiarato dell'operatività: una
volta raggiunto, le posizioni che lo inseguivano non hanno più ragione di
esistere.

---

## 6. Gap

### SETUP-09 — Ingresso su gap

Si applica quando il prezzo interagisce con una `zona_gap` di timeframe
inferiore a quello del gap target (DEF-15bis).

```
SE  gap_fase == 3                       (DEF-43, liquidazione)
AND si forma un CRT nella direzione della bias su un timeframe ammesso
ALLORA si applica SETUP-03
ALTRIMENTI nessun ingresso
```

Le fasi 1 e 2 non sono operative. La fase 3 senza CRT non produce ordini: lo
sbilanciamento dell'estremo della fase 1, da solo, non è un segnale.

`divergenza_rsi` (DEF-44) viene registrata ma non modifica la decisione.

### SETUP-10 — Doppio ingresso in presenza di gap

```
SE  esiste un gap attivo su TF_gap
AND il CRT si forma su TF_gap o su un timeframe inferiore
ALLORA sono ammessi due ingressi, con il rischio diviso a metà (RISK-04)
ALTRIMENTI l'ingresso è unico, con rischio pieno
```

Per i gap il CRT può formarsi **anche sullo stesso timeframe del gap**. Per i
key level invece il CRT deve stare su un timeframe strettamente inferiore
(SETUP-02). Sono due regole diverse e non vanno confuse.

Esempio conforme: gap su `TF_1W`, CRT ammesso su `TF_1W`, `TF_1D`, `TF_H12`,
`TF_H6`, `TF_H4`, `TF_H1`.

**Stop dei due ingressi.**

```
Ingresso ancorato al CRT   → stop_aggressivo   (estremo di N2)
Ingresso ancorato al gap   → stop_conservativo (estremo della zona_gap)
```

### SETUP-11 — Nuovo setup dopo uno stop

```
SE una posizione è stata chiusa in stop
AND successivamente un timeframe superiore produce un nuovo CRT valido
ALLORA il nuovo ingresso è ammesso
ALTRIMENTI nessuna azione
```

Lo stop su un timeframe non preclude l'ingresso su un timeframe superiore. Un
ingresso anticipato su `TF_H1` che va in stop non impedisce l'ingresso su `N3`
di `TF_1D` se il mercato lo ripropone.

---

## 7. Stop e target

### SETUP-12 — Stop loss

```
SE il CRT non è a supporto di un gap
ALLORA stop = stop_aggressivo

SE il CRT è a supporto di un gap
ALLORA sono ammessi entrambi i livelli, uno per ciascuno dei due ingressi
       di SETUP-10
```

```
stop_aggressivo   short: high[N2]      long: low[N2]
stop_conservativo short: bordo esterno superiore della zona_gap
                  long:  bordo esterno inferiore della zona_gap
```

Per RISK-12 lo stop è sorvegliato sul future e la chiusura avviene a mercato
sul CFD. Non esiste alcun ordine pendente presso il broker.

### SETUP-13 — Take profit

```
TP1 = KL_50 della candela N1 del timeframe SU CUI È NATO IL CRT
      (50% del range di N1, DEF-36)
```

```
SE il prezzo raggiunge TP1
ALLORA chiudi il 25% della posizione
       sposta lo stop del restante 75% a break even (prezzo di ingresso)
ALTRIMENTI la posizione resta invariata
```

Il restante 75% non ha ulteriori parziali: viene chiuso interamente al target
finale.

### SETUP-14 — Target finale ed estensione progressiva

Il target del 75% residuo è il key level del timeframe più alto disponibile
nella direzione dell'operazione.

```
Alla chiusura di ogni candela di un timeframe superiore a quello del CRT:
SE  quel timeframe conferma il pattern nella stessa direzione
ALLORA target_finale = KL di quel timeframe nella direzione dell'operazione
ALTRIMENTI target_finale resta invariato
```

L'estensione è progressiva e a senso unico: il target si sposta solo verso
l'alto nella gerarchia dei timeframe, mai indietro.

**Scelta tra key level e gap sullo stesso timeframe.** Quando su un timeframe
esistono sia un key level sia un gap nella direzione dell'operazione, la scelta
non è meccanica: vedi GIUD-01.

Esempio conforme: CRT su `TF_H4`, ingresso short. Target iniziale sul key level
`TF_H4`. Alla chiusura di `TF_1D`, se il giornaliero conferma il pattern, il
target si estende al minimo `TF_1D`. Se poi `TF_1W` conferma, si estende al
minimo `TF_1W`, e così via fino al gap di `tf_comando`.

---

## 8. Condizioni che vietano l'ingresso

### SETUP-15 — Esclusioni

Nessun ordine viene inviato se anche una sola di queste è vera:

```
- nessun key level è stato preso (SETUP-00)
- bias_comando è NESSUNA
- la direzione del CRT è opposta a bias_comando
- il timeframe del CRT non è inferiore a quello del key level preso
- meno di 2 timeframe sono allineati (SETUP-05)
- mitigazione_attesa è NON_DETERMINATA su un ingresso da gap (DEF-42)
- sono già aperte 4 posizioni sullo strumento (RISK-06)
- un limite di 05_rischio.md è raggiunto
- si è dentro finestra_blocco per news 3 stelle (RISK-13)
- un dato del vocabolario è mancante o incoerente
```

In tutti questi casi si applica PRIN-99: non operare, senza giustificazione.

### SETUP-16 — Setup non eseguito per limite di rischio

```
SE un setup si presenta mentre un limite di 05_rischio.md è attivo
ALLORA il setup NON viene recuperato quando il limite si azzera
ALTRIMENTI nessun effetto
```

Un nuovo setup che si presenti in una giornata successiva è valutato
normalmente, come setup nuovo.

### SETUP-17 — Cambio di bias su posizione aperta

```
SE  una posizione è aperta
AND bias_comando cambia in direzione opposta a quella della posizione
ALLORA sposta lo stop a break even
ALTRIMENTI la posizione resta invariata
```

La posizione non viene chiusa: viene protetta.

### SETUP-18 — Direzioni opposte su strumenti diversi

Sono ammesse posizioni in direzioni opposte su strumenti diversi
contemporaneamente. Ogni strumento è valutato indipendentemente.

---

## 9. Punti di giudizio

I punti che non si riducono a numeri sono isolati qui, non nascosti nella prosa.
Risposte chiuse, mai giudizio libero. La categoria C significa sempre
astensione.

### GIUD-01 — Target tra key level e gap vicini

```
DOMANDA: Sul timeframe di riferimento esistono sia un key level sia un gap
         nella direzione dell'operazione. Quale è il target?

RISPOSTE: A = il gap    | B = il key level    | C = ambiguo

DATI DA USARE: distanza_kl_gap, atr del timeframe, mitigazione_attesa (DEF-42)

CRITERIO DICHIARATO:
  Se key level e gap sono vicini tra loro, il prezzo tende a puntare al gap
  e il target è il gap.
  Se sono distanti, il prezzo può invertire alla presa del key level: in tal
  caso valgono le regole del gap, cioè conta se la terza candela accetta o
  rifiuta (DEF-42).

REGOLA DI USCITA: se C, il target resta al key level e non si estende al gap.

ESEMPI: vedi 07_casi.md — da produrre, minimo 10 per categoria
```

> **APERTO — vedi PA-44.** "Vicini" e "distanti" non hanno ancora una soglia.
> Serve un numero, espresso in multipli di ATR del timeframe di riferimento
> oppure in percentuale del range della candela N1.

---

## 10. Punti aperti

| ID | Punto aperto | Priorità |
|---|---|---|
| PA-40 | Allineamento | CHIUSO in v0.3 (SETUP-05): i due TF immediatamente superiori |
| PA-41 | Chiusura posizioni al target | CHIUSO in v0.3 (SETUP-08): chiusura a mercato |
| PA-42 | CRT a supporto di gap | CHIUSO in v0.3 (SETUP-10): CRT su TF del gap o inferiore |
| PA-43 | Stop del doppio ingresso | CHIUSO in v0.3 (SETUP-10) |
| PA-44 | Soglia numerica di "vicini" e "distanti" in GIUD-01 | ALTA |
