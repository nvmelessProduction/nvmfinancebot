# Passaggio di consegne: tutto quello che serve per ripartire

_Aggiornato il 24/10/2026, dopo il commit `de50bef`._

**Chi lavora su questo progetto legge questo file per primo e lo aggiorna prima di chiudere ogni sessione.** Va
aggiornato soprattutto in: §5 (stato del bot), §6 (decisioni aperte), §7 (lavoro in corso). Il proprietario lo vuole
«alla virgola», per non perdersi fra una chat e l'altra (24/10/2026). I dettagli completi delle regole stanno in
`documenti/spec/metodo_foto.md`; qui c'è il riassunto e il "dove siamo".

---

## 1. Chi, cosa, dove

- **Il progetto.** Un bot che fa trading col metodo CRT del proprietario, detto «il metodo delle foto», perché le
  regole vengono dai suoi esempi su TradingView, in `documenti/casi/foto/`. Gira su una VPS Windows con MetaTrader 5,
  sul **conto demo da 900 € con leva 1:500**. Legge le candele da TradingView (collegamento MCP) e scrive su Telegram in
  due canali: **operativo** ed **équipe**.
- **Il repository.** `nvmelessProduction/nvmfinancebot`. Il ramo di lavoro, e quello che il bot dal vivo scarica, è
  **`claude/zealous-albattani-394cd9`** (`vivo.RAMO`).
- **La VPS si aggiorna da sola.** Ogni 2 minuti controlla il ramo; se cambiano file di codice (`.py .json .npz .bat
  .txt`) si aggiorna e riparte, e lo scrive su Telegram con la «Novità» presa dal titolo del commit. I soli `.md` non la
  fanno ripartire. **Ogni push di codice arriva al bot vero entro 2 minuti.**
- **Le persone.**
  - Il proprietario: scrive in italiano e spesso ascolta le risposte mentre guida.
  - Il suo socio.
  - **Venice**: un'intelligenza artificiale esterna che fa da revisore. I suoi messaggi arrivano incollati dal
    proprietario; vanno verificati sul codice, come lei stessa chiede.
  - **Codex** lavora anche lui nel repository: sempre `git fetch` prima di fare push.
- **Romeo** è l'autore dei video del metodo originale, non il proprietario. Il metodo dei video è nel codice ma spento
  (`giro.METODO = "foto"`). Anche le 112 entrate di `documenti/casi/entrate-romeo.csv` sono di Romeo.

## 2. Regole fisse (non si violano mai)

1. **Segreti**: mai leggere o stampare il `.env` della VPS, mai chiedere chiavi in chat, mai segreti nel repository.
2. **Git**:
   - push solo su `claude/zealous-albattani-394cd9`;
   - mai cancellare `claude/trading-bot-infrastructure-5rht0h`;
   - niente force push e niente riscrittura della storia;
   - nessuna pull request se non la chiede il proprietario.
3. **Prima di ogni push di codice**: prove verdi (`python -m pytest -q`). Oggi l'unica che non passa, ed è attesa, è la
   foto 4/6 (§6).
