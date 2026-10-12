# La rete neurale

Il proprietario, 08/10/2026: *"creiamo la rete neurale ... una volta che l'addestramento è completo, quindi che
comunque il bot riesce a fare le operazioni come nelle foto e ha un RR positivo, allora si fa andare sul demo"*;
11/10/2026: *"iniziamo creando la rete neurale"*. Il bot dal vivo non la usa: si allena e si prova a parte
(`nvm/rete/`, `requirements-rete.txt`).

## Le tre scuole e l'esame

1. **Scuola 1, leggere i grafici da sola**: si nasconde il 15% delle candele e la rete le indovina.
2. **Scuola 2, il metodo delle foto dalle regole degli agenti**: a ogni apertura di una candela a 4 ore risponde come
   gli agenti (`nvm/rete/etichette.py`): direzione di giorno, settimana e mese (`foto.bias_candela`), se apre la
   candela 3 di un CRT a 4 ore o del giorno (`foto.trova`), se e' un setup completo (key level preso e direzione
   dalla sua parte, `foto.direzione`).
3. **Scuola 3, l'occhio del proprietario**: i suoi esempi e le sue correzioni (da fare: i pulsanti, la scuola
   sull'archivio).
4. **Esame** sugli anni che non ha mai visto (dal 2023), con spread e commissioni; solo se passa, il demo.

## Com'e' fatta (`nvm/rete/modello.py`)

- Vede le ultime 40 candele chiuse a 1 ora, 4 ore, giorno, settimana e mese (le candele di MT5), con i prezzi
  rispetto all'ultima chiusura e in unita' del range medio giornaliero (`nvm/rete/finestre.py`).
- Un transformer piccolo (circa 166 mila pesi, 3 strati, 64 numeri per candela) fa parlare fra loro tutte le
  candele di tutti i timeframe; un segnaposto raccoglie il quadro intero.
- Una testa per la scuola 1 e una per ogni domanda della scuola 2.

## Anni

Impara fino al 2019, si controlla sul 2020-2022, esame dal 2023. Dati: le ore di Dukascopy (qui 6 strumenti dal
2006: EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY, XAUUSD).

## Come si allena

    pip install -r requirements-rete.txt   # torch per processore: vedi il file
    python -m nvm.rete.scuola --minuti 45

Pesi e resoconto in `dati/rete/` (non va nel repository).

## Su Kaggle, con la scheda grafica (`kaggle_rete/`)

Lo storico lungo viene da **HistData.com** (gratis, un file zip per anno: nessun limite stretto come Dukascopy).
Due cose scoperte e verificate contro Dukascopy (EURUSD 2006, 2007, 2013, 2019, 2024, GBPUSD 2008, USDJPY 2010,
XAUUSD 2015):

- l'ora di HistData **non** e' New York fisso come dichiarano: segue l'ora legale europea. UTC = ora HistData + 5
  d'inverno, + 4 dall'ultima domenica di marzo all'ultima di ottobre. Dal 2024 i prezzi sono identici a Dukascopy;
  prima vengono da un'altra fonte (stessi orari, qualche pip di differenza);
- alcune serie cambiano natura: il "DXY" prima di dicembre 2018 ha i valori del Dow Jones, il "DAX" 2020-2023
  quelli dell'Euro Stoxx; il WTI manca dal 2024 a maggio 2026; gli anni 2000-2001 hanno prezzi sbagliati.
  `histdata.pezzi_buoni` taglia a ogni salto impossibile (oltre il 40% fra due chiusure orarie) e a ogni buco di
  oltre 10 giorni e tiene ogni pezzo continuo di almeno 4 anni come serie a se'.

Come si lancia: dataset privato su Kaggle con lo zip di `nvm/` e `kaggle_rete/`, notebook con GPU e Internet, e la
cella di `kaggle_rete/cella_kaggle.txt`. Scarica (circa 45 minuti), prepara le finestre una volta sola, allena e
fa l'esame; nella scheda Output restano `occhi.pt` e `resoconto.json`. Risultati della prima notte in
`registro/misure/2026-10-12-rete-kaggle.txt`.

## Passo 2: la scuola dell'esperienza (`kaggle_rete/esperienza.py`, `trader.py`)

Ogni setup che il bot avrebbe visto negli anni, come lo vede dal vivo (`giro.occasioni_foto`: un'occasione per
apertura e verso, il timeframe piu' grande; quadro tagliato all'apertura della candela 3), col trade del bot simulato
ora per ora (`campo.simula`: 25% al TP1 col pareggio, il resto al target finale delle foto, o tutto al TP1; lo stop
vince se una candela tocca tutti e due; commissioni tolte; scadenza `giro.TETTO_FOTO`). HistData ha solo il bid:
l'ask e' bid + uno spread fisso prudente per strumento (`esperienza.SPREAD`). Mancano i setup presi dal DXY.

`python -m kaggle_rete.prepara_casi CARTELLA_DATI casi.npz` prepara i casi (qui, su 4 processori); su Kaggle il
cervello (occhi della prima notte + la "scheda" del setup) impara a stimare l'R di ogni caso. Per confronto lo stesso
cervello senza occhi. Soglie scelte sul 2020-2022, esame dal 2023 contro il bot (A+) e il bot di adesso (A+ e
1:1,5).
