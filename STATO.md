# Dove siamo

_Aggiornato il 24/09/2026._

Ogni sessione di lavoro parte da qui e, prima di chiudere, aggiorna questo
file. Il piano completo è in `PIANO.md`.

## Fasi attuali: A — Specifica, B — Dati, E — Gli altri agenti (dopo la prima prova del Capo)

**A.** Il CRT di RomeoTPT si riscrive dalle fonti, partendo dal
**Cacciatore** (l'agente che risponde a "c'è un CRT qui?").

- **Fatto:** fonti raccolte (`spec/FONTI-ROMEO.md`); regole del Cacciatore
  decise sulle fonti, con una variante dichiarata (`spec/cacciatore.md`);
  schede del Grilletto (`spec/grilletto.md`) e delle prime conferme
  (`spec/conferme.md`).
- **Manca:** altri casi fino a 20 CRT, e i casi "non è un CRT"; le schede
  di Rischio e Sentinella. CASO-001 (GBPUSD a 15 minuti) aspetta i minuti.
- **Casi verificati sui dati:** sette, da CASO-002 a CASO-008 (EURUSD
  giornaliero, settimanale e mensile, XAUUSD giornaliero, 2024–2025). Il
  bot ritrova tutti i CRT di Romeo, con livelli entro 1–2 pip. Hanno
  corretto tre regole: la durata dell'operazione (due volte), i tentativi
  del Grilletto, e hanno fatto nascere la variante "stop stretto". Dove si
  vede l'ingresso, Romeo entra su un timeframe più basso e più in alto del
  bot, spesso al secondo colpo. Obiettivo del PIANO: 20 CRT e 10 "non è un
  CRT"; per ora 8 e 0.
- **Fonte nuova (msg 6718, febbraio 2026):** una pagina del manuale di
  Romeo, "Elements of a high probability trade setup": key level del
  timeframe alto, ora della manipolazione, massimo prima della
  manipolazione; *"ignore the fvgs, obs, brks"*.
- **Varianti dichiarate:** 3 su 3, e non se ne aggiungono altre. "Chiusura
  dentro" per il Cacciatore, "stop stretto" per Livelli, "un gradino sotto"
  per il Grilletto (scritta il 24/09 prima di misurarla,
  `spec/grilletto.md`).
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
  scaricati direttamente. I cinque mesi che mancavano prima del 2024 sono
  stati scaricati il 24/09: lo storico 2006–2023 è completo. AUDUSD
  2007–2010 ha dati sporchi (buchi, ask sotto il bid): da tenere presente.
- **Manca:** i quindici minuti e i minuti di vent'anni (per la coppia 4 ore
  → 15 minuti e per entrare come Romeo, sul timeframe basso). Da qui
  Dukascopy risponde piano: un mese di ore richiede da 30 secondi a 10
  minuti.

**E.** Le prime conferme sono scritte, provate e misurate
(`spec/conferme.md`, `nvm/agenti/conferme.py`): key level, orario, bias.
Nessuna, da sola, separa le operazioni buone dalle cattive in modo stabile.

**F, prima prova (24/09).** Il Capo (`spec/capo.md`, `nvm/agenti/capo.py`,
`capo.py`) ha pesato le conferme anno per anno, senza guardare avanti, in
quattro configurazioni. **Nessuna passa il cancello**, e il Capo non si
fida delle conferme: guarda quasi solo quanto sono lontani target e stop.
Come dice la scheda, la Fase F non è chiusa e si torna agli agenti. Il
prossimo agente da provare è l'ingresso sul timeframe basso, come fa
Romeo: servono i minuti.

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
| mensile → giornaliero | 1.884 | −0,013 | [−0,112; +0,086] |
| settimanale → 4 ore | 9.314 | −0,053 | [−0,105; +0,002] |
| giornaliero → 1 ora | 38.608 | −0,078 | [−0,100; −0,055] |
| **tutto** | **49.806** | **−0,071** | **[−0,093; −0,048]** |

Rifatta lo stesso giorno dopo due correzioni: i cinque mesi che mancavano,
e il campo di prova che ora, quando una candela apre oltre lo stop, esce
all'apertura e non allo stop. Uscita completa in
`registro/misure/2026-09-24-base-e-conferme-2.txt`.

È il numero da battere. Per passare, la Fase F deve fare almeno +0,10 R
meglio di questo, con i criteri del `PIANO.md` §2.

Com'è fatta (giornaliero → 1 ora): 63% allo stop, 17% al target (+2,7 R
in media), 19% in pareggio dopo il primo target; 41 operazioni a settimana
su sei strumenti; stop mediano su EURUSD di 25 pip. Romeo dice "1-2 a
settimana" e usa stop di 1-5 pip: filtri e stop stretto sono le prime cose
da guardare.