4. Mai il nome del socio né il titolo del suo libro in quello che va nel repository. Le foto di TradingView si tagliano
   in alto (la riga col nome dell'account). Gli screenshot di WhatsApp non vanno mai nei documenti.
5. Messaggi dei commit in italiano, come gli altri, con le righe di attribuzione che dà la sessione. Nessun nome di
   modello nei contenuti pubblicati.
6. Le candele di TradingView si usano così come sono. Il proprietario, 13/10: *"non deve costruire niente ma
   utilizzare i dati con gli orari che gli vengono forniti così come sono"*.
7. Il principio del proprietario: *"Tutto quello che sta scritto là [sulle foto] è quello che deve fare la rete
   neurale. Su ogni fottuto pair."*
8. **Dimensione e scelta** (24/10, concordato col proprietario):
   - *"se è valida deve aprire"* è una regola di **dimensione**: un setup scelto non resta fuori perché il conto è
     piccolo, si apre almeno il lotto minimo;
   - *"il Capo deve selezionare i CRT"* è una regola di **scelta**.
   - Insieme: **si seleziona, ma quello che si seleziona si apre sempre.**

## 3. Come lavorare col proprietario

- **Come scrivere:** italiano semplice, frasi corte, il perché delle cose, numeri veri anche quando vanno male. Niente
  gergo, niente «dovrebbe migliorare».
- **Se chiede di «leggergli» qualcosa:** testo da ascoltare, cioè niente tabelle, niente nomi di codice, gli schemi
  raccontati a parole.
- **Mentre lavori:** frasi brevi su cosa stai facendo. Ha rifiutato una domanda a scelta multipla: meglio chiedere in
  testo.
- **I file che chiede** (PDF, recap) vanno mandati come file, non solo descritti.
- **Le sue decisioni** sono la legge del bot. Se una proposta (di Venice o tua) va contro una sua decisione, si dice
  quale e con che data, e si aspetta il suo sì.

## 4. Il bot che gira oggi sul demo, in breve

La spiegazione completa, con le foto e le frasi del proprietario, è nel PDF «Il bot sul conto demo» del 23-24/10.
L'ha ricevuto il proprietario; il generatore stava fuori dal repository ed è andato perso a fine sessione. Le regole
con le fonti: `documenti/spec/metodo_foto.md`.

- **Il giro di ogni ora** (`vivo.Bot.giro`), 5 secondi dopo la chiusura della candela:
  1. candele nuove da TradingView;
  2. CRT con la candela 3 appena aperta su 1 ora, 4 ore, 6 ore, giorno, settimana, mese (`foto.TF_CRT`);
  3. le occasioni (`giro.occasioni_foto`), la squadra, il Capo, il Rischio, la rete, l'Esecutore;
  4. i messaggi.
  - Ogni minuto il bot segue le operazioni aperte.
  - Oltre 10 minuti dall'apertura della candela 3 non si entra (`RITARDO_MASSIMO = 600`).
  - Dal 24/10 la durata del giro va nel registro, con un allarme sopra gli 8 minuti (`DURATA_ALLARME`).
- **I mercati** (`vivo.STRUMENTI_VIVO`):
  - EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCHF, USDCAD entrano **solo** con un CRT del DXY (`CAPITALCOM:DXY`) che ha preso
    un key level;
  - XAUUSD e XAGUSD entrano coi **loro** CRT (il DXY è solo un parere);
  - BTCUSD ed ETHUSD entrano **solo** con un CRT della TOTAL (`CRYPTOCAP:TOTAL`) che ha preso un key level, nello
    stesso verso.
- **Le coppie col dollaro:**
  - si usano gli orari del CRT del DXY e i prezzi della coppia in quelle ore (`foto.dal_dxy`);
  - DXY long vuol dire vendita su EUR, GBP, AUD, NZD e acquisto su CHF e CAD;
  - un CRT del DXY che è lo stesso movimento di uno già usato non fa entrare (`giro.stesso_movimento`);
  - la coppia che fa anche lei il CRT con un key level prende la ★ (Cacciatore +1).
- **Il CRT** (`foto.trova`):
  - la candela 1 è il range: se è una inside bar si usa la madre (fino a 12 candele);
  - la candela 2 prende un lato e chiude dentro, senza toccare l'altro e senza sforare (`TOLLERANZA_CHIUSURA = 0`);
  - l'ora del rollover (17 di New York) non conta.
- **Il key level** (`foto.key_level_presi`): massimo o minimo del periodo prima (D, W, M, 3M, 12M), preso per la prima
  volta; per 4, 6 e 12 ore vale anche quello di oggi. Il CRT a 1 ora vale solo col DH/DL e il massimo o minimo a 4 ore
  (`giro.setup_buono`).
- **La direzione** (`foto.direzione`): obbligatoria per oro e argento, un parere per i guidati. Blocca solo la candela
  dei 3 o 12 mesi contro, su un CRT a 1 ora che ha preso soltanto livelli del giorno.
- **Ingresso, stop e TP1:**
  - ingresso all'apertura della candela 3;
  - stop oltre la candela 2, almeno `max(5 pip, 7% del range giornaliero medio di 14 giorni)`;
  - TP1 all'altro lato del range: lì si chiude il 25% (se il lotto si divide) e lo stop va a pareggio più le
    commissioni (`esecutore.Esecutore.pareggio`). Mai alla chiusura della candela d'ingresso.
- **Il target finale** (`foto.obiettivo_finale`), in quest'ordine:
  1. il key level opposto del timeframe più basso preso, solo se sta oltre il TP1;
  2. un gap valido;
  3. il key level di liquidazione;
  4. l'altro lato del periodo più grande;
  5. il DH o DL di ieri;
  6. se no, tutto al TP1.
  - Il piano deve rendere almeno 1 R (`foto.RR_MINIMO = 1.0`).
  - I piani sono due: il 25% al TP1 col resto al target, oppure tutto al TP1. Il terzo piano (target più in là) è
    calcolato ma **spento**: `piani_romeo` ne passa uno solo.
- **La squadra** (`nvm/intelligenti/`):
  - le regole obbligatorie sono CRT, key level (quello della guida per i guidati) e direzione;
  - 8 agenti votano da −2 a +2: Cacciatore, Key level, Bias, Gap, DXY, Orario, Livelli, Grilletto;
  - **i voti non bloccano**, il veto non esiste più (22/10, *"Leva il veto ovunque"*). La previsione della domenica
    vale ±0,5.
- **Il Capo:** parte dal 40%, pesa i voti con la fiducia imparata dal vivo, mette in ordine e prende tutto. Una
  operazione per strumento, nessun massimo per giro.
- **Il Rischio:**
  - ripartito da zero il 23/10 (`RIPARTENZA_RISCHIO`), base 1%;
  - puntata = base × e^(convinzione·z − aperte·100·esposizione − stesso·100·stesso), con l'esponente tenuto fra −5 e 3;
  - la ricalcola prima di ogni ordine vedendo le operazioni appena aperte (`Squadra.ripunta`), senza tetti;
  - esempio: 6 coppie dallo stesso CRT del DXY puntano 1%, poi 0,82, 0,70, 0,60, 0,54 e 0,48%, in tutto circa il 4,1%.
- **La rete neurale:** sui setup con tutte le regole, e su quelli del DXY o della TOTAL, entra sempre. Se ne lascia
  uno, in équipe compare il pulsante «Apri lo stesso» (valido 30 minuti); dopo ogni apertura c'è «Correggi».
- **L'Esecutore** (`nvm/vivo/esecutore.py`) controlla: solo conto demo, Algo Trading acceso, lo stop c'è, il prezzo
  non è già oltre lo stop o il TP1, la distanza minima del broker, il CRT non è già aperto (commento sull'ordine).
  - **Dal 23/10, sotto il lotto minimo apre sempre il minimo** (`sempre_il_minimo=True` dalla squadra) e scrive quanto
    rischia davvero. Sull'oro e sull'argento, col conto da 900 €, il minimo rischia circa il 2-4% del conto.
- **Telegram:**
  - comandi `/strumenti`, `/grafico`, `/piano`, `/romeo`;
  - messaggi 📐 per i CRT delle guide, ⏸ per le occasioni non aperte col perché, 🕑 per gli orari dei grafici guida a
    ogni avvio;
  - riepilogo alle 17 di New York; riunione il sabato dalle 8 UTC; previsione della settimana la domenica dalle 18
    UTC.
- **Gli orari dei grafici:**
  - si leggono dalle candele a 4 ore (`tradingview.griglia`): vince la griglia che ne spiega di più; sotto il 90%
    allarme ma si usa lo stesso; per correggere un orario salvato basta il 60%;
  - il DXY risulta sulle 20 di New York all'80% (candele alle 2-6-10 italiane); le coppie alle 18 di New York (0-4-8);
    TOTAL e crypto in UTC;
  - **attenzione al cambio d'ora**: il 25/10 in Italia, il 1/11 a New York.

## 5. Stato al 24/10/2026

- **Gli ultimi commit sul ramo:**
  - `de50bef` durata del giro misurata, allarme oltre 8 minuti;
  - `a55edcb` sotto il lotto minimo si apre sempre il minimo;
  - `5869c77` orari dei grafici guida in ore italiane;
  - `5cab224` Rischio ripartito da zero e più intelligente;
  - `f3d48a3` orari del DXY e della TOTAL a ogni avvio;
  - prima: le correzioni del 22-23/10, descritte in `documenti/CORREZIONE-22-10.md`.
- **Le prove:** 407 in tutto; passano tutte tranne `test_foto.py::test_gli_esempi_del_proprietario[4/6-...]`, attesa
  (§6).
- **Il risultato atteso, il punto più importante:**
  - la misura sui vent'anni del 15/10 (fase 3 di Nameless su Kaggle, 740 mila setup, 85 mercati, con le regole di
    allora, **senza i setup del DXY**) dice **−0,08 R a operazione** in ogni periodo, circa −0,03 senza lo spread;
  - il Capo di quella prova non ha trovato un gruppo di setup che guadagni;
  - **le regole di oggi non sono mai state misurate**: è il lavoro in corso (§7).
- **I dati della VPS** (ramo `dati-vps`: `vivo/registro.jsonl`, `libro.jsonl`, `stato.json`) sono fermi all'**8/10**.
  Per giudicare il demo serve che il proprietario lanci `consegna.bat` sulla VPS.
- **Il PDF delle funzioni** l'ha ricevuto il proprietario (versione corretta del 24/10). L'ha chiesto per mandarlo al
  socio, così da capire dove sono ancora i problemi.

## 6. Decisioni aperte (aspettano il proprietario)

1. **Foto 4/6** (oro, 1 ora, 10/09):
   - la foto vuole come target il WL 4328 (key level di liquidazione); il bot mette il DL 4384, il key level opposto
     cercato per primo;
   - **A** = la liquidazione prima del key level opposto (passano tutte le prove);
   - **B** = resta com'è (si cambia la prova).
2. **Le operazioni aperte per sbaglio** il 22/10 alle 12 (AUDUSD, GBPUSD, USDCHF col «CRT H6») e nella notte del 23/10
   (USDCHF delle 00:01 e altre): se chiuderle a mano lo decide lui.
3. **Le voci 0.4 e 0.5 di Venice** si decidono **solo dopo la misura** (§7.A):
   - 0.4: le correlazioni dell'Esecutore sulle puntate della squadra. Attenzione: il Rischio riduce già vedendo le
     aperte, e insieme ridurrebbero due volte;
   - 0.5: il target lontano quando il vicino rende meno di 1,5 R.
4. **Le tappe 1-4 di Venice** (generatore di tutti i candidati, doppia etichetta, selettore allenato sull'R fuori
   campione, corpo e libri): dopo la misura, una alla volta, col cancello di `documenti/PIANO.md` §2 (+0,10 R sulla
   base, intervallo sopra zero).

## 7. Lavoro in corso, coi passi esatti

### 7.A La misura delle regole di oggi sui vent'anni (chiesta il 24/10)

La richiesta, parola per parola (da Venice, accettata dal proprietario):

> Misura le regole di oggi sui vent'anni, coi costi e fuori campione, usando la stessa catena del bot dal vivo. Nello
> stesso run confronta target vicino vs lontano, RR 1.0 vs 1.5, e con/senza correlazioni, così chiudi anche 0.4 e 0.5.
> Dichiara cosa non è misurabile (BTC/ETH con la TOTAL) e misura le coppie col DXY sintetico. Dammi i numeri: baseline,
> R per mercato e timeframe, intervalli, occasioni, e le 24 foto come controllo. Poi, senza aspettare, fai 0.2 e 0.6.

Il numero che conta è l'R del sottoinsieme scelto, con l'intervallo tutto sopra zero.

**A che punto è:** codice della misura **non ancora scritto**.

**I dati:**
- In questo container c'erano, in `dati/grezzi/ore/` (fuori da git, quindi **non ci sono** in una sessione nuova), le
  ore di Dukascopy con bid e ask veri, 2006-01 → 2026-08, per EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY e XAUUSD.
- **Dukascopy è lento** («troppe richieste»: circa 50 secondi per mese, ore e ore).
- **HistData è veloce**: `kaggle_rete.histdata.scarica_tutto([...], Path(cartella))` scrive in `cartella/ore_bid`,
  per mese, leggibile da `nvm.dati.ore.carica`. Dà solo il bid: lo spread si stima con `kaggle_rete.esperienza.SPREAD`
  e `con_spread`. HistData ha anche il **DXY vero** (`UDXUSD`, nome `DXY` in `histdata.NOMI`), ma **solo dal 2010**;
  prima si usa quello calcolato, `foto.dxy(basi)`, che vuole EURUSD, USDJPY, GBPUSD, USDCAD e USDCHF.
- Il 24/10 si scaricavano da HistData DXY (fatto: 2010 → 2026/10), USDCAD, NZDUSD e XAGUSD nella cartella di lavoro
  temporanea, che si perde a fine sessione. **Da rifare in una sessione nuova:**

  ```
  python -c "from pathlib import Path; from kaggle_rete.histdata import scarica_tutto; \
  scarica_tutto(['DXY','USDCAD','NZDUSD','XAGUSD','EURUSD','GBPUSD','AUDUSD','USDCHF','USDJPY','XAUUSD'], Path('dati/storico'), pausa=0.5)"
  ```

  `dati/` è fuori da git per le cartelle `grezzi` e `tabelle`. Aggiungere `dati/storico/` al `.gitignore`.
- In alternativa c'è **Kaggle** (dataset `nameless-dati`: 85 mercati HistData e crypto Binance, celle in
  `kaggle_rete/`), ma lì la misura la deve lanciare il proprietario a mano.

