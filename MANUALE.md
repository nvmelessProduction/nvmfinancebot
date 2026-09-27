# NVM — Manuale d'uso

NVM è un sistema di trading automatico per MetaTrader 5. Una squadra di agenti, ognuno con
un suo cervello allenato su vent'anni di mercato, guarda i grafici, discute, decide le
operazioni e continua a imparare da ogni risultato. Il metodo di base è il **CRT** (Candle
Range Theory): il prezzo esce da un range, prende la liquidità, rientra e inverte.

> **Avvertenza.** Il trading con leva può far perdere tutto il capitale investito. I risultati
> passati, anche quelli dal vivo, non garantiscono quelli futuri. NVM oggi opera **solo su
> conti demo**: se trova un conto reale si ferma.

## 1. Cosa fa

- **Guarda fino a 40 strumenti**: 28 coppie forex, oro, argento, petrolio, i principali indici,
  Bitcoin ed Ethereum (quelli che il tuo broker offre).
- **Trova le occasioni** sui grafici mensile, settimanale, giornaliero e 4 ore, con l'ingresso
  sul grafico più piccolo.
- **La squadra ragiona**:
  - *Cacciatore* trova i range;
  - *Grilletto* vede l'ingresso;
  - *Livelli* sceglie stop e obiettivi;
  - *Key level*, *Orario* e *Bias* guardano livelli, orari e direzione;
  - *Rischio* decide quanto rischiare sul conto intero.
  Ognuno dà il suo giudizio, sente i colleghi e può cambiare idea; poi si decide.
- **Impara sempre**:
  - dopo ogni risultato vero, ogni cervello si corregge;
  - ogni settimana tornano a scuola sui vent'anni, provano a migliorare se stessi e tengono
    solo i cambiamenti che reggono all'esame.
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

Lascia aperta la finestra nera:
- se si chiude per un problema (MT5 chiuso, internet assente), il bot riparte da solo dopo un
  minuto;
- si ferma davvero solo se trova un conto reale.

## 4. Leggere Telegram

- **Operativo**: ogni operazione aperta (ingresso, stop, obiettivi, lotti, rischio in euro e in
  percentuale del conto) e ogni chiusura, con il risultato in euro e in "R" (1 R = quanto si
  rischiava).
- **Équipe**:
  - su ogni operazione aperta: chi ha visto il segnale, chi era a favore e chi contro, quanto
    ci credono i cervelli prima e dopo il confronto, il piano scelto, il rischio sul conto
    intero;
  - ogni sera alle 17 di New York: il riepilogo della giornata;
  - il sabato: la riunione della settimana;
  - quando i cervelli si modificano: cosa hanno provato e cosa hanno tenuto.

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

**Posso cambiare quanto rischia?** Il profilo di rischio è il calo massimo che accetti di
vedere sul conto: di base il 20%. Il Rischio sceglie da solo le puntate per restarci dentro.

**Un messaggio dice "il simbolo non c'è su questo conto".** Il broker chiama i simboli con un
suffisso: scrivilo in `MT5_SUFFISSO_SIMBOLI` nel file `.env`.

**Il bot si aggiorna da solo?** Sì: quando c'è una versione nuova si riavvia in pochi secondi.
Le posizioni aperte restano protette sul broker.
