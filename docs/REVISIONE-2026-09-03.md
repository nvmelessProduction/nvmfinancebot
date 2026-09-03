# Revisione dei documenti — 2026-09-03

> **Chiuso.** Tutti i punti bloccanti elencati qui sono stati sciolti il
> 2026-09-03 su richiesta dell'autore. Le decisioni, con il ragionamento e la
> categoria di ciascuna, stanno in **`docs/DECISIONI-2026-09-03.md`**; sono
> applicate in `core/parametri.py`, dizionario `SCELTE`, e reversibili una per
> una. I documenti di strategia sono stati corretti solo dove si trattava di
> cancellare un residuo, mai di riscrivere una regola.
>
> Due voci erano mie imprecisioni, corrette il 2026-09-03:
> **REV-18** (`CTX-02` la qualificazione per strumento ce l'ha, nel paragrafo
> dopo il blocco di codice: nessun conflitto con `RISK-13`, declassata a
> FORMALE) e **REV-23** (non era una scelta: con i key level su `C0` il
> `DEF-38` riscritto in v1.8 confronterebbe `high[C0] > high[C0]`, sempre
> falso).
>
> Questo file resta come traccia di cosa è stato trovato e perché.


Lettura completa degli otto file, nell'ordine indicato: `01`, `03`, `02`, `04`,
`05`, `06`, `00`, `07`.

Questo file **elenca** contraddizioni, ambiguità e regole non eseguibili. Non
le corregge: le scelte spettano all'autore della strategia.

Ogni voce ha un ID `REV-nn` per poterla citare. Gli ID `REV-` sono un namespace
separato e non interferiscono con `DEF-`, `SETUP-`, `PA-` eccetera.

Legenda della colonna *effetto*:

- **BLOCCA** — senza una risposta non posso scrivere quella parte del motore
- **CAMBIA I NUMERI** — posso scrivere il codice, ma due letture legittime
  producono un numero di operazioni diverso
- **FORMALE** — non cambia il comportamento, ma viola una regola che i
  documenti si sono dati (tipicamente `ESCL-18`, `ESCL-19`, `ESCL-20`)

---

# Stato dopo la revisione documenti del 2026-09-03

Aggiornato dopo `01_definizioni.md` v1.8, `03_setup.md` v0.4, `04_gestione.md`
v0.3, `05_rischio.md` v0.5, `06_esclusioni.md` (ESCL-15 riscritta).

`00_principi.md`, `02_contesto.md` e `07_casi.md` non sono stati modificati.

## Chiuse — 8 voci

| REV | Come è stata chiusa |
|---|---|
| REV-04 | `DEF-47` + `RISK-03` v0.5: la distanza si misura interamente sul future. Resta `PA-62` (fattore `k`), che il documento stesso marca BLOCCANTE |
| REV-05 | Vocabolario esteso: `valore_punto`, `pnl_settimanale`, `pnl_mensile`, `atr`, `distanza_kl_gap` |
| REV-06 | `SETUP-19`, con l'ID nuovo invece di riciclare `SETUP-08` — corretto per `ESCL-18`. La nota sulla doppia trasformazione (tabella in direzioni CFD + segno `DEF-33` sul future) risolve anche il punto che non avevo sollevato |
| REV-07 | `DEF-46`: `target_di(TF)` = key level del timeframe immediatamente superiore |
| REV-09 | `DEF-45`: separazione CALCOLO / SORVEGLIANZA. Vedi però REV-43 |
| REV-12 | `GEST-01` v0.3: `rr` su `TP1`, con la tabella di esempio che mostra l'effetto. `CTX-01` #5 diventa coerente |
| REV-24 | `DEF-36`: aggiunta `liv_50(candela)`, applicabile a `N1` su qualsiasi timeframe |
| REV-33 | Parzialmente: `ESCL-15` ammette l'ATR come sola unità di misura e il vocabolario lo contiene. Resta aperta la soglia `PA-44`, quindi `GIUD-01` non è ancora eseguibile — per un motivo invece di tre |

## Nuove — 3 voci

### REV-42 — `RISK-02` adesso dice sia sì sia no al ridimensionamento — BLOCCA

La frase vecchia non è stata cancellata. Nella stessa regola convivono:

> **Ridimensionamento.** A ogni nuova apertura **tutte** le posizioni già aperte
> vengono ridimensionate al nuovo `rischio_operazione`.

e, ventisei righe più sotto:

> `n` si calcola al momento dell'invio dell'ordine [...] Le posizioni già aperte
> **non** vengono ridimensionate quando `n` cresce.

Il blocco `SE n == 1 / n == 2 / n >= 3` compare inoltre due volte, identico.

La colonna "Rischio totale" della tabella è corretta **solo** nella lettura con
ridimensionamento. Con l'altra restano validi i numeri di REV-01 e REV-02
(2,65% per quattro posizioni, 13,25% per cinque strumenti). Finché la frase
vecchia resta, non so quale delle due regole applicare — ed è la differenza fra
un'esposizione massima di 1,80% e una di 2,65% per strumento.

Nota: la non monotonia è ora dichiarata voluta, e va bene. Ma vale solo con il
ridimensionamento: senza, non esiste proprio.

### REV-43 — `DEF-43` ricade nel CALCOLO ma il suo testo parla di prezzo scambiato — BLOCCA

