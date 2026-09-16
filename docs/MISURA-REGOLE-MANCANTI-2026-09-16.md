# Le otto regole mancanti, scritte e misurate

`docs/BIBBIA-CRT.md` elencava 6 punti **ASSENTI** e 2 **CONTRARI**. Sono stati
scritti in `core/` e misurati sui prezzi veri Dukascopy, BID e ASK, 2006–2026.
Questo documento riporta cosa hanno detto i numeri, compreso il caso in cui
hanno detto che la regola non serve.

## Metodo

Per ogni regola: **CRT base** contro **CRT più quella regola**. Se il secondo
non batte il primo, la regola non serve, per quanto autorevole sia chi la
scrive. Ogni risultato porta il proprio σ, e quello che sopravvive passa per
la divisione in epoche e per un placebo che seleziona la stessa frazione di
segnali senza alcun legame col segnale.

Esito in R: stop all'estremo di `N2` (GEST-02), bersaglio al 50% di `N1`
(GEST-07), 24 barre di tempo massimo. Nessun costo: qui si confrontano regole
fra loro, e il costo è lo stesso per tutte.

---

## Un lookahead trovato e corretto durante la misura

La prima versione di `CRT-17` dava **85,7% di winrate e +15,3σ**. Non era un
risultato: era la firma di un lookahead. Filtravo con le due candele del
timeframe **alto successive a N2** — su `D1→H1` i due giorni dopo, mentre
l'esito si risolve entro 24 ore.

Corretto guardando solo ciò che è accaduto **dentro `N2`** sul timeframe
basso, `CRT-17` sparisce del tutto: meno di 30 campioni in ogni coppia.

Vale la pena dirlo esplicitamente perché è il quinto falso positivo di questa
cartella, e tutti e cinque avevano lo stesso aspetto: un numero troppo bello.

---

## I risultati

### `D1 → H1`, 7.806 segnali

| Regola | n | win | R medio | σ≠0 | σ vs base |
|---|---:|---:|---:|---:|---:|
| CRT base | 7.806 | 59,6% | +0,017 | +1,4σ | — |
| **CRT-11 con CISD** | **3.640** | **63,0%** | **+0,089** | **+4,5σ** | **+3,0σ** |
| CRT-12 con divergenza SMT | 1.455 | 59,0% | +0,036 | +1,1σ | +0,5σ |
| CRT-12 senza divergenza | 6.317 | 59,8% | +0,013 | +1,0σ | −0,2σ |
| CRT-10 double purge concorde | 283 | 88,7% | −0,015 | −0,8σ | −1,4σ |
| CRT-15 fuori finestra Romeo | 7.786 | 59,6% | +0,014 | +1,1σ | −0,2σ |
| CRT-19 ombre piccole | 256 | 33,6% | −0,049 | −0,5σ | −0,6σ |
| CRT-20 ombre grandi | 5.956 | 62,9% | +0,015 | +1,2σ | −0,1σ |

### `W1 → H4` — la coppia di Romeo, misurata per la prima volta

| Regola | n | win | R medio | σ≠0 | σ vs base |
|---|---:|---:|---:|---:|---:|
| CRT base | 1.611 | 60,6% | +0,032 | +1,3σ | — |
| **CRT-11 con CISD** | **749** | **64,5%** | **+0,085** | **+2,5σ** | **+1,3σ** |
| CRT-12 con divergenza SMT | 260 | 59,6% | −0,005 | −0,1σ | −0,6σ |
| CRT-15 dentro finestra Romeo | 1.593 | 60,7% | +0,034 | +1,3σ | +0,0σ |
| CRT-20 ombre grandi | 1.194 | 63,1% | +0,033 | +1,3σ | +0,0σ |

---

## Il CISD fuori campione, col placebo

È l'unica regola che è arrivata fin qui.

### `D1 → H1`

| Epoca | n con CISD | R con | R senza | σ diff | placebo |
|---|---:|---:|---:|---:|---:|
| 2006–2012 | 1.261 | +0,052 | −0,058 | **+2,6σ** | −0,8σ |
| 2013–2019 | 1.263 | +0,082 | +0,029 | +1,2σ | +0,9σ |
| 2020–2026 | 1.116 | +0,138 | −0,111 | **+5,4σ** | −0,8σ |
| **Tutto** | **3.640** | **+0,089** | **−0,045** | **+5,2σ** | **−0,3σ** |

