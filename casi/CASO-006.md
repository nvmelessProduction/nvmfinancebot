# CASO-006 — EURUSD, CRT settimanale, settembre 2025

```
id:            CASO-006
tipo:          CRT
strumento:     EURUSD
coppia:        W1 -> H4
candela_range: la settimana dell'08/09/2025 (apre il 07/09 alle 17 NY): H 1.17799, L 1.16589
manipolazione: la settimana del 15/09, fino a 1.19186 (la Fed del 17/09)
rientro:       la candela 2 chiude a 1.17405, dentro il range
verso:         SHORT
ingresso:      "SELL 6" circa 1.18396 e "SELL 15" circa 1.18161, dopo il picco (msg 6385, 6387, 6447)
stop:          pochi pip sopra ciascun ingresso
target:        il CRT low, intorno a 1.1660
esito:         il CRT low viene toccato il 25/09
immagine:      https://t.me/officialRomeotpt/6387 ("My CRT in the flesh. Euro weekly.")
fonte:         canale Telegram ufficiale di Romeo, 25/09/2025
```

## Verifica sui dati (24/09/2026)

| | Romeo | Il bot | |
|---|---|---|---|
| Range | le linee a 1.1780 e 1.1660 | H 1.17799, L 1.16589 | ✅ |
| Ingresso | 1.18396 e 1.18161, dopo il picco del 17/09 | primo Model#1 (scatto 16/09 alle 21 NY) a 1.18583, **stoppato** dal picco; **secondo** Model#1 (TS la candela delle 17 NY del 17/09, scatto all'1:00 del 18/09) a 1.17949 | ✅ col secondo colpo, ma 20–45 pip più in basso |
| Stop | stretto, sopra l'ingresso | 1.19186 (l'estremo); lo stop stretto 1.18139 viene preso alle 5:00 del 18/09 | ⚠️ |
| Esito | CRT low toccato il 25/09 | target il 25/09, +0,85 R | ✅ |

Terzo caso su tre in cui l'operazione pubblicata è un colpo dopo il primo.
Romeo vende i rimbalzi dopo il picco su timeframe bassi (il grafico a 30
minuti del msg 6385); il bot sulle 4 ore entra una volta sola, più in
basso, con lo stop all'estremo.
