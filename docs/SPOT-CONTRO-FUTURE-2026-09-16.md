# Analizzare sullo spot invece che sul future — il falso positivo più bello

Nato da un'intuizione tua: *«testare direttamente sul CFD al posto del
future»*. Era l'unico asse rimasto non testato, ed era una buona idea. Il
risultato è stato il più bello del progetto, ed è **falso**. Questo documento
dice perché, perché la lezione vale più del risultato.

## 1. Cosa sembrava

Stesso modello, stesse regole, cinque coppie forex, periodo controllato
2006–2026. Unica differenza: i prezzi.

| Sorgente | n | winrate | divario | **netto** | sigma |
|---|---:|---:|---:|---:|---:|
| future | 1.127 | 27,9% | +0,8 pp | +0,030 | +2,2 |
| **spot** | 1.119 | **34,5%** | **+9,1 pp** | **+0,370** | **+6,5** |

Fuori campione (2016–2026) andava ancora meglio: netto **+0,480** a 5,2 sigma,
e **tutti e cinque** gli strumenti positivi singolarmente.

Con 1.000 € e l'1% di rischio: **31.278 € in 21 anni, +17,8% l'anno, drawdown
massimo 18,3%**. Numeri che un fondo professionale si sogna.

## 2. I controlli che ha superato

| Controllo | Esito |
|---|---|
| i range spot sono compressi? | sì (0,77–0,94), ma la correlazione con il vantaggio è **+0,17**: lo strumento più compresso guadagna meno |
| è un effetto del periodo? | no: controllato 2006–2026, il vantaggio resta |
| è la grana giornaliera che nasconde gli stop? | no: risolto sulle orarie, **1 esito su 183** cambia |
| regge fuori campione? | sì: +3,2 σ dentro, +5,2 σ fuori |
| regge strumento per strumento? | sì: 5 su 5 positivi fuori campione |

Cinque cancelli su cinque. A questo punto ci avevo quasi creduto.

## 3. Il controllo che lo ha smontato

Il test sulle orarie **non dimostrava niente**, e me ne sono accorto dopo: le
orarie vengono dallo **stesso feed** delle giornaliere. Se quel feed attenua
gli estremi, li attenua a ogni grana, e il confronto non può rilevarlo.

Il test giusto è un altro: prendere i segnali nati sullo spot e misurarne
l'esito sui **prezzi future**, che sono scambi realmente avvenuti. Le distanze
si trasportano in forma relativa, perché spot e future differiscono per il
basis.

| Gli stessi 1.118 segnali | winrate | divario | netto |
|---|---:|---:|---:|
| esito misurato sullo **spot** | 34,5% | +9,1 pp | **+0,371** |
| esito misurato sul **future** | 23,3% | −4,9 pp | **−0,181** |

**Il 37,7% degli esiti cambia. Duecentosettantaquattro operazioni passano da
vincita a perdita.**

Il vantaggio non esiste. Era il feed.

## 4. Il meccanismo, in una riga

Lo stop è un livello che deve essere **toccato**. Il feed spot di Yahoo è
indicativo: i suoi massimi e minimi giornalieri sono campionati, non i veri
estremi scambiati — misurato, sono il **77–94%** di quelli del future. Estremi
attenuati significano stop toccati meno spesso, e su una strategia stop-e-
bersaglio questo è tutto il gioco.

Le 274 operazioni che "vincevano" avevano lo stop preso, nei prezzi veri.

## 5. La regola che ne esce

> **Un vantaggio basato sui prezzi non si valida su un feed di cui non si sono
> verificati gli estremi contro scambi reali.**

Non basta che il feed sia plausibile, continuo, o coerente con sé stesso: deve
essere confrontato con prezzi che qualcuno ha davvero pagato. Un feed
indicativo è perfetto per guardare un grafico e inutile per misurare una
strategia a stop.

Questo vale anche per il CFD del broker: **il suo feed non è quello di
Yahoo**, e se un giorno si volesse rifare questa misura sui prezzi CFD veri,
andrebbero presi dal broker, non da internet.

## 6. Cosa resta valido

`DEF-32` ed `ESCL-12` — analisi sul future, esecuzione sul CFD — escono
**confermate**, per una ragione che i documenti non dicevano: il future è
l'unica delle due serie fatta di prezzi che qualcuno ha pagato davvero.

E resta il numero di sempre: sui prezzi veri il modello sta fra **−0,18 e
+0,05 R** per operazione, a seconda della coppia di timeframe. Nessuna delle
misure di questo progetto ha mai superato quella soglia quando è stata
verificata contro scambi reali.
