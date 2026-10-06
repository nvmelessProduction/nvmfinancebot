# CASO-009 — Oro, CRT a 4 ore, 8 novembre 2022 (esempio base del proprietario)

Esempio fatto dal proprietario sul future dell'oro (COMEX) in TradingView, con lo schema di
`07_casi`. Foto: `casi/img/CASO-009.png`. Orari della foto: ora italiana (UTC+1 a novembre).

```
id:            CASO-009
tipo:          CRT
strumento:     oro (future COMEX); da noi XAUUSD
coppia:        H4 (key level dal giornaliero)
candela_range: N1 08/11/2022 04:00-08:00 italiane: H 1676,5  L 1670,7
manipolazione: N2 08:00-12:00: H 1674,3  L 1667,1 (spazza il minimo di N1 e il minimo
               del giorno prima, DL 1670,1, ed entra nel vuoto giornaliero)
rientro:       N2 chiude dentro il range; N3 apre alle 12:00 a 1672,9
verso:         LONG
ingresso:      1672,9, all'apertura della candela 3 (12:00 italiane, 06:00 New York)
stop:          1667,2, sotto il minimo della candela 2
target:        TP1 1676,5 = massimo del CRT ("chiusura CRT H4"), poi stop a pareggio;
               target finale 1686,4, appena sopra il massimo del giorno (DH 1685,7)
esito:         TP finale, +2,37 R (rischio/rendimento sul TP1: 0,63)
bias:          rialzista, dal timeframe annuale (vuoto annuale; minimo dell'anno prima a 1673,5)
allineati:     H4 e H6 fanno tutti e due un CRT e aprono tutti e due alle 12:00
etichetta:     CONFORME (del proprietario)
immagine:      casi/img/CASO-009.png
fonte:         il proprietario, foto del 06/10/2026
```

## Verifica sui dati (06/10/2026)

I nostri dati sono l'oro spot di Dukascopy, a 1 ora: i prezzi stanno circa 2,6 sotto quelli del
future. I 15 minuti del 2022 non li abbiamo, quindi la prova del Grilletto è fatta sulle ore.

Le candele a 4 ore del future partono alle 18 di New York (mezzanotte italiana), quelle di MT5 e
le nostre alle 17: un'ora prima. Con le candele del future (UTC 03-07, 07-11) i numeri tornano: N1
spot 1673,80-1668,00 (ampiezza 5,8 come nella foto), N2 1671,89-1664,56, N3 apre a 1670,36. Con le
nostre il CRT c'è lo stesso, un'ora prima.

| | Il proprietario | Il bot | |
|---|---|---|---|
| CRT rialzista | N1, N2 che spazza e richiude, N3 | lo stesso: range 02:00 UTC, finta 06:00, candela 3 dalle 10:00 UTC; finisce sul lato opposto | ✅ |
| Key level | minimo del giorno prima (DL) | "un vecchio minimo mai ripreso" a 1666,71 = il minimo del 07/11 | ✅ |
| Vuoto giornaliero | la candela 2 ci entra | il vuoto spot 1640,86-1666,71 c'è; il bot vede quello a 4 ore (1671,96) | ✅ in parte |
| Entrata | all'apertura della candela 3 | aspetta nella candela 3 un Model#1, una vera rottura o un kiss of death: quel giorno nessuno | ❌ il bot non entra |
| Primo obiettivo | il massimo del CRT, poi pareggio | il 50% del range: la candela 3 lo tocca nella prima ora, e per il bot "il 50% è già preso" | ❌ |
| Obiettivo finale | il massimo del giorno (DH), la liquidità sopra | il lato opposto del range, o mezza ampiezza oltre | ❌ |
| Stop | sotto il minimo della candela 2 | sotto la punta della candela di conferma | ❌ |
| Bias | dal timeframe annuale | dal giornaliero e dai CRT più grandi | ⚠️ |
| H4 e H6 allineati | conferma | il 6 ore non c'è | ⚠️ |

Il periodo (2022) non è nel 2024–2026 chiuso.
