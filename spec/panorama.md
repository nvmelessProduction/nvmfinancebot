# Scheda: Allineamento e Gap

> **Stato:** in uso dal 25/09/2026. Codice in `nvm/agenti/panorama.py`
> (cosa vedono), `nvm/agenti/inventate.py` (le loro domande), scheda
> dell'équipe in `nvm/vivo/messaggi.py`.

## Perché

L'utente, 25/09/2026: *"bisogna anche insegnargli l'allineamento dei
timeframe e i gap, magari creando anche un nuovo agente"*. Gli altri agenti
guardano il CRT e il timeframe subito sopra; nessuno guardava tutti i
timeframe grandi insieme, né i buchi lasciati dal prezzo.

## Cosa vedono **[D]**

- **Allineamento.** Su ognuno dei quattro timeframe grandi (4 ore, giorno,
  settimana, mese) il bias di Romeo sulle ultime due candele chiuse (msg
  5754, lo stesso foglio del Bias): a favore, contro o neutro. E su quanti
  livelli più grandi c'è un CRT armato nello stesso verso (il Cacciatore
  dice solo se ce n'è almeno uno).
- **Gap.** I fair value gap di un timeframe: tre candele, con il minimo
  della terza sopra il massimo della prima (o il contrario). Un gap resta
  aperto finché il prezzo non torna a riempirlo tutto. E il gap di apertura
  della settimana: dove ha chiuso venerdì e dove ha riaperto, finché il
  prezzo non torna al prezzo di venerdì; conta solo se è almeno una
  frazione dell'ampiezza media dei 20 giorni prima.

Tutto si guarda con le sole candele chiuse prima dello scatto.

## Come imparano **[D]**

Come gli altri, senza regole fisse: hanno i loro mattoni e ne fanno
domande sì/no, che la palestra prova sui vent'anni con lo stesso esame
(`spec/allenamento.md`). Una domanda entra nel Capo solo se migliora le
prestazioni.

| Agente | Mattoni |
|---|---|
| Allineamento | almeno N timeframe (dal 4 ore o dal giorno in su) a favore o contro; due timeframe insieme a favore o contro; CRT più grandi armati su 2 o 3 livelli |
| Gap | un FVG aperto (ora, 4 ore, giorno, settimana; nelle ultime 20, 50 o 100 candele) fra l'ingresso e l'altro lato del CRT, o alle spalle alla stessa distanza; qualunque, nel verso dell'operazione o contro; il gap del weekend ancora aperto, da chiudere a favore o contro (0,05 … 0,5 del giorno medio) |

Un agente nuovo prova prima le domande del suo mestiere (`inventate.PRIME`,
sei a testa), poi ogni settimana ne inventa due a caso come gli altri.

## In équipe

Nella scheda 🧠 di ogni decisione ognuno dice cosa vede: quali timeframe
sono a favore e quali contro, il FVG aperto più vicino verso l'obiettivo, il
gap del weekend. Finché la palestra non gli tiene una domanda, aggiunge
"sto imparando: il Capo non mi ascolta ancora".
