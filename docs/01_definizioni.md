# 01_definizioni.md

Versione: 1.9 — sciolti i punti aperti di docs/DECISIONI-2026-09-03.md
Data: 2026-08-11
Stato: CHIUSO per tutto ciò che compete a questo file. I punti residui in
sezione 9 appartengono ad altri documenti.

Fuso orario di riferimento per tutto il documento: **UTC**.
Ogni orario citato in qualsiasi file della strategia è espresso in UTC.

ID ritirati e mai riutilizzabili: `DEF-05`, `DEF-06`, `DEF-07`, `DEF-08`
(posizione della chiusura nel range). Ritirati in v0.2 perché la bias non
dipende da dove la candela chiude dentro il proprio range, ma da dove chiude
rispetto agli estremi della candela precedente.

---

## 1. Timeframe

### DEF-01 — Timeframe ammessi e nomenclatura

| Nome | Periodo | Ruolo |
|---|---|---|
| `TF_12M` | 12 mesi | bias |
| `TF_6M` | 6 mesi | bias |
| `TF_3M` | 3 mesi | bias |
| `TF_1M` | 1 mese | bias |
| `TF_1W` | 1 settimana | bias |
| `TF_1D` | 1 giorno | bias ed esecuzione |
| `TF_H12` | 12 ore | solo gap |
| `TF_H6` | 6 ore | solo gap |
| `TF_H4` | 4 ore | esecuzione |
| `TF_H1` | 1 ora | esecuzione |

Ordine gerarchico completo, dal più alto al più basso:
`TF_12M > TF_6M > TF_3M > TF_1M > TF_1W > TF_1D > TF_H12 > TF_H6 > TF_H4 > TF_H1`

Il timeframe su cui è ammessa la ricerca dell'ingresso non è fisso: dipende dal
timeframe del gap attivo. Vedi PA-09.

Nessun altro timeframe può essere citato da nessuna regola della strategia.

Esiste **una sola** gerarchia, quella completa qui sopra. La versione a otto
timeframe presente fino alla v1.8 era un residuo precedente all'introduzione di
`TF_H12` e `TF_H6`, ed è stata rimossa (REV-10).

`TF_H12` e `TF_H6` restano esclusi dall'**allineamento** per regola propria di
SETUP-05, che è cosa diversa dalla gerarchia.

### DEF-45 — Calcolo e sorveglianza

Il sistema compie due attività di natura diversa, e il vincolo delle candele
chiuse si applica solo alla prima.

```
CALCOLO      Determinare bias, gap, key level, CRT, target e livelli di stop.
             Usa ESCLUSIVAMENTE candele chiuse (DEF-02, PRIN-11, ESCL-13).
             Nessun calcolo avviene mai su una candela in formazione.

SORVEGLIANZA Verificare se un livello GIÀ FISSATO da un calcolo precedente
             è stato toccato dal prezzo.
             Usa il prezzo scambiato, in continuo.
```

La sorveglianza non produce mai un livello nuovo: verifica soltanto il
raggiungimento di livelli calcolati su candele chiuse. Per questo non viola il
vincolo.

Regole di sola sorveglianza: DEF-27 (livello consumato), DEF-29 (target
raggiunto), DEF-34, RISK-12, GEST-04 (TP1 e break even), GEST-11, e le
**fasi 1, 2 e 3 di DEF-43** (interazione del prezzo con zona_gap ed
estremo_fase1). La zona e l'estremo sono livelli già fissati da un calcolo su
candele chiuse: verificarne il tocco rientra nella definizione di sorveglianza.

La **fase 4 di DEF-43 è calcolo**: richiede un CRT formato, che si valuta solo
su candele chiuse.

Regole di solo calcolo: tutte le altre.

**DEF-38 appartiene al calcolo.** La presa di un key level si conferma
esclusivamente **alla chiusura di candela**, non sul prezzo scambiato. Uno
sfioramento intraday che non trova conferma alla chiusura non è una presa e non
abilita alcuna ricerca di setup.

### DEF-02 — Candela chiusa e notazione

Una candela è chiusa quando l'orario corrente è maggiore o uguale all'orario di
fine del suo periodo.

Ogni regola della strategia usa **esclusivamente candele chiuse**.
La candela in formazione non viene mai valutata da nessuna regola.

Notazione, per un dato timeframe:

- `C0` = ultima candela chiusa
- `C1` = candela chiusa precedente a `C0`
- `C2` = candela chiusa precedente a `C1`

### DEF-03 — Riferimento temporale delle candele

Il sistema usa due fusi distinti, che non vanno confusi:

```
fuso_analisi     = sessione dell'exchange CME/COMEX, tipo ETH
                   (Electronic Trading Hours, sessione elettronica completa)
fuso_esecuzione  = server FP Markets, MT5
                   (UTC+2 in ora solare, UTC+3 in ora legale)
```

**Costruzione delle candele.** Tutte le candele di analisi sono costruite sulla
sessione ETH dell'exchange. Il fuso di visualizzazione del grafico
(Europa/Roma) non influisce sui confini delle candele: cambia solo le etichette
dell'asse temporale. Il giorno di contrattazione del future comincia alle 18:00
di New York del giorno solare precedente.

**Conseguenza vincolante.** La candela `TF_1D` del future non coincide con la
giornata solare né con la candela giornaliera del CFD. Nessuna regola può
confrontare una candela del future con una candela del CFD.

**Disallineamento dell'ora legale.** Stati Uniti ed Europa cambiano l'ora legale
in date diverse. Nelle settimane di disallineamento lo scarto tra
`fuso_analisi` e `fuso_esecuzione` varia di un'ora. Le candele non ne
risentono. Ogni orario operativo scritto in qualsiasi file della strategia va
espresso in `fuso_esecuzione` e mai in ora locale.

---

## 2. Misure di base sulla candela

### DEF-04 — Range della candela

```
range = high - low
```

SE `range == 0`
ALLORA il dato è considerato incoerente: si applica PRIN-99 (astensione)
ALTRIMENTI il range è utilizzabile

### DEF-09 — Inside bar

Su un dato timeframe:

