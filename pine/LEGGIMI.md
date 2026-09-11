# L'indicatore su TradingView

## Cos'è

`crt_nvmfinancebot.pine` riconosce il CRT sul grafico, lo disegna, e alla
chiusura della candela manda un avviso al bot.

**Propone, non decide.** Non calcola la size, non guarda il calendario delle
notizie, non sa quante posizioni sono aperte sugli altri strumenti, non
conosce il tuo conto. Quelle non sono cose del grafico. Il bot rivaluta tutto
con il proprio motore prima di muovere un euro, quindi un errore qui non può
aprire un'operazione che le regole vietano: può solo far guardare il motore a
vuoto.

Le regole non sono reinterpretate dai documenti: sono trasposte da
`core/setup.py` e `core/definizioni.py`, che sono già tradotti e coperti da
test. Ogni blocco cita l'identificativo della regola, così le due
implementazioni restano confrontabili riga per riga.

---

## Come si installa, una volta per strumento

1. Apri il grafico del **future**: `GC1!` per l'oro. Mai il CFD.
2. Metti il timeframe su **H4** (oppure H1).
3. In basso apri **Pine Editor**, incolla il contenuto di
   `crt_nvmfinancebot.pine`, e premi **Add to chart**.
4. Nelle impostazioni dell'indicatore, incolla la **parola segreta**: è la
   stessa che sta in `WEBHOOK_SECRET` nel file `.env` del bot.

Da qui in poi vedi sul grafico i key level dei timeframe superiori, e quando
si forma un CRT vedi l'etichetta, lo stop e il TP1.

---

## Come si crea l'avviso

1. Tasto destro sul grafico → **Aggiungi avviso**.
2. **Condizione**: scegli l'indicatore `nvmfinancebot — CRT`, e poi
   **"Any alert() function call"**.
3. **Frequenza**: *Once Per Bar Close*.
4. Scheda **Notifiche** → spunta **Webhook URL** e incolla l'indirizzo del
   bot, con `/webhook` in fondo.
5. Salva.

Il campo **Messaggio** lascialo com'è: il testo lo costruisce l'indicatore, e
quello che scrivi lì verrebbe ignorato.

> **Serve la 2FA attiva sul tuo account TradingView**, altrimenti il campo
> Webhook URL resta bloccato e non capisci perché.

---

## Quanto dura un avviso

Lo crei **una volta** e resta: scatta a ogni chiusura di candela in cui la
condizione si verifica, all'infinito. Non si ricrea dopo ogni scatto.

**Ma scade, e dipende dal piano:**

| Piano | Durata dell'avviso |
|---|---|
| Essential, Plus | **due mesi**, poi va riattivato |
| Premium e superiori | opzione *Open-ended*: non scade mai |

Su Essential quindi ogni due mesi devi riattivare i sette avvisi. Non è
ricrearli da zero — TradingView permette di far ripartire un avviso scaduto —
ma è una cosa da ricordarsi, e se te ne dimentichi il bot smette di ricevere
segnali senza dirtelo.

Il bot continua comunque a prendersi le candele da solo, quindi non resta
cieco: perde i segnali dell'indicatore, non i prezzi.

---

## Quando va rifatto

| Cosa succede | Che fare |
|---|---|
| L'avviso scatta | niente, continua da solo |
| Passano due mesi (Essential) | riattivalo dalla lista degli avvisi |
| Cambia l'indirizzo del bot | **modifichi** l'avviso, non lo ricrei |
| Cambio il codice dell'indicatore | ricarichi lo script; l'avviso di solito regge |
| Togli l'indicatore dal grafico | l'avviso muore con lui |

Con un indirizzo fisso per il VPS, il caso più fastidioso — quello
dell'indirizzo che cambia — sparisce del tutto.

---

## Cosa non ho potuto provare

Pine si compila solo dentro TradingView: questo file è scritto dalle regole
verificate del bot, ma **la prima compilazione avviene sul tuo schermo**. Se
l'editor segnala errori, mandameli e li correggo: sono cose di sintassi, non
di regole.

La cosa che invece va guardata con calma sei tu a doverla giudicare: se
quello che disegna sul grafico è quello che tu chiami CRT. È il motivo per
cui partiamo da un solo strumento.
