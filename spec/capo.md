# Scheda: il Capo

> **Stato:** scritta il 24/09/2026, **prima** di vedere un solo risultato
> del Capo. Quello che è scritto qui non si cambia dopo aver visto i numeri:
> se si cambia, è un tentativo nuovo e va nel registro (`PIANO.md` §2,
> punto 5).

## La domanda

Tutto considerato, conviene entrare in questa operazione?

## Come risponde

Stima due probabilità, con due regressioni logistiche:

- `p1`: che il prezzo arrivi al primo target (il 50%) prima dello stop;
- `q`: che, arrivato al primo target, arrivi anche al secondo prima di
  tornare all'ingresso.

Con la metà chiusa al primo target e il resto a pareggio (`spec/grilletto.md`),
il guadagno atteso in R è

    E = p1 × (0,5 × RR1 + 0,5 × q × RR2) − (1 − p1) − costi

dove RR1 e RR2 sono le distanze dei due target in R, e i costi (spread e
commissione, in R) si conoscono prima di entrare. **Si entra solo se
E > 0.** È la regola del `PIANO.md` §1 (`p × RR − (1 − p) − costi > 0`),
scritta per un'operazione che chiude in due metà.

Una regressione logistica si legge: per ogni risposta degli agenti c'è un
peso, e si vede quanto il Capo si fida di ognuno.

## Cosa guarda **[D]**

Solo quello che si sa all'istante dello scatto, e solo risposte degli
agenti o numeri del piano, **mai lo strumento** (il Capo non deve imparare
"EURUSD va bene nel 2011"):

| Da chi | Cosa |
|---|---|
| Conferma key level | massimo preso, arriva al massimo, rejection block, FVG (0/1), e "non so" |
| Conferma orario | la fascia di 4 ore di New York dello scatto (17, 21, 1, 5, 9, 13), come 5 colonne 0/1 |
| Contesto: bias | candela del range a favore / contro; timeframe sopra a favore / contro |
| Grilletto | secondo o terzo colpo sullo stesso CRT; liquidità presa prima della manipolazione, e ripresa fuori dal CRT (dal 25/09/2026) |
| Cacciatore | la coppia di timeframe (settimanale → 4 ore, giornaliero → 1 ora) |
| Livelli | RR1, RR2, e lo stop in proporzione all'ampiezza del CRT |

Le colonne numeriche si standardizzano con media e deviazione del periodo
di allenamento, non di tutto lo storico.

## Come impara **[D]**

- Regressione logistica con penalità L2, peso 1 (fisso, non si sceglie
  guardando i risultati).
- **Anno per anno, senza guardare avanti.** Per giudicare l'anno Y il Capo
  si allena solo sulle operazioni **chiuse** prima del 1° gennaio di Y. Il
  primo anno giudicato è il 2008 (due anni di allenamento); l'ultimo il
  2023. Il 2024–2026 resta chiuso.

## Le configurazioni provate

Dichiarate qui, prima di guardare. Con K configurazioni il cancello chiede
l'intervallo al `1 − 5%/K`.

| # | Cacciatore | Livelli |
|---|---|---|
| 1 | manuale | stop all'estremo |
| 2 | manuale | stop stretto |
| 3 | chiusura dentro | stop all'estremo |
| 4 | chiusura dentro | stop stretto |

**K = 4**: intervallo al 98,75%.

## Il cancello della Fase F

Sugli anni 2008–2023, le operazioni scelte dal Capo contro tutte quelle
della base negli stessi anni (con le stesse regole di Cacciatore e Livelli
della configurazione 1):

1. almeno **300** operazioni scelte;
2. R medio almeno **+0,10** sopra la base;
3. intervallo al 98,75% della differenza sopra lo zero, a blocchi
   settimanali;
4. la differenza ha lo stesso segno in almeno l'**80%** degli anni;
5. regge con lo **spread × 1,5**: rifatto tutto con lo spread allargato, la
   differenza resta sopra lo zero.

Se nessuna configurazione passa, la Fase F non è chiusa: si scrive il
numero, e si torna agli agenti.

