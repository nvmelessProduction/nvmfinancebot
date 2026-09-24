# Schede: le prime conferme (key level, orario, bias)

> **Stato:** regole decise sulle fonti il 24/09/2026. Le conferme non
> bloccano niente da sole. Ognuna dice sì, no o non so, con un numero, e il
> Capo impara quanto fidarsi (`PIANO.md` §1). Nella Fase E ognuna si misura
> contro la base; la decisione si prende nella Fase F.
>
> Segni: **[R]** Romeo, **[S]** studenti, **[D]** deciso qui.

---

## 1. Key level

### La domanda

La manipolazione del CRT è entrata in una zona del timeframe più alto?

### Perché

*"All of this only matters if it occurs at a key level"*: è la nota in fondo
al suo foglio "Determining HTF bias for next candle" (msg 5754) **[R]**. E
ancora: *"Manipulation time + Key Level + pre-m. Liquidity pool = turtle
soup"* (msg 3871), *"1- plan the key level (Htf pd array). 2- plan the draw
on liquidity. 3- execute"* (msg 3331). E nel 2026, dal suo manuale: *"1.
Plan the higher timeframe key level. 2. Mark the manipulation time. 3. Mark
a pre-manipulation swing high/low. 4. 2 & 1 are more important than 3"*
(msg 6718).

### Da quale timeframe **[S]**

Quello sopra il range: CRT su 4 ore → key level giornalieri, giornaliero →
settimanali, settimanale → mensili. Per il CRT mensile, i mesi precedenti
**[D]**.

### Cosa conta come key level (short; il long è lo specchio)

Solo candele del timeframe alto già **chiuse** prima della manipolazione.
Si guardano le ultime 24 **[D]**.

| Tipo | Definizione | Fonte |
|---|---|---|
| **Massimo** | un massimo di swing (più alto delle due candele prima e delle due dopo) non ancora superato. La manipolazione lo supera | **[R]** "I don't trade orderblocks and fvgs as confidently as I trade highs and lows" (msg 1313); "you want to find pd arrays created at highs and lows" (msg 1329) |
| **Rejection block** | l'ombra superiore di un massimo di swing, cioè la zona fra il corpo e il massimo. La manipolazione ci entra | **[R]** "rejection blocks can be turtle souped, not just the wicks" (msg 175); "the key level: 4 hour rejection block" (msg 3834) |
| **FVG ribassista** | tre candele in cui il massimo della terza sta sotto il minimo della prima: la zona fra i due, non ancora riempita del tutto. La manipolazione ci entra | **[R]** "Model #2: HTF FVG = LTF turtle soup" (msg 4841) |
| **Arriva al massimo** | la manipolazione finisce vicino a un massimo di swing non ancora preso: entro il 10% dell'ampiezza del CRT, sopra o sotto **[D]** | **[R]** il disegno del msg 6718: il prezzo supera il massimo prima della manipolazione e **arriva** alla linea del key level, poi crolla |

Il foglio del msg 6718 (febbraio 2026, dal suo manuale) dice di ignorare
FVG, order block e breaker, e di guardare il key level del timeframe alto,
l'ora della manipolazione e il massimo prima della manipolazione. L'FVG
resta nella misura perché nel 2024 lo usava (msg 4841, 4973), ma la sua
fonte più recente lo mette da parte.

Order block e breaker restano fuori dalla prima versione: le definizioni di
Romeo cambiano col contesto ("an orderblock can be any up-close candle
before the bearish impulse wave, or it can be the thick up-close candle
that dug into a previous high", msg 4206), e vanno scritte a parte.

### Cosa risponde

Sì o no per ciascun tipo, più quanti tipi insieme (da 0 a 3). L'estremo
della manipolazione è quello toccato fino allo scatto, non dopo **[D]**.
Un massimo o un vuoto già presi fra la loro candela e la manipolazione non
contano più **[D]**.

---

## 2. Orario

### La domanda

A che ora di New York è avvenuta la manipolazione, e a che ora è scattato il
Model#1?

### Perché

*"T symbolises Time and Turtle soup. Time is the heart and brain of these
charts"* (msg 6361) **[R]**; *"GCT: Golden candle time (9am-1pm NY time)"*
(terminologia, msg 6110) **[R]**; *"3 trades a day: 3-5am, 930, 1330"* (msg
772, 2023) **[R]**. Gli studenti aggiungono le candele a 4 ore dell'1, delle
5 e delle 9 di New York **[S]**.

### Cosa risponde

- l'ora di New York dello scatto e della manipolazione (un numero da 0 a
  23);
- sì o no: lo scatto cade nella Golden candle time, 9:00–13:00 di New York.

Il Capo impara quali ore contano, invece di decidere a priori le finestre.

---

## 3. Bias

### La domanda

Il bias della candela alta va nel verso del CRT, contro, o non c'è?

### Perché

Il foglio "Determining HTF bias for next candle" (msg 5754) **[R]**:

1. chiusura sopra = prezzi più alti;
2. chiusura sotto = prezzi più bassi;
3. ombra sopra = prezzi più bassi;
4. ombra sotto = prezzi più alti.

