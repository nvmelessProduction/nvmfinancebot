# Diario delle operazioni

Ogni operazione aperta dal bot, riverificata contro l'archivio: il CRT c'era
davvero? Nel verso giusto? Lo stop stava dove il CRT lo vuole? Com'e' finita?

## Correzioni fatte

_(questa sezione la scrivo a mano man mano che si corregge qualcosa, con la
data e il caso concreto che l'ha fatta scoprire)_

<!-- QUI SOPRA SCRIVO IO, LO SCRIPT NON TOCCA NULLA -->

<!-- DA QUI IN GIU' RIGENERA LO SCRIPT: NON SCRIVERE A MANO -->

_Rigenerato il 23/09/2026 17:55 UTC da `diario_operazioni.py`._

## Riepilogo

- operazioni esaminate: **12** (7 chiuse)
- esito: **0 in utile** su 2, R totale **-2.50**, R medio **-1.25**
- parziale preso: 5

**Quello che conta per correggere:**
- ingressi **senza nessun CRT** ricostruibile: **0** su 12
- ingressi con CRT ma **stop in un altro posto**: **2** su 12

## Tutte le operazioni

| quando | strumento | verso | esito | R | durata | parziale | c'era il CRT? |
|---|---|---|---|---|---|---|---|
| 23/09 17:30 | XAUUSD+ | BUY | ⚪ chiusa fuori | —R | 9m | no | sì (TF_H4→TF_M15) |
| 23/09 17:30 | GBPUSD+ | BUY | 🔵 aperta | —R | aperta | sì | sì (TF_H1→TF_M5) |
| 23/09 17:30 | USDCHF+ | SELL | ⚪ chiusa fuori | —R | 13m | no | sì (TF_H4→TF_M15) |
| 23/09 17:35 | XAUUSD+ | BUY | ⚪ chiusa fuori | —R | 4m | no | sì (TF_H4→TF_M15) |
| 23/09 17:35 | GBPUSD+ | BUY | 🔵 aperta | —R | aperta | sì | sì (TF_H1→TF_M5) |
| 23/09 17:35 | USDCHF+ | SELL | ⚪ chiusa fuori | —R | 8m | no | sì (TF_H4→TF_M15) |
| 23/09 17:40 | GBPUSD+ | BUY | 🔵 aperta | —R | aperta | sì | sì (TF_H1→TF_M5) |
| 23/09 17:47 | XAUUSD+ | SELL | ⚪ chiusa fuori | —R | 35s | no | sì (TF_M15→TF_M1min) |
| 23/09 17:50 | EURUSD+ | BUY | 🔵 aperta | —R | aperta | no | sì (TF_H4→TF_M15) |
| 23/09 17:50 | AUDUSD+ | BUY | 🔵 aperta | —R | aperta | no | sì (TF_H4→TF_M15) |
| 23/09 17:50 | USDJPY+ | SELL | ➖ pareggio | -2.13R | 4s | sì | sì, ma stop a 274.50R dal suo |
| 23/09 17:55 | USDJPY+ | SELL | ➖ pareggio | -0.37R | 3s | sì | sì, ma stop a 275.88R dal suo |

## I casi da guardare sul grafico

Sono 2. Ognuno ha data, ora e livelli: si apre il grafico, si va li', e si vede chi ha ragione.

### 23/09/2026 17:50 · USDJPY+ SELL · ➖ pareggio (-2.13R)

- ingresso `158.204`, stop `158.196`, target `158.167`
- durata 4s, parziale preso
- CRT trovato su **TF_1M → TF_1D**: bordo `160.20300`, spinta fino a `160.39200`, rientro alle 22:00 dopo 1 barre
- ⚠️ **lo stop del bot non e' quello del CRT**: dista 274.50R dall'estremo della manipolazione

### 23/09/2026 17:55 · USDJPY+ SELL · ➖ pareggio (-0.37R)

- ingresso `158.193`, stop `158.185`, target `158.167`
- durata 3s, parziale preso
- CRT trovato su **TF_1M → TF_1D**: bordo `160.20300`, spinta fino a `160.39200`, rientro alle 22:00 dopo 1 barre
- ⚠️ **lo stop del bot non e' quello del CRT**: dista 275.88R dall'estremo della manipolazione

