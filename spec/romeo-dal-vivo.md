# Scheda: Romeo dal vivo

> **Stato:** in uso dal 25/09/2026. Codice in `nvm/vivo/romeo_vivo.py`,
> risposte in `nvm/vivo/messaggi.py`, riunione in `nvm/vivo/riunione.py`.

## Perché

Il bot ritrova le entrate di Romeo sul 4 ore, non quelle sul minuto: con i
soli prezzi non si ricostruiscono (`registro/tentativi.md`, 25/09/2026). Per
imparare a somigliargli servono più sue entrate, e le 62 del 2023 sono poche.
Le sue entrate nuove arrivano ogni settimana sul suo canale: l'utente le vede,
e il bot può impararle.

## Come si usa

Su uno dei due canali del bot (operativo o équipe):

    /romeo EURUSD compra 1.0765 stop 1.0760 target 1.0800

- strumento: EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY, XAUUSD (anche "oro");
- verso: compra, compro, buy, long / vende, vendo, sell, short;
- il primo numero è l'ingresso; `stop` (o `sl`) e `target` (o `tp`) sono
  facoltativi, ma senza stop la distanza si misura solo in pip;
- i decimali si possono scrivere con la virgola.

Il bot risponde sul canale équipe: la decisione sua più vicina nelle 24 ore
prima (stesso strumento, stesso verso), a quanti rischi di Romeo, se l'aveva
presa. Un comando che non si legge riceve la spiegazione di cosa manca.
Messaggi da chat che non sono i canali del bot non contano.

## Cosa ne fa il bot **[D]**

- **Non la copia mai.** Nessun ordine nasce da un /romeo: Romeo è il metro
  e un esempio (decisione dell'utente del 24/09/2026: addestrare non vuol
  dire obbligare).
- **Il sabato impara.** Le decisioni dal vivo da 24 ore prima della prima
  entrata mandata diventano candidati: per ogni entrata di Romeo, la
  decisione più vicina al suo prezzo vale 1, le altre 0, come per il 2023
  (`nvm/prova/romeo.etichette`). Si aggiungono ai candidati del 2023 e la
  somiglianza a Romeo si riaddestra su tutti.
- **Il metro, ogni sabato.** La riunione dice quante sue entrate il bot
  aveva visto, ritrovato entro metà del suo rischio e preso, e quante
  operazioni ha aperto per ognuna delle sue: i due numeri del cancello del
  `PIANO.md` (7 su 10, al massimo 3 per ognuna). Il secondo vale solo se
  l'utente le manda tutte.

## Limiti

- Le entrate che l'utente non manda restano fra gli "altri": se ne manda
  poche, la somiglianza impara meno, non peggio.
- L'ora conta solo per la finestra di 24 ore: il bot usa l'ora del
  messaggio, non quella scritta da Romeo.
- Il periodo sigillato (2024-2026, `casi/entrate-romeo.csv`) resta fuori:
  qui entrano solo le entrate nuove, dal 25/09/2026 in poi.

## Gli errori **[D]**

Quando l'utente vede una decisione sbagliata, lo dice al bot su uno dei suoi
canali: rispondendo alla scheda della decisione con `/errore` e il perché,
oppure scrivendo lo strumento, per esempio `/errore USDJPY comprato contro
una spinta forte` (la decisione più recente su quello strumento nelle
ultime 48 ore). Il bot la conserva, dice in équipe chi aveva spinto per
entrare e chi frenava, e il sabato, riaddestrando il Capo, le dà il doppio
del peso (`nvm/vivo/errori.py`). Le correzioni più profonde (manopole o
domande nuove) nascono dagli screenshot che l'utente manda a Claude.
