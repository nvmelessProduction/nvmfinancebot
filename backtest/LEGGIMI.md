# Backtest

Ripercorre l'archivio barra per barra e chiede a `core.motore.valuta()` cosa
farebbe. Non è un simulatore parallelo: se il motore non opererebbe, qui non
si opera. I risultati dell'ultima esecuzione stanno in
`docs/BACKTEST-2026-09-15.md`.

## Come si usa

```
python scarica_storico.py --orari          # semina l'archivio (una volta)
cd backtest
DB_PATH=../dati/bot.db python raccogli.py  # la scansione, lenta: ~1 ora
DB_PATH=../dati/bot.db python rapporto.py  # le tabelle, veloce
```

La scansione si fa una volta sola e scrive `segnali.pickle`. `GEST-01` viene
disattivato lì dentro di proposito: è un filtro sull'ultimo numero calcolato,
quindi scartare dopo dà gli stessi segnali di una scansione con la soglia
attiva, più quelli che servono a misurare cosa cambierebbe abbassandola.

## I file

| File | Cosa fa |
|---|---|
| `archivio.py` | carica lo storico dall'archivio e costruisce i timeframe derivati |
| `scansione.py` | cammina sulle chiusure di candela e raccoglie le decisioni |
| `fasi.py` | ricostruisce il modello a fasi di `DEF-43` dalle barre orarie |
| `esiti.py` | dal segnale all'esito: stop, TP1, break even o target |
| `raccogli.py` | la scansione completa sui sei strumenti |
| `rapporto.py` | le tabelle: imbuto, esiti, sensibilità a `RR_MINIMO` |
| `costi.py` | spread, commissioni e size minima del broker |
| `placebo.py` | il CRT contro entrate a caso con la stessa geometria |

## Il test che conta più di tutti

`placebo.py` non misura la strategia: misura se la strategia dice qualcosa.
Confronta ogni segnale con venti entrate **a caso** nello stesso strumento,
stesso periodo, stessa direzione e — soprattutto — stesse distanze relative
di stop e bersaglio. Se i due tassi di successo coincidono, il pattern non
aggiunge informazione e tutto quello che si stava misurando era la forma del
bersaglio.

Va rifatto per primo ogni volta che si cambia la regola d'ingresso. Ottimizzare
un segnale che non batte il caso produce backtest belli e conti vuoti.

## Le approssimazioni, tutte in un posto

Nessuna è nascosta nel codice: ognuna è scritta nella docstring della
funzione che la introduce, e sono elencate insieme in
`docs/BACKTEST-2026-09-15.md` §1.

La più importante: **dentro una barra non si sa in che ordine il prezzo sia
passato**. Quando una barra tocca sia lo stop sia TP1 vince lo stop, come in
`sentinella.livello_toccato`. È la lettura peggiore delle due, ed è una
scelta: su cinque operazioni su cinquanta cambia il segno del risultato.
