# Installare il bot e Claude sulla VPS Windows

Obiettivo: bot e Claude Code sulla **stessa macchina**, così posso leggere i
log, l'archivio e il codice mentre il bot opera, e fare da trader
discrezionale in diretta.

MT5 gira solo su Windows, quindi la VPS Windows non è un compromesso: è il
posto giusto.

---

## 1. Cosa serve sulla VPS

| | versione | dove |
|---|---|---|
| **Python** | 3.11 o 3.12 | [python.org](https://www.python.org/downloads/windows/) — spunta **"Add python.exe to PATH"** |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org) — serve a Claude Code, non al bot |
| **Git** | qualsiasi | [git-scm.com](https://git-scm.com/download/win) |
| **MetaTrader 5** | del tuo broker | dal sito di FP Markets |

> Python 3.13 non va ancora bene: il pacchetto `MetaTrader5` non ha le ruote
> compilate per quella versione. 3.11 è la scelta sicura.

---

## 2. Il bot

Apri **PowerShell** e:

```powershell
cd C:\
git clone https://github.com/nvmelessProduction/nvmfinancebot.git
cd nvmfinancebot
git checkout claude/trading-bot-infrastructure-5rht0h

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Il file `.env`

Crealo nella cartella del progetto. **Non finisce mai su GitHub** — è già in
`.gitignore`.

```ini
MODE=dry_run
FORNITORE_DATI=dukascopy
SENTINELLA_ATTIVA=true
CONSENTI_CONTO_REALE=false
MERCATO_INTERVALLO_SEC=120

GIUDIZIO_ATTIVO=true
ANTHROPIC_API_KEY=sk-ant-...

MT5_LOGIN=123456
MT5_PASSWORD=...
MT5_SERVER=FPMarkets-Demo
MT5_SUFFISSO_SIMBOLI=

WEBHOOK_SECRET=una-stringa-lunga-a-caso
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```

> **Il token Telegram che avevi incollato in chat va revocato.** Era finito su
> GitHub e resta nella storia del repository anche dopo la rimozione. Su
> @BotFather: `/revoke`, e metti qui quello nuovo.

### Trova il suffisso dei simboli

Alcuni broker chiamano i simboli `EURUSD.a` o `EURUSD.pro`. Sbagliarlo rende
muti i conteggi di `RISK-02` e `RISK-06` senza alcun errore nei log:

```powershell
python prova_esecuzione.py
```

Ti dice il suffisso: mettilo in `MT5_SUFFISSO_SIMBOLI`.

### Semina l'archivio

```powershell
.\semina.bat
```

Vent'anni di candele vere Dukascopy, sei strumenti. Circa un'ora la prima
volta. Si può rilanciare: riprende da dove era.

### Accendi

```powershell
.\avvia.bat
```

Pannello su `http://127.0.0.1:8000/`.

---

## 3. Claude Code sulla stessa macchina

```powershell
npm install -g @anthropic-ai/claude-code
cd C:\nvmfinancebot
claude
```

Al primo avvio chiede l'autenticazione: apre il browser, fai login col tuo
account Anthropic.

Da quel momento sono **dentro la VPS**: vedo il codice, l'archivio, i log,
e posso interrogare il bot mentre gira.

### Collegarti da fuori con Cowork

Una volta che `claude` gira sulla VPS, la sessione è raggiungibile da
`claude.ai/code` col tuo account — dal telefono o da un altro computer. È
quello che intendi per Cowork: tu scrivi da dove sei, io opero sulla VPS.

---

## 4. Farlo partire da solo al riavvio

La VPS si riavvia, e un bot che non riparte è un bot spento senza che nessuno
lo sappia.

**Utilità di pianificazione** (`taskschd.msc`) → Crea attività:

- **Generale** → "Esegui indipendentemente dalla connessione", "Esegui con
  privilegi più elevati"
- **Attivazione** → All'avvio del sistema, ritardo 2 minuti *(MT5 deve partire
  prima)*
- **Azioni** → Avvia programma: `C:\nvmfinancebot\avvia.bat`
- **Condizioni** → togli "Avvia solo se il computer è alimentato a corrente"

MT5 va messo in avvio automatico separatamente, e deve **collegarsi da solo**
al conto: in MT5, Strumenti → Opzioni → Server → "Mantieni account personale".

---

## 5. Le tre modalità, in ordine

| `MODE` | Cosa fa |
|---|---|
| `dry_run` | Valuta e registra, **non manda nulla**. Parti da qui. |
| `semi` | Ti avvisa su Telegram e aspetta la tua conferma a mano. |
| `auto` | Manda gli ordini da solo. |

Resta in `dry_run` finché le decisioni registrate non sono quelle che ti
aspetti. Poi `semi`. Poi `auto` **su demo**.

`CONSENTI_CONTO_REALE=false` blocca gli ordini automatici su qualunque conto
non-demo. Non toglierlo finché non hai dati tuoi.

---

## 6. Il freno a mano

Crea un file chiamato `STOP` nella cartella del progetto: blocca **l'apertura**
di nuove posizioni. Non blocca la sorveglianza — un interruttore che smette
anche di proteggere ciò che è già aperto sarebbe un interruttore pericoloso.

Per riprendere, cancella il file.

---

## 7. Cosa guardare

```
http://127.0.0.1:8000/salute            broker, sentinella, mercato, errori
http://127.0.0.1:8000/decisioni         le decisioni con motivo e regole
http://127.0.0.1:8000/posizioni         cosa è aperto e con quali livelli
http://127.0.0.1:8000/cowork/in-attesa  i setup che aspettano il mio giudizio
```

Su Telegram arrivano ordini, TP1, break even e chiusure.

---

## 8. Se qualcosa non va

| sintomo | causa quasi certa |
|---|---|
| `mt5_disponibile: false` | MT5 chiuso, o Python 3.13 |
| ordini rifiutati, simbolo assente | `MT5_SUFFISSO_SIMBOLI` sbagliato |
| il bot non decide mai | archivio troppo corto: `DEF-26` fa tacere i timeframe senza storia |
| `giudizio non disponibile` | `ANTHROPIC_API_KEY` assente o scaduta |
| nessuna candela nuova | Dukascopy risponde 503 sotto carico: i tentativi lo gestiscono, guarda i log |

Il bot **si astiene** in ogni caso dubbio invece di tirare a indovinare. Se
tace, `/decisioni` dice quale regola l'ha fermato.
