# Il mese in corso non esiste come file orario

*17 settembre 2026*

## Il fatto

Dukascopy pubblica i file orari **un mese alla volta, a mese chiuso**.

```
EURUSD 2026-08 (chiuso)    HTTP 200,  6009 byte
EURUSD 2026-09 (in corso)  HTTP 404,   162 byte
EURUSD 2026-10 (futuro)    HTTP 404,  3464 byte
```

Il mese in corso risponde `404`, esattamente come un mese che non esistera'
mai. Non e' un file parziale che cresce: fino al primo del mese successivo,
quelle ore **non esistono** come file orario.

## Perche' e' grave

`H1`, `H4`, `D1`, `W1`, `M1` si costruiscono tutti dalle orarie. Senza il mese
in corso restano fermi all'ultimo giorno del mese scorso, per un tempo che
cresce di giorno in giorno fino a trentun giorni.

E' dove vive il range del CRT. La coppia col risultato migliore misurato e'
`4h -> 15m`: il `4h` sarebbe congelato mentre il `15m`, che viene dai minuti,
continuerebbe ad aggiornarsi. Il motore cercherebbe l'ingresso di oggi dentro
un range di tre settimane fa.

Con la protezione di `archivio_vecchio` il bot si astiene invece di operarci,
il che e' meglio — ma vuol dire un bot fermo per quasi tutto il mese.

## Cosa avevo creduto invece

Che l'archivio della VPS si fermasse al 31 agosto per via dei `503`. I 503
c'erano davvero, ed erano colpa di un difetto mio. Ma non erano **questa**
causa, e la differenza conta: i 503 passano, questo no.

Il docstring di `orarie_recenti` diceva *"Dukascopy pubblica il mese corrente
man mano: l'ultima candela puo' essere di poche ore fa"*. L'avevo scritto io,
e non l'avevo mai verificato.

## La soluzione, e la misura che la giustifica

I file al **minuto** sono giornalieri e ci sono anche per oggi. Un'ora sono
sessanta minuti: l'informazione c'e' tutta.

Resta da mostrare che ricostruire non introduce differenze. Misurato su una
settimana di agosto 2026, `EURUSD`, confrontando le orarie ricostruite dai
minuti con quelle del file orario di Dukascopy:

| | |
|---|---:|
| ore confrontabili | 117 |
| **identiche in tutto** | **117 (100,0%)** |
| apertura uguale | 117 |
| massimo uguale | 117 |
| minimo uguale | 117 |
| chiusura uguale | 117 |
| scostamento peggiore sugli estremi | **0,0 punti** |

Era il risultato atteso — il massimo di un'ora e' il massimo dei suoi minuti —
ma fra il dato e il risultato ci sono due aggregazioni e un fuso orario, e
"atteso" non e' "verificato".

## Come funziona adesso

`core/duka_minuti.orarie_dai_minuti` ricostruisce le ore di un intervallo di
giorni. Il ciclo di mercato la usa per il mese in corso e continua a prendere
i mesi chiusi dal file orario, che e' un solo scaricamento invece di trenta.

Il mese in corso **non si chiede piu'** come file orario: sarebbe una
richiesta buttata a ogni giro, e la risposta sarebbe sempre 404.

Il giorno in corso si riscarica ogni volta; i giorni chiusi vengono dalla
cache su disco.

## Cosa resta da sapere

Il primo del mese, il file orario del mese appena chiuso potrebbe non essere
ancora pubblicato. Non produce un buco: durante quel mese il ciclo ne aveva
gia' archiviato le ore ricostruite dai minuti, e `salva_candele` non le
sovrascrive quando il file arrivera'. Le due versioni sono identiche, quindi
la differenza e' senza conseguenze — ma e' identica *perche' e' stato
misurato*, non perche' debba esserlo.