**Come farla** (`strumenti/misura_vivo.py`, da scrivere):
1. **Le ore di ogni strumento** e le giornaliere lunghe per 3, 6 e 12 mesi. Gli orari come dal vivo:
   `candele.SESSIONI[...] = "18"` per coppie e metalli, `"20"` per il DXY.
2. **Mese per mese, per ogni strumento:**
   `giro.occasioni_foto(strumento, ore_fino_a_fine_mese, dal=inizio_mese, adesso=fine_mese, capo, gemelli={"DXY": ore_dxy}, lunghe=..., lunghe_dxy=...)`.
   - Il quadro si taglia a ogni candela 3 (`q.taglia`): niente futuro.
   - Tenere al massimo circa 13.000 ore per chiamata, come `vivo.ORARIE`, per la velocità.
   - Per accettare un'occasione usare le stesse regole della squadra: `metodo.valuta_foto` e `a_piu`.
3. **Una sola operazione aperta per strumento**: le occasioni mentre una è aperta si saltano. Ritardo zero
   all'ingresso.
4. **L'esito** con `nvm.prova.campo.simula`: il 25% al TP1 col pareggio più commissioni, il resto al target, la
   scadenza di `giro.TETTO_FOTO`, i costi (spread vero dove c'è l'ask, se no la stima, più `campo.COMMISSIONE`). Come
   riferimento: `kaggle_rete/esperienza.py` e `nvm/nameless/esiti.py`, che lo fanno già per i setup senza DXY.
