# 02_contesto.md

Versione: 0.1 — bozza in revisione
Data: 2026-08-12
Stato: INCOMPLETO. Vedi sezione 7 (Punti aperti).

Questo file elenca le condizioni in cui **non si opera a prescindere**, anche
in presenza di un setup formalmente valido. I filtri qui descritti hanno
precedenza su `03_setup.md` (PREC-01).

---

## 1. Principio

```
CTX-00  Il bot analizza sempre, in ogni momento di mercato aperto.
        Opera solo quando esiste un setup E nessun filtro di questo file
        è attivo.
```

Analisi e operatività sono cose distinte. Il sistema non si spegne mai: si
astiene.

---

## 2. Filtri di astensione

### CTX-01 — Elenco completo

Nessun ordine viene inviato se anche una sola di queste condizioni è vera:

```
1.  Nessun key level è stato preso                        (SETUP-00)
2.  bias_comando è NESSUNA                                (SETUP-06)
3.  Direzione del CRT opposta a bias_comando              (SETUP-07)
4.  Meno di 2 timeframe superiori allineati               (SETUP-05)
5.  Rapporto rischio/rendimento su TP1 inferiore a 1,5    (GEST-01)
6.  Quattro posizioni già aperte sullo strumento          (RISK-06)
7.  Limite giornaliero, settimanale o mensile raggiunto   (RISK-07/08/09)
8.  Finestra di blocco per news 3 stelle                  (CTX-02)
9.  Giorno di festività di mercato                        (CTX-04)
10. mitigazione_attesa NON_DETERMINATA su ingresso da gap (DEF-42)
11. Dato del vocabolario mancante o incoerente            (PRIN-99)
```

In tutti questi casi si applica PRIN-99: non operare, senza giustificazione.

### CTX-02 — News ad alto impatto

```
fonte_calendario = investing.com, calendario economico
filtro           = eventi a impatto 3 stelle
finestra_blocco  = da 30 minuti prima a 30 minuti dopo l'orario della news
```

```
SE l'orario corrente è dentro finestra_blocco
ALLORA nessun nuovo ordine
ALTRIMENTI l'operatività è consentita
```

Per gli strumenti forex il filtro si applica quando la news riguarda una delle
due valute della coppia. Per `XAUUSD` si applica a **tutte** le news 3 stelle,
di qualsiasi paese.

**Posizioni già aperte.** Una posizione aperta prima dell'inizio della finestra
resta aperta e attraversa la news senza modifiche. Il blocco riguarda solo le
nuove aperture.

Esempio: news alle 14:30. Setup alle 14:00 → eseguibile. Setup alle 14:05 →
non eseguibile. Nuove aperture dalle 15:00.

### CTX-03 — Assenza di filtri sulle condizioni di mercato

Non esistono filtri su volatilità, ampiezza dello spread, o divergenza tra
future e CFD.

```
CTX-03  Il bot si basa esclusivamente su ciò che accade sul future.
        Nessuna condizione del CFD può impedire un'operazione né
        provocarne la chiusura.
```

> **NOTA OPERATIVA.** L'assenza di un filtro sullo spread significa che in
> momenti di liquidità ridotta l'ordine può essere eseguito a un prezzo
> sensibilmente peggiore di quello del future. Non è un errore: è una
> conseguenza della scelta di CTX-03, e va tenuta presente confrontando i
> risultati del backtest con quelli reali.

### CTX-04 — Festività di mercato

Nei giorni seguenti il bot non apre nuove posizioni:

| Data | Festività |
|---|---|
| 1 gennaio | Capodanno |
| 19 gennaio | Martin Luther King Day |
| 16 febbraio | Presidents' Day |
| 3 aprile | Venerdì Santo |
| 25 maggio | Memorial Day |
| 19 giugno | Juneteenth |
| 3 luglio | Independence Day |
| 7 settembre | Labor Day |
| 26 e 27 novembre | Thanksgiving |
| 24 e 25 dicembre | Vigilia e Natale |

> **APERTO — vedi PA-53.** Queste date valgono per il 2026. Le festività
> statunitensi a data mobile (Martin Luther King, Presidents' Day, Venerdì
> Santo, Memorial Day, Labor Day, Thanksgiving) cambiano ogni anno. La tabella
> va aggiornata a inizio anno, oppure va sostituita da un calcolo automatico.
> Se non aggiornata, il bot opererà in giorni di liquidità ridotta e si
> asterrà in giorni normali.

