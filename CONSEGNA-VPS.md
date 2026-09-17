# Consegna alla sessione sulla VPS

*17 settembre 2026 — stato al momento del passaggio*

Questo file esiste perché chi riprende il lavoro non deve ricostruirlo dalla
memoria di qualcun altro. Dice dove siamo, cosa è rotto, cosa non va toccato.

---

## Dove gira

- cartella: `c:\bot\progetto`
- ramo: `claude/trading-bot-infrastructure-5rht0h` — **non spingere altrove**
- Python: quello con `MetaTrader5` installato (`python -c "import MetaTrader5"`
  deve rispondere senza errori). Se dice *No module named*, è il 3.13: serve
  il 3.11, e si usa `py -3.11` al posto di `python`.
- MT5: il terminale deve essere **aperto e collegato**, o il bot non ha né
  conto né prezzo e si astiene su tutto.

## Regole che non si discutono

1. **Nessun segreto a schermo.** Il `.env` contiene chiavi vere. Per vedere
   cosa c'è dentro si elencano solo i nomi:
   `awk -F= '/^[A-Z_]+=./ {print $1}' .env`. Mai il contenuto, mai in chat,
   mai in un commit.
2. **`.env` non si committa mai.** È in `.gitignore` e ci deve restare.
3. **Conto demo.** `CONSENTI_CONTO_REALE` resta `False`. Con un conto non
   demo il bot rifiuta di mandare ordini in automatico, ed è voluto.
4. **Non alzare il parallelismo verso Dukascopy.** I valori attuali (4 per le
   orarie, 6 per i minuti) non sono cautela: con 12 la fonte ha smesso di
   rispondere a questo indirizzo per ore. C'è un freno condiviso in
   `core/fonte_dukascopy.Freno` e va lasciato fare.
5. **Le prove devono passare prima di ogni commit**:
   `python -m pytest tests/ -q` e `python test_impianto.py`.

## In sospeso, da fare a mano dall'autore

Il token del bot Telegram è finito nella storia di git in un commit vecchio.
È stato tolto dal tracciamento ma **resta nella storia**: va revocato da
@BotFather con `/revoke` e sostituito nel `.env`. Non è stato fatto.

---

## Stato dell'impianto

### Cosa funziona

- La catena dal ciclo al motore. Verificato sulla VPS: `EURUSD TF_M5` arriva
  al motore e produce un'astensione con la sua regola. Fino a ieri **nessuna
  candela raggiungeva il motore**: `mercato_duka` costruiva un `AlertIn` coi
  nomi dei campi sbagliati, pydantic lo rifiutava, un `except` generico
  inghiottiva l'errore e il contatore di `/salute` cresceva lo stesso.
- La strategia. Si vedono CRT trovati e scartati da `CRT-20`, `RISK-05`,
  `SETUP-07`: non è più "non trovo niente".
- MT5 connesso, conto demo, `mt5_trading_permesso: true`.
- Il DXY: `SETUP-19` ha la sua bias.

### Cosa è rotto o sospeso

1. **L'archivio orario si ferma al 31 agosto.** Causa accertata: Dukascopy
   **non pubblica il file orario del mese in corso** (404 fino a mese
   chiuso). Non erano i 503. Rimedio già in codice: il ciclo ricostruisce le
   ore del mese in corso dai file al minuto, che sono giornalieri — misurato
   identico al file orario, 117 ore su 117, scostamento zero
   (`docs/ORARIE-DAI-MINUTI-2026-09-17.md`).
2. **Il DXY in archivio viene dalla fonte gratuita**, non da Dukascopy:
   14.141 candele giornaliere sono 56 anni, che Dukascopy non ha. Funziona,
   ma è un'altra costruzione. `importa_dxy.py` lo sostituisce con quello
   calcolato dai sei costituenti e toglie le candele della vecchia fonte,
   perché due costruzioni nella stessa serie sono peggio di entrambe.
3. **Dukascopy limita questo indirizzo.** A intermittenza: `curl` ha dato
   `503`, poi `000 timed out`, poi `200`. Prima di qualunque scaricamento,
   provare:
   `curl -sS -o NUL -w "%{http_code}\n" https://datafeed.dukascopy.com/datafeed/EURUSD/2024/04/BID_candles_hour_1.bi5`
   `200` si procede, `503` si aspetta, timeout **non si insiste**.

---

## I tre passi, in ordine

### 1. Rimettere in pari l'archivio, senza rete

```
python importa_pacchetto.py
python prova_giro.py
```

`dati/pacchetto-2026-09.csv.gz` contiene agosto e settembre per i sei
strumenti su tutti i timeframe, costruito con le stesse funzioni della
semina. Non sovrascrive: riempie i buchi.

`prova_giro.py` percorre la catena una volta e dice a quale anello si ferma.
Deve chiudersi con quattro righe: archivio, DXY, calendario, catena. Un `NO`
è un guasto; un `NONE` che cita una regola è un'astensione vera.

### 2. Decidere il listino, con una misura

```
python confronta_feed.py
```

Dukascopy e MT5 sono due listini diversi. Ogni misura del progetto è stata
fatta su Dukascopy — `+0,3613 R` su `4h -> 15m` viene da lì. MT5 però non ha
limiti, serve il mese in corso, ed è **il listino su cui si esegue**:
analizzare e operare sulla stessa serie toglie uno scostamento che nessuna
regola può recuperare.

`core/mercato_mt5.py` è già scritto e non è il predefinito. Lo si attiva solo
se il confronto dice che i due listini coincidono. Metro di giudizio: c'è un
precedente nel progetto dove, fra fonte gratuita e Dukascopy, **il 37,7%
degli esiti cambiava**. Se gli scostamenti su massimo e minimo sono
trascurabili rispetto all'ampiezza media, si passa a MT5; se sono
confrontabili, le misure vanno rifatte prima.

### 3. Le 24 ore

Con `prova_giro.py` pulito:

```
avvia.bat
```

Poi sorvegliare `http://127.0.0.1:8000/salute`. Cosa guardare:

- `richieste_al_giorno` — sopra le diecimila si torna nei 503;
- `ultimo_errore` — deve restare `null`;
- `valutazioni` che cresce **e** decisioni nuove in archivio: il primo senza
  il secondo era esattamente il guasto di ieri;
- `posizioni_aperte_broker` contro `posizioni_aperte_archivio`: se divergono,
  la sentinella sta sorvegliando qualcosa che non c'è o viceversa.

Il freno a mano è un file chiamato `STOP` nella cartella: blocca le aperture
e lascia la sorveglianza.

---

## Come è fatto il progetto

La strategia è quella di @Romeotpt, scritta come regole numerate
(`docs/BIBBIA-CRT.md`). Ogni regola ha un codice — `DEF-`, `SETUP-`, `GEST-`,
`RISK-`, `CTX-`, `PRIN-`, `ESCL-`, `CRT-` — e ogni astensione del motore
porta i codici che l'hanno causata. Quando si tocca il comportamento, si cita
la regola.

I punti che i documenti non decidono stanno in `PUNTI_APERTI` e si sciolgono
in `SCELTE` (`core/parametri.py`). Uno è stato cambiato dall'autore oggi:
`PA-55 = "opera"`, cioè **senza calendario news il bot lavora lo stesso**.
Costo dichiarato: `CTX-02` non ha più nulla contro cui bloccare, quindi si
può aprire a ridosso di un dato ad alto impatto. È una scelta, non un
difetto: non "correggerla".

Il commento nel codice spiega **perché**, non cosa. Dove c'è un numero
misurato, va citato con la misura.
