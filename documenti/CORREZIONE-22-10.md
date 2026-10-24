# La correzione del 22/10/2026: DXY, oro e argento, TOTAL

Il proprietario, 22/10/2026, con gli schemi del DXY (4 ore, Capital.com), dell'oro (4 ore, FXCM), della TOTAL con BTC
ed ETH e i messaggi della squadra su AUDUSD, GBPUSD e USDCHF: *"Prima di modificare il codice, individua il punto esatto
in cui la logica si discosta dalle regole"*.

## Le regole

| Mercati | Chi decide la direzione | Cosa serve per entrare | Il resto |
|---|---|---|---|
| Coppie forex col dollaro (EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCHF, USDCAD) | solo il DXY | un CRT del DXY che ha preso un key level | il CRT della coppia nel verso del DXY dà più vantaggio, non decide |
| Oro e argento | il loro grafico | il loro CRT con le regole di sempre (CRT, key level, direzione) | il DXY è un parere |
| BTC ed ETH | solo la TOTAL | un CRT della TOTAL che ha preso un key level | i loro CRT non fanno entrare |

## I tre casi, ricostruiti sul codice di quel momento

### 22/10 alle 10: il DXY fa il CRT a 4 ore dopo il WL e il DL, nessuna coppia si apre

- **Dove si stacca.** `foto.dal_dxy` portava il setup del DXY sulla coppia cercando la candela della coppia che
  partiva alla stessa ora della candela 2 del DXY. Il DXY di Capital.com ha le 4 ore alle 2-6-10-14 italiane (UTC),
  le coppie alle 0-4-8-12 (le 18 di New York): la candela delle 6 sulla coppia non c'è, e il setup cadeva.
- **Prova.** Sui prezzi di Yahoo del 22/10, col DXY sugli orari UTC, il codice di allora scrive per tutte e sei le
  coppie *"le sue candele non si possono mettere accanto a quelle del DXY"*.
- **Con la correzione.** Lo stesso giro apre EURUSD, GBPUSD, AUDUSD e NZDUSD in vendita, USDCHF e USDCAD in acquisto,
  alle 10.

### 22/10 alle 12: aperte AUDUSD, GBPUSD e USDCHF col «CRT H6»

- **Da dove vengono.** Dal 20/10 sulle coppie forex i CRT loro non fanno entrare: nel codice l'unica strada è un CRT
  del DXY. Queste tre vengono quindi da un CRT a 6 ore del DXY con la candela 3 alle 12, portato sulle coppie.
- **Perché sembravano CRT delle coppie.** Il titolo dei messaggi era «AUDUSD · vendita · CRT H6», e il key level e
  gli allineati erano quelli della coppia.
- **Gli errori veri, due.**
  1. Dal 21/10 il CRT del DXY non doveva più avere preso un key level: era un errore mio.
  2. Il 6 ore delle 12 era lo stesso movimento del 4 ore delle 10, cioè la stessa presa del WL e del DL.
- **Con la correzione:**
  - il CRT del DXY deve avere preso un key level;
  - un CRT del DXY che è lo stesso movimento di uno di prima non fa entrare di nuovo (`giro.stesso_movimento`);
  - i titoli dicono «CRT … del DXY».

### 21/10 alle 12: il CRT a 4 ore dell'oro dopo il DL, non aperto

- **Dove si stacca.** Dal 20/10 l'oro e l'argento erano in `foto.GUIDATI_DAL_DXY`: i loro CRT non facevano mai
  entrare. Era un errore mio, contro la regola delle correlazioni dell'08/10 (*"circa l'85%"*).
- **Con la correzione.** L'oro e l'argento entrano coi loro CRT.

### 21/10 alle 22: la TOTAL fa il CRT short a 4 ore dopo il DH, BTC ed ETH non aperti

- **Fino alla squadra era giusto.** Il giro ha costruito i setup:

  | | Ingresso | TP1 | Target | Il proprietario |
  |---|---|---|---|---|
  | BTC | 84.447 | 83.169 | 81.097 | ~84.412 / 83.181 / 81.110 |
  | ETH | 2.493 | 2.455 | 2.371 | ~2.492 / 2.456 / 2.372 |

