# Dove siamo

_Aggiornato il 13/10/2026._

Ogni sessione di lavoro parte da qui e, prima di chiudere, aggiorna questo
file. Il piano completo è in `documenti/PIANO.md`.

## 14/10/2026: fase 1 di Nameless passata, si lancia la fase 2

Gli occhi hanno passato l'esame su Kaggle (3 ore, tutti i mercati): leggono le candele nascoste molto meglio di chi
copia l'ultima (dal 4% al 17% del suo errore) e prevedono la forma delle prossime candele; sulla direzione nessun
vantaggio, come previsto. Prossimo passo: la fase 2 (`kaggle_rete/cella_zone.txt`). Dettagli in
`documenti/PROGETTO-NAMELESS.md`.

## 14/10/2026 (notte): fase 2 di Nameless pronta, le zone

Mentre su Kaggle gira la fase 1, preparata la fase 2: le risposte delle regole delle foto per ogni CRT e ogni candela
(rifanno le 24 foto come il bot) e una testa per materia sopra gli occhi. Esame dal 2023: ogni materia al 98% e le 24
foto. Si lancia dopo l'esame degli occhi con `kaggle_rete/cella_zone.txt` e il codice nuovo (`nvm-codice.zip` come
nuova versione del dataset). Dettagli: `documenti/PROGETTO-NAMELESS.md`, "A che punto siamo".

## 13/10/2026 (notte, dopo): fase 1 di Nameless pronta, gli occhi

Mentre Kaggle scarica i dati, preparata la fase 1: la rete che legge i nove timeframe del proprietario tutti insieme, con
gli orari di TradingView, e impara indovinando candele nascoste (a caso, o tutto quello dopo un taglio: il futuro).
Esame dal 2023: meglio di chi copia l'ultima candela, su ogni timeframe. Provata qui su 5 mercati (48 minuti sul
processore): passata. Sulla direzione nessun vantaggio, com'e' normale in questa fase. Si lancia con
la cella unica (`python -m kaggle_rete.cella_unica occhi`, niente da scaricare). La fase 0 e' chiusa: 85 mercati su 86
pronti su Kaggle. Dettagli: `documenti/PROGETTO-NAMELESS.md`, "A che punto siamo".

## 13/10/2026 (notte): fase 0 di Nameless

Il proprietario ha dato il via; i dati li scarica Kaggle. Fatto: 24 foto su 24 anche con gli orari di TradingView;
lo scaricamento di tutti i mercati su Kaggle (66 da HistData, 20 crypto da Binance: `kaggle_rete/cella_dati.txt`); i
costi veri del demo (l'entrata e' al prezzo voluto, le perdite vengono dai trade, non dai costi); tolto il Nameless di
prova. Dettagli e cosa manca: `documenti/PROGETTO-NAMELESS.md`, "A che punto siamo".

## 13/10/2026 (sera): il progetto Nameless

Il proprietario: *"voglio creare un cervello funzionante, voglio creare un trader che funzioni realmente, come se fosse
una persona"*. Deciso il piano: **`documenti/PROGETTO-NAMELESS.md`** (un solo cervello al posto di regole, équipe,
rete e modelli separati; sei fasi, ognuna con un esame; le due pagelle, mestiere e risultato; Kaggle ogni settimana; il
libro del socio nella fase 6). Prossimo passo: fase 0 (un solo percorso, dati di tutti i mercati sugli orari di
TradingView, costi veri), appena il proprietario dà il via e conferma il paracadute (2% per trade, 20% dal massimo).

## 13/10/2026 (pomeriggio): le candele di TradingView così come sono

Il proprietario ha visto un CRT a 4 ore di EURUSD aperto alle 15 italiane: era una candela di MT5 (23-3-7-11-15-19),
mentre sul suo grafico di TradingView le 4 ore vanno 0-4-8-12-16-20 e quella candela non era ancora finita. Il bot
scaricava da TradingView solo le ore e si costruiva il resto con gli orari di MT5. Il proprietario: *"non deve
costruire niente ma utilizzare i dati con gli orari che gli vengono forniti così come sono"*, *"1h 4h 6h 12h 1d 1w 1m 3m
12m"*. Adesso, sui grafici di TradingView, il bot prende da TradingView ogni timeframe così com'è (1 ora, 4 ore, giorno,
settimana, mese; 6 e 12 ore e 3, 6, 12 mesi se TradingView li dà, se no li mette insieme dalle sue candele sulla sua
griglia e lo dice una volta), legge l'orario di ogni grafico dalle sue candele a 4 ore, e bot e rete lavorano su quelle.
La prima partenza scarica tutto (qualche minuto); poi le candele restano su disco (`dati/vivo/tradingview_candele.pkl`)
e il bot riprende un timeframe solo quando ne chiude una candela.

## 13/10/2026: foto per foto, il bot e la rete fanno quello che c'è sulle foto

Il proprietario: *"vedi una foto, vedi la rete neurale che fa, vedi un'altra foto ... fino a quando quello che sta
scritto su quelle foto non lo fa anche la rete neurale"*; *"quelli sono i trade che il bot e la rete neurale devono
fare. Sono esattamente quelli. Su ogni pair"*. Il libro del socio è messo da parte (*"lasciamo perdere il libro"*).

Rifatte le 24 foto (cartelle 2-5, CASO-009, e i tre trade aperti dal bot il 07/10 con le correzioni del proprietario
sui suoi grafici) con tutta la catena del bot dal vivo: CRT, key level, direzione, target finale, piano, regole della
squadra, rete. Prima il bot ne prendeva 16 su 23 e la rete da sola 3 su 22. Adesso **24 su 24**: le 22 da prendere
col target della foto (entro la differenza fra future e spot), la 5/6 e il franco-yen lasciati. Il Bitcoin (2/4) non
si può provare: mancano i dati. Le regole cambiate, ognuna con la foto che la decide, sono in
`documenti/spec/metodo_foto.md` e nel registro; in breve:

