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

- **Guarda fino a 40 strumenti**: 28 coppie forex, oro, argento, petrolio, i principali indici,
  Bitcoin ed Ethereum (quelli che il tuo broker offre).
- **Le candele** aprono come sui future: il giorno alle 18 di New York (mezzanotte italiana), le 4 ore alle
  18, 22, 2, 6, 10 e 14 di New York; ci sono anche le 6 e 12 ore e le candele di 3, 6 e 12 mesi.
- **Trova le occasioni** sui CRT a 1 ora, 4 ore, 6 ore, giorno, settimana e mese, ed entra **all'apertura
  della candela 3**, a qualunque ora. Le regole (ognuna con la foto da cui viene in `spec/metodo_foto.md`):
  - *Cacciatore*: la candela 2 ha preso il massimo o il minimo del range ed è rientrata (il range è la
    candela 1, o la candela madre se dopo ci sono inside bar);
  - *Key level*: la finta ha preso un livello importante: il massimo o minimo del giorno, della settimana,
    del mese, dei 3 mesi o dell'anno prima (il CRT a 1 ora vale solo se prende quello del giorno e il
    massimo o minimo delle 4 ore: anticipa la candela a 4 ore dopo);
  - *Bias*: il timeframe di comando (settimana, mese, 3, 6, 12 mesi) è dalla nostra parte, o c'è un gap
    da riempire nel nostro verso.
  Se manca anche una regola non si entra; se ci sono tutte si entra. Se lo strumento ha già un'operazione
  aperta decide il Rischio quanto puntare (impara lui quanto ridurre).
- **Stop e obiettivi come nelle foto**: stop oltre la candela 2; **TP1** all'altro lato del range, dove si
  chiude metà e lo stop va al prezzo d'entrata; il resto al **target finale**: il gap del grafico grande se
  c'è, altrimenti il key level (l'altro lato del periodo di cui la finta ha preso la liquidità). Se davanti
  c'è un gap già toccato che ha appena reagito contro di noi, il target è il minimo (massimo) della sua
  aggressione: la liquidazione.
- **Il gap** (agente *Gap*): le fasi aggressione, reazione automatica, liquidazione, continuazione; l'RSI
  serve solo lì, per la continuazione (minimi decrescenti sul grafico, crescenti sull'RSI).
- **Il DXY** (agente *DXY*): l'indice del dollaro, calcolato dalle coppie; un suo setup rialzista vende le
  coppie col dollaro al denominatore (e l'oro) e compra quelle col dollaro al numeratore.
- **Come impara, esattamente** (niente intelligenza artificiale esterna):
  - ogni agente stima quanto spesso un'occasione come quella va bene, guardando i numeri del suo mestiere,
    e corregge la stima dopo ogni occasione finita (presa o lasciata). All'inizio non sa niente e lo dice;
  - gli agenti si ascoltano con le regole che legano i mestieri (per esempio il DXY a favore o il gap a
    favore rafforzano il Bias). Quanto pesa ogni collega lo imparano dai risultati, e su Telegram si dice chi
    cambia idea e perché;
  - il Capo mette insieme i giudizi e guarda i casi simili già finiti dal vivo. Lascia un'occasione con
    tutte le regole solo quando i casi simili sono abbastanza e perdono con certezza (*"lose, journal,
    avoid"*);
  - i risultati veri del broker contano più di quelli calcolati sulla carta;
  - Livelli sceglie fra tre modi di uscire (tutto al TP1; metà al TP1 e il resto al target finale, come nelle
    foto; metà al TP1 e il resto più in là); il Rischio parte dall'1% del conto e si corregge coi risultati.
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
   Le app di MT5 per il telefono non mostrano i disegni dei programmi: sul telefono il bot manda la
   foto del grafico disegnato su Telegram a ogni operazione nuova, e quando vuoi la chiedi tu
   scrivendo «/grafico EURUSD» (o «/grafico XAUUSD H4») su uno dei due canali.
   Con «/strumenti» il bot manda la lista di tutti gli strumenti del broker, con segnati quelli che guarda.

Lascia aperta la finestra nera:
- se si chiude per un problema (MT5 chiuso, internet assente), il bot riparte da solo dopo un
  minuto;
- si ferma davvero solo se trova un conto reale.

## 4. Leggere Telegram

- **Operativo**: ogni operazione aperta (ingresso, stop, obiettivi, lotti, rischio in euro e in
  percentuale del conto) e ogni chiusura, con il risultato in euro e in "R" (1 R = quanto si
  rischiava).
- **Équipe**:
  - su ogni operazione aperta: ogni agente dice la sua regola (il CRT, il key level preso, la
    direzione del timeframe di comando) e i punti in più (timeframe allineati, gap, DXY), poi il
    Capo e il Rischio con i soldi in gioco;
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

**Il bot apre poche operazioni.** È voluto. Rischia solo quando la squadra ci crede
abbastanza, e mai più di quanto il conto regge. Su conti piccoli il lotto minimo del broker
può essere troppo grande per la puntata giusta: in quel caso l'operazione si lascia.

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
