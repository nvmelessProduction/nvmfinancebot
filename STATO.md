# Dove siamo

_Aggiornato il 24/09/2026._

Ogni sessione di lavoro parte da qui e, prima di chiudere, aggiorna questo
file. Il piano completo è in `PIANO.md`.

## Fase attuale: A — Specifica

Si riscrive insieme il **CRT di RomeoTPT**, partendo dal **Cacciatore**
(l'agente che risponde a "c'è un CRT qui?"), e si raccolgono i casi annotati.

- **Fatto:** le fonti su Romeo sono raccolte (`spec/FONTI-ROMEO.md`) e la
  bozza del Cacciatore è scritta (`spec/cacciatore.md`).
- **Manca:** le tue risposte alle domande della bozza, l'approvazione e i
  casi.

### Cosa serve da te

- [ ] **Spegnere il vecchio bot sulla VPS.** Vedi sotto.
- [ ] **Rigenerare il token Telegram.** Il `.env` caricato l'11/09 è ancora
      nella storia del vecchio branch, e con lui il token. Su Telegram:
      @BotFather → `/revoke` → scegli il bot. Il token nuovo va solo nel
      `.env` sul computer.
- [ ] **Leggere la bozza del Cacciatore** (`spec/cacciatore.md`) e
      rispondere alle 7 domande in fondo, con quello che hai imparato dai
      video di Romeo. Le fonti trovate in rete sono in `spec/FONTI-ROMEO.md`.
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
| 24/09/2026 | Ogni agente fa carriera (neolaureato → in prova → promosso), e sopra tutti c'è il Capo, che impara anche lui. |
| 24/09/2026 | Due tempi: l'apertura delle operazioni avviene tutta in memoria; la riunione (riallenamento, consigli, promozioni) è staccata e non la rallenta mai. |
| 24/09/2026 | Gli agenti si danno consigli nella riunione senza influenzarsi: un consiglio è un'ipotesi che solo l'agente responsabile può provare, con il cancello. Tutto si vede nel canale Telegram dell'équipe. |
| 24/09/2026 | Due canali Telegram, già collegati. **Operativo:** avvio del bot, decisioni di apertura, chiusure, avvisi urgenti. **Équipe:** solo la comunicazione fra gli agenti, sempre attivo, con il rendiconto principale nel fine settimana. |

## Domande aperte

Si decidono durante la Fase A.

- **Strumenti:** quali? Il vecchio bot usava EURUSD, GBPUSD, USDCHF, USDJPY,
  AUDUSD e XAUUSD, ma dal vivo operava quasi solo sull'oro.
- **Il CRT di Romeo:** le 7 domande in fondo a `spec/cacciatore.md`.
- **Fonte dei prezzi:** una sola per tutti i timeframe. Il vecchio progetto
  mescolava future, CFD, Dukascopy e MT5, e molti errori venivano da lì.
- **Canale équipe: un bot o uno per agente?** Un solo bot che scrive col
  nome di ogni agente è più semplice. Un bot per agente, ognuno con il suo
  nome e la sua foto, rende l'équipe più viva, ma vuol dire crearne una
  decina con @BotFather. Si decide prima della Fase F.
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
