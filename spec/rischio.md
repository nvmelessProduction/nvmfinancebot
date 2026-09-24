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
del logaritmo del conto dopo l'operazione). Nessun tetto e nessuna
frazione di sicurezza: più il Capo è addestrato bene, più la puntata è
giusta.

## Quello che decide il broker

- **Il lotto minimo.** Se la puntata è sotto il lotto minimo, si apre il
  lotto minimo quando, con le stime del Capo, fa comunque crescere il conto
  (crescita attesa sopra zero).
- **Una posizione o due.** Se il volume non si divide in due metà, si
  sceglie fra "tutta al primo target" e "tutta al secondo, con lo stop a
  pareggio dopo il primo" quella che fa crescere di più il conto.
- **Il margine.** Se il broker rifiuta l'ordine, lo si scrive sul canale
  operativo.

## Cosa può imparare

Niente di suo: la puntata viene dalle stime del Capo. Quanto più il Capo si
riaddestra con i dati dal vivo, tanto più le puntate sono giuste.
