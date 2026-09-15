# Che cos'è davvero il CRT — studio delle fonti e misura

Nato da un'obiezione precisa: *«il problema è strutturale nell'analisi del
grafico, il bot non interpreta il CRT come dovrebbe»*. L'obiezione era
fondata. Questo documento dice in cosa, con le fonti, e lo dimostra con una
misura fuori campione.

## 1. Il punto di partenza: non c'era niente contro cui verificare

`07_casi.md` è marcato **DA POPOLARE** e contiene **zero** casi annotati.
L'unico esempio ha `n/d` proprio nei campi che servirebbero — `N1 high/low`,
`N2 high/low/close`, `N3 open`. I documenti stessi ne chiedono 75 come minimo.

Senza un solo caso reale non esiste modo di verificare l'interpretazione
contro l'intenzione: è la ragione per cui una lettura sbagliata è potuta
sopravvivere a 426 test.

## 2. Cosa dicono le fonti

Cinque fonti indipendenti, tutte concordi sulla struttura:

| Fonte | Cosa stabilisce |
|---|---|
| [MQL5 — CRT/AMD](https://www.mql5.com/en/articles/20323) | il range «usa massimo e minimo della **barra precedente** sul timeframe del range» |
| [GrandAlgo — CRT key levels](https://grandalgo.com/guides/crt-key-levels) | «CRT tratta massimo e minimo di **una candela completata** come key level istituzionali»; key level = PDH/PDL, PWH/PWL |
| [TradingFinder — ICT CRT](https://tradingfinder.com/education/forex/ict-candle-range-theory/) | «il massimo di questa candela diventa CRT-High e il minimo CRT-Low»; stop «dietro la candela del liquidity grab»; TP «il 50% è il primo bersaglio sicuro», poi «il lato opposto del range» |
| [WritOfFinance](https://www.writofinance.com/candle-range-theory-crt/) | la candela raid «spazza l'estremo **della candela precedente** richiudendo dentro il range»; la terza «rompe l'estremo della candela raid» |
| [JustWolves — modello a 3 candele](https://justwolves.in/learn/forex/candle-range-theory-crt-3-candle-model-forex-traders) | «C2 deve rompere oltre uno dei livelli **di C1** e poi richiudere dentro il range di C1»; «C3 conferma rompendo il minimo o massimo di C2»; «le regole sono binarie» |

Il modello canonico, in tre righe:

```
C1   candela di range. Il suo massimo e il suo minimo SONO i livelli.
C2   spazza uno dei due estremi DI C1 e richiude dentro il range di C1.
C3   rompe l'estremo di C2 nella direzione opposta. E' la CONFERMA, ed e'
     li' che si entra.
```

## 3. Le tre divergenze del motore

| | canonico | motore (fedele ai documenti) |
|---|---|---|
| livello spazzato | l'estremo di **`C1` stesso** | un key level di un TF **strettamente superiore** (`SETUP-00`, `DEF-30`) |
| conferma | **`C3` rompe l'estremo di `C2`** | nessuna: si entra all'apertura di `C3` (`SETUP-04`) |
| bersaglio | 50% e lato opposto **del range di `C1`** | 50% di `N1`, poi key level del TF del CRT |

La prima è la più pesante. Pretendere che lo stesso spazzamento superi
**insieme** l'estremo di `C1` e un livello di un timeframe più alto è una
coincidenza rara: è quella che riduce i CRT di due ordini di grandezza e
lascia 50 operazioni in ventisei anni.

I documenti se ne accorgono a metà. `SETUP-00` scrive *«ogni massimo e minimo
di candela chiusa su TF_1D … TF_12M è un key level (DEF-36)»* — che è la
definizione di **`DEF-25`** (livello strutturale), non di `DEF-36`, il quale
limita i key level alla sola `C1`. Le due letture differiscono di tre ordini
di grandezza nel numero di livelli.

## 4. La misura: il pattern canonico porta informazione

Metodo identico a quello già usato: ogni configurazione contro il **suo**
placebo — entrate a caso, stesso strumento, stessa direzione, stesse distanze
relative. Nessun filtro di contesto: si isola il pattern.

| Timeframe | conferma `C3` | filtro chiusura | n | vantaggio sul caso |
|---|---|---|---:|---:|
| `TF_1D` | no | no | 14.039 | +0,050 (+2,8 σ) |
| `TF_1D` | no | sì | 6.748 | +0,074 (+4,4 σ) |
| `TF_1D` | **sì** | no | 8.142 | +0,088 (+12,8 σ) |
| `TF_1D` | **sì** | **sì** | 4.580 | **+0,138 (+16,4 σ)** |
| `TF_1W` | sì | sì | 1.200 | +0,121 (+7,5 σ) |
| `TF_H4` | sì | sì | 2.890 | +0,080 (+7,2 σ) |
| `TF_H1` | sì | sì | 11.240 | +0,110 (+20,8 σ) |

**La conferma su `C3` raddoppia il vantaggio ovunque.** È il pezzo mancante
più grosso: il motore entra all'apertura di `C3` senza aspettare che `C3`
rompa l'estremo di `C2`.

## 5. Quale uscita

| Uscita | `TF_1D` netto costi | `TF_H1` netto costi |
|---|---:|---:|
| **tutto a TP1 (50% di `C1`)** | **+0,048** | −0,081 |
| parziale senza break even | +0,026 | −0,083 |
| parziale con break even | −0,059 | −0,177 |
| tutto al lato opposto | −0,082 | −0,183 |

Due cose:

- **il vantaggio vive nel movimento fino al 50%, non oltre.** Il lato opposto
  del range ha un vantaggio di soli +0,035 contro +0,195 del 50%;
- **`TF_H1` non è operabile**: il costo di un giro vale 0,081 R contro 0,013 R
  del giornaliero, e si mangia tutto. Gli stop orari sono troppo stretti
  rispetto allo spread.

## 6. Validazione fuori campione

La configurazione è stata scelta guardando 64 combinazioni, quindi va
verificata su dati che non hanno partecipato alla scelta. Taglio al 2013.

| | n | CRT | a caso | vantaggio | netto costi | winrate |
|---|---:|---:|---:|---:|---:|---:|
| 2000–2012 (in campione) | 2.091 | +0,064 | −0,094 | +0,158 (+9,6 σ) | +0,054 | 80,9% |
| **2013–2026 (fuori campione)** | 2.489 | +0,058 | −0,172 | **+0,230 (+19,9 σ)** | **+0,043** | 81,0% |

E regge su **tutti e sei gli strumenti**, presi uno per uno fuori campione:

| Strumento | n | vantaggio | netto costi |
|---|---:|---:|---:|
| XAUUSD | 249 | +0,252 (+6,5 σ) | +0,071 |
| EURUSD | 466 | +0,243 (+9,6 σ) | +0,065 |
| GBPUSD | 402 | +0,232 (+7,9 σ) | +0,059 |
| USDCHF | 477 | +0,240 (+9,4 σ) | +0,051 |
| AUDUSD | 477 | +0,193 (+7,3 σ) | +0,025 |
| USDJPY | 418 | +0,191 (+6,6 σ) | +0,000 |

## 7. Il conflitto con le regole scritte

Il profilo è **alto winrate, basso R**: 81% di successi con vincite da circa
**0,31 R** e perdite da 1 R.

Questo confligge frontalmente con `GEST-01`, che rifiuta ogni setup con
rapporto su TP1 sotto 1,5. **`GEST-01` scarterebbe il 100% di queste 4.580
operazioni.** È la stessa regola che, nella configurazione precedente,
riduceva 26.285 CRT a 50.

Non è una regola da correggere di nascosto: è una scelta di impostazione, e
va presa sapendo cosa comporta. Un sistema a 0,31 R per vincita non tollera
slippage: tre vincite le cancella una perdita, e lo slippage su un ordine stop
non è modellato qui.

## 8. Cosa resta da verificare prima di operare

- **slippage sull'ordine di ingresso.** L'ingresso canonico è una rottura
  dell'estremo di `C2`, cioè un ordine stop: si riempie peggio del prezzo
  richiesto, e con vincite da 0,31 R il margine è sottile;
- `TF_1D` produce circa **180 operazioni l'anno su sei strumenti**, il che con
  `RISK-02` significa posizioni spesso sovrapposte;
- il capitale minimo resta quello di `BACKTEST-2026-09-15.md` §8: circa
  **1.220 $** per coprire i sei strumenti a regola.
