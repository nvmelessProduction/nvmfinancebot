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
| 0 Fondamenta | dati di tutti i mercati scaricati su Kaggle (HistData per intero, 66 mercati; Binance, 20 crypto) con gli orari di TradingView; controllo qualità; costi veri dal demo; pulizia di quello che il bot di oggi non usa (il resto nella fase 5) | 24 foto su 24 con gli orari di TradingView; dati controllati (`mercati.json`) | il via; lancia la cella dei dati su Kaggle |
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

- 13/10/2026: piano deciso. Il proprietario ha dato il via (*"procedi hai il mio via"*); il paracadute 2% / 20% resta
  quello proposto finché non dice altro (serve dalla fase 4). I dati si scaricano su Kaggle, non sul suo computer.
- Fase 0, fatto:
  - **24 foto su 24 con gli orari di TradingView** (candele dalle 18 di New York anche per il forex, senza spostare
    l'ora): `python -m strumenti.foto --dati <histdata> --orari-tradingview`.
  - **Lo scaricamento su Kaggle** (`kaggle_rete/dati.py`, cella `kaggle_rete/cella_dati.txt`): HistData per intero (66
    mercati: i 38 di prima, 16 esotiche e 4 coppie dello yen e del fiorino, l'oro contro euro, sterlina, franco e dollaro
    australiano, Australia 200, Francia 40, Hong Kong 50, Euro Stoxx 50) e 20 crypto da Binance; `mercati.json` dice
    cosa c'e' e cosa ha tagliato il controllo di qualita'. Dukascopy limita le richieste ("troppe richieste"): resta per
    gli spread a campione, se serviranno.
  - **I costi veri del demo** (26/09-08/10, dal branch `dati-vps`): su 71 trade il prezzo d'entrata ottenuto e' quello
    voluto (media -0,02 R, cioe' leggermente meglio; mediana 0). Gli 80 trade chiusi hanno perso -0,16 R l'uno (-12,9 R):
    le perdite non vengono dai costi d'entrata ma dai trade. E' la domanda della fase 3.
  - **Pulizia**: tolto il Nameless di prova (`kaggle_rete/nameless.py`, mai acceso). Il resto (cervelli di settembre, Capo
    di prima, metodo dei video, la rete che giudica dopo l'equipe) lo usa ancora il bot di oggi: si toglie nella fase 5,
    quando Nameless prende il comando, per non toccare il bot che lavora.
- **Fase 0 chiusa** (13/10/2026): la cella dei dati ha girato su Kaggle in 235 minuti, 85 mercati pronti su 86 (notebook
  `nvmeless/notebookcd42dcf8f1`), tutti con gli orari di TradingView (le 18 di New York; UTC le crypto). Il controllo di
  qualita' (`mercati.json`) ha tolto UNI (la crypto: un'ora vera da +60% a febbraio 2024 e pezzi sotto i 4 anni), il DAX
  dopo giugno 2020 (HistData ci mette altri valori), AUDJPY nel 2005 e nel 2012, DOGE prima del 29/01/2021. Finiscono
  prima: oro in euro, sterline, franchi e dollari australiani e l'Euro Stoxx (2018-2019), il WTI (dicembre 2023).
- Fase 1, pronta da lanciare appena c'e' il dataset della fase 0:
  - **I sensi** (`nvm/nameless/sensi.py`): le candele di tutti i mercati sui nove timeframe del proprietario (1h, 4h,
    6h, 12h, 1d, 1w, 1m, 3m, 12m) con gli orari di TradingView. Ogni ora vede solo candele gia' chiuse, e solo del
    suo mercato.
  - **Gli occhi** (`nvm/nameless/occhi.py`): un transformer che legge 40 candele per timeframe, tutte insieme. La scuola
    nasconde candele a caso (leggere) o tutto quello che chiude dopo un taglio da 1 a 24 ore indietro (prevedere). La
    rete parte da "copia l'ultima candela" e impara solo la correzione: quello che fa meglio, l'ha imparato. Accanto a
    ogni candela vede la candela vista prima e quella vista dopo (il vicinato): nella prova qui, a parita' di passi,
    impara molto piu' in fretta (al primo controllo sbaglia il 42% di chi copia invece del 98%).
  - **L'esame** (dal 2023): per ogni timeframe e nei due modi, errore piu' basso di chi copia l'ultima candela (dove
    ci sono almeno 200 candele da confrontare). In piu', solo da leggere: sulla chiusura del futuro, la rete contro chi
    dice "il prezzo resta dov'e'". E' la direzione: non e' l'esame di questa fase, e se resta vicino al 100% e' normale.
  - **La cella**: `python -m kaggle_rete.cella_unica occhi` (scheda grafica, 3 ore). Porta dentro di se' i file nuovi,
    cosi' il proprietario non deve scaricare e ricaricare il codice (*"non riesco a scaricare lo zip, la connessione
    muore"*); se e' copiata a meta' lo dice. Input: `nvm-codice` com'e' (quello della fase 0) e l'output del notebook
    dei dati. Nell'output: `occhi_nameless.pt` (la rete, da cui parte la fase 2) ed `esame_occhi.json`. Con il codice
    aggiornato su Kaggle basta `kaggle_rete/cella_occhi.txt`.
  - **Prova qui, sul processore** (5 mercati: EURUSD, GBPUSD, XAUUSD, DXY, SPX500; rete piccola, 48 minuti, 2112
    passi): esame passato. Candele nascoste a caso: la rete sbaglia il 20-32% di chi copia su ogni timeframe. Il futuro:
    dal 93% (1h) al 14% (1w) di chi copia. Sulla direzione (la chiusura del futuro) il 103% di chi dice "resta dov'e'":
    nessun vantaggio sulla direzione, come ci si aspetta da questa fase. Su Kaggle: tutti i mercati, rete piu' grande,
    tanti piu' passi.
