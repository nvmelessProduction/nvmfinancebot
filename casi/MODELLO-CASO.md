# Come si annota un caso

Un caso è un pezzo di grafico su cui tu sai già la risposta giusta. Il codice
dovrà ritrovarlo esattamente così: i casi sono il metro con cui si misura se
il codice ha capito la regola.

Un file per caso: `casi/CASO-001.md`, `casi/CASO-002.md`, … Lo screenshot va
in `casi/img/` con lo stesso numero.

**Se ti manca un prezzo esatto, scrivi solo l'orario**: i prezzi li
ricaviamo dai dati. Contano lo screenshot e gli orari.

## Modello da copiare

```
id:            CASO-001
tipo:          CRT                  # CRT oppure NON-CRT
strumento:     EURUSD
coppia:        H4 -> M15            # timeframe del range -> timeframe di ingresso
candela_range: 2026-09-10 08:00     # apertura della candela del range, ora UTC
manipolazione: 2026-09-10 12:15     # la barra che esce dal range
rientro:       2026-09-10 12:30     # la barra che richiude dentro il range
verso:         SHORT                # LONG oppure SHORT
ingresso:                           # prezzo o orario, se lo sai
stop:
target:
esito:                              # se lo sai: target, stop, pareggio
immagine:      casi/img/CASO-001.png
fonte:         video di Romeo "…", minuto 12:40
perché:        una o due frasi: cosa lo rende un CRT, oppure perché non lo è
```

## Che casi servono

- **Almeno 20 CRT** puliti, su strumenti e orari diversi.
- **Almeno 10 NON-CRT**: grafici che sembrano un CRT ma non lo sono, con il
  motivo. Sono i più preziosi, perché insegnano al codice dove fermarsi.
- **Qualche caso al limite**, quando ti capita: quelli su cui esiteresti
  anche tu. Scrivi cosa faresti e perché.
