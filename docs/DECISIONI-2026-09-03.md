# Decisioni sui punti aperti — 2026-09-03

Su richiesta esplicita dell'autore ("risolvile te"), questo file scioglie i
punti che fermavano il motore. Sostituisce, per i punti elencati qui, la regola
originaria "non scegliere per me".

**Ogni decisione è reversibile in una riga.** Vivono tutte nel dizionario
`SCELTE` di `core/parametri.py`: cambiarne una non richiede di toccare la
logica.

## Le tre categorie

| Categoria | Significato | Quanto fidarsi |
|---|---|---|
| **RICOSTRUZIONE** | La risposta era già nei documenti. Due regole si contraddicevano, ma una era un residuo di una versione precedente, oppure una regola più specifica o più recente decideva già la questione. Non ho inventato: ho tolto il rumore | Alta. Verifica il ragionamento, non il merito |
| **GIUDIZIO** | I documenti tacciono davvero. Ho scelto io | Media. È qui che devi guardare |
| **MISURA** | Non è una decisione ma un numero da leggere dal broker o dal calendario. Risolto architetturalmente: il motore lo legge, non lo indovina | Alta, ma va verificato sul conto |

## Il criterio per i pareggi

Dove due letture restavano ugualmente difendibili ho scelto **quella che opera
di meno**. Non è una mia preferenza: è il default che i documenti si sono dati.

> `PRIN-99` — In assenza di una regola applicabile: NON OPERARE.
> Un trade saltato costa zero. Un trade sbagliato costa.

---

## 1. Ricostruzioni

### REV-10 — Gerarchia dei timeframe → **completa**

`DEF-01` conteneva due gerarchie. La seconda è identica alla prima meno
`TF_H12` e `TF_H6`: è la versione precedente all'introduzione di quei due
timeframe, sopravvissuta a una riscrittura. La tabella all'inizio di `DEF-01`
li elenca entrambi, e fra le due gerarchie c'è la frase di chiusura *"Nessun
altro timeframe può essere citato"* — che chiude il primo elenco, non apre il
secondo.

**Deciso:** vale la gerarchia completa a dieci timeframe. Il secondo blocco è
stato rimosso da `DEF-01`.

Questo non tocca `SETUP-05`, che esclude `TF_H12` e `TF_H6` dall'allineamento
con una regola esplicita e motivata. Una cosa è la gerarchia, un'altra è quali
timeframe possano allineare.

### REV-42 — Ridimensionamento delle posizioni → **sì, si ridimensiona**

La nota di versione di `05_rischio.md` v0.5 è letteralmente *"ridimensionamento
e size sul future"*, e il paragrafo nuovo è stato aggiunto per rispondere a
`REV-01`. La frase vecchia in fondo alla regola e la seconda copia del blocco
`SE n == 1 / n == 2 / n >= 3` sono residui non cancellati.

**Deciso:** a ogni nuova apertura tutte le posizioni aperte si adeguano al
nuovo `rischio_operazione`. La colonna "Rischio totale" della tabella diventa
corretta, e i numeri di `REV-01`/`REV-02` decadono. Testo residuo rimosso.

### REV-44 — Tabella DXY duplicata → **cancellato il promemoria**

La sezione 8 di `01_definizioni.md` si intitola *"da rimuovere prima della
consegna"*. La migrazione a `SETUP-19` è avvenuta.

**Deciso:** sezione 8 rimossa. Resta solo `SETUP-19`.

### REV-14 — Ritardo di esecuzione → **nessun ritardo**

Tre affermazioni, di cui la più recente è la revisione v1.6 di `DEF-32`
(*"Non esiste un ritardo prestabilito"*), confermata in modo indipendente da
`CTX-05` in un altro documento. Il paragrafo dei 10 minuti la precede.

**Deciso:** `RITARDO_ESECUZIONE_MINUTI = 0`. L'ingresso è all'apertura di `N3`,
e la tollerabilità di un ritardo la stabilisce `rr >= 1.5` (`GEST-01`,
`CTX-05`), non un timer. I 10 minuti restano solo come `LATENZA_DXY_MINUTI`,
che `CTX-06` conserva esplicitamente per il solo dato DXY.

### REV-13 — Fonte dati sui timeframe bassi → **solo future**

