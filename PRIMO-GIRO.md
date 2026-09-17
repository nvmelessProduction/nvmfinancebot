# Primo giro sulla VPS — istruzioni per la sessione Claude Code

Questo file è per la sessione di Claude Code che gira **sulla VPS Windows**,
accanto al bot. Leggilo per intero prima di toccare qualcosa.

---

## Dove sei

`c:\bot\progetto`, ramo `claude/trading-bot-infrastructure-5rht0h`. Sulla
stessa macchina girano MetaTrader 5 e il bot. Hai accesso all'archivio, ai
log e al codice mentre il bot opera: è il motivo per cui sei qui.

## Cosa fa il bot, in una riga

Applica la **Candle Range Theory di @Romeotpt**: una candela di timeframe
alto definisce un range, il prezzo ne spazza un estremo e rientra, e
sull'ingresso si entra al ritorno nell'FVG dopo il CISD (`CRT-13`). Le regole
sono in `docs/`, la strategia normativa in `docs/BIBBIA-CRT.md`.

---

## 0. Aggiornare il codice

```
aggiorna.bat
```

Doppio click, o dal terminale. Fa da solo la sequenza che `git pull` da solo
non riesce a fare quando in cartella ci sono modifiche locali: mette al
sicuro il calendario news, manda il resto in `git stash`, aggiorna, rimette
il calendario.

**Non usare `git reset --hard`** per sbloccare un pull rifiutato: butta via
le modifiche locali per sempre. Lo `stash` le conserva, e `git stash list`
le ritrova.

---

## 1. Verifica prima di accendere

```powershell
python -c "from core import storage; storage.inizializza(); [print(f\"{r['strumento']:8s} {r['tf']:9s} {r['quante']:7d}\") for r in storage.copertura_candele()]"
```

Devono esserci **sei strumenti** — EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY,
XAUUSD — **piu' ICEUS**, che e' il dollar index, e per ciascuno:

| timeframe | atteso | da dove |
|---|---:|---|
| `TF_H1` | ~129.000 | `importa_dukascopy.py` |
| `TF_H4` | ~33.000 | idem |
| `TF_1D` | ~6.000 | idem |
| `TF_1W` | ~1.000 | idem |
| `TF_1M` | ~250 | idem |
| `TF_M15` | ~6.000 | `importa_minuti.py` |
| `TF_M5` | ~18.000 | idem |
| `TF_M1min` | ~90.000 | idem |

E per `ICEUS`, che non ha intraday perche' serve solo alla bias:

| timeframe | atteso | da dove |
|---|---:|---|
| `TF_H1` | ~31.000 | `importa_dxy.py` |
| `TF_1D` | ~1.300 | idem |
| `TF_1W` | ~260 | idem |
| `TF_1M` | ~60 | idem |

**Se mancano dei mesi** nei timeframe alti: rilancia `python
importa_dukascopy.py`. Un mese fallito per 503 **non viene messo in cache**,
quindi il secondo giro riprova solo quelli. Ripeti finché i numeri smettono
di crescere.

**Se mancano i tre intraday**: `python importa_minuti.py`. Senza di essi la
coppia `4h → 15m` — quella col risultato migliore misurato — non può girare.

**Se manca `ICEUS`**: `python importa_dxy.py`. È il dollar index, e senza di
esso `SETUP-19` **non abilita alcuna operazione** su cinque coppie su sei —
resta libero solo `XAUUSD`, che `PRIN-09` esenta. Dukascopy pubblica un
`USDIDX` che sembra servire e non serve: è un file inerte, volume zero e un
solo valore ripetuto per tutto il mese. L'indice si calcola dai suoi sei
costituenti, e quanto quella costruzione si discosta da quella vera è
misurato in `docs/DXY-INVOLUCRO-2026-09-17.md` — 96,1% di accordo sulla bias
giornaliera, e sbaglia sempre per astensione, mai per direzione.

### La prova che dice se la catena regge

```powershell
python prova_giro.py
```

Percorre la catena **una volta** — archivio, DXY, alert, fotografia, motore —
e stampa a quale anello si ferma ogni strumento e ogni timeframe. Non apre
nulla e non scrive nulla.

Serve perché un bot che non opera e un bot che opera e si astiene hanno lo
stesso aspetto da fuori: `/salute` mostra contatori che salgono e nessun
errore. Una riga `[ NO ]` è un guasto; un `NONE` con un motivo che cita una
regola è un'astensione vera.

### MetaTrader 5

```powershell
python -c "import MetaTrader5; print('ok')"
python prova_esecuzione.py
```

Se il primo dice `No module named 'MetaTrader5'`, è Python 3.13: quel
pacchetto non esiste per quella versione. Serve **Python 3.11**, installabile
accanto senza disinstallare niente, poi si usa `py -3.11` al posto di
`python`.