SE `high[C0] <= high[C1]` AND `low[C0] >= low[C1]`
ALLORA `C0` è una `INSIDE_BAR`
ALTRIMENTI `C0` non è una `INSIDE_BAR`

Il confronto usa i valori esatti. Nessuna tolleranza.

---

## 3. Gap

Il gap è un pattern di **tre candele chiuse consecutive** sullo stesso
timeframe. Per un dato timeframe:

- `P1` = la più vecchia delle tre candele
- `P2` = la candela centrale
- `P3` = la più recente delle tre

### DEF-10 — Gap rialzista

SE `low[P3] > high[P1]`
ALLORA esiste un gap rialzista con:
```
zona_gap    = [ high[P1] , low[P3] ]
livello_inv = low[P1]
```
ALTRIMENTI non esiste gap rialzista su quelle tre candele

### DEF-11 — Gap ribassista

SE `high[P3] < low[P1]`
ALLORA esiste un gap ribassista con:
```
zona_gap    = [ high[P3] , low[P1] ]
livello_inv = high[P1]
```
ALTRIMENTI non esiste gap ribassista su quelle tre candele

### DEF-12 — Distinzione tra zona e livello di invalidazione

`zona_gap` e `livello_inv` sono due grandezze diverse.

- `zona_gap` è l'area di interesse operativo
- `livello_inv` è il prezzo la cui violazione annulla il gap (DEF-14)

Per un gap rialzista `livello_inv` è **sotto** il bordo inferiore della zona.
Per un gap ribassista `livello_inv` è **sopra** il bordo superiore della zona.

### DEF-13 — Gap attivo

Per ciascuna direzione esiste al massimo **un solo** gap attivo alla volta.

Selezione del gap attivo rialzista (a specchio per il ribassista):

```
Passo 1 — Scorri i timeframe in questo ordine esatto:
          TF_12M, TF_6M, TF_3M, TF_1M, TF_1W, TF_1D, TF_H12, TF_H6
          (TF_H12 e TF_H6 inclusi per DEF-31; corretto in v1.9, REV-15)
Passo 2 — Fermati al PRIMO timeframe in cui esiste almeno un gap rialzista
          non invalidato secondo DEF-14
Passo 3 — SE su quel timeframe esiste più di un gap rialzista non invalidato
          ALLORA seleziona quello formato più di recente
          ALTRIMENTI seleziona l'unico presente
Passo 4 — SE nessun timeframe della lista contiene un gap rialzista non
          invalidato
          ALLORA gap_attivo_long = NESSUNO
```

Il timeframe più alto vince sempre sul timeframe più basso.
Il criterio "più recente" si applica **solo** a parità di timeframe.

### DEF-14 — Invalidazione di un gap

L'invalidazione si verifica **sullo stesso timeframe su cui il gap si è
formato**. Chiusure su timeframe diversi non invalidano il gap.

Gap rialzista:
SE esiste una candela chiusa, sul timeframe del gap, con `close < livello_inv`
ALLORA il gap è `INVALIDATO`
ALTRIMENTI il gap resta `VALIDO`

Gap ribassista:
SE esiste una candela chiusa, sul timeframe del gap, con `close > livello_inv`
ALLORA il gap è `INVALIDATO`
ALTRIMENTI il gap resta `VALIDO`

1. Le ombre non invalidano mai un gap. Conta esclusivamente `close`.
2. Un gap `INVALIDATO` non torna mai `VALIDO`, in nessuna circostanza.

### DEF-15 — Ruolo del gap

- Il gap attivo sul timeframe più alto in cui esiste definisce il `target`
  direzionale (vedi PA-04)
- I gap sui timeframe inferiori a quello del gap attivo definiscono le zone di
  reazione in cui cercare l'ingresso

Nessuna regola può usare un gap con ruolo diverso da quello qui assegnato.

---

## 4. Accettazione e rifiuto

### DEF-19 — Livello di riferimento

Il livello di riferimento per la valutazione di `C0` è costituito dagli estremi
della candela precedente sullo stesso timeframe, **ombre incluse**:

```
livello_sup = high[C1]
livello_inf = low[C1]
```

Nessuna tolleranza e nessuna soglia minima di superamento: il superamento è
verificato con confronto stretto sui prezzi. Un solo tick oltre il livello
conta come superamento.

### DEF-20 — Accettazione

Accettazione a rialzo:
SE `close[C0] > livello_sup`
ALLORA `C0` è `ACCETTAZIONE_RIALZO`
ALTRIMENTI non è `ACCETTAZIONE_RIALZO`

Accettazione a ribasso:
SE `close[C0] < livello_inf`
ALLORA `C0` è `ACCETTAZIONE_RIBASSO`
ALTRIMENTI non è `ACCETTAZIONE_RIBASSO`

### DEF-21 — Rifiuto

Definita nella sezione successiva, insieme a corpo e ombre (DEF-39).
La versione originaria, priva della condizione sulla spike, è ritirata.

### DEF-39 — Corpo e ombre

```
corpo     = |close - open|
ombra_sup = high - max(open, close)
ombra_inf = min(open, close) - low
```

### DEF-21 — Rifiuto

Questa definizione sostituisce la versione precedente di DEF-21.

Il **rifiuto forte** richiede due condizioni simultanee: la mancata accettazione
del livello e una spike prevalente sul corpo. Il **rifiuto semplice** richiede
la sola mancata accettazione, senza alcuna soglia sulla spike.

La formulazione precedente attribuiva a entrambi i gradi la condizione sulla
spike, che appartiene al solo grado forte. Corretto in v1.9 (PA-31, REV-08):
DEF-16 passi 4 e 5 usano il rifiuto semplice, come scritto nella sua
definizione.

Esistono **due gradi** di rifiuto, con scopi diversi. Non sono
interscambiabili: usare il grado sbagliato cambia il numero di segnali.

**Rifiuto semplice** — usato per determinare la bias (DEF-16).

Rialzo:
```
SE  high[C0] > livello_sup
AND close[C0] <= livello_sup
AND close[C0] < close[C1]
ALLORA C0 è RIFIUTO_RIALZO
ALTRIMENTI non è RIFIUTO_RIALZO
```

