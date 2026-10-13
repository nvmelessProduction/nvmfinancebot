# Progetto Nameless: il cervello unico

_Deciso il 13/10/2026 col proprietario. Ogni sessione di lavoro su Nameless parte da qui e da `documenti/STATO.md`._

Il proprietario: *"voglio creare un cervello funzionante, voglio creare un trader che funzioni realmente, come se fosse
una persona"*; *"più in là gli voglio dare in pasto il libro del mio socio"*; allenamento su Kaggle ogni settimana.
Gli schemi da cui nasce: la pagina "Il cervello di Nameless" e "Cervello umano e Nameless" (gli artifact del 13/10).

## Cos'è

Un solo cervello al posto dei sei pezzi di oggi (regole, équipe, rete, Nameless su Kaggle, cervelli di settembre,
Capo di prima). È una rete neurale (transformer, `nvm/rete/modello.py` come punto di partenza) fatta come un cervello:

| Pezzo | Come un cervello umano | Cosa fa |
|---|---|---|
| Sensi | sensi | candele di TradingView così come sono (1h, 4h, 6h, 12h, D, W, M, 3M, 12M), DXY, TOTAL; da MT5 solo il conto |
| Smistamento | talamo | le candele in fila per timeframe (`nvm/rete/finestre.py`) |
| Occhi | cortecce sensoriali | leggono tutti i timeframe insieme |
| Zone | aree specializzate | CRT, key level, bias, gap, DXY, livelli: l'équipe di oggi dentro la rete |
| Capo | prefrontale | decide se entrare e quale setup |
| Rischio | | quanto puntare, quando fermarsi |
| Allarme | amigdala | zone che si contraddicono, spread larghi, serie di perdite fuori dal normale |
| Mani | cervelletto | esegue su MT5 e confronta l'eseguito col voluto |
| Diario | ippocampo | ogni setup, preso o sulla carta, col risultato |
| Premio | dopamina | stima contro risultato: corregge zone e Capo |
| Studio | sonno | ogni weekend su Kaggle, poi il compito |

Due pagelle (il proprietario: *"così sembra che stiamo focalizzando il successo sul guadagno"*): **il mestiere**
(vede giusto, prende i setup giusti, esegue bene, disciplina) ogni giorno; **il risultato** solo su tanti trade.

## La strada: sei fasi, ognuna con un esame

Non si passa alla fase dopo senza l'esame. Intanto il bot di oggi resta acceso sul demo, com'è.

| Fase | Cosa si costruisce | Esame | Il proprietario |
|---|---|---|---|
| 0 Fondamenta | un solo percorso (via cervelli di settembre, Capo di prima, Nameless LightGBM, metodo dei video, la rete che giudica dopo l'équipe); dati di tutti i mercati (Dukascopy bid e ask: forex, metalli, indici, energia; Binance: crypto) con gli orari di TradingView; controllo qualità; costi veri dal demo | candele uguali a quelle di TradingView; dati senza buchi; 24 foto su 24 con i dati nuovi | il via; conferma del paracadute |
| 1 Gli occhi | scuola delle candele: indovinare le candele nascoste su tutti i mercati e timeframe | meglio di "copia l'ultima candela" sugli anni mai visti | lancia la cella su Kaggle |
| 2 Le zone | una testa per materia, con le risposte delle regole delle foto (`nvm/agenti/foto.py`, 24/24) | ogni materia ≥ 98% uguale alle regole sugli anni mai visti; la rete rifà le 24 foto | lancia la cella su Kaggle |
| 3 Il Capo | il risultato di ogni setup valido (R con i costi veri, TP1 25% + pareggio, target), 20 anni, tutti i mercati | sugli anni mai visti (dal 2023), coi costi: i setup scelti guadagnano più di zero con sicurezza statistica, e più di "prenderli tutti" | niente |
| 3b (se la 3 non passa) | il Capo impara filtri suoi dentro il metodo: timeframe, mercati, condizioni | lo stesso esame. Se non passa neanche così, la strategia su questi mercati non ha vantaggio: lo si dice | niente |
| 4 Rischio e allarme | puntata dalla stima del Capo e dalla sua incertezza (una frazione di Kelly), test continuo "continua / fermati" per setup e mercato; allarme | sugli anni mai visti la perdita dal massimo resta dentro il paracadute | conferma 2% per trade e 20% dal massimo |
| 5 Dal vivo | Nameless sul demo prima in ombra (decide sulla carta accanto all'équipe), poi al comando; diario, premio, studio del weekend automatico su Kaggle dalla VPS, compito, pagelle della domenica | in ombra: pagella del mestiere ≥ 95%; poi 3 mesi e almeno 100 trade col test continuo | chiave di Kaggle nel `.env` della VPS (mai in chat); 10 minuti la domenica |
| 6 Il libro | nuove materie: struttura A-B, inducement, EPA, MSU, i sei modelli del gap (`documenti/spec/metodo_libro.md`, `nvm/agenti/struttura.py`) | materie ≥ 98%; gli esempi del socio 100%; poi il Capo impara quando rende | esempi annotati dal socio, come le foto |

## Cosa può riuscire e cosa no

- **Fasi 0-2** (vede come le foto, impara, si corregge): alta probabilità, perché ogni pezzo si controlla e le
  risposte giuste esistono (le regole che tornano 24/24).
- **Fase 3** (guadagnare): nessuno può prometterlo. Le misure finora sui 20 anni sono negative. Il piano garantisce
  che lo si sappia sugli anni mai visti, coi costi veri, prima di rischiare; se non c'è vantaggio, il Capo prova a
  trovare dove c'è (3b); se non c'è da nessuna parte, lo si sa senza perdere altri mesi.
- **È un'AI vera**: una rete neurale (transformer, la famiglia delle AI moderne) che impara dai dati invece di eseguire
  regole scritte, riconosce grafici mai visti e si migliora riallenandosi. Non è un'intelligenza generale e non ha
  coscienza: è un'AI specialista della strategia.

## Regole fisse (non si imparano)

Solo demo finché non decide il proprietario; ogni operazione con lo stop; una aperta per strumento; mai contro la
previsione della domenica; almeno 1 R al target; il compito sulle foto si passa sempre; paracadute 2% per trade e 20%
dal massimo (da confermare); le chiavi mai nel repository.

## Kaggle

Circa 30 ore di scheda grafica gratis a settimana. Fasi 1-3: una cella da lanciare (come `kaggle_rete/cella_kaggle.txt`).
Dalla fase 5: la VPS manda i dati della settimana, lancia lo studio e riprende la rete solo se passa il compito.

## A che punto siamo

- 13/10/2026: piano deciso. Prossimo passo: fase 0, appena il proprietario dà il via e conferma il paracadute.
