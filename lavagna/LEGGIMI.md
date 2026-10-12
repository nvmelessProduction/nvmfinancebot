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