### `W1 → H4`

| Epoca | n con CISD | R con | R senza | σ diff | placebo |
|---|---:|---:|---:|---:|---:|
| 2006–2012 | 246 | +0,116 | +0,044 | +0,8σ | −0,7σ |
| 2013–2019 | 256 | +0,103 | −0,068 | +1,9σ | +0,3σ |
| 2020–2026 | 247 | +0,035 | −0,020 | +0,7σ | −0,2σ |
| **Tutto** | **749** | **+0,085** | **−0,014** | **+2,0σ** | **−0,2σ** |

**Il segno non cambia in nessuna delle sei epoche**, su due coppie
indipendenti, e il placebo sta a zero. È la prima cosa misurata in questo
progetto che sopravvive a tutta la disciplina.

---

## Cosa significa, e cosa non significa

**Il CISD moltiplica per cinque il vantaggio di base** — da +0,017 a +0,089 R
su `D1→H1` — e separa nettamente i CRT che funzionano da quelli che non
funzionano: senza CISD il rendimento è **negativo** (−0,045 R).

Avevo implementato l'**MSS** al suo posto. Lo swing strutturale sta più
lontano della serie di consegna, quindi l'MSS arriva sempre dopo: su un
ingresso che vive dentro una candela di timeframe superiore, "dopo" significa
a prezzo peggiore, e a volte significa mai. La differenza non era accademica.

**Ma +0,089 R resta sotto il costo.** `docs/MISURA-DEFINITIVA-2026-09-16.md`
misura lo spread fra 0,15 e 0,35 R. Il CISD porta il CRT molto più vicino alla
soglia di quanto fosse, e non la supera da solo.

---

## Le regole che non hanno retto, dette chiaramente

**`CRT-12`, la divergenza SMT.** Le fonti la dichiarano una delle tre
confluenze **non negoziabili**. Su questi dati non mostra nulla: +0,5σ,
−0,6σ, +0,2σ a seconda della coppia. Non è un errore di implementazione — i
test verificano il segno della correlazione su coppie positive e negative. È
che su sei strumenti a granularità oraria non si vede. Può darsi che serva la
granularità al minuto su cui Romeo lavora; può darsi che non funzioni. Come
sta scritta e come l'ho misurata, non aiuta.

**`CRT-10`, il Double Purge.** 88,7% di winrate e R **negativa**: tante
vittorie piccole e poche perdite grandi. Ed è la variante *concorde* — quella
che segue il verso della regola — a essere peggiore della base (−1,4σ). È il
caso in cui il winrate inganna e l'R dice la verità.

**`CRT-15`, le finestre orarie.** Nessuna differenza: +0,0σ e −0,2σ. Su
`D1→H1` quasi tutti i segnali cadono *fuori* dalle finestre di Romeo, il che
dice che quelle finestre sono pensate per timeframe d'ingresso più bassi di
quelli che il bot può usare.

**`CRT-19`/`CRT-20`, le ombre.** Il sospetto era fondato nel **verso**: le
ombre piccole sono peggiori (33,6% di winrate su `D1→H1`), quindi il filtro
"sweep efficiente" che le teneva scartava i CRT buoni. Ma il vantaggio delle
ombre grandi è nullo rispetto alla base (−0,1σ, +0,0σ): la conoscenza serve a
non fare la cosa sbagliata, non a guadagnare.

**`CRT-17`** — lookahead, vedi sopra.

**`CRT-06`**, i tre modelli allineati: scritto e collaudato, non ancora
misurato. Richiede di incrociare tre coppie sullo stesso istante.

---

## Prossimo passo

Il CISD è l'unico candidato. Va portato **dentro il motore** — oggi vive in
`core/definizioni.py` e non lo chiama nessuno, che è esattamente lo stato in
cui si trovava `DEF-33` — e poi rimisurato insieme ai costi veri, per vedere
quanto manca davvero alla soglia.
