# I cervelli degli agenti

> **Stato:** 27/09/2026. L'utente: *"tutti gli agenti devono essere intelligenti, capaci
> di ragionare, pensare, confrontarsi con gli altri agenti in maniera intelligente,
> modificarsi autonomamente… il mercato dei 20 anni serviva solo per l'addestramento, adesso
> devono vivere nel mondo reale"*.

## Cosa sono

Ogni agente (Cacciatore, Grilletto, Livelli, Key level, Orario, Bias) ha un cervello: una
rete neurale piccola scritta da noi in numpy (`nvm/cervello/rete.py`), senza AI esterne.

- **Vede** il mercato nel suo campo (`viste.py`): le candele e le misure del suo mestiere al
  momento dell'ingresso, nel verso dell'operazione e in unità del range (29-56 numeri).
  Le viste sono le stesse sullo storico e dal vivo.
- **Giudica**: quanto crede che l'operazione guadagni (impara se ha guadagnato, pesato per
  quanto: una perdita grande insegna più di una piccola).
- **Si confronta** (`squadra.py`): un secondo cervello per agente riceve quello che vede lui
  più i giudizi dei colleghi e decide se cambiare idea. Quando qualcuno cambia idea si
  calcola chi l'ha convinto (il suo giudizio rifatto senza quel collega).
- **Il Capo** mette insieme i giudizi dopo il confronto (regressione logistica).
- **A scuola** sui vent'anni ogni pezzo impara solo da giudizi su esempi che i pezzi prima
  di lui non avevano visto. Quello che sanno sta nei pesi: dal vivo non rileggono lo storico.
- **Dal vivo** (`dal_vivo.py`) giudicano ogni occasione; dopo ogni risultato vero (presa o
  seguita sulla carta) ogni cervello e il Capo imparano un passo. Gli esempi dal vivo restano
  in `dati/vivo/cervelli_esempi.jsonl` e si reimparano quando torna la squadra di scuola.
- **Ogni settimana** (`scuola.py`, dentro `capo.py --vivo`) tornano a scuola e fanno
  l'esame contro il Capo di oggi: stesse occasioni, stesso Rischio, conto intero fuori
  campione 2012-2023 (ogni anno deciso solo con gli anni prima). Se fanno crescere il conto
  di più senza superare il calo del profilo, **decidono loro** (con la loro fiducia al posto
  del Kelly, e parte e fiducia minima imparate per loro); altrimenti restano **in prova**.

## Com'è andata la prima volta (27/09/2026, 6 strumenti)

| | Prevedere il primo obiettivo (log-loss, più basso è meglio) | Conto intero fuori campione 2012-2023 |
|---|---|---|
| Capo di oggi | 0,6122 | +1,7% l'anno, calo 19% |
| Cervelli senza confronto | 0,6047 | +0,7% l'anno, calo 8% |
| Cervelli col confronto | 0,6055 | 0,0% l'anno, calo 9% |

I cervelli **vedono meglio** del Capo di oggi (prevedono meglio il primo obiettivo) e più
sono sicuri meglio va (sopra 55 su 100: +0,08 R a operazione, anche nel 2017-2023), ma sul
conto intero **non guadagnano di più**. Il confronto per ora non aggiunge niente. Restano in
prova: dal vivo giudicano, si confrontano e imparano, e su Telegram si vede il loro
ragionamento e la gara di ogni sera con il Capo.

Prima di questi è stata provata una memoria dei casi simili (`memoria.py`: sfogliare lo
storico a ogni occasione): peggiorava le decisioni in tutte le varianti. Scartata.

## I piani: i cervelli scelgono stop e obiettivi (`piani.py`)

