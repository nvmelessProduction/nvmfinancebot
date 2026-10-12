# La lavagna (prova)

Pagina in stile TradingView dove il proprietario e il socio segnano key level e setup su grafici storici, per
insegnare il loro occhio alla rete (scuola 3). Pubblicata su claude.ai: https://claude.ai/artifact/Q9L3dThjHAKFwuSnK7wA66
(privata; il socio va aggiunto dal menu Condividi come Contributor).

- `prepara_lezioni.py`: le 24 lezioni di EURUSD (2014-2019, anni in cui la rete impara: l'esame resta pulito), con
  tutti i timeframe da 1 minuto a 12 mesi fino all'istante della lezione, niente futuro. Le candele che il bot conosce
  (1m, 5m, 15m, 1h, 4h, 6h, 12h, giorno e oltre) sono fatte con `costruisci` del bot; 3m, 30m, 45m, 2h e 3h con blocchi
  dalle 17 di New York. Meta' delle lezioni sono setup A+ del bot, meta' istanti a caso: quali, lo dice solo
  `indice_segreto.json`, fuori dalla pagina.
- `lavagna.html`: Lightweight Charts di TradingView, righe (key level), posizione long/short (ingresso, stop, TP1,
  target), calamita, trascinamento, prezzi scrivibili. I disegni vanno nel database della pagina, collezione `disegni`,
  un documento per lezione e persona.

Regola concordata: se i dati o i disegni non tornano, ci si ferma. I disegni entrano nella rete solo in una copia a parte,
che sostituisce l'attuale solo se all'esame va meglio.

## Versione 2 (12/10/2026)

Il proprietario: *"deve essere trading view ... ogni cosa che faccio viene vista da questa rete neurale"*; il lavoro
e' per famiglie (X/USD con DXY, USD/X, incroci col loro indice, metalli, petrolio, crypto con la total market cap).

- `prepara_lezioni2.py`: per ogni lezione lo strumento principale e i suoi confronti (per ora EURUSD con DXY e GBPUSD),
  tutti i timeframe, con il tempo vero di ogni candela (`u`) perche' i disegni restino al loro posto cambiando
  timeframe. Il DXY e' quello del bot (`foto.dxy` dalle 5 coppie: HistData prima del 2019 ha un'altra serie).
- `lavagna.html`: riga, raggio, verticale, tendenza, rettangolo, Fibonacci, long/short (un clic e poi si trascinano
  stop, TP1, target e la fine del box), testo; selezione, trascinamento, colori, "cos'e'" (key level, gap, range CRT,
  liquidita', SMT, bias, sessione), annulla/ripeti, elenco degli oggetti, cambio di simbolo.
- Il percorso: ogni passaggio (apertura, timeframe, simbolo, parte di grafico guardata, disegno creato, modificato o
  cancellato, decisione) con il tempo, salvato in `percorsi` (a pezzi da 150 kB); i disegni finali e il trade in
  `disegni` (versione 2).