5. **Le varianti nello stesso run:**
   - target come oggi, oppure lontano (`foto.target_dopo`, il terzo piano) quando il vicino rende meno di 1,5 R;
   - `RR_MINIMO` 1,0 contro 1,5;
   - per il conto (puntate): 1% fisso, il Rischio di oggi (esposizione), il Rischio più `portafoglio.riduzione` (0.4).
     Per queste tre servono l'equity, il drawdown massimo e il rendimento.
6. **I numeri da dare:**
   - la base («prendili tutti»);
   - l'R medio per mercato e per timeframe del CRT, e quante occasioni;
   - l'intervallo di confidenza al 95% (bootstrap a blocchi di settimane);
   - i periodi 2008-2022 (scelta della variante) e 2023-2026 (esame, guardato una volta sola);
   - le 24 foto come controllo (`tests/test_foto.py`: deve restare tutto uguale).
7. **Da dichiarare:**
   - BTC ed ETH con la TOTAL non si possono misurare (la TOTAL storica non c'è);
   - prima del 2010 il DXY è calcolato;
   - lo spread è stimato dove c'è solo il bid;
   - le candele sono di Dukascopy/HistData, non di TradingView.
8. **Scrivere i risultati** in `documenti/registro/tentativi.md` e qui. Niente collegato al vivo se non passa il
   cancello.

### 7.B Voce 0.6 di Venice: la pulizia del codice che dice cose non più vere (da fare, non cambia le decisioni)

- **`veto`**: il campo `Parere.veto` in `nvm/intelligenti/pareri.py` non lo assegna più nessuno. Va tolto con i suoi
  usi (`squadra.riunione`, `al_lavoro._scegli_nel_giro`, `decisione_in_parole`), con prove.
- **`tradingview.ora_di_sessione`**: la usano solo le prove. Va tolta lei con le sue prove, **non** la regola: scrivere
  sempre la griglia migliore e allarmare sotto il 90% è giusto. Venice aveva chiesto il contrario (0.3) e ha
  riconosciuto l'errore: rimetterebbe il bug del 23/10.
- **`nvm/vivo/scelte.json`**: il campo `perche` è vecchio («metà al TP1», «nessun limite di operazioni»). Va riscritto
  com'è oggi.
- **Commenti che non sono più veri:**
  - `vivo.Bot._accendi_tradingview`: dice «il bot propone e apre solo col vostro Apri»; non è più così, apre da solo;
  - l'inizio di `nvm/vivo/giro.py`: dice «decide come avrebbe deciso sullo storico», non vale per il metodo delle foto;
  - il commento su `piani_romeo` va bene, ma va detto che il terzo piano è spento.
- **`documenti/spec/metodo_foto.md`**: aggiungere la riga «dimensione e scelta» (§2 punto 8 di questo file).

### 7.C Altre cose rimaste da prima

- La pulizia generale di `documenti/ANALISI-CODICE.md`: restano le decisioni su «una operazione per strumento», la rete
  di oggi e la rimozione di Romeo.
- **Model 1** (ingressi con ordini limite sull'order block del timeframe basso): mai fatto.
- I dati storici della TOTAL.

## 8. Le correzioni di Venice già verificate (24/10), per non rifarle

**Giusto:**
- il bot prende tutti i setup validi;
- il terzo piano è spento;
- il dato "vivo" del vecchio Capo è a zero (`_decisione_foto`: x a zero, `p1` 0,5, `atteso` 0, quindi
  `Decisione.entra` sempre falso). Però con la squadra accesa non lo usa nessuno;
- le correlazioni dell'Esecutore sono spente (`riduci=False`);
- `VERSIONE` e `RIPARTENZA_RISCHIO` sono interruttori a mano;
- la fase 3 vede solo i setup presi;
- l'esame al 98% misura la somiglianza, non il guadagno.

**Sbagliato:**
- 0.3 (rimetterebbe il bug del 23/10);
- il «17% al target» viene dal metodo dei video (24/09);
- le 112 entrate sono di Romeo;
- il Capo della fase 3 non è un selettore pronto;
- «6 coppie rischiano come 6 trade»: in tutto è circa il 4,1%, non il 6%;
- misurare i 10 minuti «quando parte l'ordine» li renderebbe più stretti, non più larghi.

## 9. Dove stanno le cose

| Cosa | Dove |
|---|---|
| Il bot | `vivo.py` (`Bot.giro`, `_decidi`, `minuto`, `_candele_tradingview`, `_orari_dalle_candele`) |
| Le occasioni | `nvm/vivo/giro.py` (`occasioni_foto`, `_decisione_foto`, `piani_foto`, `stesso_movimento`) |
| Le regole delle foto | `nvm/agenti/foto.py` (`trova`, `key_level_presi`, `direzione`, `dal_dxy`, `dal_totale`, `obiettivo_finale`) |
| La squadra | `nvm/intelligenti/` (`metodo.py`, `pareri.py`, `squadra.py`, `al_lavoro.py`) |
| Gli ordini su MT5 | `nvm/vivo/esecutore.py` |
| TradingView | `nvm/vivo/tradingview.py` |
| I messaggi | `nvm/vivo/messaggi.py`, `conversazione.py`, `foto_grafico.py` |
| La rete dal vivo | `nvm/vivo/rete_vivo.py` |
| Le regole con le fonti | `documenti/spec/metodo_foto.md` |
| Le correzioni del 22-23/10 | `documenti/CORREZIONE-22-10.md` |
| L'analisi del codice | `documenti/ANALISI-CODICE.md` |
| La storia fino al 15/10 | `documenti/STATO.md` |
| Il piano e il cancello (+0,10 R) | `documenti/PIANO.md` |
| I tentativi e le misure | `documenti/registro/tentativi.md` |
| Le foto del proprietario | `documenti/casi/foto/` |
| Le prove delle foto | `tests/test_foto.py` |
| Kaggle (Nameless) | `kaggle_rete/`, `documenti/PROGETTO-NAMELESS.md` |
| I dati della VPS | ramo `dati-vps` |

## 10. La storia in breve

- **Settembre:** il metodo dei video di Romeo e gli agenti.
- **06/10:** il proprietario manda le sue foto, e il bot passa al «metodo delle foto».
- **13/10:** le candele di TradingView così come sono; le foto diventano le prove.
- **13-15/10:** Nameless su Kaggle (fasi 0-3). La fase 3 dice −0,08 R a operazione prendendoli tutti.
- **20/10:** forex solo col DXY, crypto solo con la TOTAL, 10 mercati, pareggio solo al TP1.
- **22-23/10:** le correzioni:
  - il DXY sugli orari suoi, il key level della guida, lo stesso movimento;
  - metalli coi loro CRT, niente veto;
  - gli orari del DXY;
  - il target oltre il TP1;
  - il Rischio da zero;
  - il lotto minimo.
- **24/10:** l'audit di Venice e la misura delle regole di oggi.