Su ogni occasione ci sono nove piani: lo stop *stretto* (oltre il livello della conferma),
*all'estremo* (il manuale) o *largo* (un quarto di range più in là), e il profitto *tutto al
primo obiettivo*, *metà e metà* (il manuale) o *tutto al secondo* col pareggio. Sui vent'anni
ogni operazione è rifatta con tutti e nove sugli stessi prezzi. Il cervello dei Livelli
(`ReteValori`) guarda quello che vedono lui e i colleghi e stima quanto vale ogni piano nella
situazione; quando decidono i cervelli apre il piano che vale di più, e lo dice in équipe
("Scelgo stop largo, tutto al secondo obiettivo: in casi così vale +0,12 volte il rischio, il
piano di sempre +0,03"). Dal vivo impara il valore vero del piano seguito.

Nessun limite scritto: lo stop lontanissimo non conviene perché si misura quanto si guadagna
rispetto a quanto si rischia (una vincita piccola su un rischio grande vale poco), e le
operazioni hanno comunque un tempo massimo.

Prima prova anno per anno (2010-2023): il piano scelto rende più di quello di sempre nel
2010-2016 (+0,03/+0,05 R contro −0,03), non nel 2017-2023 (−0,04/−0,07 contro −0,06). Sui
vent'anni, in media, lo stop stretto perde molto (−0,34 R: i costi su uno stop piccolo) e il
largo col secondo obiettivo è il migliore (−0,016).

## Si modificano da soli (`genoma.py`)

Il genoma di ogni agente è la forma del suo cervello: quanti neuroni (8, 16, 24, 32), quanto
frena i pesi (regole più semplici o più fini), quali parti della sua vista guarda (per esempio
il Grilletto: tentativo, manipolazione, liquidità, distanza dell'obiettivo, candele piccole).
Ogni settimana, dentro `capo.py --vivo`, ogni agente prova su se stesso una modifica mai provata
prima; la squadra modificata rifà l'esame anno per anno (2010-2023) e la modifica resta solo se
la squadra rende di più nel complesso, in almeno 6 anni su 10 e di almeno la sua incertezza.
Se più modifiche passano, restano insieme solo se insieme passano ancora. Le prove restano in
`nvm/vivo/genomi.json` (mai la stessa due volte); il racconto va in équipe. Cambiano i
cervelli, non il programma che li fa girare.

Prima settimana (S39): sei modifiche provate, nessuna tenuta (la migliore, il Grilletto che
smette di guardare il tentativo, +0,009 R ma meglio solo in 8 anni su 14).

## Gli occhi nuovi da Romeo (29/09/2026)

Dalle trascrizioni dei suoi video (`spec/FONTI-ROMEO.md`, "Dai video") sette cose nuove nelle
viste: candele interne e ora del range (Cacciatore); entrata nella candela 2 o 3 e distanza
dall'apertura, spessore della candela del turtle soup, FVG, SMT col gemello (Grilletto);
posizione nella settimana e CRT dei grafici grandi armati a favore o contro (Bias). Sono
blocchi del genoma: partono **chiusi**, perché nei cervelli interi tutti insieme peggiorano la
squadra e uno alla volta nessuno supera l'esame. Ogni settimana l'evoluzione può riaprirne
uno ("torna a guardare «SMT»") e lo tiene solo se passa. La tabella del bot si rifà da sola
quando cambiano le viste.

## Imparano da ogni esperienza (`esperienza.py`, 29/09/2026)

Una persona non migliora un giorno alla settimana: sbaglia, capisce, la volta dopo fa meglio.
Dal vivo, appena un'occasione finisce (presa o no), la squadra impara subito:

- **la lezione pesa di più quando erano sicuri e hanno sbagliato** (la sorpresa) e quando
  l'operazione ha mosso tanto;
- **ripassano mentre imparano**: ogni passo mescola la lezione con 2000 ricordi di scuola
  (`nvm/vivo/ricordi.npz`) e con le esperienze vissute prima. Più esperienze vive hanno, più
  contano (fino al 70% del ripasso): un errore che si ripete si somma e li cambia davvero;
- **si controllano**: se dopo la lezione sbagliano di più su quello che sapevano (oltre l'1%),
  tornano indietro e riprovano più piano; se ancora peggio, la lezione non resta;
- **ricordano**: dopo ogni esperienza la squadra si salva (`dati/vivo/cervelli_vivi.json`) e
  riparte da lì. Con una scuola nuova rivive una per una tutte le esperienze vere di prima.

Perché non di più: nei mercati un risultato solo è in gran parte caso. Prova su un gruppo
finto: spostare molto un caso "sicuro e sbagliato" rovinava fino al +30% di quello che
sapevano. Il Capo, che mette insieme giudizi grandi, dal vivo si sposta piano (con i passi di
prima una lezione sola peggiorava del 23% i ricordi). Prova su un mondo che dopo la scuola
rovescia una regola: chi impara passa da 1,10 a 0,52 di errore in 600 esperienze, chi resta
fermo resta a 1,10; 592 lezioni su 600 restano.

## Si modificano anche dal vivo, di continuo (le sfidanti, 29/09/2026)

Una volta a settimana non basta. Ogni volta che si riallenano, in palestra per ogni agente si
prepara una versione diversa di se' mai provata (`scuola.scegli_sfidanti`: un occhio in meno o
in piu', piu' o meno neuroni, piu' o meno freno), allenata su tutti i vent'anni. Dal vivo le
sfidanti giudicano ogni occasione e imparano da ogni esperienza come la squadra; per ognuna si
segna, esperienza dopo esperienza, chi aveva giudicato meglio. Appena una sfidante sbaglia
chiaramente meno (almeno 100 esperienze vere e una differenza oltre 3 errori standard: severa
perche' si guarda dopo ogni esperienza) prende subito il posto di quella di prima, e l'agente
lo racconta in equipe. La palestra lo legge dal registro (`capo.cambi_dal_vivo`) e riparte da
li'. Prova su un gruppo finto: una versione di adesso che non ha capito niente contro una
sfidante buona: dopo 136 esperienze vere la sfidante prende il posto.

## Cosa manca

- Più dati: con 40 strumenti gli esempi diventano circa sei volte tanti, e le reti ne hanno
  bisogno più di una formula semplice.