`DEF-45` elenca come sorveglianza: `DEF-27`, `DEF-29`, `DEF-34`, `RISK-12`,
`GEST-04`, `GEST-11`. E chiude con *"Regole di solo calcolo: tutte le altre"*.

`DEF-43` non è nell'elenco, quindi è calcolo, quindi solo candele chiuse. Ma il
suo testo dice tre volte *"il prezzo scambiato"* (entra, esce, rientra dalla
zona) e *"`estremo_fase1` si aggiorna **in continuo** durante la fase 1"*.

Non è un dettaglio: `gap_fase == 3` è la condizione di ingresso di `SETUP-09`.
Valutare le fasi a tick o a candela chiusa cambia quando — e se — scatta.
`DEF-43` va messo in una delle due liste, e se va nel calcolo il suo testo va
riscritto.

### REV-44 — La tabella DXY esiste ora in due posti, con contenuto diverso — FORMALE

`SETUP-19` la reintroduce, ma la copia nel promemoria §8 di
`01_definizioni.md` è rimasta, e le due non coincidono:

| | Colonna `XAUUSD` | Riga `NESSUNA` |
|---|---|---|
| §8 promemoria | presente ("non derivata dal DXY") | assente |
| `SETUP-19` | assente | presente |

REV-40 diceva di rimuovere §8 **dopo** la migrazione. La migrazione è fatta:
ora §8 va cancellato, o le due copie divergeranno.

## Restano aperte — 30 voci

Nessuna di queste è stata toccata da questo giro.

**Bloccanti:** REV-03 (`XAUUSD` senza scala di rischio: `RISK-02` dice
"esclusivamente forex", `RISK-06` dice "segue la scala di RISK-02"), REV-08
(`PA-31`), REV-20 (`CTX-08` contro `CTX-10`), REV-21 (`PRIN-16` contro
`SETUP-04`), REV-22 (`SETUP-05` con due condizioni diverse), REV-25 (`PA-60`),
REV-26 ("conferma il pattern" non definito).

**Cambiano i numeri:** REV-01 (dipende da REV-42), REV-02 (idem), REV-10, REV-11,
REV-13, REV-14, REV-15, REV-16, REV-17, REV-18, REV-23, REV-27, REV-28, REV-29,
REV-30, REV-31, REV-32.

**Formali:** REV-19, REV-34, REV-35, REV-36, REV-37, REV-38, REV-39, REV-41.

---

## 1. Aritmetica del rischio che non torna

Li metto per primi perché non sono ambiguità di lettura: sono conti.

### REV-01 — La colonna "Rischio totale" di RISK-02 contraddice la regola che le sta sotto — BLOCCA

`RISK-02` fissa la scala e poi dice:

> `n` si calcola al momento dell'invio dell'ordine [...] **Le posizioni già
> aperte non vengono ridimensionate quando `n` cresce.**

Se le posizioni non si ridimensionano, il rischio totale è la **somma di quello
che ciascuna aveva al proprio ingresso**, non `n × rischio_corrente`. La tabella
calcola invece `n × rischio_corrente`:

| `n` | Totale secondo la tabella | Totale effettivo, aprendo in sequenza |
|---|---|---|
| 1 | 1,00% | 1,00% |
| 2 | 1,50% | 1,75% (1,00 + 0,75) |
| 3 | 1,35% | 2,20% (1,00 + 0,75 + 0,45) |
| 4 | 1,80% | **2,65%** (1,00 + 0,75 + 0,45 + 0,45) |
| 5 | 2,25% | 3,10% |

Due conseguenze, entrambe pesanti:

1. La tabella non è monotona: passando da 2 a 3 posizioni il rischio totale
   **scende** da 1,50% a 1,35%. Aprire una terza posizione ridurrebbe
   l'esposizione complessiva. Questo può accadere solo se tutte e tre vengono
   aperte simultaneamente e ridimensionate insieme — cioè esattamente ciò che
   la regola vieta.
2. Tutti i numeri costruiti su quella colonna sono sottostimati. Vedi REV-02.

### REV-02 — L'esposizione massima dichiarata è sbagliata per difetto, e su quella si stanno decidendo PA-33 e PA-52 — BLOCCA

`RISK-06` ("Conseguenza aritmetica da conoscere") e `PRIN-15` / nota `PA-52`
usano i totali della tabella di `RISK-02`:

| Grandezza | Valore dichiarato | Valore effettivo con la regola del non-ridimensionamento |
|---|---|---|
| 4 posizioni su uno strumento | 1,80% | **2,65%** |
| 5 strumenti forex × 4 posizioni | 9,00% | **13,25%** |
| Su conto prop da 50.000 | 4.500 EUR | **6.625 EUR** |

`PA-33` (tetto di rischio aggregato) e `PA-52` (vincoli prop) sono decisioni che
stai per prendere su questi numeri. Sono sbagliati di circa il 47%.

### REV-03 — XAUUSD non ha alcuna scala di riduzione del rischio — BLOCCA

`RISK-02` si apre con: *"Si applica **esclusivamente** agli strumenti forex
derivati dal DXY: EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY."* — l'oro è escluso.

Ma `RISK-06`, che ammette fino a 4 posizioni **per singolo strumento** e vale
per tutti, chiude con: *"Il rischio di ciascuna posizione segue la scala di
RISK-02."*

Per `XAUUSD` le due regole si contraddicono. Se vale `RISK-01` senza scala,
quattro posizioni sull'oro valgono **4,00%** di rischio: più del doppio di
qualsiasi strumento forex, e oltre il limite giornaliero di `RISK-07` (3%) già
prima di aver perso un euro.

