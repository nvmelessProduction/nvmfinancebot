# La strategia di Terence, dal suo libro (12/10/2026)

Fonte: *L'arte dell'1%* di Terence Bordacchini, socio del proprietario (PDF di 301 pagine sul ramo `main`,
caricato dal proprietario il 12/10/2026). La strategia è nel capitolo 2 (pagine 83-192 del libro); il capitolo 1
dà le basi (struttura, 4 fasi, Fibonacci, sessioni, timeframe), il capitolo 3 è analisi fondamentale e non entra
nel bot. Il libro **non parla di CRT**: come Terence unisce le due cose lo dice il suo video *"Come ho integrato il
CRT nel mio trading"* (in fondo). Seguiranno i suoi video del canale (sottotitoli in scaricamento).

Dove il libro è chiaro la regola è scritta così com'è; dove serve una scelta per farne codice è segnata con
**[da decidere]** e va chiesta a Terence (elenco in fondo). Niente di questo è ancora nel bot.

## 1. Struttura

- **Massimi e minimi**: ogni volta che se ne forma uno ci si chiede *"è stato rotto il massimo (minimo)
  precedente?"*. Sì: struttura **esterna** aggiornata (dà la direzione). No: siamo nella struttura **interna**,
  che non dice niente da sola, salvo quando si riallinea con l'esterna.
- **Tre strutture**: rialzista, ribassista, laterale (né massimi né minimi nuovi). L'inversione è solo il
  passaggio da una all'altra.
- **Rialzista**: punto A = minimo di riferimento, punto B = massimo di riferimento. Valida finché il prezzo sta
  sopra A; rotto A, diventa ribassista. Si cercano buy solo sotto il 50% di A-B (**discount**); sopra il 50% è
  **premium**, rischioso per comprare. Ribassista: lo specchio.
- **Le 4 fasi**: range (accumulo) → espansione → ritracciamento (mitigazione) → continuazione.
- **Il 50% decide quanto ritraccia**: se la rottura di struttura è avvenuta sopra il 50% dell'impulso, il
  ritracciamento si ferma sul 50%; se sotto, può scendere fino alla **zona di causa** (range, gap, EPA da cui è
  partito tutto). Nel secondo caso il 50% è il primo target o parziale.
- **Fibonacci al contrario**: in una struttura long si traccia dal massimo al minimo. Livelli: **0,5** (centro),
  **0,382** (golden pocket = il 61,8 classico), **0,25** (= 75), **0,114** (= 88,6). Tra 0,5 e 0,25 è l'**area
  decisionale**, tra 0,25 e 0,114 la **zona estrema**.
- **[da decidere]** quanto deve essere grande un massimo/minimo per contare (quante candele per lato), e su quale
  timeframe si legge la struttura.

## 2. Le tre zone

- **EPA** (Efficient Price Action): in struttura long l'**ultimo sell prima del buy** (in short l'ultimo buy prima
  del sell), cioè l'origine dell'impulso che ha costruito la struttura. Serve a due cose: **stop** sotto il minimo
  della EPA (se la EPA si rompe la struttura è invalidata) e **contesto** per l'entrata (non è un'entrata da sola).
- **IPA** (Inefficient Price Action): la zona di rottura lasciata da un impulso forte o da una notizia, non
  ancora testata. Il prezzo quasi sempre torna a colmarla; colmata, passa da inefficiente a efficiente
  (**switch**) e il prezzo può continuare.
- **Inducement (IDM)**: in struttura long l'**ultimo minimo che ha generato il massimo** (short: l'ultimo massimo
  che ha generato il minimo). È **sempre uno solo** e si aggiorna a ogni nuovo massimo. Finché non viene preso,
  il mercato non è pronto: è il primo filtro.

## 3. MSU, il grilletto

**MSU** (Manipulation Setup): il mercato **prende liquidità e rompe struttura**, e la struttura piccola si
riallinea con quella principale. *"Senza MSU non esiste ingresso"*. Dalle figure del libro (TOTAL settimanale):

- **Tipo 1** (struttura esterna): preso un minimo (✗), il prezzo rompe il massimo che c'era sopra (✓).
- **Tipo 2**, di continuazione (struttura esterna): in un trend, preso il minimo (o in short il massimo) del
  ritracciamento, il prezzo rompe di nuovo nel verso del trend.
- **Tipo 3** (struttura interna): la stessa cosa su massimi e minimi piccoli dentro la gamba.

