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

## Verifica sui dati (24/09/2026)

Orarie Dukascopy, giornaliere che chiudono alle 17:00 di New York.

| | Romeo | Il bot | |
|---|---|---|---|
| Range | la candela verde grande | la giornaliera del 5/12/2024 (apre il 4/12 alle 17 NY): H 1.05896, L 1.05077 | ✅ |
| Manipolazione | l'ombra cerchiata sopra la verde | armato il 6/12 alle 04:00 NY, massimo 1.06298 | ✅ |
| Ingresso | "entry in the wick", vendita intorno a 1.0580 | Model#1 sulle orarie, scatto il 6/12 alle 10:00 NY a **1.05788** | ✅ |
| Target | la linea nera a 1.05064 | CRT low 1.05077 | ✅ (1,3 pip) |
| Esito | il target arriva il 10/12 | 50% preso il 9/12, target 2 il 10/12, cioè nella **candela 4** | ⚠️ |

**Cosa ha cambiato:** la durata dell'operazione. La regola "fino alla fine
della candela 3" avrebbe chiuso il resto lunedì 9 sera, prima del target.
Ora non c'è uscita a tempo (`spec/grilletto.md`).

Lo stop dello screenshot non si legge bene: resta da capire.
