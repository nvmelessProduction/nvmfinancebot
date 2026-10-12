# nvmfinancebot

Bot di trading che analizza i grafici (TradingView o MT5), decide con la rete neurale e opera da solo su MT5
(conto demo), spiegando ogni scelta su Telegram. Il metodo è il CRT di Romeo come lo usa il proprietario (il
metodo delle foto), con la strategia del libro del socio in arrivo.

Il progetto è ripartito da zero il 24/09/2026. Il lavoro precedente è archiviato sul branch
`claude/trading-bot-infrastructure-5rht0h`.

## Com'è fatta la cartella

| Dove | Cosa |
|---|---|
| `vivo.py` | il bot dal vivo (lo lancia `avvia.bat`) |
| `*.bat` | i doppi clic sulla VPS: `avvia`, `avvio_automatico`, `tradingview_accesso`, `rete_installa`, `scarica`, `scarica_nuovi`, `scarica_video`, `consegna` |
| `nvm/` | tutto il codice: `vivo/` il bot dal vivo, `agenti/` le regole del metodo, `intelligenti/` la squadra, `rete/` e `cervello/` le reti neurali, `dati/` candele e scaricamento, `prova/` le misure sullo storico |
| `strumenti/` | gli script da lanciare a mano (misure, allenamento, scaricamento, consegna dei dati, accesso a TradingView), come moduli: `python -m strumenti.misura`; `strumenti/lavagna/` la pagina per segnare i setup |
| `kaggle_rete/` | l'allenamento della rete neurale su Kaggle |
| `mt5/` | gli indicatori che il bot installa su MT5 per disegnare sul grafico |
| `tests/` | le prove (`python -m pytest`) |
| `documenti/` | tutto quello che si legge: vedi sotto |

## Da dove si comincia

| File | Cosa |
|---|---|
| `documenti/STATO.md` | dove siamo, cosa serve adesso, decisioni prese. **Si legge per primo.** |
| `documenti/VPS.md`, `documenti/AVVIO.md` | come si installa e si avvia il bot sulla VPS |
| `documenti/MANUALE.md` | come si usa il bot |
| `documenti/PIANO.md` | l'équipe, come imparano gli agenti, le fasi, le regole del gioco |
| `documenti/spec/` | le regole scritte con parole semplici: `metodo_foto.md` (quello che usa il bot), `metodo_romeo.md`, `metodo_libro.md`, una scheda per agente |
| `documenti/casi/` | i casi annotati dai grafici e le foto d'esempio del proprietario (`foto/`) |
| `documenti/registro/` | ogni prova fatta, anche quelle andate male, e le misure |