`prova_esecuzione.py` dice anche il **suffisso dei simboli** del broker
(`EURUSD.a`, `EURUSD.pro`…). Va in `MT5_SUFFISSO_SIMBOLI` nel `.env`:
sbagliarlo rende muti i conteggi di `RISK-02` e `RISK-06` **senza alcun
errore nei log**.

---

## 2. Accendi

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Poi da un'altra finestra:

```powershell
curl http://127.0.0.1:8000/salute
```

Deve dire `modalita: dry_run` e il ciclo Dukascopy `in_funzione: true`.

---

## 3. Cosa guardare nelle 24 ore

```
GET /salute            broker, sentinella, mercato, ultimo errore
GET /decisioni         le decisioni con motivo e regole applicate
GET /posizioni         cosa è aperto e con quali livelli
GET /cowork/in-attesa  i setup che aspettano un giudizio
```

Le domande a cui il primo giro deve rispondere, in ordine di importanza:

1. **Il bot valuta?** `/salute` → `valutazioni` deve crescere. Se resta a
   zero, il ciclo di mercato non fa scattare niente.
2. **Trova CRT?** In `/decisioni`, quante volte compare `SETUP-00` (nessun
   CRT) contro le altre regole. `SETUP-00` sul 90% è normale: i CRT sono rari.
3. **Arma setup?** Cerca `CRT-13` fra le regole che bloccano — significa
   "setup armato, attendo il ritorno nell'FVG". Poi controlla se qualcuno
   arriva all'ingresso.
4. **Quali conferme fermano di più?** `CRT-20`, `RISK-05`, `CTX-02`… Se una
   sola regola blocca tutto, va guardata: potrebbe essere giusta o rotta.

Il bot **si astiene in ogni caso dubbio** invece di tirare a indovinare. Se
tace, `/decisioni` dice sempre quale regola l'ha fermato: non esistono
astensioni senza motivo, e se ne trovi una è un difetto del motore.

---

## 4. Cosa NON fare

- **Non passare a `auto`** finché `dry_run` non ha prodotto decisioni che
  hanno senso. L'ordine è `dry_run` → `semi` → `auto` su demo.
- **Non toccare `CONSENTI_CONTO_REALE`**. È `false` e blocca gli ordini
  automatici su qualunque conto non-demo.
- **Non mettere segreti in chat, nei commit o nei log.** Il token Telegram di
  questo progetto è già finito pubblico su GitHub una volta. `metti_chiave.py`
  esiste apposta.

---

## 5. Lo stato delle misure, per non ripartire da zero

Misurato su prezzi veri Dukascopy con BID e ASK, 2006–2026:

| configurazione | n | R netto | σ |
|---|---:|---:|---:|
| `4h→15m`, ingresso CRT-13, filtro CRT-20 | 226 | **+0,3613** | +1,6 |
| `4h→15m`, ingresso alla chiusura del range | 172 | −0,0782 | −0,6 |
| `1h→5m`, ingresso CRT-13 | 886 | −0,0494 | −1,1 |
| `15m→1m`, ingresso CRT-13 | 3.514 | −0,2195 | −11,1 |

**σ = +1,6 su 226 operazioni non è una certezza.** È il migliore che esiste
nei dati. Serve raccogliere operazioni vere su demo per distinguerlo dal caso.

Le conferme di Romeo sono **tutte valutate** su ogni setup e finiscono nel
dossier del giudice; solo `CRT-20` blocca da sola. Come veti in AND bloccano
tutto: 18 CRT trovati, 18 fermati.

Dettagli in `docs/MISURA-REGOLE-MANCANTI-2026-09-16.md` e
`docs/MISURA-DEFINITIVA-2026-09-16.md`.

---

## 6. Il metodo, che vale più dei numeri

Quattro volte in questo progetto un risultato negativo si è rivelato **un
errore di chi misurava**, non della strategia:

- il costo dello spread calcolato su un allineamento BID/ASK sbagliato
  (12 R invece di 0,07 R);
- l'aggregatore che collassava 4 ore e giornaliero a un'ora;
- le regole misurate isolate invece che come confluenze;
- la finestra del CISD che includeva la barra di rottura (16 CISD su 3.622).

E due volte un risultato **troppo bello** era un lookahead: `+19,9σ` su
`canonico.py`, `+15,3σ` su `CRT-17`.

**Prima di concludere che una regola non funziona, sospetta del codice.** E
prima di credere a un numero bello, cerca il futuro nel filtro.

Ogni misura va con il suo σ **contro un placebo** con la stessa geometria. Un
numero senza placebo non è una misura.
