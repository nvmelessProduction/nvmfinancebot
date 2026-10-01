# NVM — Manuale d'uso

NVM è un sistema di trading automatico per MetaTrader 5. Segue il **CRT** (Candle Range Theory) di
RomeoTPT, come lo spiega nei suoi 17 video: ogni candela è un range; la candela dopo lo supera o gli fa una
finta (turtle soup) e rientra; nella candela 3 si entra verso il 50% e il lato opposto. Una squadra di agenti
controlla le regole di Romeo, impara dai risultati dal vivo e decide.

> **Avvertenza.** Il trading con leva può far perdere tutto il capitale investito. I risultati
> passati, anche quelli dal vivo, non garantiscono quelli futuri. NVM oggi opera **solo su
> conti demo**: se trova un conto reale si ferma.

## 1. Cosa fa

- **Guarda fino a 40 strumenti**: 28 coppie forex, oro, argento, petrolio, i principali indici,
  Bitcoin ed Ethereum (quelli che il tuo broker offre).
- **Trova le occasioni** sui grafici mensile, settimanale, giornaliero e 4 ore, con l'ingresso
  sul grafico più piccolo.
- **Le regole di Romeo, tutte obbligatorie** (ognuna col video e il minuto in `spec/metodo_romeo.md`):
  - *Cacciatore*: la candela 2 ha fatto la finta ed è chiusa dentro, si opera la candela 3;
  - *Grilletto*: la finta oltre l'apertura della candela 3 (a mezzanotte di New York per giorno, settimana e
    mese) e una delle tre entrate di Romeo: il **Model#1** (la candela spessa che si infila in un vecchio
    massimo, chiusura oltre il suo corpo), la **vera rottura di struttura** col ritorno nella zona, o il
    **kiss of death** dopo il 50%;
  - *Key level*: la finta arriva su un livello importante del grafico grande;
  - *Bias*: il grafico grande non va contro;
  - *Orario*: la finta arriva nelle ore di Romeo (Londra o la mattina di New York; la settimana fra lunedì
    e mercoledì; il mese nelle prime due settimane);
  - *Livelli*: l'obiettivo è ancora da prendere. Stop alla punta della finta, e al 50% si prende sempre
    qualcosa.
  Se manca anche una regola non si entra; se ci sono tutte si entra, senza limiti al numero di operazioni.
- **Come impara, esattamente** (niente intelligenza artificiale esterna):
  - ogni agente stima quanto spesso un'occasione come quella va bene, guardando i numeri del suo mestiere,
    e corregge la stima dopo ogni occasione finita (presa o lasciata). All'inizio non sa niente e lo dice;
  - gli agenti si ascoltano con le regole di Romeo che legano i mestieri (per esempio l'SMT confermato
    rafforza il Bias). Quanto pesa ogni collega lo imparano dai risultati, e su Telegram si dice chi cambia
    idea e perché;
  - il Capo mette insieme i giudizi e guarda i casi simili già finiti dal vivo. Lascia un'occasione con
    tutte le regole solo quando i casi simili sono abbastanza e perdono con certezza (*"lose, journal,
    avoid"*);
  - i risultati veri del broker contano più di quelli calcolati sulla carta;
  - Livelli sceglie fra tre modi di uscire, tutti di Romeo; il Rischio parte dall'1% del conto e si
    corregge coi risultati.
- **Esce prima dell'obiettivo** solo nei due casi in cui Romeo dice che l'obiettivo non arriva: l'SMT
  confermato contro di noi, o il prezzo che chiude oltre il kiss of death dopo il primo obiettivo.
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
   «Servizi» → «Aggiorna». Da lì il bot disegna su ogni grafico aperto le sue operazioni come le
   disegna Romeo: la candela 1 col suo 50%, la finta sul key level, l'apertura della candela 3,
   la candela del Model#1, l'entrata, lo stop e i due obiettivi; la domenica il massimo e il minimo
   della settimana passata. Se il servizio non parte: trascina «NvmDisegniGrafico» (Indicatori →
   NVM) su un grafico qualsiasi.
   Le app di MT5 per il telefono non mostrano i disegni dei programmi: sul telefono il bot manda la
   foto del grafico disegnato su Telegram a ogni operazione nuova, e quando vuoi la chiedi tu
   scrivendo «/grafico EURUSD» (o «/grafico XAUUSD H4») su uno dei due canali.

Lascia aperta la finestra nera:
- se si chiude per un problema (MT5 chiuso, internet assente), il bot riparte da solo dopo un
  minuto;
- si ferma davvero solo se trova un conto reale.

## 4. Leggere Telegram

- **Operativo**: ogni operazione aperta (ingresso, stop, obiettivi, lotti, rischio in euro e in
  percentuale del conto) e ogni chiusura, con il risultato in euro e in "R" (1 R = quanto si
  rischiava).
- **Équipe**:
  - su ogni operazione aperta: ogni agente dice la sua regola di Romeo (candela 3, la finta
    oltre l'apertura, la candela spessa, il key level, la direzione del grafico grande, l'ora,
    il 50% ancora da prendere), poi il Capo e il Rischio con i soldi in gioco;
  - su ogni operazione chiusa: cosa impara la squadra;
  - ogni sera alle 17 di New York: il riepilogo della giornata;
  - il sabato (come Romeo nel video CRTology SS): giorno e ora del massimo e del minimo della
    settimana, la forma della candela, il key level, gli errori di esecuzione, e cosa la squadra
    ha imparato;
  - la domenica: la previsione della settimana e i livelli da guardare.

Le regole vengono dai 17 video di Romeo, ognuna col video e il minuto: `spec/metodo_romeo.md`.

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