*"Use for HTF bias mainly, & secondly for stop loss / stop run trading
setups."* E *"1- Frame a HTF bias (CRT) 2- Look for a LTF entry (Model#1)"*
(X, 05/04/2025).

### Come si legge **[D]**

Sempre rispetto alla candela prima: "chiusura sopra" è chiudere sopra il
suo massimo, "ombra sopra" è superare il suo massimo e richiudere sotto.
Il disegno dell'ombra sul foglio è una candela sola: questa è la lettura
più vicina al CRT, che è fatto proprio di massimi e minimi presi o no. Se
i segni si contraddicono (le due ombre insieme) o la candela resta dentro,
non c'è bias.

Si guarda su due livelli:

- **range:** la candela del range rispetto a quella prima. Dà il bias della
  candela 2, dove avviene la manipolazione;
- **sopra:** le ultime due candele chiuse del timeframe sopra (quello del
  key level), prima della manipolazione.

### Cosa risponde

Per ciascun livello: a favore, contro, o niente.

---

## Le misure (Fase E)

In `registro/tentativi.md`, con il numero di candidati provati: ogni
risposta confrontata è un candidato, e alza l'asticella del cancello
(`PIANO.md` §2, punto 5).

## Le risposte alla Romeo (24/09/2026) **[D]**

Scritte dopo che la regola "il metro è Romeo" (`PIANO.md`) ha mostrato che
le risposte di prima non distinguono le sue entrate dalle altre del bot
(`registro/tentativi.md`, 24/09). Sono quattro domande in più, ognuna presa
da una sua frase o dal modo in cui entra nel periodo di studio (2023). Come
le altre conferme non decidono niente da sole: le pesa il Capo.

| Agente | Domanda | Risposta | Fonte |
|---|---|---|---|
| Orario | La candela dello scatto cade nell'ora di Londra di Romeo? | sì se tocca l'1–5 di New York | msg 772 *"3-5am"*; le sue entrate del 2023 alle 1:40 e fra le 3 e le 5 |
| Orario | La candela dello scatto cade nell'ora di New York di Romeo? | sì se tocca l'8–11 di New York | msg 772 *"930"*, msg 4072 *"09:00 am"*; le sue entrate del 2023 alle 8:50, 9:36, 10:42 |
| Cacciatore | Il CRT sta dentro uno più grande, nello stesso verso? | sì se, all'istante dello scatto, un CRT di una coppia con il range più grande è armato nello stesso verso | msg 5121 *"There is always a micro CRT within the macro CRT"* |
| Bias | Si compra a sconto e si vende a premio? | per un long, l'ingresso è nella metà bassa della settimana chiusa prima; per uno short, nella metà alta. "Non so" se la settimana manca | msg 1067 *"Range lows are for buying… range highs are for selling"*; msg 3691, *premium/discount* |

Le ore toccate sono quelle di New York coperte dalla candela dello scatto:
una candela di un'ora o di un quarto d'ora ne tocca una, una di quattro
ore quattro, una giornaliera tutte. L'ordine delle coppie per "più grande"
è quello del range: mensile, settimanale, giornaliero, 4 ore.

## La liquidità presa: la terza gamba (25/09/2026) **[D]**

### La domanda

La manipolazione ha preso la liquidità lasciata prima di lei? La chiede il
**Grilletto**, che guarda il timeframe basso.

### Perché

È la terza gamba del suo sgabello *"Elements of a high probability trade
setup"*: *manipulation time*, *higher timeframe key level* e
*pre-manipulation liquidity pool* (msg 3860, 2023). Nel manuale del 2026:
*"3. Mark a pre-manipulation swing high/low"* (msg 6718), e nel disegno il
prezzo supera il massimo lasciato prima della manipolazione, arriva al key
level e crolla **[R]**. Le altre due gambe hanno già un agente (Orario e Key
level); questa non l'aveva nessuno.

### Cosa conta (short; il long è lo specchio)

Sulle candele del Grilletto, dall'inizio del range fino alla candela del
turtle soup esclusa:

| Risposta | Definizione |
|---|---|
| **Liquidità presa prima** | c'è un massimo di swing (più alto delle due candele prima e delle due dopo, tutte prima del turtle soup) che nessuna candela ha superato fino al turtle soup, e l'estremo della manipolazione, noto allo scatto, lo supera |
| **Liquidità ripresa fuori dal CRT** | come sopra, e quel massimo sta sopra il CRT high: il prezzo era già uscito dal range, è tornato giù, e la manipolazione torna a prenderlo |

### Cosa si è misurato (`registro/tentativi.md`, 25/09/2026)

- Fra i candidati del 2023, le scelte di Romeo hanno la liquidità presa nel
  44% dei casi contro il 27% degli altri; ripresa fuori dal CRT nel 33%
  contro l'11%.
- Sui 49.806 casi 2006-2023, con la liquidità presa il primo target arriva
  il 46% delle volte contro il 32%; l'R medio resta simile, perché quel
  primo target è più vicino.
- Il Capo, anno per anno, la impara come uno dei pesi più forti sul primo
  target. La somiglianza a Romeo, fuori campione per trimestre, le
  riconosce a 0,62 invece di 0,60.

Provate insieme e lasciate fuori, perché cambiavano poco o niente:
l'estremo del giorno, della settimana e del mese prima presi, la sessione
asiatica presa, l'ingresso sopra l'apertura del giorno o della settimana.
