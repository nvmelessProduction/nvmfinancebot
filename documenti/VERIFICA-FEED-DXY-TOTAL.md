# Verifica dei feed DXY e TOTAL per la fase 3

Data della verifica: 16 ottobre 2026. Riferimento codice: branch `claude/zealous-albattani-394cd9`.

## Perché la fase 3 non è ancora una prova della strategia live

Il bot live in `nvm/vivo/giro.py` usa due contesti esterni: per le coppie FX con USD il CRT del DXY genera verso e timeframe, mentre la coppia locale conferma; BTC ed ETH seguono il CRT di TOTAL. Queste regole sono esplicite in `occasioni_foto()`.

La scuola del Capo in `kaggle_rete/capo.py` costruisce invece setup e risultati dai CRT locali contenuti in `materie.crt`, per ciascun mercato. Non carica una serie storica DXY/TOTAL per applicare l'instradamento del live. L'esito negativo di questa fase, quindi, non è ancora un test conclusivo della strategia DXY/TOTAL richiesta: serve prima un dataset coerente e la stessa logica di segnali.

C'è anche una discrepanza da risolvere nella scelta del simbolo DXY: `nvm/vivo/ambiente.py` documenta `CAPITALCOM:DXY` come default, mentre il commento in `nvm/vivo/giro.py` nomina FP Markets USDX. Il file `.env` non è nel repository e non va caricato qui; la configurazione effettiva va letta in modo locale e senza stampare segreti.

## Feed alternativi verificati

### DXY

- L'API ufficiale Capital.com espone prezzi storici in candele con risoluzione `HOUR`, intervallo `from/to` e massimo 1.000 barre per richiesta. Richiede una sessione API del conto; documentazione: [Capital.com Public API](https://open-api.capital.com/).
- Capital.com offre il CFD sullo US Dollar Index e il codice già cita `CAPITALCOM:DXY`. È il primo candidato da confrontare con la configurazione effettiva, ma bisogna verificare l'epic disponibile nel conto e quanta storia oraria è scaricabile.
- ICE descrive il DXY ufficiale come indice calcolato intraday dai prezzi midpoint delle sei valute componenti e offre serie intraday a un'ora. È un riferimento autorevole, ma non dimostra che la serie coincida con il CFD del broker; accesso e licenza vanno quotati direttamente da ICE. [ICE U.S. Dollar Index](https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices) · [ICE serie orarie I60](https://developer.ice.com/fixed-income-data-services/guides/ice-python-user-guide-overview/gettimeseries)

### TOTAL

- CoinDesk Data documenta il feed **MktCap Historical OHLCV — All Assets Hour**, con OHLC orari della capitalizzazione totale degli asset che superano i suoi criteri di volume e listing; l'endpoint supporta paginazione fino a 2.000 punti per richiesta. È la migliore alternativa API individuata per generare i CRT su una serie di capitalizzazione aggregata: [endpoint CoinDesk](https://developers.coindesk.com/documentation/data-api/overview_v1_historical_marketcap_all_assets_hours).
- Non è la stessa definizione di TradingView `CRYPTOCAP:TOTAL`: TradingView dichiara che TOTAL somma la capitalizzazione dei 125 cryptoasset in cima al proprio screener e che la composizione storica può cambiare o essere ricalcolata. CoinDesk applica criteri propri, quindi i CRT possono divergere. [metodo TradingView per TOTAL](https://www.tradingview.com/support/solutions/43000550480-where-do-i-find-crypto-market-capitalization-and-dominance/) · [variazioni storiche di CRYPTOCAP](https://www.tradingview.com/support/solutions/43000540941-crypto-market-capitalization-data-is-incorrect-being-recalculated/).
- La pagina piani CoinDesk indica 7 giorni di storico orario nel piano Personal, 30 nel piano Start-Up e oltre 10 anni nell'accesso Enterprise; il piano Start-Up richiede un preventivo. Va verificato che l'endpoint specifico sia incluso nel piano scelto prima di costruire il backtest lungo. [piani e copertura CoinDesk](https://developers.coindesk.com/pricing/).
- L'endpoint storico Global Metrics di CoinMarketCap fornisce un punto di quotazione per intervallo, non candele OHLC del TOTAL. I relativi OHLC orari sono per singola criptovaluta. Non basta per identificare massimi/minimi del CRT aggregato. [CoinMarketCap Global Metrics](https://coinmarketcap.com/api/documentation/pro-api-reference/global-metrics) · [OHLCV per singola crypto](https://coinmarketcap.com/api/documentation/pro-api-reference/cryptocurrency).

## Vincolo di licenza per l'uso online

Il codice in `nvm/vivo/tradingview.py` acquisisce i grafici tramite il server MCP ufficiale di TradingView. La documentazione MCP attuale lo limita all'uso personale interattivo ed esclude raccolta automatica/non supervisionata e l'alimentazione di sistemi automatici di trading o decisione. Quindi un bot pianificato che usa quei dati per generare segnali non può essere messo online su quel feed senza una licenza o autorizzazione esplicita compatibile. [Regole del server MCP](https://www.tradingview.com/support/solutions/43000795699-mcp-server-connect-your-ai-assistant-to-tradingview/) · [Termini TradingView](https://www.tradingview.com/policies/).

Questo vincolo si applica già allo shadow automatico e al backtest che usano dati MCP; cambiare soltanto il feed DXY/TOTAL non basta se le candele degli asset tradati continuano ad arrivare da TradingView. Il percorso per l'uso online richiede dunque feed autorizzati per tutte le serie usate dal bot (DXY, TOTAL e strumenti operati), oppure un'autorizzazione scritta specifica di TradingView. Il piano di valutazione non deve acquisire automaticamente dati MCP né usarli in un confronto machine-driven.

## Percorso raccomandato

1. Verificare la copertura, il mapping dei simboli e le condizioni d'uso di Capital.com per DXY e degli strumenti effettivamente tradati. Per TOTAL, valutare il feed OHLC CoinDesk e ottenere conferma che il piano/licenza copra l'uso previsto dal bot automatico.
2. Se si accetta una definizione di TOTAL diversa dal top-125 TradingView, trattare Capital.com/CoinDesk come una nuova variante della strategia: usare solo le serie dei feed autorizzati, con orari UTC e candele chiuse, e registrare fonte, metodo, versione, timestamp di acquisizione e copertura.
3. Modificare la fase 3 affinché ricostruisca l'instradamento live FX/DXY e BTC/ETH/TOTAL e usi le stesse fonti autorizzate, candele, fusi e regole di esecuzione. La validazione deve includere dataset e mapping nel rapporto dell'esame.
4. Se è requisito riprodurre esattamente i simboli di TradingView, fermarsi prima della raccolta automatica e richiedere una licenza/autorizzazione scritta per quello specifico uso. Senza quella, la fase 3 e l'online vanno valutati con una strategia basata su feed alternativi, senza presentarla come identica.

Non sono stati acquistati piani API, usate credenziali o modificati i bot operativi. Il prossimo avanzamento tecnico è verificare le condizioni d'uso e la copertura dei feed candidati, poi implementare un downloader/normalizzatore per le fonti autorizzate. Le chiavi API vanno conservate nei segreti di Kaggle o del server, mai in chat o nel repository.
