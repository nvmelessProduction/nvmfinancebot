# Scheda agente: Cacciatore

> **Stato:** regole decise sulle fonti il 24/09/2026. L'utente non può
> rispondere alle domande e ha chiesto di cercare le risposte nelle fonti
> (`documenti/spec/FONTI-ROMEO.md`). Dove le fonti non bastano c'è una **variante
> dichiarata**, che si misura invece di sceglierla. Manca la prova sui casi
> presi dai grafici di Romeo.
>
> Segni: **[R]** l'ha detto o disegnato Romeo, **[S]** lo dicono i suoi
> studenti, **[D]** deciso qui, perché le fonti non lo dicono.

## La domanda

Su questa coppia di timeframe, una candela alta ha fatto da range, e il
prezzo lo sta manipolando da un lato?

## Cosa guarda

- Le candele **chiuse** del timeframe alto e del timeframe basso della
  coppia, sui prezzi BID (`documenti/spec/dati.md`). Mai una candela ancora aperta.
- Nient'altro: niente key level, orari o pareri di altri agenti.

## Cosa NON fa

Il vecchio bot aveva tutto in una funzione da 686 righe, e lì nascevano gli
errori. Il Cacciatore trova il CRT e basta:

- **se entrare** lo decide il **Grilletto** (il Model#1 sul timeframe basso);
- **stop e target** li mette **Livelli**;
- **la qualità del CRT** (key level, orari, candele interne) la giudicano le
  **Conferme** e il **Contesto**.

## La regola del manuale

1. **Le coppie di timeframe** **[R]**, dal post del 06/01/2025:

   | Range (timeframe alto) | Ingresso (timeframe basso) |
   |---|---|
   | mensile | giornaliero |
   | settimanale | 4 ore |
   | giornaliero | 1 ora |
   | 4 ore | 15 minuti |

2. **Il range** **[R]**. Ogni candela chiusa del timeframe alto è un range
   ("every single candle is a range"):
   - `CRT high` = il suo massimo;
   - `CRT low` = il suo minimo;
   - `CRT 50%` = a metà fra i due.

   Ogni candela fa da range per le **due candele alte successive**, la
   "candela 2" e la "candela 3" (**[R]** "you only need 3 candles"). Quindi in
   ogni momento ci sono più range aperti insieme, e va bene così.

3. **La manipolazione** **[R]**. Si guardano le candele basse che cadono
   dentro la candela 2 e la candela 3:
   - **short:** la prima candela bassa con il massimo **sopra** `CRT high`;
   - **long:** la prima candela bassa con il minimo **sotto** `CRT low`.

   "Sopra" vuol dire strettamente sopra: basta un punto, niente soglia **[D]**.
   Da quel momento il CRT è **armato** in quella direzione.

4. **L'estremo della manipolazione** **[D]**. È il punto più lontano toccato
   oltre il range: il massimo più alto per uno short, il minimo più basso per
   un long. Si aggiorna a ogni candela bassa. Serve a Livelli per lo stop.

5. **Il rientro: si entra senza aspettare la chiusura della candela alta**
   **[R]**. Romeo scrive "Frame a HTF bias (CRT), look for a LTF entry
   (Model#1)" e "Monthly CRT → Daily model#1". Nel canale lo dice ancora più
   chiaro (msg 6615): "When I'm bearish, this is the ideal reaction: 1- Candle
   opens. 2- Stabs into an old CRTH. 3- Dumps." Il rientro lo giudica il
   Grilletto sul timeframe basso, non il Cacciatore.

6. **Quando il CRT decade.** Vale la prima di queste che succede:
   - **rottura:** la candela 2 chiude oltre il range, cioè sopra `CRT high`
     per uno short. Non era una manipolazione, era una rottura **[S]**;
   - **lato opposto:** una candela bassa tocca l'altro estremo del range
     prima dell'ingresso. Il movimento è già avvenuto **[D]**;
   - **scadenza:** finisce la candela 3 **[R]**.

7. **Un CRT per range e per lato** **[D]**. Se lo stesso lato viene spazzato
   più volte, resta un CRT solo e si aggiorna l'estremo. I due lati sono
   indipendenti: può armarsi uno short e poi un long sullo stesso range. Ma
   quando il long spazza `CRT low`, lo short ha toccato il lato opposto e
   decade.

## La variante dichiarata

| Nome | Cosa cambia | Perché esiste |
|---|---|---|
| **Manuale** | le regole qui sopra | è quello che dicono i post e gli schemi di Romeo |
| **Chiusura dentro** | il CRT si arma solo quando la candela 2 **chiude dentro** il range dopo averlo spazzato: lo schema a tre candele. Si entra solo nella candela 3 | è la lettura di molti studenti, e lo schema "CRT is fractal" di Romeo la mostra |

È una delle 3 varianti permesse dal piano. Si decide nella Fase F, con il
walk-forward, e mai guardando il 2024–2026.

## Cosa risponde

- **Stato:** nessun CRT, short armato, long armato, oppure decaduto con il
  motivo (rottura, lato opposto, scadenza).
- **Numeri:** la coppia, l'orario della candela di range, `CRT high`, `CRT
  low`, `CRT 50%`, l'orario della manipolazione e l'estremo.

## Le domande passate ad altri agenti

Le fonti ne parlano, ma non riguardano il Cacciatore:

| Domanda | Chi la tiene | Punto di partenza | Fonte |
|---|---|---|---|
| Orari (candele a 4 ore dell'1, delle 5, delle 9 di New York) | Contesto | filtro spento: si misura quanto conta | **[S]**, non trovato in un post di Romeo |
| Dove va lo stop | Livelli | appena oltre l'estremo della manipolazione; variante: a un quarto del range | **[R]** 04/02/2023: "your stoploss is 25% of the range" |
| Quanto si chiude al 50% | Sentinella | metà al 50%, il resto al lato opposto | **[R]** 05/04/2025: "take profit at 50% and then CRTH/L"; la quantità non la dice |

## I casi

Si prendono dai grafici che Romeo ha pubblicato, con strumento, timeframe e
data riconoscibili, e si ritrovano sui dati. Obiettivo: 20 CRT e 10 "sembra
un CRT ma non lo è". Se non se ne trovano abbastanza, si scrive quanti sono.

I suoi tre schemi (`documenti/spec/FONTI-ROMEO.md`) diventano subito prove di forma:
non hanno date, ma dicono cosa deve e cosa non deve essere un CRT.

## Cosa può imparare

All'inizio niente: la definizione è fissa.

Più avanti, un numero solo: di quanto deve andare oltre il range la
manipolazione per contare, in frazioni del range (oggi basta un punto). Si
misura se migliora il risultato dei CRT trovati, con il cancello del
`documenti/PIANO.md` §2.

## Approvazione

- [x] Regole decise sulle fonti, su delega dell'utente, il 24/09/2026
- [ ] Prova sui casi presi dai grafici di Romeo
