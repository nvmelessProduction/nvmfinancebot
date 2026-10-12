# CASO-003 — EURUSD, CRT mensile, agosto–ottobre 2024

```
id:            CASO-003
tipo:          CRT
strumento:     EURUSD
coppia:        MN -> D1
candela_range: agosto 2024
manipolazione: settembre 2024, sopra il massimo di agosto
rientro:       settembre chiude dentro il range
verso:         SHORT
ingresso:      non indicato
stop:          non indicato
target:        "CRT 50%, target 1 (partial)" 1.09687; "CRT low - target 2" 1.07768
esito:         il CRT low viene toccato a fine ottobre (secondo screenshot: 1.07643)
immagine:      https://t.me/officialRomeotpt/5623
fonte:         canale Telegram ufficiale di Romeo, 23/10/2024
perché:        "CRT high - Ts" 1.12018: settembre spazza il massimo di agosto e
               torna dentro; ottobre scende al lato opposto.
```

## Verifica sui dati (24/09/2026)

| | Romeo | Il bot | |
|---|---|---|---|
| Range | CRT high 1.12018, CRT low 1.07768 | agosto 2024: H 1.12015, L 1.07774 | ✅ (meno di 1 pip) |
| Manipolazione | settembre sopra 1.12018 | armato il 25/09 alle 17:00 NY (massimo 1.12140) | ✅ |
| Target 2 | CRT low, toccato a fine ottobre | lato opposto toccato il 23/10 | ✅ |
| 50% | 1.09687 | 1.09895 | ❓ la sua linea non è a metà del range: da capire |
| Ingresso | non indicato | **nessun Model#1 sulle giornaliere**: la giornaliera che supera 1.12015 (25/09) chiude in ribasso, con l'ombra sopra | — |

Sulle **4 ore** il Model#1 c'è. Il 25/09 la candela delle 5:00 NY è
rialzista e supera 1.12015 (apertura 1.11848). Quella delle 9:00 NY, la
"Golden candle time", chiude a 1.11344, sotto l'apertura.

**Cosa dice:** il Model#1 può comparire un timeframe sotto quello della
coppia. Su un caso solo non si cambia la regola: è annotato come possibile
variante del Grilletto.

**Cosa ha cambiato:** questo caso ha fatto cadere la prima regola sulla
durata dell'operazione, "fino alla fine della candela d'ingresso".