La coppia 4 ore → 15 minuti non si può ancora misurare: servono i quindici
minuti di vent'anni, che non ci sono.

### Gli agenti della Fase E, contro la base

Operazioni col sì contro quelle col no, su tutte e tre le coppie
(2006–2023). Differenza in R per operazione, intervallo al 95% a blocchi
settimanali, e in quanti anni la differenza ha lo stesso segno (il cancello
chiede l'80%).

| Agente | Lettura | Quante col sì | Differenza | IC95 | Anni concordi |
|---|---|---:|---:|---|---:|
| Conferma key level | massimo preso | 3% | −0,067 | [−0,180; +0,053] | 56% |
| | arriva al massimo | 2% | −0,048 | [−0,193; +0,096] | 61% |
| | rejection block | 14% | −0,060 | [−0,118; −0,002] | 67% |
| | FVG | 12% | +0,076 | [+0,009; +0,148] | 78% |
| | almeno uno | 25% | −0,001 | [−0,048; +0,047] | 44% |
| Conferma orario | Golden candle time 9–13 NY | 22% | +0,032 | [−0,014; +0,079] | 67% |
| Contesto: bias | candela del range a favore | 24% | −0,026 | [−0,060; +0,009] | 61% |
| | timeframe sopra a favore | 40% | −0,018 | [−0,060; +0,023] | 50% |

**Candidati provati finora nella Fase E: 11.** Con 11 tentativi il
cancello chiede un intervallo al 99,5% invece che al 95% (`PIANO.md` §2,
punto 5): nessuna lettura ci arriva. La più vicina è l'FVG, che però
Romeo stesso nel 2026 dice di ignorare.

Quello che i numeri dicono, in parole semplici: prendere tutti i CRT
sull'ora con lo stop all'estremo perde un po', e nessun filtro di Romeo
preso da solo lo raddrizza. Nei casi verificati Romeo entra più tardi e
più in alto, sul timeframe basso, con stop di pochi pip: la differenza
vera sembra lì, nel **come** si entra, più che nel **quando**.

### Il Capo (Fase F), prima prova, 24/09/2026

Per ogni anno dal 2008 al 2023 il Capo impara solo dalle operazioni chiuse
prima del 1° gennaio, e sceglie quelle dell'anno. Le scelte si confrontano
con tutta la base negli stessi anni (44.312 operazioni, −0,068 R). Quattro
configurazioni dichiarate prima, quindi intervallo al 98,75%.

| # | Cacciatore, stop | Scelte | R medio delle scelte | Differenza | IC98,75 | Anni concordi | Con spread ×1,5 |
|---|---|---:|---:|---:|---|---:|---:|
| 1 | manuale, all'estremo | 15.779 | −0,022 | +0,046 | [+0,015; +0,077] | 75% | +0,068 |
| 2 | manuale, stretto | 5.927 | −0,065 | +0,003 | [−0,073; +0,081] | 38% | +0,020 |
| 3 | chiusura dentro, all'estremo | 3.432 | +0,027 | +0,095 | [+0,038; +0,154] | 81% | +0,088 |
| 4 | chiusura dentro, stretto | 2.175 | −0,004 | +0,065 | [−0,037; +0,168] | 62% | +0,071 |

**Nessuna passa.** Il cancello chiede almeno +0,10. La 3 ci arriva vicino
(+0,095), ma le operazioni che sceglie guadagnano appena +0,03 R l'una, e
con lo spread ×1,5 scendono sotto zero (−0,007). Il Capo pesa quasi solo
la geometria (quanto sono lontani i target, quanto è largo lo stop);
key level, orario e bias hanno pesi vicini a zero. Uscita completa in
`registro/misure/2026-09-24-capo.txt`.

Una prima versione di questa prova dava la configurazione 4 a +0,47 R, con
il 100% degli anni concordi. Era un errore: con la "chiusura dentro" il
bot entrava prima che la candela 2 chiudesse, cioè sapendo già come
sarebbe finita. Trovato, corretto e provato (`registro/tentativi.md`).

## Fasi

| Fase | Stato |
|---|---|
| A. Specifica | in corso |
| B. Dati | in corso |
| C. Cacciatore | — |
| D. La base | fatta per tre coppie su quattro (24/09) |
| E. Gli altri agenti | in corso: key level, orario e bias misurati (24/09) |
| F. Capo e apprendimento | prima prova fatta (24/09): nessuna configurazione passa, si torna agli agenti |
| G. Verifica finale | — |
| H. Dal vivo, in demo | — |

## Da fare dopo

Idee fuori dalla fase attuale. Si annotano qui e si fanno quando tocca.

- _(vuoto)_
