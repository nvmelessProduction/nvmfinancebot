# I dati dalla VPS alla palestra

La palestra degli agenti (`strumenti/allena.py`) gira da Claude. Da lì Dukascopy
blocca i download dei prezzi al minuto; dalla VPS no. E le settimane dal
vivo nascono sulla VPS. Per questo la VPS scarica e spedisce, e la palestra
riceve.

Tre passi, una volta sola. Il bot può continuare a girare durante tutto.

## 1. Scaricare vent'anni di prezzi al minuto

Nella cartella del bot sulla VPS (quella con `avvia.bat`), **doppio clic su
`scarica.bat`**.

- La prima volta prepara Python da solo: un paio di minuti.
- Poi scarica un mese alla volta e scrive a che punto è.
- **Ci mette parecchie ore**, anche una notte. Puoi chiudere la finestra
  quando vuoi: al prossimo doppio clic riprende da dove era.
- Occupa qualche GB nella cartella `dati\grezzi`.
- Alla fine scrive `Finito`.

## 2. La chiave per spedire (una volta sola)

La chiave è un segreto: **non mandarla a nessuno, nemmeno a Claude**. Va solo
nel file `.env` della VPS, che non entra mai nel repository.

1. Entra su **github.com** con il tuo account.
2. In alto a destra, clic sulla tua foto → **Settings**.
3. In fondo al menu a sinistra → **Developer settings**.
4. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
5. **Token name**: `bot VPS dati`. **Expiration**: la più lunga che ti offre.
6. **Repository access** → **Only select repositories** → scegli
   `nvmfinancebot`.
7. **Permissions** → **Repository permissions** → **Contents** →
   **Read and write**. Il resto lascialo com'è.
8. In fondo, **Generate token**. Copia la chiave (inizia con `github_pat_`):
   GitHub la mostra una volta sola.
9. Sulla VPS, nella cartella del bot, apri il file `.env` con il **Blocco
   note** e aggiungi in fondo una riga:

   ```
   GITHUB_TOKEN=la_chiave_che_hai_copiato
   ```

   Salva con lo stesso nome (`.env`, non `.env.txt`) e chiudi.

Questa chiave può scrivere solo in questo repository. Se un giorno vuoi
toglierla, la cancelli da GitHub (stesso posto del punto 4) e togli la riga
dal `.env`.

## 3. Spedire

Quando `scarica.bat` ha finito, **doppio clic su `consegna.bat`**.

- Fa candele da 15 minuti dai minuti scaricati (quindici volte più
  leggere), ci aggiunge le decisioni e i risultati del bot dal vivo, e
  spedisce tutto su GitHub in un ramo a parte, `dati-vps`, che non tocca il
  codice.
- Prima di spedire, toglie dal registro del bot ogni valore segreto del
  `.env` (token, password): i segreti non escono mai dalla VPS.
- Alla fine scrive `GitHub: spedito.` Dillo a Claude: prende i dati e li
  porta in palestra.
- Da lì in poi il bot spedisce da solo le settimane dal vivo, ogni sabato
  dopo la riunione.

## 4. Gli altri strumenti

Il bot impara anche dalle altre 23 coppie forex fra le otto valute
principali (EURGBP, GBPJPY, AUDNZD, …), dall'argento, dal petrolio (WTI e
Brent), da sei indici (S&P 500, Nasdaq 100, Dow Jones, DAX, FTSE 100,
Nikkei) e da due crypto (BTCUSD, ETHUSD); l'elenco è in
`nvm/dati/strumenti.py`. Tutti gratis da Dukascopy. Quando `scarica.bat`
ha finito:

1. **Doppio clic su `scarica_nuovi.bat`.** Prima scarica le ore (un paio
   d'ore), poi i minuti (qualche giorno: puoi chiudere e riprendere quando
   vuoi).
2. Quando le ore sono finite, e poi di nuovo quando sono finiti i minuti,
   **doppio clic su `consegna.bat`**: spedisce quello che c'è di nuovo.

## 5. I video di Romeo

Claude studia i video di Romeo guardando i grafici mentre legge le sue
parole. YouTube blocca gli scaricamenti dai server (anche dalla VPS): si
fanno dal **computer di casa**.

1. Sul computer di casa estrai `RomeoVideo.zip` (te lo manda Claude; dentro
   ci sono `scarica_video.bat` e `strumenti/video.py`) e fai **doppio clic su
   `scarica_video.bat`**. La prima volta installa Python da solo. Per ogni
   video prende un fotogramma ogni 15 secondi e i sottotitoli, poi cancella
   il video. Circa un'ora; puoi chiudere e riprendere quando vuoi.
