# Scheda agente: Grilletto (il Model#1)

> **Stato:** regole decise sulle fonti il 24/09/2026. La definizione del
> Model#1 viene da uno schema disegnato da Romeo nel suo canale Telegram
> ufficiale (msg 4836). Manca la prova sui casi.
>
> Segni: **[R]** l'ha detto o disegnato Romeo, **[S]** lo dicono i suoi
> studenti, **[D]** deciso qui, perché le fonti non lo dicono.

## La domanda

Il CRT è armato: sul timeframe basso è scattato il Model#1, cioè è il
momento di entrare?

## Cosa guarda

- I CRT armati dal Cacciatore: verso, `CRT high`, `CRT low`.
- Le candele **chiuse** del timeframe basso della coppia, sui prezzi BID.

Non guarda key level, orari o SMT: sono Conferme e Contesto.

## La regola del manuale (short; il long è lo specchio)

1. **Quando cerca** **[R]**. Solo mentre il CRT è armato. "Step 1: Know where
   price is going - CRT. Step 2: Entry pattern - model#1" (msg 5390).

2. **La candela del turtle soup** **[R]**. Una candela bassa **rialzista**
   (chiusura sopra l'apertura) con il massimo **sopra** `CRT high`: "Thick
   up-close candle that liquidated an old high (turtle soup) = Bearish
   orderblock" (msg 4836). Il massimo liquidato è il `CRT high`, perché "a
   turtle soup happens at the CRT high or low" (msg 5133).

   "Thick" Romeo non lo misura: nel manuale basta una candela rialzista **[D]**.
   Quanto debba essere spessa è il numero che il Grilletto può imparare.

3. **Il livello** **[R]**. È l'**apertura** di quella candela (la linea "-Ob"
   dello schema). Se più avanti un'altra candela rialzista fa un turtle soup
   sopra `CRT high`, il livello passa alla sua apertura **[D]**.

4. **Lo scatto** **[R]**. Una candela bassa **chiude sotto il livello**:
   "confirmed with close below". Conta il corpo, non l'ombra. Si entra alla
   chiusura di quella candela.

5. **Fino a tre tentativi** **[D]**, corretto dal CASO-004. Dopo uno stop il
   Grilletto può sparare ancora sullo stesso CRT, finché è armato, ma solo
   con un turtle soup **nuovo**. La candela che prende lo stop può essere lei
   stessa il turtle soup nuovo: è la spinta che spazza e poi crolla, il
   "kiss of death" di Romeo ("there's always one last turtle soup"). Nel
   CASO-004 l'operazione di Romeo è proprio il secondo Model#1.

## La variante dichiarata "un gradino sotto" **[D]**

Scritta il 24/09/2026, **prima** di misurarla, dopo che la prima prova del
Capo non è passata (`registro/tentativi.md`). È la **terza e ultima**
variante permessa dal piano (`PIANO.md`, Fase F): dopo questa non se ne
aggiungono altre.

**La regola.** Il Model#1 si cerca sul timeframe d'ingresso della coppia
di Romeo di un gradino più in basso, e da lì fa tutto il resto della
catena: il Cacciatore si arma sulla prima candela di quel timeframe oltre
il range, il Grilletto cerca lì turtle soup e scatto, e l'operazione si
simula su quelle candele.

| Coppia del manuale | Un gradino sotto |
|---|---|
| mensile → giornaliero | mensile → 4 ore |
| settimanale → 4 ore | settimanale → 1 ora |
| giornaliero → 1 ora | giornaliero → 15 minuti |

Range, candela 2 e 3, rottura, target e stop restano quelli del manuale:
cambia solo il timeframe su cui si guarda l'ingresso.

**Perché.** Nei casi verificati (CASO-004…008) Romeo entra più in alto del
bot e con stop di pochi pip, cioè su un timeframe più basso di quello della
coppia. Le fonti: "the secret is to look at how the lower timeframe reacts
at higher time frame pd arrays" (msg 689); "every HTF key level will give
you three LTF entries: 1- Turtle soup…" (msg 4973); "if you're a beginner,
stick to the higher timeframe… then play with the lower timeframes"
(msg 3826).