Ribasso:
```
SE  low[C0] < livello_inf
AND close[C0] >= livello_inf
AND close[C0] > close[C1]
ALLORA C0 è RIFIUTO_RIBASSO
ALTRIMENTI non è RIFIUTO_RIBASSO
```

**Rifiuto forte** — usato per il CRT (SETUP-01) e per l'aspettativa di
mitigazione del gap (DEF-42). Richiede il rifiuto semplice più la prevalenza
della spike sul corpo.

Rialzo:
```
SE  C0 è RIFIUTO_RIALZO
AND ombra_sup[C0] > 0.5 × corpo[C0]
ALLORA C0 è RIFIUTO_FORTE_RIALZO
ALTRIMENTI non è RIFIUTO_FORTE_RIALZO
```

Ribasso:
```
SE  C0 è RIFIUTO_RIBASSO
AND ombra_inf[C0] > 0.5 × corpo[C0]
ALLORA C0 è RIFIUTO_FORTE_RIBASSO
ALTRIMENTI non è RIFIUTO_FORTE_RIBASSO
```

Il superamento del livello non ha soglia minima: un tick oltre è sufficiente.

SE `corpo[C0] == 0`
ALLORA la condizione sulla spike è soddisfatta da qualsiasi ombra maggiore di
       zero
ALTRIMENTI si applica il confronto numerico

### DEF-40 — Candela confluente al trend

Confluente ribassista:
```
SE  close[C0] < open[C0]
AND corpo[C0] > ombra_inf[C0]
AND close[C0] < low[C1]
ALLORA C0 è CONFLUENTE_RIBASSO
ALTRIMENTI non è CONFLUENTE_RIBASSO
```

Confluente rialzista:
```
SE  close[C0] > open[C0]
AND corpo[C0] > ombra_sup[C0]
AND close[C0] > high[C1]
ALLORA C0 è CONFLUENTE_RIALZO
ALTRIMENTI non è CONFLUENTE_RIALZO
```

### DEF-41 — Candela di indecisione

Corrisponde al doji della letteratura tecnica: apertura e chiusura
praticamente coincidenti, con ombre su entrambi i lati.

```
SE  corpo[C0] <= 0.05 × range[C0]
AND min(ombra_sup[C0], ombra_inf[C0]) >= 0.40 × max(ombra_sup[C0], ombra_inf[C0])
ALLORA C0 è INDECISIONE
ALTRIMENTI non è INDECISIONE
```

La prima condizione impone il corpo minuscolo tipico del doji. La seconda
esclude le figure sbilanciate da un lato: un martello o una shooting star hanno
il corpo piccolo ma una sola ombra lunga, e non sono candele di indecisione.

**Grado rafforzato.** La mancata accettazione della candela precedente non è
obbligatoria, ma aumenta la validità della figura ai fini del gap e del CRT.

```
SE  C0 è INDECISIONE
AND close[C0] <= high[C1]
AND close[C0] >= low[C1]
ALLORA C0 è INDECISIONE_FORTE
ALTRIMENTI non è INDECISIONE_FORTE
```

### DEF-43 — Le quattro fasi del gap

Ogni interazione del prezzo con una `zona_gap` segue questa sequenza. Il campo
`gap_fase` registra la fase corrente.

Caso di zona sopra il prezzo, bias short (a specchio per il caso opposto):

```
FASE 1 — AGGRESSIONE
SE il prezzo scambiato entra in zona_gap
ALLORA gap_fase = 1
       estremo_fase1 = massimo prezzo raggiunto dentro la zona

FASE 2 — AUTOMATIC REACTION
SE gap_fase == 1
AND il prezzo scambiato esce da zona_gap nella direzione contraria
ALLORA gap_fase = 2

FASE 3 — LIQUIDAZIONE
SE gap_fase == 2
AND il prezzo scambiato rientra in zona_gap
AND il prezzo supera estremo_fase1
ALLORA gap_fase = 3

FASE 4 — CONTINUAZIONE
SE gap_fase == 3
AND si forma un pattern CRT nella direzione della bias (SETUP-01)
ALLORA gap_fase = 4 e l'ingresso è ammesso
ALTRIMENTI nessun ingresso: la fase 3 senza CRT non è operativa
```

`estremo_fase1` si aggiorna in continuo durante la fase 1 e si congela
all'uscita dalla zona.

La fase 1 non è mai operativa: è il movimento che gli appunti definiscono fake.
La fase 3 è la sola in cui si cerca l'ingresso, e solo se accompagnata da un
setup. Lo sbilanciamento dell'estremo della fase 1 senza CRT non produce
alcun ordine.

### DEF-44 — Divergenza RSI

Si applica **esclusivamente** ai gap. Nessun'altra regola della strategia usa
l'RSI.

```
rsi_periodo    = 14
rsi_timeframe  = timeframe del gap
```

I due punti da confrontare non vanno cercati sul grafico: sono determinati dal
modello delle fasi (DEF-43).

```
punto_A = estremo_fase1        (estremo raggiunto in fase 1)
punto_B = estremo di fase 3    (estremo che rompe estremo_fase1)
```

Divergenza ribassista, gap con bias short:
```
SE  gap_fase == 3
AND prezzo[punto_B] > prezzo[punto_A]
AND rsi[punto_B] < rsi[punto_A]
ALLORA divergenza_rsi = RIBASSISTA
ALTRIMENTI divergenza_rsi = NESSUNA
```

Divergenza rialzista, gap con bias long:
```
SE  gap_fase == 3
AND prezzo[punto_B] < prezzo[punto_A]
AND rsi[punto_B] > rsi[punto_A]
ALLORA divergenza_rsi = RIALZISTA
ALTRIMENTI divergenza_rsi = NESSUNA
```

SE la fase 3 produce più estremi successivi che rompono `estremo_fase1`
ALLORA il confronto si ripete per ciascuno di essi, usando sempre `punto_A`
       come riferimento fisso
ALTRIMENTI si valuta il solo estremo disponibile

**Uso.** La divergenza non è condizione necessaria per l'ingresso: un setup
valido in fase 3 si esegue anche senza divergenza. Il campo `divergenza_rsi`
viene registrato per ogni operazione a fini statistici, così da poter misurare
a posteriori se i trade con divergenza si comportino diversamente dagli altri.

