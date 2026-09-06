# Far girare il bot 24 ore su 24

Il bot gira sul tuo PC Windows, e tre cose devono restare vive
contemporaneamente:

| Cosa | Perché serve | Se muore |
|---|---|---|
| **MetaTrader 5**, aperto e loggato | il bot non fa il login da solo: si aggancia al terminale già aperto | niente ordini, niente prezzi per la sorveglianza |
| **`main.py`** (il server) | riceve gli alert, decide, sorveglia stop e target | le posizioni aperte restano **senza stop e senza target** |
| **`cloudflared`** (il tunnel) | è la porta da cui entra TradingView | gli alert non arrivano più, in silenzio |

Nessuna di queste tre si riavvia da sola: gli script in questa cartella
servono a questo.

---

## 1. Il tunnel deve avere un indirizzo fisso

È il punto che rovina la maggior parte dei tentativi di far girare tutto
h24, ed è meglio saperlo prima.

Il tunnel gratuito "quick" (`cloudflared tunnel --url http://localhost:8000`)
genera **un indirizzo nuovo a ogni avvio**. Riavviarlo automaticamente
produce quindi la peggiore delle situazioni: un bot che sembra funzionare —
il server gira, MT5 è connesso, `/salute` risponde in locale — mentre
TradingView continua a scrivere a un indirizzo che non esiste più. Nessun
errore, nessuna notifica, semplicemente non succede più niente.

Per il funzionamento continuo serve un **tunnel nominato**, che ha un
indirizzo stabile. È gratuito, ma richiede **un dominio tuo** con i DNS
gestiti da Cloudflare (un dominio economico costa una decina di euro
l'anno). Si crea una volta sola:

```bat
cloudflared tunnel login
cloudflared tunnel create nvmfinancebot
cloudflared tunnel route dns nvmfinancebot bot.iltuodominio.it
```

Poi crea il file `C:\Users\<tuonome>\.cloudflared\config.yml`:

```yaml
tunnel: nvmfinancebot
credentials-file: C:\Users\<tuonome>\.cloudflared\<id-del-tunnel>.json

ingress:
  - hostname: bot.iltuodominio.it
    service: http://localhost:8000
  - service: http_status:404
```

Da quel momento l'URL dell'alert su TradingView è
`https://bot.iltuodominio.it/webhook` e **non cambia più**.

---

## 2. Far partire tutto all'accensione

1. Premi **Windows+R**, scrivi `shell:startup`, Invio. Si apre la cartella
   dei programmi che partono da soli.
2. Metti lì dentro un **collegamento** a:
   - `avvio\avvia_bot.bat`
   - `avvio\avvia_tunnel.bat`
   - `terminal64.exe` di MetaTrader 5
3. In MetaTrader, menù *Strumenti → Opzioni → Server*, spunta **"Mantieni
   le informazioni personali"** perché faccia il login da solo. E lascia
   acceso **Algo Trading**.

I due `.bat` non partono e basta: se il programma che avviano muore, lo
**rifanno partire** dopo 15 secondi, all'infinito. Ogni riavvio finisce in
`avvio\riavvii.log`: se quel file cresce, qualcosa non va e lì c'è scritto
quando.

---

## 3. Perché il PC deve accedere da solo

Se manca la corrente, al ritorno Windows si ferma alla schermata di accesso
e **niente parte**, perché tutto quanto sopra parte al *login*, non
all'avvio.

Serve quindi l'accesso automatico: `Windows+R` → `netplwiz` → togli la
spunta a *"Per utilizzare questo computer è necessario che l'utente immetta
il nome e la password"*.

> **Il prezzo di questo:** chiunque abbia accesso fisico al PC entra senza
> password, e su quel PC c'è il tuo `.env` con la parola segreta del
> webhook. Se il computer non sta in un posto tuo, non farlo.

---

## 4. Windows Update

Un riavvio a sorpresa nel mezzo di una posizione aperta è esattamente ciò
che non vuoi. Non si può disattivare del tutto, ma si può governare:

- *Impostazioni → Windows Update → Opzioni avanzate → **Ore di attività***:
  impostale sull'orario in cui i mercati sono aperti.
- Nella stessa pagina, **"Sospendi aggiornamenti"** per rimandarli a un
  momento in cui sei davanti al computer.

Dopo ogni riavvio, controlla `/salute`: è la verifica che tutte e tre le
cose sono ripartite davvero.

---

## 5. Accorgersi che è morto, senza dipendere dal PC

Se il PC si spegne muore anche Telegram, quindi il bot **non può dirti che
è morto**. Serve qualcosa fuori.

Il modo più semplice è un servizio gratuito di monitoraggio (ce ne sono
diversi) puntato su `https://bot.iltuodominio.it/salute`, con un controllo
ogni pochi minuti e la notifica via email o push quando smette di
rispondere. Costa zero e copre il caso peggiore: black-out, disco pieno,
Windows che si riavvia da solo alle tre di notte.

---

## 6. Se il server riparte con posizioni aperte

Non è un disastro: i livelli di stop e target non stanno nella memoria del
programma, stanno **in archivio** (`bot.db`). Alla ripartenza la sentinella
li rilegge e ricomincia a sorvegliarli, e riconcilia con quello che il
broker ha davvero aperto.

Quello che si perde sono **i secondi di buco**: mentre il server era giù,
nessuno guardava i livelli. Se il prezzo li ha attraversati in quel
momento, la chiusura avviene alla ripartenza, al prezzo di allora e non a
quello del livello.

`/salute` ha un campo `posizioni_scoperte` che serve esattamente a questo:
se è diverso da zero, ci sono posizioni aperte che nessuno sta
sorvegliando.