- **Dove si stacca.** La squadra chiedeva, fra le regole obbligatorie, la direzione di BTC e di ETH dalla loro parte.
  Il settimanale spingeva su, quindi ha detto no a tutti e due, senza dirlo.
- **Correzioni già fatte.**
  - Questa regola è stata tolta alle 23:26 dello stesso giorno: sui setup della guida la direzione dello strumento è
    un parere.
  - Dalla stessa ora ogni occasione non aperta lo dice (⏸).
  - La rete neurale lasciava questi setup: corretta il 22/10 alle 11:50.
- **Prova.** Il giro di allora rifatto sui prezzi di Yahoo, col CRT di BTC delle 22 al posto della TOTAL, che su Yahoo
  non c'è.

## Cosa è cambiato nel codice

| Dove | Cosa |
|---|---|
| `foto.dal_dxy` | il setup sulla coppia negli orari delle candele del DXY: il range nelle ore della candela 1, la candela 2 nelle ore della sua candela 2, l'ingresso all'apertura della candela 3 del DXY; lo stop allargato fino allo stop minimo come in `trova` |
| `foto.GUIDATI_DAL_DXY` | solo le coppie forex col dollaro |
| `foto.crt_propri` | i CRT della coppia nel verso della guida, anche sullo stesso timeframe con altri orari, solo quelli con la presa di un key level (senza, il 22/10 la stella l'avevano tutte e sei le coppie; con, tre su sei) |
| `giro.occasioni_foto` | la guida deve avere preso un key level; un CRT della guida che è lo stesso movimento di uno di prima non fa entrare; i CRT propri vanno al Cacciatore; l'oro e l'argento coi loro CRT, col CRT del DXY vicino come parere |
| `metodo.valuta_foto` | il key level obbligatorio è quello della guida (per il CRT a 1 ora anche il massimo o minimo a 4 ore della guida) |
| `pareri` | il Cacciatore dice quando la coppia fa anche lei il CRT; il key level della coppia dice che è della coppia; il Bias segue il DXY solo sulle coppie forex |
| `messaggi.guide` | il no della guida in una riga; prima le coppie col CRT proprio, con la ★ |
| `vivo.Bot._tema`, `foto_grafico` | «CRT … del DXY», «… della TOTAL» nei titoli |

Il modulo che apre gli ordini su MT5 (`esecutore.py`) non è cambiato.

## Come si verifica

- **Le prove.**
  - `tests/test_foto.py`:
    - `test_il_dxy_con_altri_orari_arriva_lo_stesso_alle_coppie`;
    - `test_lo_stesso_movimento_del_dxy_non_fa_entrare_di_nuovo`;
    - `test_oro_e_argento_entrano_coi_crt_loro_anche_senza_il_dxy`;
    - `test_il_crt_della_coppia_nel_verso_del_dxy_da_piu_vantaggio`;
    - `test_sulle_coppie_col_dollaro_entra_solo_il_pattern_del_dxy`, col key level della guida.
  - `tests/test_intelligenti.py`: `test_sugli_strumenti_guidati_le_regole_le_da_il_crt_del_dxy`.
  - `tests/test_pareri.py`: `test_l_oro_non_e_fermato_dalla_previsione_della_settimana_del_dxy`.
- **Sul canale operativo, al prossimo CRT del DXY.**
  - Il 📐 dice su quali coppie nasce l'occasione, prima quelle con la ★.
  - Se il DXY non ha preso un key level, una riga sola: «non ha preso un key level: non è il pattern».
  - Se il CRT è lo stesso movimento di uno di prima, lo dice.
- **In équipe.** Il titolo dice «CRT … del DXY».

## La notte del 23/10: il "CRT a 6 ore del DXY delle 00:00"

Il DXY apre alle 2 italiane, eppure il bot ha detto "CRT a 6 ore" con la candela 3 alle 00:00 e ha aperto delle coppie.

- **La causa.** L'orario di ogni grafico si legge dalle sue candele a 4 ore: ci voleva che il 98% partisse a orari
  fissi. Il DXY di Capital.com apre la settimana la domenica sera con una candela fuori griglia, una ogni 30 circa:
  l'orario non si capiva e il bot usava le 18 di New York, gli orari delle coppie (0-4-8 italiane), invece dell'UTC
  (2-6-10). Con l'orario sbagliato il bot prendeva per chiuse candele del DXY a meta' e vedeva CRT che sul grafico non
  c'erano. E l'orario si rileggeva solo quando arrivavano tutte le candele a 4 ore: dopo i riavvii restava quello.
- **La prova.** Il bot intero simulato la notte del 23/10, col DXY che apre la domenica fuori griglia e TradingView che
  non da' le 6 e 12 ore: alle 00:00 "CRT long 6 ore, giornaliero del DXY" e quattro coppie aperte, col target finale
  sul TP1. Con la correzione: alle 00:00 niente, alle 2:00 il CRT giornaliero del DXY, sui suoi orari.
- **La correzione.**
  - L'orario si capisce col 90% delle candele, e vince la griglia che ne spiega di piu' (`tradingview.griglia`).
  - Si rilegge dalle candele a 4 ore gia' avute a ogni aggiornamento; se era sbagliato, le candele di quel grafico si
    riprendono tutte e lo si dice sul canale operativo con 🕑 (`vivo.Bot._orari_dalle_candele`).

## Il target finale sul TP1 (il buy di ETH del 22/10)

- **La causa.** Il key level opposto si prendeva come target anche se non stava oltre il TP1: il piano col target
  finale diventava impossibile e si andava tutto al TP1. Era anche il motivo per cui 8 delle 9 prove delle foto
  fallivano.
- **La correzione.** Il key level opposto vale solo oltre il TP1; se no si passa agli altri target del metodo (gap,
  liquidazione, key level piu' grande) e, prima di arrendersi al TP1, all'altro lato di ieri (DH, DL)
  (`foto.target_minimo`, `foto.obiettivo_finale`). Delle 24 foto ne resta fuori una, la 4/6.

## Il lotto minimo su ETH e l'oro non aperto per "conto troppo piccolo"

Il messaggio "la puntata giusta era più piccola del minimo che il broker accetta: apro il minimo" vuol dire che il
Rischio della squadra aveva una puntata sotto lo 0,01; il 23/10 alle 8 per lo stesso motivo non si è aperto il CRT a 4
ore dell'oro ("conto troppo piccolo per il lotto minimo"). Il Rischio aveva imparato anche dalle operazioni aperte su
CRT del DXY che non c'erano.

Il proprietario, 23/10/2026: *"deve decidere lui quanto puntare e basta, resetta tutto quanto ciò che riguarda il
rischio ... su trade punterà di più, su altri trade punterà di meno, deve essere intelligente"*; *"quando il bot
funzionerà ... sarà la rete neurale a decidere quanto rischiare"*. Quindi, senza tetti:

- il Rischio riparte da zero una volta (`squadra.RIPARTENZA_RISCHIO`): puntata base 1%;
- punta di più dove il Capo crede di più fin dalla prima occasione (prima aspettava 10 occasioni);
- rifà la puntata subito prima di ogni ordine, vedendo le operazioni appena aperte nello stesso giro
  (`Squadra.ripunta`): quando il DXY fa il CRT le coppie si aprono dalla migliore e le altre, mosse dallo stesso
  dollaro, prendono di meno. Quanto di meno lo impara dai risultati.

Poi, lo stesso giorno, l'oro a 4 ore delle 16 lasciato ancora per "conto troppo piccolo per il lotto minimo". Con
900 € e un CRT a 4 ore dell'oro, 0,01 lotti (un'oncia) con uno stop di 20-30 dollari rischiano circa il 2-4% del
conto, più del doppio della puntata del Rischio, e il bot non apriva (la leva non c'entra: decide il margine, non
quanto si perde allo stop). Il proprietario: *"Se ci sta una cosa valida, deve aprire"*. Da ora sui setup della
squadra, se la puntata sta sotto il lotto minimo, si apre il minimo, sempre, e il messaggio d'apertura dice quanto
rischia davvero (`Esecutore.apri(sempre_il_minimo=True)`, `tests/test_vivo.py::
test_un_setup_della_squadra_si_apre_sempre_almeno_col_lotto_minimo`). Con 0,01 lotti il 25% al TP1 non si può
chiudere: tutta la posizione va al target finale, col pareggio al TP1.