> **APERTO — vedi PA-39.** Va deciso se la divergenza debba restare un dato
> solo statistico oppure diventare operativa, per esempio aumentando la size o
> escludendo gli ingressi che ne sono privi. Allo stato attuale non modifica
> alcuna decisione del bot.

### DEF-42 — Aspettativa di mitigazione del gap

Determina se il gap formato con `P3 = C0` è atteso in mitigazione a breve.

```
SE C0 è CONFLUENTE al trend nella direzione del gap (DEF-40)
ALLORA mitigazione_attesa = false
       il gap tende a restare non mitigato e a promuoversi su TF superiore

ALTRIMENTI SE C0 è RIFIUTO_FORTE (DEF-21)
        OR C0 è INDECISIONE (DEF-41)
        OR C0 è INSIDE_BAR (DEF-09)
ALLORA mitigazione_attesa = true
       il gap tende a essere mitigato, e la direzione riprende dopo

ALTRIMENTI mitigazione_attesa = NON_DETERMINATA
       nessun ingresso è ammesso su quel gap: si applica PRIN-99
```

Il caso `NON_DETERMINATA` non è un errore: è una condizione prevista e comporta
astensione. Un trade saltato costa zero.

---

## 5. Bias

### DEF-16 — Bias di un singolo timeframe

Algoritmo a passi. Si applica il **primo** passo la cui condizione è vera e si
interrompe la valutazione.

```
Passo 1  SE high[C0] > high[C1]
         AND low[C0]  < low[C1]
         AND close[C0] >= low[C1]
         AND close[C0] <= high[C1]
         ALLORA bias_TF = NESSUNA
         (candela che rompe entrambi gli estremi e chiude all'interno:
          rifiuto a rialzo e rifiuto a ribasso sarebbero simultanei)

Passo 2  SE C0 è ACCETTAZIONE_RIALZO (DEF-20)
         ALLORA bias_TF = LONG

Passo 3  SE C0 è ACCETTAZIONE_RIBASSO (DEF-20)
         ALLORA bias_TF = SHORT

Passo 4  SE C0 è RIFIUTO_RIALZO (DEF-21)
         ALLORA bias_TF = SHORT

Passo 5  SE C0 è RIFIUTO_RIBASSO (DEF-21)
         ALLORA bias_TF = LONG

Passo 6  SE C0 è INSIDE_BAR (DEF-09)
         ALLORA applica DEF-23

Passo 7  ALTRIMENTI bias_TF = NESSUNA
```

### DEF-23 — Bias in presenza di inside bar

```
SE C0 è INSIDE_BAR
AND C0 forma un gap rialzista secondo DEF-10 con P3 = C0
ALLORA bias_TF = LONG
       attesa operativa = ritracciamento dentro zona_gap, poi ripresa al rialzo

ALTRIMENTI SE C0 è INSIDE_BAR
AND C0 forma un gap ribassista secondo DEF-11 con P3 = C0
ALLORA bias_TF = SHORT
       attesa operativa = ritracciamento dentro zona_gap, poi ripresa al ribasso

ALTRIMENTI SE C0 è INSIDE_BAR
AND C0 non forma alcun gap
ALLORA applica DEF-24 (bias ereditata)
```

### DEF-24 — Bias ereditata

SE si applica l'eredità (DEF-23)
ALLORA `bias_TF` assume lo stesso valore che aveva alla chiusura della candela
       precedente dello stesso timeframe
ALTRIMENTI non si applica

SE non esiste alcun valore precedente di `bias_TF` (avvio del sistema, storico
insufficiente)
ALLORA `bias_TF = NESSUNA`

L'eredità è ricorsiva: una serie consecutiva di inside bar senza gap mantiene
invariata l'ultima bias determinata da una candela non inside.

### DEF-17 — Gerarchia della bias tra timeframe

La bias del timeframe più alto prevale sempre su quella dei timeframe
inferiori.

SE la bias di un timeframe inferiore è opposta a `bias_12M`
ALLORA quel timeframe non produce alcun segnale operativo, e si attende il
       riallineamento
ALTRIMENTI quel timeframe può essere usato per la ricerca dell'ingresso

Nessuna operazione di reversal è ammessa in nessuna circostanza mentre
`bias_12M` è definita e il suo target non è stato raggiunto.

### DEF-18 — Durata della bias

`bias_12M` viene calcolata alla chiusura della candela `TF_12M` — che segue i
confini di sessione ETH dell'exchange (DEF-03), non il giorno solare — e resta
invariata fino alla chiusura della candela annuale successiva.

La parentesi "31 dicembre, 24:00 UTC" presente fino alla v1.8 è stata rimossa:
contraddiceva DEF-03, che si dichiara conseguenza vincolante (REV-16).

Lo stesso principio vale per ogni altro timeframe: la bias di un timeframe
cambia solo alla chiusura di una sua candela.

### DEF-30 — Timeframe ammessi per l'ingresso

Il timeframe su cui è ammessa la ricerca dell'ingresso dipende dal timeframe
del gap attivo (DEF-13):

**Regola unica.** Il trigger si cerca su qualsiasi timeframe **strettamente
inferiore** a quello del riferimento, secondo la gerarchia di DEF-01.

```
TF_trigger ammesso  SE  TF_trigger < TF_riferimento
```

dove `TF_riferimento` è il timeframe del gap attivo (DEF-13) oppure il
timeframe del key level preso (DEF-38), a seconda di quale abbia generato il
contesto operativo.

Esempi conformi alla regola:

| TF di riferimento | TF ammessi per il trigger |
|---|---|
| `TF_1M` | `TF_1W`, `TF_1D`, `TF_H12`, `TF_H6`, `TF_H4`, `TF_H1` |
| `TF_1W` | `TF_1D`, `TF_H12`, `TF_H6`, `TF_H4`, `TF_H1` |
| `TF_1D` | `TF_H12`, `TF_H6`, `TF_H4`, `TF_H1` |

SE un segnale di ingresso si forma su un timeframe non elencato nella riga
corrispondente al gap attivo
ALLORA il segnale viene ignorato
ALTRIMENTI il segnale è valutabile

