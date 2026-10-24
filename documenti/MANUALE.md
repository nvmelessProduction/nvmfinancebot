# NVM — Manuale d'uso

NVM è un sistema di trading automatico per MetaTrader 5. Segue il **CRT** (Candle Range Theory) di
RomeoTPT come lo fa il proprietario nei suoi esempi (le foto in `documenti/casi/ESEMPI-PROPRIETARIO.md`): ogni candela
è un range; la candela 2 prende la liquidità di un lato e rientra; si entra all'apertura della candela 3 verso
l'altro lato del range, e poi verso il gap o il key level del grafico grande. Una squadra di agenti controlla
le regole, impara dai risultati dal vivo e decide.

> **Avvertenza.** Il trading con leva può far perdere tutto il capitale investito. I risultati
> passati, anche quelli dal vivo, non garantiscono quelli futuri. NVM oggi opera **solo su
> conti demo**: se trova un conto reale si ferma.

## 1. Cosa fa

- **Guarda 10 strumenti**: EURUSD, GBPUSD, NZDUSD, AUDUSD, USDCHF, USDCAD, XAUUSD, XAGUSD, BTCUSD ed ETHUSD.
  DXY e TOTAL sono grafici guida, non strumenti negoziati.
- **Le candele** aprono come sui future: il giorno alle 18 di New York (mezzanotte italiana), le 4 ore alle
  18, 22, 2, 6, 10 e 14 di New York; ci sono anche le 6 e 12 ore e le candele di 3, 6 e 12 mesi.
- **Trova le occasioni** sui CRT a 1 ora, 4 ore, 6 ore, giorno, settimana e mese, ed entra **all'apertura
  della candela 3**, a qualunque ora. Le regole (ognuna con la foto da cui viene in `documenti/spec/metodo_foto.md`):
  - *Cacciatore*: la candela 2 ha preso il massimo o il minimo del range ed è rientrata (il range è la
    candela 1, o la candela madre se dopo ci sono inside bar);
  - *Key level*: la finta ha preso un livello importante: il massimo o minimo del giorno, della settimana,
    del mese, dei 3 mesi o dell'anno prima (il CRT a 1 ora vale solo se prende quello del giorno e il
    massimo o minimo delle 4 ore: anticipa la candela a 4 ore dopo);
  - *Bias*: ogni giorno, settimana, mese, 3 e 12 mesi il bot guarda la candela precedente. Se ha accettato
    contro di noi (ha chiuso oltre la candela prima) e il prezzo non ha ancora preso il suo massimo o minimo,
    non si entra: prima si aspetta la presa di quel livello. Se nessuna blocca, basta un timeframe sopra
    dalla nostra parte o un gap da riempire nel nostro verso.
  Le coppie forex col dollaro entrano solo da un CRT valido del DXY con almeno un key level preso; per l'H1 servono
  anche il key level del giorno e il massimo/minimo H4. Oro e argento entrano sui propri CRT completi, con il DXY
  come parere. BTC ed ETH entrano solo da un CRT della TOTAL con key level preso. Se i grafici guida non hanno una
  fonte oraria configurata e convalidata, le relative operazioni restano bloccate. Per le coppie e le crypto, i prezzi
  dello strumento si misurano sugli intervalli reali delle candele guida: orari diversi non fanno sparire il setup.
  Un secondo CRT guida che rappresenta la stessa presa di liquidità non genera un nuovo ingresso. Se manca una regola
  non si entra; se ci sono tutte decide la squadra (sotto, *Come decide la squadra*).
  Al massimo un'operazione aperta per strumento (il proprietario, 07/10/2026): le altre occasioni su quello
  strumento si seguono sulla carta, e la squadra impara anche da quelle. Si entra solo entro 10 minuti
  dall'apertura della candela 3.
- **Stop e obiettivi come nelle foto**: stop oltre la candela 2; **TP1** è l'altro lato del range. Alla chiusura
  effettiva della candela 3 del timeframe del CRT, il bot chiude a mercato il **25%** se il lotto si divide e porta lo
  stop del resto oltre l'ingresso quanto basta per coprire le commissioni di apertura e chiusura, anche se il prezzo
  non ha raggiunto TP1. Se il lotto non si divide, niente parziale.
  Il resto va al **target finale**: key level opposto del timeframe più basso preso; se il setup viene dalla guida e manca un
  livello dell'asset, usa il livello corrispondente al periodo della guida. Il target deve stare oltre TP1; se non è
  valido si provano i fallback del metodo e, se non c'è un target almeno 1 R, tutto al TP1 se vale almeno 1 R. Un gap
  non è un target se il prezzo ci è già entrato (è mitigato) o se la terza candela che lo
  ha creato ha accettato la precedente (chiusa oltre, con più corpo che ombra): allora non si punta nemmeno oltre.
  Se un gap già toccato contro di noi è nella reazione automatica e l'estremo dell'aggressione è un key level, il
  target è quel key level (la liquidazione). Al target finale almeno 1 volta il rischio.
