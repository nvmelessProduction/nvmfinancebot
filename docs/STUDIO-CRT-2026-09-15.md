# Che cos'è davvero il CRT — studio delle fonti e misura

Nato da un'obiezione precisa: *«il problema è strutturale nell'analisi del
grafico, il bot non interpreta il CRT come dovrebbe»*. **L'obiezione è
fondata**: il motore diverge dal CRT della letteratura in tre punti, e il §3
li elenca con le fonti.

**Ma correggerli non basta.** Il CRT canonico, implementato bene, batte
un'entrata a caso di +0,031 R a 2,5 sigma — un vantaggio che non regge fra i
due periodi e che resta molto sotto quello che serve. Il §4 è un errata: una
versione precedente di questo documento riportava +0,195 R a 20 sigma, e quel
numero era prodotto da un difetto del simulatore.

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

## 4. ERRATA — il primo risultato era un artefatto

**Questa sezione corregge una versione precedente di questo documento, che
riportava un vantaggio di +0,195 R a 20 sigma e un risultato netto positivo
fuori campione. Quel risultato era falso.** Resta scritto qui invece di
sparire, perche' l'errore e' istruttivo e perche' il numero sbagliato e' stato
comunicato.

**Cosa era successo.** Entrando sulla rottura dell'estremo di `C2`, il 50% di
`C1` e' gia' stato superato **nel 77% dei casi** (misurato: 3.527 segnali su
4.580). Il simulatore calcolava il guadagno come `|TP1 - ingresso| / rischio`
senza verificare che `TP1` stesse **oltre** l'ingresso, e la condizione di
raggiungimento risultava vera sulla prima barra. Tremilacinquecento operazioni
venivano chiuse in profitto sulla barra d'ingresso, con una vincita che il
mercato non ha mai pagato.

Il sintomo era visibile e non l'ho riconosciuto: winrate dell'81% con vincite
medie da 0,31 R. Un profilo del genere, su un pattern di reversione, andava
verificato prima di essere pubblicato, non dopo.

La correzione e' in `backtest/canonico.bersaglio_valido`, con il test che la
fissa.

## 5. La misura corretta

Il bersaglio e' il primo livello del range di `C1` ancora **oltre**
l'ingresso: prima l'EQ, poi il lato opposto. Se entrambi sono gia' stati
superati non c'e' operazione. E' la lettura canonica — *«targets the midpoint,
opposite side, or next liquidity pool»* — non uno scarto arbitrario.

| Timeframe | conferma `C3` | filtro chiusura | n | CRT | a caso | vantaggio | netto costi | winrate |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `TF_1D` | no | no | 13.375 | −0,155 | −0,171 | +0,016 (+1,1 σ) | −0,190 | 50,7% |
| `TF_1D` | no | sì | 6.253 | −0,138 | −0,163 | +0,025 (+1,8 σ) | −0,162 | 60,0% |
| `TF_1D` | sì | no | 6.691 | −0,153 | −0,156 | +0,003 (+0,4 σ) | −0,167 | 66,7% |
| `TF_1D` | **sì** | **sì** | 3.636 | −0,106 | −0,138 | **+0,031 (+2,5 σ)** | −0,120 | 70,4% |
| `TF_1W` | sì | sì | 1.000 | −0,127 | −0,124 | −0,002 (−0,1 σ) | −0,132 | 69,8% |

E la verifica fuori campione **non regge**:

| | n | vantaggio |
|---|---:|---:|
| 2000–2012 (in campione) | 1.653 | **−0,024 (−1,2 σ)** |
| 2013–2026 (fuori campione) | 1.983 | +0,086 (+5,9 σ) |

Negativo in un periodo, positivo nell'altro: e' la firma del rumore, non di un
vantaggio.

## 6. Perche' la geometria non funziona comunque

Anche prendendo per buono il +0,031, il pattern perde **0,106 R per
operazione** in assoluto. Il motivo e' strutturale e si legge dai numeri:

```
winrate 70,4%   →   0,704 x vincita - 0,296 x 1 = -0,106
                →   vincita media = +0,27 R
                →   per pareggiare servirebbe +0,42 R
```

Entrare sulla rottura di un estremo di `C2` mettendo lo stop all'estremo
opposto significa rischiare **l'intero range di `C2`** per guadagnare quel che
resta del range di `C1`. Il rapporto e' sfavorevole per costruzione, e nessun
filtro lo cambia: i filtri spostano il winrate, non la geometria.

## 7. Cosa resta valido di questo studio

Le tre divergenze del §3 restano documentate e reali, e la conferma su `C3`
resta la piu' utile delle tre: alza il winrate dal 50,7% al 70,4% e porta il
vantaggio da +0,016 a +0,031. Semplicemente non basta.

Restano vere anche le due osservazioni sui documenti:

- `07_casi.md` e' vuoto — **zero casi su 75 richiesti** — quindi non esiste
  niente contro cui verificare l'interpretazione;
- `SETUP-00` chiama key level *«ogni massimo e minimo di candela chiusa»*, che
  e' la definizione di `DEF-25`, mentre cita `DEF-36`, che li limita alla sola
  `C1`. Tre ordini di grandezza di differenza.

## 8. Cosa servirebbe per andare avanti

Non altre varianti misurate sugli stessi dati: ne ho gia' provate un centinaio
fra uscite, filtri e timeframe, e a forza di provarne una uscira' positiva per
caso. Servono **casi reali annotati** — i 75 di `07_casi.md` — perche' senza
non c'e' modo di distinguere "il bot legge male il grafico" da "il pattern non
funziona".
