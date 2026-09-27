# I cervelli degli agenti

> **Stato:** 27/09/2026. L'utente: *"tutti gli agenti devono essere intelligenti, capaci
> di ragionare, pensare, confrontarsi con gli altri agenti in maniera intelligente,
> modificarsi autonomamente… il mercato dei 20 anni serviva solo per l'addestramento, adesso
> devono vivere nel mondo reale"*.

## Cosa sono

Ogni agente (Cacciatore, Grilletto, Livelli, Key level, Orario, Bias) ha un cervello: una
rete neurale piccola scritta da noi in numpy (`nvm/cervello/rete.py`), senza AI esterne.

- **Vede** il mercato nel suo campo (`viste.py`): le candele e le misure del suo mestiere al
  momento dell'ingresso, nel verso dell'operazione e in unità del range (29-56 numeri).
  Le viste sono le stesse sullo storico e dal vivo.
- **Giudica**: quanto crede che l'operazione guadagni (impara se ha guadagnato, pesato per
  quanto: una perdita grande insegna più di una piccola).
- **Si confronta** (`squadra.py`): un secondo cervello per agente riceve quello che vede lui
  più i giudizi dei colleghi e decide se cambiare idea. Quando qualcuno cambia idea si
  calcola chi l'ha convinto (il suo giudizio rifatto senza quel collega).
- **Il Capo** mette insieme i giudizi dopo il confronto (regressione logistica).
- **A scuola** sui vent'anni ogni pezzo impara solo da giudizi su esempi che i pezzi prima
  di lui non avevano visto. Quello che sanno sta nei pesi: dal vivo non rileggono lo storico.
- **Dal vivo** (`dal_vivo.py`) giudicano ogni occasione; dopo ogni risultato vero (presa o
  seguita sulla carta) ogni cervello e il Capo imparano un passo. Gli esempi dal vivo restano
  in `dati/vivo/cervelli_esempi.jsonl` e si reimparano quando torna la squadra di scuola.
- **Ogni settimana** (`scuola.py`, dentro `capo.py --vivo`) tornano a scuola e fanno
  l'esame contro il Capo di oggi: stesse occasioni, stesso Rischio, conto intero fuori
  campione 2012-2023 (ogni anno deciso solo con gli anni prima). Se fanno crescere il conto
  di più senza superare il calo del profilo, **decidono loro** (con la loro fiducia al posto
  del Kelly, e parte e fiducia minima imparate per loro); altrimenti restano **in prova**.

## Com'è andata la prima volta (27/09/2026, 6 strumenti)

| | Prevedere il primo obiettivo (log-loss, più basso è meglio) | Conto intero fuori campione 2012-2023 |
|---|---|---|
| Capo di oggi | 0,6122 | +1,7% l'anno, calo 19% |
| Cervelli senza confronto | 0,6047 | +0,7% l'anno, calo 8% |
| Cervelli col confronto | 0,6055 | 0,0% l'anno, calo 9% |

I cervelli **vedono meglio** del Capo di oggi (prevedono meglio il primo obiettivo) e più
sono sicuri meglio va (sopra 55 su 100: +0,08 R a operazione, anche nel 2017-2023), ma sul
conto intero **non guadagnano di più**. Il confronto per ora non aggiunge niente. Restano in
prova: dal vivo giudicano, si confrontano e imparano, e su Telegram si vede il loro
ragionamento e la gara di ogni sera con il Capo.

Prima di questi è stata provata una memoria dei casi simili (`memoria.py`: sfogliare lo
storico a ogni occasione): peggiorava le decisioni in tutte le varianti. Scartata.

## Cosa manca

- Più dati: con 40 strumenti gli esempi diventano circa sei volte tanti, e le reti ne hanno
  bisogno più di una formula semplice.
- Che cambino da soli la propria forma (quanti neuroni, cosa guardano) in palestra, tenendo
  solo quello che passa l'esame.
