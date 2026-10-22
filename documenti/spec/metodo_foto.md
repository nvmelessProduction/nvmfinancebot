# Il metodo delle foto del proprietario (06/10/2026)

Il proprietario ha mandato 23 esempi suoi (foto di TradingView, cartelle `1` … `7` in `documenti/casi/foto/` e `documenti/casi/CASO-009.md`,
riassunte in `documenti/casi/ESEMPI-PROPRIETARIO.md`) e alle domande ha risposto così:

1. video o esempi? *"come nelle foto"*;
2. le candele *"devono partire come sul futures"*;
3. la candela 2 *"non deve sforare. potrebbe essere un errore mio, ho dato per scontato che non avesse
   accettato"* (07/10/2026);
4. *"il kl è sempre il tp1+be come nelle foto e il gap il target finale, ovvio che se non c'è gap il target è
   il kl"*;
5. *"4664.3 ... è il range low h6, questa logica viene utilizzata nel momento in cui il prezzo o con la candela
   successiva fa inside bar o comunque fa il crt, e prendendo liq ... andiamo a puntare il minimo del range"*;
6. 3, 6 e 12 mesi sì; *"terza candela che non accetta significa che il prezzo o ha fatto inside bar (non ha
   creato né nuovo max né nuovo min) oppure ha preso semplicemente liq e non è riuscita ad accettare la candela
   precedente. ritracciamento intendo che la direzione principale a tf alto è es. long ma il prezzo deve
   tornare a ribasso per poi proseguire long"*;
