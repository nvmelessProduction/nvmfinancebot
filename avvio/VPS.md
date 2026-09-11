# Farlo girare su un VPS

## Cosa è cambiato

Quando il bot aspettava gli alert di TradingView serviva un indirizzo
pubblico raggiungibile da internet, e quindi un tunnel, un dominio, dei DNS.
Adesso il bot **va a prendersi i dati da solo**: fa solo richieste in uscita
(la fonte delle candele, Telegram) e parla con MT5 sulla stessa macchina.

**Non c'è niente da esporre, nessuna porta da aprire, nessun dominio.** Un
VPS Windows qualsiasi va bene: si clona il progetto, si lancia `avvia.bat`,
finito.

---

## Deve essere Windows. Non è una preferenza

L'API Python di MetaTrader 5 esiste **solo per Windows**: MetaQuotes non
pubblica una build Linux, e il pacchetto `MetaTrader5` si installa solo lì
(nel `requirements.txt` c'è già il marcatore `sys_platform == "win32"`).

Questo esclude i VPS gratuiti, che sono tutti Linux — Oracle Cloud Always
Free, Google Cloud, AWS. Su Oracle per giunta la macchina gratuita è ARM,
quindi per far girare MT5 servirebbe Wine **più** l'emulazione x86: fragile,
lento, e una cosa in più che può rompersi mentre una posizione è aperta.

> **La trappola da evitare.** L'*MQL5 Virtual Hosting* (~12,80 $/mese) è
> l'opzione più economica che troverai cercando "hosting MT5", ed è pensata
> apposta per MetaTrader. Ma ospita **solo il terminale e gli Expert Advisor
> scritti in MQL5**: non esegue un processo Python. Per questo bot non serve
> a niente.

---

## Le due strade

### Il VPS del broker

Molti broker ne offrono uno gratuito a chi raggiunge un volume mensile o un
deposito minimo. FP Markets, indicativamente, chiede 5 lotti al mese su conto
Standard (10 su Raw) oppure un deposito intorno ai 1.000 $.

Sono condizioni che cambiano e che **valgono sul conto reale, non sul demo**:
fattele confermare da loro prima di contarci.

### Un VPS Windows a pagamento

Dai 10 ai 15 $ al mese. Serve poco: **2 GB di RAM e 1 vCPU bastano** — il bot
è un processo Python che dorme quasi sempre, e il consumo vero è MetaTrader.
Prendine uno in un datacenter europeo se il tuo broker è europeo.

---

## Come si mette su

Dal tuo PC, connettiti al VPS con **Connessione Desktop remoto** (`mstsc`).
Poi, dentro il VPS:

1. **Python 3.11 o superiore** da python.org, spuntando *"Add python.exe to
   PATH"*.
2. **Git per Windows** da git-scm.com.
3. **MetaTrader 5 di FP Markets**, con il login al conto e *"Mantieni le
   informazioni personali"* spuntato. Accendi **Algo Trading**.
4. Il progetto:

   ```bat
   cd C:\
   mkdir bot
   cd bot
   git clone -b claude/trading-bot-infrastructure-5rht0h https://github.com/nvmelessProduction/nvmfinancebot.git progetto
   cd progetto
   avvia.bat
   ```

5. Una volta sola, per farlo ripartire a ogni riavvio del VPS:

   ```bat
   avvio\installa_avvio_automatico.bat
   ```

**Non copiare il `.env` dal PC di casa**: rifai la configurazione sul VPS.
Copiare un file che contiene una chiave significa averne due copie in giro.

---

## La cosa che rovina i VPS: disconnettersi male

È il punto che fa perdere più tempo, e non è ovvio.

Quando chiudi il Desktop remoto hai due modi:

| Come esci | Cosa succede |
|---|---|
| **Chiudi la finestra** (o *Disconnetti*) | La sessione resta viva. MT5 e il bot **continuano a girare**. È così che si fa. |
| **Disconnetti → Esci / Log off** | La sessione viene chiusa. MT5 si spegne, il bot si spegne. **Tutto fermo.** |

Usa sempre il primo. Se un giorno trovi il bot fermo senza spiegazione,
questa è la prima cosa da controllare.

Serve comunque l'accesso automatico (`netplwiz`), perché al riavvio del VPS
niente parte finché qualcuno non entra — e su un VPS non c'è nessuno.

---

## Due cose da tenere d'occhio, che a casa non hai

**L'indirizzo del datacenter.** La fonte gratuita delle candele è un endpoint
pubblico senza contratto, e da un indirizzo di datacenter è più facile
incontrare limitazioni che da una connessione di casa. Se dopo il passaggio
vedi comparire errori nel ciclo di mercato, guarda `ultimo_errore` in
`/salute`: il bot non inventa dati, si limita a non aggiornare l'archivio
finché la fonte non risponde di nuovo.

**Il monitoraggio.** Su un VPS non ti accorgi nemmeno che è morto, perché non
ci passi davanti. Le notifiche Telegram coprono il caso in cui il bot sia
vivo; per il caso in cui sia morto serve qualcosa fuori dal VPS.

---

## Quello che il VPS non risolve

Un VPS toglie il problema "il PC deve restare acceso". **Non** toglie:

- il calendario news da aggiornare
- `TF_H4`, `TF_H6`, `TF_H12` che si riempiono solo girando
- la scelta fra `dry_run`, `semi` e `auto`, che resta tua

E soprattutto: spostare su un VPS un bot che non hai ancora visto lavorare
significa solo non averlo sotto gli occhi mentre impara. Il VPS ha senso
**dopo** che ti fidi, non prima.
