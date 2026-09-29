# I dati dalla VPS alla palestra

La palestra degli agenti (`allena.py`) gira da Claude. Da lì Dukascopy
blocca i download dei prezzi al minuto; dalla VPS no. E le settimane dal
vivo nascono sulla VPS. Per questo la VPS scarica e spedisce, e la palestra
riceve.

Tre passi, una volta sola. Il bot può continuare a girare durante tutto.

## 1. Scaricare vent'anni di prezzi al minuto

Nella cartella del bot sulla VPS (quella con `avvia.bat`), **doppio clic su
`scarica.bat`**.

- La prima volta prepara Python da solo: un paio di minuti.
- Poi scarica un mese alla volta e scrive a che punto è.
- **Ci mette parecchie ore**, anche una notte. Puoi chiudere la finestra
  quando vuoi: al prossimo doppio clic riprende da dove era.
- Occupa qualche GB nella cartella `dati\grezzi`.
- Alla fine scrive `Finito`.

## 2. La chiave per spedire (una volta sola)

La chiave è un segreto: **non mandarla a nessuno, nemmeno a Claude**. Va solo
nel file `.env` della VPS, che non entra mai nel repository.

1. Entra su **github.com** con il tuo account.
2. In alto a destra, clic sulla tua foto → **Settings**.
3. In fondo al menu a sinistra → **Developer settings**.
4. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
5. **Token name**: `bot VPS dati`. **Expiration**: la più lunga che ti offre.
6. **Repository access** → **Only select repositories** → scegli
   `nvmfinancebot`.
7. **Permissions** → **Repository permissions** → **Contents** →
   **Read and write**. Il resto lascialo com'è.
8. In fondo, **Generate token**. Copia la chiave (inizia con `github_pat_`):
   GitHub la mostra una volta sola.
9. Sulla VPS, nella cartella del bot, apri il file `.env` con il **Blocco
   note** e aggiungi in fondo una riga:

   ```
   GITHUB_TOKEN=la_chiave_che_hai_copiato
   ```

   Salva con lo stesso nome (`.env`, non `.env.txt`) e chiudi.

Questa chiave può scrivere solo in questo repository. Se un giorno vuoi
toglierla, la cancelli da GitHub (stesso posto del punto 4) e togli la riga
dal `.env`.

## 3. Spedire

Quando `scarica.bat` ha finito, **doppio clic su `consegna.bat`**.

- Fa candele da 15 minuti dai minuti scaricati (quindici volte più
  leggere), ci aggiunge le decisioni e i risultati del bot dal vivo, e
  spedisce tutto su GitHub in un ramo a parte, `dati-vps`, che non tocca il
  codice.
- Prima di spedire, toglie dal registro del bot ogni valore segreto del
  `.env` (token, password): i segreti non escono mai dalla VPS.
- Alla fine scrive `GitHub: spedito.` Dillo a Claude: prende i dati e li
  porta in palestra.
- Da lì in poi il bot spedisce da solo le settimane dal vivo, ogni sabato
  dopo la riunione.

## 4. Gli altri strumenti

Il bot impara anche dalle altre 23 coppie forex fra le otto valute
principali (EURGBP, GBPJPY, AUDNZD, …), dall'argento, dal petrolio (WTI e
Brent), da sei indici (S&P 500, Nasdaq 100, Dow Jones, DAX, FTSE 100,
Nikkei) e da due crypto (BTCUSD, ETHUSD); l'elenco è in
`nvm/dati/strumenti.py`. Tutti gratis da Dukascopy. Quando `scarica.bat`
ha finito:

1. **Doppio clic su `scarica_nuovi.bat`.** Prima scarica le ore (un paio
   d'ore), poi i minuti (qualche giorno: puoi chiudere e riprendere quando
   vuoi).
2. Quando le ore sono finite, e poi di nuovo quando sono finiti i minuti,
   **doppio clic su `consegna.bat`**: spedisce quello che c'è di nuovo.

## 5. I video di Romeo

Claude studia i video di Romeo guardando i grafici mentre legge le sue
parole. YouTube blocca gli scaricamenti dai server (anche dalla VPS): si
fanno dal **computer di casa**.

1. Sul computer di casa estrai `RomeoVideo.zip` (te lo manda Claude; dentro
   ci sono `scarica_video.bat` e `video.py`) e fai **doppio clic su
   `scarica_video.bat`**. La prima volta installa Python da solo. Per ogni
   video prende un fotogramma ogni 15 secondi e i sottotitoli, poi cancella
   il video. Circa un'ora; puoi chiudere e riprendere quando vuoi.
2. Alla fine nella cartella c'è `video_romeo.zip`: copialo sulla VPS, nella
   cartella del bot o sul Desktop, e sulla VPS **doppio clic su
   `consegna.bat`**. Lo apre e lo spedisce.

## Se qualcosa va storto

| Cosa vedi | Cosa vuol dire |
|---|---|
| `TroppeRichieste` | Dukascopy ha smesso di rispondere per un po'. Aspetta mezz'ora e rilancia `scarica.bat` |
| `Manca GITHUB_TOKEN nel file .env` | manca la riga del punto 2.9, o il file non si chiama `.env` |
| `GitHub non accetta i dati` | la chiave è sbagliata, scaduta o senza **Contents: Read and write**: rifai il punto 2 |
| `YouTube chiude tutte le porte a questa VPS` | YouTube blocca la VPS. Mandane la foto a Claude |
| `python non è riconosciuto` | manca Python. Installalo da python.org, spuntando "Add Python to PATH" |
| qualsiasi altro errore | manda a Claude una foto della finestra (senza la chiave in vista) |
