# CASO-008 — EURUSD, CRT giornaliero, 30 settembre – 2 ottobre 2025

```
id:            CASO-008
tipo:          CRT
strumento:     EURUSD
coppia:        D1 -> H1
candela_range: la giornaliera di martedì 30/09/2025 (apre il 29/09 alle 17 NY): H 1.17615, L 1.17119
manipolazione: mercoledì 01/10, fino a 1.17785 alle 3:00 NY
rientro:       la barra delle 3:00 NY chiude a 1.17498, sotto l'apertura della barra rialzista delle 2:00
verso:         SHORT
ingresso:      "SELL 21" circa 1.17599 e "SELL 60" circa 1.17587 (msg 6415)
stop:          appena sopra, intorno a 1.1762
target:        la linea sotto, intorno a 1.1710: il CRT low
esito:         il 02/10 il prezzo è sul CRT low ("CRT is trading")
immagine:      https://t.me/officialRomeotpt/6415
fonte:         canale Telegram ufficiale di Romeo, 02/10/2025
```

## Verifica sui dati (24/09/2026)

| | Romeo | Il bot | |
|---|---|---|---|
| Range | le linee a 1.1760 e 1.1710 | H 1.17615, L 1.17119 | ✅ |
| Ingresso | 1.1759, dentro la barra delle 3:00 dopo il massimo | primo Model#1: TS alle 2:00 NY, scatto alle 3:00, ingresso 1.17498 | ✅ stesso colpo, 10 pip più in basso |
| Stop | circa 1.1762 | 1.17785 (l'estremo); stop stretto 1.17547 | ⚠️ |
| Esito | CRT low toccato il 02/10 | 50% preso alle 5:00, poi **pareggio** alle 8:00 NY (+0,20 R); il CRT low arriva il 02/10 alle 11:00 | ⚠️ |

Qui il pareggio dopo il 50% toglie al bot il secondo target. Anche lo stop
di Romeo, intorno a 1.1762, sarebbe stato toccato dalla barra delle 8:00
(massimo 1.17688) sui prezzi di Dukascopy: o il suo feed è diverso, o ha
chiuso prima. Il caso resta segnato come dubbio sull'esito, non sulle
regole.