### REV-04 — `RISK-03` mescola prezzi future e prezzi CFD, che `ESCL-12` vieta di mescolare — BLOCCA

```
distanza_stop = |prezzo_ingresso - livello_stop|   (RISK-03)
```

- `prezzo_ingresso` è il prezzo a cui si è eseguito **sul CFD** di FP Markets
- `livello_stop` è l'estremo di `N2` (`SETUP-12`, `GEST-02`), e `N2` è una
  candela **del future** (`DEF-32`: *"Ogni valore di open/high/low/close usato
  da qualsiasi regola proviene dal grafico future"*)

Quella sottrazione è una differenza fra un prezzo CFD e un prezzo future.
`ESCL-12` — divieto permanente, e per `PREC-05` batte tutto — dice:

> Mai convertire prezzi tra future e CFD. Mai confrontare un prezzo future con
> un prezzo CFD.

Stessa cosa in `PRIN-07` e in `DEF-03`. Il calcolo della size, così com'è
scritto, è vietato da tre regole.

Il caso peggiore è `USDJPY` e `USDCHF`: per `PRIN-08` e `DEF-33` hanno segno
**invertito**, quindi `6J` e `6S` non sono nemmeno sulla stessa scala della
coppia CFD. La distanza in punti sul future non ha alcuna relazione lineare con
la distanza sul CFD, e `ESCL-12` vieta di convertirla.

### REV-05 — `valore_punto`, `pnl_settimanale`, `pnl_mensile` non esistono nel vocabolario — BLOCCA

`ESCL-14`: *"Mai usare un dato assente dal vocabolario di 01_definizioni.md. Se
una regola richiede un dato non presente in quella tabella, la regola non è
eseguibile."*

| Dato richiesto da | Presente nel vocabolario (`01_definizioni.md` §7)? |
|---|---|
| `valore_punto` — `RISK-03` | **no** |
| `pnl_settimanale` — `RISK-08` | **no** (c'è solo `pnl_giornaliero`) |
| `pnl_mensile` — `RISK-09` | **no** |
| equity di inizio giornata / settimana / mese — `RISK-07/08/09` | **no** (c'è solo `equity` corrente) |
| `atr` — `GIUD-01` e `07_casi.md` §3.1 | **no** |

Per la lettera di `ESCL-14`, `RISK-03`, `RISK-08`, `RISK-09` e `GIUD-01` non
sono eseguibili. O si allarga il vocabolario, o quelle regole restano ferme.

---

## 2. Bloccanti sulla direzionalità

### REV-06 — `SETUP-08` non è la regola che tre documenti dicono che sia — BLOCCA

Tre regole derivano la direzione delle coppie forex dal DXY citando `SETUP-08`:

- `PRIN-09`: *"Le cinque coppie forex derivano la direzione dal DXY secondo SETUP-08"*
- `DEF-33`: *"serve solo a determinare la direzione degli strumenti forex (SETUP-08)"*
- `RISK-05`: *"la direzione del setup è inversa a quella del DXY secondo SETUP-08"*

`SETUP-08` in `03_setup.md` è **"Reversal dopo il target"**. Non contiene la
parola DXY. Verificato: in tutto `03_setup.md` la stringa "DXY" non compare mai.

L'unica tabella che mappa bias DXY → direzione per strumento sta in
`01_definizioni.md` §8, sotto l'intestazione:

> ## 8. Promemoria di lavoro (**da rimuovere prima della consegna**)
> [...] → destinazione `03_setup.md`

Quella migrazione non è avvenuta. Senza quella tabella non posso determinare la
direzione di nessuna delle cinque coppie forex, e cinque strumenti su sei
diventano inoperabili.

### REV-07 — "il target di `tf_comando`" non è definito da nessuna parte — BLOCCA

`SETUP-06` passo 2 richiede: *"il **target associato** non è RAGGIUNTO"*, per
ciascun timeframe scorso. `SETUP-07`, `SETUP-08` e `GEST-10` parlano del
*"target di `tf_comando`"*.

Ma `DEF-22` definisce **un solo** target direzionale, cercato sempre a partire
da `TF_12M` (*"La ricerca parte sempre da TF_12M, indipendentemente dal
timeframe del gap attivo"*). Non esiste una definizione di "target di `TF_1W`"
o "target associato a un timeframe".

`SETUP-06` è il punto in cui si decide la direzione di tutto il sistema, e la
sua condizione (b) non è calcolabile.

### REV-08 — `PA-31`, già segnalato come BLOCCANTE, riguarda una contraddizione interna a `DEF-21`

Il preambolo di `DEF-21` dice:

> Il rifiuto richiede **due** condizioni simultanee: la mancata accettazione del
> livello e una spike prevalente sul corpo.

Poi definisce **rifiuto semplice** *senza* la condizione sulla spike, e
**rifiuto forte** *con* la spike. Il preambolo descrive solo il rifiuto forte,
ma è scritto come se valesse per entrambi.

`DEF-16` passi 4 e 5 usano il rifiuto **semplice** per la bias. Se valesse il
preambolo, una candela che spazza un estremo e richiude dentro senza spike
prevalente non produrrebbe bias — che è esattamente la domanda aperta di
`PA-31`.

---

## 3. Candele chiuse contro prezzo scambiato

### REV-09 — La regola più assoluta del corpus è violata da otto regole — BLOCCA

`ESCL-13` (divieto permanente, `PREC-05` batte tutto), `PRIN-11` e `DEF-02`
dicono la stessa cosa senza eccezioni:

> Ogni regola usa esclusivamente candele chiuse. La candela in formazione non
> viene mai valutata.

Queste regole valutano invece il prezzo **dentro** la candela in formazione, e
lo dicono esplicitamente:

| Regola | Testo |
|---|---|
| `DEF-27` | *"Il consumo si verifica al tocco, sul prezzo scambiato, non alla chiusura di candela"* |
| `DEF-29` | *"Il raggiungimento si verifica al tocco, non alla chiusura di candela"* |
| `DEF-38` | *"La presa si verifica sul prezzo scambiato, non alla chiusura di candela"* |
| `DEF-43` | *"il prezzo scambiato entra in zona_gap"*, `estremo_fase1` *"si aggiorna in continuo"* |
| `DEF-34` | *"SE il prezzo scambiato del future raggiunge target_valore"* |
| `RISK-12` | *"SE il prezzo scambiato del future raggiunge livello_stop"* |
| `GEST-04` | *"SE il prezzo scambiato del future raggiunge TP1"* |
| `GEST-11` | *"SE il prezzo del future raggiunge stop o target"* |

Manca la distinzione che risolverebbe tutto, e nessun documento la fa:

- **candela chiusa** → per calcolare pattern, bias, gap, livelli
- **prezzo scambiato** → per sorvegliare soglie *già fissate* da un calcolo su
  candele chiuse

Finché non è scritta, `DEF-38` (presa del key level) è la più critica: è la
condizione che **abilita la ricerca del setup**. Valutarla a ogni tick o solo a
fine candela cambia sia il momento sia il numero degli ingressi.

---

## 4. Contraddizioni dirette

### REV-10 — `DEF-01` contiene due gerarchie diverse, e regole diverse usano gerarchie diverse — CAMBIA I NUMERI

Dentro `DEF-01`, a diciassette righe di distanza:

```
Ordine gerarchico completo:
TF_12M > TF_6M > TF_3M > TF_1M > TF_1W > TF_1D > TF_H12 > TF_H6 > TF_H4 > TF_H1

Ordine gerarchico, dal più alto al più basso:
TF_12M > TF_6M > TF_3M > TF_1M > TF_1W > TF_1D > TF_H4 > TF_H1
```

`DEF-30` dice *"secondo la gerarchia di DEF-01"* senza dire quale. La tabella di
esempi di `DEF-30` usa quella **completa** (per `TF_1D` ammette `TF_H12` e
`TF_H6`). La tabella di `SETUP-05` usa quella **ridotta** (per `TF_H1` i due
superiori sono `TF_H4` e `TF_1D`, saltando `TF_H6` e `TF_H12`).

### REV-11 — Un CRT su `TF_H12` o `TF_H6` è ammesso da `SETUP-10` e reso impossibile da `SETUP-05` — CAMBIA I NUMERI

`SETUP-10`, esempio testuale: *"gap su TF_1W, CRT ammesso su TF_1W, TF_1D,
**TF_H12**, **TF_H6**, TF_H4, TF_H1"*.

`SETUP-05`, tabella dei due timeframe superiori: nessuna riga per `TF_H12` e
`TF_H6`, con la nota *"non compaiono: servono solo ai gap (DEF-31) e non sono
timeframe di allineamento"*.

`SETUP-15` e `CTX-01` #4 vietano l'ingresso se *"meno di 2 timeframe [superiori]
allineati"*. Un CRT su `TF_H12` non può mai soddisfare quella condizione, perché
per quel timeframe la condizione non è definita. Risultato: `SETUP-10` autorizza
un ingresso che `SETUP-05` rende strutturalmente irraggiungibile.

### REV-12 — Il filtro rischio/rendimento è definito su due grandezze opposte — CAMBIA I NUMERI

| Dove | Su cosa si calcola `rr` |
|---|---|
| `GEST-01` | *"`target_iniziale` = target_finale alla data dell'ingresso (SETUP-14), **NON TP1**"* |
| `CTX-01` #5 | *"Rapporto rischio/rendimento su **TP1** inferiore a 1,5 (GEST-01)"* |
| `07_casi.md` §2 | campo `rr_su_tp1` |
| `07_casi.md` §3.2 | *"rapporto rischio/rendimento sotto 1,5 (GEST-01)"* |

`TP1` è il 50% del range di `N1`; il target finale è un key level di timeframe
superiore, molto più lontano. Il rapporto calcolato sul primo è di norma una
frazione di quello calcolato sul secondo. È il filtro più selettivo della
strategia — `CTX-01` lo elenca fra le condizioni di astensione — e la scelta fra
le due letture cambia radicalmente quante operazioni passano.

### REV-13 — `DEF-32` si contraddice sulla fonte dati, e `ESCL-12` vieta il meccanismo che propone — BLOCCA

Prima riga di `DEF-32`:

> Ogni valore di `open`, `high`, `low`, `close` usato da qualsiasi regola della
> strategia proviene dal **grafico future**, mai dal CFD.

Tabella dentro la stessa regola, tre righe dopo:

| Timeframe | Fonte primaria |
|---|---|
| `TF_H12`, `TF_H6` | **CFD Capital.com** |
| `TF_H4`, `TF_H1` | **CFD Capital.com** |

E il testo: *"Sui timeframe inferiori il segnale viene rilevato sul CFD e diventa
operativo solo quando il dato del future lo **conferma**"*.

"Confermare" significa confrontare un segnale CFD con un dato future. `ESCL-12`
(*"Mai confrontare un prezzo future con un prezzo CFD"*) e `DEF-03`
(*"Nessuna regola può confrontare una candela del future con una candela del
CFD"*) lo vietano. Per `PREC-05` vince il divieto, e resta da capire come si
leggano i segnali su `TF_H4` e `TF_H1`.

### REV-14 — `DEF-32` dice sia "nessun ritardo fisso" sia "10 minuti obbligatori nel backtest" — CAMBIA I NUMERI

Intestazione del file: *"Versione 1.6 — DEF-32 rivista: **nessun ritardo fisso
di esecuzione**"*.

Dentro `DEF-32`, revisione v1.6: *"Non esiste un ritardo prestabilito di
esecuzione. L'ingresso avviene all'apertura di N3, il prima possibile."*

Nel paragrafo immediatamente successivo, stessa regola: *"Il momento di
valutazione è l'arrivo del dato di chiusura del future, che può avvenire fino a
10 minuti dopo la chiusura effettiva del periodo. **Ogni backtest deve usare lo
stesso ritardo.**"*

E la colonna "Momento operativo" della tabella dice *"10 minuti dopo la chiusura
del periodo"* per tutti i timeframe. Tre affermazioni, due incompatibili.

### REV-15 — `DEF-13` e `DEF-31` danno due liste di scansione diverse — CAMBIA I NUMERI

`DEF-13` passo 1, elenco esplicito: `TF_12M, TF_6M, TF_3M, TF_1M, TF_1W, TF_1D`.

`DEF-31`: *"Questi due timeframe [`TF_H12`, `TF_H6`] entrano nell'ordine di
scansione di `DEF-13` nella posizione stabilita dalla gerarchia di `DEF-01`,
subito sotto `TF_1D`."*

Se un gap esiste solo su `TF_H12`, con la prima lista `gap_attivo = NESSUNO` e
per `DEF-30` *nessun timeframe è ammesso per l'ingresso*; con la seconda il gap
esiste e si opera.

### REV-16 — `DEF-18` e `DEF-03` datano la chiusura annuale in due momenti diversi — CAMBIA I NUMERI

`DEF-18`: *"`bias_12M` viene calcolata alla chiusura della candela `TF_12M`
(**31 dicembre, 24:00 UTC**)"*.

`DEF-03`: le candele si costruiscono sulla sessione ETH dell'exchange, e *"Il
giorno di contrattazione del future comincia alle 18:00 di New York del giorno
solare precedente"*.

Con la sessione ETH la candela annuale del future non chiude il 31 dicembre a
24:00 UTC. `DEF-03` è dichiarata *"conseguenza vincolante"*; `DEF-18` usa il
giorno solare. Sposta la data di calcolo della bias che comanda tutto l'anno.

### REV-17 — `SETUP-15` e `CTX-01` sono due elenchi di esclusioni che dovrebbero coincidere e non coincidono — CAMBIA I NUMERI

| Condizione | `CTX-01` | `SETUP-15` |
|---|---|---|
| Festività di mercato (`CTX-04`) | sì (#9) | **no** |
| `rr` sotto 1,5 (`GEST-01`) | sì (#5) | **no** |
| TF del CRT non inferiore a quello del key level | **no** | sì |
| Finestra news | sì, citando `CTX-02` | sì, citando `RISK-13` |

Nessuno dei due dichiara di essere quello normativo. Implementare l'unione
produce un comportamento che nessuno dei due documenti descrive.

### REV-18 — `CTX-02` blocca tutti gli strumenti, `RISK-13` blocca solo quello coinvolto — CAMBIA I NUMERI

`CTX-02`: *"SE l'orario corrente è dentro `finestra_blocco` ALLORA **nessun
nuovo ordine**"* — senza qualificazione.

`RISK-13`: *"ALLORA nessun nuovo ordine **su quello strumento**"*.

Con una news 3 stelle sulla sterlina: `CTX-02` ferma anche `EURUSD` e `XAUUSD`,
`RISK-13` ferma solo `GBPUSD`. Entrambe sono citate come la regola del filtro
news (da `CTX-01` #8 e da `SETUP-15` rispettivamente).

### REV-19 — `CTX-07` nega e conferma la stessa cosa in due frasi — FORMALE

> `SE` mancano candele nello storico di un timeframe `ALLORA` il timeframe resta
> utilizzabile [...] **Non esiste esclusione automatica di un timeframe per dati
> mancanti.** Resta valido il requisito minimo di `DEF-26`: almeno 3 candele
> chiuse entro il `lookback` di 5 anni.

`DEF-26` *è* un'esclusione automatica per dati mancanti: *"ALLORA quel timeframe
non produce né bias né livelli strutturali"*.

### REV-20 — `CTX-08` e `CTX-10` si contraddicono sul primo minuto di vita del bot — BLOCCA

`CTX-08`: *"Il bot è operativo immediatamente all'avvio. Non esiste periodo di
osservazione né riscaldamento. Se allo start esiste un setup valido, viene
eseguito."*

`CTX-10`: *"SE l'analisi del timeframe appena chiuso non è stata ricalcolata
ALLORA nessuna operatività sui timeframe inferiori."*

All'avvio nessun timeframe è mai stato ricalcolato *dal sistema*. O `CTX-10` si
riferisce solo ai ricalcoli successivi all'avvio — e va detto — oppure `CTX-08`
è irrealizzabile.

### REV-21 — `PRIN-16` (conferma manuale) rende quasi ogni setup non eseguibile per `SETUP-04` — BLOCCA

`PRIN-16` impone la modalità semi-automatica come modalità iniziale.
`SETUP-04`: *"l'ordine si invia all'apertura di N3, **senza attese**"* e *"Un CRT
non eseguito all'apertura di N3 non è più eseguibile."*

`PA-51` lo riconosce già. Lo segnalo qui perché è **la prima cosa che
incontrerai sul conto demo**: su `TF_H1` la finestra di conferma è di pochi
secondi.

---

## 5. Ambiguità che cambiano il comportamento

### REV-22 — `SETUP-05` definisce due condizioni diverse con lo stesso ID — BLOCCA

Dentro `SETUP-05`:

1. *"Condizione di allineamento"*: `bias TF_A == bias TF_B` **AND** entrambi
   presentano un CRT nella stessa direzione.
2. *"Regola dei due timeframe superiori"*: i due TF immediatamente superiori
   devono aver **sbilanciato un key level** nella direzione dell'operazione.

Sono condizioni diverse, su dati diversi. `CTX-01` #4 e `SETUP-15` citano
*"meno di 2 timeframe allineati (SETUP-05)"* senza dire quale.

### REV-23 — `DEF-36`: i key level si calcolano su `C1` o su `C0`? — CAMBIA I NUMERI

`DEF-36` dice *"calcolati sulla candela chiusa precedente `C1`"* e usa
`high[C1]`, `low[C1]`.

Con la notazione di `DEF-02` (`C0` = ultima chiusa, `C1` = quella prima), i key
level userebbero la **penultima** candela chiusa. Nell'uso corrente "il massimo
della settimana precedente" è l'ultima candela chiusa, cioè `C0`.

Sposta ogni key level di un intero periodo, e con esso ogni presa (`DEF-38`),
ogni CRT (`SETUP-02`) e ogni `TP1` (`SETUP-13`).

### REV-24 — `TP1` è definito con una formula che `DEF-36` non contiene — BLOCCA

`SETUP-13` e `GEST-07`: *"`TP1` = `KL_50` della candela `N1` del timeframe su cui
è nato il CRT (`DEF-36`)"*.

Ma `DEF-36`:
- calcola `KL_50` su `C1`, non su `N1`
- lo definisce solo per `TF_12M … TF_1D`, **non** per `TF_H4` e `TF_H1`

Un CRT nato su `TF_H4` — il caso dell'esempio di `SETUP-14` e del `CASO 01` di
`07_casi.md` — non ha alcun `KL_50` definito da `DEF-36`. La formula che serve,
`(high[N1] + low[N1]) / 2`, non è scritta in nessun documento.

### REV-25 — `SETUP-14` usa i key level come target, e `DEF-36` glielo vieta — BLOCCA

`DEF-36` è esplicito nel separare le due famiglie di livelli:

> I livelli strutturali sono l'insieme di tutti i massimi e minimi entro
> `lookback` e servono **per il target** di lungo periodo (`DEF-22`). I key level
> sono i tre valori qui sopra [...] e servono **per l'ingresso**.

`SETUP-14` e `GEST-08` fanno l'opposto: *"il target del 75% residuo è il **key
level** del timeframe più alto disponibile"*.

Ne segue che esistono due target diversi — quello di `DEF-22` (livello
strutturale, per `tf_comando`) e quello di `SETUP-14` (key level, per la
posizione) — e `GEST-01` non dice quale sia `target_iniziale`. Vedi anche
REV-12.

### REV-26 — "quel timeframe conferma il pattern" non è definito — BLOCCA

È la condizione che governa l'estensione progressiva del target in `SETUP-14` e
`GEST-08`, ed è scritta così e basta. Un CRT formato? Una bias concorde? Un key
level sbilanciato? `ESCL-19` vieta esattamente questo:

> Mai introdurre un aggettivo valutativo senza soglia numerica.

### REV-27 — Con due gap attivi non si sa quale comanda — CAMBIA I NUMERI

`DEF-13` produce `gap_attivo_long` **e** `gap_attivo_short`, potenzialmente su
timeframe diversi (il vocabolario ha infatti `gap_long_tf` e `gap_short_tf`
distinti).

`DEF-15bis` dice *"Il gap attivo sul timeframe più alto in cui esiste (`DEF-13`)
è **un** target"*, al singolare. `DEF-30` dice *"`TF_riferimento` è il timeframe
del gap attivo"*, al singolare. Con un gap long su `TF_1M` e uno short su
`TF_1W`, quale dei due?

### REV-28 — `DEF-30` non dice come si sceglie fra gap e key level — CAMBIA I NUMERI

> `TF_riferimento` è il timeframe del gap attivo (`DEF-13`) **oppure** il
> timeframe del key level preso (`DEF-38`), **a seconda di quale abbia generato
> il contesto operativo**.

Non esiste una regola che stabilisca quale dei due ha generato il contesto. Nel
caso di ingresso da gap (`SETUP-09`) ci sono per forza entrambi, perché
`SETUP-00` impone che un key level sia sempre stato preso.

### REV-29 — `DEF-42`: "direzione del gap" è la polarità o la direzione operativa? — CAMBIA I NUMERI

`DEF-42` chiede se `C0` sia *"CONFLUENTE al trend nella direzione del gap"*.

`DEF-15bis` stabilisce espressamente che le due cose possono essere opposte:
*"Un gap rialzista situato sotto il prezzo è un target ribassista."*

La scelta cambia il ramo di `DEF-42`, e quindi `mitigazione_attesa`, e quindi
— per `CTX-01` #10 — se si operi o ci si astenga.

### REV-30 — `DEF-43`: "esce nella direzione contraria" a cosa — CAMBIA I NUMERI

Fase 2: *"il prezzo scambiato esce da `zona_gap` nella direzione contraria"*.
Contraria all'ingresso in zona, o alla bias? Per una zona sopra il prezzo con
bias short il prezzo entra dal basso, e le due letture indicano due lati
opposti.

Fase 3 ha lo stesso problema di ordine: *"rientra in `zona_gap`" **AND** "supera
`estremo_fase1`"*. Se `estremo_fase1` è interno alla zona, superarlo può portare
fuori dalla zona dal lato opposto: le due condizioni possono non essere
simultaneamente vere.

### REV-31 — `DEF-44` e il vocabolario usano due timeframe diversi per l'RSI — CAMBIA I NUMERI

`DEF-44`: `rsi_timeframe = timeframe del gap`.
Vocabolario `01_definizioni.md` §7: *"`rsi` — RSI(14) sul **timeframe di
trigger**"*.

Per `DEF-30` il trigger è sempre su un timeframe **inferiore** a quello del gap,
quindi i due non coincidono mai.

### REV-32 — `DEF-41` usa 0.05, `PA-29` chiede di confermare 0.10 — CAMBIA I NUMERI

Testo di `DEF-41`: `corpo[C0] <= 0.05 × range[C0]`.
`PA-29`: *"Soglie di `DEF-41` (indecisione): confermare **0.10** e 0.40"*.

La soglia scritta nella regola e quella citata nel punto aperto che la governa
non coincidono.

### REV-33 — `GIUD-01` non è eseguibile per tre motivi indipendenti — BLOCCA

1. Richiede `atr del timeframe`. L'ATR non è nel vocabolario → `ESCL-14`.
2. `ESCL-15`: *"Mai usare indicatori oltre l'RSI applicato ai gap"*. L'ATR è un
   indicatore, e non è applicato ai gap.
3. `PA-44`: la soglia fra "vicini" e "distanti" non esiste.

`07_casi.md` §3.1 chiede `atr_tf` e `rapporto` in ognuno dei 30 casi di
categoria A/B/C, cioè proprio i dati che serviranno a chiudere `PA-44`. Il modo
per raccoglierli è vietato dalle regole che quei casi devono verificare.

### REV-34 — `RISK-06` descrive un ingresso su `N2`, `SETUP-03` dice che non esiste — FORMALE

`RISK-06`: *"Un trigger su `TF_H1` abilita un ingresso sulla candela **N2** di
`TF_H4`"*.

`SETUP-03` anticipa e risolve l'obiezione — *"l'ingresso su `N3` di un timeframe
inferiore [...] cade temporalmente dentro la candela `N2` del timeframe
superiore"* — quindi le due sono conciliabili. Ma la formulazione di `RISK-06`
viola `ESCL-20` (rimandi impliciti), e la progressione che descrive è ciò che
determina il conteggio delle 4 posizioni massime: va riscritta in modo esplicito
o il conteggio resta interpretabile.

### REV-35 — `SETUP-05` "la catena non si spezza" non ha effetto osservabile — FORMALE

*"SE un timeframe intermedio non è allineato ALLORA il CRT già formato su un
timeframe inferiore NON viene invalidato."*

Ma per `SETUP-04` un CRT non eseguito all'apertura di `N3` decade comunque, e
per la "regola dei due timeframe superiori" quel CRT non può produrre ingresso.
Un CRT che resta valido senza poter mai essere eseguito e che decade da solo:
va detto cosa cambia, nei fatti.

---

## 6. Rimandi rotti

| ID | Dove | Cita | Ma quella regola è |
|---|---|---|---|
| REV-36 | `RISK-04` | *"il CRT è a supporto di un gap (`SETUP-04`)"* | `SETUP-04` è "Immediatezza dell'ingresso". Il riferimento corretto è `SETUP-10` |
| REV-37 | `RISK-11` | *"Il livello è quello definito da `SETUP-10`"* | `SETUP-10` copre solo il doppio ingresso su gap. Il caso senza gap è in `SETUP-12` / `GEST-02` |
| REV-38 | `SETUP-15` | *"finestra_blocco per news 3 stelle (`RISK-13`)"* | `CTX-01` #8 cita `CTX-02` per la stessa condizione. Vedi REV-18 |
| REV-39 | `DEF-21`, `DEF-15` | *"La versione originaria [...] è ritirata"* | Ma l'ID viene riusato per la nuova versione (`DEF-21`) o affiancato da un bis (`DEF-15bis`), mentre `ESCL-18` dice *"Se una regola viene ritirata, il suo ID muore con lei"* |
| REV-40 | `01_definizioni.md` §8 | *"Promemoria di lavoro (da rimuovere prima della consegna)"* | Contiene l'universo strumenti (→ `PRIN-08`, migrato) e la tabella DXY (→ non migrata, REV-06). Va rimosso solo dopo aver spostato la seconda |

### REV-41 — L'ordine di precedenza non è leggibile in un solo posto — FORMALE

| Regola | Definita in |
|---|---|
| `PREC-01` | `00_principi.md` §7, `02_contesto.md` §6, `05_rischio.md` §3 — **tre volte** |
| `PREC-02` | `00_principi.md`, `02_contesto.md` |
| `PREC-03` | `00_principi.md`, `02_contesto.md` |
| `PREC-04` | solo `02_contesto.md` |
| `PREC-05` | solo `06_esclusioni.md` |

Inoltre non esiste un ordinamento fra `PREC-01` (RISK batte SETUP) e `PREC-04`
(CONTESTO batte SETUP): entrambe bloccano, quindi in pratica non serve, ma
`PREC-02` (timeframe alto comanda) può entrare in conflitto con `PREC-05`
(esclusioni battono tutto) senza che sia detto chi vince.

---

## 7. Punti aperti già dichiarati: quali fermano il codice

Non li ho scoperti io, sono già nei documenti. Li classifico per impatto sul
motore, come richiesto.

| PA | Argomento | Effetto sul motore |
|---|---|---|
| `PA-31` | `DEF-16` passi 4-5 senza soglia spike | **BLOCCA** — già marcato BLOCCANTE. Vedi REV-08 |
| `PA-44` | Soglia "vicini/distanti" di `GIUD-01` | **BLOCCA** `GIUD-01`. Vedi REV-33 |
| `PA-05` | Regole proprie di `XAUUSD` | **BLOCCA** l'oro: `PRIN-09` dice che ha bias propria, nessuna regola la definisce |
| `PA-15` | Conferma dei correlati | **BLOCCA** se è una condizione di ingresso; irrilevante se è statistica. Non è detto quale |
| `PA-51` | Setup proposto e non confermato | **BLOCCA** la modalità `semi`. Vedi REV-21 |
| `PA-33` | Tetto di rischio aggregato | Da decidere sui numeri corretti di REV-02, non su quelli scritti |
| `PA-47` | Stop aggressivo con gap invalidato | **BLOCCA** `GEST-06` secondo caso |
| `PA-48` | Target consumato prima di `TP1` | **BLOCCA** `GEST-09` |
| `PA-49` | Dove si salva lo stato delle posizioni | **Risolvibile subito**: l'archivio SQLite esiste già (tabella `posizione`) |
| `PA-38` | Perdita del flusso dati | **BLOCCA** in produzione, non in demo |
| `PA-46` | `buffer_be` per strumento | Default configurabile possibile |
| `PA-53` | Festività a data mobile | Default configurabile. La tabella 2026 di `CTX-04` è **corretta** per il 2026, verificata data per data: scade il 1° gennaio 2027 |
| `PA-54`, `PA-55` | Calendario news | **BLOCCA** — il filtro news è nell'elenco obbligatorio di `CTX-01` #8 e `SETUP-15` |
| `PA-30` | `mitigazione_attesa = NON_DETERMINATA` | Già risolto da `DEF-42` e `CTX-01` #10: astensione |
| `PA-34`, `PA-37`, `PA-39`, `PA-50`, `PA-52` | — | Non bloccano il motore |

---

## 8. Conseguenze della scelta di collaudare su demo

Il forward test su conto demo è coerente con `PRIN-15` Fase 1. Rimuove il motore
di replay storico, ma non tutto quello che il replay serviva a coprire.

**Resta necessario lo storico.** `DEF-26` impone un `lookback` di 5 anni per i
livelli strutturali, e `DEF-13` scandisce fino a `TF_12M`. All'avvio il motore ha
bisogno di cinque anni di candele chiuse sui future CME/COMEX (`GC`, `6E`, `6B`,
`6A`, `6S`, `6J`) più `ICEUS` per il DXY. Il conto demo FP Markets fornisce
**CFD**, e `DEF-32` e `PRIN-08` impongono l'analisi sul future. La domanda sulla
fonte dati non sparisce: cambia forma, da "storico per il replay" a "storico di
riscaldamento più flusso live sui future". `DEF-33` segnala anche che `ICEUS` è
ICE, non CME, e richiede un abbonamento dati separato.

**I tempi di raccolta cambiano ordine di grandezza.** `07_casi.md` chiede minimo
75 casi, di cui 30 di categoria A/B/C per chiudere `PA-44`. Con `bias_comando`
determinata da timeframe trimestrali o annuali (`SETUP-06`) e ingressi che
richiedono key level preso, CRT formato e due timeframe superiori allineati, la
frequenza di segnale è bassa. Su demo quei 30 casi arrivano in tempo di mercato
reale, non in un pomeriggio di replay. La procedura del `07_casi.md` §4 —
TradingView Replay, manuale — resta la via più veloce per popolarli, e non
dipende dal bot.

**`CTX-03` presuppone il confronto.** La nota operativa dice: *"va tenuta
presente confrontando i risultati del backtest con quelli reali"*. Senza
backtest quel confronto non esiste, e l'effetto dello spread — che `CTX-03`
sceglie deliberatamente di non filtrare — si misura solo a posteriori sui trade
demo.

**Cosa c'è già.** L'infrastruttura ha le tabelle `alert`, `decisione` e
`posizione`, e registra ogni decisione con il suo esito. È la base naturale sia
per le statistiche richieste (conteggio per filtro di `CTX-01`, distribuzione
del `rapporto` di `GIUD-01`) sia per l'esportazione nel formato blocco di
`07_casi.md`.
