# Dove siamo

_Aggiornato il 24/09/2026._

Ogni sessione di lavoro parte da qui e, prima di chiudere, aggiorna questo
file. Il piano completo è in `PIANO.md`.

## Fasi attuali: A — Specifica, e B — Dati in parallelo

**A.** Il CRT di RomeoTPT si riscrive dalle fonti, partendo dal
**Cacciatore** (l'agente che risponde a "c'è un CRT qui?").

- **Fatto:** fonti raccolte (`spec/FONTI-ROMEO.md`); regole del Cacciatore
  decise sulle fonti, con una variante dichiarata (`spec/cacciatore.md`).
- **Manca:** i casi presi dai grafici pubblicati da Romeo; le schede del
  Grilletto (Model#1) e degli altri agenti.
- **Casi verificati sui dati:** CASO-002 (EURUSD giornaliero), CASO-003
  (EURUSD mensile), CASO-004 (XAUUSD giornaliero). Hanno corretto tre
  regole: la durata dell'operazione (due volte), i tentativi del Grilletto,
  e hanno fatto nascere la variante "stop stretto".
- **Varianti dichiarate:** 2 su 3. "Chiusura dentro" per il Cacciatore,
  "stop stretto" per Livelli.
- **Già pronto per la Fase C:** il codice del Cacciatore
  (`nvm/agenti/cacciatore.py`), con la variante dichiarata e le prove sugli
  schemi di Romeo, compresa quella che controlla che non sbirci il futuro.
  Non si considera buono finché non passa i casi.

**B.** Una fonte sola, candele ricostruite con la giornata che chiude alle
17:00 di New York (`spec/dati.md`).

- **Fatto:** scaricatore, candele, controlli (`nvm/dati/`, `scarica.py`).
  Verificato il pacchetto del vecchio branch: minuti e orarie giusti, 4 ore
  e giornaliere su confini sbagliati (`registro/verifica-dati-vecchi.md`).
- **Fatto:** vent'anni di ore con bid e ask per i sei strumenti, dai file
  Dukascopy del vecchio bot. Verificati identici, bid e ask, a quelli
  scaricati direttamente. Mancano cinque mesi prima del 2024 (tre di
  USDJPY, due di XAUUSD), in scaricamento. AUDUSD 2007–2010 ha dati sporchi
  (buchi, ask sotto il bid): da tenere presente.

### Cosa serve da te

- [x] **Spegnere il vecchio bot sulla VPS.** Fatto il 24/09.
- [ ] **Rigenerare il token Telegram.** Il `.env` caricato l'11/09 è ancora
      nella storia del vecchio branch, e con lui il token. Su Telegram:
      @BotFather → `/revoke` → scegli il bot. Il token nuovo va solo nel
      `.env` sul computer.
- Niente altro: l'utente ha chiesto di fare tutto da qui (24/09). La VPS
  resta ferma; `VPS.md` e `scarica.bat` restano pronti se un giorno servono.

Le domande sulla strategia non le fai tu: le risposte si cercano nelle
fonti, e dove le fonti non bastano si provano le letture possibili.

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
| 24/09/2026 | L'utente non può rispondere alle domande sulla strategia: le risposte si cercano nelle fonti, e dove non bastano si dichiarano varianti. I casi si prendono dai grafici pubblicati da Romeo. |
| 24/09/2026 | L'utente chiede di procedere senza fermarsi. Le domande della bozza ancora senza risposta diventano **varianti dichiarate** (al massimo 3, `PIANO.md` §3), da misurare invece che scegliere. La Fase B (dati) parte in parallelo alla A, perché non dipende dalla specifica del CRT. |
| 24/09/2026 | Due canali Telegram, già collegati. **Operativo:** avvio del bot, decisioni di apertura, chiusure, avvisi urgenti. **Équipe:** solo la comunicazione fra gli agenti, sempre attivo, con il rendiconto principale nel fine settimana. |

## Domande aperte

Si decidono durante la Fase A.

- **Strumenti:** quali? Il vecchio bot usava EURUSD, GBPUSD, USDCHF, USDJPY,
  AUDUSD e XAUUSD, ma dal vivo operava quasi solo sull'oro.
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

### La base (Fase D), misurata il 24/09/2026

Tutti i CRT col manuale (Cacciatore → Grilletto → Livelli), 2006–2023, sei
strumenti, orarie Dukascopy con **bid e ask veri** e commissioni. Il
2024–2026 è chiuso. Intervallo al 95% a blocchi settimanali.

| Coppia | Operazioni | R medio | IC95 |
|---|---:|---:|---|
| mensile → giornaliero | 1.876 | −0,008 | [−0,105; +0,098] |
| settimanale → 4 ore | 9.289 | −0,047 | [−0,099; +0,008] |
| giornaliero → 1 ora | 38.524 | −0,072 | [−0,094; −0,050] |
| **tutto** | **49.689** | **−0,065** | **[−0,087; −0,043]** |

È il numero da battere. Per passare, la Fase F deve fare almeno +0,10 R
meglio di questo, con i criteri del `PIANO.md` §2.

Com'è fatta (giornaliero → 1 ora): 63% allo stop, 17% al target (+2,7 R
in media), 19% in pareggio dopo il primo target; 41 operazioni a settimana
su sei strumenti; stop mediano su EURUSD di 25 pip. Romeo dice "1-2 a
settimana" e usa stop di 1-5 pip: filtri e stop stretto sono le prime cose
da guardare.

La coppia 4 ore → 15 minuti non si può ancora misurare: servono i quindici
minuti di vent'anni, che non ci sono.

## Fasi

| Fase | Stato |
|---|---|
| A. Specifica | in corso |
| B. Dati | in corso |
| C. Cacciatore | — |
| D. La base | fatta per tre coppie su quattro (24/09) |
| E. Gli altri agenti | — |
| F. Capo e apprendimento | — |
| G. Verifica finale | — |
| H. Dal vivo, in demo | — |

## Da fare dopo

Idee fuori dalla fase attuale. Si annotano qui e si fanno quando tocca.

- _(vuoto)_
