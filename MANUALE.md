# NVM — Manuale d'uso

NVM è un sistema di trading automatico per MetaTrader 5. Segue il **CRT** (Candle Range Theory) di
RomeoTPT come lo fa il proprietario nei suoi esempi (le foto in `casi/ESEMPI-PROPRIETARIO.md`): ogni candela
è un range; la candela 2 prende la liquidità di un lato e rientra; si entra all'apertura della candela 3 verso
l'altro lato del range, e poi verso il gap o il key level del grafico grande. Una squadra di agenti controlla
le regole, impara dai risultati dal vivo e decide.

> **Avvertenza.** Il trading con leva può far perdere tutto il capitale investito. I risultati
> passati, anche quelli dal vivo, non garantiscono quelli futuri. NVM oggi opera **solo su
> conti demo**: se trova un conto reale si ferma.

## 1. Cosa fa

- **Guarda 37 strumenti**: 28 coppie forex, oro, argento, petrolio WTI, S&P 500, Nasdaq, Dow Jones, DAX,
  Bitcoin ed Ethereum (quelli che il tuo broker offre; Brent, FTSE e Nikkei tolti il 07/10/2026).
- **Le candele** aprono come sui future: il giorno alle 18 di New York (mezzanotte italiana), le 4 ore alle
  18, 22, 2, 6, 10 e 14 di New York; ci sono anche le 6 e 12 ore e le candele di 3, 6 e 12 mesi.
- **Trova le occasioni** sui CRT a 1 ora, 4 ore, 6 ore, giorno, settimana e mese, ed entra **all'apertura
  della candela 3**, a qualunque ora. Le regole (ognuna con la foto da cui viene in `spec/metodo_foto.md`):
  - *Cacciatore*: la candela 2 ha preso il massimo o il minimo del range ed è rientrata (il range è la
    candela 1, o la candela madre se dopo ci sono inside bar);
  - *Key level*: la finta ha preso un livello importante: il massimo o minimo del giorno, della settimana,
    del mese, dei 3 mesi o dell'anno prima (il CRT a 1 ora vale solo se prende quello del giorno e il
    massimo o minimo delle 4 ore: anticipa la candela a 4 ore dopo);
  - *Bias*: ogni giorno, settimana, mese, 3 e 12 mesi il bot guarda la candela precedente. Se ha accettato
    contro di noi (ha chiuso oltre la candela prima) e il prezzo non ha ancora preso il suo massimo o minimo,
    non si entra: prima si aspetta la presa di quel livello. Se nessuna blocca, basta un timeframe sopra
    dalla nostra parte o un gap da riempire nel nostro verso.
  Se manca anche una regola non si entra; se ci sono tutte decide la squadra (sotto, *Come decide la squadra*).
  Al massimo un'operazione aperta per strumento (il proprietario, 07/10/2026): le altre occasioni su quello
  strumento si seguono sulla carta, e la squadra impara anche da quelle. Si entra solo entro 10 minuti
  dall'apertura della candela 3.
- **Stop e obiettivi come nelle foto**: stop oltre la candela 2; **TP1** all'altro lato del range, dove si
  chiude il **25%** e lo stop va al prezzo d'entrata; il resto al **target finale**: il gap del grafico grande
  se c'è ed è valido, altrimenti il key level (l'altro lato del periodo di cui la finta ha preso la
  liquidità). Un gap non è un target se il prezzo ci è già entrato (è mitigato) o se la terza candela che lo
  ha creato ha accettato la precedente.
