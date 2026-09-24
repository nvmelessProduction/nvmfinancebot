# Dove siamo

_Aggiornato il 24/09/2026._

Ogni sessione di lavoro parte da qui e, prima di chiudere, aggiorna questo
file. Il piano completo è in `PIANO.md`.

## Fase attuale: A — Specifica

Si riscrive insieme il **CRT di RomeoTPT**, partendo dal **Cacciatore**
(l'agente che risponde a "c'è un CRT qui?"), e si raccolgono i casi annotati.

### Cosa serve da te

- [ ] **Spegnere il vecchio bot sulla VPS.** Vedi sotto.
- [ ] **Rigenerare il token Telegram.** Il `.env` caricato l'11/09 è ancora
      nella storia del vecchio branch, e con lui il token. Su Telegram:
      @BotFather → `/revoke` → scegli il bot. Il token nuovo va solo nel
      `.env` sul computer.
- [ ] **Le fonti di Romeo:** i link ai video e ai post da cui prendi la
      strategia. Ogni regola della specifica dovrà dire da dove viene.
- [ ] **Raccontare il CRT con parole tue**, come lo fa Romeo: da lì scriviamo
      insieme la scheda del Cacciatore.
- [ ] **Casi annotati:** almeno 20 CRT e 10 "sembra un CRT ma non lo è", con
      il modello `casi/MODELLO-CASO.md`. Meglio se presi dai grafici che
      Romeo stesso mostra. Uno screenshot con due orari basta: i prezzi li
      ricaviamo dai dati.

### Come si spegne il vecchio bot

1. Sulla VPS chiudi la finestra di `avvia.bat`. Se la chiudi con Ctrl+C,
   rispondi `S`. Finché la finestra è aperta, il bot riparte da solo dopo 15
   secondi.
2. Windows+R → `shell:startup` → cancella il collegamento al bot, così non
   riparte alla prossima accensione.
3. In MetaTrader 5 chiudi a mano le posizioni demo ancora aperte e spegni il
   pulsante **Algo Trading**.

## Decisioni prese

| Data | Decisione |
|---|---|
| 24/09/2026 | Si riparte da zero. Il vecchio branch `claude/trading-bot-infrastructure-5rht0h` resta come archivio e non si cancella. |
| 24/09/2026 | La strategia di partenza è il CRT di RomeoTPT (@Romeotpt). |
| 24/09/2026 | La specifica si riscrive: i vecchi documenti non valgono più come riferimento. |
| 24/09/2026 | Il vecchio bot sulla VPS si ferma. |
| 24/09/2026 | Architettura ad agenti. Gli agenti imparano sia sullo storico sia dal vivo, sempre dietro il cancello del `PIANO.md` §2. |

## Domande aperte

Si decidono durante la Fase A.

- **Strumenti:** quali? Il vecchio bot usava EURUSD, GBPUSD, USDCHF, USDJPY,
  AUDUSD e XAUUSD, ma dal vivo operava quasi solo sull'oro.
- **Coppie di timeframe** su cui cercare il CRT. I vecchi documenti si
  contraddicevano: uno diceva settimanale → giornaliero e 4 ore → 1 ora,
  l'altro settimanale → 4 ore e 4 ore → 15 minuti. Cosa fa Romeo?
- **Quanto si aspetta dopo il CRT** prima che il setup decada, su ogni coppia.
- **Il target:** il lato opposto del range, o un livello chiave? Anche qui i
  vecchi documenti si contraddicevano.
- **Fonte dei prezzi:** una sola per tutti i timeframe. Il vecchio progetto
  mescolava future, CFD, Dukascopy e MT5, e molti errori venivano da lì.
- **Rischio per operazione, e cifra del conto demo.** Il vecchio conto demo
  era stato portato a 1.000.000 €, con operazioni da 50 lotti d'oro: in 7
  ore −13.915 €. Il demo deve avere la cifra che useresti davvero.

## Numeri validi

Nessuno, per ora.

Solo come riferimento, dal vecchio progetto: prendendo tutti i CRT dal 2006
al 2023, con i costi, la base rendeva −0,05 R per operazione. Va rimisurato:
il nuovo Cacciatore sarà diverso.

## Fasi

| Fase | Stato |
|---|---|
| A. Specifica | in corso |
| B. Dati | — |
| C. Cacciatore | — |
| D. La base | — |
| E. Gli altri agenti | — |
| F. Capo e apprendimento | — |
| G. Verifica finale | — |
| H. Dal vivo, in demo | — |

## Da fare dopo

Idee fuori dalla fase attuale. Si annotano qui e si fanno quando tocca.

- _(vuoto)_
