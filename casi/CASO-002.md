# CASO-002 — EURUSD, CRT giornaliero, dicembre 2024

```
id:            CASO-002
tipo:          CRT
strumento:     EURUSD
coppia:        D1 -> ?             # il grafico è giornaliero
candela_range: la candela verde grande di inizio dicembre 2024 (circa 5/12)
manipolazione: la candela dopo, con l'ombra sopra il massimo della verde (cerchiata)
rientro:       la stessa candela chiude sotto il massimo della verde
verso:         SHORT
ingresso:      "Entry in the wick": dentro l'ombra, sopra il massimo della verde
stop:          sopra, intorno a 1.0580-1.0600 (linea "SL" sullo screenshot)
target:        il minimo della verde, circa 1.0506 (linea nera)
esito:         una candela rossa grande arriva a circa 1.0506
immagine:      https://t.me/officialRomeotpt/5730
fonte:         canale Telegram ufficiale di Romeo, "EURUSD CRT. Entry in the wick.", 10/12/2024
perché:        la candela 2 spazza il CRT high e chiude dentro; l'obiettivo è il
               CRT low. È lo schema "candle opens, stabs into an old CRTH, dumps".
```

## Da verificare sui dati

- Le date esatte delle candele e i livelli, sulle giornaliere che chiudono
  alle 17:00 di New York (`spec/dati.md`).
- Dove sta lo stop rispetto all'estremo dell'ombra.
