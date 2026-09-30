# Avviare il bot sulla VPS

Il bot apre posizioni **solo sul conto demo**: se trova un conto reale si
ferma e lo scrive su Telegram. Si aggiorna da solo quando qui c'è una
versione nuova.

## Una volta sola

1. **Telegram: il token nuovo.** Su Telegram apri @BotFather, scrivi
   `/revoke`, scegli il bot, e copia il token nuovo che ti dà.
2. **Scarica il progetto sulla VPS.** Apri **PowerShell** e incolla questa
   riga (poi Invio):

   ```
   cd $HOME; git clone -b claude/zealous-albattani-394cd9 https://github.com/nvmelessProduction/nvmfinancebot nvm-nuovo
   ```

   Se la cartella `nvm-nuovo` c'è già (dallo scaricamento dei dati), incolla
   invece: `cd $HOME\nvm-nuovo; git pull`
3. **Il file `.env`.** Copia il file `.env` dalla cartella del vecchio bot
   dentro `nvm-nuovo` (Esplora file: copia e incolla). Aprilo con Blocco
   note, e dopo `TELEGRAM_TOKEN=` metti il token nuovo del punto 1. Salva.
4. **MT5.** Apri il terminale MT5 collegato al **conto demo da 1.000 €**, e
   accendi il pulsante **Algo Trading** in alto.

## Ogni volta

Nella cartella `nvm-nuovo`, **doppio clic su `avvia.bat`**. La prima volta
prepara Python (qualche minuto). Poi, sul canale operativo, arriva
"🟢 Bot avviato".

Lascia aperta la finestra nera: se la chiudi, il bot si ferma (le posizioni
aperte restano protette sul broker con i loro stop).

## Facoltativo: un bot Telegram per ogni agente

Senza questo passo l'équipe parla lo stesso, tutta da un bot solo (ogni riga
col nome dell'agente). Con un bot per agente, nel gruppo équipe ognuno scrive
col suo nome e la sua foto, come colleghi in una chat.

Per ogni agente che vuoi (anche solo alcuni: gli altri parlano dal bot
principale):

1. Su Telegram apri **@BotFather**, scrivi `/newbot`. Come nome metti quello
   dell'agente (per esempio `Capo`), come nome utente uno libero che finisce
   in `bot` (per esempio `nvm_capo_bot`). BotFather ti dà un **token**: non
   mandarlo a nessuno, nemmeno in chat con Claude.
2. Aggiungi il bot nuovo al gruppo **équipe**. Se l'équipe è un *canale*,
   aggiungilo come amministratore con il permesso di pubblicare.
3. Apri il file `.env` sulla VPS con Blocco note e aggiungi una riga col
   token, con il nome giusto:

   | Agente | Riga nel `.env` |
   |---|---|
   | Capo | `TELEGRAM_TOKEN_CAPO=...` |
   | Grilletto | `TELEGRAM_TOKEN_GRILLETTO=...` |
   | Rischio | `TELEGRAM_TOKEN_RISCHIO=...` |
   | Cacciatore | `TELEGRAM_TOKEN_CACCIATORE=...` |
   | Livelli | `TELEGRAM_TOKEN_LIVELLI=...` |
   | Key level | `TELEGRAM_TOKEN_KEY_LEVEL=...` |
   | Orario | `TELEGRAM_TOKEN_ORARIO=...` |
   | Bias | `TELEGRAM_TOKEN_BIAS=...` |
   | Allineamento | `TELEGRAM_TOKEN_ALLINEAMENTO=...` |
   | Gap | `TELEGRAM_TOKEN_GAP=...` |

4. Salva, chiudi la finestra nera e fai doppio clic su `avvia.bat`.

In un *canale* Telegram i messaggi compaiono col nome del canale, non del
bot: per vedere ogni agente col suo nome serve un **gruppo**. Se l'équipe
oggi è un canale e vuoi passare a un gruppo, chiedimelo e ti guido.

## Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| `Manca il file .env` | rifai il punto 3 |
| sul canale: "MT5 non si collega" | apri MT5 e collegati al conto, poi doppio clic su `avvia.bat` |
| sul canale: "accendi il pulsante Algo Trading" | accendilo in MT5: il bot riprova da solo |
| sul canale: "il simbolo ... non c'è su questo conto" | mandami una foto: il broker chiama i simboli con un suffisso |
| qualsiasi altra cosa | mandami una foto della finestra nera o del messaggio |