SE `gap_attivo` è NESSUNO
ALLORA nessun timeframe è ammesso per l'ingresso, si applica PRIN-99

### DEF-31 — Timeframe di soli gap

Su `TF_H12` e `TF_H6` si applicano esclusivamente DEF-10 e DEF-11 (formazione
del gap). DEF-16 non si applica: su questi timeframe non si calcola alcuna bias
da accettazione o rifiuto.

Questi due timeframe entrano nell'ordine di scansione di DEF-13 (selezione del
gap attivo) nella posizione stabilita dalla gerarchia di DEF-01, subito sotto
`TF_1D`.

**La polarità del gap non determina la bias.** Un gap rialzista non implica
bias LONG, né un gap ribassista implica bias SHORT. Vedi DEF-15.

### DEF-15bis — Ruolo del gap, versione corretta

Questa definizione sostituisce integralmente DEF-15.

**Gap come target.** Il gap attivo sul timeframe più alto in cui esiste
(DEF-13) è un target. La direzione operativa è quella che il prezzo deve
percorrere per raggiungerlo, indipendentemente dalla polarità del gap:

```
SE zona_gap è interamente sotto il prezzo attuale
ALLORA direzione verso il target = SHORT
ALTRIMENTI SE zona_gap è interamente sopra il prezzo attuale
ALLORA direzione verso il target = LONG
ALTRIMENTI il prezzo è già dentro la zona: il gap non è più un target
```

Un gap rialzista situato sotto il prezzo è un target ribassista. Un gap
ribassista situato sopra il prezzo è un target rialzista.

**Gap come zona di reazione.** I gap sui timeframe inferiori a quello del gap
target sono zone in cui cercare l'ingresso. Qui la polarità conta: la zona è
utilizzabile solo se la sua polarità concorda con la bias operativa in corso.

Nessuna regola può usare un gap con un ruolo diverso da quello qui assegnato.

### DEF-32 — Fonte del dato e latenza

Ogni valore di `open`, `high`, `low`, `close` usato da qualsiasi regola della
strategia proviene dal **grafico future**, mai dal CFD.

| Timeframe | Fonte | Momento operativo |
|---|---|---|
| Tutti, da `TF_12M` a `TF_H1` | Future CME | all'apertura di N3, senza ritardo prestabilito |

Corretto in v1.9 (REV-13). La versione precedente indicava il CFD Capital.com
come fonte primaria su `TF_H12`, `TF_H6`, `TF_H4` e `TF_H1`, con conferma del
future. Quel meccanismo è un confronto fra un dato CFD e un dato future, che
ESCL-12 e DEF-03 vietano e che PREC-05 rende prevalente sul resto.

**Conseguenza operativa:** serve il flusso dati CME su tutti i timeframe, non
solo sui più alti. Il CFD di FP Markets resta esclusivamente lo strumento di
esecuzione.

**Revisione in v1.6.** Non esiste un ritardo prestabilito di esecuzione.
L'ingresso avviene all'apertura di `N3`, il prima possibile. Un ritardo di
alcuni minuti è tollerato purché il rapporto rischio/rendimento ricalcolato sui
prezzi effettivi resti pari o superiore a 1,5 (GEST-01, CTX-05). Il valore di
10 minuti resta valido come latenza attesa del solo dato DXY (CTX-06).

Conseguenza vincolante: nessuna regola può assumere l'esecuzione al prezzo di
chiusura della candela. Il momento di valutazione è l'arrivo del dato di
chiusura del future.

**Nessun ritardo prestabilito.** Il paragrafo che imponeva 10 minuti è stato
rimosso in v1.9 (REV-14): contraddiceva la revisione v1.6 di questa stessa
regola e CTX-05. La tollerabilità di un ritardo la stabilisce il rapporto
rischio/rendimento ricalcolato sui prezzi effettivi (GEST-01, CTX-05), non un
limite di tempo. I 10 minuti restano validi per il solo dato DXY (CTX-06).

### DEF-33 — Corrispondenza tra strumento di analisi e strumento di esecuzione

| Esecuzione (CFD, FP Markets) | Analisi (future) | Segno |
|---|---|---|
| — (solo analisi) | `ICEUS` (DXY future) | diretto |
| `EURUSD` | `6E` | diretto |
| `GBPUSD` | `6B` | diretto |
| `AUDUSD` | `6A` | diretto |
| `USDJPY` | `6J` | **invertito** |
| `USDCHF` | `6S` | **invertito** |
| `XAUUSD` | `GC` | diretto |

Il DXY non è uno strumento operativo: serve solo a determinare la direzione
degli strumenti forex (SETUP-08). Simboli di riferimento:

```
dxy_analisi_tf_alti  = ICEUS   (future, per TF_1D e superiori)
dxy_analisi_tf_bassi = CAPITALCOM:DXY  (CFD, per TF_H12 e inferiori,
                                        con conferma ICEUS dopo 10 minuti)
```

Il future DXY è quotato da ICE, non dal CME: richiede un abbonamento dati
distinto da quello CME usato per gli altri strumenti.

Segno `invertito` significa che una bias LONG rilevata sul future corrisponde a
un ordine SELL sul CFD, e viceversa. Il future `6J` quota yen contro dollaro,
`6S` quota franco contro dollaro: entrambi si muovono in direzione opposta alla
coppia CFD corrispondente.

### DEF-34 — Chiusura delle posizioni sul target

Il target (DEF-22) è definito sul prezzo del **future**.

SE il prezzo scambiato del future raggiunge `target_valore`
ALLORA la posizione corrispondente sul CFD viene chiusa a mercato
ALTRIMENTI la posizione resta aperta

Nessun livello viene convertito dal prezzo future al prezzo CFD. I due prezzi
non vengono mai confrontati tra loro.

### DEF-35 — Gap da rollover del contratto

Un gap formatosi in corrispondenza del cambio di contratto future è trattato
come un gap valido a tutti gli effetti. Non esiste alcun filtro per data di
rollover, né alcuna esclusione.

