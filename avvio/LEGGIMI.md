# Farlo girare da solo

## In breve

1. **Doppio clic su `avvia.bat`.** La prima volta prepara tutto e fa tre
   domande; dalla seconda in poi parte e basta.
2. **Una volta sola, doppio clic su `avvio\installa_avvio_automatico.bat`.**
   Da quel momento il bot riparte da solo a ogni accensione del PC.

Non c'è altro. Niente alert da creare, niente tunnel, niente dominio, niente
segreti da copiare.

---

## Cosa deve restare acceso

Solo due cose, non più tre:

| Cosa | Perché | Se muore |
|---|---|---|
| **MetaTrader 5**, aperto e connesso | il bot non fa il login da solo: si aggancia al terminale già aperto | niente ordini, niente prezzi per la sorveglianza |
| **`avvia.bat`** | è il bot: cerca le candele, decide, sorveglia stop e target | le posizioni aperte restano **senza stop e senza target** |

Il tunnel non serve più. Prima serviva perché TradingView doveva riuscire a
bussare al tuo PC; adesso è il bot che va a prendersi i dati, quindi non c'è
niente da esporre su internet. È sparito anche tutto quello che ci girava
intorno: indirizzi che cambiano, domini da comprare, `WEBHOOK_SECRET` da
tenere allineato.

`avvia.bat` non parte e basta: se il bot muore lo **rifà partire** dopo 15
secondi, all'infinito. Ogni riavvio finisce in `avvio\riavvii.log`: se quel
file cresce, lì c'è scritto quando e quante volte.

---

## Le due cose che Windows non fa da solo

### MetaTrader deve aprirsi e collegarsi da solo

Premi **Windows+R**, scrivi `shell:startup`, Invio: si apre la cartella dei
programmi che partono all'accensione. Mettici dentro un collegamento a
`terminal64.exe` di MetaTrader 5.

Poi, dentro MT5: *Strumenti → Opzioni → Server*, spunta **"Mantieni le
informazioni personali"** perché faccia il login da solo. E lascia acceso il
pulsante **Algo Trading**.

### Il PC deve accedere da solo

Se manca la corrente, al ritorno Windows si ferma alla schermata di accesso e
**niente parte**, perché tutto quanto sopra parte al *login*, non all'avvio.

`Windows+R` → `netplwiz` → togli la spunta a *"Per utilizzare questo computer
è necessario che l'utente immetta il nome e la password"*.

> **Il prezzo:** chiunque abbia accesso fisico al PC entra senza password, e
> su quel PC c'è il tuo `.env`. Se il computer non sta in un posto tuo, non
> farlo.

---

## Windows Update

Un riavvio a sorpresa nel mezzo di una posizione aperta è esattamente ciò che
non vuoi. Non si disattiva del tutto, ma si governa:

- *Impostazioni → Windows Update → Opzioni avanzate → **Ore di attività***:
  impostale sull'orario in cui i mercati sono aperti.
- Nella stessa pagina, **"Sospendi aggiornamenti"** quando non vuoi sorprese.

Dopo ogni riavvio il bot riparte da solo, ma MT5 deve essersi ricollegato:
apri `http://localhost:8000/salute` e guarda che `mt5_connesso` sia vero.

---

## Se il bot riparte con posizioni aperte

Non è un disastro: stop e target non stanno nella memoria del programma,
stanno in **`bot.db`**. Alla ripartenza la sentinella li rilegge e riconcilia
con quello che il broker ha davvero aperto.

Quello che si perde sono i **secondi di buco**: mentre il bot era giù nessuno
guardava i livelli. Se il prezzo li ha attraversati in quel momento, la
chiusura avviene alla ripartenza, al prezzo di allora e non a quello del
livello.

`/salute` ha un campo `posizioni_scoperte`: se è diverso da zero, ci sono
posizioni aperte che nessuno sta sorvegliando.

### E non si rivaluta il passato

Se il bot è stato spento due giorni, alla ripartenza trova decine di candele
nuove. Le **archivia tutte**, perché servono alla storia, ma **decide solo
sull'ultima**. Decidere adesso su prezzi di ieri sarebbe sbagliato, e farlo
venti volte di fila sarebbe peggio.

---

## Accorgersi che è morto, senza dipendere dal PC

Se il PC si spegne muore anche Telegram, quindi il bot **non può dirti che è
morto**. Serve qualcosa fuori: il modo più semplice resta un servizio
gratuito di monitoraggio, ma adesso che non c'è più un indirizzo pubblico
serve un piccolo ponte (o un controllo che fai tu). È l'unica cosa che il
passaggio al funzionamento autonomo ha reso più scomoda, e vale la pena
saperlo.
