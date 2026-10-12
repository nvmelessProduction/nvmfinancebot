# CASO-004 — XAUUSD, CRT giornaliero, 16–19 luglio 2024

```
id:            CASO-004
tipo:          CRT
strumento:     XAUUSD
coppia:        D1 -> H1
candela_range: la giornaliera del 16/07/2024 (apre il 15/07 alle 17 NY): H 2469.58, L 2419.84
manipolazione: il 17/07, fino a 2483.55 ("TS" sul suo grafico)
rientro:       Model#1 sulle orarie: alle 9:00 NY del 17/07 una candela rialzista spessa
               (2473.26 -> 2482.85) spazza i massimi; alle 10:00 NY chiude a 2463.60, sotto
verso:         SHORT
ingresso:      "SELL 3" intorno a 2466.36 (screenshot MT5)
stop:          2474.00 (screenshot MT5)
target:        la linea nera intorno a 2420, cioè il CRT low
esito:         il 19/07 il prezzo è sotto 2420 e la posizione è ancora aperta
immagine:      https://t.me/officialRomeotpt/5198
fonte:         canale Telegram ufficiale di Romeo, "CRT > everything.", 20/07/2024
```

## Verifica sui dati (24/09/2026)

| | Romeo | Il bot | |
|---|---|---|---|
| Range e target | CRT low intorno a 2420 | 2419.84 | ✅ |
| Ingresso | circa 2466 | **secondo** Model#1: 17/07 alle 11:00 NY, 2463.60 | ✅ |
| Stop | 2474.00 | stop stretto: 2474.47; stop all'estremo: 2483.55 | ✅ con lo stop stretto |
| Esito | ancora aperta, prezzo sotto 2420 | stop all'estremo: target, +1,57 R. Stop stretto: stoppato il 18/07 a 2474.8, per 30 centesimi | ⚠️ feed diversi |

## Cosa ha cambiato

1. **Il Grilletto spara più di una volta.** Il primo Model#1 (1:00 NY del
   17/07) viene stoppato dalla spinta delle 9:00. L'operazione di Romeo è
   quella dopo, e la candela che stoppa il primo tentativo è proprio il
   turtle soup nuovo ("one last turtle soup", il KOD). Ora il Grilletto può
   ritentare dopo uno stop, fino a 3 volte per CRT, e il turtle soup nuovo
   può essere la candela stessa dello stop.
2. **Lo stop stretto diventa una variante dichiarata di Livelli:** oltre il
   livello del Model#1 invece che oltre l'estremo. È quello che Romeo fa in
   tutte le operazioni pubblicate con lo stop visibile (1–5 pip su EURUSD e
   GBPUSD). Qui torna al dollaro, ma basta 1 dollaro di differenza fra feed
   per cambiare l'esito: la misura su migliaia di operazioni deciderà.