Si applicano integralmente DEF-10, DEF-11, DEF-13 e DEF-14. In particolare, la
rottura della zona secondo DEF-14 invalida il gap e apre la valutazione nella
direzione opposta, esattamente come per qualsiasi altro gap.

Il campo `gap_da_rollover` è registrato per ogni gap a fini statistici. Non è
usato da nessuna regola operativa.

### DEF-36 — Key level

Per ciascun timeframe della lista `TF_12M`, `TF_6M`, `TF_3M`, `TF_1M`, `TF_1W`,
`TF_1D`, calcolati sulla candela chiusa precedente `C1` di quel timeframe:

```
KL_max_TF = high[C1]
KL_min_TF = low[C1]
KL_50_TF  = (high[C1] + low[C1]) / 2
```

**Il livello del 50% è calcolabile su qualsiasi candela e qualsiasi
timeframe.** Quando `TP1` (GEST-07) richiede il 50% della candela `N1`, si usa:

```
liv_50(candela) = (high[candela] + low[candela]) / 2
```

applicato a `N1` del timeframe su cui è nato il CRT, incluso `TF_H4` e
`TF_H1`. È la stessa formula di `KL_50_TF`, applicata a una candela diversa:
`KL_50_TF` si riferisce a `C1`, `TP1` si riferisce a `N1`. Non sono lo stesso
valore e non vanno confusi.

I key level si ricalcolano alla chiusura di ogni candela del rispettivo
timeframe, e in nessun altro momento.

I key level sono cosa diversa dai livelli strutturali di DEF-25. I livelli
strutturali sono l'insieme di tutti i massimi e minimi entro `lookback` e
servono per il target direzionale globale di DEF-22. I key level sono i tre
valori qui sopra, riferiti alla sola candela precedente, e servono per
l'ingresso **e per il target della singola posizione** (DEF-46, SETUP-14).

Precisato in v1.9 (PA-60): i due target sono distinti e leciti. Quello di
DEF-22 è su livelli strutturali e riguarda `tf_comando`; quello di DEF-46 e
SETUP-14 è su key level e riguarda la posizione aperta.

### DEF-37 — Priorità e assorbimento dei key level

Quando due key level di timeframe diversi coincidono, si considera valido solo
quello del timeframe più alto; quello del timeframe inferiore viene scartato e
non genera segnali propri.

```
SE KL_x su TF_A == KL_y su TF_B    (uguaglianza esatta, nessuna tolleranza)
AND TF_A è più alto di TF_B nella gerarchia di DEF-01
ALLORA KL_y viene scartato
ALTRIMENTI entrambi i key level restano attivi
```

L'uguaglianza esatta è il criterio corretto e non è un caso raro: il minimo di
una candela mensile è, per costruzione, identico al minimo di una delle sue
candele settimanali. Sono lo stesso prezzo, non due prezzi vicini.

### DEF-38 — Presa di un key level

```
Alla chiusura di una candela sul timeframe del key level:

SE high[C0] > KL_max_TF
ALLORA KL_max_TF è PRESO_RIALZO

SE low[C0] < KL_min_TF
ALLORA KL_min_TF è PRESO_RIBASSO

ALTRIMENTI il key level non è preso
```

La presa si conferma **alla chiusura di candela**, mai sul prezzo scambiato
(DEF-45). Un superamento intraday rientrato prima della chiusura non conta: il
key level resta non preso e nessun setup viene cercato.

È la condizione che abilita la ricerca del setup (SETUP-00, SETUP-02).

---

## 6. Target

### DEF-25 — Livello strutturale

Su un dato timeframe:

- ogni `high` di candela chiusa è un **livello strutturale rialzista**
- ogni `low` di candela chiusa è un **livello strutturale ribassista**

Ogni livello strutturale porta con sé il timeframe su cui si è formato. Un
livello formato su `TF_1M` ha priorità su un livello formato su `TF_1W`
(DEF-27).

### DEF-26 — Storico di riferimento

```
lookback = 5 anni solari a ritroso dalla data corrente
```

Nessun livello strutturale formatosi prima di `lookback` è considerato.
Lo stesso `lookback` si applica a tutti i timeframe.

SE un timeframe non dispone di almeno 3 candele chiuse dentro `lookback`
ALLORA quel timeframe non produce né bias né livelli strutturali
ALTRIMENTI il timeframe è utilizzabile

### DEF-27 — Livello consumato

Un livello strutturale rialzista di valore `L`:

SE dopo la sua formazione esiste almeno un prezzo scambiato `>= L`
ALLORA il livello è `CONSUMATO`
ALTRIMENTI il livello è `DISPONIBILE`

A specchio per i livelli ribassisti, con prezzo scambiato `<= L`.

Il consumo si verifica **al tocco**, sul prezzo scambiato, non alla chiusura di
candela. Un livello `CONSUMATO` non torna mai `DISPONIBILE`.

### DEF-28 — Aggiornamento dei livelli

L'insieme dei livelli strutturali di un timeframe si ricalcola alla chiusura di
ogni candela di quel timeframe, e in nessun altro momento.

Frequenza di ricalcolo per timeframe: `TF_12M` una volta l'anno, `TF_6M` due,
`TF_3M` quattro, `TF_1M` dodici, `TF_1W` a ogni chiusura settimanale, `TF_1D` a
ogni chiusura giornaliera, `TF_H4` e `TF_H1` a ogni chiusura del rispettivo
periodo.

### DEF-46 — Target di un timeframe

Ogni timeframe ha un proprio target, distinto dal target direzionale globale di
DEF-22.

```
target_di(TF) = key level del timeframe IMMEDIATAMENTE SUPERIORE a TF,
                nella direzione della bias di TF
```

| Timeframe | Target su |
|---|---|
| `TF_H1` | `TF_H4` |
| `TF_H4` | `TF_1D` |
| `TF_1D` | `TF_1W` |
| `TF_1W` | `TF_1M` |
| `TF_1M` | `TF_3M` |
| `TF_3M` | `TF_6M` |
| `TF_6M` | `TF_12M` |
| `TF_12M` | vedi sotto |

Direzione:
```
bias LONG  → target_di(TF) = KL_max del timeframe superiore
bias SHORT → target_di(TF) = KL_min del timeframe superiore
```

