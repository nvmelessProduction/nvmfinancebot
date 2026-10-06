# Il metodo delle foto del proprietario (06/10/2026)

Il proprietario ha mandato 23 esempi suoi (foto di TradingView, cartelle `1` … `7` e `casi/CASO-009.md`,
riassunte in `casi/ESEMPI-PROPRIETARIO.md`) e alle domande ha risposto così:

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
    sullo stesso strumento: una per CRT.

Dove i video e le foto dicono cose diverse vincono le foto (risposta 1). Il metodo dei video resta nel
codice (`spec/metodo_romeo.md`, `giro.METODO = "candela 3"`) ma il bot usa questo.

## Le regole e dove stanno

| Regola | Da dove | Codice |
| --- | --- | --- |
| Candele come sui future: il giorno alle 18 di New York (mezzanotte italiana), 4 ore alle 18-22-2-6-10-14, 6 e 12 ore, 3-6-12 mesi; l'ora della domenica prima delle 18 va nella prima candela | risposta 2; foto 5/5, 5/7, 5/8: CRT solo con queste candele | `nvm/tempo.py` |
| CRT sui timeframe 1 ora, 4 ore, 6 ore, giorno, settimana, mese | le foto | `foto.TF_CRT` |
| La candela 2 prende il massimo (minimo) del range e chiude dentro, senza toccare l'altro lato e senza sforare (la chiusura sul lato conta dentro, un filo oltre no) | tutte; il proprietario, 07/10/2026: *"non deve sforare"* | `foto.trova`, `TOLLERANZA_CHIUSURA` |
| Il range è la candela madre se la candela 1 è una inside bar (e così via) | risposta 5, foto 2/7 | `foto._madre` |
| Entrata all'apertura della candela 3, a qualunque ora | risposte 1 e 10; tutte le foto | `foto.trova`, `giro.occasioni_foto` |
| Stop oltre l'estremo della candela 2 | tutte le foto | `foto.trova` |
| TP1 = l'altro lato del range, metà chiusa e stop a pareggio; una posizione sola, la metà la chiude il bot (se il lotto non si divide, solo il pareggio) | risposte 4 e 12; tutte le foto ("TP1 PARZ + BE") | `foto.trova`, `giro.piani_foto`, `esecutore.Esecutore` |
| Key level = massimo o minimo del periodo prima (giorno, settimana, mese, 3 mesi, anno), almeno giornaliero e almeno grande come il CRT, preso dal CRT (candela 1 o 2) o dalla candela appena prima; per 4, 6 e 12 ore anche il massimo (minimo) di oggi fatto prima del range | tutte le foto ("KL preso: DH, WH, ML, max annuale…"); foto 3/4 ("per l'entry H4 come KL ho usato il DH") | `foto.key_level_presi` |
| Il CRT a 1 ora vale solo se prende il key level del giorno e il massimo (minimo) dell'ultima candela a 4 ore | risposta 9, foto 4/6 | `foto._h4_preso`, `giro.setup_buono` |
| Target finale: il gap ancora intatto del timeframe sopra il CRT (al massimo 1-2 anni di età: 120 giorni, 52 settimane, 24 mesi, 8 trimestri, 6 semestri, 6 anni), oltre il TP1; se davanti c'è un gap già toccato che ha appena reagito contro di noi, l'estremo della sua aggressione (la liquidazione); il più vicino dei due | risposta 4; cartella 2; foto 3/4, 4/1, 4/6 | `foto.obiettivo_finale`, `gap_target`, `liquidazione` |
| Senza gap: il key level, l'altro lato del periodo più grande di cui la finta ha preso la liquidità (presa del ML → MH; presa del DH → DL); l'anno solo per i CRT della settimana e del mese. Senza neanche quello, tutto al TP1 | risposta 4; cartella 3 | `foto.kl_target` |
| Direzione: almeno un timeframe sopra il CRT (giorno, settimana, mese, 3, 6, 12 mesi) dalla nostra parte, o un gap da riempire nel nostro verso (ritracciamento), o una liquidazione in corso | risposta 6; le foto ("bias comando") | `foto.direzione`, `foto.bias_candela` |
| La direzione di una candela: chiude oltre la candela prima = accetta; prende un lato e chiude dentro = non accetta, va dall'altra parte; inside bar = non accetta, resta la direzione di prima; prende tutti e due i lati = nessuna | risposta 6; Romeo V1 35:12 | `foto.bias_candela` |
| Le fasi del gap, lette due timeframe sotto il gap (3 mesi sul giornaliero, settimana sul 4 ore, giorno sull'orario): aggressione, reazione automatica (prima chiusura oltre il massimo della candela del minimo), liquidazione (preso il minimo dell'aggressione), continuazione (più la divergenza RSI 14) | risposte 7 e 8; foto 4/1 (il minimo dei 3 mesi è quello di giugno) | `foto.fase`, `foto.rsi` |
| DXY sintetico dalle coppie (formula ICE, la corona svedese ferma a 10); un suo setup vale per EURUSD, GBPUSD, AUDUSD, NZDUSD, XAUUSD, XAGUSD (verso opposto) e USDJPY, USDCHF, USDCAD (stesso verso), con stop e TP1 della coppia | risposta 8, foto 2/6 | `foto.dxy`, `foto.dal_dxy`, `giro.occasioni_foto` |
| Timeframe allineati (una confluenza): un altro timeframe con un CRT nello stesso verso | tutte le foto ("TF allineati") | `foto.allineati` |
| Un'occasione per apertura e verso (il timeframe più grande) | lo stesso movimento su 1, 4 e 6 ore è la stessa idea | `giro.occasioni_foto` |
| Più operazioni sullo stesso strumento: le decide il Rischio, che punta meno se lo strumento ha già un'operazione aperta e impara quanto | il proprietario, 07/10/2026: *"lo gestisce l'agente rischio. decisione sua"* | `squadra._rischio` |

Le domande obbligatorie (`metodo.valuta_foto`): **CRT**, **key level**, **direzione**. Le altre sono
confluenze: timeframe allineati, inside bar, key level grande, dentro un gap a favore, continuazione col RSI,
target sul gap, DXY a favore. La squadra (`squadra.py`, memoria `foto-1`) impara dal vivo quanto conta
ognuna; gli agenti nuovi sono **Gap** e **DXY**.

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