- **Il gap** (agente *Gap*): le fasi aggressione, reazione automatica, liquidazione, continuazione; l'RSI
  serve solo lì, per la continuazione (minimi decrescenti sul grafico, crescenti sull'RSI).
- **Il DXY** (agente *DXY*): l'indice del dollaro, calcolato dalle coppie; un suo setup rialzista vende le
  coppie col dollaro al denominatore (e l'oro) e compra quelle col dollaro al numeratore.
- **Come decide la squadra** (il proprietario, 07/10/2026: *"ognuno dà le proprie opinioni e poi il capo decide
  ma tutti vengono presi in considerazione"*; niente intelligenza artificiale esterna; `nvm/intelligenti/pareri.py`):
  - **primo giro**: ognuno guarda l'occasione col suo mestiere e vota da −2 a +2, dicendo perché. Il
    Cacciatore guarda quanto è grande il CRT e se è allineato coi grafici grandi; il Key level che liquidità
    ha preso; il Bias la sua previsione del giorno e quella della domenica; il Gap i gap; il DXY il dollaro;
    l'Orario l'ora (l'apertura di Wall Street, il rollover); Livelli lo stop e i target; il Grilletto come la
    candela 2 ha fatto la finta; il Rischio quanto siamo già esposti sulla stessa valuta;
  - **secondo giro**: si sentono fra colleghi. Chi ha un motivo cambia voto e lo dice per nome (per esempio
    il Cacciatore che sente il Bias contro, o il Key level che sente le inside bar del Cacciatore). Se dal
    vivo sentire un collega non aiuta, quell'ascolto si spegne;
  - **il Bias è fedele alle sue previsioni**: quella del giorno la fa all'apertura (le 18 di New York) e la
    tiene fino a sera, cambia solo quando il livello è preso; la **previsione della domenica** non si tradisce
    mai: contro quella il Capo non entra;
  - **il Capo** pesa i voti di tutti, ognuno per quanto ci ha preso dal vivo, stima quanto spesso il CRT va
    bene ed entra solo con abbastanza punti a favore. In ogni giro mette in ordine i CRT per probabilità e
    sceglie i migliori (al massimo 3, una sola idea per valuta); in équipe dice chi prende, chi lascia e
    perché. Decide lui e se ne prende la responsabilità; dopo ogni occasione finita impara di chi fidarsi;
  - **il Rischio** parte dall'1% del conto, punta di più quando il Capo è più convinto del solito, toglie per
    le aperte sulla stessa valuta, non supera il 5% del conto a rischio insieme, si ferma dopo il 3% perso in
    un giorno, e arrotonda il lotto quanto basta (fino a 1,5 volte la puntata) per poter chiudere il 25% al TP1;
  - i risultati veri del broker contano più di quelli calcolati sulla carta;
  - Livelli sceglie fra tre modi di uscire (tutto al TP1; il 25% al TP1 e il resto al target finale, come
    nelle foto; il 25% al TP1 e il resto più in là).
- **Una posizione sola per CRT** (il proprietario, 07/10/2026): sul broker stanno lo stop e il target finale;
  quando il prezzo arriva al TP1 il bot chiude il 25% e mette lo stop al prezzo d'entrata. Se il lotto è
  troppo piccolo per chiuderne il 25%, al TP1 sposta solo lo stop e tiene tutto fino al target finale. Lo stesso CRT non si apre mai due volte (il commento della posizione dice quale CRT è).
- **Esce** allo stop, al pareggio dopo il TP1, o al target finale.
- **Protegge il conto**:
  - stop e obiettivi stanno sempre sul broker, anche se il computer si spegne;
  - la dimensione delle operazioni tiene conto di tutte quelle aperte insieme.

## 2. Cosa serve

- Un computer Windows sempre acceso, meglio una **VPS**.
- **MetaTrader 5** collegato a un conto **demo**, con il pulsante *Algo Trading* acceso.
- **Python 3.11** (lo prepara il programma d'avvio la prima volta).
- **Telegram**: un bot (da @BotFather) e due canali o gruppi:
  - *operativo*: aperture, chiusure, allarmi;
  - *équipe*: il ragionamento della squadra.

## 3. Installazione

1. Copia la cartella di NVM sul computer.
2. Copia `.env.example` come `.env` e completa i valori: token del bot Telegram e id dei due
   canali. Il file `.env` contiene segreti: non condividerlo mai.
3. Apri MetaTrader 5 sul conto demo e accendi *Algo Trading*.
4. Doppio clic su **`avvia.bat`**. La prima volta prepara Python (qualche minuto), poi sul
   canale operativo arriva "🟢 Bot acceso".

5. **I disegni sul grafico** (una volta sola): in MT5 apri il Navigatore (Ctrl+N), poi «Servizi»,
   cartella «NVM»: tasto destro su «NvmDisegni» → «Avvia». Se non lo vedi: tasto destro su
   «Servizi» → «Aggiorna». Da lì il bot disegna su ogni grafico aperto le sue operazioni come
   nelle foto: il range, la finta della candela 2, il key level preso, l'entrata all'apertura della
   candela 3, lo stop, il TP1 e il target finale; la domenica il massimo e il minimo della settimana
   passata. Se il servizio non parte: trascina «NvmDisegniGrafico» (Indicatori →
   NVM) su un grafico qualsiasi.
   Le app di MT5 per il telefono non mostrano i disegni dei programmi: per il telefono il bot disegna
   da sé la foto di ogni operazione nuova e la manda su Telegram (sfondo bianco, candele verdi e rosse,
   solo l'operazione: il range, la finta, l'entrata, lo stop, il TP1 e il target finale, con i prezzi
   scritti grandi). Quando vuoi la chiedi tu scrivendo «/grafico EURUSD» (o «/grafico XAUUSD H4») su
   uno dei due canali: arrivano le candele con le operazioni aperte su quello strumento.
   Con «/strumenti» il bot manda la lista di tutti gli strumenti del broker, con segnati quelli che guarda.

Lascia aperta la finestra nera:
- se si chiude per un problema (MT5 chiuso, internet assente), il bot riparte da solo dopo un
  minuto;
- si ferma davvero solo se trova un conto reale.

## 4. Leggere Telegram

- **Operativo**: ogni operazione aperta (ingresso, stop, obiettivi, lotti, rischio in euro e in
  percentuale del conto) e ogni chiusura, con il risultato in euro e in "R" (1 R = quanto si
  rischiava).
- **Operativo**, in più: il messaggio di ogni apertura arriva come didascalia della sua foto, così con più
  operazioni insieme foto e messaggi non si mescolano.
- **Équipe** (ogni messaggio comincia con 📌 e l'asset di cui si parla):
  - a ogni giro con CRT validi: il Capo dice quali sceglie, quali lascia e perché;
  - su ogni operazione aperta: ogni agente dice il suo voto e perché (e chi ha cambiato idea sentendo un
    collega), poi il Capo che decide e il Rischio con i soldi in gioco;
  - ogni giorno all'apertura: le previsioni del Bias su tutti gli strumenti;
  - su ogni operazione chiusa: cosa impara la squadra;
  - ogni sera alle 17 di New York: il riepilogo della giornata;
  - il sabato (come Romeo nel video CRTology SS): giorno e ora del massimo e del minimo della
    settimana, la forma della candela, il key level, gli errori di esecuzione, e cosa la squadra
    ha imparato;
  - la domenica: la previsione della settimana e i livelli da guardare.

Le regole vengono dalle foto del proprietario (6 ottobre 2026), ognuna con la foto da cui viene:
`spec/metodo_foto.md`. Il metodo dei 17 video (`spec/metodo_romeo.md`) resta nel codice ma non si usa.

## 5. Il rendiconto

Ogni operazione vera è scritta nel **libro** (`dati/vivo/libro.jsonl`). Ogni riga porta
l'impronta di quella prima: se qualcuno cambia, toglie o aggiunge una riga, la verifica se ne
accorge.

Per vedere i risultati, apri un prompt nella cartella del bot e scrivi:

```
.venv\Scripts\python.exe rendiconto.py
```

Per una verifica indipendente, collega il conto a un servizio esterno come Myfxbook, che il
bot non può toccare.

## 6. Domande frequenti

**Il bot apre poche operazioni.** È voluto. Il Capo sceglie solo i CRT su cui la squadra è convinta,
al massimo tre per giro, e mai più di quanto il conto regge. Su conti piccoli il lotto minimo del broker
può essere troppo grande per la puntata giusta: in quel caso l'operazione si lascia.

**Quanto rischia?** Il Rischio parte dall'1% del conto per operazione, punta un po' di più quando
il Capo è più convinto del solito, toglie per le aperte sulla stessa valuta, e si corregge coi
risultati veri. Insieme non rischia mai più del 5% del conto, e dopo il 3% perso in un giorno si ferma.

**Il metodo di Romeo guadagna?** Nessuno lo sa ancora. Sui vent'anni di prezzi il CRT preso alla
lettera perdeva un po' dopo i costi; nella prova sul 2023 della versione precedente le occasioni
con tutte le regole erano poche (su 6 strumenti, circa una ogni 3 settimane), troppo poche per un
giudizio. Le regole di questa versione non sono ancora state misurate sui vent'anni. Per questo il bot gira solo sul demo: il conto demo è la prova.

**Un messaggio dice "il simbolo non c'è su questo conto".** Il broker chiama i simboli con un
suffisso: scrivilo in `MT5_SUFFISSO_SIMBOLI` nel file `.env`.

**Il bot si aggiorna da solo?** Sì: quando c'è una versione nuova si riavvia in pochi secondi.
Le posizioni aperte restano protette sul broker.
