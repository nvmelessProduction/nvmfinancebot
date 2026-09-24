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
| Grilletto | secondo o terzo colpo sullo stesso CRT |
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
