# La misura definitiva — prezzi veri, spread vero, nessuna assunzione

Ultimo atto della ricerca. Tutte le misure precedenti avevano almeno
un'assunzione: il costo di un giro era **stimato** da un listino, e i prezzi
venivano da un aggregatore. Qui non resta nessuna delle due.

## 1. Il dato

1.510.058 candele orarie da Dukascopy, sei strumenti, 2006–2026, **BID e ASK
separati**. Circa 6.000 giornaliere e 1.060 settimanali per strumento.

## 2. Il metodo: lo spread non si assume, si paga

Con le due serie la meccanica reale sta dentro i prezzi:

```
LONG    si compra in ASK   e si chiude in BID
SHORT   si vende  in BID   e si chiude in ASK
```

È la stessa regola che `sentinella.livello_toccato` applica dal vivo. Lo
spread viene quindi pagato **dove e quando il mercato lo faceva pagare**:
allargato sulle news, stretto a mezzogiorno di Londra, enorme alla riapertura
della domenica. Un costo medio non può rappresentarlo, perché lo spread si
allarga proprio quando i prezzi corrono — cioè quando gli stop vengono presi.

E uno stop short viene colpito quando **l'ASK** tocca il livello, non il bid.

## 3. Il risultato

| Coppia | n | winrate | serve | divario | **R netto** | vantaggio sul caso |
|---|---:|---:|---:|---:|---:|---:|
| `W1`→`D1` + criteri | 1.437 | 25,0% | 29,1% | −4,1 pp | **−0,142** | +0,008 (+0,2 σ) |
| `M1`→`D1` + criteri | 572 | 23,1% | 24,9% | −1,8 pp | **−0,073** | −0,009 (−0,1 σ) |
| `D1`→`H1` base | 14.643 | 20,8% | 24,4% | −3,5 pp | **−0,144** | +0,052 (+3,0 σ) |
| `H4`→`H1` + criteri | 26.431 | 22,0% | 32,3% | −10,3 pp | **−0,319** | +0,046 (+5,1 σ) |

**Ogni configurazione perde.**

## 4. Con gli spread di oggi cambia?

Lo spread misurato è passato da ~1,2 pip (2006–2012) a ~0,3 pip (2020–2026).
Era l'ultima speranza: i costi erano il killer, e oggi costano un quarto.

| Coppia | 2006–2012 | 2013–2019 | **2020–2026** |
|---|---:|---:|---:|
| `D1`→`H1` | −0,214 | −0,076 | **−0,182** |
| `W1`→`D1` | −0,071 | −0,222 | **−0,136** |
| `H4`→`H1` | −0,346 | −0,274 | **−0,333** |

**No.** Nessuna epoca, nessuna coppia, nessun segno positivo.

## 5. Il risultato scientifico, che è diverso dal risultato pratico

Sui campioni grandi il CRT **batte l'entrata casuale in modo statisticamente
solido**: +0,052 R a 3,0 σ su `D1`→`H1`, +0,046 a 5,1 σ su `H4`→`H1`.

**Il pattern contiene informazione. È misurabile e non è rumore.**

Ma quell'informazione vale circa **0,05 R per operazione**, e attraversare lo
spread ne costa fra **0,15 e 0,35**. L'edge è reale e un ordine di grandezza
troppo piccolo per pagarsi il biglietto.

E non è nemmeno stabile: su `D1`→`H1` il vantaggio fa −2,3 σ, +3,6 σ, +0,6 σ
nelle tre epoche. Un edge che cambia segno non si può operare.

## 6. Conclusione

Il CRT, come lo descrivono i documenti e come lo insegna chi l'ha inventato,
misurato su prezzi realmente scambiati con lo spread realmente pagato, **non
ha un'aspettativa positiva su nessuno dei sei strumenti, in nessuna
combinazione di timeframe, in nessuna delle tre epoche.**

Non è un'opinione sul metodo né un giudizio su chi lo insegna: è quello che
dicono 1,5 milioni di ore di prezzi veri.

## 7. Cosa NON dice questa misura

- Che il CRT non funzioni **in mano a un discrezionale**. Il backtest prende
  ogni setup; chi opera ne sceglie una frazione. Il §9 di
  `CRT-ROMEO-2026-09-15.md` quantifica quanto dovrebbe valere quella scelta.
- Che non esistano altri vantaggi nei mercati. Dice che questo, così, no.
- Che il lavoro sia stato inutile: il motore è corretto in cinque punti
  strutturali, e l'infrastruttura di misura ha smascherato **quattro** falsi
  positivi, uno dei quali prometteva il +17,8% annuo.