- **La rete neurale**: sui setup con tutte le regole delle foto entra sempre (la sua stima la scrive, ma lì non
  decide lei). `python -m strumenti.foto --dati <cartella>` rifà le foto del proprietario una per una.
- **Il gap** (agente *Gap*): le fasi aggressione, reazione automatica, liquidazione, continuazione; l'RSI
  serve solo lì, per la continuazione (minimi decrescenti sul grafico, crescenti sull'RSI).
- **Il DXY** (agente *DXY*): guida in modo esclusivo le coppie forex col dollaro; un suo setup rialzista vende
  EURUSD, GBPUSD, NZDUSD e AUDUSD e compra USDCHF e USDCAD. Oro e argento seguono i propri CRT, mentre il DXY
  resta un parere.
- **Come decide la squadra** (il proprietario, 07/10/2026: *"ognuno dà le proprie opinioni e poi il capo decide
  ma tutti vengono presi in considerazione"*; niente intelligenza artificiale esterna; `nvm/intelligenti/pareri.py`):
  - **primo giro**: ognuno guarda l'occasione col suo mestiere e vota da −2 a +2, dicendo perché. Il
    Cacciatore guarda se altri timeframe fanno il CRT nello stesso verso e le inside bar; il Key level che
    liquidità ha preso; il Bias la sua previsione del giorno e quella della domenica; il Gap i gap; il DXY il
    dollaro; l'Orario l'ora; Livelli i costi e i target; il Grilletto come la candela 2 ha fatto la finta;
  - **secondo giro**: si sentono fra colleghi. Chi ha un motivo cambia voto e lo dice per nome (per esempio
    il Cacciatore che sente il Bias contro, o il Key level che sente le inside bar del Cacciatore). Se dal
    vivo sentire un collega non aiuta, quell'ascolto si spegne;
  - **il Bias** mantiene le sue previsioni del giorno; la previsione settimanale contraria è un voto che riduce
    la fiducia, non un veto che blocca il trade;
  - **il Capo** pesa i voti di tutti, ognuno per quanto ci ha preso dal vivo, stima quanto spesso il CRT va
    bene ed entra quando le regole del metodo sono rispettate. Riordina le occasioni per fiducia e dice in équipe
    chi prende, chi lascia e perché. Decide lui e se ne prende
    la responsabilità; dopo ogni occasione finita impara di chi fidarsi;
  - **il Rischio** riparte dall'1%, punta di più sulle occasioni più convincenti e riduce la puntata per operazioni
    correlate già aperte. Ricalcola la puntata prima di ogni ordine. Sui setup validi della squadra apre comunque
    il lotto minimo anche se questo supera la percentuale desiderata; Telegram mostra il rischio effettivo. Sul demo
    il lotto minimo può esporre il conto al 2–4% o più per un singolo trade: non c'è un tetto fisso al rischio totale;
  - i risultati veri del broker contano più di quelli calcolati sulla carta;
  - Livelli sceglie il target finale secondo le foto; se manca un target valido, il restante 75% può uscire a TP1.
- **Una posizione sola per CRT**: sul broker stanno lo stop e il target finale. Alla chiusura della candela 3 chiude
  il 25% (se il lotto si divide) e sposta lo stop a un prezzo che copre le commissioni; lo stesso CRT non si apre due volte.
- **Esce** allo stop, al target finale o a TP1 per la parte restante quando è il fallback scelto.
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
`documenti/spec/metodo_foto.md`. Il metodo dei 17 video (`documenti/spec/metodo_romeo.md`) resta nel codice ma non si usa.

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
al massimo tre per giro. Su conti piccoli il lotto minimo del broker
può essere più grande della puntata giusta: dal 23/10/2026 il bot apre lo stesso il lotto minimo e
nel messaggio scrive quanto rischia davvero.

**Quanto rischia?** Il Rischio parte dall'1% del conto per operazione, punta un po' di più quando
il Capo è più convinto del solito e meno quando ci sono altre operazioni aperte, e si corregge coi
risultati veri. Non c'è un tetto fisso al rischio totale: con molte operazioni aperte insieme il
conto può scendere molto.

**Il metodo di Romeo guadagna?** Nessuno lo sa ancora. Sui vent'anni di prezzi il CRT preso alla
lettera perdeva un po' dopo i costi; nella prova sul 2023 della versione precedente le occasioni
con tutte le regole erano poche (su 6 strumenti, circa una ogni 3 settimane), troppo poche per un
giudizio. Le regole di questa versione non sono ancora state misurate sui vent'anni. Per questo il bot gira solo sul demo: il conto demo è la prova.

**Un messaggio dice "il simbolo non c'è su questo conto".** Il broker chiama i simboli con un
suffisso: scrivilo in `MT5_SUFFISSO_SIMBOLI` nel file `.env`.

**Il bot si aggiorna da solo?** Sì: quando c'è una versione nuova si riavvia in pochi secondi.
Le posizioni aperte restano protette sul broker.
