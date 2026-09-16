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

**ASSENTE.** Mai implementata, mai misurata.

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

**ASSENTE.** Il codice non la riconosce affatto.

---

## 4. La conferma

### CRT-11 — Dopo il raid serve un CISD sul timeframe basso
Change In State Of Delivery: il primo segno che la consegna ha cambiato verso.

**CONTRARIA.** Ho implementato l'**MSS** (Market Structure Shift), che è
parente ma non identico: l'MSS chiede la rottura di uno swing strutturale, il
CISD chiede la rottura dell'ultima serie di candele di consegna opposta. Il
secondo è più precoce. `backtest/romeo_completo.py` usa l'MSS.

### CRT-12 — Divergenza SMT fra mercati correlati
Uno strumento fa un nuovo estremo, il correlato no: è divergenza, e le fonti
la dichiarano **non negoziabile**.

**ASSENTE.** È la lacuna più grave di questo documento: dichiarata
indispensabile, mai implementata, e la più facile da misurare — sei strumenti
correlati sono già in archivio.

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

**CONTRARIA.** Ho misurato killzone diverse (Londra 3-6, New York 8:30-11:30).
Le finestre di Romeo non sono mai state provate. `PRIN-12` dichiara il sistema
attivo 24 ore su 24: se queste finestre entrano, `PRIN-12` va riscritta.

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

**ASSENTE.**

---

## 7. Le ombre — il blocco più trascurato

### CRT-18 — Il punto medio dell'ombra è un livello
Tenerlo favorisce la continuazione, attraversarlo invalida.

**ASSENTE.**

### CRT-19 — Ombre piccole su C2 favoriscono l'espansione
### CRT-20 — Ombre grandi su C2 favoriscono la mean-reversion

**SOSPETTA DI SEGNO INVERTITO.** Il CRT **è** un'operazione di mean-reversion.
Se `CRT-20` è vera, le ombre **grandi** dovrebbero dare i CRT migliori — e il
mio filtro «sweep efficiente» scartava proprio quelle, tenendo le piccole.
Non l'ho mai misurata nei due versi. Finché non lo faccio, ogni numero che ho
dato su quel filtro va letto sapendo che potrebbe essere il contrario.

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
| VIVE | 9 |
| PARZIALI | 5 |
| CONTRARIE | 2 |
| ASSENTI | 6 |

**Le quattro lacune che contano**, in ordine di peso dichiarato dalle fonti:

1. **Divergenza SMT** (`CRT-12`) — dichiarata non negoziabile, mai scritta.
2. **Analisi delle ombre** (`CRT-18`, `CRT-19`, `CRT-20`) — un blocco intero,
   e il mio unico filtro in quest'area potrebbe avere il segno invertito.
3. **Double Purge Sweep** (`CRT-10`) — una forma di CRT che il codice non
   riconosce.
4. **Tre modelli allineati** (`CRT-06`) e la coppia **`W1→H4`** (`CRT-04`) —
   confluenze mai provate. La coppia su cui ho dato il risultato migliore,
   `W1→D1`, non è di Romeo.

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

---

## 11. Come si aggiorna questo documento

1. Una regola passa a **VIVA** solo quando `python audit_regole.py` la conta
   fra le vive. Non quando è scritta, non quando ha i test verdi.
2. Una misura entra qui solo col suo σ contro placebo e la dimensione del
   campione. Un numero senza placebo non è una misura.
3. Una divergenza fra codice e regola si scrive qui **prima** di correggerla,
   non dopo: il documento serve a sapere dove si è, non a dire che va tutto
   bene.
