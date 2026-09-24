# Scheda: i dati

> **BOZZA.** Non è un agente che decide: è la base su cui lavorano tutti gli
> altri. Nel vecchio progetto molti errori venivano da qui, per esempio fonti
> mescolate, orari del server presi per UTC e metà archivio inventato.

## La regola in una riga

**Una fonte sola per lo storico, candele ricostruite da noi a partire dal
minuto, con la giornata che chiude alle 17:00 di New York.**

## La fonte

| Uso | Fonte | Perché |
|---|---|---|
| **Storico** (Fasi B–G) | **Dukascopy**, candele al minuto, **BID e ASK separati**, dal 2006 | gratuita, vent'anni, e con bid e ask lo spread si misura invece di stimarlo |
| **Dal vivo** (Fase H) | il broker, da MetaTrader 5 | è dove si opera |

Le due fonti devono dare gli stessi CRT: sui mesi in comune almeno il 95%,
stessa candela e stessa direzione (`PIANO.md`, "Dove ci si ferma"). Se non
coincidono, si sistemano i dati prima di andare avanti.

## L'orario: la giornata chiude alle 17:00 di New York

Ogni candela sopra il minuto si costruisce da noi. Tutte seguono la stessa
convenzione, quella dei grafici forex su TradingView e dei broker MT5 a
UTC+2/UTC+3:

| Timeframe | Quando apre (ora di New York) |
|---|---|
| giornaliero | 17:00 del giorno prima |
| 4 ore | 17:00, 21:00, 01:00, 05:00, 09:00, 13:00 |
| 1 ora, 15 minuti, 5 minuti | allo scoccare dell'ora o del quarto |
| settimanale | domenica 17:00 → venerdì 17:00 |
| mensile | la prima giornata di trading del mese |

L'ora legale di New York si segue da sola: in estate le 17:00 di New York
sono le 21:00 UTC, in inverno le 22:00 UTC.

**Perché conta:** con questa convenzione le candele a 4 ore aprono all'1,
alle 5 e alle 9 di New York, cioè gli orari di cui parlano gli studenti di
Romeo. Ed è anche il modo in cui Romeo vede i suoi grafici. Con le
giornaliere spezzate a mezzanotte UTC i range sarebbero **diversi**, e il
Cacciatore troverebbe altri CRT.

## Bid e ask

- Il **CRT si cerca sui prezzi BID**, come appaiono sui grafici.
- I **costi si pagano sui prezzi veri**: un long compra in ASK e chiude in
  BID, uno short il contrario. Lo spread si paga dove e quando il mercato lo
  faceva pagare, per esempio più largo alle notizie e alla riapertura della
  domenica.

## Strumenti

Per ora: EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY, XAUUSD. Sono gli stessi
del vecchio bot, da riconfermare (domanda aperta in `STATO.md`).

## Come si conserva

- Un file per strumento per mese, in `dati/grezzi/`, fuori da git.
- I prezzi si tengono in **punti interi**, come li dà Dukascopy, così non si
  perde precisione. Un punto vale 0,00001 per la maggior parte dei cambi e
  0,001 per USDJPY e XAUUSD.
- I minuti senza scambi (volume zero) si scartano: Dukascopy li riempie
  ripetendo l'ultimo prezzo, ma lì il mercato non c'era.

## I controlli

Prima di usare i dati, un controllo automatico che produce un rapporto:

| Controllo | Cosa cerca |
|---|---|
| **Coerenza delle candele** | minimo sopra apertura o chiusura, massimo sotto |
| **Spread** | ask sotto bid, oppure spread assurdo per lo strumento |
| **Buchi** | minuti mancanti a mercato aperto, oltre una soglia |
| **Salti** | variazioni da un minuto all'altro troppo grandi per lo strumento |
| **Confini** | candele giornaliere e a 4 ore che non aprono agli orari della tabella |

Ogni anomalia va nel rapporto con data e numero. Niente si corregge in
silenzio.

## Lo scaricamento

- Gira sulla VPS, non qui: Dukascopy risponde "troppe richieste" ai server
  condivisi.
- Una richiesta alla volta, con una pausa fra una e l'altra. Se Dukascopy
  risponde "troppe richieste", si aspetta sempre di più e si riprova.
- **Riprende da dove si era fermato**: i giorni già scaricati non si
  richiedono di nuovo.
- Ordine di grandezza: vent'anni per sei strumenti, bid e ask, fanno circa
  60.000 file e qualche GB. Qualche ora di scaricamento, una volta sola.