**Tre entrate** dopo l'MSU (long; short allo specchio):
1. sul **ritest della rottura** (la IPA dell'MSU: switch da inefficiente a efficiente);
2. **buy limit al 50% della EPA** (di solito già nella zona 75/88,6 e con altra liquidità vicino);
3. **buy limit al livello di Fibonacci** dell'impulso dell'MSU: al 50% se la rottura è sopra il 50%, più in
   basso se è sotto.

La scelta dipende dal contesto, non è sempre la stessa. **[da decidere]** quale delle tre usare quando.

## 4. Le 3 regole per entrare (sempre tutte, sempre in quest'ordine)

1. **Presa di inducement**: senza, *"non c'è carburante"* e si aspetta.
2. **Prezzo in zona di EPA**: fuori dalla EPA non c'è vantaggio, anche se il pattern è bello.
3. **MSU** come conferma e ingresso.

*"Se anche una sola di queste condizioni manca, il trade non esiste."* Stop sotto la EPA, obiettivo il massimo
della struttura.

## 5. Il ciclo di liquidità

Presa di IDM → MSU con il **primo BOS** → ritorno in EPA/IPA → **secondo BOS**. Al secondo BOS il ciclo è finito:
il prezzo può continuare, ma **non si cercano più entrate su quel ciclo**. Il ciclo nuovo riparte da una nuova
presa di IDM. Serve a non entrare in ritardo.

## 6. I quattro tipi di liquidità

- **Da break even (BE)**: in long il **primo minimo dopo la rottura** (short: il primo massimo). È una sola per
  ciclo. Il prezzo ci torna spesso a prendere gli stop spostati a pareggio e poi riparte: spesso coincide con la
  EPA e con il 75-88,6, ed è **spesso la nostra entrata**. Conseguenza per la gestione: **mai mettere il
  pareggio su quel livello**.
- **Dinamica**: due o più massimi (minimi) uguali (**orizzontale**: doppi massimi/minimi) oppure crescenti o
  decrescenti (**build up / build down**), costruiti vicino a EPA, IPA, gap o range. Più sono, più liquidità: il
  prezzo la prende tutta, rientra nella causa e riprende il trend. Prima può fare falsi movimenti sulla
  liquidità interna.
- **A linea**: livelli dove più aperture e chiusure coincidono (grafico a linea). Stanno poco prima dei massimi e
  minimi strutturali: per questo il prezzo spesso **gira qualche pip prima del massimo**. Conta per mettere i
  take profit.
- **Statica algoritmica**: massimi e minimi dei periodi precedenti, **PDH/PDL, PWH/PWL, PMH/PML**, trimestre,
  semestre, anno; più è alto il timeframe, più contano. Il prezzo ci torna e reagisce (assorbimento, MSU di
  inversione o continuazione). Con un gap nello stesso punto la probabilità sale molto.

## 7. Il gap

- **Tre candele**. Rialzista: dal **massimo della candela 1** al **minimo della candela 3**; ribassista: dal minimo
  della 1 al massimo della 3. Va letto nel trend.
- **La terza candela decide**: se è direzionale, accetta la precedente e non ha spike contro, il gap **non viene
  mitigato subito** (forza, continuazione prima del ritorno). Se è di rifiuto, più ombra che corpo, inside bar o
  indecisa, il prezzo **ci rientra subito** e poi riparte.
- **Sei modelli d'entrata** (stop sempre oltre il gap, obiettivo il massimo della struttura):
  1. **Fake out**: il prezzo reagisce poco prima del gap, quel minimo diventa liquido, viene preso ed entra nel
     gap; due minimi (il secondo più basso) con **divergenza RSI** e una candela di conferma → entrata.
  2. **Aggressione**: entra con forza nel gap → reazione automatica → liquida il minimo dell'aggressione →
     continuazione, con divergenza RSI.
  3. **Aggressione con consolidamento**: come il 2, ma dopo la reazione lateralizza e costruisce micro-strutture
     (*"qui molti entrano male, noi aspettiamo"*), poi liquida e riparte; divergenza RSI fra il minimo prima del
     consolidamento e quello della liquidazione.
  4. **Consolidamento nel gap**: entra con forza e lateralizza dentro il gap senza reazione; entrata sulla
     rottura del consolidamento (la IPA), **senza RSI**.
  5. **Inversione**: un gap evidente coperto e accettato da **una sola candela** con il corpo (due o più candele:
     non vale; le ombre non contano). Pochissime regole ma rigide.
  6. **Sell-off**: solo short, **solo su timeframe bassi** (M5, M3; mai H4 e sopra): tre candele ribassiste di
     fila con la terza forte e senza indecisione; short alla chiusura della terza, stop sopra il gap. Vale di più
     con liquidità dinamica a sinistra e minimi evidenti da prendere.
- **[da decidere]** quanto deve essere "evidente" un gap (in rapporto a cosa) per il modello 5.

## 8. Il range (solo M15 e sotto)

- Si cerca **solo** su M15, M5, M3, M1 (*"dall'M30 in su non sono validi"*), partendo da M15 e scendendo solo se
  non c'è. **Il range è uno solo.**
- Cinque tipi: tre di **consolidamento** (**a blocco**: 3 o più candele contenute; **inside bar**; **candela di
  equilibrio**: ombre più grandi del corpo e simili fra loro) e due **sell to buy / buy to sell** (le prime due
  candele con corpi più grandi delle ombre e ombre diverse fra loro; la terza non deve rientrare nel range).
- Vale solo se dopo c'è una **rottura di struttura**. Si opera la fase 4 (continuazione) dopo espansione e
  ritracciamento, con gli stessi modelli d'entrata del gap.

## 9. Timeframe, sessioni, candela

- **Top-down**: 12, 6, 3 mesi = cicli e grande liquidità; mese e settimana = direzione di medio periodo; giorno,
  12, 6, 4 ore = trend operativo e setup; 90, 60, 45, 30 minuti = intraday; **15, 5, 3, 1 minuto solo per
  l'entrata**.
- **Sessioni** (ora italiana): Europa dalle 9, New York dalle 14:30, chiusura alle 22. La sovrapposizione
  Europa-America è il momento migliore.
- Ogni candela fa **apertura, manipolazione, distribuzione, chiusura**.
- **Wyckoff** (accumulazione, mark up, distribuzione, mark down, spring/upthrust): *"le schematiche non si
  tradano, si interpretano"*. Solo contesto.

## 10. Come Terence ci mette il CRT (dal video)

Il gap è il pattern a 3 candele, **uno solo, sul timeframe più alto**; *"prima dentro e poi fuori"*; i CRT prima
del gap sono inutili; il primo movimento dentro il gap è finto (la M); entrata col turtle soup sulla candela 2 da
un timeframe sotto, rientro con l'MSU; target la liquidità esterna; al primo target pareggio e parziale; pochi
trade.

## Cosa c'è già nel bot e cosa è nuovo

| Concetto | Nel bot oggi |
| --- | --- |
| Gap a 3 candele, terza che accetta o no, fasi aggressione → reazione → liquidazione → continuazione con RSI 14 | sì, dal metodo delle foto (`foto.fase`, `foto.rsi`, `Gap.terza_accetta`) |
| Massimi e minimi dei periodi prima (PDH, PWH, PMH…) | sì, come key level (`foto.key_level_presi`) |
| Inside bar | sì, come confluenza del CRT |
| Struttura esterna/interna, punti A e B, premium/discount, Fibonacci 0,5/0,382/0,25/0,114 | no |
| EPA, IPA, inducement, MSU di tipo 1-2-3 e le sue tre entrate | no |
| Ciclo di liquidità (primo e secondo BOS) | no |
| Liquidità da BE, dinamica (uguali, build up/down), a linea | no |
| Gap modelli 1, 3, 4, 5, 6 | no (c'è solo l'aggressione) |
| Range su M15→M1 | no |

## Come diventa allenamento per la rete

1. **Rivelatori** in codice (uno per concetto qui sopra), con prove sulle figure del libro e sugli esempi che
   Terence vorrà mandarci.
2. Ogni rivelatore diventa una **domanda in più nella scheda** che la rete legge (*l'IDM è stato preso? siamo in
   EPA? c'è stato l'MSU? siamo in discount? dove sta la liquidità da BE?*), così la rete impara quanto conta
   ognuna sui vent'anni, insieme alle correzioni fatte con «Correggi».
3. Le **3 regole di Terence** si misurano anche da sole, come strategia, sui vent'anni (2008-2023 per scegliere,
   il resto chiuso per l'esame), con i costi veri. Entrano nelle decisioni solo se migliorano la rete senza di
   loro.

## Da chiedere a Terence

1. Massimi e minimi: quante candele per lato servono? Su quale timeframe si legge la struttura che dà la
   direzione, e su quale si cerca l'MSU (per esempio 4 ore e 15 minuti)?
2. La EPA è una candela sola (l'ultima rossa prima della salita) o tutte le rosse di fila? Dal corpo o
   dall'ombra?
3. Delle tre entrate dopo l'MSU, quale usa e quando?
4. Il target è sempre il massimo della struttura? Parziale e pareggio dove, visto che il pareggio non va sulla
   liquidità da BE?
5. Il gap "evidente" del modello di inversione: grande rispetto a cosa?
6. Il range su M15→M1 serve solo per entrare dentro una zona del timeframe alto o anche da solo?
