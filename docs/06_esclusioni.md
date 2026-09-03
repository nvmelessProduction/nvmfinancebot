# 06_esclusioni.md

Versione: 0.1 — bozza in revisione
Data: 2026-08-12

Questo file elenca ciò che il sistema **non fa mai, in nessuna circostanza**.
Le regole qui contenute non ammettono eccezioni e non sono soggette a
valutazione caso per caso.

Differenza rispetto a `02_contesto.md`: là ci sono condizioni temporanee che
sospendono l'operatività. Qui ci sono divieti permanenti.

---

## 1. Divieti sull'operatività

```
ESCL-01  Mai operare contro bias_comando.
         Nemmeno con un CRT formato correttamente, nemmeno con timeframe
         intermedi allineati nella direzione opposta.

ESCL-02  Mai entrare senza la presa di un key level.
         Nessuna configurazione di candele, per quanto conforme al CRT,
         produce un ingresso in assenza di un key level sbilanciato.

ESCL-03  Mai prendere reversal prima che il target di tf_comando sia
         raggiunto.

ESCL-04  Mai operare su timeframe inferiori a TF_H1.
         Nessuna analisi, nessun ingresso, nessuna gestione.

ESCL-05  Mai operare su strumenti diversi da quelli elencati in PRIN-08.
```

---

## 2. Divieti sulla gestione

```
ESCL-06  Mai mediare una posizione in perdita.
         Nessun incremento di size su una posizione in negativo, con
         qualsiasi motivazione.

ESCL-07  Mai allargare uno stop.
         Lo stop si sposta solo a break even, e solo dopo TP1.

ESCL-08  Mai spostare lo stop prima del raggiungimento di TP1.

ESCL-09  Mai usare trailing stop, in nessuna forma.

ESCL-10  Mai aprire una posizione senza stop loss definito.
         Se lo stop non è calcolabile, l'ordine non parte.

ESCL-11  Mai superare quattro posizioni contemporanee sullo stesso
         strumento.
```

---

## 3. Divieti sui dati

```
ESCL-12  Mai convertire prezzi tra future e CFD.
         Mai confrontare un prezzo future con un prezzo CFD.

ESCL-13  Mai valutare una candela in formazione.
         Ogni regola usa esclusivamente candele chiuse.

ESCL-14  Mai usare un dato assente dal vocabolario di 01_definizioni.md.
         Se una regola richiede un dato non presente in quella tabella, la
         regola non è eseguibile.

ESCL-15  Mai usare indicatori per generare o filtrare segnali.
         Due sole eccezioni, entrambe circoscritte:

         a) RSI, applicato ai soli gap e limitatamente alla registrazione
            della divergenza (DEF-44). Non modifica alcuna decisione.

         b) ATR(14), ammesso ESCLUSIVAMENTE come unità di misura per
            normalizzare distanze (GIUD-01, 07_casi.md §3.1).
            L'ATR non può mai generare un segnale, filtrare un ingresso,
            determinare uno stop né dimensionare una posizione.
            Serve solo a esprimere una distanza in una scala confrontabile
            tra strumenti e timeframe diversi.

ESCL-16  Mai considerare un gap INVALIDATO come nuovamente valido.

ESCL-17  Mai considerare un livello CONSUMATO come nuovamente disponibile.
```

---

## 4. Divieti sulla manutenzione delle regole

```
ESCL-18  Mai riciclare un ID di regola.
         Se una regola viene ritirata, il suo ID muore con lei e non viene
         mai riassegnato.

ESCL-19  Mai introdurre un aggettivo valutativo senza soglia numerica.
         "Forte", "chiaro", "significativo", "vicino": ogni termine di
         questo tipo va sostituito da un numero o isolato in un blocco GIUD.

ESCL-20  Mai usare rimandi impliciti tra parti dei documenti.
         "Come detto sopra", "vale anche qui", "analogamente": vietati.
         Si ripete il contenuto, oppure si cita l'ID.

ESCL-21  Mai inserire informazione presente solo in un'immagine.
         Ogni concetto illustrato da un grafico va scritto anche a parole.
```

---

## 5. Divieti sull'esercizio

```
ESCL-22  Mai fare eccezioni discrezionali alle regole.
         Non esiste il caso in cui si opera "perché si vede che è buono".
         Se una situazione ricorrente merita un'operazione, va scritta come
         regola in 03_setup.md, non eseguita come eccezione.

ESCL-23  Mai etichettare un caso in 07_casi.md sull'esito del trade.
         L'etichetta è conforme / non conforme alla strategia. Vinto e perso
         sono informazione separata.

ESCL-24  Mai aggiungere uno strumento all'operatività senza modificare
         PRIN-08. Non esistono strumenti abilitati da parametro.
```

---

## 6. Ciò che invece è ammesso

Elencato qui per evitare che venga confuso con un divieto.

```
AMM-01   È ammesso l'intervento manuale di chiusura di una posizione.
         L'operatore può chiudere in qualsiasi momento, per qualsiasi
         motivo, senza che questo violi alcuna regola.

AMM-02   È ammesso riaprire sullo stesso strumento e sullo stesso timeframe
         dopo uno stop, se il setup si riforma. Nessun timeframe resta
         "bruciato" dopo una perdita.

AMM-03   È ammesso avere posizioni in direzioni opposte su strumenti
         diversi contemporaneamente.

AMM-04   È ammesso mantenere posizioni aperte attraverso la chiusura
         settimanale e il fine settimana.

AMM-05   È ammesso operare durante il rollover del contratto future.
```

**Nota su AMM-01.** L'intervento manuale è ammesso, ma ogni chiusura manuale
va annotata in `07_casi.md` con etichetta di conformità. Una chiusura manuale
non prevista dalle regole è, per definizione, `NON CONFORME`: registrarla è
ciò che permette di capire se sia il caso di modificare una regola oppure di
correggere il comportamento.

---

## 7. Precedenza di questo file

```
PREC-05  In conflitto: ESCLUSIONI batte tutto.
         Nessuna regola di alcun altro file può autorizzare ciò che è
         vietato qui.
```