`DEF-32` si contraddiceva. La gerarchia delle precedenze la scioglie da sola:
`PREC-05` dice che le esclusioni battono tutto, e `ESCL-12` vieta di
confrontare un prezzo future con uno CFD. Il meccanismo "rilevo sul CFD e
confermo sul future" è quel confronto.

**Deciso:** ogni OHLC di ogni timeframe viene dal future, come dice la prima
riga di `DEF-32`. La tabella con Capital.com come fonte primaria è rimossa.

**Conseguenza che devi conoscere:** serve il flusso CME anche su `TF_H4` e
`TF_H1`, non solo sui timeframe alti. Il CFD di FP Markets resta esclusivamente
lo strumento di esecuzione.

### REV-17 — Due elenchi di esclusioni → **unione**

`CTX-01` e `SETUP-15` chiudono entrambi con *"in tutti questi casi si applica
PRIN-99"*. Quando due elenchi di **motivi per non operare** differiscono,
l'unione è l'unica lettura coerente con il default che li governa.

**Deciso:** il motore applica l'unione delle undici condizioni di `CTX-01` e
delle dieci di `SETUP-15`. Tredici condizioni distinte in tutto.

### REV-19 — `CTX-07` contro `DEF-26` → **entrambe, su piani diversi**

`CTX-07` parla di **buchi** nello storico: un timeframe con candele mancanti
resta utilizzabile. `DEF-26` fissa un **pavimento**: sotto tre candele chiuse
dentro il lookback, quel timeframe non produce nulla. Non si contraddicono, e
`CTX-07` lo dice già nella sua ultima frase.

**Deciso:** nessuna esclusione per buchi; pavimento di `DEF-26` sempre attivo.

### REV-20 — `CTX-08` contro `CTX-10` → **ricalcola, poi opera**

`CTX-08` vieta un **periodo di osservazione**: il bot non aspetta candele
nuove prima di operare. Non vieta di calcolare da candele che esistono già.

**Deciso:** all'avvio il motore ricostruisce bias, key level, gap e target da
tutto lo storico disponibile, poi si dichiara pronto. Il ricalcolo è
istantaneo e non è un riscaldamento: `CTX-08` e `CTX-10` sono entrambe
rispettate. Se lo storico non basta per un timeframe, quel timeframe tace
(`DEF-26`).

### REV-16 — Chiusura della candela annuale → **sessione ETH**

`DEF-03` si dichiara *"conseguenza vincolante"* e `PREC-03` mette il future al
comando. In `DEF-18` la stringa "31 dicembre, 24:00 UTC" è fra parentesi: è
un'illustrazione, non la regola. La regola è *"alla chiusura della candela
`TF_12M`"*.

**Deciso:** tutte le candele, annuale compresa, seguono i confini di sessione
ETH dell'exchange. La parentesi è stata rimossa da `DEF-18`.

### REV-15 — `TF_H12` e `TF_H6` nella scansione del gap → **inclusi**

