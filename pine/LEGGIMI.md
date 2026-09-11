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

## Quali regole applica, e quali no

Applica tutto quello che si puo' calcolare da un grafico:

| Regola | Cosa fa |
|---|---|
| `DEF-16` | bias di ogni timeframe, con i sette passi, il rifiuto **semplice**, l'inside bar e l'eredita' ricorsiva |
| `DEF-36` | key level sugli estremi di **C1**, non di C0 |
| `DEF-37` | assorbimento fra livelli coincidenti |
| `DEF-38` | presa del key level da parte della C0 del suo timeframe |
| `SETUP-00` | nessun CRT senza un key level **gia' preso** |
| `SETUP-02A/B` | le quattro condizioni del CRT |
| `SETUP-05` | i due timeframe superiori devono aver sbilanciato nella stessa direzione |
| `SETUP-06` | bias di comando, dal timeframe piu' alto in giu' |
| `DEF-17` | nessun CRT contro la bias di comando |
| `PREC-02` | fra piu' key level comanda quello del timeframe piu' alto |
| `GEST-01` | stop e target da parti opposte, e rapporto minimo |
| `GEST-02` | stop sull'estremo di N2 |
| `GEST-07` | TP1 al 50% del range di N1 |
| `DEF-31`, `REV-11` | su H12 e H6 non si lavora |

Non applica, perche' non sono cose del grafico:

- il **calendario delle notizie** (`CTX-02`, `SETUP-15`)
- la **size** e i limiti di rischio (`RISK-01/02/03`, `RISK-06/07`)
- le **posizioni aperte sugli altri strumenti** e i gruppi di correlazione
- i **limiti di perdita** giornaliero, settimanale, mensile
- il passo (b) di `SETUP-06`, cioe' se il target del timeframe di comando e'
  gia' stato raggiunto: richiede i livelli strutturali, che sono storia
  profonda

Le verifica il bot, e il riquadro di riepilogo lo scrive nell'ultima riga.

---

## Leggere il riquadro

| Riga | Cosa dice |
|---|---|
| bias comando | chi comanda, e da quale timeframe (`SETUP-06`) |
| bias 1W / 1D | la bias dei due timeframe superiori (`DEF-16`) |
| sbilanciamento | in che direzione hanno preso un key level (`SETUP-05`) |
| 1W max/min | i livelli, e quali sono gia' stati **presi** |
| CRT | se c'e', in che direzione e da quante barre |
| ingresso / R | prezzo e rapporto rischio-rendimento |
| **scartato** | **perche' un CRT che c'era non e' diventato un segnale** |

L'ultima riga e' quella che serve davvero: quando a occhio vedi un CRT e
l'indicatore non segna niente, li' c'e' scritto quale regola l'ha escluso.

Sul grafico, un key level **gia' preso** e' una linea piena; uno non ancora
preso e' tratteggiato e sbiadito. Solo i primi possono abilitare un CRT.

---

## Cosa non ho potuto provare

Pine si compila solo dentro TradingView: questo file è scritto dalle regole
verificate del bot, ma **la prima compilazione avviene sul tuo schermo**. Se
l'editor segnala errori, mandameli e li correggo: sono cose di sintassi, non
di regole.

La cosa che invece va guardata con calma sei tu a doverla giudicare: se
quello che disegna sul grafico è quello che tu chiami CRT. È il motivo per
cui partiamo da un solo strumento.
