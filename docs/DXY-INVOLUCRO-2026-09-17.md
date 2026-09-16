# Quanto sbaglia il DXY costruito dalle candele orarie

*17 settembre 2026*

## La domanda

`SETUP-19` fa dipendere cinque coppie su sei dalla bias del dollar index.
Dukascopy non serve un DXY utilizzabile — `USDIDX` esiste ma e' inerte, volume
zero su ogni record e un solo valore ripetuto per l'intero mese, verificato su
2020, 2025 e 2026 — quindi l'indice va calcolato dai suoi sei costituenti.

La formula ICE da' un valore **esatto a un istante**. Una *candela* del DXY
richiede anche un massimo e un minimo, e li' l'esattezza si perde: il massimo
vero e' il massimo dell'indice durante l'ora, che non coincide col valore
dell'indice calcolato sugli estremi orari dei sei costituenti — perche' quei
sei estremi non avvengono tutti nello stesso momento.

Applicando a ogni coppia l'estremo che spinge l'indice verso l'alto si ottiene
un **involucro**: un massimo almeno pari a quello vero. La domanda e' quanto
piu' grande, e soprattutto se la differenza cambia la **bias**, che e' l'unica
cosa che il motore legge.

## Il metodo

- **Vero**: indice calcolato minuto per minuto dai sei costituenti, poi
  aggregato a OHLC. E' la migliore approssimazione disponibile senza i tick.
- **Involucro**: formula applicata agli estremi delle candele orarie.
- Periodo: giugno-agosto 2026. 92.878 minuti in cui tutti e sei i costituenti
  hanno una candela, 1.581 ore confrontabili.
- Confronto finale sulla **bias di DEF-16**, non sui prezzi: e' cio' che
  `bias_comando_dxy` calcola e l'unica cosa che arriva al motore.

## Il risultato

| timeframe | candele | ampiezza media del vero | involucro sopra il massimo | involucro sotto il minimo | bias uguale |
|---|---:|---:|---:|---:|---:|
| H1 | 1.509 | 0,0737 | +11,5% | +13,0% | **83,2%** |
| D1 | 76 | 0,3917 | +3,0% | +3,8% | **96,1%** |
| W1 | 13 | 1,0501 | +0,7% | +1,6% | **100%** |

L'errore assoluto dell'involucro **non cresce** con la durata della candela:
e' l'asincronia fra i sei estremi, ed e' la stessa a un'ora e a un giorno.
L'ampiezza della candela invece cresce molto. Per questo l'errore relativo
cala da un ottavo dell'ampiezza a un trentesimo.

## Perche' si usa lo stesso

`bias_per_timeframe` gira su `TF_BIAS`, cioe' `M12, M6, M3, M1, W1, D1`.
**L'ora non e' fra questi.** L'83,2% orario e' il numero peggiore possibile e
non riguarda nessuna decisione: la bias che `SETUP-19` legge e' quella
giornaliera e piu' lenta, dove l'accordo e' 96,1% e 100%.

Conta anche **come** sbaglia. I tre disaccordi su D1 sono tutti della stessa
forma:

```
2026-07-06   vero SHORT     involucro NESSUNA
2026-07-07   vero LONG      involucro NESSUNA
2026-07-31   vero SHORT     involucro NESSUNA
```

L'involucro non ha mai invertito una bias, e non ne ha mai inventata una dove
il vero diceva `NESSUNA`. Ha solo **perso** una bias che c'era — l'estremo
gonfiato rende la candela piu' avvolgente e DEF-16 finisce al passo 1 o al
passo 7. E con `SETUP-19` bias `NESSUNA` significa *non si opera su alcuna
coppia*.

Quindi l'errore di questa costruzione costa **operazioni mancate**, mai
operazioni sbagliate. E' la direzione giusta in cui sbagliare, e il tasso —
tre giorni su settantasei — e' il prezzo di avere un DXY invece di non
averne uno, che significherebbe astenersi **sempre** su cinque coppie.

## Cosa NON si e' fatto, e perche'

Si potrebbe calcolare il DXY dai **minuti**, che darebbe massimi e minimi
quasi esatti. Non si fa, per due ragioni:

1. `DEF-26` chiede cinque anni di storia per i timeframe di bias. Cinque anni
   di minuti per sei costituenti sono circa undicimila file, contro i
   trecentosessanta orari.
2. Peggio: mescolare i due metodi — cinque anni dall'orario e gli ultimi
   giorni dal minuto — creerebbe nella serie un punto in cui la costruzione
   cambia. DEF-16 confronta una candela con la precedente, e proprio in quel
   punto il confronto sarebbe fra due oggetti diversi. Una sola costruzione,
   con il suo errore misurato e dichiarato, e' meglio di due giuste che si
   incontrano male.

Se un giorno servisse la precisione al minuto, va rifatta **tutta** la serie,
non la sua coda.

## Come riprodurre

`importa_dxy.py` semina. La misura sta in
`scratchpad/misura_dxy.py` e `scratchpad/misura_dxy_d1.py` della sessione;
il metodo e' descritto sopra ed e' ricostruibile in una trentina di righe.
