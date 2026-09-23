# Diario delle operazioni

Ogni operazione aperta dal bot, riverificata contro l'archivio: il CRT c'era
davvero? Nel verso giusto? Lo stop stava dove il CRT lo vuole? Com'e' finita?

## Correzioni fatte

_(questa sezione la scrivo a mano man mano che si corregge qualcosa, con la
data e il caso concreto che l'ha fatta scoprire)_

<!-- QUI SOPRA SCRIVO IO, LO SCRIPT NON TOCCA NULLA -->

<!-- DA QUI IN GIU' RIGENERA LO SCRIPT: NON SCRIVERE A MANO -->

_Rigenerato il 23/09/2026 18:10 UTC da `diario_operazioni.py`._

## Riepilogo

- operazioni esaminate: **21** (14 chiuse)
- esito: **0 in utile** su 5, R totale **-0.25**, R medio **-0.05**
- parziale preso: 12

**Quello che conta per correggere:**
- ingressi **senza nessun CRT** ricostruibile: **0** su 21
- ingressi con CRT ma **stop in un altro posto**: **0** su 21

## Tutte le operazioni

| quando | strumento | verso | esito | R | durata | parziale | c'era il CRT? |
|---|---|---|---|---|---|---|---|
| 23/09 17:11 | USDCHF+ | SELL | ⚪ chiusa fuori | —R | 33m | sì | sì (TF_H1→TF_M5) |
| 23/09 17:12 | XAUUSD+ | BUY | ⚪ chiusa fuori | —R | 27m | sì | sì (TF_H1→TF_M5) |
| 23/09 17:25 | GBPUSD+ | BUY | 🔵 aperta | —R | aperta | sì | sì (TF_H1→TF_M5) |
| 23/09 17:25 | USDCHF+ | SELL | ⚪ chiusa fuori | —R | 18m | no | sì (TF_H1→TF_M5) |
| 23/09 17:26 | XAUUSD+ | BUY | ⚪ chiusa fuori | —R | 13m | no | sì (TF_H4→TF_M15) |
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
| 23/09 17:50 | USDJPY+ | SELL | ➖ pareggio | -0.09R | 4s | sì | sì (TF_H4→TF_M15) |
| 23/09 17:55 | USDJPY+ | SELL | ➖ pareggio | -0.01R | 3s | sì | sì (TF_H4→TF_M15) |
| 23/09 18:03 | XAUUSD+ | SELL | 🔵 aperta | —R | aperta | sì | sì (TF_M15→TF_M1min) |
| 23/09 18:05 | XAUUSD+ | SELL | ➖ pareggio | -0.02R | 5s | sì | sì (TF_H1→TF_M5) |
| 23/09 18:05 | EURUSD+ | SELL | ➖ pareggio | 0.00R | 3s | sì | sì (TF_H1→TF_M5) |
| 23/09 18:05 | EURUSD+ | SELL | ➖ pareggio | -0.13R | 56s | sì | sì (TF_H1→TF_M5) |

## I casi da guardare sul grafico

Nessuno: ogni ingresso e' spiegato da un CRT ricostruibile con lo stop al posto giusto.

