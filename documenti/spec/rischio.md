# Scheda agente: Rischio

> **Stato:** scritta il 24/09/2026, quando l'utente ha deciso che il bot apre
> posizioni sul conto demo, che **decide il bot**, e che gli agenti si
> addestrano e si configurano ma **non si bloccano né si limitano**.

## La domanda

Quanto mettere su questa operazione?

## Come risponde

Dal Capo arrivano `p1` (primo target prima dello stop) e `q` (secondo target
dopo il primo); da Livelli RR1, RR2 e i costi in R. Gli esiti possibili sono
tre: lo stop (−1 R), il primo target e poi il pareggio, i due target.

Il Rischio sceglie la frazione del conto che, ripetuta tante volte, fa
crescere di più il conto (il **criterio di Kelly**: si massimizza la media
del logaritmo del conto dopo l'operazione). Nessun tetto fisso: la parte
del Kelly da usare (`parte`, in `nvm/vivo/rischio.json`) il Rischio la
impara dalle operazioni passate: se il Capo sopravvaluta le sue stime, se
ne fida meno.

## Il conto intero (dal 27/09/2026)

L'utente: *"impareranno mai che se aprono miliardi di operazioni il conto si
brucerà non appena ci sarà uno scivolone?"*. Un'operazione alla volta non lo
vede: il Rischio impara sul **conto intero** (`nvm/agenti/portafoglio.py`),
con tutte le operazioni che il Capo avrebbe preso nel 2008-2023 (ogni anno
allenato solo sugli anni prima), aperte insieme come sarebbero state, la
puntata decisa sul conto di quel momento.

Impara tre cose:

- **la fiducia minima** (`minimo`): sotto questo Kelly pieno l'operazione
  non prende soldi. Nei vent'anni la metà meno sicura delle operazioni del
  Capo ha perso (−0,028 R l'una), il quinto più sicuro ha guadagnato
  (+0,07/+0,10 R);
- **la parte del Kelly** (`parte`);
- **se guardare le operazioni legate** già aperte (EURUSD e GBPUSD comprati
  insieme scommettono tutte e due contro il dollaro): quanto vanno insieme
  lo misura dai vent'anni per quello che hanno in comune (`gambe`), e toglie
  alla puntata quello che rischiano le legate (il Kelly di più scommesse).
  Se conviene lo decidono i dati: finora **no** (vedi sotto).

Sceglie la combinazione che fa crescere di più il conto **nelle storie
sfortunate**: gli stessi mesi rimescolati a caso 500 volte (anche quelli
senza operazioni), il 10% peggiore. Una storia in cui il conto scende sotto
l'1% di quello di partenza è una **rovina** e vale meno infinito: così
puntate enormi su poche operazioni fortunate non convincono (la prima volta,
a storie per anni e senza rovina, il Rischio aveva scelto il Kelly intero su
40 operazioni, e il conto vero si azzerava).

**Nessun tetto al calo** (l'utente, 28/09/2026: *"il profilo di rischio deve
essere anche quello intelligente"*). Il Rischio accetta il calo che serve a
far crescere di più il conto, e lo dice. Sui vent'anni, con le operazioni del
Capo, sceglie fiducia minima 0,06 e parte 0,07 del Kelly: +16,6% l'anno ma
calo peggiore 59%, giornata peggiore −16%, fino al 36% del conto a rischio
insieme; nelle storie sfortunate +4,3% l'anno e calo 71%. Un tetto
(`scegli(..., calo=…)`) resta possibile per un prodotto destinato a clienti:
è una scelta commerciale, non del bot. Fino al 28/09 il tetto era il 20%
(parte 0,01, +3% l'anno, calo 11%).

Si riallena ogni settimana: in palestra (`capo.py --vivo`, con i vent'anni)
e il sabato dal vivo (`riunione`, con i vent'anni e le operazioni vere). Il
bot usa il più recente dei due (`rischio.json`, campo `quando`).

## Quello che decide il broker

- **Il lotto minimo.** Se la puntata è sotto il lotto minimo, si apre il
  lotto minimo solo quando fa comunque crescere il conto **con la fiducia
  nelle stime che il Rischio ha imparato**: col vantaggio ridotto a `parte`,
  la crescita ha il massimo a `parte` × Kelly e torna a zero al doppio. Oltre
  il doppio l'operazione non si apre e si conta nel riepilogo della sera.
  (Fino al 27/09/2026 il controllo usava le stime prese per buone: su un
  conto da 1.000 € una giornata di prova arrivava ad aprire il minimo col
  31% del conto a rischio, e a oltre metà del conto a rischio in tutto.)
  **Dal 23/10/2026 sui setup della squadra non vale più**: se la puntata sta
  sotto il lotto minimo si apre il minimo, sempre, e il messaggio d'apertura
  dice quanto rischia davvero (il proprietario, sull'oro lasciato con un
  conto da 900 €: *"Se ci sta una cosa valida, deve aprire"*;
  `Esecutore.apri(sempre_il_minimo=True)`).
- **Una posizione o due.** Se il volume non si divide in due metà, si
  sceglie fra "tutta al primo target" e "tutta al secondo, con lo stop a
  pareggio dopo il primo" quella che fa crescere di più il conto.
- **Il margine.** Se il broker rifiuta l'ordine, lo si scrive sul canale
  operativo.

## Cosa può imparare

Niente di suo: la puntata viene dalle stime del Capo. Quanto più il Capo si
riaddestra con i dati dal vivo, tanto più le puntate sono giuste.