## Il Capo impara Romeo (24/09/2026) **[D]**

Scritto dopo il cambio del metro (`PIANO.md`, "il metro è Romeo").
**Decisione dell'utente, 24/09/2026:** *"addestrare però non significa
obbligarlo e imporgli delle cose"*. Il Capo e gli agenti imparano; nessuna
regola del bot li obbliga a fare come Romeo o limita quante operazioni
aprono. Il cancello del `PIANO.md` (7 su 10, al massimo 3 per ognuna) è il
metro con cui **noi** giudichiamo il bot, non una regola dentro il bot.

**La somiglianza a Romeo**, `r`: una regressione logistica che stima quanto
un'operazione somiglia a una che Romeo prenderebbe. È un **parere**:
l'équipe lo sente, il Capo lo riferisce, ma decide col guadagno atteso,
come prima.

- **Da dove impara.** Dal catalogo `casi/entrate-romeo.csv`, solo il
  periodo di studio (fino al 2023). I candidati sono tutte le operazioni
  del 2023 delle coppie del bot dal vivo (mensile → giornaliero,
  settimanale → 4 ore, giornaliero → 1 ora, e 4 ore → 15 minuti dove ci
  sono i minuti). Per ogni entrata di Romeo, il candidato dello stesso
  strumento e verso, con l'ingresso nella sua finestra e il prezzo più
  vicino al suo (`nvm/prova/romeo.confronta`), vale 1; tutti gli altri 0.
- **Cosa guarda.** Solo le quattro risposte alla Romeo e le due del
  Grilletto sulla liquidità presa (`spec/conferme.md`). Con tutte le
  colonne del Capo, provata fuori campione per trimestre, riconosceva le
  sue scelte come il caso (AUC 0,51); con le quattro risposte 0,59–0,60, con
  la liquidità 0,62 (`registro/tentativi.md`).
- **Penalità L2: 10**, scelta fra 1, 10 e 100 allenando su tre trimestri
  del 2023 e provando sul quarto.
- **Come arriva Romeo nelle decisioni: la fiducia in Romeo.** L'utente,
  24/09: *"voglio che il capo diventi il cervello di Romeo… nulla toglie
  che può migliorarsi da solo"*. Romeo è un membro dell'équipe: la sua voce
  sposta la stima del primo target del Capo di `fiducia × z`, dove `z` è
  quanto la somiglianza di questa operazione è sopra la media (sul
  logaritmo delle quote). **La fiducia non la sceglie nessuno**: il Capo la
  impara dai risultati, a parità di tutto il resto (una regressione con un
  solo peso, penalità 1), prima sui candidati del 2023 e poi, ogni sabato,
  anche su tutte le decisioni dal vivo. Se le operazioni alla Romeo vanno
  meglio, lo ascolta di più; se vanno peggio, di meno. Ha la sua pagella
  come gli altri.
- **Perché ha senso.** Fra i candidati del 2023, quelli che sono le scelte
  di Romeo hanno preso il primo target nel 63% dei casi contro il 36% (R
  medio +1,37 contro −0,06), e il Capo stimava 36% per tutti. Con un
  limite: Romeo pubblica soprattutto le operazioni riuscite, quindi il 63%
  è probabilmente alto. Il Capo ne tiene conto da solo, perché la fiducia
  la impara dai risultati e non da quel numero.
- **Come migliora.** Ogni sabato il Capo ripassa le entrate di Romeo e si
  riaddestra sui risultati della settimana. Quando il catalogo cresce o
  arrivano i minuti di un periodo nuovo, `python capo.py --vivo` rifà
  tutto e il bot si aggiorna da solo.
- **Come si giudica.** Sul periodo di studio solo fuori campione (tre
  trimestri per allenare, il quarto per provare); il giudizio vero è una
  volta sola sul 2024–2026, nella Fase G.

Una prima versione (24/09, sera) faceva entrare il Capo solo sopra una
soglia di somiglianza, calcolata per dare al massimo 3 operazioni per
ognuna di Romeo. Tolta lo stesso giorno per la decisione dell'utente: era
un obbligo, non un addestramento.