2. Alla fine prepara i file `video_romeo_1.zip`, `video_romeo_2.zip`, ... (ognuno sotto i
   25 MB) e apre la pagina di GitHub per caricarli sul ramo dei dati
   (https://github.com/nvmelessProduction/nvmfinancebot/upload/dati-vps): trascinali dentro
   e premi **Commit changes**. Poi dillo a Claude. (In alternativa, se puoi copiarli sulla
   VPS: nella cartella del bot o sul Desktop, e doppio clic su `consegna.bat`.)

## 6. Analizzare su TradingView, in automatico

Il bot analizza sui grafici di TradingView che scegliete voi e apre da solo gli ordini su MT5. Il proprietario, il
12/10/2026: TradingView ha dato l'ok all'uso automatico tramite il loro server MCP, senza webhook (la mail resta al
proprietario: conservatela). Webhook il bot non ne usa.

1. **Il login, una volta sola.** Sulla VPS fai doppio clic su `tradingview_accesso.bat`. Si apre il browser: entra
   col vostro account TradingView (serve il piano Essential o superiore) e premi **Allow**. La finestra poi prova a
   leggere i grafici e scrive `OK` o `NO` per ognuno. Le chiavi restano sulla VPS in `dati\vivo\tradingview.json`:
   non mandarle a nessuno.
2. **I grafici.** Nel file `.env` aggiungi la riga coi grafici, scritti come su TradingView (la fonte prima dei due
   punti come la scrive TradingView: ICE e' `FX_IDC:`, FXCM e' `FX:`, Capital.com e' `CAPITALCOM:`):
   `TRADINGVIEW_SIMBOLI=FX_IDC:EURUSD, FX:XAUUSD, FX:SPX500, CRYPTO:BTCUSD`. Se il nome dopo i due punti e' diverso
   da quello del bot, aggiungi il nome del bot dopo l'uguale: `OANDA:US30USD=US30`. Per il dollaro:
   `TRADINGVIEW_DXY=CAPITALCOM:DXY` (se manca, TVC:DXY). Per le crypto: `TRADINGVIEW_TOTAL=CRYPTOCAP:TOTAL` (un
   setup CRT sulla TOTAL fa entrare su BTC ed ETH dalla stessa parte).
3. **Riavvia il bot** (chiudi la finestra di `avvia.bat` e rifai doppio clic). Sul canale operativo arriva
   "📺 Da adesso analizzo su TradingView e apro da solo".

Come funziona:
- Quando c'e' un setup decide la rete neurale (punto 7; senza la rete, la squadra). Se lo prende, il bot entra su MT5
  a mercato con stop e target **ai prezzi di TradingView**, e manda "🧠 PERCHÉ HO APERTO" con la spiegazione e
  **Correggi**. Non entra se su MT5 il prezzo e' gia' oltre lo stop o il TP1, o se sullo strumento c'e' gia'
  un'operazione.
- Se la rete lo lascia, arriva in équipe con **Apri lo stesso** (vale 30 minuti dall'apertura della candela 3) e
  **Correggi**. I pulsanti hanno risposta subito.
- Se il bot si riavvia (anche per un aggiornamento), gli «Apri lo stesso» ancora aperti non valgono piu'.
- Se TradingView non risponde o l'accesso scade, arriva un allarme e il bot non analizza: non torna mai di nascosto
  ai prezzi di MT5. Le operazioni aperte le segue lo stesso. Per l'accesso scaduto: rifai il punto 1.
- Per tornare ai prezzi di MT5: togli la riga `TRADINGVIEW_SIMBOLI` dal `.env` e riavvia (anche li' decide la rete e
  il bot apre da solo).

## 7. La rete neurale: decide lei, e la correggete voi

La rete allenata su Kaggle guarda ogni setup del bot e decide se entrare, con la sua spiegazione: cosa vedono i suoi
"occhi" (la direzione di giorno, settimana e mese; i CRT a 4 ore e del giorno) e cosa la spinge o la frena rispetto a
un setup tipico del bot.

1. **Una volta sola:** doppio clic su `rete_installa.bat` (scarica PyTorch, circa 200 MB, qualche minuto). Alla fine
   scrive "Rete neurale pronta". Se esce WinError 1114 (c10.dll), installa il Visual C++ di Microsoft
   (https://aka.ms/vs/17/release/vc_redist.x64.exe), riavvia la VPS e rifai il doppio clic. Poi riavvia il bot: sul
   canale operativo arriva "🧠 La rete neurale è collegata".
2. **Come lavora:** quello che prende lo apre da solo e vi spiega perché («PERCHÉ HO APERTO», con **Correggi**);
   quello che lascia arriva in équipe con **Apri lo stesso** e **Correggi**.
3. **Correggi:** arriva un messaggio con una riga di pulsanti per ogni cosa che la rete ha detto (il trade, la
   direzione di giorno, settimana e mese, i CRT): premete la risposta giusta (il punto • segna quella della rete).
   Per spiegare il perché, rispondete a quel messaggio scrivendo. Tutto resta sulla VPS in `dati\vivo\rete\`, con
   quello che la rete aveva visto: sono gli esempi per riallenarla.
4. **La sera**, nel riepilogo in équipe, c'e' la pagella della rete: quante volte ci ha preso e come sono andati i
   suoi trade.

Senza PyTorch il bot lavora come prima (decide la squadra) e lo dice con un allarme.

## Se qualcosa va storto

| Cosa vedi | Cosa vuol dire |
|---|---|
| `TroppeRichieste` | Dukascopy ha smesso di rispondere per un po'. Aspetta mezz'ora e rilancia `scarica.bat` |
| `Manca GITHUB_TOKEN nel file .env` | manca la riga del punto 2.9, o il file non si chiama `.env` |
| `GitHub non accetta i dati` | la chiave è sbagliata, scaduta o senza **Contents: Read and write**: rifai il punto 2 |
| `YouTube chiude tutte le porte a questa VPS` | YouTube blocca la VPS. Mandane la foto a Claude |
| `python non è riconosciuto` | manca Python. Installalo da python.org, spuntando "Add Python to PATH" |
| qualsiasi altro errore | manda a Claude una foto della finestra (senza la chiave in vista) |