**Cosa ci si aspetta, scritto prima.** Ingresso più vicino all'estremo,
quindi stop più corto in prezzo, RR più alti, e meno operazioni vincenti.
Se il vantaggio di Romeo sta nel *come* si entra, la base con questa
variante deve andare meglio della base del manuale sulle stesse coppie.

**Come si misura.**

1. Prima la base, coppia per coppia, contro la base del manuale sulle
   stesse coppie e negli stessi anni (2006–2023). Mensile e settimanale si
   misurano con le ore; il giornaliero aspetta i minuti.
2. Poi il Capo, con quattro configurazioni nuove (le 1–4 di `spec/capo.md`
   con l'ingresso un gradino sotto). I tentativi della Fase F diventano
   **K = 8**: intervallo al 99,375%.

## Cosa risponde

- **Nessuno scatto**, oppure **scatto**: l'istante, il prezzo di chiusura
  della candela che ha rotto, il livello, e la candela del turtle soup che
  l'ha definito.

## Da passare agli altri agenti

| Cosa | Chi | Punto di partenza | Fonte |
|---|---|---|---|
| Stop | Livelli | appena oltre l'estremo del turtle soup, ma mai più vicino all'ingresso di un quarto del range (dal 25/09/2026) | **[R]** msg 163: "turtle soup high has to be the ceiling"; 04/02/2023: "Your stoploss is 25% of the range, if it hits it you're wrong". Sui vent'anni, col Capo, le scelte passano da −0,011 a +0,009 R e battono la base in tutti gli anni (`registro/tentativi.md`) **[D]** |
| Stop, **variante dichiarata "stop stretto"** | Livelli | oltre il livello del Model#1, più il 10% dell'escursione della candela del turtle soup | è quello che Romeo fa nelle operazioni pubblicate: stop di 1–5 pip su EURUSD e GBPUSD; sull'oro (CASO-004) stop 2474.00 contro 2474.47 del bot. La misura decide fra le due |
| Primo target | Livelli | `CRT 50%` | **[R]** "the 50% is almost always guaranteed" (msg 6561) |
| Target finale | Livelli | oltre il lato opposto del range di metà della sua ampiezza (fino al 25/09/2026: sul lato) | **[R]** "take profit at 50% and then CRTH/L"; ma i suoi target letti nel 2023 stanno oltre il lato, fra 1,2 e 1,8 volte il range. Sui vent'anni, col Capo, le scelte passano da −0,022 a −0,011 R (`registro/tentativi.md`, 25/09/2026) **[D]** |
| Ingresso già oltre il 50% | Livelli | niente operazione: il primo target starebbe alle spalle | **[D]**, nel vecchio bot "12 posizioni su 17 morte in 6 secondi" |
| Quanto dura l'operazione | Livelli | **nessuna uscita a tempo**: stop, target, o pareggio dopo il primo target. Solo un tetto di sicurezza largo per la simulazione (~10 candele alte) | Romeo non parla mai di uscite a tempo. Due casi hanno smentito le durate provate prima: nel mensile di EURUSD (msg 5623) il target 2 arriva nella candela 3, nel giornaliero di dicembre 2024 (msg 5730) nella candela 4 |
| Quanto si chiude al primo target | Sentinella | metà | **[R]** "CRT 50%, target 1 (partial)" (msg 5623); la quantità non la dice |
| Rientro sul livello (RTM1) | più avanti | "retrade to model#1": un secondo ingresso quando il prezzo torna sul livello | **[R]** terminologia, msg 6110 |

## Cosa può imparare

Lo spessore minimo della candela del turtle soup, in frazione del suo
intervallo (oggi: basta che sia rialzista). Si misura se migliora il
risultato delle operazioni, con il cancello del `PIANO.md` §2.

## Approvazione

- [x] Regole decise sulle fonti, su delega dell'utente, il 24/09/2026
- [ ] Prova sui casi presi dai grafici di Romeo