- i metalli con le candele del future, dalle 18 di New York (i CRT a 4 ore dell'oro delle foto);
- la candela precedente dei 3 e 12 mesi che ha accettato contro blocca solo il CRT a 1 ora che ha preso soltanto
  livelli del giorno (il franco-yen); un gap contro nella reazione automatica dà la direzione (la liquidazione);
- la terza candela di un gap accetta solo se ha più corpo che ombra (dal libro del socio: *"se è direzionale"*), e
  oltre un gap che ha accettato non si punta (euro-australiano: il DH);
- la liquidazione è il target quando l'estremo dell'aggressione è un key level (3/4, 4/6: il WL; 4/1: il minimo dei 3
  mesi), mai un estremo qualunque (euro-yen: il DH); dentro un gap già toccato vale solo un gap di timeframe uguale o
  più grande (il gap annuale del DXY, il gap dei 3 mesi dell'argento);
- rendimento minimo al target **1 R** invece di 1,5: la foto 2/8 sta a 1,1 R e la 3/1 a 1,4 R; i trade del demo a 0,9,
  0,7 e 0,1 R restano fuori. **Se il proprietario rivuole 1,5, è `foto.RR_MINIMO`** (allora 2/8 e 3/1 non si prendono);
- la rete neurale sui setup con tutte le regole entra sempre: la sua stima la scrive, ma lì non decide lei.

Da sapere, onestamente: la stima della rete su queste foto è negativa (da −0,04 a −0,88 R a trade). Non è un errore di
lettura: è la media che ha visto sui vent'anni per setup simili, e le misure del bot sui vent'anni sono negative. Le foto
sono trade scelti che sono andati bene; il bot ora li prende tutti, e prende anche tutti quelli uguali che vanno male.
Il risultato vero si vede sul demo.

`python -m strumenti.foto --dati <cartella>` rifà la prova; una foto nuova del proprietario si aggiunge con una riga.

## 12/10/2026 (sera, dopo): il libro del socio e il PDF della mentorship di Romeo

Il proprietario: *"addestriamo la rete neurale sui video di Romeo"* e sul materiale del socio; poi ha caricato sul
ramo `main` il libro del socio (*"non c'entra il crt ma la sua strategia"*) e i 17 video di Romeo già lavorati
(gli stessi di `documenti/spec/metodo_romeo.md`). Il proprietario non vuole il nome del socio nel repository. La strategia del
libro, in regole e con cosa manca nel bot, è in `documenti/spec/metodo_libro.md` (*"nel libro ci sta scritto tutto"*: le
scelte vengono dal libro); il PDF "Romeo's Private Mentorship" (di uno studente, @ict_nandhu) è in
`documenti/spec/FONTI-ROMEO.md`; il TP1 resta l'altro lato del range (il 50% era già stato tolto). I rivelatori sono in
`nvm/agenti/struttura.py` (struttura A-B, inducement, EPA, MSU). Prima misura sui vent'anni (fino al 2022, 6
strumenti): **negativa**, R −0,097 sul 2008-2019 e −0,288 sul 2020-2022, poche occasioni
(`documenti/registro/tentativi.md`): la traduzione delle regole va rifatta prima di darla alla rete.

Su richiesta del proprietario (*"sistema pure GitHub ... fai tu"*) la cartella è riordinata: nella radice restano
il bot (`vivo.py`) e i `.bat`; gli script sono in `strumenti/` (si lanciano come `python -m strumenti.misura`, i
`.bat` lo fanno da soli), i documenti in `documenti/` (con `spec/`, `casi/` e le foto in `documenti/casi/foto/`,
`registro/`). Cancellati gli import del vecchio bot di settembre (`importa_vecchi.py`, `importa_candele_vecchie.py`,
`importa_grezzi.py` e la sua prova) e `nvm/cervello/memoria.py`, che nessuno usava più.

## 12/10/2026 (notte, fine): tutto automatico su TradingView, decide la rete

Il proprietario: *"metti tutto automatico sul bot, niente più richieste"*, *"no automatico con tw"*. Sulla risposta di
TradingView alla richiesta di permesso il proprietario ha riferito: *"ok, no problem. we can use the system"*, e *"niente
webhook però"*; la mail non e' stata vista qui (*"non posso mandarti foto"*): il permesso e' quello riferito dal
proprietario, che conserva la mail. Fatto: con TradingView il bot apre da solo quello che la rete prende (o la squadra,
se la rete non c'e'), con "🧠 PERCHÉ HO APERTO" e Correggi; quello che la rete lascia va in équipe con «Apri lo stesso».
Lo stesso sui prezzi del broker. Niente webhook (il bot non ne ha mai usati).

## 12/10/2026 (notte, ultima): la rete neurale decide cosa proporre, spiega, e si corregge

Il proprietario: *"voglio che sia la rete a decidere, così la addestriamo"*, con la spiegazione della sua analisi e una
sezione *"correggi"*. Fatto (`nvm/vivo/rete_vivo.py`, pesi in `nvm/vivo/rete.pt`, VPS.md punto 7):
- la rete del passo 2 (occhi + scheda, Kaggle) giudica ogni setup del metodo delle foto: stima in R, probabilita' di
  chiudere in guadagno, entra se sopra la soglia scelta sul 2020-2022 (-0,127 R, il 5% migliore dei setup del bot);
- spiegazione: le risposte degli occhi (direzione D/W/M, CRT 4 ore e del giorno, setup) e cosa la spinge/frena rispetto
  a un setup tipico del bot (gradienti integrati dalla mediana dei setup A+ dello studio e da un grafico piatto);
- con TradingView: quelli che prenderebbe sul canale operativo (Apri, Lascia, Correggi), quelli che lascia in équipe
  (Apri lo stesso, Correggi); Correggi = pulsanti per il trade e per ogni risposta degli occhi + spiegazione scritta
  in risposta; tutto in `dati/vivo/rete/` (correzioni.jsonl, analisi/*.npz con finestre e scheda del momento);
- la sera la pagella (giuste, e i suoi trade in R); `Seguita.rete` tiene il parere;
- i pulsanti: un filo legge Telegram sempre e risponde subito; il bot li esegue fra uno strumento e l'altro.

Da fare: riallenare la rete con le correzioni (quando ce ne sono abbastanza: arrivano con la consegna dei dati).

## 12/10/2026 (notte, dopo): la TOTAL guida BTC ed ETH

Il proprietario vuole le crypto con la TOTAL di TradingView; alla domanda su come la usa: *"B, esatto"*, cioe' come
il DXY ma nello stesso verso: un setup CRT sulla TOTAL fa entrare su BTC ed ETH dalla stessa parte (`foto.dal_totale`,
`foto.CRYPTO_TOTALE`). Si accende con `TRADINGVIEW_TOTAL=CRYPTOCAP:TOTAL` nel `.env` (solo con l'analisi su
TradingView); la TOTAL ha gli orari delle crypto (giorni da mezzanotte UTC). In squadra parla l'agente DXY ("il
setup l'ha fatto la TOTAL"), il key level e' quello preso dalla TOTAL, come per i setup del DXY.

## 12/10/2026 (notte): l'analisi su TradingView, con i pulsanti Apri / Lascia

Il proprietario: *"io voglio che la rete neurale analizzi il mercato su TradingView, sui pair che dico io, dei broker
che dico io, e operi su MetaTrader 5"*. Le condizioni di TradingView (sezione 3) vietano il trading automatico sui loro
dati senza un permesso scritto: il proprietario manda la richiesta a TradingView; intanto *"iniziamo facendo apri e
lascia"*. Fatto (`nvm/vivo/tradingview.py`, VPS.md punto 6):
- con `TRADINGVIEW_SIMBOLI` nel `.env` le candele (ore, quarti d'ora, giornaliere, DXY) arrivano da TradingView col
  server MCP ufficiale (`get_ohlcv`, 5.000 candele al massimo: circa 10 mesi di ore, il resto dalle giornaliere);
  login una volta con `tradingview_accesso.bat`, rinnovo da solo, chiavi in `dati/vivo/tradingview.json`;
- quando la squadra entra, invece dell'ordine arriva la proposta coi pulsanti; con Apri si entra su MT5 a mercato con
  stop e target di TradingView (controlli: scadenza 30 minuti, oltre stop/TP1, RR almeno 1,5, una per strumento);
  ogni scelta va nel registro ("scelta del proprietario");
- senza la riga nel `.env` il bot lavora come prima, su MT5. Se TradingView non risponde: allarme, niente analisi,
  mai i prezzi di MT5 di nascosto.

Da fare: il login sulla VPS e la riga nel `.env` (li fa il proprietario); la mail a TradingView per il permesso. Il
formato preciso della risposta di `get_ohlcv` non e' documentato: il bot cerca la lista di candele `t, o, h, l, c`
dentro la risposta, e `tradingview_accesso.bat` lo verifica sulla VPS.

## 12/10/2026 (sera): lo stop troppo vicino si allarga, non si scarta

Il proprietario: *"se vede che c'ha uno stop troppo piccolo, aumenta di poco lo stop ... da un minimo di 5 o 10
pips ... non lo levare, perché esistono dei setup dove ci sta uno stop minuscolo e partono"*. Lo stop resta
sull'estremo della candela 2; se e' piu' vicino all'ingresso di `foto.stop_minimo` (il piu' grande fra 5 pip e il 7%
del range giornaliero medio di 14 giorni: EURUSD circa 5 pip, GBPJPY circa 10, oro circa 5 dollari) si allarga fin
li'. Vale dal vivo e nello studio della rete (prima nello studio quei setup, il 3,6%, erano stati tolti: con lo stop
quasi sull'ingresso il risultato in R esplodeva).

## 12/10/2026 (pomeriggio, dopo): lo stoppino del rollover non e' una presa

GBPCAD del 9/10, CRT H6 long: per il bot la candela 2 aveva preso il DL (1.88009) con un minimo a 1.87890. Il
proprietario: *"il prezzo non ha preso in primis kl, il dl non è stato sbilanciato"*. Era cosi': quel minimo c'e' solo
su FP, alle 23 italiane (il rollover, le 17 di New York: sui conti raw lo spread si allarga e il bid fa stoppini);
su HistData e Yahoo quell'ora restava 8-10 pip piu' su (1.87973, 1.87989) e il DL non era preso. Adesso la presa
del range e dei key level della candela 2 si guarda senza l'ora del rollover (`foto._senza_rollover`); lo stop
resta sull'estremo vero della candela 2. Il TP1 di quel trade era a 0,6 volte il rischio: con l'1:1,5 non si
aprirebbe comunque. Gli orari: MT5 di FP mostra l'ora del server, un'ora avanti all'Italia (le 06:00 di MT5 sono le
05:00 italiane del messaggio).

## 12/10/2026 (pomeriggio): le regole decidono, la squadra da' solo il parere; target almeno all'altro lato

Un AUDUSD da manuale (presi WH e DH, poi CRT H1 alle 04:00 italiane, stop sul massimo della candela 2, TP1 al
completamento del CRT con BE e 25%, target finale almeno il DL) il bot l'aveva trovato "con tutte le regole del
metodo", ma il Capo l'ha lasciato perche' la squadra non arrivava a +3 (Grilletto -1). Il proprietario: *"tu devi
seguire quello che c'è scritto nelle foto e tutte le varie cose che io ti ho detto"*, *"fai direttamente"*.

- Con tutte le regole del metodo (CRT, key level, direzione) e almeno 1:1,5 si entra: i punti della squadra sono un
  parere e si dicono in equipe, ma non bloccano (`squadra.riunione`). Restano i no delle regole (mai contro la
  previsione), il massimo di 3 per giro, uno per strumento, e il Rischio che decide quanto.
- Il target finale non sta mai prima dell'altro lato del key level piu' piccolo preso (`foto.target_minimo`: preso
  il DH, almeno il DL). Stamattina il bot aveva preso come target un gap piu' vicino del DL. Tutti gli esempi delle
  foto hanno gia' il target li' o oltre: i loro test passano uguali.

## 12/10/2026: mai sotto 1 a 1,5

Tre trade del demo su H6 (AUDUSD, GBPUSD, US30, tutti short) avevano rendimento al target finale di 0,9, 0,7 e
0,1 volte il rischio: su US30 la candela 2 aveva chiuso quasi sul target. Il proprietario: *"1/1,5"*. Adesso un piano
(`giro.piani_foto`) che al suo ultimo target non rende almeno `foto.RR_MINIMO` = 1,5 R non si usa, e se nessun piano
ci arriva il setup non si prende. Degli esempi delle foto del proprietario uno solo resta sotto: il 3/1 (EURUSD
mensile long di dicembre 2025, 1,37 R al suo target).

## 12/10/2026: la rete allenata su Kaggle con la scheda grafica

Il proprietario: *"sì posso anche allenare su kaggle ma non ho i dati"*. Dati gratis da HistData (`kaggle_rete/`,
`documenti/spec/rete.md`): 38 strumenti, forex dal 2002, il resto dal 2009-2010, con la pulizia dei pezzi sbagliati (il loro
orario segue l'ora legale europea; il loro DXY prima del 2018 e' il Dow Jones). Una notte su una Tesla T4: rete da
826 mila pesi, 577 mila esempi per imparare, 6 ore (bastavano 2: il controllo si ferma a 0.945 al minuto 121).

All'esame dal 2023 (212 mila casi, `documenti/registro/misure/2026-10-12-rete-kaggle.txt`): direzione di giorno e settimana
giusta 94%, mese 90%; CRT a 4 ore e del giorno trovati 93-99%, e quando la rete dice "c'e'" ha ragione 74-81% delle
volte (ieri 37-39%); setup trovati 94-98%, ma quando dice "setup" ha ragione solo 42-45% (ieri 12-21%). Controllo ed
esame quasi uguali: non ha imparato a memoria. Gli occhi sono la base per il passo 2 (la scuola dei risultati).
Pesi (`occhi.pt`) nell'output di Kaggle e nello zip del proprietario, non nel repository.

## 11/10/2026: la rete neurale, prima parte (scuole 1 e 2)

Il proprietario: *"iniziamo creando la rete neurale"*. Fatto `nvm/rete/` (scheda `documenti/spec/rete.md`): la rete vede le
ultime 40 candele chiuse a 1 ora, 4 ore, giorno, settimana e mese (candele di MT5, senza futuro); scuola 1 indovina
le candele nascoste, scuola 2 risponde come gli agenti (direzione di giorno, settimana e mese; CRT a 4 ore e del
giorno; setup completo). Transformer piccolo (166 mila pesi); impara fino al 2019, controllo 2020-2022, esame dal
2023. PyTorch solo per allenare (`requirements-rete.txt`), il bot dal vivo non la usa.

Primo allenamento (45 minuti, 6 strumenti, `documenti/registro/misure/2026-10-11-rete.txt`), all'esame dal 2023: i CRT e i setup
del giorno li trova quasi tutti (richiamo medio 93%) ma con tanti falsi allarmi (quando dice "c'e'", c'e' 2-4 volte su
10); a 4 ore richiamo 72% (CRT) e 80% (setup); la direzione di giorno, settimana e mese solo in parte (59-61% medio
per giorno e settimana, 54% per il mese). Il controllo saliva ancora a ogni misura: va allenata piu' a lungo.

## 08/10/2026 (notte): il comando /piano

Il proprietario: *"puoi modificare quel segnale su mt5? dicendo al bot di prendere il TP1, mettere il TP finale e mettere
a BE una volta preso il TP1 e preso il 25%"*. Nuovo comando Telegram «/piano STRUMENTO TP1 TPFINALE» (`vivo._piano`):
sull'operazione aperta il TP finale va su MT5, il bot tiene il TP1 col 25% e il pareggio; lo stop non cambia. Non va se
il TP1 è già stato preso o se i prezzi sono dal lato sbagliato.

## 08/10/2026 (sera, ultima): le candele come su MT5, dalle 17 di New York

Il bot ha comprato SPX500 su un CRT a 4 ore alle 16 italiane a 7778.29; su MT5 la candela 2 chiudeva alle 15 a circa
7768 e il TP1 (massimo della candela 1) era più in alto: il bot tagliava le 4 ore alle 0-4-8-12-16-20 italiane (i
future, dal 06/10), MT5 alle 23-3-7-11-15-19. Il proprietario: *"mi adatti immediatamente l'orario, per favore, perché
se no così sta cosa non si risolverà mai"*. Fatto (`nvm/tempo.py`, SPOSTAMENTO 7 ore): forex, oro e indici con le
candele di MT5, giorno dalle 17 di New York; le giornaliere del broker non si spostano più. Le crypto restano sul
calendario UTC. Degli esempi delle foto 13 su 14 tornano uguali; il 5/8 (oro 4 ore, 02/09/2026) non è più un CRT (era
uno dei tre che lo erano solo coi future, e il 3 mesi lo bloccava già). 305 prove passano.

## 08/10/2026 (sera, dopo): via BTC ed ETH; le correlazioni col DXY

- Il proprietario: *"togliamo dagli asset del bot btc e ethusd"*: tolti (`vivo.TOLTI`), il bot guarda 35 mercati.
- La foto delle correlazioni del proprietario: il forex col dollaro segue il DXY al 100% (*"quando lui sale tutte le
  coppie forex scendono e viceversa"*); oro, argento, S&P 500, Dow e Nasdaq circa all'85% (*"a volte può capitare che
  il DXY va long e anche gold va long"*); *"è più importante il grafico del DXY per determinare la bias delle coppie
  forex"*. Fatto: l'agente DXY pesa 2 sul forex e 1 su oro, argento e indici (`foto.CORRELATI_85`); un setup del DXY
  ne crea uno sulla coppia solo sul forex; il Bias delle coppie forex mette prima la previsione del giorno del DXY
  (pesa 2) e poi quella della coppia (pesa 1). La previsione della domenica resta quella di ogni strumento.
- Poi il proprietario: *"il dxy comanda la bias di tutti gli asset forex usd"*, e la foto del mensile del DXY come
  esempio di struttura e di cosa si aspetta nei prossimi anni (un CRT ribassista nei TF alti da cavalcare comprando
  EURUSD, GBPUSD). Fatto: sulle coppie forex col dollaro la previsione del giorno del DXY decide (pesa 2; quella della
  coppia conta solo se il DXY non ha direzione); la domenica vale quella del DXY, nel messaggio e nel veto; di fondo
  il DXY è ribassista (`foto.FONDO_DXY`, pesa 1). Nessun livello della foto è scritto nel bot.

## 08/10/2026 (sera): il DXY dal grafico USDX del broker; la finestra di avvia.bat dice a che punto è

- Il proprietario: *"il dxy non dovrà più essere generato ma bisognerà far sì che l'agente dxy analizzi il grafico che
  su fptrading si chiama USDX"*. Dal vivo l'agente DXY legge il grafico del broker (`terminale.GRAFICI`: USDX, DXY,
  DX, col suffisso o senza): all'avvio due anni di ore, poi ogni ora le nuove, e le giornaliere lunghe. Non si
  calcola più dalle coppie: se il conto non ha USDX, l'agente DXY resta neutro e arriva un allarme. Il DXY calcolato
  (`foto.dxy`) resta solo per le prove sullo storico, dove il grafico non c'è.
- Il proprietario: *"quando faccio avvia.bat rimane bloccato"* (e su Telegram niente). Ora la finestra scrive ogni
  passo dell'avvio con l'ora (MT5, conto, ora del server, candele strumento per strumento, USDX, Telegram) e gli
  allarmi: si vede dove si ferma. `avvia.bat` non è cambiato.
- 303 prove passano.

## 08/10/2026 (pomeriggio): le crypto con gli orari crypto

Il bot alle 6 di New York ha comprato BTC su un CRT a 6 ore. Il proprietario: *"nel tf h6 non abbiamo avuto una
presa liquidità ma bensì il prezzo ha accettato a ribasso"*; *"la candela giornaliera delle crypto apre alle 2 e non
a 00, quindi la prima candela h4 apre alle 2,6,10,14 ... la prima candela h6 apre alle 2,8 ... h12 che apre alle 2"*;
*"basati solo sulle crypto, per la total poi vedremo"*. Il bot tagliava anche le crypto dalle 18 di New York: con
quelle candele la notte del 7-8/10 era un CRT, con quelle crypto la candela 2 (2-8 italiane) chiudeva sotto il range.

- Solo per le crypto (BTCUSD, ETHUSD), `nvm/tempo.py`: candele sul calendario UTC, giornata a mezzanotte UTC (le 2
  italiane d'estate, l'1 d'inverno), 4 ore alle 0-4-8-12-16-20 UTC, 6 ore alle 0-6-12-18, 12 ore alle 0 e alle 12,
  settimana da lunedì a mezzanotte UTC, mese, 3, 6 e 12 mesi dal giorno 1 a mezzanotte UTC. Forex, oro, indici
  restano dalle 18 di New York.
- Le giornaliere lunghe del broker per le crypto vanno al giorno UTC che coprono (`terminale.giornaliere`); il
  giorno e la settimana del Bias per le crypto sono quelli crypto (`pareri.apertura_giorno`, `pareri.settimana`); i
  disegni e il controllo della candela 2 passano il segno "crypto".
- Ogni crypto sui suoi CRT; il TOTAL (market cap) per ora no.
- Prova col caso vero (`tests/test_foto.py`, orarie BTC di Yahoo): a 6 ore niente CRT, a 4 ore il CRT rialzista
  con entrata alle 10 italiane. 301 prove passano.

## 08/10/2026: la squadra parla davvero e decide il Capo; mai contro la previsione della domenica

Il proprietario, dopo i dieci stop del 07/10: *"gli agenti non parlano tra di loro realmente e ... non seguono le
previsioni che fanno la domenica"*; *"il capo deve decidere quali CRT hanno più probabilità"*; Telegram con foto e
messaggi sfasati e l'équipe in cui non si capisce di che asset si parla. Fatto (`nvm/intelligenti/pareri.py`):

- **Primo giro**: ogni agente vota da −2 a +2 col suo mestiere e dice perché. **Secondo giro**: si sentono fra
  colleghi e chi ha un motivo cambia voto dicendolo per nome; un ascolto che dal vivo non aiuta si spegne.
- **Il Bias è fedele alle previsioni**: quella del giorno (fatta all'apertura, tenuta fino a sera) e quella della
  domenica, contro la quale il Capo non entra mai.
- **Il Capo** pesa tutti (impara dal vivo di chi fidarsi), entra con almeno +3 punti, in ogni giro mette i CRT in
  ordine di probabilità e prende i migliori (al massimo 3); in équipe dice cosa prende e cosa lascia, e se ne prende
  la responsabilità. Il giro raccoglie le occasioni di tutti gli strumenti prima di decidere.
- **Telegram**: l'apertura è la didascalia della sua foto; ogni messaggio in équipe comincia con 📌 e l'asset.

**Misura** (`documenti/registro/misure/2026-10-08-squadra.txt`, 6 strumenti): la squadra prende circa 3 operazioni a settimana
invece di 14 e perde molto meno del bot di adesso (2008–2018 −120 R contro −1098; 2019–2023 −161 contro −574;
2024–2026 −2 contro −287), ma per operazione non è ancora positiva (−0,07, −0,18, −0,005 R). La previsione della
domenica, nella storia, non separa le occasioni buone dalle cattive: si segue perché lo vuole il proprietario.

**Tolte su richiesta del proprietario** (*"Leva immediatamente queste ... cose che hai inserito senza che io te
l'abbia detto"*): l'Orario contro l'apertura di Wall Street e il rollover; Livelli contro lo stop sotto 0,3 del range;
il Cacciatore che preferiva i CRT dal giornaliero in su; una sola idea per valuta; il tetto del 5%, lo stop dopo il
3% perso nel giorno e il lotto arrotondato del Rischio (il Rischio è tornato com'era). La misura sopra era con quelle
regole dentro. Regola del proprietario: niente iniziative, si fa solo quello che chiede.

## 07/10/2026 (sera): TP1 al 25%, gap mitigati, la candela precedente comanda

Dai tre esempi dal vivo del proprietario (regole per tutto): al TP1 il 25%; un gap toccato o con la terza candela
che ha accettato non è un target (si va al key level); per giorno, settimana, 1, 3 e 12 mesi, se la candela
precedente ha accettato contro di noi e il suo livello non è preso, non si entra. Sei esempi vecchi non si
prendono più (il proprietario lo sa). Dettagli in `documenti/registro/tentativi.md`.

## 07/10/2026: una posizione sola per CRT, al massimo una aperta per strumento

Il bot apriva euro-dollaro di continuo e due posizioni per ogni CRT. Ora: una posizione sola (stop e target
finale sul broker; al TP1 il bot chiude metà e mette lo stop a pareggio, se il lotto si divide); lo stesso CRT
non si apre mai due volte; un errore su uno strumento non fa più ripartire il giro dell'ora. Le foto per
Telegram le disegna il bot (`nvm/vivo/foto_grafico.py`: sfondo bianco, candele verdi e rosse, solo
l'operazione). Il giro dell'ora non si rompe più (l'errore 34/31 del Capo di prima), non si entra oltre 10
minuti dall'apertura della candela 3, e al massimo un'operazione aperta per strumento (scelta del
proprietario dopo 62 operazioni in 30 ore nella prova del bot intero). Dettagli in `documenti/registro/tentativi.md`.

## 06/10/2026: il metodo delle foto del proprietario

Il proprietario ha mandato 23 esempi suoi (cartelle di foto, `documenti/casi/ESEMPI-PROPRIETARIO.md`) e ha risposto
*"come nelle foto"*. Il bot ora segue quelli (`documenti/spec/metodo_foto.md`, `nvm/agenti/foto.py`):

- **Candele come sui future**: aprono alle 18 di New York (mezzanotte italiana); in più 6 e 12 ore, 3, 6 e 12
  mesi. Con le candele di prima tre esempi suoi sull'oro non erano CRT.
- **Entrata all'apertura della candela 3**, a qualunque ora; **stop oltre la candela 2**; **TP1 all'altro lato
  del range** (metà e pareggio); **target finale** il gap del timeframe grande, o il key level, o la
  liquidazione di un gap che ha appena reagito. Il range è la candela madre se ci sono inside bar.
- **Obbligatori**: CRT, key level (massimo o minimo del periodo prima, preso dal CRT), direzione del
  timeframe di comando. CRT a 1 ora solo col key level del giorno e il massimo/minimo delle 4 ore.
- **Gap** con le fasi (aggressione, reazione, liquidazione, continuazione con l'RSI) e **DXY** sintetico: due
  agenti nuovi nella squadra (memoria nuova `foto-1`).
- **Verifica**: tutti e 17 gli esempi controllabili danno il setup; il target finale coincide in 13 (gli altri
  4 sono oro 2026, dove mancano i dati di marzo). Prove in `tests/test_foto.py`.
- **La routine settimanale dei vent'anni è spenta** (il proprietario: *"a tua discrezione"*).
- Il bot dal vivo prende anche le giornaliere lunghe da MT5 (per i 3, 6, 12 mesi).

**Da sapere:** circa 12 setup a settimana per strumento. 07/10/2026: la candela 2 non deve sforare (niente
tolleranza); più operazioni sullo stesso strumento le decide il Rischio (punta meno e impara quanto); il
comando `/strumenti` dà la lista di tutti gli strumenti del broker. Tolti Brent, FTSE e Nikkei: 37 strumenti.

## 01/10/2026: la strategia dei video alla lettera, e una squadra che impara davvero

Il proprietario: *"Voglio che tutto quello che ho chiesto venga fatto e che non sono preso in giro… bot
intelligente e strategia di Romeo"*. Confronto riga per riga del codice con i 17 video (pacchi nel ramo
`main`: 13 con il parlato, V7, V13, V14 e V15 solo fotogrammi). Cambiato:

- **Apertura di Romeo**: giorno, settimana e mese a mezzanotte di New York (prima: 17:00 e domenica sera).
- **Model#1 sul vecchio massimo**: la candela spessa deve prendere un massimo di swing mai ripreso (prima
  bastava un massimo nuovo dentro la candela 3).
- **Le tre entrate di Romeo**: Model#1, vera rottura di struttura col ritorno nella zona, kiss of death
  dopo il 50% (prima solo il Model#1).
- **Orario dei video** sull'ora della finta: Londra o mattina di New York; settimana lunedì-mercoledì;
  mese prime due settimane (prima: 2-11 NY e "primo 60% della candela").
- **Sempre un parziale al 50%**: Livelli sceglie fra tre piani di Romeo (prima nove, anche senza 50%).
- **SMT**: solo le coppie di Romeo, solo con la vera rottura a confermarlo; con l'SMT confermato contro si
  esce prima del primo obiettivo. **KOD**: dopo il primo obiettivo, chiusura oltre il kiss of death = si esce.
- **La squadra** (`nvm/intelligenti/squadra.py`, memoria nuova `video-2`): ogni agente ha un suo modello
  appreso dal vivo sui numeri del suo mestiere; secondo giro di ascolto con le regole di Romeo che legano i
  mestieri, pesi appresi; il Capo pesa i giudizi (fiducia appresa) e guarda i casi simili; lascia un'A+ solo
  con almeno 15 casi simili in perdita con certezza; impara prima dai risultati veri del broker.
- **Testi onesti**: benvenuto e `documenti/MANUALE.md` dicono cosa fa il codice, senza "cervelli che ragionano".

**Da sapere:** le regole nuove non sono misurate sui vent'anni (i dati sono sulla VPS); il kiss of death e
la vera rottura, provati da soli il 30/09, rendevano meno del Model#1. All'avvio la memoria della squadra
riparte da zero: i primi giudizi diranno "non ho ancora esperienza".

## Dove siamo: il metro diventa Romeo

**A.** Il CRT di RomeoTPT si riscrive dalle fonti, partendo dal
**Cacciatore** (l'agente che risponde a "c'è un CRT qui?").

- **Fatto:** fonti raccolte (`documenti/spec/FONTI-ROMEO.md`); regole del Cacciatore
  decise sulle fonti, con una variante dichiarata (`documenti/spec/cacciatore.md`);
  schede del Grilletto (`documenti/spec/grilletto.md`) e delle prime conferme
  (`documenti/spec/conferme.md`).
- **Manca:** altri casi fino a 20 CRT, e i casi "non è un CRT"; le schede
  di Rischio e Sentinella. CASO-001 (GBPUSD a 15 minuti) aspetta i minuti.
- **Casi verificati sui dati:** sette, da CASO-002 a CASO-008 (EURUSD
  giornaliero, settimanale e mensile, XAUUSD giornaliero, 2024–2025). Il
  bot ritrova tutti i CRT di Romeo, con livelli entro 1–2 pip. Hanno
  corretto tre regole: la durata dell'operazione (due volte), i tentativi
  del Grilletto, e hanno fatto nascere la variante "stop stretto". Dove si
  vede l'ingresso, Romeo entra su un timeframe più basso e più in alto del
  bot, spesso al secondo colpo. Obiettivo del PIANO: 20 CRT e 10 "non è un
  CRT"; per ora 8 e 0.
- **Fonte nuova (msg 6718, febbraio 2026):** una pagina del manuale di
  Romeo, "Elements of a high probability trade setup": key level del
  timeframe alto, ora della manipolazione, massimo prima della
  manipolazione; *"ignore the fvgs, obs, brks"*.
- **Varianti dichiarate:** 3 su 3, e non se ne aggiungono altre. "Chiusura
  dentro" per il Cacciatore, "stop stretto" per Livelli, "un gradino sotto"
  per il Grilletto (scritta il 24/09 prima di misurarla,
  `documenti/spec/grilletto.md`).
- **Già pronto per la Fase C:** il codice del Cacciatore
  (`nvm/agenti/cacciatore.py`), con la variante dichiarata e le prove sugli
  schemi di Romeo, compresa quella che controlla che non sbirci il futuro.
  Non si considera buono finché non passa i casi.

**B.** Una fonte sola, candele ricostruite con la giornata che chiude alle
17:00 di New York (`documenti/spec/dati.md`).

- **Fatto:** scaricatore, candele, controlli (`nvm/dati/`, `strumenti/scarica.py`).
  Verificato il pacchetto del vecchio branch: minuti e orarie giusti, 4 ore
  e giornaliere su confini sbagliati (`documenti/registro/verifica-dati-vecchi.md`).
- **Fatto:** vent'anni di ore con bid e ask per i sei strumenti, dai file
  Dukascopy del vecchio bot. Verificati identici, bid e ask, a quelli
  scaricati direttamente. I cinque mesi che mancavano prima del 2024 sono
  stati scaricati il 24/09: lo storico 2006–2023 è completo. AUDUSD
  2007–2010 ha dati sporchi (buchi, ask sotto il bid): da tenere presente.
- **Manca:** i quindici minuti e i minuti di vent'anni (per la coppia 4 ore
  → 15 minuti e per entrare come Romeo, sul timeframe basso). Da qui
  Dukascopy risponde piano: un mese di ore richiede da 30 secondi a 10
  minuti.

**E.** Le prime conferme sono scritte, provate e misurate
(`documenti/spec/conferme.md`, `nvm/agenti/conferme.py`): key level, orario, bias.
Nessuna, da sola, separa le operazioni buone dalle cattive in modo stabile.

**F (24/09).** Il Capo (`documenti/spec/capo.md`, `nvm/agenti/capo.py`, `strumenti/capo.py`)
ha pesato le conferme anno per anno, senza guardare avanti, in otto
configurazioni: le quattro di partenza e le stesse con l'ingresso "un
gradino sotto", la terza e ultima variante. **Nessuna passa il cancello.**
Il Capo non si fida delle conferme: guarda quasi solo quanto sono lontani
target e stop. E l'ingresso un gradino sotto, che doveva avvicinarci a come
entra Romeo, va peggio del manuale.

È il caso scritto nel `documenti/PIANO.md` §3, "Dove ci si ferma": **il CRT di
Romeo, così come è scritto, non guadagna dopo i costi. Non si aggiungono
regole per farlo passare: si decide cosa fare con quel numero davanti.**
Resta da misurare solo il giornaliero → 15 minuti della terza variante,
che aspetta vent'anni di minuti (da qui Dukascopy ne dà uno ogni 30–75
secondi: un anno di uno strumento richiede circa 11 ore).

**Il metro Romeo (24/09).** Guardate tutte le 1.266 foto del suo canale
(marzo 2023 – settembre 2026). Le sue entrate lette dalle foto sono in
`documenti/casi/entrate-romeo.csv`: 112, di cui 62 del 2023 (periodo di studio) e 50
del 2024–2026 (chiuse fino alla Fase G); 15 sono su indici (NAS100,
S&P 500), che non abbiamo ancora nei dati. `python -m strumenti.romeo` le controlla
sui prezzi veri e le confronta col bot (`documenti/registro/misure/2026-09-24-romeo.txt`):

- **Le letture reggono:** per tutte le 82 entrate con un prezzo letto, il
  prezzo è passato davvero di lì nella finestra. L'ora del suo server è New
  York + 7 ore; le ore lette sull'asse dei grafici sbagliano di 1–2 ore, e
  per quelle la finestra è larga.
- **Il bot oggi non entra come Romeo.** Delle 25 entrate del 2023 con
  ingresso e stop letti, il bot ne ritrova 6 entro metà del rischio di
  Romeo (3 con il filtro del Capo). Il cancello chiede 7 su 10. E ne fa
  troppe: nelle settimane in cui Romeo entra, 25,8 operazioni per ognuna
  delle sue (7,2 col Capo); il cancello ne chiede al massimo 3.
- **Perché:** le sei ritrovate sono sue idee sul timeframe alto (stop di
  20–70 pip). Le sue esecuzioni sono sul minuto–15 minuti con stop di 1–9
  pip, in due fasce orarie (1–5 e 8:30–10:45 di New York): senza i minuti
  il bot non le può nemmeno vedere. E un CRT armato nel suo verso c'è quasi
  sempre (49 volte su 53), ma c'è anche nel verso opposto (45): vedere un
  CRT non distingue la scelta di Romeo. La scelta sta nell'ora, nel key
  level e nel bias, cioè negli agenti che il Capo oggi quasi ignora.
- **Il Capo impara Romeo (24/09, sera).** Le risposte di prima non
  distinguono le scelte di Romeo (fuori campione, come tirare a sorte).
  Quattro risposte nuove, prese dalle sue frasi (`documenti/spec/conferme.md`): l'ora
  di Londra (1–5 NY) e di New York (8–11 NY), il CRT dentro uno più grande,
  il comprare a sconto sulla settimana. Il Capo impara dalle entrate di
  Romeo del 2023 quanto un'operazione gli somiglia (fuori campione 0,59,
  dove il caso è 0,5). **È un parere, non un obbligo** (decisione
  dell'utente: *"addestrare non significa obbligarlo e imporgli delle
  cose"*): l'équipe lo sente, il Capo decide col guadagno atteso e impara
  dai risultati quanto pesare le risposte alla Romeo. Il cancello del
  PIANO (7 su 10, al massimo 3 per ognuna) è il nostro metro per giudicare
  il bot, non una regola dentro il bot.
- **Il Capo come cervello di Romeo (proposta approvata dall'utente, 24/09).**
  Le scelte di Romeo fra i candidati del 2023 hanno preso il primo target
  nel 63% dei casi contro il 36% (probabilmente meno: lui pubblica
  soprattutto le riuscite). Romeo è un membro dell'équipe: la sua voce
  alza o abbassa la stima del Capo, con una fiducia che il Capo impara dai
  risultati e ricalcola ogni sabato anche dal vivo. Oggi è piccola (+0,03),
  perché il Capo lo riconosce ancora poco: crescerà se le operazioni alla
  Romeo andranno meglio e se impara a riconoscerlo (i minuti).
- **Il collegamento con MT5:** a ogni avvio il bot chiede al broker se
  accetterebbe un ordine minimo su ogni strumento (senza mandarlo) e lo
  scrive sul canale operativo.
- **Romeo entra sul minuto dentro il CRT a 4 ore.** Sui minuti di EURUSD
  gennaio–maggio 2023, il 4 ore → 1 minuto arriva vicino a tutte le sue 15
  entrate, e su quelle al minuto a 1–2 pip dal suo prezzo; ma sono 43
  candidati per ognuna delle sue, e il guadagno atteso imparato sulle
  orarie non sa stimare stop così piccoli. Si rifà sull'anno intero.
- **Le otto configurazioni contro Romeo** (`--configurazioni 1-8`). Delle
  25 entrate con lo stop letto, 11 sono sul timeframe alto: il manuale ne
  ritrova 6, ma con 26–31 operazioni per ognuna delle sue; il Capo ne
  scarta metà e resta a 4–7 per ognuna. La "chiusura dentro" col Capo
  scende a una operazione per ognuna di Romeo, ma ne ritrova solo una.
  Nessuna configurazione vede le 14 sul timeframe basso. **Il prossimo
  passo sono i minuti** (EURUSD e GBPUSD 2023, in scaricamento: circa
  un'ora per mese).
- **Il Grilletto impara la terza gamba di Romeo (25/09).** Il suo manuale
  dice tre cose: key level, ora della manipolazione, liquidità presa prima
  della manipolazione (msg 3860, 6718). Le prime due avevano un agente, la
  terza no. Ora il Grilletto risponde: "la manipolazione ha preso la
  liquidità lasciata prima?" e "l'ha ripresa fuori dal CRT?". Le scelte di
  Romeo del 2023 ce l'hanno molto più spesso (44% contro 27%; fuori dal
  CRT 33% contro 11%). Il Capo la impara da solo come uno dei segnali più
  forti. Sul riconoscere Romeo il guadagno della prima misura (0,62
  invece di 0,60) non si è ripetuto con più minuti (45 sue scelte: 0,56 con
  e senza); ritrova un'entrata di Romeo in più (7 invece di 6). Provate e
  lasciate fuori altre sette domande che non aiutavano
  (`documenti/registro/tentativi.md`).
- **I Livelli spostano il secondo obiettivo (25/09).** Dove si leggono, i
  target di Romeo del 2023 stanno oltre il lato opposto del CRT (1,2–1,8
  volte il range), non sul lato. Sui vent'anni un secondo obiettivo a mezzo
  range oltre il lato rende di più in 13 anni su 16; col Capo, anno per
  anno, le operazioni scelte passano da −0,022 a −0,011 R. Dopo il primo
  obiettivo lo stop è a pareggio, quindi lasciar correre la seconda metà
  costa poco.
- **E lo stop non è mai troppo stretto (25/09).** Romeo: *"Your stoploss is
  25% of the range, if it hits it you're wrong"*. Lo stop resta
  all'estremo della manipolazione, ma mai più vicino all'ingresso di un
  quarto del range: gli stop più stretti li mangiano il rumore e i costi.
  Con le due modifiche dei Livelli, sui vent'anni anno per anno, **le
  operazioni scelte dal Capo sono in media positive per la prima volta**
  (+0,009 R, prima −0,022) e battono la base in tutti i 16 anni. Il
  cancello non passa ancora: +0,054 sulla base, serve +0,10. Capo e
  Rischio riaddestrati: il Rischio usa 0,18 del Kelly (era 0,08). Sul
  metro Romeo, le sue entrate ritrovate fra le scelte del Capo nel 2023
  passano da 6 a 5 su 45 (i Livelli cambiano le uscite, non le entrate:
  le entrate che il bot vede restano 11).
- **Tutti gli agenti imparano da soli (25/09).** Ogni specialista ha il suo
  mansionario: le manopole che può girare, dentro limiti presi da Romeo
  (`documenti/spec/allenamento.md`). Ogni domenica va in palestra: rilegge i suoi
  vent'anni, prova da solo un passo per ogni manopola, e tiene una modifica
  solo se fa guadagnare di più con certezza (più prove, asticella più
  alta) senza passare i paletti: scadute, durata, drawdown, Romeo. La
  prima palestra: 19 prove, una tenuta. I Livelli portano il secondo
  obiettivo a 0,75 del range oltre il lato: sui vent'anni la squadra passa
  da +0,121 a +0,363 R a settimana, meglio nell'82% degli anni, entrate di
  Romeo ritrovate 5 → 5. Le altre 18 non sono bastate. Il rapporto arriva
  in équipe al primo avvio dopo l'aggiornamento.
- **Un cervello che si allena da solo (25/09, giorno).** Su indicazione
  dell'utente (*"non devono avere obblighi… devono potersi migliorare in
  autonomia in ogni dettaglio"*):
  - **niente recinti**: ogni manopola si sposta di un passo senza limiti
    fissi; anche il Rischio impara da solo quanto puntare;
  - **si allenano le prestazioni, non il guadagno**: una modifica resta se
    alza la qualità delle operazioni (rendimento diviso per quanto oscilla),
    che non cambia puntando di più o aprendo di più; uno stop enorme la
    peggiora da solo;
  - **l'asticella cresce con tutte le prove fatte da sempre**, per non
    imparare il caso;
  - **il pareggio e due uscite nuove si imparano** (idea invalidata, troppo
    lenta), anche nel bot vero con la chiusura a mercato su MT5;
  - **gli agenti inventano**: ognuno ha i mattoni del suo mestiere e ogni
    settimana inventa due domande nuove; quelle che migliorano diventano
    colonne del Capo e il bot le fa dal vivo;
  - **più veloce**: decide 5 secondi dopo la chiusura della candela (prima
    20–80), apre gli ordini prima dei messaggi, e non rifà due volte lo
    stesso calcolo (un giro da 4,8 a 2,8 s);
  - **un cervello ad alberi per il Capo** è pronto e provato: oggi non fa
    meglio della regressione, perché il limite sono le informazioni, non il
    cervello.
  La palestra di oggi: tenuto il secondo obiettivo a 0,75 del range (qualità
  +0,005 → +0,017, drawdown 216 → 170 R); nessuna delle 12 idee inventate
  né le uscite nuove sono ancora abbastanza sicure.
- **Gli agenti si chiedono da soli dove hanno sbagliato (25/09, sera).**
  Niente comando per segnalare gli errori, su richiesta dell'utente. Dopo
  ogni operazione finita, Livelli e Grilletto la rifanno sui prezzi veri
  con ogni loro scelta vicina e dicono se una l'avrebbe salvata; gli agenti
  dei segnali che avevano sbagliato guardano se quel segnale di solito
  funziona (vent'anni e dal vivo); il Capo confronta la sua stima con le
  decisioni simili. Il sabato Livelli e Grilletto dicono cosa avrebbe reso
  di più su tutte le operazioni dal vivo (`documenti/spec/allenamento.md`). Trovato
  e corretto nel frattempo: due CRT uno dentro l'altro che scattano sullo
  stesso turtle soup avevano lo stesso nome, e in équipe il messaggio
  sembrava doppio; ora il nome porta il CRT.
- **Due agenti nuovi: Allineamento e Gap (25/09, sera).** L'Allineamento
  guarda il bias di Romeo su 4 ore, giorno, settimana e mese, e su quanti
  livelli ci sono CRT più grandi nello stesso verso; il Gap i fair value gap
  ancora aperti e il gap del weekend (`documenti/spec/panorama.md`). Parlano nella
  scheda di ogni decisione. Primo allenamento: le 6 domande del mestiere di
  ognuno, sui vent'anni; nessuna migliora il Capo (tutte fra −0,008 e 0 di
  qualità), quindi il Capo non li ascolta ancora. Ogni domenica ne
  inventano due nuove, come gli altri.
- **Il Capo decide sulle prestazioni (25/09, notte).** Su richiesta
  dell'utente non entra più se "il guadagno atteso è sopra zero", ma se la
  qualità attesa (guadagno atteso diviso per quanto l'operazione può
  oscillare) supera la sua soglia, che si allena in palestra. Prima prova:
  abbassarla peggiora con certezza, alzarla a 0,05 migliora un po' ma non
  abbastanza; resta 0 (stesse operazioni di prima). Le invenzioni non
  passavano perché erano deboli, non perché l'esame è severo (anche senza
  correzione ne passerebbe una sola su 55): ora ripartono dalle quasi
  riuscite.
- **I dati dalla VPS (25/09, pomeriggio).** Le entrate di Romeo l'utente non
  le ha e non le può trovare: il metro Romeo resta sulle 62 del 2023. Gli
  altri dati nascono sulla VPS: l'utente ha creato la chiave di GitHub e ha
  avviato `scarica.bat` (vent'anni di minuti, molte ore). Poi `consegna.bat`
  li spedisce come quarti d'ora nel ramo `dati-vps`, e il bot rispedisce da
  solo le settimane dal vivo ogni sabato. La palestra della domenica li
  prende (`strumenti/importa_vps.py`) e allena anche la coppia 4 ore → 15 minuti sui
  vent'anni, che finora il Capo imparava solo dal vivo.
- **40 strumenti, dal vivo su tutti (25/09, sera).** Su richiesta
  dell'utente il bot conosce 28 coppie forex, oro, argento, petrolio (WTI e
  Brent), sei indici e due crypto (`nvm/dati/strumenti.py`), tutti con dati
  gratis da Dukascopy (`scarica_nuovi.bat` sulla VPS). Dal vivo, sul demo,
  opera su tutti quelli che il broker ha, trovandone il nome da solo. Il
  Capo è allenato sui sei di partenza: sugli altri la prova dal vivo è la
  più onesta. Con tanti strumenti possono esserci molte operazioni aperte
  insieme, anche su mercati legati fra loro: sul demo va bene per
  imparare, prima di soldi veri il Rischio deve impararlo.
- **Gli altri agenti, la stessa notte.** Sulle ore sono state provate
  altre 33 domande per Orario, Key level, Cacciatore e Bias, più la seconda
  entrata di Romeo (msg 1891) e il Grilletto sui 5 e sull'1 minuto: nessuna
  aiuta, e restano scritte nel registro e rifacibili con `strumenti/banco.py`. Il caso
  per caso dice dove sta il resto: Romeo entra sul minuto su un turtle
  soup della liquidità della giornata (il minimo della sessione, il secondo
  massimo), non solo sul lato del CRT. Provato anche questo, con i minuti di
  GBPUSD: il Grilletto sulla liquidità della sessione non ritrova le sue
  entrate sul minuto meglio di quello di oggi. Con i dati di prezzo da soli
  quelle entrate non si ricostruiscono: dipendono da livelli che Romeo
  sceglie lui.

### Cosa serve da te

- [x] **Spegnere il vecchio bot sulla VPS.** Fatto il 24/09.
- [ ] **Rigenerare il token Telegram.** Il `.env` caricato l'11/09 è ancora
      nella storia del vecchio branch, e con lui il token. Su Telegram:
      @BotFather → `/revoke` → scegli il bot. Il token nuovo va solo nel
      `.env` sul computer.
- [ ] **Facoltativo, quando vedi un'entrata di Romeo:** mandala al bot, su
      uno dei suoi due canali, così:
      `/romeo EURUSD compra 1.0765 stop 1.0760 target 1.0800`
      Il bot risponde in équipe se l'aveva vista anche lui, e il sabato
      impara da quella. Non la copia mai (`documenti/spec/romeo-dal-vivo.md`).
- Niente altro: l'utente ha chiesto di fare tutto da qui (24/09). La VPS
  resta ferma; `documenti/VPS.md` e `scarica.bat` restano pronti se un giorno servono.

Le domande sulla strategia non le fai tu: le risposte si cercano nelle
fonti, e dove le fonti non bastano si provano le letture possibili.

## Decisioni prese

| Data | Decisione |
|---|---|
| 24/09/2026 | Si riparte da zero. Il vecchio branch `claude/trading-bot-infrastructure-5rht0h` resta come archivio e non si cancella. |
| 24/09/2026 | La strategia di partenza è il CRT di RomeoTPT (@Romeotpt). |
| 24/09/2026 | La specifica si riscrive: i vecchi documenti non valgono più come riferimento. |
| 24/09/2026 | Il vecchio bot sulla VPS si ferma. |
| 24/09/2026 | Architettura ad agenti. Gli agenti imparano sia sullo storico sia dal vivo, sempre dietro il cancello del `documenti/PIANO.md` §2. |
| 24/09/2026 | Ogni agente fa carriera (neolaureato → in prova → promosso), e sopra tutti c'è il Capo, che impara anche lui. |
| 24/09/2026 | Due tempi: l'apertura delle operazioni avviene tutta in memoria; la riunione (riallenamento, consigli, promozioni) è staccata e non la rallenta mai. |
| 24/09/2026 | Gli agenti si danno consigli nella riunione senza influenzarsi: un consiglio è un'ipotesi che solo l'agente responsabile può provare, con il cancello. Tutto si vede nel canale Telegram dell'équipe. |
| 24/09/2026 | L'utente non può rispondere alle domande sulla strategia: le risposte si cercano nelle fonti, e dove non bastano si dichiarano varianti. I casi si prendono dai grafici pubblicati da Romeo. |
| 24/09/2026 | **Il metro diventa Romeo** (`documenti/PIANO.md`, "Il cambio del 24/09/2026"). Dopo le otto configurazioni che non passano, l'utente decide che il test che conta è se il bot fa le stesse entrate di Romeo: la strategia è in gran parte discrezionale, e gli agenti devono imparare le sue scelte. Il guadagno si misura sempre, ma non decide. Dal vivo solo in demo. |
| 24/09/2026 | L'utente chiede di procedere senza fermarsi. Le domande della bozza ancora senza risposta diventano **varianti dichiarate** (al massimo 3, `documenti/PIANO.md` §3), da misurare invece che scegliere. La Fase B (dati) parte in parallelo alla A, perché non dipende dalla specifica del CRT. |
| 25/09/2026 | **Romeo è la partenza, il traguardo è il trading** (`documenti/PIANO.md`, "Il chiarimento del 25/09/2026"). Un miglioramento oltre Romeo entra se migliora fuori campione e non ci allontana da lui oltre il rumore; per la Fase F servono il cancello del guadagno e il metro Romeo. Poi arriveranno altre strategie. |
| 25/09/2026 | **Tutti gli agenti imparano da soli**, non solo Capo, Romeo e Rischio: ogni settimana la palestra (`documenti/spec/allenamento.md`), dentro il mansionario e i paletti. |
| 25/09/2026 | **Romeo dal vivo.** Il bot legge il comando `/romeo` dai suoi due canali: confronta l'entrata di Romeo con le sue decisioni, lo dice in équipe e il sabato ne impara la somiglianza. Mai operazioni copiate: Romeo resta il metro e un esempio (`documenti/spec/romeo-dal-vivo.md`). |
| 25/09/2026 | **Niente comando per gli errori: gli agenti si chiedono da soli dove hanno sbagliato** (*"il bot deve essere intelligente"*). Dopo ogni operazione rifanno i conti con le loro alternative sui prezzi veri (`nvm/vivo/autoanalisi.py`). |
| 24/09/2026 | Due canali Telegram, già collegati. **Operativo:** avvio del bot, decisioni di apertura, chiusure, avvisi urgenti. **Équipe:** solo la comunicazione fra gli agenti, sempre attivo, con il rendiconto principale nel fine settimana. |

## Domande aperte

Si decidono durante la Fase A.

- **Strumenti:** quali? Il vecchio bot usava EURUSD, GBPUSD, USDCHF, USDJPY,
  AUDUSD e XAUUSD, ma dal vivo operava quasi solo sull'oro.
- **Fonte dei prezzi:** una sola per tutti i timeframe. Il vecchio progetto
  mescolava future, CFD, Dukascopy e MT5, e molti errori venivano da lì.
- **Canale équipe: un bot o uno per agente?** Un solo bot che scrive col
  nome di ogni agente è più semplice. Un bot per agente, ognuno con il suo
  nome e la sua foto, rende l'équipe più viva, ma vuol dire crearne una
  decina con @BotFather. Si decide prima della Fase F.
- **Rischio per operazione, e cifra del conto demo.** Il vecchio conto demo
  era stato portato a 1.000.000 €, con operazioni da 50 lotti d'oro: in 7
  ore −13.915 €. Il demo deve avere la cifra che useresti davvero.

## Il bot dal vivo (dal 24/09/2026)

**Gira dal 24/09/2026 sera** sulla VPS, cartella `Desktop\nvmfinancebot`,
conto demo 903400 su UltimaMarkets-Demo (1.000 €, server UTC+3).
Istruzioni in `documenti/AVVIO.md`, codice in `vivo.py` e `nvm/vivo/`. Il registro
dal vivo resta sulla VPS (`dati/vivo/`): da qui si vede solo quello che
l'utente riporta dai canali. Decisioni dell'utente: il bot apre posizioni sul **conto demo
da 1.000 €**, **decide il bot**, e gli agenti si addestrano ma non si
bloccano.

- Ogni ora, la stessa catena delle prove sullo storico (una prova lo
  controlla ora per ora); il Capo decide, il Rischio sceglie la puntata
  (Kelly sul conto intero: fiducia minima e parte imparate, `documenti/spec/rischio.md`), l'Esecutore apre due metà con
  stop e target sul broker e sposta a pareggio.
- Canale **operativo**: avvio, aperture col perché, primo target, chiusure,
  allarmi. Canale **équipe**: dopo ogni decisione ogni agente dice quanto
  spinge o frena; quando finisce, chi aveva ragione (pagelle e carriere);
  il sabato la riunione: pagelle, consigli fra agenti, riaddestramento di
  Capo (i casi recenti pesano di più) e Rischio.
- **Messaggi riscritti (24/09).** Una scheda sola per decisione (cosa dice
  ogni agente, cosa decide il Capo, chi ha pesato di più), compro/vendo,
  euro e percentuali. Il peso di ogni agente è **di quanto sposta il
  guadagno atteso**, in R: prima era lo spostamento della probabilità del
  primo target, che faceva sembrare i Livelli contrari a tutto. Oggi il
  Capo, imparato su 50.000 operazioni, ascolta soprattutto i Livelli (in
  media 0,24 R), poi Orario e Bias (0,05); il resto quasi niente, perché
  nei dati i loro segnali cambiavano poco i risultati. Non sono esclusi: se
  dal vivo contano, il sabato li ascolta di più.
- Si aggiorna da solo da questo branch: quello che si aggiunge qui arriva al
  bot entro due minuti (dal 24/09; prima una volta l'ora).
- **Telegram da professionisti (27/09).** L'utente: *"su telegram non si
  capisce niente… voglio un'equipe di professionisti"*. Dal vivo erano ~57
  decisioni al giorno, ~100 messaggi in équipe, di cui ~12 su operazioni
  vere. Ora l'équipe parla solo quando serve: **operazione aperta**
  (Grilletto dice il segnale e dove, parla l'agente che ha pesato di più a
  favore e quello di più contro, con il numero dei vent'anni solo se
  sostiene quello che dice, il Rischio dice quanto del conto è a rischio
  in tutto, il Capo chiude), **operazione chiusa** (com'è finita, e chi con
  una scelta vicina avrebbe fatto meglio), **riepilogo alle 17 di New
  York** (un messaggio: occasioni, prese, lasciate e come sarebbero andate,
  le operazioni che il Capo voleva ma non si sono aperte e perché, le
  lezioni del giorno), **palestra** in poche righe (il rapporto lungo resta
  nel registro), **riunione** del sabato. Le occasioni lasciate non fanno
  messaggi. Ogni agente può avere il suo bot (`documenti/AVVIO.md`): nel gruppo
  scrive col suo nome. Le frasi sono costruite dai dati, non da un modello
  di linguaggio.
- **Il conto intero (27/09).** La giornata di prova su 40 strumenti ha
  mostrato puntate fino al 31% del conto sul lotto minimo e oltre metà del
  conto a rischio insieme. Simulato il conto intero 2008-2023 (6 strumenti,
  13.770 operazioni del Capo, aperte insieme come sarebbero state): **il
  modo di puntare di prima avrebbe bruciato il conto** — calo peggiore 96%,
  giornata peggiore −51%, fino al 129% del conto a rischio insieme. Ora il
  Rischio impara sul conto intero (`nvm/agenti/portafoglio.py`,
  `documenti/spec/rischio.md`): fiducia minima per metterci soldi (0,06 di Kelly
  pieno), parte del Kelly (0,01), scelte perché il conto cresca di più
  nelle storie sfortunate senza superare il 20% di calo. Nei vent'anni:
  +3,0% l'anno, calo peggiore 11%, giornata peggiore −2,3%, al massimo 5% a
  rischio insieme. **Fuori campione** (ogni anno deciso solo con gli anni
  prima), 2011-2023: **+3,2% l'anno**, calo peggiore 22%. Il vantaggio c'è
  ma è sottile: le operazioni sicure del Capo guadagnano (il quinto più
  sicuro +0,07/+0,10 R), le incerte perdono (la metà meno sicura −0,028 R);
  forte nel 2008-2014, debole nel 2015-2022. Guardare le operazioni legate
  (correlazioni per valute in comune) nei dati **non** migliora il conto:
  il codice c'è, il Rischio lo userà solo se i dati cambiano idea. Con
  1.000 € le puntate giuste (0,1-0,3% del conto) stanno quasi sempre sotto
  il lotto minimo: il bot aprirà poco.

## Numeri validi

### La base (Fase D), misurata il 24/09/2026

Tutti i CRT col manuale (Cacciatore → Grilletto → Livelli), 2006–2023, sei
strumenti, orarie Dukascopy con **bid e ask veri** e commissioni. Il
2024–2026 è chiuso. Intervallo al 95% a blocchi settimanali.

| Coppia | Operazioni | R medio | IC95 |
|---|---:|---:|---|
| mensile → giornaliero | 1.884 | −0,013 | [−0,112; +0,086] |
| settimanale → 4 ore | 9.314 | −0,053 | [−0,105; +0,002] |
| giornaliero → 1 ora | 38.608 | −0,078 | [−0,100; −0,055] |
| **tutto** | **49.806** | **−0,071** | **[−0,093; −0,048]** |

Rifatta lo stesso giorno dopo due correzioni: i cinque mesi che mancavano,
e il campo di prova che ora, quando una candela apre oltre lo stop, esce
all'apertura e non allo stop. Uscita completa in
`documenti/registro/misure/2026-09-24-base-e-conferme-2.txt`.

È il numero da battere. Per passare, la Fase F deve fare almeno +0,10 R
meglio di questo, con i criteri del `documenti/PIANO.md` §2.

Com'è fatta (giornaliero → 1 ora): 63% allo stop, 17% al target (+2,7 R
in media), 19% in pareggio dopo il primo target; 41 operazioni a settimana
su sei strumenti; stop mediano su EURUSD di 25 pip. Romeo dice "1-2 a
settimana" e usa stop di 1-5 pip: filtri e stop stretto sono le prime cose
da guardare.

La coppia 4 ore → 15 minuti non si può ancora misurare: servono i quindici
minuti di vent'anni, che non ci sono.

### Gli agenti della Fase E, contro la base

Operazioni col sì contro quelle col no, su tutte e tre le coppie
(2006–2023). Differenza in R per operazione, intervallo al 95% a blocchi
settimanali, e in quanti anni la differenza ha lo stesso segno (il cancello
chiede l'80%).

| Agente | Lettura | Quante col sì | Differenza | IC95 | Anni concordi |
|---|---|---:|---:|---|---:|
| Conferma key level | massimo preso | 3% | −0,067 | [−0,180; +0,053] | 56% |
| | arriva al massimo | 2% | −0,048 | [−0,193; +0,096] | 61% |
| | rejection block | 14% | −0,060 | [−0,118; −0,002] | 67% |
| | FVG | 12% | +0,076 | [+0,009; +0,148] | 78% |
| | almeno uno | 25% | −0,001 | [−0,048; +0,047] | 44% |
| Conferma orario | Golden candle time 9–13 NY | 22% | +0,032 | [−0,014; +0,079] | 67% |
| Contesto: bias | candela del range a favore | 24% | −0,026 | [−0,060; +0,009] | 61% |
| | timeframe sopra a favore | 40% | −0,018 | [−0,060; +0,023] | 50% |

**Candidati provati finora nella Fase E: 11.** Con 11 tentativi il
cancello chiede un intervallo al 99,5% invece che al 95% (`documenti/PIANO.md` §2,
punto 5): nessuna lettura ci arriva. La più vicina è l'FVG, che però
Romeo stesso nel 2026 dice di ignorare.

Quello che i numeri dicono, in parole semplici: prendere tutti i CRT
sull'ora con lo stop all'estremo perde un po', e nessun filtro di Romeo
preso da solo lo raddrizza. Nei casi verificati Romeo entra più tardi e
più in alto, sul timeframe basso, con stop di pochi pip: la differenza
vera sembra lì, nel **come** si entra, più che nel **quando**.

### Il Capo (Fase F), prima prova, 24/09/2026

Per ogni anno dal 2008 al 2023 il Capo impara solo dalle operazioni chiuse
prima del 1° gennaio, e sceglie quelle dell'anno. Le scelte si confrontano
con tutta la base negli stessi anni (44.312 operazioni, −0,068 R). Quattro
configurazioni dichiarate prima, quindi intervallo al 98,75%.

| # | Cacciatore, stop | Scelte | R medio delle scelte | Differenza | IC98,75 | Anni concordi | Con spread ×1,5 |
|---|---|---:|---:|---:|---|---:|---:|
| 1 | manuale, all'estremo | 15.779 | −0,022 | +0,046 | [+0,015; +0,077] | 75% | +0,068 |
| 2 | manuale, stretto | 5.927 | −0,065 | +0,003 | [−0,073; +0,081] | 38% | +0,020 |
| 3 | chiusura dentro, all'estremo | 3.432 | +0,027 | +0,095 | [+0,038; +0,154] | 81% | +0,088 |
| 4 | chiusura dentro, stretto | 2.175 | −0,004 | +0,065 | [−0,037; +0,168] | 62% | +0,071 |

**Nessuna passa.** Il cancello chiede almeno +0,10. La 3 ci arriva vicino
(+0,095), ma le operazioni che sceglie guadagnano appena +0,03 R l'una, e
con lo spread ×1,5 scendono sotto zero (−0,007). Il Capo pesa quasi solo
la geometria (quanto sono lontani i target, quanto è largo lo stop);
key level, orario e bias hanno pesi vicini a zero. Uscita completa in
`documenti/registro/misure/2026-09-24-capo.txt`.

**Con l'ingresso un gradino sotto** (configurazioni 5–8, solo mensile e
settimanale, contro la base del manuale sulle stesse coppie: 9.974
operazioni, −0,045 R; K = 8, intervallo al 99,375%):

| # | Cacciatore, stop | Scelte | R medio delle scelte | Differenza | IC99,375 | Con spread ×1,5 |
|---|---|---:|---:|---:|---|---:|
| 5 | manuale, all'estremo | 5.699 | −0,047 | −0,001 | [−0,101; +0,092] | +0,008 |
| 6 | manuale, stretto | 2.103 | +0,015 | +0,061 | [−0,151; +0,287] | +0,044 |
| 7 | chiusura dentro, all'estremo | 974 | −0,086 | −0,040 | [−0,180; +0,103] | −0,038 |
| 8 | chiusura dentro, stretto | 830 | −0,200 | −0,154 | [−0,387; +0,104] | −0,287 |

La base della variante, senza Capo, va peggio di quella del manuale:
mensile → 4 ore −0,052 (manuale −0,013), settimanale → 1 ora −0,115
(manuale −0,053). Stop più corti e target più lontani, come previsto, ma lo
stop si prende nell'81% dei casi.

Una prima versione di questa prova dava la configurazione 4 a +0,47 R, con
il 100% degli anni concordi. Era un errore: con la "chiusura dentro" il
bot entrava prima che la candela 2 chiudesse, cioè sapendo già come
sarebbe finita. Trovato, corretto e provato (`documenti/registro/tentativi.md`).

## Fasi

| Fase | Stato |
|---|---|
| A. Specifica | in corso |
| B. Dati | in corso |
| C. Cacciatore | — |
| D. La base | fatta per tre coppie su quattro (24/09) |
| E. Gli altri agenti | in corso: key level, orario e bias misurati (24/09) |
| F. Capo e apprendimento | **ferma** (24/09): 8 configurazioni su 8 non passano, varianti esaurite. Manca solo il giornaliero → 15 minuti, che aspetta i minuti |
| G. Verifica finale | — |
| H. Dal vivo, in demo | — |

## Da fare dopo

Idee fuori dalla fase attuale. Si annotano qui e si fanno quando tocca.

- **Il Rischio senza tetto (28/09).** L'utente: *"il profilo di rischio deve
  essere anche quello intelligente"*. Tolto il tetto del 20%: il Rischio
  sceglie da solo la puntata che fa crescere di più il conto nelle storie
  sfortunate (mesi rimescolati; sotto l'1% del conto di partenza è rovina).
  Sceglie fiducia minima 0,06 e parte 0,07: nei vent'anni +16,6% l'anno ma
  calo peggiore 59%, giornata −16%. È la scelta che massimizza la crescita:
  i cali grandi sono il suo prezzo, e l'utente lo sa.
- _(vuoto)_
