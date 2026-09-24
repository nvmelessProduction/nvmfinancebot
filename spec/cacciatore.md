# Scheda agente: Cacciatore

> **BOZZA, non ancora approvata.** Costruita dalle fonti in
> `spec/FONTI-ROMEO.md`. Ogni regola porta il suo segno: **[R]** l'ha detto
> Romeo, **[S]** lo dicono i suoi studenti, **[?]** lo decidi tu. Le domande
> sono in fondo.

## La domanda

Su questa coppia di timeframe, la candela alta appena chiusa è un range, e
il prezzo lo sta manipolando da un lato?

## Cosa guarda

- Le candele **chiuse** del timeframe alto e del timeframe basso della
  coppia. Mai una candela ancora aperta: il futuro non si guarda.
- Nient'altro: niente key level, orari o pareri di altri agenti.

## Cosa NON fa

Il vecchio bot aveva tutto in una funzione da 686 righe, e lì nascevano gli
errori. Il Cacciatore trova il CRT e basta:

- **se entrare** lo decide il **Grilletto** (il Model#1 sul timeframe basso);
- **stop e target** li mette **Livelli**;
- **la qualità del CRT** (key level, orari, candele interne) la giudicano le
  **Conferme** e il **Contesto**.

## La regola del manuale

1. **Le coppie di timeframe** **[R]**

   | Range (timeframe alto) | Ingresso (timeframe basso) |
   |---|---|
   | mensile | giornaliero |
   | settimanale | 4 ore |
   | giornaliero | 1 ora |
   | 4 ore | 15 minuti |

2. **Il range** **[R]**. Ogni candela chiusa del timeframe alto è un range:
   - `CRT high` = il suo massimo;
   - `CRT low` = il suo minimo;
   - `CRT 50%` = a metà fra i due.

3. **Dove si cerca la manipolazione** **[R]**. Dentro la candela alta
   successiva (la "candela 2"), guardando le candele basse che cadono dentro
   di essa.

4. **La manipolazione** **[R]**:
   - **short:** una candela bassa fa un massimo **sopra** `CRT high`;
   - **long:** una candela bassa fa un minimo **sotto** `CRT low`.

   Per "sopra" basta un tick, finché non si decide diversamente **[?]**.

5. **L'estremo della manipolazione.** Il punto più lontano raggiunto oltre
   il range: il massimo più alto per uno short, il minimo più basso per un
   long. Si aggiorna finché la manipolazione continua. Serve a Livelli per
   lo stop.

6. **Il rientro** **[?]**. È il punto da decidere. Le due letture sono nelle
   domande, alla numero 1.

7. **Quando il CRT decade:**
   - la candela 2 chiude **oltre** il range (sopra `CRT high` per uno
     short): non era una manipolazione, era una rottura **[S]**;
   - il prezzo raggiunge il lato opposto prima dell'ingresso: il movimento
     è già avvenuto **[?]**;
   - la candela 2 finisce senza ingresso **[?]**: vedi la domanda 2.

8. **Un CRT per candela di range e per lato** **[?]**. Se lo stesso lato
   viene spazzato più volte, resta un CRT solo, con l'estremo aggiornato.

## Cosa risponde

- **Stato:** nessun CRT, oppure short armato, long armato o decaduto (con il
  motivo).
- **Numeri:** la coppia di timeframe, l'orario della candela di range, `CRT
  high`, `CRT low`, `CRT 50%`, l'estremo della manipolazione e il suo
  orario.

## I casi

Da raccogliere (vedi `casi/MODELLO-CASO.md`): almeno 20 CRT e 10 "sembra un
CRT ma non lo è". I tre schemi di Romeo in `spec/FONTI-ROMEO.md` valgono
come esempi di forma, non come casi: non hanno date né prezzi.

## Cosa può imparare

All'inizio niente: la definizione è fissa.

Più avanti, un numero solo: di quanto deve andare oltre il range la
manipolazione per contare, in frazioni del range (oggi basta un tick). Si
misura se migliora il risultato dei CRT trovati, con il cancello del
`PIANO.md` §2.

## Da dove viene

Vedi `spec/FONTI-ROMEO.md`: le coppie dal post di Romeo del 06/01/2025, il
range e la manipolazione dai suoi schemi, la divisione "CRT sul timeframe
alto, Model#1 sul basso" dal post del 05/04/2025.

## Domande per te

Rispondi con quello che hai imparato dai video di Romeo. Anche "non lo so"
va bene: in quel caso si provano entrambe le letture, dichiarate prima (al
massimo 3 varianti, `PIANO.md` §3).

1. **Il rientro: serve che la candela alta chiuda dentro il range?**
   - **A. Sì.** La candela 2 deve chiudere dentro il range: è lo schema a
     tre candele. Si entra solo nella candela 3.
   - **B. No.** Basta che il prezzo esca dal range e che sul timeframe basso
     scatti il Model#1. Si entra mentre la candela 2 è ancora aperta.

   Lo schema del Model#1 di Romeo sembra la B. Anche la coppia "mensile →
   giornaliero" la fa pensare: con la A si aspetterebbe un mese intero prima
   di entrare. Ma decidi tu.
2. **Se la candela 2 finisce senza ingresso**, il CRT vale ancora nella
   candela 3, o decade?
3. **Se nella candela 2 vengono spazzati entrambi i lati**, cosa fa Romeo?
4. **Le coppie:** solo le quattro di Romeo, o anche 1 ora → 5 minuti e 15
   minuti → 1 minuto, che usava il vecchio bot?
5. **Gli orari** (candele a 4 ore dell'1, delle 5 e delle 9 di New York):
   Romeo li insegna, o li hanno aggiunti gli studenti?

Queste due servono a **Livelli**, ma tanto vale chiederle adesso:

6. **Lo stop "al 25% del range":** la distanza fra ingresso e stop è un
   quarto del range, oppure lo stop va appena oltre l'estremo della
   manipolazione?
7. **"Take profit at 50% and then CRT high/low":** quanta parte si chiude al
   50% e quanta si lascia andare fino al lato opposto?

## Approvazione

- [ ] Approvata da te il ____