`DEF-31` affronta la domanda in modo esplicito e specifico (*"entrano
nell'ordine di scansione di DEF-13... subito sotto TF_1D"*). L'elenco dentro
`DEF-13` è l'enumerazione più vecchia.

**Deciso:** l'ordine di scansione è `TF_12M, TF_6M, TF_3M, TF_1M, TF_1W,
TF_1D, TF_H12, TF_H6`. Elenco corretto dentro `DEF-13`.

### REV-11 — CRT su `TF_H12` e `TF_H6` → **vietato**

`SETUP-10` li include in una riga che comincia con *"Esempio conforme:"*.
`SETUP-05` li esclude con una regola e una motivazione (*"servono solo ai gap,
non sono timeframe di allineamento"*). Un esempio non batte una regola.

**Deciso:** su `TF_H12` e `TF_H6` si rilevano gap e nient'altro (`DEF-31`).
Nessun CRT, nessun ingresso. L'esempio di `SETUP-10` è stato corretto.

### REV-22 — Quale condizione di `SETUP-05` → **i due timeframe superiori**

`SETUP-05` contiene due blocchi. Il secondo è introdotto da **"Numero
minimo."**, che è esattamente ciò a cui si riferiscono `CTX-01` #4 e
`SETUP-15` quando dicono *"meno di 2 timeframe allineati"*. Il primo blocco
definisce il **termine** "allineati", usato dal campo `tf_allineati` di
`07_casi.md`.

**Deciso:** il cancello di ingresso è la regola dei due timeframe
immediatamente superiori che hanno sbilanciato un key level nella direzione
dell'operazione. La prima definizione resta come vocabolario per l'annotazione.

### REV-23 — Key level su `C1` o `C0` → **`C1`**, e non era una scelta

Il `DEF-38` riscritto in v1.8 confronta `high[C0] > KL_max_TF`. Se
`KL_max_TF` venisse da `C0`, il confronto sarebbe `high[C0] > high[C0]`:
sempre falso, regola vuota. Solo con `C1` la presa di un key level significa
qualcosa.

**Deciso:** `C1`, come dice la lettera di `DEF-36`.

### REV-26 — "conferma il pattern" → **CRT formato nella stessa direzione**

"Pattern" ha un significato fisso in questi documenti. `00_principi.md` §1:
*"Ciò che cambia da un timeframe all'altro non è il pattern, ma il contesto"*,
riferito alla CRT. `PRIN-01` parla di *"un CRT formato correttamente"*.

**Deciso:** un timeframe conferma quando vi si è formato un CRT nella
direzione dell'operazione (`SETUP-02A`/`SETUP-02B`). Il target si estende al
key level di quel timeframe.

### REV-27 — Due gap attivi → **vince il timeframe più alto**

`DEF-13` lo dice per la selezione (*"Il timeframe più alto vince sempre sul
timeframe più basso"*) e `PREC-02` lo dice in generale.

**Deciso:** fra `gap_attivo_long` e `gap_attivo_short`, il gap target è quello
sul timeframe più alto. A parità di timeframe, quello formato più di recente
(`DEF-13` passo 3).

### REV-28 — `TF_riferimento`: gap o key level → **lo decide il tipo di ingresso**

La risposta era nella domanda. `DEF-30` dice *"a seconda di quale abbia
generato il contesto operativo"*, e i due contesti sono regole distinte:
`SETUP-09` è l'ingresso su gap, `SETUP-02`/`SETUP-03` l'ingresso su key level.
`SETUP-10` conferma che sono due regimi diversi (*"Per i gap il CRT può
formarsi anche sullo stesso timeframe del gap. Per i key level invece deve
stare su un timeframe strettamente inferiore. Sono due regole diverse"*).

**Deciso:** ingresso da gap → riferimento è il gap. Ingresso da key level →
riferimento è il key level.

### REV-29 — "direzione del gap" in `DEF-42` → **polarità**

`DEF-42` valuta il gap **nel momento in cui si forma**, con `P3 = C0`. In quel
momento la direzione operativa di `DEF-15bis` non esiste ancora: dipende da
dove sarà il prezzo rispetto alla zona, e il prezzo l'ha appena lasciata. Le
conseguenze descritte confermano la polarità: *"il gap tende a restare non
mitigato e a promuoversi su TF superiore"* descrive un gap rialzista con una
candela rialzista confluente.

**Deciso:** polarità del gap (`DEF-10`/`DEF-11`).

### REV-31 — Timeframe dell'RSI → **quello del gap**

`DEF-44` lo scrive come assegnazione (`rsi_timeframe = timeframe del gap`) e
costruisce i due punti di confronto sul modello delle fasi, che vive sul
timeframe del gap. La riga del vocabolario è una didascalia.

**Deciso:** RSI(14) sul timeframe del gap. Riga del vocabolario corretta.

### REV-43 — Le fasi del gap → **sorveglianza (1-3), calcolo (4)**

`DEF-45` definisce sorveglianza come *"verificare se un livello GIÀ FISSATO da
un calcolo precedente è stato toccato"*. `zona_gap` ed `estremo_fase1` sono
esattamente questo. Le fasi 1, 2 e 3 rientrano nella definizione che `DEF-45`
si è data. La fase 4 richiede un CRT, che è calcolo su candele chiuse.

**Deciso:** `DEF-43` aggiunto all'elenco delle regole di sorveglianza, con la
fase 4 esplicitamente esclusa. Testo di `DEF-43` invariato: era già corretto.

### PA-31 — Il preambolo di `DEF-21` → **vale per il solo rifiuto forte**

Il preambolo dice che il rifiuto richiede due condizioni. Le due definizioni
sotto dicono altro: il semplice non ha la spike, il forte sì. Il preambolo
descrive il forte e generalizza per errore.

**Deciso:** `DEF-16` passi 4 e 5 usano il rifiuto **semplice**, senza soglia
sulla spike, come scritto nella definizione. Preambolo corretto.

### PA-05 — Bias propria di `XAUUSD` → **`SETUP-06` senza il passaggio DXY**

`PRIN-09` dice che l'oro non deriva la direzione dal DXY. Non serve una regola
in più: serve una regola in meno. Per l'oro si salta `SETUP-19` e
`bias_comando` si calcola con `SETUP-06` applicato a `GC`, come per qualsiasi
altro strumento. Tutto il resto è identico.

**Deciso:** nessun filtro DXY su `XAUUSD`.

### PA-51 — Setup non confermato in tempo → **scade, non si recupera**

`SETUP-16` dà già il modello per un setup non eseguito: *"NON viene recuperato
quando il limite si azzera"*.

**Deciso:** in modalità `semi`, se la conferma non arriva prima dell'apertura
di `N3` il setup decade e si archivia con esito `scaduto`. Nessun recupero.

**Nota operativa che resta vera:** su `TF_H1` la finestra è di secondi. La
modalità `semi` è praticabile da `TF_1D` in su. Non è un difetto del codice.

### PA-47 — Stop aggressivo con gap invalidato → **nessuna azione**

`GEST-06` secondo caso già lo dice: *"nessuna azione automatica"*. Le
alternative sono precluse: portare a break even prima di `TP1` violerebbe
`GEST-03` ed `ESCL-08`.

**Deciso:** la posizione resta com'è, con il suo stop iniziale.

### PA-48 — Target consumato prima di `TP1` → **si ricalcola il target**

`DEF-29` dà il modello: quando un target è raggiunto, *"si riesegue DEF-22 per
determinare il target successivo"*.

**Deciso:** se il target viene consumato prima di `TP1`, si riesegue
`SETUP-14`/`GEST-08` per il target successivo. La posizione resta aperta con
lo stop iniziale. Se non esiste un target successivo, `PRIN-99`: si chiude a
mercato.

### PA-60 — `SETUP-14` usa i key level come target → **corretto, lo dice `DEF-46`**

`DEF-46`, introdotta in v1.8, formalizza esattamente questo:
`target_di(TF) = key level del timeframe immediatamente superiore`. Esistono
due target distinti e leciti: quello globale di `DEF-22` su livelli
strutturali per `tf_comando`, e quello della posizione su key level.

**Deciso:** nessun conflitto. La frase di `DEF-36` è stata qualificata.

### PA-44 — Soglia "vicini/distanti" → **tutto categoria C, per ora**

`GIUD-01` ha già la propria via d'uscita: *"REGOLA DI USCITA: se C, il target
resta al key level e non si estende al gap."*

**Deciso:** finché la soglia non esiste, ogni caso è C. Il target resta al key
level. Il motore registra comunque `distanza_kl_gap`, `atr_tf` e `rapporto`
per ogni decisione, che è ciò che serve a chiudere `PA-44` con i dati.

Nessun numero inventato, e il comportamento è quello conservativo previsto dal
documento.

---

## 2. Giudizi

Qui i documenti tacciono. Queste sono scelte mie.

### REV-32 — Soglia del corpo in `DEF-41` → **0.05**

Il testo della regola dice 0.05, `PA-29` chiede di confermare 0.10. Il testo
della regola è normativo, il punto aperto è un promemoria. E 0.05 è la soglia
**più selettiva**: produce meno candele di indecisione, quindi meno
`mitigazione_attesa = true`, quindi meno ingressi da gap. Per il criterio dei
pareggi, vince.

**Rischio se sbaglio:** perdi qualche ingresso su doji larghi. Cambia
`"REV-32": "0.10"` per invertire.

### REV-03 — Scala del rischio su `XAUUSD` → **si applica, per gruppo di correlazione**

`RISK-02` si intitola *"Rischio ridotto in caso di correlazione piena"* ed
esclude l'oro perché non è correlato alle cinque coppie. Ma `RISK-06` ammette
quattro posizioni **sullo stesso strumento**, e quelle quattro sono correlate
fra loro in modo totale: sono lo stesso strumento.

**Deciso:** `n` si conta dentro il gruppo di correlazione. Per le cinque coppie
forex il gruppo sono tutte insieme; per `XAUUSD` il gruppo sono le sue
posizioni. Così l'oro è coperto dalla scala e si ferma a 1,80% invece di
arrivare al 4,00% che `RISK-01` secco produrrebbe.

**Rischio se sbaglio:** rischi meno del previsto sull'oro. Cambia
`"REV-03": "rischio_pieno_risk01"` per il comportamento letterale di `RISK-01`
— ma guarda prima che quattro posizioni al 4,00% superano il limite
giornaliero di `RISK-07` prima ancora di aver perso un euro.

### REV-30 — Le fasi 2 e 3 di `DEF-43` → **uscita dal lato di entrata, condizioni sequenziali**

*"Esce nella direzione contraria"*: contraria all'aggressione. Il prezzo entra
in zona da un lato ed esce dallo stesso lato. È l'unica lettura che rende
coerente il nome della fase 2, *automatic reaction*: una reazione è un
ritorno indietro.

Fase 3: *"rientra"* e *"supera estremo_fase1"* sono **sequenziali**, non
simultanee. Prima il rientro, poi il superamento — che può portare il prezzo
fuori dalla zona, ed è normale: la fase 3 è definita dallo sbilanciamento
dell'estremo, non dalla permanenza in zona.

**Rischio se sbaglio:** le fasi scattano nel momento sbagliato e con esse gli
ingressi da gap. È il giudizio su cui sono meno tranquillo di tutti: se hai un
grafico in cui hai visto le quattro fasi, guardalo e dimmi se torna.

### PA-15 — Conferma dei correlati → **solo statistica**

Nessun documento la rende una condizione, e non esiste un criterio scritto
(quali future, con quale soglia). Un filtro senza criterio non è
implementabile senza inventarlo.

**Deciso:** si registra l'allineamento dei correlati per ogni decisione, non
blocca nulla. `RISK-05` già copre la logica fra strumenti.

### PA-63 — Ridimensionamento non eseguibile → **non si apre la nuova posizione**

Se adeguare le posizioni esistenti non riesce (passo minimo del broker,
chiusura parziale rifiutata), aprire comunque la nuova produrrebbe
un'esposizione fuori scala e non dichiarata.

**Deciso:** la nuova posizione non si apre. Le esistenti restano come sono.
Coerente con `RISK-11` e `PRIN-99`.

### PA-46 — `buffer_be` → **2 volte lo spread corrente**

`GEST-04` dice che il buffer deve coprire spread e commissioni perché il
pareggio sia reale. Un numero fisso per strumento invecchia; lo spread lo
sappiamo al momento.

**Deciso:** `buffer_be = 2 × spread` letto da MT5 all'istante del passaggio a
break even. Il fattore 2 è mio.

### PA-54 — Calendario news → **file locale, letto a ogni valutazione**

Nessuna dipendenza nuova, nessuna chiamata di rete nel percorso critico.

**Deciso:** il motore legge `dati/news.csv` (data e ora UTC, valuta, impatto).
Se il file manca, è vuoto o è più vecchio di 24 ore, si applica `PA-55`:
astensione. Come lo si popola resta una scelta tua — a mano, o con uno script
separato che non fa parte del motore.

---

## 3. Misure

### PA-62 — Il fattore `k` non può essere una costante, e `DEF-47` va corretta

Questa merita più di una riga, perché la soluzione proposta da `DEF-47` è
sbagliata in matematica, non in forma.

`6E`, `6B`, `6A` e `GC` quotano la stessa cosa dei rispettivi CFD, nella stessa
scala: `k = 1`.

`6J` e `6S` no. `6J` quota dollari per yen (circa 0,0068), `USDJPY` quota yen
per dollaro (circa 147). Sono **reciproci**. E la derivata del reciproco non è
costante:

```
y = 1/x   →   dy = −dx / x²
```

Una distanza fissa su `6J` corrisponde a una distanza su `USDJPY` che
**dipende dal livello di prezzo**. Nessun numero in tabella può essere
corretto per più di un istante. Con `k` fisso la size su `USDJPY` e `USDCHF`
sbaglierebbe tanto più quanto più il prezzo si allontana dal punto in cui `k`
è stato misurato.

**Deciso — distanza relativa invece di fattore di conversione.**

```
Passo 1  Sul future, distanza di stop in forma adimensionale:
         r = |chiusura_N2_future − stop_future| / chiusura_N2_future

Passo 2  Sul CFD, distanza in punti:
         distanza_cfd = r × prezzo_cfd_corrente

Passo 3  size_lotti = (equity × rischio_operazione) / (distanza_cfd × valore_punto)
         con valore_punto letto da MT5, non da tabella
```

Perché funziona: `r` è un numero puro, non un prezzo. Non c'è confronto fra
future e CFD, quindi `ESCL-12` è rispettata. E per una relazione reciproca una
variazione relativa `r` sul future corrisponde a una variazione relativa `r`
sul CFD, al primo ordine, con il segno invertito — che è esattamente ciò che
serve, perché il segno lo gestisce già `DEF-33`.

Perché è meglio di una tabella: niente numeri da misurare e da rimisurare,
niente da aggiornare quando il prezzo si muove, e `valore_punto` arriva da
`symbol_info` di MT5 che è la fonte autorevole per il conto su cui operi.

`PA-62` è chiuso. `DEF-47` va riscritta di conseguenza: la riscrittura la
lascio a te perché cambia una regola, non un residuo.

**Approssimazione dichiarata:** al primo ordine. Su uno stop dell'1% l'errore
è dell'ordine dell'1% della size, cioè lo 0,01% di equity su un rischio
dell'1%. Trascurabile. Su uno stop del 10% diventa visibile, ma uno stop del
10% ha altri problemi.

### PA-53 — Festività → **calcolate, non tabellate**

Sei delle dodici date sono mobili e la tabella scade il 1° gennaio 2027.

**Deciso:** il motore calcola le festività USA a data mobile con le loro regole
(n-esimo lunedì del mese, Venerdì Santo dal computus di Gauss per la Pasqua,
osservanza al venerdì o al lunedì per le date fisse che cadono nel fine
settimana). `PA-53` si chiude per sempre invece che ogni gennaio.

Verificato contro la tabella 2026 di `CTX-04`: le dodici date coincidono.

---

## 4. Cosa resta aperto, e perché

| ID | Perché non l'ho deciso |
|---|---|
| `PA-33` | Tetto di rischio aggregato: è una scelta di quanto vuoi rischiare, non una contraddizione. Con il ridimensionamento l'esposizione massima è 2,25% per gruppo, e i limiti di `RISK-07/08/09` reggono. Se vuoi un tetto, dimmi il numero |
| `PA-34` | Se un limite di perdita debba chiudere le posizioni aperte: cambia il profilo di rischio, non risolve un'ambiguità. `RISK-10` una scelta l'ha già fatta |
| `PA-37` | Rischio di apertura domenicale: `AMM-04` e `RISK-14` hanno già deciso di accettarlo |
| `PA-38` | Perdita del flusso dati: architettura, non regola. Va deciso quando il motore gira davvero |
| `PA-50`, `PA-52` | Passaggio fra le fasi e vincoli prop: fuori dal motore |
| `REV-21` | `PRIN-16` contro `SETUP-04`: risolto sul piano tecnico da `PA-51`, ma la decisione se usare `semi` sotto `TF_1D` resta tua |

---

## REV-46 — SETUP-05: la direzione confrontata è quella dello spazzamento

**Classificazione: RICOSTRUZIONE.** La risposta era nei documenti: bastava
leggere insieme `SETUP-02A` e `DEF-38`.

**Il problema.** `SETUP-05` scrive che i due timeframe immediatamente
superiori devono aver sbilanciato un key level *«nella direzione
dell'operazione»*. Tradotto alla lettera — `sbilanciamento == direzione` — il
cancello non si apre mai, e si dimostra:

- `SETUP-02A` costruisce un CRT short sopra un `KL_max`, che `N2` supera
  verso l'**alto**;
- `DEF-38` chiama quella una presa a **rialzo**, che
  `sbilanciamenti_per_timeframe` registra come `LONG`;
- `DUE_TF_SUPERIORI` garantisce che il timeframe che ha generato quel livello
  sia uno dei due interrogati da `SETUP-05`.

Quindi la condizione chiede che `LONG` sia uguale a `SHORT`.

**La misura.** Sui prezzi reali archiviati — sei strumenti, 11.005 CRT
formati, 298 sopravvissuti a `GEST-01` — la condizione letterale si è
verificata **zero volte**. Non è una rarità statistica: è una
contraddizione.

**La decisione.** Il confronto avviene con la direzione dello **spazzamento**,
che è l'opposto dell'operazione. I due timeframe superiori devono aver
spazzato dalla stessa parte, e l'operazione è la reazione contraria a quello
spazzamento — che è il meccanismo stesso del CRT.

Il valore della regola resta intatto: *i due superiori devono essere
d'accordo*. Cambia il verso del confronto, non il vincolo. Nessuna soglia è
stata toccata: `RR_MINIMO` resta 1.5, `GEST-01` resta com'è, il CRT conserva
tutte e quattro le condizioni.

**Risultato misurato dopo la correzione:** 56 setup operabili su sei
strumenti in 2,4 anni di dati orari, circa **due al mese** in totale.

**Perché i test non lo avevano visto.** Le prove su `allineamento_soddisfatto`
costruivano `sbilanciamenti` a mano, già concordi con l'operazione: uno stato
che la catena reale non può produrre. Aggiunta
`test_setup05_il_crt_produce_davvero_lo_stato_richiesto`, che parte da un CRT
vero e verifica quale stato ne discende, collegando le due regole invece di
assumerle.

---

## REV-47 — Il gap target non è una zona di ingresso

**Classificazione: RICOSTRUZIONE.** `DEF-15bis` assegna al gap due ruoli e
chiude vietando di confonderli. Il motore li confondeva.

**Il problema.** `motore.valuta` passava a `SETUP-09` e `SETUP-10` il gap
restituito da `gap_target`, cioè il gap attivo sul **timeframe più alto**
(`DEF-13`). Ma `DEF-15bis` dice che quel gap è un **target**, e che le zone in
cui cercare l'ingresso sono i gap sui timeframe **inferiori** al suo.
`SETUP-09` lo ripete nella sua prima riga: *«si applica quando il prezzo
interagisce con una `zona_gap` di timeframe inferiore a quello del gap
target»*.

**La conseguenza, misurata.** `doppio_ingresso` è un semplice confronto fra
timeframe: un CRT su `TF_H1` non è mai più alto di un gap su `TF_12M`, quindi
risultava «a supporto del gap» **sempre**. E poiché il prezzo non entra quasi
mai nella zona di un gap annuale, `gap_fase` restava 0 e `SETUP-09` bloccava
l'ingresso. Sull'archivio reale dell'oro: **3.237 CRT formati, 3.237
bloccati**. Nessuna operazione possibile, su nessuno strumento, mai.

**La decisione, in due parti.**

1. Aggiunta `stato.gap_di_reazione`, che seleziona con le regole di `DEF-13`
   fra i soli gap di timeframe **strettamente inferiore** a quello del gap
   target, e solo con la polarità concorde alla bias operativa — come
   `DEF-15bis` prescrive. La `Fotografia` porta ora due campi distinti:
   `gap_attivo` (il bersaglio) e `gap_reazione` (la zona). `SETUP-09` e
   `SETUP-10` leggono il secondo.
2. `SETUP-09` si applica solo se il prezzo **sta interagendo** con quella
   zona, cioè `gap_fase > 0`. È la prima riga della regola, e non era mai
   stata verificata: `doppio_ingresso` confronta timeframe, non posizioni del
   prezzo. In fase 0 la zona non è stata toccata, il CRT è un CRT normale e
   non c'è nessun doppio ingresso da dimezzare (`RISK-04` parla di un CRT
   *«a supporto di un gap»*, non di un CRT che ha un gap da qualche parte
   sopra di sé).

Nessuna soglia toccata. Il modello a fasi di `DEF-43` resta obbligatorio dove
serve davvero: quando si entra *dentro* una zona di reazione.

---

## REV-48 — Senza key level su `TF_H4`, `TF_H1` non è eseguibile

**Classificazione: CONTRADDIZIONE FRA DOCUMENTI.** Tre regole che non stanno
insieme, e una lettura che le tiene tutte.

**Il problema.**

- `DEF-36` elenca i timeframe che hanno key level e si ferma a `TF_1D`:
  `TF_12M`, `TF_6M`, `TF_3M`, `TF_1M`, `TF_1W`, `TF_1D`.
- `SETUP-05` scrive però una riga esplicita per `TF_H1`, che per operare
  pretende lo sbilanciamento di un key level di **`TF_H4`**.
- `PRIN-10` mette `TF_H4` e `TF_H1` fra i timeframe di **esecuzione**.

Un timeframe che non ha key level non può sbilanciarne uno. Quindi la riga
`TF_H1` di `SETUP-05` non è soddisfabile, e `TF_H1` non è eseguibile —
contraddicendo `PRIN-10`. È la stessa forma di `REV-46`, un piano più in
basso: una regola scritta per un oggetto che la regola vicina non produce.

**La decisione.** I key level si calcolano anche su `TF_H4`, con la stessa
formula di `DEF-36` applicata alla sua `C1` (`TF_KEY_LEVEL` in
`parametri.py`). È il cambiamento più piccolo fra quelli possibili: l'altro
sarebbe stato dichiarare `TF_H1` non operabile, cioè cancellare una riga di
`SETUP-05` e mezza riga di `PRIN-10`.

`TF_H12` e `TF_H6` restano fuori (`DEF-31`, `REV-11`) e `TF_H1` non produce
key level propri: sotto di lui non c'è nessun trigger da servire.

**Conseguenza operativa.** Serve davvero avere le candele `TF_H4`. La fonte
gratuita non le serve, quindi `scarica_storico.py` le costruisce dalle orarie
(`aggregazione.aggrega_orarie`) e `core/mercato.py` le tiene aggiornate. Sono
blocchi ancorati all'orologio UTC, non alla sessione: coincidono con il
confine giornaliero della fonte d'inverno e sbagliano di un'ora durante l'ora
legale americana. Dal vivo le `TF_H4` vere arrivano dagli alert di
TradingView e prendono il posto di queste; chi vuole i confini esatti fin da
subito importa lo storico dal CSV di TradingView.

---

## REV-49 — Il target del 75% residuo non è TP1

**Classificazione: RICOSTRUZIONE.** `SETUP-14` dice esattamente qual è, e lo
dice con un esempio numerico.

**Il problema.** `motore.valuta` costruiva l'ordine con
`target_finale = TP1`. Ma `TP1` è il livello a cui `GEST-07` chiude il **25%**
della posizione. Con i due valori uguali il 75% residuo si chiude nello stesso
istante del parziale, e quattro regole diventano lettera morta:

- `GEST-04` chiude un quarto e porta a break even un residuo che non esiste;
- `GEST-05` protegge quel residuo;
- `GEST-08` e `SETUP-14` estendono un target già consumato.

**Cosa dice il documento.** `SETUP-14`: *«Il target del 75% residuo è il key
level del timeframe più alto disponibile nella direzione dell'operazione»*, e
l'esempio conforme dice da dove parte: *«CRT su `TF_H4`, ingresso short.
**Target iniziale sul key level `TF_H4`**. Alla chiusura di `TF_1D`, se il
giornaliero conferma il pattern, il target si estende al minimo `TF_1D`»*.

**La misura che l'ha fatto emergere.** Il backtest del 15 settembre: 50
operazioni, **zero** pareggi e **una** sola estensione del target. Le
posizioni morivano nella barra successiva all'ingresso, perché stop e
bersaglio erano entrambi dentro il range immediato. Un pareggio richiede un
residuo da proteggere, e il residuo non esisteva mai.

**La decisione.** Aggiunta `setup.target_iniziale`, che restituisce il key
level del timeframe del CRT nel verso dell'operazione — `KL_min` per una
short, `KL_max` per una long. Per un CRT su `TF_H1`, che non ha key level
propri (`DEF-36`, `REV-48`), si sale di un gradino: è quanto `DEF-46`
prescrive per `TF_H1`. Se nessuno dei due esiste non si apre: `PRIN-99`, una
posizione senza bersaglio non ha ragione di esistere.

Il controllo sta **dopo** `verifica_divieti`, non prima: `PREC-05` vuole le
esclusioni come ultimo controllo, e un'astensione che le scavalcasse
nasconderebbe il motivo vero per cui quell'ordine non andava mandato.

**Cosa cambia e cosa no.** Non cambia nessun ingresso: gli stessi CRT passano
gli stessi filtri, `GEST-01` continua a misurarsi su `TP1` come vuole la sua
formula, il winrate sui primi obiettivi resta quello. Cambia solo la **coda
destra**: dove prima ogni vincita valeva `R(TP1)`, ora un quarto vale
`R(TP1)` e tre quarti corrono fino al key level, che su uno short è il minimo
di `N1` — cioè circa il doppio della distanza.

La `Fotografia` porta ora `key_level_correnti` accanto a `key_level_presi`:
`SETUP-14` non chiede che il livello sia stato spazzato, chiede che esista.