7. le fasi del gap: *"aggressione è quando il prezzo entra nel gap per la prima volta con forza, automatic
   reaction è quando per la prima volta reagisce nella direzione del gap, liquidazione è quando il prezzo va
   a liquidare il minimo creato nella fase di aggressione, continuazione avviene quando le tre fasi
   precedenti sono complete e in più rsi ci conferma il setup (minimi decrescenti sul grafico e crescenti
   sull'rsi)"*;
8. *"rsi lo utilizziamo solo ed esclusivamente per i gap ... per la fase di continuazione"*; il DXY *"è un
   grafico fondamentale (se lui ci forma un setup long possiamo shortare tutte le coppie forex che hanno il
   dollaro al denominatore, e longare tutte quelle che hanno usd al numeratore)"*;
9. *"se il prezzo prende kl daily e sbilancia un max minimo h4 e si forma un crt h1 noi entriamo sulla terza
   candela h1 che equivale entrare sulla successiva candela h4"*;
10. *"non c'è limite di orario entra ad apertura candela"*;
11. la routine dei vent'anni *"a tua discrezione"*: spenta il 06/10/2026.
12. 07/10/2026: *"vorrei che apri una sola operazione. Quando arriva [al TP1], parzializza. Se si può
    parzializzare, altrimenti no. E continua fino al TP"*; lo stop dopo il parziale va a pareggio; più operazioni
    sullo stesso strumento: una per CRT. Dopo il primo giorno dal vivo (62 operazioni in 30 ore nella prova):
    **"Max 1 aperta per strumento"**.
13. 07/10/2026, tre esempi dal vivo (cartelle `eurjpy`, `euraud`, `chfjpy` in `documenti/casi/foto/`): *"attualmente il bot fa bene l'entry
    ... lo stoploss lo mette bene, il tp1 lo mette bene ma sbaglia la percentuale e deve prendere il 25%
    dell'operazione al posto del 50%"*; euro-yen: *"il tp finale non può essere il gap weekly visto che è già stato
    usato (quindi mitigato) per andare sell, quindi non essendoci gap il target è il kl cioè il DH"*, *"il gap è già
    stato mitigato quindi non può essere un target"*; euro-australiano: *"la terza candela accetta la precedente e
    quindi il target non è il gap bensì il kl quindi il dh"*, *"per quanto riguarda i gap invece devi guardare
    sempre la terza candela che crea il gap, si vale per ogni gap"*; franco-yen: *"tutto giusto ma la bias errata
    visto che la candela trimestrale ha accettato a ribasso quindi ci aspettiamo che il minimo trimestrale venga
    preso e solo dopo ha senso cercare buy"*, *"la candela giornaliera che devi guardare è sempre la precedente"*,
    *"il bot ogni giorno, settimana, mese deve rianalizzare la bias"*, *"anche 1 mese, tre mesi, dodici mesi"*;
    *"quelle tre valute ... erano esempi ... cose che ti ho spiegato valgono per tutto"*.

Dove i video e le foto dicono cose diverse vincono le foto (risposta 1). Il metodo dei video resta nel
codice (`documenti/spec/metodo_romeo.md`, `giro.METODO = "candela 3"`) ma il bot usa questo.

Correzioni operative concordate il 16/10/2026: il DXY arriva da TradingView CAPITALCOM:DXY; le coppie USD
usano il CRT locale solo come conferma del segnale DXY. BTC ed ETH seguono esclusivamente CRYPTOCAP:TOTAL.
Il target finale usa il key level del timeframe più basso preso, se disponibile. Il TP1 alla chiusura della
candela d'ingresso, deciso quel giorno, è tolto il 20/10/2026: il pareggio si mette solo al TP1 (riga sotto).

## Le regole e dove stanno

| Regola | Da dove | Codice |
| --- | --- | --- |
| Candele come su MT5 (dall'08/10/2026): il giorno alle 17 di New York (le 23 italiane), 4 ore alle 23-3-7-11-15-19 italiane, 6 e 12 ore, 3-6-12 mesi. I metalli (oro, argento) dal 13/10/2026 con le candele del future, dalle 18 di New York (4 ore alle 24-4-8-12-16-20 italiane): così tornano i CRT a 4 ore dell'oro delle foto 4/5, 5/5, 5/7 e 5/8 | il proprietario, 08/10/2026: *"mi adatti immediatamente l'orario"* (CRT 4 ore di SPX500); 13/10: le foto vanno fatte tutte | `nvm/tempo.py`, `candele.calendario` |
| **Sui grafici di TradingView le candele sono le sue, così come sono**: 1 ora, 4 ore, giorno, settimana e mese scaricati da TradingView (anche 6 e 12 ore, 3, 6 e 12 mesi se li dà; se no si mettono insieme le sue ore e i suoi mesi, sulla sua griglia). L'orario di ogni grafico si legge dalle sue candele a 4 ore (i grafici del proprietario: 0, 4, 8, 12, 16, 20 italiane) e vale per tutto, bot e rete. Il bot le tiene su disco e riprende ogni timeframe quando ne chiude una candela | il proprietario, 13/10/2026: un CRT a 4 ore di EURUSD aperto con gli orari di MT5 che su TradingView non era finito; *"non deve costruire niente ma utilizzare i dati con gli orari che gli vengono forniti così come sono"*; *"1h 4h 6h 12h 1d 1w 1m 3m 12m"* | `tradingview.candele_tv`, `ora_di_sessione`, `vivo.Bot._candele_tradingview`, `foto.Quadro.da` |
| Le crypto con gli orari crypto: il giorno a mezzanotte UTC (le 2 italiane d'estate), 4 ore alle 2-6-10-14, 6 ore alle 2-8-14-20, 12 ore alle 2 e alle 14, settimana da lunedì | il proprietario, 08/10/2026 (BTC a 6 ore) | `nvm/tempo.py` |
| CRT sui timeframe 1 ora, 4 ore, 6 ore, giorno, settimana, mese | le foto | `foto.TF_CRT` |
| La candela 2 prende il massimo (minimo) del range e chiude dentro, senza toccare l'altro lato e senza sforare (la chiusura sul lato conta dentro, un filo oltre no) | tutte; il proprietario, 07/10/2026: *"non deve sforare"* | `foto.trova`, `TOLLERANZA_CHIUSURA` |
| Il range è la candela madre se la candela 1 è una inside bar (e così via) | risposta 5, foto 2/7 | `foto._madre` |
| Entrata all'apertura della candela 3, a qualunque ora | risposte 1 e 10; tutte le foto | `foto.trova`, `giro.occasioni_foto` |
| Stop oltre l'estremo della candela 2 | tutte le foto | `foto.trova` |
| TP1 = l'altro lato del range, a prezzo, cioè il CRT completato: quando il prezzo ci arriva il bot chiude il 25% (se il lotto si divide) e sposta lo stop a pareggio. Il pareggio non è il prezzo d'entrata preciso ma un poco in guadagno, quanto le commissioni d'apertura e di chiusura (quelle vere di MT5; se non le dà, quelle della tabella degli strumenti). Mai alla chiusura della candela d'ingresso: quella regola (16/10/2026) è tolta, anche per le posizioni aperte prima | il proprietario, 20/10/2026: *"levi assolutamente la funzione che alla chiusura della candela d'entrata il bot mette be. lo deve mettere solo al tp1"*; *"il be va messo nel momento in cui viene completato il crt nel tf in cui si è entrati"*; *"il be ... leggermente in guadagno per coprire i costi di commissione"*; regole delle foto per il 25% | `esecutore.Esecutore.sorveglia`, `esecutore.Esecutore.pareggio` |
| Key level = massimo o minimo del periodo prima (giorno, settimana, mese, 3 mesi, anno), almeno giornaliero e almeno grande come il CRT, preso dal CRT (candela 1 o 2) o dalla candela appena prima; per 4, 6 e 12 ore anche il massimo (minimo) di oggi fatto prima del range | tutte le foto ("KL preso: DH, WH, ML, max annuale…"); foto 3/4 ("per l'entry H4 come KL ho usato il DH") | `foto.key_level_presi` |
| Il CRT a 1 ora vale solo se prende il key level del giorno e il massimo (minimo) dell'ultima candela a 4 ore | risposta 9, foto 4/6 | `foto._h4_preso`, `giro.setup_buono` |
| Target finale: se sono stati presi key level di più timeframe, puntare direttamente al key level opposto del timeframe più basso preso (per esempio WH + DH → DL) e chiudere al suo raggiungimento. Sui setup nati dal DXY (dalla TOTAL), se la coppia non ha preso key level suoi conta lo sbilanciamento del DXY: il livello di quel periodo della coppia dalla parte dove va l'operazione (il DXY prende il DH, EURUSD compra: il DH di EURUSD). Se manca quel livello, valgono i fallback del metodo originale: gap valido, key level di liquidazione, key level del periodo più grande o altro lato del range. Se il target finale manca o non rende 1 R, tutto al TP1 (dal 16 al 21/10/2026 si saltava: il 21/10 il bot non è entrato sull'argento) | correzione concordata il 16/10/2026; il proprietario, 20/10/2026: *"il tp finale sullo sbilanciamento del kl ... il prezzo prende kl sbilanciamento dl si forma un crt h1 e il bot sul completamento del crt h1 deve mettere a be e targhettizzare il dh"*; risposte 4 e 13; esempi euro-yen ed euro-australiano | `foto.target_minimo`, `foto.obiettivo_finale` |
| Oltre un gap che ha accettato non si punta: il prezzo non ci torna presto, il target sta prima (euro-australiano: il DH, non il massimo dei 3 mesi oltre il gap). Oltre un gap già toccato che fa pressione contro (il "muro") nemmeno, tranne un gap di timeframe uguale o più grande che sta dentro il muro (foto 2/5: il gap annuale del DXY dentro quello dei 6 mesi; 2/8: il gap dei 3 mesi dell'argento dentro quello mensile); un gap più piccolo dentro il muro no (foto 3/4: *"il gap a ribasso ci serve solo a capire che ci potrebbe essere pressione long al suo interno"*) | foto 2/5, 2/8, 3/4; euro-australiano | `foto.muro_accettato`, `gap_target` |
| Senza gap: se il gap contro di noi è nella reazione automatica e l'estremo dell'aggressione è un key level, il target è quel key level (la liquidazione: foto 3/4 *"il target è il WL cioè un KL"*, 4/6 il WL oltre il DL, 4/1 il minimo dei 3 mesi); un estremo che non è un key level non è un target (euro-yen: *"il gap è già stato mitigato"*, il DH). Se no l'altro lato del periodo più grande di cui la finta ha preso la liquidità (presa del ML → MH; presa del DH → DL); l'anno solo per i CRT della settimana e del mese. Senza neanche quello, tutto al TP1 | risposta 4; cartelle 3 e 4; euro-yen | `foto.kl_liquidazione`, `foto.kl_target` |
| Il rendimento al target finale almeno 1 volta il rischio: sotto non si entra (i trade del demo a 0,9, 0,7 e 0,1 R). Il 12/10 il proprietario aveva detto *"1/1,5"*, ma la foto 2/8 sta a 1,1 R e la 3/1 a 1,4 R, e le foto si prendono tutte | 12/10 e 13/10/2026 | `foto.RR_MINIMO`, `giro.piani_foto` |
| Direzione: per giorno, settimana, 1, 3 e 12 mesi (sopra il CRT) si guarda la candela precedente. Se ha accettato dalla nostra parte e il prezzo non ha ancora preso il suo livello, è il comando. Blocca solo quella dei 3 o dei 12 mesi che ha accettato contro di noi, su un CRT a 1 ora che ha preso soltanto livelli del giorno (il franco-yen); il CASO-009 e la 5/8 (presi livelli della settimana) e le foto 2/1, 3/4, 4/1, 4/6 (contro il mensile) si prendono. Poi: almeno un timeframe sopra dalla nostra parte (quelli col livello già preso non contano più), un gap valido da riempire nel nostro verso (ritracciamento), o un gap contro nella reazione automatica (la fase dopo è la liquidazione, foto 4/1) | risposte 6 e 13; franco-yen; tutte le foto (13/10/2026) | `foto.direzione`, `foto.accettazione`, `foto.blocca` |
| La direzione di una candela: chiude oltre la candela prima = accetta; prende un lato e chiude dentro = non accetta, va dall'altra parte; inside bar = non accetta, resta la direzione di prima; prende tutti e due i lati = nessuna | risposta 6; Romeo V1 35:12 | `foto.bias_candela` |
| Le fasi del gap, lette due timeframe sotto il gap (3 mesi sul giornaliero, settimana sul 4 ore, giorno sull'orario): aggressione, reazione automatica (prima chiusura oltre il massimo della candela del minimo), liquidazione (preso il minimo dell'aggressione), continuazione (più la divergenza RSI 14) | risposte 7 e 8; foto 4/1 (il minimo dei 3 mesi è quello di giugno) | `foto.fase`, `foto.rsi` |
| DXY da TradingView CAPITALCOM:DXY. Le coppie col dollaro e i metalli (EURUSD, GBPUSD, NZDUSD, AUDUSD, USDCHF, USDCAD, XAUUSD, XAGUSD) entrano **solo ed esclusivamente** col pattern del DXY: un suo CRT (la candela 2 prende il massimo o il minimo del range e rientra; quello a 1 ora solo se prende anche il key level del giorno e il massimo o minimo a 4 ore). Non serve che il DXY prenda un key level giornaliero: il 21/10/2026 il CRT a 4 ore del DXY delle 12 non l'aveva, il proprietario è entrato sull'oro proprio col setup che ne nasce (ingresso, stop, TP1 e target uguali) e il bot, che il 20/10 lo chiedeva, no. Per ogni CRT del DXY il bot scrive sul canale operativo su quali strumenti nasce l'occasione e, dove no, perché. Anche per la squadra che decide: sugli strumenti guidati il key level obbligatorio è lo sbilanciamento del CRT del DXY (della TOTAL) e la direzione dello strumento è solo un parere (21/10/2026: la squadra scartava in silenzio BTC ed ETH dopo il CRT della TOTAL delle 22). Ogni occasione non aperta lo dice sul canale operativo, col perché. Anche la rete neurale: sui setup nati dal DXY (dalla TOTAL) le regole le dà il CRT della guida e la rete non li lascia (la sua stima resta scritta); il 22/10/2026, sui prezzi del 21/10 alle 12, lasciava 7 setup su 8, oro compreso, e li mandava in équipe con «Apri lo stesso». La previsione della settimana che può dire no è quella della guida: il DXY per le coppie col dollaro e i metalli, la TOTAL per BTC ed ETH. Il Capo prende al massimo 3 occasioni per giro (`al_lavoro.MASSIMO_PER_GIRO`): quando il DXY fa il CRT nascono fino a 8 occasioni insieme. I loro CRT non fanno mai entrare, neanche come conferma (la regola del 16/10 chiedeva anche il CRT della coppia: tolta). DXY long: short sulle coppie col dollaro sotto e sui metalli, long su USDCHF e USDCAD. Stop oltre la candela 2 della coppia, TP1 l'altro lato del suo range | il proprietario, 20/10/2026: il bot era entrato short su GBPUSD per un CRT 4 ore suo; *"il bot si deve basare solo ed esclusivamente solo sul dxy ... solo ed esclusivamente quando il dxy da il pattern quindi il crt con i vari sbilanciamenti"*; risposta 8, foto 2/6 | `foto.GUIDATI_DAL_DXY`, `foto.dal_dxy`, `giro.occasioni_foto` |
| BTC ed ETH: entrano solo col pattern della TOTAL (CRYPTOCAP:TOTAL), un suo CRT come per il DXY, nello stesso verso; i loro CRT non fanno mai entrare. Senza la TOTAL, nessun ingresso crypto | il proprietario, 16 e 20/10/2026: *"per entrare buy o sell su btc o eth dovevi analizzare il grafico total"* | `vivo.TOTAL_TRADINGVIEW`, `foto.dal_totale`, `giro.occasioni_foto` |
| Mercati del bot dal vivo: EURUSD, GBPUSD, NZDUSD, AUDUSD, XAUUSD, XAGUSD, USDCHF, USDCAD, BTCUSD, ETHUSD; il DXY e la TOTAL come guida. Anche se il .env di TradingView ne ha altri, si guardano solo questi | il proprietario, 20/10/2026: *"leviamo le coppie inutili e lasciamo solo dxy, eurusd, gbpusd, nzdusd, audusd, xauusd, xagusd, aggiungiamo xptusd, usdchf usdcad poi total, btcusd, ethusd"*; poco dopo: *"togli xpt"* | `vivo.STRUMENTI_VIVO`, `vivo.GRAFICI_PREDEFINITI` |
| Timeframe allineati (una confluenza): un altro timeframe con un CRT nello stesso verso | tutte le foto ("TF allineati") | `foto.allineati` |
| Un'occasione per apertura e verso (il timeframe più grande) | lo stesso movimento su 1, 4 e 6 ore è la stessa idea | `giro.occasioni_foto` |
| Al massimo un'operazione aperta per strumento: le altre occasioni su quello strumento si seguono sulla carta | il proprietario, 07/10/2026 (prima *"lo gestisce l'agente rischio"*, poi, visto il numero di operazioni, *"Max 1 aperta per strumento"*) | `vivo.Bot._decidi` |
| La rete neurale entra sempre su un setup con tutte le regole (CRT, key level, direzione): la sua stima la scrive, ma lì non decide lei. Provata foto per foto, da sola ne lasciava 19 su 22 | il proprietario, 13/10/2026: *"quelli sono i trade che il bot e la rete neurale devono fare. Sono esattamente quelli"* | `rete_vivo.Giudizio.regole` |

Le domande obbligatorie (`metodo.valuta_foto`): **CRT**, **key level**, **direzione**. Le altre sono
confluenze: timeframe allineati, inside bar, key level grande, dentro un gap a favore, continuazione col RSI,
target sul gap, DXY a favore. La squadra (`squadra.py`, memoria `foto-1`) impara dal vivo quanto conta
ognuna; gli agenti nuovi sono **Gap** e **DXY**.

## La verifica foto per foto (13/10/2026)

`python -m strumenti.foto --dati <cartella di HistData>`: le 24 foto (cartelle 2-5, CASO-009 e i tre trade del bot
del 07/10 con le correzioni del proprietario) passano tutta la catena del bot dal vivo: CRT, key level, direzione,
target, piano, regole della squadra e rete. **24 su 24**: si entra nelle 22 da prendere col target della foto (entro la
differenza fra future e spot) e si lasciano la 5/6 (la candela 2 sfora) e il franco-yen (la bias). Manca il Bitcoin
(2/4): non abbiamo i suoi dati. `tests/test_foto.py` rifà le 14 che stanno nei dati di Dukascopy.

## La verifica sugli esempi (06/10/2026)

Sui dati spot di Dukascopy (`tests/test_foto.py`, in fondo): nei 17 esempi che si possono controllare il bot
trova il setup, il key level e la direzione in tutti; il target finale coincide con quello del proprietario
in 13 (entro la differenza fra future e spot). I 4 che mancano sono l'oro di aprile-giugno 2026: nei nostri
dati manca marzo 2026, e il gap dei 3 mesi esce sbagliato. Il range madre della foto 2/7 torna preciso
(4656,3 sullo spot = 4664,3 sul future).

**Quante occasioni**: sul 2021-2023 (fuori dal periodo chiuso), su EURUSD e oro, circa 12 setup a settimana
per strumento (circa 3 se si tenesse un'operazione alla volta per strumento: lo decide il Rischio). Non sono
numeri di guadagno: il proprietario non vuole il fattore dei vent'anni nelle decisioni. La foto 6 della
cartella 5 (la candela 2 che chiude 0,1 sopra) col *"non deve sforare"* non è più un CRT.

## Da chiedere ancora

- Quanti strumenti: le foto usano euro, sterlina, oro, argento, DXY e Bitcoin; il bot ne guarda 40 (39 al
  broker). La lista completa del broker arriva su Telegram (`/strumenti`).