---

## 3. Qualità e tempestività dei dati

### CTX-05 — Momento dell'ingresso

```
L'ingresso avviene all'apertura della candela N3, il prima possibile.
```

Non esiste un ritardo prestabilito. Un ritardo di alcuni minuti è accettabile
purché, ricalcolando il rapporto rischio/rendimento sui prezzi effettivi al
momento dell'ordine, questo resti pari o superiore a 1,5 (GEST-01).

```
SE il ritardo ha portato rr sotto 1.5
ALLORA l'ordine non viene inviato
ALTRIMENTI l'ordine è ammesso
```

È il rapporto rischio/rendimento a stabilire se il ritardo sia tollerabile, non
un limite di tempo fisso.

### CTX-06 — Latenza del dato DXY

```
latenza_dxy = fino a 10 minuti
```

Il DXY può arrivare con un ritardo di 10 minuti senza che questo comprometta
l'analisi, essendo usato per la bias e non per l'esecuzione.

### CTX-07 — Storico incompleto

```
SE mancano candele nello storico di un timeframe
ALLORA il timeframe resta utilizzabile
ALTRIMENTI nessun effetto
```

Non esiste esclusione automatica di un timeframe per dati mancanti. Resta
valido il requisito minimo di DEF-26: almeno 3 candele chiuse entro il
`lookback` di 5 anni.

### CTX-08 — Avvio del sistema

```
Il bot è operativo immediatamente all'avvio.
```

Non esiste periodo di osservazione né riscaldamento. Se allo start esiste un
setup valido, viene eseguito.

---

## 4. Serie negative

### CTX-09 — Nessun blocco per perdite consecutive

```
Non esiste un limite al numero di perdite consecutive.
L'unica protezione sono i limiti percentuali di RISK-07, RISK-08 e RISK-09.
```

> **NOTA OPERATIVA.** Con il rischio all'1% per operazione, il limite
> giornaliero del 3% viene raggiunto dopo tre stop pieni. Con più posizioni
> aperte simultaneamente il limite può essere raggiunto in un'unica sequenza di
> chiusure.

---

## 5. Calendario e cicli dei timeframe

### CTX-10 — Aggiornamento dell'analisi a fine periodo

Alla chiusura di ogni periodo, l'analisi del timeframe corrispondente va
ricalcolata prima di qualsiasi operatività sul nuovo periodo.

| Momento | Timeframe da ricalcolare |
|---|---|
| Primo giorno dell'anno | `TF_12M`, e a cascata tutti gli inferiori |
| 1 gennaio e 1 luglio | `TF_6M` e inferiori |
| Inizio di ogni trimestre | `TF_3M` e inferiori |
| Primo giorno del mese | `TF_1M` e inferiori |
| Lunedì | `TF_1W` e inferiori |
| Ogni giorno | `TF_1D` e inferiori |

```
SE l'analisi del timeframe appena chiuso non è stata ricalcolata
ALLORA nessuna operatività sui timeframe inferiori
ALTRIMENTI l'operatività è consentita
```

Il ricalcolo riguarda bias (DEF-16), key level (DEF-36), gap attivo (DEF-13) e
target (DEF-22).

### CTX-11 — Rollover del contratto future

```
Nei giorni di rollover il bot opera normalmente.
```

L'analisi avviene sul future e l'esecuzione sul CFD: il cambio di contratto non
interrompe l'operatività. I gap formati in corrispondenza del rollover sono
trattati come gap ordinari (DEF-35).

---

## 6. Precedenze

```
PREC-01  In conflitto: RISK batte SETUP
PREC-02  In conflitto tra timeframe: il timeframe più alto comanda
PREC-03  In conflitto tra fonti dati: il future comanda
PREC-04  In conflitto: CONTESTO batte SETUP
         Un filtro di questo file impedisce l'esecuzione di qualsiasi setup,
         per quanto valido.
```

---

## 7. Punti aperti

| ID | Punto aperto | Priorità |
|---|---|---|
| PA-53 | Aggiornamento annuale del calendario festività, o sostituzione con calcolo automatico delle festività USA a data mobile | ALTA |
| PA-54 | Modalità di lettura del calendario news da investing.com: manuale, file, o interrogazione automatica | ALTA |
| PA-55 | Comportamento se il calendario news non è disponibile al momento della valutazione di un setup | MEDIA |
