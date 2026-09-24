# La bibbia del CRT

> *«Io voglio la strategia di romeotpt scritta come se fosse la bibbia e il
> codice la deve rispettare a 360 gradi non una virgola di meno.»*

Questo documento è la **specifica normativa**. Non descrive cosa il bot fa:
descrive cosa il bot **deve** fare. Dove il codice diverge, la divergenza è
scritta qui sotto con nome e cognome, non nascosta.

Ogni regola ha un ID `CRT-nn`, una formulazione imperativa, la fonte da cui
viene, e lo stato. Gli stati sono quattro e uno solo è buono:

| Stato | Significa |
|---|---|
| **VIVA** | implementata **e** raggiungibile dal percorso di produzione |
| **MORTA** | implementata ma nessuno la chiama — la classe di errore di `DEF-33` |
| **ASSENTE** | mai scritta |
| **CONTRARIA** | il codice fa qualcosa, ma non quello che la regola dice |

«Implementata e collaudata» non è uno stato. `DEF-33` era implementata, aveva
cinque test verdi, ed era morta: su `USDJPY` e `USDCHF` gli ordini sarebbero
partiti rovesciati. Lo stato lo assegna `audit_regole.py`, non la lettura.

## Fonti

Il CRT è di [@Romeotpt](https://en.rattibha.com/thread/1782691074739241159).
La codifica in 57 regole viene da
[CandelaCharts](https://www.candelacharts.com/blog/candle-range-theory-crt),
integrata con [WritOfFinance](https://www.writofinance.com/candle-range-theory-crt/),
[GrandAlgo](https://grandalgo.com/blog/crt-trading-strategy-candle-range-theory)
e [TradingFinder](https://tradingfinder.com/education/forex/ict-candle-range-theory/).

Il CRT è l'applicazione del **Power of Three** di ICT (Accumulazione,
Manipolazione, Distribuzione) con ingresso **Turtle Soup** — Linda Raschke,
*Street Smarts*, 1995. Chi conosce quei due riconosce tutto.

---

## 1. Il ciclo

### CRT-01 — Ogni range vive tre fasi
Ogni candela di timeframe superiore è un **range** che attraversa
accumulazione, manipolazione e distribuzione. Non sono tre candele: sono tre
momenti dentro una candela sola, visibili sul timeframe inferiore.

**VIVA** — `core/setup.py: cerca_crt`. Il modello a due candele di `SETUP-01`
è la lettura di questo: `N1` è il range, `N2` è manipolazione e distribuzione.

### CRT-02 — Il massimo e il minimo del range sono liquidità
`CRT-High` e `CRT-Low` non sono resistenza e supporto: sono i luoghi dove
stanno gli stop degli altri, e per questo il prezzo ci va.

**VIVA** — `core/definizioni.py: key_level_di`, `TipoKeyLevel.MAX/MIN`.

### CRT-03 — Il 50% del range è il bersaglio primario
Dopo lo sweep il prezzo torna al 50% del range manipolato.

**VIVA** — `core/gestione.py: tp1` (`liv_50` applicato a `N1`), collegata alla
sentinella dal 16/09.
**MISURATA**: è il livello che il mercato raggiunge più spesso. Vedi
`docs/MISURA-DEFINITIVA-2026-09-16.md`.

---

## 2. I timeframe

### CRT-04 — Il CRT è una coppia di timeframe, non tre candele
Un CRT si legge **sempre** su due timeframe: il range sta sull'alto, lo sweep
e l'ingresso sul basso. Le coppie canoniche sono:

```
5m → 15s      15m → 1m      1h → 5m      4h → 15m
D  → 1h       W  → 4h       M  → D
```

**VIVA** — `SETUP-01` è stata riscritta (REV-50) proprio perché descriveva tre
candele dello stesso timeframe, che è un'altra strategia.
**PARZIALE**: il bot opera su `TF_H1`, `TF_H4`, `TF_1D` (`TF_OPERATIVI` in
`core/mercato.py`). Le coppie sotto l'ora richiedono dati a 15 secondi e a 1
minuto che l'archivio non ha.

> **DIVERGENZA MISURATA.** Ho testato `W1→D1` e riportato il risultato
> migliore su quella coppia. `W1→D1` **non è una coppia di Romeo**: la sua è
> `W1→H4`. Il numero che ho dato riguarda una coppia che la strategia non
> prescrive. `W1→H4` non è ancora stata misurata.

### CRT-05 — Il flusso va dall'alto verso il basso
Il timeframe alto dà la direzione, l'intermedio valida, il basso esegue. Non
si esegue mai contro l'alto.

**VIVA** — `core/setup.py: bias_comando` (SETUP-06) e `direzione_concorde`
(SETUP-07).

### CRT-06 — Tre modelli CRT allineati danno l'accuratezza massima
`1h/5m` + `4h/15m` + `D/1h` che puntano nella stessa direzione.

**Nel motore dal 2026-09-23** (`core/setup.py: crt06_allineamento`), che dal
24/09 deriva da `quanti_modelli_allineati`: prima reimplementava il conteggio
inline mentre `modelli_allineati` — quella citata qui sotto — non la chiamava
nessuno. **La gradazione non entra ancora nella Fase 2**: il responso delle
conferme è booleano, e finché non c'è un canale numerico accanto si perde
proprio l'informazione che questa regola indica come il punto.

**SCRITTA** — `core/setup.py: modelli_allineati`. Non ancora misurata:
richiede di incrociare tre coppie sullo stesso istante. Delle tre coppie che
le fonti nominano, **una sola** è esprimibile coi timeframe che DEF-01 ammette.

---

## 3. Lo sweep

### CRT-07 — Il prezzo deve spazzare un estremo e rigettarlo
Non basta toccare: deve **superare** `CRT-High` o `CRT-Low` e **richiudere
dentro** il range.

**VIVA** — `core/setup.py: cerca_crt`.

> **DIFETTO CORRETTO.** `backtest/romeo_completo.cerca` escludeva il caso più
> comune — la barra che spazza *e* richiude dentro nella stessa barra. Il
> conteggio dei segnali crollò da 5.265 a 2.591 e fu così che me ne accorsi.

### CRT-08 — Lo sweep deve avvenire su una PD Array del timeframe alto
FVG, Order Block o Breaker. Uno sweep nel vuoto non è un CRT.

**PARZIALE.** Il FVG c'è (`core/definizioni.py: gap`, famiglia `DEF-43`/`DEF-45`).
**Order Block e Breaker: ASSENTI.**
**MISURATA**: il filtro FVG *peggiora* il risultato sul campione disponibile.

### CRT-09 — L'ingresso è un Turtle Soup
Raid su un pool di liquidità significativo, poi rientro. È Raschke, 1995.

**VIVA** — `SETUP-02A`/`SETUP-02B`.

### CRT-10 — Double Purge Sweep
Una candela che rompe **entrambi** i lati del range e richiude dentro è la
forma più forte del pattern.

**Corretta il 2026-09-24.** Riceveva `n2`, la candela **sintetica** creata
dalla riscrittura di `SETUP-02` del 23/09, che impacchetta un lato solo della
manipolazione: un double purge — che chiede *entrambi* i lati spazzati — non
poteva risultare mai. Su 226 decisioni reali ha risposto `None` 226 volte.
Adesso guarda le barre **vere** della fase, una per una.

**SCRITTA E MISURATA — non regge.** `core/definizioni.py: double_purge`,
`verso_del_double_purge`. 88,7% di winrate e R **negativa**: tante vittorie
piccole e poche perdite grandi. La variante *concorde*, quella che segue il
verso della regola, è **peggiore della base** (−1,4σ). È il caso in cui il
winrate inganna e l'R dice la verità.

---

## 4. La conferma

### CRT-11 — Dopo il raid serve un CISD sul timeframe basso
Change In State Of Delivery: il primo segno che la consegna ha cambiato verso.

**SCRITTA E MISURATA — è l'unica che regge.** `core/definizioni.py: cisd`.

Avevo implementato l'**MSS**, che chiede la rottura di uno swing strutturale
mentre il CISD chiede la rottura dell'ultima serie di consegna opposta. Lo
swing sta più lontano, quindi **l'MSS arriva sempre dopo**: a prezzo peggiore,
e a volte mai.

Il CISD moltiplica per cinque il vantaggio di base — da +0,017 a **+0,089 R**
su `D1→H1` — e senza di esso il CRT rende **negativo** (−0,045 R). Positivo in
**tutte e sei** le epoche su due coppie indipendenti, placebo a zero (−0,3σ).
Resta comunque sotto il costo dello spread. Vedi
`docs/MISURA-REGOLE-MANCANTI-2026-09-16.md`.

**Nel motore dal 2026-09-23**, come una delle otto conferme
(`core/setup.py: crt11_cisd`). Non è un veto all'armamento — il CISD avviene
dopo la chiusura di `N2`, chiederlo lì vuol dire chiederlo prima che possa
essere successo — ma è obbligatorio all'ingresso: `ingresso_ltf.controlla`
senza CISD non entra mai.

**Il 2026-09-24 la conferma è stata corretta.** Faceva `cisd(...) is not
None`, cioè *«esiste una serie da rompere»* e non *«è stata rotta»*: una
domanda diversa e quasi sempre vera. Il ramo armato lo faceva già giusto, e
per due giorni sono state due implementazioni della stessa regola che
rispondevano a due domande.

### CRT-12 — Divergenza SMT fra mercati correlati
Uno strumento fa un nuovo estremo, il correlato no: è divergenza, e le fonti
la dichiarano **non negoziabile**.

**SCRITTA E MISURATA — non mostra nulla.** `core/definizioni.py:
divergenza_smt`, con le coppie in `COMPAGNE_SMT` e il segno derivato da
`correlazione_positiva` (la stessa proprietà che usa DEF-33, non una seconda
tabella che potrebbe divergere).

+0,5σ, −0,6σ, +0,2σ a seconda della coppia. Non è un errore di
implementazione: i test verificano il segno su coppie positive e negative. È
che su sei strumenti a granularità oraria non si vede. Può darsi che serva la
granularità al minuto su cui Romeo lavora.

Le fonti la dichiarano non negoziabile. I dati dicono di no. Resta scritta,
perché il giorno in cui arrivano dati al minuto la domanda si può rifare.

---

## 5. L'ingresso

### CRT-13 — Si entra sul retest di FVG o Order Block dopo la conferma
Non al mercato: al ritorno sulla zona.

**PARZIALE.** Il FVG c'è ma il percorso è **inerte in produzione**:
`Fotografia.gap_fase` resta 0 perché serve la sorveglianza a tick, e `SETUP-09`
blocca. È dichiarato in `core/fornitore_tradingview.py:324-327`. Order Block:
assente.

### CRT-14 — Non si prende ogni istanza
Il contesto del timeframe alto decide quali istanze valgono. Il CRT non è un
segnale automatico.

**PARZIALE, e per costruzione.** Questa regola dice che serve discrezionalità.
Il bot applica dieci filtri di `CTX-01` e dieci esclusioni di `SETUP-15`, che
sono la sua approssimazione. È il punto da cui parte il lavoro sul bot
discrezionale.

### CRT-15 — Finestre orarie
CRT orario: 2-4, 7-9, 8-10, 20-22 ora di New York. CRT a 4 ore: 1-9 e 13-21.

**SCRITTA E MISURATA — nessuna differenza.** `core/contesto.py:
dentro_finestra_crt`, con l'ora convertita **adesso** e non una volta per
tutte: il fuso di New York cambia due volte l'anno e una tabella in UTC
sarebbe sbagliata per metà anno.

**Nel motore dal 2026-09-23 come veto, e tolta dai veti il 24/09**: fermava
61 decisioni su 238 — un quarto — contro `PRIN-12`, che dice che il sistema è
attivo 24 ore su 24 e non ha fasce escluse. Resta **valutata** e nel responso.

+0,0σ e −0,2σ. Su `D1→H1` quasi tutti i segnali cadono *fuori* dalle finestre,
il che dice che sono pensate per timeframe d'ingresso più bassi di quelli che
il bot può usare. `PRIN-12` non va toccata.

**Nel campo di prova della Fase 1 è una costante: `None` su tutte e 16.463 le
righe.** `FINESTRE_CRT_NY` dà finestre solo ai CRT di range `H1` e `H4`, e le
due coppie con vent'anni di storia hanno range `W1` e `D1`. Non è un difetto
da correggere: è la conferma che CRT-15 vive sulle coppie intraday, cioè
esattamente dove la Fase 1bis deve portare i dati.

---

## 6. I bersagli

### CRT-16 — Primo bersaglio il 50%, poi il lato opposto
**VIVA** — `GEST-07` (TP1) e `SETUP-14` (target del residuo), entrambe
collegate dal 16/09. Fino a quel giorno `target_finale` valeva `TP1`: il
residuo si chiudeva nello stesso istante del parziale e metà dell'apparato di
gestione era lettera morta (REV-49).

### CRT-17 — Espansione nella metà del range, e bias che si ribalta
Il prezzo che tiene la metà alta espande verso l'alto; se la metà cede, la
bias si ribalta.

**SCRITTA — e la prima misura era un lookahead.** `core/definizioni.py:
meta_tenuta`. Filtrando con le candele del timeframe **alto successive a N2**
dava 85,7% di winrate e +15,3σ. Guardando solo ciò che accade **dentro `N2`**,
cioè ciò che si vede davvero al momento dell'ingresso, sparisce del tutto:
meno di 30 campioni in ogni coppia.

È il quinto falso positivo di questo progetto, e tutti e cinque avevano lo
stesso aspetto: un numero troppo bello.

**E il 24/09 si è capito perché sparisce.** Su 16.463 CRT del campo di prova
ha risposto `True` **una volta sola**. Non è debolezza statistica, è
struttura: un CRT *è* lo sweep di un estremo del range, quindi al momento del
rientro le chiusure recenti stanno per forza dalla parte opposta a quella in
cui si entra, e `meta_tenuta` risponde sempre al contrario della direzione.
Come è cablata, CRT-17 può dire solo «no» o «non lo so».

Delle due l'una, e nessuna delle due si può decidere inventando: o CRT-17 non
è una conferma d'ingresso — è una lettura di contesto su un range **già
risolto** — oppure va letta su barre diverse da quelle d'ingresso. Le fonti
non lo dicono, quindi resta misurata e dichiarata così, non riscritta a
intuito.

---

## 7. Le ombre — il blocco più trascurato

### CRT-18 — Il punto medio dell'ombra è un livello
Tenerlo favorisce la continuazione, attraversarlo invalida.

**NEL MOTORE dal 2026-09-23** (`core/setup.py: crt18_meta_ombra`), e
**corretta il 24/09**: la prima versione confrontava `chiusura <= meta_ombra`
della stessa candela, che è una **tautologia** — il punto medio sta fra il
corpo e l'estremo, quindi la chiusura ci sta sempre sotto. Su 226 decisioni
reali ha risposto `True` 226 volte, e una costante non è un segnale.

Il punto medio è un **livello**: adesso si calcola sull'ombra della barra che
ha spazzato e si guarda se le barre successive lo tengono. `None` quando non
ce n'è nessuna dopo — il livello esiste ma nessuno l'ha messo alla prova.

### CRT-19 — Ombre piccole su C2 favoriscono l'espansione
### CRT-20 — Ombre grandi su C2 favoriscono la mean-reversion

**SCRITTE E MISURATE NEI DUE VERSI — il sospetto era fondato, il vantaggio
no.** `core/definizioni.py: peso_ombre`, `meta_ombra`.

Le ombre **piccole** sono peggiori: 33,6% di winrate su `D1→H1` contro il
59,6% della base. Quindi il mio filtro «sweep efficiente», che teneva proprio
quelle, scartava i CRT buoni — il verso del sospetto era giusto.

Ma le ombre grandi non battono la base (−0,1σ, +0,0σ). La conoscenza serve a
non fare la cosa sbagliata, non a guadagnare.

---

## 8. Le tre confluenze non negoziabili

### CRT-21 — HTF PD Array + Turtle Soup + Divergenza SMT
Le fonti sono esplicite: tutte e tre, non una.

**UNA SU TRE.** Turtle Soup c'è. La PD Array c'è a metà (FVG sì, OB e Breaker
no) ed è inerte in produzione. La divergenza SMT è assente.

### CRT-22 — Senza contesto del timeframe alto il CRT è rumore
**VIVA** — `SETUP-06`, `SETUP-07`, `SETUP-15`, `CTX-01`.

---

## 9. Il verdetto

Su 57 regole delle fonti, ricondotte ai 22 punti normativi qui sopra:

| | |
|---|---:|
| VIVE (nel motore) | 9 |
| SCRITTE e misurate, fuori dal motore | 6 |
| PARZIALI | 5 |
| ASSENTI | 0 |
| **di cui MISURATE e che reggono** | **1 — il CISD** |

Non ci sono più regole assenti. Delle otto che mancavano, **sette sono state
misurate** e una sola regge: il **CISD** (`CRT-11`).

Quello che resta da fare, in ordine:

1. **Portare il CISD dentro il motore.** Oggi vive in `core/definizioni.py` e
   non lo chiama nessuno — lo stato esatto in cui si trovava `DEF-33`. Finché
   è così, la misura riguarda una regola che il bot non applica.
2. **Rimisurare il CISD coi costi veri**, per vedere quanto manca alla soglia.
   +0,089 R contro 0,15–0,35 R di spread: manca, ma non di un ordine di
   grandezza come prima.
3. **Misurare `CRT-06`**, i tre modelli allineati — l'unica scritta e non
   ancora provata.
4. **Decidere il conflitto `CRT-04` / `DEF-01`**: quattro delle sette coppie
   di Romeo nominano timeframe che DEF-01 non ammette. O DEF-01 si allarga, o
   il bot opera dichiaratamente su un sottoinsieme del CRT.

---

## 10. Cosa dicono le misure, e cosa non dicono

Vedi `docs/MISURA-DEFINITIVA-2026-09-16.md` per i numeri. In breve, su
1.510.058 candele orarie Dukascopy con BID e ASK veri, 2006–2026:

- il CRT **porta informazione reale**: +3,0σ e +5,1σ sopra il placebo sui
  campioni grandi;
- il vantaggio (~0,05 R) è **un ordine di grandezza sotto il costo dello
  spread** (0,15–0,35 R);
- cambia segno fra le epoche.

**Quei numeri riguardano una versione della strategia a cui manca un terzo
delle regole**, incluse le tre che le fonti dichiarano non negoziabili. Non
sono un verdetto sul CRT di Romeo: sono un verdetto su quello che il bot
sapeva fare a metà settembre.

Prima di dire qualunque altra cosa sul CRT vanno misurate le quattro lacune
qui sopra. In ordine: la divergenza SMT, perché è dichiarata indispensabile ed
è la più facile; poi le ombre nei due versi, perché un segno invertito
spiegherebbe molto.

### 10.1 Il campo di prova della Fase 1 — 2026-09-24

`backtest/campo_prova.py`, 16.463 CRT dal 2006-01-16 al 2023-12-29 su
`W → 4h` e `D → 1h`, holdout 2024–2026 **chiuso**, costi misurati dentro
(spread al 90° percentile per strumento e ora, più la commissione misurata di
4,06 EUR/lotto). Un CRT per candela di riferimento, preso **alla barra in cui
si forma**.

**B0 — prendere tutti i CRT: −0,0509 R ± 0,0162.** È la linea che la Fase 2
deve battere di ≥0,10 R. Target 35,9%, stop 63,3%, scaduti 0,8%. Rapporto
mediano 2,21 R, che è dentro l'intervallo «da 1,85 a 3,92 R» delle fonti
(SETUP-02C).

Per coppia: `W → 4h` +0,0086 ± 0,0438 (indistinguibile da zero), `D → 1h`
−0,0623 ± 0,0173 (negativo).

**Tre conferme su otto non portano informazione su queste coppie:**

| regola | risposte | nota |
|---|---|---|
| CRT-15 | `None` 16.463 su 16.463 | **costante.** `FINESTRE_CRT_NY` definisce finestre solo per CRT a `H1` e `H4`; qui il range è `W1`/`D1`. Non è un difetto: è che CRT-15 vive sulle coppie intraday, cioè nella Fase 1bis. |
| CRT-17 | `True` **1** su 16.463 | **costante di fatto.** Strutturale: un CRT È uno sweep dell'estremo del range, quindi le chiusure recenti stanno per forza dalla parte opposta alla direzione che si prende, e `meta_tenuta` risponde sempre al contrario. Il documento diceva già che la lettura onesta «sparisce del tutto»; ora si sa perché. |
| CRT-20 | 50/50 | risponde, ma separa di ±0,0023 R: nessuna informazione. |

**Quelle che separano qualcosa** (nessuna vicina ai +0,10 R richiesti):

| regola | sì | no | non lo so |
|---|---|---|---|
| CRT-11 | +0,0366 (1.452) | −0,0338 (9.488) | +0,0485 (5.523) |
| CRT-18 | +0,0327 (5.685) | +0,0464 (94) | −0,0178 (10.684) |
| CRT-10 | −0,0729 (47) | **−0,3475** (255) | +0,0057 (16.161) |
| CRT-06 | −0,0129 (6.709) | +0,0319 (1.843) | +0,0035 (7.911) |

Due letture da non dare per buone senza misurarle meglio:

- **CRT-18 separa quasi solo fra `True` e `None`** (5.685 contro 10.684, con
  94 soli `False`). `None` significa «dopo la barra che ha spazzato non c'è
  nessuna barra»: il segnale potrebbe essere la **lunghezza della fase**, non
  la tenuta del punto medio. Va distinto prima di pesarlo.
- **CRT-06 va al contrario**: allineato vale meno che non allineato, e il
  conteggio non è monotono (0 → −0,0190, 1 → −0,0755, 2 → −0,0052). Le fonti
  dicono «tre modelli allineati danno l'accuratezza massima»; nessun CRT del
  campione ne ha tre.

Campione efficace (`backtest/campione_efficace.py`): 14.848 blocchi
indipendenti su 16.463 righe, il 90,2%. Sopra le 300 prove che il protocollo
chiede, quindi il bootstrap a blocchi della Fase 2 ha di che lavorare.

1.315 CRT (il 7,4%) non hanno etichetta: il rientro ha chiuso oltre il 50%
del range, quindi TP1 sta già alle spalle dell'ingresso. È lo stesso caso che
dal vivo il bot rifiuta con `tp1_alle_spalle`.

---

## 11. Come si aggiorna questo documento

1. Una regola passa a **VIVA** solo quando `python audit_regole.py` la conta
   fra le vive. Non quando è scritta, non quando ha i test verdi.
2. Una misura entra qui solo col suo σ contro placebo e la dimensione del
   campione. Un numero senza placebo non è una misura.
3. Una divergenza fra codice e regola si scrive qui **prima** di correggerla,
   non dopo: il documento serve a sapere dove si è, non a dire che va tutto
   bene.