`TF_H12` e `TF_H6` non compaiono: servono solo ai gap (DEF-31).

```
SE TF == TF_12M
ALLORA target_di(TF_12M) = target direzionale globale (DEF-22)
ALTRIMENTI si applica la tabella sopra
```

È questo il valore a cui si riferiscono SETUP-06 e SETUP-08 quando citano "il
target di `tf_comando`".

### DEF-47 — Calcolo della size sul future

Regola che sostituisce il calcolo di RISK-03 nella parte che confrontava
prezzi future e CFD.

```
Passo 1 — Sul FUTURE, calcola la distanza di stop in punti:
          distanza_stop_future = |prezzo_riferimento_future - livello_stop_future|
          dove prezzo_riferimento_future è la chiusura di N2 sul future

Passo 2 — Converti la distanza in rischio percentuale usando il valore punto
          dello strumento CFD:
          size_lotti = (equity × rischio_operazione) / (distanza_stop_future × valore_punto)

Passo 3 — Arrotonda per difetto al passo minimo del broker
```

Nessun prezzo CFD entra nel calcolo della distanza: la distanza è misurata
interamente sul future. Il CFD interviene solo con `valore_punto`, che è un
moltiplicatore monetario e non un prezzo.

Su `USDJPY` e `USDCHF` la distanza si misura sul future `6J` e `6S`, di segno
invertito rispetto al CFD (DEF-33). Il valore assoluto della distanza è
invariante rispetto all'inversione di segno, quindi il calcolo resta valido.

> **APERTO — vedi PA-62.** Il rapporto tra un punto di `6J` e un punto di
> `USDJPY` non è uno a uno: i due strumenti hanno quotazione e moltiplicatore
> diversi. Serve, per ciascuno dei sei strumenti, il fattore di conversione tra
> punto future e punto CFD, da misurare una volta e inserire in tabella.

### DEF-22 — Target direzionale

Caso bias LONG (a specchio per SHORT):

```
Passo 1 — Scorri i timeframe in questo ordine esatto:
          TF_12M, TF_6M, TF_3M, TF_1M, TF_1W, TF_1D, TF_H4, TF_H1
Passo 2 — Fermati al PRIMO timeframe che contiene almeno un livello
          strutturale rialzista DISPONIBILE (DEF-27) di valore superiore
          al prezzo attuale
Passo 3 — Tra i livelli DISPONIBILI di quel timeframe, seleziona quello di
          valore più basso, cioè il più vicino al prezzo attuale
Passo 4 — SE nessun timeframe contiene livelli DISPONIBILI sopra il prezzo
          ALLORA nessun target definito, si applica PRIN-99 (astensione)
```

La ricerca parte sempre da `TF_12M`, indipendentemente dal timeframe del gap
attivo.

### DEF-29 — Raggiungimento del target

SE il prezzo scambiato raggiunge il valore del target
ALLORA il target è `RAGGIUNTO`, il livello diventa `CONSUMATO` (DEF-27), e si
       riesegue DEF-22 per determinare il target successivo
ALTRIMENTI il target resta attivo

Il raggiungimento si verifica al tocco, non alla chiusura di candela.

---

## 7. Vocabolario dati

Ogni regola della strategia può usare esclusivamente i campi elencati qui.
Se una regola richiede un dato assente da questa tabella, quella regola non è
eseguibile.

| Nome campo | Significato | Fonte |
|---|---|---|
| `symbol` | Strumento in analisi | TradingView |
| `gap_fase` | 1, 2, 3 o 4 (DEF-43) | Calcolato dal server |
| `estremo_fase1` | Estremo raggiunto dentro la zona in fase 1 (DEF-43) | Calcolato dal server |
| `tf` | Timeframe della candela valutata (DEF-01) | TradingView |
| `open`, `high`, `low`, `close` | OHLC della candela chiusa `C0` | TradingView |
| `high_c1`, `low_c1` | Estremi della candela `C1` | TradingView |
| `candle_close_time_utc` | Orario di chiusura candela, UTC | TradingView |
| `range` | `high - low` (DEF-04) | Calcolato dal server |
| `is_inside_bar` | true/false (DEF-09) | Calcolato dal server |
| `is_accettazione_rialzo` | true/false (DEF-20) | Calcolato dal server |
| `is_accettazione_ribasso` | true/false (DEF-20) | Calcolato dal server |
| `is_rifiuto_rialzo` | true/false (DEF-21) | Calcolato dal server |
| `is_rifiuto_ribasso` | true/false (DEF-21) | Calcolato dal server |
| `gap_long_tf` | Timeframe del gap attivo rialzista (DEF-13) | Calcolato dal server |
| `gap_long_inf` | Bordo inferiore zona gap rialzista | Calcolato dal server |
| `gap_long_sup` | Bordo superiore zona gap rialzista | Calcolato dal server |
| `gap_long_inv` | Livello di invalidazione gap rialzista (DEF-10) | Calcolato dal server |
| `gap_short_tf` | Timeframe del gap attivo ribassista (DEF-13) | Calcolato dal server |
| `gap_short_inf` | Bordo inferiore zona gap ribassista | Calcolato dal server |
| `gap_short_sup` | Bordo superiore zona gap ribassista | Calcolato dal server |
| `gap_short_inv` | Livello di invalidazione gap ribassista (DEF-11) | Calcolato dal server |
| `gap_da_rollover` | true/false, marcatura statistica (DEF-35) | Calcolato dal server |
| `bias_12M` | LONG / SHORT / NESSUNA | Calcolato dal server |
| `bias_6M`, `bias_3M`, `bias_1M`, `bias_1W`, `bias_1D` | LONG / SHORT / NESSUNA | Calcolato dal server |
| `bias_tf_precedente` | Valore di `bias_TF` alla candela precedente (DEF-24) | Calcolato dal server |
| `target_valore` | Prezzo del target attivo (DEF-22) | Calcolato dal server |
| `target_tf` | Timeframe del livello selezionato come target | Calcolato dal server |
| `target_raggiunto` | true/false (DEF-29) | Calcolato dal server |
| `livelli_long_disponibili` | Elenco livelli rialzisti DISPONIBILI con relativo TF | Calcolato dal server |
| `livelli_short_disponibili` | Elenco livelli ribassisti DISPONIBILI con relativo TF | Calcolato dal server |
| `rsi` | RSI(14) sul timeframe del gap (DEF-44) | Calcolato dal server |
| `divergenza_rsi` | RIBASSISTA / RIALZISTA / NESSUNA (DEF-44) | Calcolato dal server |
| `is_rifiuto_forte_rialzo` | true/false (DEF-21) | Calcolato dal server |
| `is_rifiuto_forte_ribasso` | true/false (DEF-21) | Calcolato dal server |
| `is_indecisione` | true/false (DEF-41) | Calcolato dal server |
| `is_confluente_rialzo` | true/false (DEF-40) | Calcolato dal server |
| `is_confluente_ribasso` | true/false (DEF-40) | Calcolato dal server |
| `mitigazione_attesa` | true / false / NON_DETERMINATA (DEF-42) | Calcolato dal server |
| `gap_fase` | 1 aggressione, 2 reazione, 3 liquidazione, 4 continuazione | Calcolato dal server |
| `dxy_close` | Chiusura DXY sulla candela valutata | TradingView |
| `equity` | Equity attuale del conto | MT5 |
| `valore_punto` | Valore monetario di 1 punto per 1 lotto, per strumento | MT5 |
| `pnl_settimanale` | P&L chiuso della settimana corrente | MT5 |
| `pnl_mensile` | P&L chiuso del mese corrente | MT5 |
| `atr` | ATR(14) sul timeframe indicato, uso esclusivo GIUD-01 | Calcolato dal server |
| `distanza_kl_gap` | Distanza tra key level e bordo del gap (GIUD-01) | Calcolato dal server |
| `pnl_giornaliero` | P&L chiuso della giornata | MT5 |

