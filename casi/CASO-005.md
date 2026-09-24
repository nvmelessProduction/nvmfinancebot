# CASO-005 — EURUSD, CRT giornaliero, 8–9 settembre 2025

```
id:            CASO-005
tipo:          CRT
strumento:     EURUSD
coppia:        D1 -> H1
candela_range: la giornaliera di lunedì 08/09/2025 (apre il 07/09 alle 17 NY): H 1.17654, L 1.17036
manipolazione: martedì 09/09, fino a 1.17799 (la candela 2 spazza il massimo)
rientro:       Model#1 sulle orarie: alle 1:00 NY del 09/09 una candela rialzista fa il massimo,
               alle 2:00 NY il prezzo crolla sotto la sua apertura
verso:         SHORT
ingresso:      "SELL 36", circa 1.17760 (screenshot MT5, msg 6332; H1 nel msg 6337)
stop:          1.17784 (screenshot MT5)
target:        la linea sotto, intorno a 1.1700: il CRT low
esito:         il CRT low viene toccato lo stesso 09/09
immagine:      https://t.me/officialRomeotpt/6332 e /6337
fonte:         canale Telegram ufficiale di Romeo, 09/09/2025
perché:        range del lunedì, turtle soup sul suo massimo all'apertura di Londra del
               martedì, e discesa fino all'altro lato
```

## Verifica sui dati (24/09/2026)

| | Romeo | Il bot | |
|---|---|---|---|
| Range | le linee a 1.1766 e 1.1700 | H 1.17654, L 1.17036 | ✅ |
| Ingresso | 1.17760, subito dopo il massimo | primo Model#1 (23:00 NY dell'08/09) a 1.17685, **stoppato** dal massimo delle 1:00; **secondo** Model#1 (TS 1:00 NY, scatto alle 2:00, ingresso 3:00 NY) a 1.17647 | ✅ col secondo colpo |
| Stop | 1.17784 | 1.17799 (l'estremo) | ✅ 1,5 pip: feed diversi |
| Esito | CRT low toccato | target alle 20:00 NY del 09/09, +2,96 R (stop stretto +5,12 R) | ✅ |

Come nel CASO-004, l'operazione di Romeo è il secondo Model#1: il primo
viene stoppato dalla spinta che fa il massimo, e quella spinta è il turtle
soup nuovo. Romeo entra sul timeframe più basso, dentro la barra oraria
delle 2:00, quindi più in alto del bot.

Il periodo è nel 2024–2026 chiuso: il caso serve solo a provare le
definizioni, non a misurare risultati.
