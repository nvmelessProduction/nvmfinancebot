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