---

## 8. Rimosso

La sezione "Promemoria di lavoro" è stata rimossa in v1.9 (REV-44). Conteneva
l'universo strumenti, migrato in PRIN-08, e la tabella di direzione dal DXY,
migrata in SETUP-19. Tenerne una seconda copia qui significava lasciarle
divergere.

---

## 9. Punti aperti

| ID | Punto aperto | Stato |
|---|---|---|
| PA-01 | Posizione della chiusura nel range | CHIUSO in v0.2: definizioni ritirate, non servono |
| PA-02 | Definizione numerica di bias su singolo timeframe | CHIUSO in v0.2 (DEF-16, DEF-23, DEF-24) |
| PA-03 | Accettazione e rifiuto | CHIUSO in v0.3. DEF-19/20/21 per gli estremi di candela, DEF-25 per i livelli strutturali |
| PA-04 | Definizione di `target` (DEF-22) e comportamento del sistema una volta raggiunto | CHIUSO in v0.3 (DEF-22, DEF-25/26/27/28/29). Resta da definire in `03_setup.md` quali setup ammettono il reversal dopo il raggiungimento del target 12M |
| PA-05 | Regole proprie di XAUUSD, che non deriva la direzione dal DXY | APERTO — destinazione `03_setup.md` |
| PA-06 | Fusi orari | CHIUSO in v1.0 (DEF-03): candele su sessione ETH exchange, esecuzione su server FP Markets |
| PA-07 | Numero minimo di candele storiche perché un timeframe produca bias valida | CHIUSO in v0.3: `lookback` 5 anni, minimo 3 candele chiuse per timeframe (DEF-26) |
| PA-08 | Simbolo DXY | CHIUSO in v1.4 (DEF-33): ICEUS sui TF alti, CAPITALCOM:DXY sui TF bassi |
| PA-39 | Se la divergenza RSI debba restare statistica o diventare operativa | APERTO |
| PA-56 | Presa del key level | CHIUSO in v1.8 (DEF-38, DEF-45): a candela chiusa |
| PA-57 | Target di un timeframe | CHIUSO in v1.8 (DEF-46) |
| PA-58 | Calcolo della size | CHIUSO in v1.8 (DEF-47): distanza misurata sul future |
| PA-62 | Fattore di conversione tra punto future e punto CFD per ciascuno dei sei strumenti | APERTO — BLOCCANTE |
| PA-59 | ATR in GIUD-01 | CHIUSO in v1.8: eccezione esplicita in ESCL-15, uso come sola unità di misura |
| PA-60 | SETUP-14 usa i key level come target, mentre DEF-36 assegna ai key level l'ingresso e ai livelli strutturali (DEF-25) il target | APERTO |
| PA-09 | Corrispondenza gap → timeframe di ingresso | CHIUSO in v0.3 (DEF-30) |
| PA-10 | Strumento di analisi vs esecuzione | CHIUSO in v0.4 (DEF-32, DEF-33, DEF-34): analisi sempre su future CME, esecuzione su CFD FP Markets, nessuna conversione di prezzo |
| PA-11 | Gestione del rollover dei contratti futures | CHIUSO in v0.5 (DEF-35): trattati come gap normali, nessun filtro |
| PA-12 | Sessione di riferimento del future | CHIUSO in v1.0 (DEF-03): sessione elettronica completa ETH |
| PA-13 | Timeframe di ingresso per gap `TF_H12` e `TF_H6` | CHIUSO in v0.5 (DEF-30) |
| PA-14 | Assenza di stop e target come ordini pendenti sul broker: la protezione dipende interamente dalla disponibilità del server e degli alert. Da affrontare in `05_rischio.md` | APERTO |
| PA-29 | Soglie di DEF-41 (indecisione): confermare 0.10 e 0.40, e decidere se la mancata accettazione sia obbligatoria | APERTO |
| PA-30 | Comportamento con `mitigazione_attesa = NON_DETERMINATA` (DEF-42) | APERTO |
| PA-31 | DEF-16 passo 4 e 5: cosa fa la bias quando una candela spazza un estremo e richiude dentro ma NON supera la soglia spike/corpo di DEF-21 | APERTO — BLOCCANTE |
| PA-15 | Regola di conferma dei correlati: quali future devono essere allineati e con quale criterio prima di un ingresso. Da affrontare in `03_setup.md` | APERTO |
